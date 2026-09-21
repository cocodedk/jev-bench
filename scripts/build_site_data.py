"""Publish only explicitly selected run artifacts, normalizing both result formats."""

import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from jev_bench.accuracy import classification_metrics

LABELS = {
    "jev-decisions": "Jev · OpenRouter",
    "openrouter-jev": "Jev · OpenRouter",
    "classifier.dev": "classifier.dev · Jev",
    "classifier-jev": "classifier.dev · Jev",
    "classifier-laya": "classifier.dev · Laya",
}


def build(root: Path = ROOT) -> int:
    manifest = json.loads((root / "published-runs.json").read_text())
    runs: list[dict[str, Any]] = []
    artifacts: list[tuple[Path, str]] = []
    seen = set()
    for entry in manifest["runs"]:
        run_id = entry["id"]
        if not isinstance(run_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", run_id) or run_id in seen:
            raise ValueError("Published run IDs must be unique lowercase URL-safe names")
        seen.add(run_id)
        source = (root / entry["path"]).resolve()
        if not source.is_relative_to((root / "results").resolve()):
            raise ValueError("Published runs must live under results/")
        for filename in ("results.json", "samples.csv", "attempts.jsonl"):
            path = (source / filename).resolve()
            if not path.is_relative_to(source) or not path.is_file():
                raise ValueError("Missing or external run artifact")
        result = json.loads((source / "results.json").read_text())
        summary = result["summary"]
        legacy = "schema_version" not in result
        source_models = {k: v for k, v in summary.items() if k != "paired"} if legacy else summary["models"]
        rounds = result["rounds"] if legacy else result["config"]["rounds"]
        planned = result["expected_measured_pairs"] if legacy else result["planned_measured_per_model"]
        sample_file = source / "samples.jsonl"
        samples = None
        if sample_file.exists():
            if not sample_file.resolve().is_relative_to(source):
                raise ValueError("External sample artifact")
            samples = [json.loads(line) for line in sample_file.read_text().splitlines() if line.strip()]
        models = []
        for name, stats in source_models.items():
            accuracy = stats.get("accuracy")
            if accuracy is None and samples is not None:
                rows = [row for row in samples if row.get("model_name", row.get("provider")) == name]
                accuracy = classification_metrics(rows, result.get("dataset", {}).get("labels"))
            models.append({"name": name, "label": LABELS.get(name, name),
                "returned_models": stats["models"] if legacy else stats["returned_models"],
                "planned": stats.get("planned", planned), "valid_responses": stats["valid_responses"],
                "correct_labels": stats["correct_labels"], "errors": stats["errors"],
                "skipped": stats.get("skipped", planned - stats["attempts"]), "accuracy": accuracy,
                **{metric: stats[metric] for metric in ("median_ms", "mean_ms", "p95_ms")}})
        attempts_used = sum(bool(line.strip()) for line in (source / "attempts.jsonl").read_text().splitlines())
        runs.append({"id": run_id, **{key: entry[key] for key in ("title", "subtitle", "dataset", "notes")},
            "started_utc": result["started_utc"], "rounds": rounds, "cases": planned // rounds,
            "measured_calls": sum(stats["attempts"] for stats in source_models.values()),
            "complete": result["complete"], "attempts_used": attempts_used,
            "models": models, "source": entry.get("source"), "json_url": f"data/{run_id}.json", "csv_url": f"data/{run_id}.csv"})
        artifacts.extend([(source / "results.json", f"{run_id}.json"), (source / "samples.csv", f"{run_id}.csv")])
    if not runs:
        raise ValueError("Select at least one published run")
    serialized = json.dumps({"version": 1, "runs": runs}, indent=2, allow_nan=False) + "\n"
    destination = root / "website" / "data"
    destination.mkdir(parents=True, exist_ok=True)
    expected = {"runs.json", *(name for _, name in artifacts)}
    for stale in destination.iterdir():
        if stale.is_file() and stale.name not in expected:
            stale.unlink()
    for source, filename in artifacts:
        shutil.copyfile(source, destination / filename)
    (destination / "runs.json").write_text(serialized)
    return len(runs)


if __name__ == "__main__":
    print(f"Built {build()} published runs")
