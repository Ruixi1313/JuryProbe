# JuryProbe Real Grounded Guardrail Evaluation

Grounded verifier: the same three cheap judges are given the original statement as a trusted reference; grounded majority determines accept/reject.

Risk assessment is panel-level, not sample-level. The routed policy protects accept decisions:

```text
if panel low-risk: RF majority
if panel high-risk and RF majority accept: grounded verifier
if panel high-risk and RF majority reject: keep reject
```

| Split | Family | Policy | False Accept | True Accept | False Consensus | Extra Verifier Items | Extra Verifier Calls | Model Calls |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Full set | number | rf_majority | 0.427 | 0.567 | 0.193 | 0 | 0 | 0 |
| Full set | number | rf_unanimous | 0.193 | 0.267 | 0.193 | 0 | 0 | 0 |
| Full set | number | always_grounded | 0.000 | 1.000 | 0.000 | 600 | 600 | 1800 |
| Full set | number | juryprobe_routed | 0.000 | 0.567 | 0.000 | 298 | 298 | 894 |
| Full set | entity | rf_majority | 0.120 | 0.640 | 0.030 | 0 | 0 | 0 |
| Full set | entity | rf_unanimous | 0.030 | 0.407 | 0.030 | 0 | 0 | 0 |
| Full set | entity | always_grounded | 0.000 | 1.000 | 0.000 | 600 | 600 | 1800 |
| Full set | entity | juryprobe_routed | 0.000 | 0.640 | 0.000 | 228 | 228 | 684 |
| Held-out | number | rf_majority | 0.500 | 0.533 | 0.213 | 0 | 0 | 0 |
| Held-out | number | rf_unanimous | 0.213 | 0.280 | 0.213 | 0 | 0 | 0 |
| Held-out | number | always_grounded | 0.000 | 1.000 | 0.000 | 300 | 300 | 900 |
| Held-out | number | juryprobe_routed | 0.000 | 0.533 | 0.000 | 155 | 155 | 465 |
| Held-out | entity | rf_majority | 0.133 | 0.647 | 0.027 | 0 | 0 | 0 |
| Held-out | entity | rf_unanimous | 0.027 | 0.393 | 0.027 | 0 | 0 | 0 |
| Held-out | entity | always_grounded | 0.000 | 1.000 | 0.000 | 300 | 300 | 900 |
| Held-out | entity | juryprobe_routed | 0.000 | 0.647 | 0.000 | 117 | 117 | 351 |
