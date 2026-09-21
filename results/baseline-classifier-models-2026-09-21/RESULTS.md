# Benchmark results

Started: 2026-09-21T10:56:06.905155+00:00

Complete: True; attempts: 42/42.

| Model | Valid / planned | Median ms | Mean ms | p95 ms | Correct / valid | Errors | Skipped |
|---|---:|---:|---:|---:|---:|---:|---:|
| classifier-jev | 20/20 | 389.0 | 393.6 | 459.6 | 20/20 | 0 | 0 |
| classifier-laya | 20/20 | 502.9 | 516.1 | 716.1 | 19/20 | 0 | 0 |

Latency includes request preparation, connection/TLS, server processing, transfer, and JSON parsing;
it excludes worker startup and validation, which are included separately in wall_ms.
Warmups and errors are excluded from latency statistics; accuracy uses valid labels only.
This is a descriptive sample from one machine, not a general model ranking.
