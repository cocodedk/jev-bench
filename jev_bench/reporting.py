"""Descriptive latency and accuracy statistics; failures remain visible."""

import itertools
import math
import statistics

from .config import Json


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize(rows: list[Json], names: list[str], planned_per_model: int) -> Json:
    models: Json = {}
    for name in names:
        measured = [r for r in rows if r["model_name"] == name and not r["warmup"]]
        valid = [r for r in measured if r["ok"]]
        times = [r["latency_ms"] for r in valid]
        models[name] = {"planned": planned_per_model, "attempts": len(measured),
            "skipped": planned_per_model - len(measured), "valid_responses": len(valid),
            "errors": len(measured) - len(valid),
            "correct_labels": sum(r["label"] == r["expected"] for r in valid),
            "accuracy_denominator": len(valid),
            "returned_models": sorted({r["returned_model"] for r in valid if r.get("returned_model")}),
            "missing_model_metadata": sum(r.get("returned_model") is None for r in valid),
            "mean_ms": statistics.mean(times) if times else None,
            "median_ms": statistics.median(times) if times else None,
            "p95_ms": percentile(times, 0.95) if times else None,
            "min_ms": min(times) if times else None, "max_ms": max(times) if times else None,
            "mean_wall_ms": statistics.mean(r["wall_ms"] for r in valid) if valid else None}
    groups: dict[int, Json] = {}
    for row in rows:
        if not row["warmup"] and row["ok"]:
            groups.setdefault(row["pair"], {})[row["model_name"]] = row
    pairs = []
    for left, right in itertools.combinations(names, 2):
        matched = [g for g in groups.values() if left in g and right in g]
        pairs.append({"left": left, "right": right, "valid_pairs": len(matched),
            "left_faster": sum(g[left]["latency_ms"] < g[right]["latency_ms"] for g in matched),
            "right_faster": sum(g[right]["latency_ms"] < g[left]["latency_ms"] for g in matched),
            "ties": sum(g[left]["latency_ms"] == g[right]["latency_ms"] for g in matched)})
    return {"models": models, "paired": pairs}


def format_metric(value: float | None) -> str:
    return f"{value:.1f}" if value is not None else "—"


def markdown_report(result: Json) -> str:
    lines = ["# Benchmark results", "", f"Started: {result['started_utc']}", "",
        f"Complete: {result['complete']}; attempts: {result['attempts_used']}/{result['attempt_budget']}.", "",
        "| Model | Valid / planned | Median ms | Mean ms | p95 ms | Correct / valid | Errors | Skipped |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, stats in result["summary"]["models"].items():
        lines.append(f"| {name} | {stats['valid_responses']}/{stats['planned']} | {format_metric(stats['median_ms'])} | "
            f"{format_metric(stats['mean_ms'])} | {format_metric(stats['p95_ms'])} | {stats['correct_labels']}/{stats['accuracy_denominator']} | "
            f"{stats['errors']} | {stats['skipped']} |")
    lines += ["", "Latency includes request preparation, connection/TLS, server processing, transfer, and JSON parsing;",
        "it excludes worker startup and validation, which are included separately in wall_ms.",
        "Warmups and errors are excluded from latency statistics; accuracy uses valid labels only.",
        "This is a descriptive sample from one machine, not a general model ranking.", ""]
    return "\n".join(lines)
