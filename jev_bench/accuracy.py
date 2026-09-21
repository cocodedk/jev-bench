"""Classification accuracy from expected labels, with mistakes retained for inspection."""

from collections import Counter

from .config import Json


def classification_metrics(rows: list[Json], labels: list[str] | None = None) -> Json:
    measured = [row for row in rows if not row["warmup"]]
    valid = [row for row in measured if row["ok"]]
    if labels is None:
        labels = sorted({row["expected"] for row in measured} | {row["label"] for row in valid})
    support = Counter(row["expected"] for row in valid)
    predicted = Counter(row["label"] for row in valid)
    correct = Counter(row["expected"] for row in valid if row["expected"] == row["label"])
    classes: list[Json] = []
    for label in labels:
        tp, actual, guesses = correct[label], support[label], predicted[label]
        classes.append({"label": label, "support": actual, "predicted": guesses, "correct": tp,
            "precision_pct": 100 * tp / guesses if guesses else 0.0,
            "recall_pct": 100 * tp / actual if actual else 0.0,
            "f1_pct": 200 * tp / (actual + guesses) if actual + guesses else 0.0})
    mistakes = [{"case_id": row.get("case_id", str(row.get("pair", "unknown"))), "text": row.get("text", ""),
                 "expected": row["expected"], "predicted": row["label"]}
                for row in valid if row["expected"] != row["label"]]
    confusions = Counter((row["expected"], row["predicted"]) for row in mistakes)
    total_correct = sum(correct.values())
    return {"accuracy_pct": 100 * total_correct / len(valid) if valid else None,
        "macro_f1_pct": sum(row["f1_pct"] for row in classes) / len(classes) if valid and classes else None,
        "correct": total_correct, "valid": len(valid), "wrong": len(mistakes), "classes": classes,
        "confusions": [{"expected": expected, "predicted": guess, "count": count}
                       for (expected, guess), count in sorted(confusions.items(), key=lambda item: (-item[1], item[0]))],
        "mistakes": mistakes}
