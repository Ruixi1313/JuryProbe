# Frozen v4 Entity N=300

Freeze date: 2026-06-08

Purpose: confirmatory Entity N=300 dataset after author audit and strict v4
post-filtering.

Artifact type: `build_freeze`. Stage: `construction`. Pool manifests, build
manifests, and evaluation manifests are tracked separately.

Source frame:

- `data/frozen/v1/entity_pool_v1.jsonl`
- `data/frozen/v1/pool_manifest_v1.json`

Frozen v4 artifacts:

- `data/frozen/v4/entity_corruption_pool_v4_n300.jsonl`
- `results/frozen/v4/entity_corruption_pool_v4_n300_build_attempts.jsonl`
- `results/frozen/v4/entity_corruption_pool_v4_n300_build_manifest.json`
- `frozen/v4/entity_corruption_pool_v4_n300_author_audit_seed20260608.md`
- `results/frozen/v4/entity_corruption_pool_v4_n300_rf.jsonl`
- `results/frozen/v4/entity_corruption_pool_v4_n300_gpt4o.jsonl`
- `results/frozen/v4/entity_corruption_pool_v4_n300_grounded.jsonl`
- `results/frozen/v4/entity_corruption_pool_v4_n300_analysis.json`
- `frozen/v4/FREEZE_MANIFEST.json`

Do not overwrite these files. If the source frame, post-filter, prompt,
validator, or audit decision changes, create a new frozen version.
