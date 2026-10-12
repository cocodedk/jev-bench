"""Independent offline contract checks; no provider calls escape mocks."""
import contextlib
import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jev_bench import cli, config, providers, reporting, runner, worker


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dataset = {"name": "synthetic", "labels": ["yes", "no"], "instructions": "Classify as yes or no",
                        "cases": [{"id": str(i), "text": f"Synthetic {i}", "expected": "yes"} for i in range(6)]}
        self.models = [{"name": name, "adapter": "classifier.dev", "model": "jev"} for name in "abc"]
        self.settings = {"dataset": "data.json", "models": self.models, "warmups": 1}
        self.path = self.root / "experiment.json"

    def experiment(self):
        self.path.write_text(json.dumps(self.settings))
        (self.root / "data.json").write_text(json.dumps(self.dataset))
        return config.load_experiment(self.path)

    def test_default_budget(self):
        exp = self.experiment()
        self.assertEqual((exp.measured_per_model, exp.attempt_budget), (6, 21))

    def test_single_model_and_repeated_adapter(self):
        self.models[:] = self.models[:1]
        self.assertEqual(self.experiment().attempt_budget, 7)

    def test_unknown_fields_reject_credentials(self):
        self.settings["api_key"] = "dummy-never-real"
        with self.assertRaises(ValueError):
            self.experiment()

    def test_duplicate_model_names(self):
        self.models[1]["name"] = "a"
        with self.assertRaises(ValueError):
            self.experiment()

    def test_numeric_config_boundaries(self):
        for value in [True, 0, 101, 1.5]:
            self.settings["rounds"] = value
            with self.subTest(value=value), self.assertRaises((TypeError, ValueError)):
                self.experiment()

    def test_invalid_adapter_and_tier(self):
        for change in [{"adapter": "generic"}, {"tier": "invalid"}, {"model": "unknown"}]:
            original = self.models[0].copy()
            self.models[0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.experiment()
            self.models[0] = original

    def test_duplicate_and_unknown_dataset_labels(self):
        for labels in [["yes", "yes"], ["up", "down"]]:
            self.dataset["labels"] = labels
            with self.assertRaises(ValueError):
                self.experiment()

    def test_duplicate_case_including_warmup(self):
        self.dataset["warmup"] = self.dataset["cases"][0].copy()
        with self.assertRaises(ValueError):
            self.experiment()

    def test_strict_json(self):
        for value in ['{"a":1,"a":2}', 'NaN', 'Infinity', '-Infinity', '1e999', '-1e999']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                config.loads(value)

    def test_payload_equivalence(self):
        left = providers.make_payload({"adapter": "openrouter-decisions", "model": "v2"}, self.dataset, "same")
        right = providers.make_payload(self.models[0], self.dataset, "same")
        self.assertEqual(left["state"], right["inputs"][0])
        self.assertEqual(list(left["questions"]["category"]["criteria"]), right["labels"])
        self.assertEqual(left["questions"]["category"]["instructions"], right["instructions"])
        self.assertEqual(left["model"], "v2")

    def test_auth_isolation(self):
        response = {"results": [{"label": "yes"}]}
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "dummy-only"}), patch.object(providers.urllib.request, "build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = json.dumps(response).encode()
            providers.request_classification(self.models[0], self.dataset, "same", 1)
            self.assertIsNone(opener.return_value.open.call_args.args[0].get_header("Authorization"))
            response = {"answers": {"category": {"type": "choice", "choice": "yes", "probabilities": {"yes": 1, "no": 0}, "confidence": 1}}}
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = json.dumps(response).encode()
            providers.request_classification({"adapter": "openrouter-decisions", "model": "v2"}, self.dataset, "same", 1)
            self.assertEqual(opener.return_value.open.call_args.args[0].get_header("Authorization"), "Bearer dummy-only")

    def test_missing_key_before_network(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(providers.urllib.request, "build_opener") as opener:
            with self.assertRaises(ValueError):
                providers.request_classification({"adapter": "openrouter-decisions", "model": "v2"}, self.dataset, "x", 1)
            opener.assert_not_called()

    def test_classifier_malformed(self):
        for raw in [[], {}, {"results": []}, {"results": [None]}, {"results": [{"label": "unknown"}]}, {"error": "x"}]:
            with self.subTest(raw=raw), self.assertRaises((ValueError, TypeError)):
                providers.decode_result(self.models[0], self.dataset, raw)

    def test_invalid_confidence(self):
        for confidence in [True, -1, 2, float("nan"), float("inf"), "high"]:
            with self.subTest(confidence=confidence), self.assertRaises((ValueError, TypeError)):
                providers.decode_result(self.models[0], self.dataset, {"results": [{"label": "yes", "confidence": confidence}]})

    def test_jev_invalid_probabilities(self):
        model = {"adapter": "openrouter-decisions"}
        for scores in [{"yes": .2, "no": .2}, {"yes": .1, "no": .9}, {"yes": True, "no": 0}, {"yes": 1}]:
            raw = {"answers": {"category": {"type": "choice", "choice": "yes", "confidence": .9, "probabilities": scores}}}
            with self.subTest(scores=scores), self.assertRaises((ValueError, TypeError)):
                providers.decode_result(model, self.dataset, raw)

    def test_noul_and_score_payloads(self):
        model = {"adapter": "openrouter-decisions", "model": "v2"}
        noul = {**self.dataset, "type": "noul", "labels": ["true", "false"]}
        self.assertNotIn("criteria", providers.make_payload(model, noul, "x")["questions"]["category"])
        noul["criteria"] = {"true": "safe", "false": "unsafe"}
        self.assertEqual(providers.make_payload(model, noul, "x")["questions"]["category"],
                         {"type": "noul", "instructions": noul["instructions"], "criteria": noul["criteria"]})
        score = {**self.dataset, "type": "score", "labels": ["low", "mid", "high"],
                 "criteria": {"low": "L", "mid": "M", "high": "H"}}
        self.assertEqual(providers.make_payload(model, score, "x")["questions"]["category"]["criteria"], ["L", "M", "H"])

    def test_noul_and_score_answers(self):
        model = {"adapter": "openrouter-decisions"}
        noul = {**self.dataset, "type": "noul", "labels": ["true", "false"]}
        for truth, label, confidence in [(0.9, "true", 0.9), (0.5, "true", 0.5), (0.2, "false", 0.8)]:
            raw = {"answers": {"category": {"type": "noul", "noul": truth}}}
            result = providers.decode_result(model, noul, raw)
            self.assertEqual((result["label"], result["confidence"]), (label, confidence))
        score = {**self.dataset, "type": "score", "labels": ["low", "mid", "high"]}
        probabilities = {"0": 0.1, "1": 0.3, "2": 0.6}
        for value, label in [(0, "low"), (0.5, "mid"), (1.49, "mid"), (1.5, "high"), (2, "high")]:
            raw = {"answers": {"category": {"type": "score", "score": value, "probabilities": probabilities, "confidence": .7}}}
            self.assertEqual(providers.decode_result(model, score, raw)["label"], label)
        for answer in [{"type": "choice", "choice": "low"}, {"type": "score", "score": 3, "probabilities": probabilities, "confidence": .7},
                       {"type": "score", "score": True, "probabilities": probabilities, "confidence": .7},
                       {"type": "score", "score": 1, "probabilities": {"0": 1}, "confidence": .7}]:
            with self.subTest(answer=answer), self.assertRaises((ValueError, TypeError)):
                providers.decode_result(model, score, {"answers": {"category": answer}})
        for truth in [True, 1.5, None]:
            with self.subTest(truth=truth), self.assertRaises((ValueError, TypeError)):
                providers.decode_result(model, noul, {"answers": {"category": {"type": "noul", "noul": truth}}})

    def test_question_type_dataset_rules(self):
        def dataset(kind, labels, **extra):
            return {**self.dataset, "type": kind, "labels": labels, **extra,
                    "cases": [{"id": "1", "text": "t", "expected": labels[0]}]}
        config.validate_dataset(dataset("noul", ["true", "false"]))
        config.validate_dataset(dataset("score", [str(i) for i in range(10)]))
        for bad in [dataset("judge", ["yes", "no"]), dataset("noul", ["false", "true"]),
                    dataset("score", [str(i) for i in range(11)]), dataset("choice", ["yes", "no"], criteria={"yes": "y"}),
                    dataset("choice", ["yes", "no"], criteria={"yes": "y", "no": ""})]:
            with self.subTest(bad=bad), self.assertRaises((ValueError, TypeError)):
                config.validate_dataset(bad)
        for change in [{"type": "score"}, {"criteria": {"yes": "y", "no": "n"}}]:
            self.dataset = {key: value for key, value in self.dataset.items() if key not in ("type", "criteria")}
            self.dataset.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.experiment()
        self.settings["models"] = [{"name": "j", "adapter": "openrouter-decisions", "model": "v2"}]
        self.assertEqual(self.experiment().dataset["criteria"], {"yes": "y", "no": "n"})

    def test_runner_sends_type_and_criteria(self):
        self.dataset.update(type="noul", labels=["true", "false"], criteria={"true": "t", "false": "f"},
                            cases=[{"id": "1", "text": "t", "expected": "true"}])
        self.settings.update(models=[{"name": "j", "adapter": "openrouter-decisions", "model": "v2"}], warmups=0)
        sent = []
        def execute(request, _timeout):
            sent.append(request["dataset"])
            return {"ok": True, "label": "true", "confidence": 1, "returned_model": None, "latency_ms": 1, "wall_ms": 1}
        with contextlib.redirect_stdout(io.StringIO()):
            runner.run_experiment(self.experiment(), self.root / "out", execute)
        self.assertEqual(sent, [{key: self.dataset[key] for key in ("type", "labels", "criteria", "instructions")}])

    def test_response_size_and_nonfinite(self):
        for body in [b'x' * (providers.MAX_RESPONSE_BYTES + 1), b'{"x":1e999}']:
            with patch.object(providers.urllib.request, "build_opener") as opener:
                opener.return_value.open.return_value.__enter__.return_value.read.return_value = body
                with self.assertRaises(ValueError):
                    providers.request_classification(self.models[0], self.dataset, "same", 1)

    def test_schedule_balances_three_positions(self):
        exp = self.experiment()
        original = copy.deepcopy(exp.dataset)
        schedule = runner.plan(exp)
        self.assertEqual(schedule, runner.plan(exp))
        self.assertEqual(exp.dataset, original)
        counts = {name: [0, 0, 0] for name in "abc"}
        for pair in range(6):
            entries = [e for e in schedule if e["pair"] == pair]
            self.assertEqual(len({e["case"]["id"] for e in entries}), 1)
            for position, entry in enumerate(entries):
                counts[entry["model"]["name"]][position] += 1
        self.assertEqual(counts, {name: [2, 2, 2] for name in "abc"})

    def test_summary_failures_skips_pairs_warmups(self):
        def row(name, pair, ok=True, latency=10, warmup=False):
            return {"model_name": name, "pair": pair, "warmup": warmup, "ok": ok,
                    "latency_ms": latency, "wall_ms": latency + 2, "label": "yes", "expected": "yes"}
        rows = [row("a", 0), row("b", 0), row("a", 1), row("b", 1, False), row("a", -1, latency=999, warmup=True)]
        result = reporting.summarize(rows, ["a", "b", "c"], 3)
        self.assertEqual(result["models"]["a"]["median_ms"], 10)
        self.assertEqual(result["models"]["b"]["errors"], 1)
        self.assertEqual(result["models"]["c"]["skipped"], 3)
        self.assertEqual(result["paired"][0]["valid_pairs"], 1)
        self.assertEqual(result["paired"][0]["ties"], 1)

    def test_percentile(self):
        self.assertAlmostEqual(reporting.percentile([1, 2, 3, 4], .95), 3.85)
        self.assertEqual(reporting.percentile([7], .95), 7)

    def test_fake_executor_artifacts(self):
        def execute(_request, _timeout):
            return {"ok": True, "label": "yes", "latency_ms": 1, "wall_ms": 2}
        output = self.root / "output"
        with contextlib.redirect_stdout(io.StringIO()):
            result = runner.run_experiment(self.experiment(), output, execute)
        self.assertEqual(result["attempts_used"], 21)
        self.assertTrue(result["complete"])
        for name in ["samples.jsonl", "attempts.jsonl"]:
            self.assertEqual(len((output / name).read_text().splitlines()), 21)
        self.assertEqual(len((output / "samples.csv").read_text().splitlines()), 22)
        self.assertTrue((output / "RESULTS.md").exists())

    def test_worker_hard_timeout(self):
        with patch.object(runner.subprocess, "run", side_effect=subprocess.TimeoutExpired("mock", .1)) as run:
            result = runner.execute_attempt({}, .1)
        self.assertEqual(run.call_args.kwargs["timeout"], .1)
        self.assertEqual(result["error_type"], "TimeoutExpired")
        self.assertFalse(result["ok"])

    def test_worker_invalid_envelopes(self):
        for stdout, code in [("[]", 0), ('{"ok":true}', 1), ('{"ok":false}', 0), ("broken", 1)]:
            with patch.object(runner.subprocess, "run", return_value=subprocess.CompletedProcess([], code, stdout, "ignored")):
                self.assertEqual(runner.execute_attempt({}, 1)["error_type"], "WorkerError")

    def test_worker_sanitizes_errors(self):
        input_data = io.TextIOWrapper(io.BytesIO(json.dumps({"model": {}, "dataset": {}, "text": "x", "timeout": 1}).encode()))
        output = io.StringIO()
        with patch.object(worker.sys, "stdin", input_data), patch.object(worker, "request_classification", side_effect=ValueError("dummy-sensitive")), contextlib.redirect_stdout(output):
            self.assertEqual(worker.main(), 1)
        self.assertNotIn("dummy-sensitive", output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["error_type"], "ValueError")

    def test_dry_run_without_key(self):
        self.models[0] = {"name": "api", "adapter": "openrouter-decisions", "model": "version"}
        self.experiment()
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), patch.object(sys, "argv", ["bench", "--config", str(self.path), "--dry-run"]), patch.object(cli, "run_experiment") as run, contextlib.redirect_stdout(output):
            self.assertEqual(cli.main(), 0)
            run.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["attempt_budget"], 21)
