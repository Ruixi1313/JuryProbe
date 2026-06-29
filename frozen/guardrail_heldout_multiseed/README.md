# Frozen Guardrail Held-out Multi-seed

Freeze date: 2026-06-09

Purpose: guardrail policy robustness over 10 held-out calibration/deployment
splits.

Artifact type: `evaluation`. Stage: `evaluation`. Pool manifests, build
manifests, and evaluation manifests are tracked separately.

Policy definition:

- `frozen/guardrail_heldout_multiseed/guardrail_policy_definition_v1.md`

Inputs:

- Number v3 frozen dataset and reference-free outputs.
- Entity v4 frozen dataset and reference-free outputs.
- Validated real grounded verifier caches, using the same cheap judge jury with
  grounded majority and no `parse_fail` verdicts.
- Validation: 15 raw `parse_fail` verdicts retried, 0 final `parse_fail`.

Split protocol:

- Seeds: 1 through 10.
- Calibration: 150 clean + 150 corrupted.
- Deployment: remaining 150 clean + 150 corrupted.
- Risk estimated only on calibration.
- Policies evaluated only on deployment.

No oracle or gold-label fallback is used.

Frozen outputs:

- `results/frozen/guardrail_heldout_multiseed/summary.json`
- `results/frozen/guardrail_heldout_multiseed/summary.md`
- `frozen/guardrail_heldout_multiseed/FREEZE_MANIFEST.json`
