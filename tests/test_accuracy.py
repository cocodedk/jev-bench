"""Independent accuracy contracts with hand-calculated asymmetric errors."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from jev_bench import accuracy, config, reporting, runner


class AccuracyTests(unittest.TestCase):
    @staticmethod
    def row(expected, predicted, index=0, **extra):
        return {"model_name": "jev", "pair": index, "warmup": False, "ok": True,
                "case_id": f"case-{index}", "text": f"Input {index}",
                "expected": expected, "label": predicted, "latency_ms": 10, "wall_ms": 12, **extra}

    def asymmetric(self):
        return [self.row(expected, predicted, i) for i, (expected, predicted) in enumerate(
            [("a", "a"), ("a", "b"), ("a", "b"), ("b", "a"), ("b", "b"), ("c", "b")])]

    def test_asymmetric_precision_recall_and_macro(self):
        metrics = accuracy.classification_metrics(self.asymmetric(), ["a", "b", "c", "absent"])
        self.assertEqual((metrics["correct"], metrics["valid"], metrics["wrong"]), (2, 6, 4))
        self.assertAlmostEqual(metrics["accuracy_pct"], 100 / 3)
        classes = {item["label"]: item for item in metrics["classes"]}
        self.assertEqual((classes["a"]["support"], classes["a"]["predicted"], classes["a"]["correct"]), (3, 2, 1))
        self.assertAlmostEqual(classes["a"]["precision_pct"], 50)
        self.assertAlmostEqual(classes["a"]["recall_pct"], 100 / 3)
        self.assertAlmostEqual(classes["a"]["f1_pct"], 40)
        self.assertEqual((classes["b"]["support"], classes["b"]["predicted"]), (2, 4))
        self.assertAlmostEqual(classes["b"]["precision_pct"], 25)
        self.assertAlmostEqual(classes["b"]["recall_pct"], 50)
        self.assertAlmostEqual(classes["b"]["f1_pct"], 100 / 3)
        self.assertAlmostEqual(metrics["macro_f1_pct"], (40 + 100 / 3) / 4)

    def test_absent_and_unpredicted_classes_are_zero(self):
        metrics = accuracy.classification_metrics(self.asymmetric(), ["a", "b", "c", "absent"])
        classes = {item["label"]: item for item in metrics["classes"]}
        for label in ["c", "absent"]:
            for key in ["precision_pct", "recall_pct", "f1_pct"]:
                self.assertEqual(classes[label][key], 0)
        self.assertEqual(classes["c"]["support"], 1)
        self.assertEqual(classes["absent"]["support"], 0)

    def test_confusions_are_directional_sorted_and_exclude_correct(self):
        self.assertEqual(accuracy.classification_metrics(self.asymmetric())["confusions"], [
            {"expected": "a", "predicted": "b", "count": 2},
            {"expected": "b", "predicted": "a", "count": 1},
            {"expected": "c", "predicted": "b", "count": 1}])

    def test_every_mistake_retains_text_and_repeated_attempts(self):
        rows = [self.row("a", "b", 5), self.row("a", "a", 6), self.row("a", "b", 5)]
        expected = {"case_id": "case-5", "text": "Input 5", "expected": "a", "predicted": "b"}
        self.assertEqual(accuracy.classification_metrics(rows)["mistakes"], [expected, expected])

    def test_warmup_and_invalid_predictions_do_not_change_metrics(self):
        base = [self.row("a", "a")]
        rows = base + [self.row("a", "b", warmup=True), self.row("b", "a", ok=False),
                       {"model_name": "jev", "pair": 4, "expected": "b", "warmup": False, "ok": False}]
        self.assertEqual(accuracy.classification_metrics(rows, ["a", "b"]),
                         accuracy.classification_metrics(base, ["a", "b"]))

    def test_no_valid_results_are_null_not_perfect_or_zero_accuracy(self):
        for rows in [[], [{"warmup": False, "ok": False, "expected": "a"}]]:
            metrics = accuracy.classification_metrics(rows, ["a", "b"])
            self.assertIsNone(metrics["accuracy_pct"])
            self.assertIsNone(metrics["macro_f1_pct"])
            self.assertEqual((metrics["correct"], metrics["valid"], metrics["wrong"]), (0, 0, 0))
            self.assertEqual(len(metrics["classes"]), 2)
            self.assertEqual((metrics["confusions"], metrics["mistakes"]), ([], []))

    def test_fallback_labels_include_expected_and_predicted(self):
        metrics = accuracy.classification_metrics([self.row("a", "b")])
        self.assertEqual({c["label"] for c in metrics["classes"]}, {"a", "b"})
        self.assertEqual((metrics["accuracy_pct"], metrics["macro_f1_pct"]), (0, 0))

    def test_summary_keeps_error_skip_wrong_and_model_denominators_separate(self):
        rows = [self.row("a", "a"), self.row("a", "b", 1), self.row("b", "b", 2, ok=False),
                self.row("a", "b", 3, warmup=True), self.row("a", "a", 4, model_name="other")]
        summary = reporting.summarize(rows, ["jev", "other", "missing"], 4, ["a", "b"])["models"]
        stats = summary["jev"]
        self.assertEqual((stats["attempts"], stats["valid_responses"], stats["errors"], stats["skipped"]), (3, 2, 1, 1))
        self.assertEqual((stats["correct_labels"], stats["accuracy_denominator"]), (1, 2))
        self.assertEqual(stats["accuracy"]["accuracy_pct"], 50)
        self.assertEqual(summary["other"]["accuracy"]["accuracy_pct"], 100)
        self.assertIsNone(summary["missing"]["accuracy"]["accuracy_pct"])

    def test_runner_passes_declared_labels_and_holds_back_answers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = {"name": "fixture", "labels": ["a", "b", "absent"], "instructions": "Classify.",
                       "cases": [{"id": "secret-id", "text": "public input", "expected": "a"}]}
            (root / "data.json").write_text(json.dumps(dataset))
            (root / "config.json").write_text(json.dumps({"dataset": "data.json", "warmups": 0,
                "models": [{"name": "jev", "adapter": "openrouter-decisions", "model": "fixture"}]}))
            requests = []

            def execute(request, _timeout):
                requests.append(request)
                return {"ok": True, "label": "a", "latency_ms": 1, "wall_ms": 2}

            with contextlib.redirect_stdout(io.StringIO()):
                result = runner.run_experiment(config.load_experiment(root / "config.json"), root / "out", execute)
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0]["dataset"], {"labels": dataset["labels"], "instructions": "Classify."})
            self.assertEqual(requests[0]["text"], "public input")
            self.assertNotIn("secret-id", json.dumps(requests))
            self.assertNotIn("expected", json.dumps(requests))
            self.assertAlmostEqual(result["summary"]["models"]["jev"]["accuracy"]["macro_f1_pct"], 100 / 3)
            saved = json.loads((root / "out/results.json").read_text())
            self.assertEqual(saved["summary"], result["summary"])

    def test_original_baselines_recompute_identical_correctness(self):
        root = Path(__file__).resolve().parents[1]
        paths = [root / "results" / name / "results.json" for name in (
            "baseline-2026-09-21", "baseline-classifier-models-2026-09-21", "baseline-workbench-2026-09-21")]
        for path in paths:
            result = json.loads(path.read_text())
            rows = [json.loads(line) for line in path.with_name("samples.jsonl").read_text().splitlines() if line.strip()]
            models = result["summary"].get("models", {k: v for k, v in result["summary"].items() if k != "paired"})
            for name, stats in models.items():
                selected = [row for row in rows if row.get("model_name", row.get("provider")) == name]
                metrics = accuracy.classification_metrics(selected)
                self.assertEqual((metrics["correct"], metrics["valid"]), (stats["correct_labels"], stats["valid_responses"]))

    def test_publication_derives_legacy_accuracy_without_changing_raw_results(self):
        import test_publication
        fixture = test_publication.PublicationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.prepare()
        source_bytes = (fixture.source / "results.json").read_bytes()
        row = self.row("a", "a", model_name="custom-name")
        (fixture.source / "samples.jsonl").write_text(json.dumps(row) + "\n")
        test_publication.BUILDER.build(fixture.root)
        run = json.loads((fixture.root / "website/data/runs.json").read_text())["runs"][0]
        self.assertEqual(run["models"][0]["accuracy"]["accuracy_pct"], 100)
        self.assertEqual((fixture.root / "website/data/selected.json").read_bytes(), source_bytes)
        row["provider"] = row.pop("model_name")
        row["provider"] = "jev-decisions"
        stats = {k: v for k, v in fixture.stats.items() if k not in {"planned", "skipped", "returned_models"}}
        stats["models"] = ["old-version"]
        fixture.result = {"rounds": 1, "expected_measured_pairs": 2, "started_utc": "old", "complete": False,
                          "summary": {"jev-decisions": stats, "paired": {}}}
        fixture.prepare()
        (fixture.source / "samples.jsonl").write_text(json.dumps(row) + "\n")
        test_publication.BUILDER.build(fixture.root)
        run = json.loads((fixture.root / "website/data/runs.json").read_text())["runs"][0]
        self.assertEqual(run["models"][0]["accuracy"]["correct"], 1)

    def test_publication_rejects_external_samples_symlink(self):
        import test_publication
        fixture = test_publication.PublicationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.prepare()
        external = fixture.root / "unselected-samples.jsonl"
        external.write_text(json.dumps(self.row("a", "a")) + "\n")
        (fixture.source / "samples.jsonl").symlink_to(external)
        with self.assertRaises(ValueError):
            test_publication.BUILDER.build(fixture.root)
        self.assertFalse((fixture.root / "website").exists())
