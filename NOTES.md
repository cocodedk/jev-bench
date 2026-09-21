## 2026-09-21 (Codex) — Measured Jev classification accuracy and automated publication

**State:** Jev matched 240/308 BANKING77 test labels (77.9% accuracy, 76.4% macro F1), with 68 wrong labels and no request errors; the fixed sample covers all 77 intents and the page exposes every mistake.

**Tried:** Independent gates verified source sampling and answer-free requests, 52 Python tests, 13 web tests, six mutation kills, and native/fallback Chrome with all seven tools; page proof is in `proof/accuracy-site/proof.json`.

**Lesson:** A perfect score on 20 synthetic examples does not establish classification quality; use a fixed labeled task and retain every error before changing the prompt.

**Next:** Publish the saved run with `scripts/run_and_publish.py --existing-run` after merging the feature; subsequent run-and-publish commands update the page automatically without editing its manifest.

## 2026-09-21 (Codex) — Completed social sharing metadata

**State:** The missing OG image and social metadata are complete and independently reviewed for publication; the image is a 1200×630 render of the existing vector branding, and the application body is unchanged.

**Tried:** The independent gate passed 21 checks covering metadata, JSON-LD, asset URLs, PNG/ICO dimensions, robots/sitemap consistency, and visual readability; the renderer and HTML pass lint.

**Lesson:** OG text tags alone leave the sharing card incomplete; verify the actual referenced image and its dimensions before calling SEO work finished.

**Next:** Keep the editable artwork with its renderer when refreshing the social preview; social platforms control their own cache refresh.

## 2026-09-21 (Codex) — Published the first Jev Bench workbench

**State:** Public repository and Pages site are live; the implementation and three selected runs are in commit `1d266bd`, and its [check/deploy workflow](https://github.com/cocodedk/jev-bench/actions/runs/35592733406) succeeded.

**Tried:** Independent checks passed 30 Python tests, eight WebMCP tests, and four mutation checks; local and live Chrome proofs passed with and without native WebMCP, including 28 invalid-input probes and mobile/desktop layouts; local evidence is in `proof/site/proof.json`, `proof/live/proof.json`, `proof/http.json`, and `proof/jev-gate.txt` (ignored by Git).

**Lesson:** Resolve the installed skill path before invoking helpers; when approval review flags source egress, establish the exact public input before retrying instead of changing the route.

**Next:** No required follow-up; select a new dataset or model configuration for the next experiment.
