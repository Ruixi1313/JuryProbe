# JuryProbe Low-risk Specificity Control

Setting: the same cheap judge jury receives the original statement as a trusted reference. This tests whether JuryProbe always flags panels as high-risk.

No oracle or gold fallback is used; grounded verdicts come from the cached grounded verifier outputs.

## Full-set Grounded Risk

| Family | High-risk | FN Corr | All-3 FN | Residual Lift | p-value | FN Vote Rate |
|---|---:|---:|---:|---:|---:|---:|
| number | False | 0.000 | 0.000 | 0.000 | 1.000 | 0.000 |
| entity | False | -0.004 | 0.000 | 0.000 | 1.000 | 0.009 |

## Held-out Calibration Specificity

| Family | High-risk Detected | FN Corr | All-3 FN | Residual Lift | p-value | FN Vote Rate | Any-FN Item Rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| number | 0/10 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 1.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| entity | 0/10 | -0.003 ± 0.002 | 0.000 ± 0.000 | 0.000 ± 0.000 | 1.000 ± 0.000 | 0.008 ± 0.002 | 0.024 ± 0.007 |
