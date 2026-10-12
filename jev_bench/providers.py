"""Two explicit API adapters; credentials come from the calling environment."""

import json
import math
import os
import time
import urllib.request
from typing import Any

from .config import Json, loads, object_value, text_value

URLS = {"openrouter-decisions": "https://openrouter.ai/api/alpha/decisions",
        "classifier.dev": "https://classifier.dev/v1/classify"}
MAX_RESPONSE_BYTES = 1024 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> None:
        return None


def make_payload(model: Json, dataset: Json, text: str) -> Json:
    if model["adapter"] == "openrouter-decisions":
        kind, labels, criteria = dataset.get("type", "choice"), dataset["labels"], dataset.get("criteria")
        question: Json = {"type": kind, "instructions": dataset["instructions"]}
        if kind == "score":
            question["criteria"] = [criteria[label] if criteria else label for label in labels]
        elif kind == "choice" or criteria:
            question["criteria"] = {label: criteria[label] if criteria else None for label in labels}
        return {"model": model["model"], "state": text, "questions": {"category": question}}
    payload = {"model": model["model"], "inputs": [text], "labels": dataset["labels"],
               "instructions": dataset["instructions"], "tier": model.get("tier", "fast")}
    if "processing" in model:
        payload["processing"] = model["processing"]
    return payload


def probability(value: Any, optional: bool = False) -> float | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("Expected a probability")
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Probability must be finite and between zero and one")
    return float(value)


def decode_result(model: Json, dataset: Json, raw: Any) -> Json:
    response = object_value(raw, "response")
    if "error" in response:
        raise ValueError("Provider returned an error")
    labels = dataset["labels"]
    confidence: float | None
    if model["adapter"] == "openrouter-decisions":
        answers = object_value(response.get("answers"), "answers")
        if set(answers) != {"category"}:
            raise ValueError("Response question IDs do not match")
        answer = object_value(answers["category"], "answer")
        kind = dataset.get("type", "choice")
        if answer.get("type") != kind:
            raise ValueError(f"Expected a {kind} answer")
        if kind == "noul":
            probability(answer.get("noul"))
            truth = float(answer["noul"])
            label, confidence = ("true", truth) if truth >= 0.5 else ("false", 1 - truth)
        else:
            levels = [str(i) for i in range(len(labels))] if kind == "score" else labels
            scores = object_value(answer.get("probabilities"), "probabilities")
            if set(scores) != set(levels):
                raise ValueError("Probability labels do not match")
            for score in scores.values():
                probability(score)
            if not math.isclose(sum(scores.values()), 1, abs_tol=min(0.05, 0.0051 * len(labels))):
                raise ValueError("Probabilities do not sum to one")
            if kind == "score":
                value = answer.get("score")
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= len(labels) - 1:
                    raise ValueError("Score is outside the rubric")
                label = labels[math.floor(value + 0.5)]
            else:
                label = text_value(answer.get("choice"), "choice")
                if label not in labels or scores[label] != max(scores.values()):
                    raise ValueError("Choice is not a highest-probability label")
            confidence = probability(answer.get("confidence"))
        returned_model = response.get("model")
    else:
        results = response.get("results")
        if not isinstance(results, list) or len(results) != 1:
            raise ValueError("Expected exactly one result")
        answer = object_value(results[0], "classification result")
        label = text_value(answer.get("label"), "label")
        if label not in labels:
            raise ValueError("Unknown classification label")
        confidence = probability(answer.get("confidence"), optional=True)
        returned_model = answer.get("model") or response.get("model")
    if returned_model is not None:
        text_value(returned_model, "returned model")
    return {"label": label, "confidence": confidence, "returned_model": returned_model}


def request_classification(model: Json, dataset: Json, text: str, timeout: float) -> Json:
    headers = {"Content-Type": "application/json", "Accept": "application/json",
               "User-Agent": "jev-bench/0.1.0"}
    if model["adapter"] == "openrouter-decisions":
        key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not key or any(not 33 <= ord(c) <= 126 for c in key):
            raise ValueError("OPENROUTER_API_KEY is missing or invalid")
        headers["Authorization"] = f"Bearer {key}"
    started = time.perf_counter_ns()
    payload = json.dumps(make_payload(model, dataset, text), allow_nan=False).encode()
    if len(payload) > 512 * 1024:
        raise ValueError("Request exceeds 512 KiB")
    request = urllib.request.Request(URLS[model["adapter"]], data=payload, headers=headers, method="POST")
    with urllib.request.build_opener(NoRedirect).open(request, timeout=timeout) as response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("Response exceeds 1 MiB")
    raw = loads(body)
    latency_ms = (time.perf_counter_ns() - started) / 1_000_000
    return {**decode_result(model, dataset, raw), "latency_ms": latency_ms}
