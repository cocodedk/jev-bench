"""Run an experiment and publish its artifacts through the existing GitHub Pages workflow."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ("metadata.json", "results.json", "samples.jsonl", "samples.csv", "attempts.jsonl", "RESULTS.md")
ORIGINS = {"git@github.com:cocodedk/jev-bench.git", "https://github.com/cocodedk/jev-bench.git", "https://github.com/cocodedk/jev-bench"}
PAGE_URL = "https://cocodedk.github.io/jev-bench/"


def git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"Git {args[0]} failed; local results are retained") from error
    if result.returncode:
        raise RuntimeError(f"Git {args[0]} failed; local results are retained; inspect git status before retrying")
    return result.stdout.strip()


def preflight(root: Path) -> None:
    if Path(git(root, "rev-parse", "--show-toplevel")).resolve() != root.resolve():
        raise ValueError("Run automatic publication from the Jev Bench source checkout")
    if git(root, "branch", "--show-current") != "main":
        raise ValueError("Automatic publication requires the main branch")
    if git(root, "status", "--porcelain"):
        raise ValueError("Commit or move pending project changes before automatic publication")
    if git(root, "remote", "get-url", "origin") not in ORIGINS:
        raise ValueError("Automatic publication requires the cocodedk/jev-bench origin")
    git(root, "fetch", "origin", "main")
    if git(root, "rev-parse", "HEAD") != git(root, "rev-parse", "origin/main"):
        raise ValueError("Synchronize main with origin/main before automatic publication")


def dataset_source(root: Path, result: dict) -> dict | None:
    digest = result.get("dataset_sha256")
    if not digest:
        return None
    for dataset in sorted((root / "datasets").glob("*.json")):
        if hashlib.sha256(dataset.read_bytes()).hexdigest() != digest:
            continue
        provenance = dataset.with_suffix(".provenance.json")
        if provenance.is_file():
            data = json.loads(provenance.read_text())
            return {"name": data["dataset"], "url": data["source_url"], "credit": data["authors"],
                    "license": data["license"], "note": data["limits"]}
    return None


def publish_run(root: Path, source: Path) -> str:
    root, source = root.resolve(), source.resolve()
    preflight(root)
    if not source.is_relative_to(root / "results") or not source.is_dir():
        raise ValueError("Only saved runs under this checkout's results/ can be published")
    for name in ARTIFACTS:
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Missing or linked run artifact: {name}")
    result = json.loads((source / "results.json").read_text())
    if result.get("schema_version") != 1:
        raise ValueError("Automatic publication requires a current workbench result")
    run_id = source.name.lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", run_id):
        raise ValueError("Run directory names must contain lowercase letters, digits, and hyphens")
    manifest_path = root / "published-runs.json"
    manifest = json.loads(manifest_path.read_text())
    if any(entry["id"] == run_id for entry in manifest["runs"]):
        raise ValueError("This run is already published; choose a new run directory for a new experiment")
    destination = root / "results" / "published" / run_id
    if destination.resolve() != destination or (root / "website/data").resolve() != root / "website/data" or manifest_path.is_symlink():
        raise ValueError("Publication destinations must not use symlinks")
    if destination.exists():
        raise ValueError("The publication destination already exists; local files are retained")
    dataset = result["dataset"]
    models = result["config"]["models"]
    provenance = dataset_source(root, result)
    entry = {"id": run_id, "title": f"{provenance['name'] if provenance else dataset['name']} · {len(models)} model{'s' if len(models) != 1 else ''}",
        "subtitle": f"{len(dataset['labels'])} labels · expected answers withheld",
        "path": str(destination.relative_to(root)), "dataset": dataset["name"],
        "notes": f"{len(dataset['cases'])} labeled cases, {result['config']['rounds']} round(s), {result['attempts_used']} recorded attempts; inspect accuracy and individual mistakes below.",
        "source": provenance}
    destination.mkdir(parents=True)
    for name in ARTIFACTS:
        shutil.copyfile(source / name, destination / name)
    manifest["runs"].insert(0, entry)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    build = subprocess.run([sys.executable, "-B", str(root / "scripts/build_site_data.py")], cwd=root, check=False)
    if build.returncode:
        raise RuntimeError("Site data generation failed; nothing was committed and local results are retained")
    if git(root, "diff", "--cached", "--name-only"):
        raise RuntimeError("The index changed during publication; nothing was committed")
    paths = [str((destination / name).relative_to(root)) for name in ARTIFACTS]
    paths += ["published-runs.json", "website/data/runs.json"]
    for published in manifest["runs"]:
        paths.extend(f"website/data/{published['id']}.{suffix}" for suffix in ("json", "csv"))
    allowed = set(paths)
    changed = git(root, "diff", "--name-only").splitlines()
    if any(path not in allowed for path in changed):
        raise RuntimeError("Unrelated project files changed during publication; refusing to commit")
    git(root, "add", "--", *paths)
    staged = git(root, "diff", "--cached", "--name-only").splitlines()
    if any(path not in allowed for path in staged):
        raise RuntimeError("Unexpected staged files; refusing to commit")
    git(root, "commit", "-m", f"Publish benchmark results: {run_id}")
    git(root, "push", "origin", "main")
    return PAGE_URL


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--config", type=Path, help="Run this experiment, register its results, commit, and push to Pages")
    mode.add_argument("--existing-run", type=Path, help="Publish an existing saved run without making classifier requests")
    parser.add_argument("--dry-run", action="store_true", help="Preview --config without requests or publication")
    args = parser.parse_args()
    if args.dry_run:
        if not args.config:
            parser.error("--dry-run requires --config")
        return subprocess.run([sys.executable, "-B", "-m", "jev_bench", "--config", str(args.config.resolve()), "--dry-run"], cwd=ROOT, check=False).returncode
    code = 0
    try:
        source = args.existing_run
        if args.config:
            preflight(ROOT)
            source = ROOT / "results" / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ").lower())
            code = subprocess.run([sys.executable, "-B", "-m", "jev_bench", "--config", str(args.config.resolve()), "--output", str(source)], cwd=ROOT, check=False).returncode
            if not (source / "results.json").is_file():
                return code or 1
        print(f"Pushed results; GitHub Actions will deploy {publish_run(ROOT, source)}")
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
        parser.error(str(error))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
