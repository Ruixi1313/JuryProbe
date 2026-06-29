# Strong Judge Slice v1

Supplementary robustness analysis only. Results are not included in primary guardrail evaluation tables.

Primary question: Do stronger reference-free judges reduce false consensus risk?

## Panel Metrics

| Panel | FN Corr | False Consensus | Lift | p-value | RF Majority False Accept | RF Majority True Accept |
|---|---:|---:|---:|---:|---:|---:|
| capability_slice | 0.252 | 0.137 | 2.169 | 0.0003 | 0.387 | 0.647 |

## Per-judge Metrics

| Panel | Judge | FN Rate (Corrupted) | True Accept (Clean) | Parse Fail |
|---|---|---:|---:|---:|
| capability_slice | llama-3.1-8b-instruct | 0.357 | 0.470 | 0 |
| capability_slice | gemma-3-12b-it | 0.527 | 0.650 | 0 |
| capability_slice | qwen3-32b | 0.333 | 0.727 | 0 |
