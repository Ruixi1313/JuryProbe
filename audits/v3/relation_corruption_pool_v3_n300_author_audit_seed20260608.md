# Relation Pool v3 N=300 Author Audit

Audit date: 2026-06-08

Dataset: `data/relation_corruption_pool_v3_n300.jsonl`

Source frame: `data/frozen/v1/relation_pool_v1.jsonl`

Sample: 50 items, fixed seed `20260608`

Sampling: 25 clean + 25 corrupted

## Summary

v3 is cleaner than v2. It removes the remaining idiom artifacts from v2, such
as `rose to fame -> fell to fame` and count/schedule frames.

Audit outcome:

- Clean: 25 inspected; true labels are acceptable, though a few relation-pool
  false positives remain.
- Corrupted: 25 inspected; 1 clear not-decisively-false item; 1 borderline
  fluency artifact.

Recommendation: build v4 with one final small source-filter expansion, then
freeze v4 if the same audit passes.

## Clear Bad / Likely Bad Corrupted Samples

| id | type | note |
|---|---|---|
| `relv3_0531` | broad_another_frame | `came before another home video console by Nintendo` may still be true because `another` is underspecified. |

## Borderline Samples

| id | note |
|---|---|
| `relv3_0471` | `merged with ... to establish` -> `split from ... to establish`; false, but relation reversal creates an awkward formation frame. |

## Remaining Clean Family-Purity Notes

| id | note |
|---|---|
| `relv3_0180` | `given a name after` is a naming relation, not temporal before/after. |
| `relv3_0297` | `third most populous ... after` is a ranking relation, not temporal before/after. |

## Recommended v4 Post-Filter

Extend deterministic source filtering:

- Reject naming paraphrases such as `given a name after`.
- Reject ordinal ranking frames like `third most populous ... after`.
- Reject broad `came before/after another ...` frames.
- Reject `merged with ... to form/establish` frames that become awkward under
  `split from`.

Do not run judge evaluation on v3.
