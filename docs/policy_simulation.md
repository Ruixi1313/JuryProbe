# JuryProbe Decision-Policy Simulation

This simulation uses frozen Number v3 and Entity v4 reference-free judge outputs.
`Always Grounded` and the verifier branch of routed policies are oracle/strong-verifier upper bounds using gold labels for escalated items.

The High-Risk Panel definition is panel-level, not sample-level:

- FN-only corr > 0.15
- detectable residual lift > 1.5
- permutation p < 0.05

Primary guardrail policy: `JuryProbe-Routed Accept Guardrail` escalates only when the panel is high-risk and the reference-free majority would accept; otherwise it keeps RF reject decisions. This protects accept decisions while avoiding verifier calls on RF rejects.

Appendix diagnostic policy: `JuryProbe-Routed Agreement Guardrail` escalates only unanimous agreement cases.

## Qualitative Guardrail Summary

| Policy | False Accept | Extra Verifier Calls |
|---|---|---|
| Reference-Free Majority | High | 0 |
| Reference-Free Unanimous | Medium | 0 |
| Always Grounded | Low | High |
| JuryProbe-Routed Accept Guardrail | Low | Medium |

## Main Policy Results

| Family | Policy | False Accept | True Accept | False Consensus | Extra Verifier Calls |
|---|---|---:|---:|---:|---:|
| Number | Reference-Free Majority | 0.427 | 0.567 | 0.193 | 0 |
| Number | Reference-Free Unanimous | 0.193 | 0.267 | 0.193 | 0 |
| Number | Always Grounded (Oracle Upper Bound) | 0.000 | 1.000 | 0.000 | 600 |
| Number | JuryProbe-Routed Accept Guardrail | 0.000 | 0.567 | 0.000 | 298 |
| Entity | Reference-Free Majority | 0.120 | 0.640 | 0.030 | 0 |
| Entity | Reference-Free Unanimous | 0.030 | 0.407 | 0.030 | 0 |
| Entity | Always Grounded (Oracle Upper Bound) | 0.000 | 1.000 | 0.000 | 600 |
| Entity | JuryProbe-Routed Accept Guardrail | 0.000 | 0.640 | 0.000 | 228 |

## Full Policy Results

| Family | Policy | False Accept | True Accept | False Consensus | Escalation Rate | Extra Verifier Calls |
|---|---|---:|---:|---:|---:|---:|
| Number | Reference-Free Majority | 0.427 | 0.567 | 0.193 | 0.000 | 0 |
| Number | Reference-Free Unanimous | 0.193 | 0.267 | 0.193 | 0.000 | 0 |
| Number | Always Grounded (Oracle Upper Bound) | 0.000 | 1.000 | 0.000 | 1.000 | 600 |
| Number | JuryProbe-Routed Accept Guardrail | 0.000 | 0.567 | 0.000 | 0.497 | 298 |
| Number | JuryProbe-Routed Agreement Guardrail | 0.233 | 0.807 | 0.000 | 0.525 | 315 |
| Entity | Reference-Free Majority | 0.120 | 0.640 | 0.030 | 0.000 | 0 |
| Entity | Reference-Free Unanimous | 0.030 | 0.407 | 0.030 | 0.000 | 0 |
| Entity | Always Grounded (Oracle Upper Bound) | 0.000 | 1.000 | 0.000 | 1.000 | 600 |
| Entity | JuryProbe-Routed Accept Guardrail | 0.000 | 0.640 | 0.000 | 0.380 | 228 |
| Entity | JuryProbe-Routed Agreement Guardrail | 0.090 | 0.783 | 0.000 | 0.657 | 394 |
