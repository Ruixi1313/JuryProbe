# JuryProbe Guardrail Policy Definition v1

Freeze date: 2026-06-09

## Risk Regime

`High-Risk Panel` is a panel-level risk regime estimated on a calibration probe,
not a sample-level classifier.

Thresholds:

- FN-only correlation > 0.15
- residual false-consensus lift > 1.5
- permutation p-value < 0.05

## Decision Policies

### Reference-Free Majority

Use the cheap judge jury without grounding. Accept if at least 2 of 3
reference-free judges say `true`.

### Reference-Free Unanimous

Use the cheap judge jury without grounding. Accept only if all 3 reference-free
judges say `true`.

### Always Grounded

Route every deployment item to the grounded verifier. The grounded verifier is
the same three cheap judges with the original statement as a trusted reference;
final decision is grounded majority.

### JuryProbe-Routed

Protect accept decisions:

```text
if panel is low-risk:
    use reference-free majority

if panel is high-risk:
    if reference-free majority would accept:
        route to grounded verifier
    else:
        keep reference-free reject
```

## Metrics

- False Accept Rate: corrupted items accepted / corrupted items.
- True Accept Rate: clean items accepted / clean items.
- False Consensus Rate: corrupted items where all three reference-free judges
  say `true` and the final policy still accepts.
- Extra Verifier Items: deployment items routed to grounded verification.
- Extra Verifier Calls: same as Extra Verifier Items.
- Model Calls: Extra Verifier Items x 3 judges.

## Constraints

- Held-out results must estimate risk only on calibration.
- Held-out policy metrics must be computed only on deployment.
- No oracle fallback.
- No gold-label fallback.
- If grounded verifier results are missing, the evaluator must report missing
  counts instead of silently using gold labels.
