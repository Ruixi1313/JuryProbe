# Frozen Guardrail Baselines v1

Freeze date: 2026-06-09

Purpose: held-out 10-split guardrail baseline comparison.

Artifact type: `evaluation`. Stage: `evaluation`. Pool manifests, build
manifests, and evaluation manifests are tracked separately.

Policies:

- RF Majority
- RF Unanimous
- Disagreement-Routed
- Random-Routed budget-matched control
- JuryProbe-Routed
- Always Grounded

Protocol:

- Seeds: 1 through 10.
- Calibration: 150 clean + 150 corrupted.
- Deployment: remaining 150 clean + 150 corrupted.
- Risk estimated only on calibration.
- Policies evaluated only on deployment.
- Random-Routed uses 100 random trials per split and samples from all deployment
  items with the same verifier-item budget as JuryProbe-Routed.

Grounded verifier:

- same cheap judge jury
- original statement as trusted reference
- grounded majority final decision
- validated grounded verifier caches with no `parse_fail` verdicts
- validation: 15 raw `parse_fail` verdicts retried, 0 final `parse_fail`

No oracle or gold-label fallback is used.
