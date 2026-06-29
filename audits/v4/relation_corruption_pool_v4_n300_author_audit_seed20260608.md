# Relation Pool v4 N=300 Author Audit

Audit date: 2026-06-08

Dataset: `data/relation_corruption_pool_v4_n300.jsonl`

Source frame: `data/frozen/v1/relation_pool_v1.jsonl`

Sample: 50 items, fixed seed `20260608`

Sampling: 25 clean + 25 corrupted

## Summary

v4 is close to final quality, but the audit still finds two deterministic frame
artifacts that should be filtered before judge evaluation.

Audit outcome:

- Clean: 25 inspected; labels are acceptable, but a few idiomatic relation-pool
  false positives remain.
- Corrupted: 25 inspected; 2 clear construction artifacts.

Recommendation: build v5 with a small final post-filter, then audit v5 before
freezing.

## Clear Bad / Likely Bad Corrupted Samples

| id | type | note |
|---|---|---|
| `relv4_0409` | category_membership_artifact | `falls within the genre` -> `rises within the genre`; not an increase/decrease relation. |
| `relv4_0437` | enabled_to_prevented_to_artifact | `enabled ... to` -> `prevented ... to`; ungrammatical prevention frame. |

## Clean Family-Purity Notes

| id | note |
|---|---|
| `relv4_0068` | `after a while` is idiomatic, not a clean temporal before/after relation. |

## Recommended v5 Post-Filter

Extend deterministic source filtering:

- Reject `falls/fell within` category-membership frames.
- Reject `enabled ... to` frames where reversal would create `prevented ... to`.
- Reject `after a while` idioms.

Do not run judge evaluation on v4.
