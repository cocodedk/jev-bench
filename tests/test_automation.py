"""Independent publication gate; git/network and benchmark calls remain mocked."""
import contextlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("run_and_publish", Path(__file__).resolve().parents[1] / "scripts/run_and_publish.py")
assert SPEC is not None and SPEC.loader is not None
AUTOMATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUTOMATION)


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "results/run-fixture"
        self.source.mkdir(parents=True)
        self.result = {"schema_version": 1, "dataset": {"name": "fixture", "labels": ["a", "b"], "cases": [{}]},
                       "config": {"models": [{"name": "jev"}], "rounds": 1}, "attempts_used": 1}
        for name in AUTOMATION.ARTIFACTS:
            (self.source / name).write_text(json.dumps(self.result) if name == "results.json" else "fixture")
        (self.root / "published-runs.json").write_text('{"runs": []}')
        self.calls = []
        self.staged = False

    def git(self, _root, *args):
        self.calls.append(args)
        answers = {("rev-parse", "--show-toplevel"): str(self.root), ("branch", "--show-current"): "main",
                   ("remote", "get-url", "origin"): "https://github.com/cocodedk/jev-bench.git",
                   ("rev-parse", "HEAD"): "same", ("rev-parse", "origin/main"): "same"}
        if args[0] == "add":
            self.staged = True
        if args == ("diff", "--cached", "--name-only") and self.staged:
            return "published-runs.json\nwebsite/data/runs.json"
        return answers.get(args, "")

    def test_preflight_rejects_unsafe_state_before_fetch(self):
        for target, answer in [(('rev-parse', '--show-toplevel'), '/elsewhere'),
                               (('branch', '--show-current'), 'feature'),
                               (('status', '--porcelain'), '?? private.txt'),
                               (('remote', 'get-url', 'origin'), 'https://github.com/other/repo.git')]:
            self.calls.clear()

            def fake(root, *args, answer=answer, target=target):
                baseline = self.git(root, *args)
                return answer if args == target else baseline

            with patch.object(AUTOMATION, "git", side_effect=fake), self.assertRaises(ValueError):
                AUTOMATION.preflight(self.root)
            self.assertFalse(any(args[0] == "fetch" for args in self.calls))

    def test_preflight_requires_remote_head_match(self):
        def fake(root, *args):
            baseline = self.git(root, *args)
            return "behind" if args == ("rev-parse", "origin/main") else baseline
        with patch.object(AUTOMATION, "git", side_effect=fake), self.assertRaises(ValueError):
            AUTOMATION.preflight(self.root)
        self.assertIn(("fetch", "origin", "main"), self.calls)

    def test_publish_copies_only_artifacts_and_stages_exact_scope(self):
        (self.source / ".env").write_text("dummy-not-public")
        with patch.object(AUTOMATION, "git", side_effect=self.git), patch.object(AUTOMATION.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)):
            self.assertEqual(AUTOMATION.publish_run(self.root, self.source), AUTOMATION.PAGE_URL)
        dest = self.root / "results/published/run-fixture"
        self.assertEqual({p.name for p in dest.iterdir()}, set(AUTOMATION.ARTIFACTS))
        manifest = json.loads((self.root / "published-runs.json").read_text())
        self.assertEqual(manifest['runs'][0]['path'], 'results/published/run-fixture')
        add = next(args for args in self.calls if args[0] == "add")
        self.assertEqual(set(add[2:]), {f"results/published/run-fixture/{name}" for name in AUTOMATION.ARTIFACTS} | {"published-runs.json", "website/data/runs.json", "website/data/run-fixture.csv", "website/data/run-fixture.json"})
        self.assertEqual(self.calls[-1], ("push", "origin", "main"))

    def test_duplicate_and_artifact_links_rejected_before_mutation(self):
        manifest = self.root / "published-runs.json"
        manifest.write_text('{"runs": [{"id": "run-fixture"}]}')
        original = manifest.read_bytes()
        with patch.object(AUTOMATION, "git", side_effect=self.git), self.assertRaises(ValueError):
            AUTOMATION.publish_run(self.root, self.source)
        self.assertEqual(manifest.read_bytes(), original)
        self.assertFalse((self.root / "results/published").exists())
        manifest.write_text('{"runs": []}')
        artifact = self.source / "samples.csv"
        artifact.unlink()
        artifact.symlink_to(self.root / "published-runs.json")
        with patch.object(AUTOMATION, "git", side_effect=self.git), self.assertRaises(ValueError):
            AUTOMATION.publish_run(self.root, self.source)
        self.assertFalse((self.root / "results/published").exists())

    def test_destination_symlink_cannot_escape_repository(self):
        with tempfile.TemporaryDirectory() as external:
            (self.root / "results/published").symlink_to(external, target_is_directory=True)
            with patch.object(AUTOMATION, "git", side_effect=self.git), self.assertRaises(ValueError):
                AUTOMATION.publish_run(self.root, self.source)
            self.assertEqual(list(Path(external).iterdir()), [])

    def test_build_failure_does_not_commit_or_push_and_retains_run(self):
        with patch.object(AUTOMATION, "git", side_effect=self.git), patch.object(AUTOMATION.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)), self.assertRaises(RuntimeError):
            AUTOMATION.publish_run(self.root, self.source)
        self.assertFalse(any(args[0] in {"add", "commit", "push"} for args in self.calls))
        self.assertTrue((self.source / "results.json").is_file())

    def test_git_errors_do_not_expose_command_output(self):
        with patch.object(AUTOMATION.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "dummy-secret", "dummy-secret")), self.assertRaises(RuntimeError) as caught:
            AUTOMATION.git(self.root, "push", "origin", "main")
        self.assertNotIn("dummy-secret", str(caught.exception))

    def test_dry_run_does_not_call_git_or_publish(self):
        with patch.object(AUTOMATION.sys, "argv", ["script", "--config", "fixture.json", "--dry-run"]), patch.object(AUTOMATION, "git") as git, patch.object(AUTOMATION, "publish_run") as publish, patch.object(AUTOMATION.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertEqual(AUTOMATION.main(), 0)
        git.assert_not_called()
        publish.assert_not_called()
        self.assertIn("--dry-run", run.call_args.args[0])

    def test_existing_run_performs_no_inference(self):
        with patch.object(AUTOMATION.sys, "argv", ["script", "--existing-run", str(self.source)]), patch.object(AUTOMATION, "publish_run", return_value=AUTOMATION.PAGE_URL) as publish, patch.object(AUTOMATION.subprocess, "run") as run, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(AUTOMATION.main(), 0)
        run.assert_not_called()
        publish.assert_called_once()

    def test_failed_preflight_prevents_benchmark_call(self):
        with patch.object(AUTOMATION.sys, "argv", ["script", "--config", "fixture.json"]), patch.object(AUTOMATION, "preflight", side_effect=ValueError("fixture")), patch.object(AUTOMATION.subprocess, "run") as run, contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            AUTOMATION.main()
        run.assert_not_called()

    def test_partial_run_is_published_and_preserves_failure_exit(self):
        def run(command, **_kwargs):
            source = Path(command[command.index("--output") + 1])
            source.mkdir(parents=True)
            (source / "results.json").write_text('{"complete": false}')
            return subprocess.CompletedProcess(command, 1)
        with patch.object(AUTOMATION, "ROOT", self.root), patch.object(AUTOMATION.sys, "argv", ["script", "--config", "fixture.json"]), patch.object(AUTOMATION, "preflight") as preflight, patch.object(AUTOMATION.subprocess, "run", side_effect=run), patch.object(AUTOMATION, "publish_run", return_value=AUTOMATION.PAGE_URL) as publish, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(AUTOMATION.main(), 1)
        preflight.assert_called_once_with(self.root)
        publish.assert_called_once()
        self.assertTrue((publish.call_args.args[1] / "results.json").is_file())

    def test_missing_results_prevents_publication(self):
        with patch.object(AUTOMATION, "ROOT", self.root), patch.object(AUTOMATION.sys, "argv", ["script", "--config", "fixture.json"]), patch.object(AUTOMATION, "preflight"), patch.object(AUTOMATION.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)), patch.object(AUTOMATION, "publish_run") as publish:
            self.assertEqual(AUTOMATION.main(), 1)
        publish.assert_not_called()

    def test_push_failure_retains_original_and_published_results(self):
        def fake(root, *args):
            result = self.git(root, *args)
            if args[0] == "push":
                raise RuntimeError("push fixture failure")
            return result
        with patch.object(AUTOMATION, "git", side_effect=fake), patch.object(AUTOMATION.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)), self.assertRaises(RuntimeError):
            AUTOMATION.publish_run(self.root, self.source)
        self.assertTrue((self.source / "results.json").is_file())
        self.assertTrue((self.root / "results/published/run-fixture/results.json").is_file())
        self.assertTrue(any(args[0] == "commit" for args in self.calls))
