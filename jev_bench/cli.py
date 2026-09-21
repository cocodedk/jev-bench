"""Select an experiment, inspect the request budget, or run it."""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .config import load_experiment
from .runner import run_experiment

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "experiments/jev-vs-classifier.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        experiment = load_experiment(args.config)
        if args.dry_run:
            print(json.dumps({"models": experiment.config["models"], "cases": len(experiment.dataset["cases"]),
                "measured_per_model": experiment.measured_per_model,
                "attempt_budget": experiment.attempt_budget}, indent=2))
            return 0
        needs_key = any(m["adapter"] == "openrouter-decisions" for m in experiment.config["models"])
        if needs_key and not os.environ.get("OPENROUTER_API_KEY", "").strip():
            parser.error("Export OPENROUTER_API_KEY before running an OpenRouter experiment")
        output = args.output or ROOT / "results" / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        result = run_experiment(experiment, output)
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))
    print(f"Results: {output.resolve() / 'RESULTS.md'}")
    return 0 if result["complete"] and result["all_valid"] else 1
