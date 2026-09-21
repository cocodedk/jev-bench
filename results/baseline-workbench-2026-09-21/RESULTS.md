# Benchmark results

Started: 2026-09-21T10:55:44.162515+00:00

Complete: True; attempts: 42/42.

| Model | Valid / planned | Median ms | Mean ms | p95 ms | Correct / valid | Errors | Skipped |
|---|---:|---:|---:|---:|---:|---:|---:|
| openrouter-jev | 20/20 | 365.5 | 374.6 | 482.4 | 20/20 | 0 | 0 |
| classifier-jev | 20/20 | 387.1 | 409.1 | 484.4 | 20/20 | 0 | 0 |

Latency includes request preparation, connection/TLS, server processing, transfer, and JSON parsing;
it excludes worker startup and validation, which are included separately in wall_ms.
Warmups and errors are excluded from latency statistics; accuracy uses valid labels only.
This is a descriptive sample from one machine, not a general model ranking.
