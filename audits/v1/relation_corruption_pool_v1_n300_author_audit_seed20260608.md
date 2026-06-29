# Relation Pool v1 N=300 Author Audit

Audit date: 2026-06-08

Dataset: `data/relation_corruption_pool_v1_n300.jsonl`

Source frame: `data/frozen/v1/relation_pool_v1.jsonl`

Sample: 50 items, fixed seed `20260608`

Sampling: 25 clean + 25 corrupted

## Summary

v1 successfully constructs 300 clean and 300 corrupted relation items from the
frozen relation pool, with permanent attempt logging and attrition. However, the
audit finds systematic family-purity and fluency issues. v1 should be kept as a
construction/audit artifact, not used for judge evaluation.

Audit outcome:

- Clean: 25 inspected; labels are mostly true, but several are relation-pool
  false positives such as `named after`, `grew up`, and noun uses of `causes`.
- Corrupted: 25 inspected; 4 clear construction artifacts and several
  recurring pattern-level artifacts in full-dataset spot checks.

## Clear Bad / Likely Bad Corrupted Samples

| id | type | note |
|---|---|---|
| `relv1_0420` | hyphenated_modifier_artifact | `Marvel-endorsed` -> `Marvel-opposed`; relation word is a modifier inside a compound adjective. |
| `relv1_0495` | fluency_artifact | `Facebook expanded to` -> `Facebook contracted to`; not fluent English for this frame. |
| `relv1_0355` | comparative_ranking_artifact | `largest living cat after the tiger` -> `before the tiger`; ranking use of `after`, not a clean temporal reversal. |
| `relv1_0488` | vague_not_decisively_false | `The Ku Klux Klan supported others` is too broad and not a precise false relation. |

## Borderline Samples

| id | note |
|---|---|
| `relv1_0390` | `sentence was increased to twelve years` may be false, but the legal sentence frame is easy to misread. |
| `relv1_0599` | sentence-initial `After` -> lowercase `before`; capitalization artifact. |

## Full-Dataset Spot Checks

Systematic issues observed outside the fixed sample:

- Clean relation-pool false positives: 28 `named after` items, 23 `grew up`
  items, and noun `causes` frames.
- Corrupt hyphenated modifier artifacts: `Marvel-endorsed` -> `Marvel-opposed`.
- Corrupt expansion artifacts: 8 `expanded to` -> `contracted to` examples.
- Corrupt comparative ranking artifacts: `second longest/highest/largest after`
  -> `before`.

## Recommended v2 Post-Filter

Build `relation_corruption_pool_v2_n300.jsonl` from the same frozen v1 source
frame with the same seed, but add deterministic strict filtering:

- Apply relation source filters to clean items too, not only corrupted items.
- Reject `named after`, `grew up`, noun `causes`, and other relation-pool false
  positives before validation.
- Reject comparative ranking uses of `after`, such as `second longest after`,
  `second highest after`, `came in second after`, and similar frames.
- Reject hyphenated relation modifiers such as `Marvel-endorsed`.
- Reject `expanded to` -> `contracted to` frames.
- Preserve capitalization when replacing a sentence-initial relation word.

Do not run judge evaluation on v1.
