"""Publication selects explicit runs and blocks external source artifacts."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("build_site_data", Path(__file__).resolve().parents[1] / "scripts/build_site_data.py")
assert SPEC is not None and SPEC.loader is not None
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "results" / "selected"
        self.source.mkdir(parents=True)
        self.entry = {"id": "selected", "path": "results/selected", "title": "Synthetic", "subtitle": "Fixture", "dataset": "Synthetic", "notes": []}
        self.stats = {"planned": 2, "attempts": 1, "valid_responses": 1, "correct_labels": 1, "errors": 0,
                      "skipped": 1, "returned_models": ["actual-version"], "mean_ms": 10, "median_ms": 10, "p95_ms": 10}
        self.result = {"schema_version": 1, "config": {"rounds": 1}, "planned_measured_per_model": 2,
                       "started_utc": "synthetic", "complete": False, "summary": {"models": {"custom-name": self.stats}, "paired": []}}
        (self.source / "samples.csv").write_text("synthetic,csv\n")
        (self.source / "attempts.jsonl").write_text('{}\n\n{}\n')

    def prepare(self, entries=None):
        (self.root / "published-runs.json").write_text(json.dumps({"runs": entries if entries is not None else [self.entry]}))
        (self.source / "results.json").write_text(json.dumps(self.result))

    def test_selected_only_and_stale_cleanup(self):
        self.prepare()
        unselected = self.root / "results" / "private"
        unselected.mkdir()
        (unselected / "results.json").write_text("not-selected")
        destination = self.root / "website" / "data"
        destination.mkdir(parents=True)
        (destination / "old.json").write_text("old")
        self.assertEqual(BUILDER.build(self.root), 1)
        self.assertEqual({p.name for p in destination.iterdir()}, {"runs.json", "selected.json", "selected.csv"})
        self.assertEqual((destination / "selected.json").read_bytes(), (self.source / "results.json").read_bytes())

    def test_v1_normalization_incomplete_counts(self):
        self.prepare()
        BUILDER.build(self.root)
        run = json.loads((self.root / "website/data/runs.json").read_text())["runs"][0]
        self.assertEqual((run["attempts_used"], run["measured_calls"], run["cases"]), (2, 1, 2))
        self.assertEqual(run["models"][0]["skipped"], 1)
        self.assertEqual(run["models"][0]["label"], "custom-name")
        self.assertEqual(run["models"][0]["returned_models"], ["actual-version"])
        self.assertFalse(run["complete"])

    def test_legacy_normalization(self):
        stats = {k: v for k, v in self.stats.items() if k not in {"planned", "skipped", "returned_models"}}
        stats["models"] = ["old-version"]
        self.result = {"rounds": 1, "expected_measured_pairs": 2, "started_utc": "old", "complete": False,
                       "summary": {"jev-decisions": stats, "paired": {}}}
        self.prepare()
        BUILDER.build(self.root)
        model = json.loads((self.root / "website/data/runs.json").read_text())["runs"][0]["models"][0]
        self.assertEqual(model["returned_models"], ["old-version"])
        self.assertEqual(model["skipped"], 1)

    def test_external_source_rejected(self):
        self.entry["path"] = "../external"
        self.prepare()
        with self.assertRaises(ValueError):
            BUILDER.build(self.root)
        self.assertFalse((self.root / "website").exists())

    def test_external_artifact_symlink_rejected(self):
        self.prepare()
        external = self.root / "outside.csv"
        external.write_text("not-public")
        artifact = self.source / "samples.csv"
        artifact.unlink()
        try:
            artifact.symlink_to(external)
        except OSError:
            self.skipTest("Symlink creation unavailable on this platform")
        with self.assertRaises(ValueError):
            BUILDER.build(self.root)

    def test_duplicate_and_unsafe_ids_rejected(self):
        for entries in [[self.entry, self.entry], [{**self.entry, "id": "../escape"}], []]:
            self.prepare(entries)
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                BUILDER.build(self.root)
