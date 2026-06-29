# JuryProbe Held-out Multi-seed Guardrail Evaluation

Policy definition: `frozen/guardrail_heldout_multiseed/guardrail_policy_definition_v1.md`.

All results use held-out evaluation: risk is estimated on calibration and policies are evaluated on deployment.

## Calibration Risk Stability

| Family | Seeds | High-risk Detected | High-risk Rate | FN Corr | Residual Lift | p-value |
|---|---:|---:|---:|---:|---:|---:|
| entity | 10 | 10/10 | 1.000 | 0.348 ± 0.062 | 11.439 ± 5.267 | 0.011 ± 0.016 |
| number | 10 | 10/10 | 1.000 | 0.385 ± 0.028 | 2.602 ± 0.202 | 0.000 ± 0.000 |

## Deployment Policy Results

| Family | Policy | False Accept | True Accept | False Consensus | Extra Verifier Items | Model Calls |
|---|---|---:|---:|---:|---:|---:|
| entity | always_grounded | 0.000 ± 0.000 | 1.000 ± 0.000 | 0.000 ± 0.000 | 300.000 ± 0.000 | 900.000 ± 0.000 |
| entity | juryprobe_routed | 0.000 ± 0.000 | 0.639 ± 0.027 | 0.000 ± 0.000 | 113.700 ± 4.398 | 341.100 ± 13.195 |
| entity | rf_majority | 0.119 ± 0.014 | 0.639 ± 0.027 | 0.035 ± 0.011 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| entity | rf_unanimous | 0.035 ± 0.011 | 0.394 ± 0.027 | 0.035 ± 0.011 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| number | always_grounded | 0.000 ± 0.000 | 1.000 ± 0.000 | 0.000 ± 0.000 | 300.000 ± 0.000 | 900.000 ± 0.000 |
| number | juryprobe_routed | 0.000 ± 0.000 | 0.581 ± 0.029 | 0.000 ± 0.000 | 151.200 ± 4.756 | 453.600 ± 14.269 |
| number | rf_majority | 0.427 ± 0.029 | 0.581 ± 0.029 | 0.201 ± 0.022 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| number | rf_unanimous | 0.201 ± 0.022 | 0.273 ± 0.027 | 0.201 ± 0.022 | 0.000 ± 0.000 | 0.000 ± 0.000 |
