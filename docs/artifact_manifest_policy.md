# Artifact Manifest Policy

Pool manifests, build manifests, and evaluation manifests are tracked separately.

```text
Construction
|-- pool_freeze
`-- build_freeze

Evaluation
|-- evaluation
`-- evaluation_cache_validation
```

Each freeze wrapper records both levels:

```json
{
  "artifact_type": "pool_freeze",
  "stage": "construction"
}
```

## Pool Manifests

Pool manifests describe the source frame from which experiments sample claims.
They record:

- source frame
- fixed seed
- pool sizes
- attrition / attempt logs
- strata counts
- frozen pool files

They should not contain corruption-build, grounded verifier parse-fail, or
evaluation-policy fields.

Examples:

- `frozen/v1/FREEZE_MANIFEST.json`
- `data/frozen/v1/pool_manifest_v1.json`

## Build Manifests

Build manifests describe how a corruption family is constructed from a frozen
pool. They record:

- accepted examples
- rejected examples
- reject reasons
- construction rules
- post-filter version
- audit version
- attempt log path

They should not contain grounded verifier parse-fail or evaluation-policy
fields.

Examples:

- `frozen/number_v3/FREEZE_MANIFEST.json`
- `frozen/v4/FREEZE_MANIFEST.json`
- `results/frozen/*/*_build_manifest.json`

## Evaluation Manifests

Evaluation manifests describe judge/verifier runs and policy evaluation. They
record:

- grounded verifier configuration
- raw `parse_fail` counts
- retried counts
- final `parse_fail` counts
- `oracle_used`
- `gold_fallback_used`
- calibration/deployment split policy

They should not redefine pool construction, source-frame attrition, or
corruption-build rules.

Examples:

- `results/guardrail_grounded/validated_cache_manifest.json`
- `frozen/guardrail_baselines_v1/FREEZE_MANIFEST.json`
- `frozen/guardrail_heldout_multiseed/FREEZE_MANIFEST.json`
- `frozen/low_risk_specificity_v1/FREEZE_MANIFEST.json`

## Stage Mapping

| artifact_type | stage | Meaning |
|---|---|---|
| `pool_freeze` | `construction` | FEVER source-frame and family-pool selection. |
| `build_freeze` | `construction` | Corruption construction, post-filtering, and audit. |
| `evaluation` | `evaluation` | RF, grounded, guardrail, and held-out policy results. |
| `evaluation_cache_validation` | `evaluation` | Grounded verifier cache parse-fail retry/validation record. |
