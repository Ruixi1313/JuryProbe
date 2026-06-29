# Frozen Number v3 N=300

Freeze date: 2026-06-08

Purpose: confirmatory Number N=300 dataset after author audit and strict v3
post-filtering.

Artifact type: `build_freeze`. Stage: `construction`. Pool manifests, build
manifests, and evaluation manifests are tracked separately.

Source frame:

- `data/frozen/v1/number_pool_v1.jsonl`
- `data/frozen/v1/pool_manifest_v1.json`

Frozen construction artifacts:

- `data/frozen/number_v3/number_corruption_pool_v3_n300.jsonl`
- `results/frozen/number_v3/number_corruption_pool_v3_n300_build_attempts.jsonl`
- `results/frozen/number_v3/number_corruption_pool_v3_n300_build_manifest.json`
- `frozen/number_v3/number_corruption_pool_v3_n300_author_audit_seed20260608.md`
- `results/frozen/number_v3/number_corruption_pool_v3_n300_rf.jsonl`
- `results/frozen/number_v3/number_corruption_pool_v3_n300_gpt4o.jsonl`
- `results/frozen/number_v3/number_corruption_pool_v3_n300_grounded.jsonl`
- `results/frozen/number_v3/number_corruption_pool_v3_n300_analysis.json`
- `frozen/number_v3/FREEZE_MANIFEST.json`

Do not overwrite these files. If the source frame, post-filter, validator, or
audit decision changes, create a new frozen version.
