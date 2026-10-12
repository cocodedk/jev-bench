# Benchmark results

Started: 2026-10-12T08:00:08.459681+00:00

Complete: True; attempts: 200/200.

| Model | Valid / planned | Median ms | Mean ms | p95 ms | Correct / valid | Accuracy | Macro F1 | Errors | Skipped |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pplx-decider-v1.1-27b | 50/50 | 319.2 | 549.2 | 1914.1 | 50/50 | 100.0% | 100.0% | 0 | 0 |
| typesafe-jev-latest | 50/50 | 327.8 | 339.1 | 466.8 | 50/50 | 100.0% | 100.0% | 0 | 0 |
| gpt-6-luna-decisions | 50/50 | 270.3 | 280.8 | 446.7 | 50/50 | 100.0% | 100.0% | 0 | 0 |
| microsoft-decision-1 | 50/50 | 307.4 | 324.1 | 380.8 | 50/50 | 100.0% | 100.0% | 0 | 0 |

Latency includes request preparation, connection/TLS, server processing, transfer, and JSON parsing;
it excludes worker startup and validation, which are included separately in wall_ms.
Warmups and errors are excluded from latency statistics; accuracy uses valid labels only.
Macro F1 gives each declared label equal weight; zero-denominator class scores are zero.
Per-class precision, recall, F1, confusions, and every incorrect classification are in results.json.
This is a descriptive sample from one machine, not a general model ranking.
