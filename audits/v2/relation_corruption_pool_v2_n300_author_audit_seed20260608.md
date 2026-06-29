# Relation Pool v2 N=300 Author Audit

Audit date: 2026-06-08

Dataset: `data/relation_corruption_pool_v2_n300.jsonl`

Source frame: `data/frozen/v1/relation_pool_v1.jsonl`

Sample: 50 items, fixed seed `20260608`

Sampling: 25 clean + 25 corrupted

## Summary

v2 is substantially cleaner than v1. The audit-derived filters removed `named
after`, `grew up`, hyphenated relation modifiers, comparative ranking frames,
and `expanded to -> contracted to` artifacts from both clean and corrupted
construction.

Audit outcome:

- Clean: 25 inspected; labels are mostly true. One clear relation-pool
  false-positive remains.
- Corrupted: 25 inspected; 2 clear fluency/frame artifacts; otherwise mostly
  clean relation reversals.

Recommendation: keep v2 as a construction/audit artifact and build v3 with a
small additional deterministic source filter.

## Clear Bad / Likely Bad Corrupted Samples

| id | type | note |
|---|---|---|
| `relv2_0534` | idiom_fluency_artifact | `rose to fame` -> `fell to fame`; ungrammatical idiom reversal. |
| `relv2_0533` | count_frame_artifact | `ended after 7 Finals games` -> `ended before 7 Finals games`; awkward count/schedule frame rather than clean relation reversal. |

## Clean Family-Purity Issue

| id | type | note |
|---|---|---|
| `relv2_0180` | relation_pool_false_positive | `falls in the fairy tale category`; idiomatic category membership, not increase/decrease. |

## Recommended v3 Post-Filter

Extend the deterministic source filter:

- Reject `rose/fell to fame` and `rose/fell to prominence` idiom frames.
- Reject `rose to the rank` career-rank frames where reversal would be
  unnatural.
- Reject `falls in ... category` category-membership frames.
- Reject `ended after <number> ... games` count/schedule frames.

Do not run judge evaluation on v2.
