# Measured results

Run started: 2026-09-21T10:39:37.678297+00:00

20 paired cases, 40 measured HTTP calls, and 2 excluded warmups; all 42 calls returned valid responses.

| Service | Median | Mean | p95 | Correct labels | Errors |
|---|---:|---:|---:|---:|---:|
| jev-decisions | 399.0 ms | 421.6 ms | 507.9 ms | 20/20 | 0 |
| classifier.dev | 499.2 ms | 468.0 ms | 512.5 ms | 20/20 | 0 |

Jev was faster in 14 of 20 pairs; classifier.dev was faster in 6.

Returned models: direct Jev `typesafe/jev-1.13-20260917`; classifier.dev `jev-1.13.0`.

This is a small client-observed latency sample from this machine, including connection/TLS and excluding CLI startup; it does not establish a general performance ranking.

This historical run used the installed Jev skill transport; the permanent runner is self-contained and records additional provenance.

See the [workbench guide](../../README.md), [raw samples](samples.csv), and [machine-readable results](results.json).
