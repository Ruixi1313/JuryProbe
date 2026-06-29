# JuryProbe Guardrail Baseline Evaluation

Held-out 10-split evaluation. Risk is estimated on calibration; policies are evaluated on deployment.

Random-Routed is budget-matched to JuryProbe-Routed and samples from all deployment items.

## Calibration Risk

| Family | High-risk Detected | FN Corr | Residual Lift | p-value |
|---|---:|---:|---:|---:|
| entity | 10/10 | 0.348 ± 0.062 | 11.439 ± 5.267 | 0.011 ± 0.016 |
| number | 10/10 | 0.385 ± 0.028 | 2.602 ± 0.202 | 0.000 ± 0.000 |

## Policy Baselines

| Family | Policy | False Accept | True Accept | False Consensus | Extra Verifier Items | Model Calls |
|---|---|---:|---:|---:|---:|---:|
| entity | rf_majority | 0.119 ± 0.014 | 0.639 ± 0.027 | 0.035 ± 0.011 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| entity | rf_unanimous | 0.035 ± 0.011 | 0.394 ± 0.027 | 0.035 ± 0.011 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| entity | disagreement_routed | 0.035 ± 0.011 | 0.841 ± 0.015 | 0.035 ± 0.011 | 102.000 ± 3.464 | 306.000 ± 10.392 |
| entity | random_routed_budget_matched | 0.074 ± 0.008 | 0.776 ± 0.021 | 0.022 ± 0.007 | 113.700 ± 4.398 | 341.100 ± 13.195 |
| entity | juryprobe_routed | 0.000 ± 0.000 | 0.639 ± 0.027 | 0.000 ± 0.000 | 113.700 ± 4.398 | 341.100 ± 13.195 |
| entity | always_grounded | 0.000 ± 0.000 | 1.000 ± 0.000 | 0.000 ± 0.000 | 300.000 ± 0.000 | 900.000 ± 0.000 |
| number | rf_majority | 0.427 ± 0.029 | 0.581 ± 0.029 | 0.201 ± 0.022 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| number | rf_unanimous | 0.201 ± 0.022 | 0.273 ± 0.027 | 0.201 ± 0.022 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| number | disagreement_routed | 0.201 ± 0.022 | 0.762 ± 0.029 | 0.201 ± 0.022 | 140.100 ± 6.488 | 420.300 ± 19.465 |
| number | random_routed_budget_matched | 0.212 ± 0.013 | 0.792 ± 0.019 | 0.100 ± 0.009 | 151.200 ± 4.756 | 453.600 ± 14.269 |
| number | juryprobe_routed | 0.000 ± 0.000 | 0.581 ± 0.029 | 0.000 ± 0.000 | 151.200 ± 4.756 | 453.600 ± 14.269 |
| number | always_grounded | 0.000 ± 0.000 | 1.000 ± 0.000 | 0.000 ± 0.000 | 300.000 ± 0.000 | 900.000 ± 0.000 |
