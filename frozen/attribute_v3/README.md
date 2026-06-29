# Frozen Attribute v3 N=300

Freeze date: 2026-06-11

Purpose: Attribute N=300 construction dataset after strict candidate filtering,
diversity-controlled replacement, and author audit.

Artifact type: `build_freeze`. Stage: `construction`. Pool manifests, build
manifests, and evaluation manifests are tracked separately.

Source frame:

- `data/frozen/attribute_v2/attribute_pool_v2.jsonl`
- `data/frozen/attribute_v2/attribute_pool_manifest_v2.json`
- derived from `data/frozen/v1/master_claim_pool_v1.jsonl`

Construction rule:

- `replacement_policy`: `balanced_v3`
- `replacement_pair_cap`: `20`
- `local_post_filter`: `strict_v3`
- GPT-4o role: hard-gate validation only, not pool selection or judge
  evaluation.

Audit result:

- Audit sample: 50 items, seed 20260611
- `VALID`: 49
- `AMBIGUOUS_FACT`: 1
- Gate: `GREEN`

Frozen construction artifacts:

- `data/frozen/attribute_v3/attribute_corruption_pool_v3_n300.jsonl`
- `results/frozen/attribute_v3/attribute_corruption_pool_v3_n300_build_attempts.jsonl`
- `results/frozen/attribute_v3/attribute_corruption_pool_v3_n300_build_manifest.json`
- `frozen/attribute_v3/attribute_corruption_pool_v3_n300_author_audit_seed20260611.md`
- `results/frozen/attribute_v3/attribute_corruption_pool_v3_n300_rf.jsonl`
- `results/frozen/attribute_v3/attribute_corruption_pool_v3_n300_gpt4o.jsonl`
- `results/frozen/attribute_v3/attribute_corruption_pool_v3_n300_grounded.jsonl`
- `results/frozen/attribute_v3/attribute_corruption_pool_v3_n300_analysis.json`
- `frozen/attribute_v3/FREEZE_MANIFEST.json`

Evaluation summary:

- GPT-4o accuracy: 0.978
- Detectable corrupted subset: 296 / 300
- FN-only correlation: 0.263
- Detectable all-3 false consensus: 0.003
- Detectable residual lift: 54.55x
- Permutation p-value: 0.0183
- Grounded correlation: 0.000
- Grounded all-3 false consensus: 0.000
- Verdict: Attribute Replication PASS; not Strong Mechanistic Replication because
  the reference-free all-3 false-consensus event rate is already very low.

Do not overwrite these files. If the source frame, replacement policy,
post-filter, validator, or audit decision changes, create a new frozen version.
