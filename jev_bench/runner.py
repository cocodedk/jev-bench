"""Execute a reproducible, finite schedule and retain every attempt."""

import csv
import hashlib
import json
import os
import platform
import random
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .config import Experiment, Json, loads
from .reporting import markdown_report, summarize


def plan(experiment: Experiment) -> list[Json]:
    config, dataset = experiment.config, experiment.dataset
    models = config["models"]
    schedule = []
    warmup_case = dataset.get("warmup", dataset["cases"][0])
    for index in range(config["warmups"]):
        for model in models:
            schedule.append({"pair": -index - 1, "warmup": True, "case": warmup_case, "model": model})
    cases = dataset["cases"] * config["rounds"]
    random.Random(config["seed"]).shuffle(cases)
    for pair, case in enumerate(cases):
        cycle, offset = divmod(pair, len(models))
        order = models[offset:] + models[:offset]
        if cycle % 2:
            order = list(reversed(order))
        for model in order:
            schedule.append({"pair": pair, "warmup": False, "case": case, "model": model})
    if len(schedule) != experiment.attempt_budget:
        raise RuntimeError("Schedule does not match the attempt budget")
    return schedule


def execute_attempt(request: Json, timeout: float) -> Json:
    started = time.perf_counter_ns()
    env = os.environ.copy()
    package_parent = str(Path(__file__).resolve().parent.parent)
    env["PYTHONPATH"] = package_parent + os.pathsep + env.get("PYTHONPATH", "")
    try:
        child = subprocess.run([sys.executable, "-B", "-m", "jev_bench.worker"],
            input=json.dumps(request), capture_output=True, text=True, env=env, timeout=timeout, check=False)
        result = loads(child.stdout)
        if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
            raise TypeError("Worker returned an invalid envelope")
        if child.returncode not in (0, 1) or (child.returncode == 0) != result["ok"]:
            raise ValueError("Worker exit code contradicts its result")
    except subprocess.TimeoutExpired:
        result = {"ok": False, "error_type": "TimeoutExpired"}
    except (OSError, ValueError, TypeError):
        result = {"ok": False, "error_type": "WorkerError"}
    return {**result, "wall_ms": (time.perf_counter_ns() - started) / 1_000_000}


def run_experiment(experiment: Experiment, output: Path,
                   execute: Callable[[Json, float], Json] = execute_attempt) -> Json:
    output.mkdir(parents=True, exist_ok=False)
    schedule = plan(experiment)
    metadata = {"schema_version": 1, "benchmark_version": __version__,
        "started_utc": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
        "platform": platform.platform(), "config": experiment.config, "dataset": experiment.dataset,
        "experiment_sha256": hashlib.sha256(experiment.config_path.read_bytes()).hexdigest(),
        "dataset_sha256": hashlib.sha256(experiment.dataset_path.read_bytes()).hexdigest(),
        "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted(Path(__file__).parent.glob("*.py"))},
        "attempt_budget": experiment.attempt_budget,
        "planned_measured_per_model": experiment.measured_per_model}
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    rows: list[Json] = []
    stop_reason = None
    deadline = time.monotonic() + experiment.config["max_seconds"]
    try:
        with (output / "attempts.jsonl").open("w") as attempts, (output / "samples.jsonl").open("w") as samples:
            for entry in schedule:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    stop_reason = "deadline"
                    break
                model, case = entry["model"], entry["case"]
                row = {"pair": entry["pair"], "warmup": entry["warmup"], "model_name": model["name"],
                       "adapter": model["adapter"], "requested_model": model["model"],
                       "case_id": case["id"], "text": case["text"], "expected": case["expected"]}
                attempts.write(json.dumps(row) + "\n")
                attempts.flush()
                os.fsync(attempts.fileno())
                timeout = min(experiment.config["timeout_seconds"], deadline - time.monotonic())
                if timeout <= 0:
                    row.update(ok=False, error_type="DeadlineBeforeRequest", wall_ms=0)
                    stop_reason = "deadline"
                else:
                    request = {"model": model, "dataset": {k: experiment.dataset[k]
                               for k in ("labels", "instructions")}, "text": case["text"], "timeout": timeout}
                    try:
                        row.update(execute(request, timeout))
                    except KeyboardInterrupt:
                        row.update(ok=False, error_type="Interrupted", wall_ms=0)
                        stop_reason = "interrupted"
                rows.append(row)
                samples.write(json.dumps(row, allow_nan=False) + "\n")
                samples.flush()
                print(f"{len(rows)}/{len(schedule)} {model['name']}: {'ok' if row['ok'] else row['error_type']}", flush=True)
                if stop_reason:
                    break
    except KeyboardInterrupt:
        stop_reason = "interrupted"
    names = [model["name"] for model in experiment.config["models"]]
    if len(rows) > experiment.attempt_budget:
        raise RuntimeError("Attempt budget exceeded")
    result = {**metadata, "attempts_used": len(rows), "complete": len(rows) == len(schedule),
              "stop_reason": stop_reason, "all_valid": bool(rows) and all(r["ok"] for r in rows),
              "summary": summarize(rows, names, experiment.measured_per_model, experiment.dataset["labels"])}
    (output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    (output / "RESULTS.md").write_text(markdown_report(result))
    fields = sorted({key for row in rows for key in row}) or ["model_name", "ok"]
    with (output / "samples.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return result
