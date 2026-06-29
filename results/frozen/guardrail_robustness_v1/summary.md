# JuryProbe Guardrail Robustness v1

This artifact uses frozen model outputs only. No model API calls are made.

Scope: threshold sensitivity, calibration-risk statistics, Random-Routed stability, and leave-one-judge-out diagnostics.

## Calibration Risk Statistics

| Source | Family | High-risk | FN Corr | False Consensus | Null | Lift | p-value |
|---|---|---:|---:|---:|---:|---:|---:|
| grounded_specificity_control | entity | 0/10 | -0.003 ± 0.002 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 1.000 ± 0.000 |
| grounded_specificity_control | number | 0/10 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 1.000 ± 0.000 |
| reference_free_calibration | entity | 10/10 | 0.348 ± 0.062 | 0.025 ± 0.011 | 0.002 ± 0.000 | 11.439 ± 5.267 | 0.011 ± 0.016 |
| reference_free_calibration | number | 10/10 | 0.385 ± 0.028 | 0.186 ± 0.022 | 0.072 ± 0.010 | 2.602 ± 0.202 | 0.000 ± 0.000 |

## Threshold Sensitivity

Counts report high-risk detected splits out of 10 using p < 0.05.

| Family | Corr Threshold | Lift 1.25 | Lift 1.50 | Lift 2.00 |
|---|---:|---:|---:|---:|
| entity | 0.10 | 10/10 | 10/10 | 10/10 |
| entity | 0.15 | 10/10 | 10/10 | 10/10 |
| entity | 0.20 | 10/10 | 10/10 | 10/10 |
| entity | 0.25 | 10/10 | 10/10 | 10/10 |
| entity | 0.30 | 6/10 | 6/10 | 6/10 |
| number | 0.10 | 10/10 | 10/10 | 10/10 |
| number | 0.15 | 10/10 | 10/10 | 10/10 |
| number | 0.20 | 10/10 | 10/10 | 10/10 |
| number | 0.25 | 10/10 | 10/10 | 10/10 |
| number | 0.30 | 10/10 | 10/10 | 10/10 |

## Random-Routed Stability

| Family | Trials/Split | False Accept | Within-split Random SD | True Accept | False Consensus | Verifier Items |
|---|---:|---:|---:|---:|---:|---:|
| entity | 100 | 0.074 ± 0.008 | 0.013 | 0.776 ± 0.021 | 0.022 ± 0.007 | 113.700 ± 4.398 |
| number | 100 | 0.212 ± 0.013 | 0.023 | 0.792 ± 0.019 | 0.100 ± 0.009 | 151.200 ± 4.756 |

## Leave-One-Judge-Out

Each row uses the held-out calibration split and recomputes FN correlation and false-consensus lift for a two-judge subpanel.

| Family | Judge Pair | High-risk | FN Corr | False Consensus | Lift | p-value |
|---|---|---:|---:|---:|---:|---:|
| entity | Llama-3.1-8B + Gemma-3-12B | 10/10 | 0.305 ± 0.079 | 0.063 ± 0.014 | 2.678 ± 0.411 | 0.007 ± 0.011 |
| entity | Llama-3.1-8B + Qwen-2.5-7B | 9/10 | 0.312 ± 0.091 | 0.040 ± 0.009 | 3.685 ± 0.925 | 0.019 ± 0.052 |
| entity | Qwen-2.5-7B + Gemma-3-12B | 10/10 | 0.427 ± 0.078 | 0.069 ± 0.012 | 3.626 ± 0.498 | 0.000 ± 0.000 |
| number | Llama-3.1-8B + Gemma-3-12B | 5/10 | 0.399 ± 0.046 | 0.282 ± 0.031 | 1.514 ± 0.068 | 0.000 ± 0.000 |
| number | Llama-3.1-8B + Qwen-2.5-7B | 10/10 | 0.413 ± 0.042 | 0.233 ± 0.019 | 1.706 ± 0.107 | 0.000 ± 0.000 |
| number | Qwen-2.5-7B + Gemma-3-12B | 0/10 | 0.342 ± 0.048 | 0.284 ± 0.026 | 1.411 ± 0.044 | 0.000 ± 0.000 |
