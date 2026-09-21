# Jev Bench

- Keep the runtime in the Python standard library; add dependencies only for a concrete need.
- Experiments select named models and a dataset; never bake credentials into either.
- Credentials come from environment variables and must never reach saved artifacts or unrelated providers.
- Every model receives identical case text, labels, and classification instructions.
- Keep latency, wall time, label correctness, errors, skipped calls, and warmups distinct.
- Record every attempt before sending it; enforce request and overall deadlines without automatic retries.
- Changing an adapter requires an independent review and offline tests before a bounded live check.
- Run `python3 -B tests/run_tests.py` (asserts the test count) and `lintp jev_bench tests`.
- Plain runs stay under ignored `results/run-*`; `scripts/run_and_publish.py` explicitly publishes selected artifacts under `results/published/` and updates the manifest automatically.
- Keep the published results UI static and dependency-free; select public runs explicitly in published-runs.json.
