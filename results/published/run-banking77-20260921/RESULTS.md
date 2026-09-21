# Benchmark results

Started: 2026-09-21T11:37:03.336020+00:00

Complete: True; attempts: 309/309.

| Model | Valid / planned | Median ms | Mean ms | p95 ms | Correct / valid | Accuracy | Macro F1 | Errors | Skipped |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| openrouter-jev | 308/308 | 359.9 | 375.7 | 469.6 | 240/308 | 77.9% | 76.4% | 0 | 0 |

Latency includes request preparation, connection/TLS, server processing, transfer, and JSON parsing;
it excludes worker startup and validation, which are included separately in wall_ms.
Warmups and errors are excluded from latency statistics; accuracy uses valid labels only.
Macro F1 gives each declared label equal weight; zero-denominator class scores are zero.
Per-class precision, recall, F1, confusions, and every incorrect classification are in results.json.
This is a descriptive sample from one machine, not a general model ranking.
