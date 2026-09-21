"""Validate experiment and dataset files before any network calls."""

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

Json = dict[str, Any]
ADAPTERS = {"openrouter-decisions", "classifier.dev"}


def finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("Non-finite JSON number")
    return parsed


def reject_constant(_value: str) -> None:
    raise ValueError("Non-finite JSON number")


def unique_keys(pairs: list[tuple[str, Any]]) -> Json:
    result: Json = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def loads(text: str | bytes) -> Any:
    return json.loads(text, parse_float=finite_float, parse_constant=reject_constant,
                      object_pairs_hook=unique_keys)


def object_value(value: Any, name: str) -> Json:
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be an object")
    return value


def text_value(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonempty text")
    return value


def number(value: Any, name: str, low: float, high: float, integer: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    if not math.isfinite(value) or not low <= value <= high or (integer and not isinstance(value, int)):
        raise ValueError(f"{name} must be {'an integer ' if integer else ''}between {low} and {high}")
    return value


def only_keys(data: Json, allowed: set[str], name: str) -> None:
    if set(data) - allowed:
        raise ValueError(f"Unknown {name} field; check the example configurations")


def validate_dataset(data: Any) -> Json:
    data = object_value(data, "dataset")
    only_keys(data, {"name", "labels", "instructions", "cases", "warmup"}, "dataset")
    text_value(data.get("name"), "dataset.name")
    text_value(data.get("instructions"), "dataset.instructions")
    labels = data.get("labels")
    if not isinstance(labels, list) or not 2 <= len(labels) <= 100:
        raise ValueError("dataset.labels must contain 2–100 labels")
    for label in labels:
        text_value(label, "label")
    if len(set(labels)) != len(labels):
        raise ValueError("Labels must be unique")
    cases = data.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 1000:
        raise ValueError("dataset.cases must contain 1–1000 cases")
    ids = []
    for case in [*cases, *([data["warmup"]] if "warmup" in data else [])]:
        case = object_value(case, "case")
        only_keys(case, {"id", "text", "expected"}, "case")
        ids.append(text_value(case.get("id"), "case.id"))
        text_value(case.get("text"), "case.text")
        if not isinstance(case.get("expected"), str) or case["expected"] not in labels:
            raise ValueError("Every expected answer must be a dataset label")
    if len(set(ids)) != len(ids):
        raise ValueError("Case IDs must be unique, including the optional warmup")
    return data


@dataclass(frozen=True)
class Experiment:
    config: Json
    dataset: Json
    config_path: Path
    dataset_path: Path

    @property
    def measured_per_model(self) -> int:
        return len(self.dataset["cases"]) * self.config["rounds"]

    @property
    def attempt_budget(self) -> int:
        return (self.measured_per_model + self.config["warmups"]) * len(self.config["models"])


def load_experiment(path: Path) -> Experiment:
    path = path.expanduser().resolve()
    data = object_value(loads(path.read_bytes()), "experiment")
    only_keys(data, {"dataset", "models", "rounds", "warmups", "seed", "timeout_seconds", "max_seconds"}, "experiment")
    dataset_path = (path.parent / text_value(data.get("dataset"), "dataset path")).resolve()
    defaults = {"rounds": 1, "warmups": 1, "seed": 42, "timeout_seconds": 15, "max_seconds": 120}
    data = {**defaults, **data}
    number(data["rounds"], "rounds", 1, 100, integer=True)
    number(data["warmups"], "warmups", 0, 10, integer=True)
    number(data["seed"], "seed", 0, 2**32 - 1, integer=True)
    number(data["timeout_seconds"], "timeout_seconds", 0.1, 300)
    number(data["max_seconds"], "max_seconds", 0.1, 3600)
    models = data.get("models")
    if not isinstance(models, list) or not 1 <= len(models) <= 16:
        raise ValueError("Provide 1–16 named models")
    names = []
    for model in models:
        model = object_value(model, "model")
        only_keys(model, {"name", "adapter", "model", "tier", "processing"}, "model")
        name = text_value(model.get("name"), "model.name")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
            raise ValueError("Model names may contain letters, digits, dots, underscores, and hyphens")
        names.append(name)
        if model.get("adapter") not in ADAPTERS:
            raise ValueError("Unknown adapter")
        text_value(model.get("model"), "model.model")
        if model["adapter"] == "classifier.dev":
            if model["model"] not in {"jev", "laya"} or model.get("tier", "fast") not in {"fast", "smart"}:
                raise ValueError("classifier.dev supports jev/laya and fast/smart tiers")
            if "processing" in model and model["processing"] not in {"fast", "bulk"}:
                raise ValueError("processing must be fast or bulk")
        elif "tier" in model or "processing" in model:
            raise ValueError("tier and processing apply only to classifier.dev")
    if len(set(names)) != len(names):
        raise ValueError("Model names must be unique, even when comparing the same adapter")
    return Experiment(data, validate_dataset(loads(dataset_path.read_bytes())), path, dataset_path)
