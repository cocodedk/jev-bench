# Benchmark results

Started: 2026-10-12T07:56:54.098607+00:00

Complete: True; attempts: 200/200.

| Model | Valid / planned | Median ms | Mean ms | p95 ms | Correct / valid | Accuracy | Macro F1 | Errors | Skipped |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pplx-decider-v1.1-27b | 50/50 | 332.1 | 485.6 | 1139.3 | 50/50 | 100.0% | 100.0% | 0 | 0 |
| typesafe-jev-latest | 50/50 | 304.2 | 319.4 | 416.7 | 48/50 | 96.0% | 96.1% | 0 | 0 |
| gpt-6-luna-decisions | 50/50 | 283.8 | 271.9 | 405.0 | 49/50 | 98.0% | 98.0% | 0 | 0 |
| microsoft-decision-1 | 50/50 | 315.2 | 355.7 | 403.7 | 44/50 | 88.0% | 88.3% | 0 | 0 |

Latency includes request preparation, connection/TLS, server processing, transfer, and JSON parsing;
it excludes worker startup and validation, which are included separately in wall_ms.
Warmups and errors are excluded from latency statistics; accuracy uses valid labels only.
Macro F1 gives each declared label equal weight; zero-denominator class scores are zero.
Per-class precision, recall, F1, confusions, and every incorrect classification are in results.json.
This is a descriptive sample from one machine, not a general model ranking.
