# Entity Pool v1 N=300 Author Audit

Audit date: 2026-06-08

Dataset: `data/frozen/v1/entity_corruption_pool_v1_n300.jsonl`

Sample: 50 items, fixed seed `20260608`

Sampling: 25 clean + 25 corrupted, shuffled for inspection

## Summary

Clean items were mostly acceptable. Corrupted items showed several systematic
construction artifacts. This audit recommends not running the judge panel on
v1 as the main confirmatory Entity dataset. Keep v1 frozen as a traceable
construction artifact and create `v2` with a pre-specified post-filter.

Approximate audit outcome:

- Clean: 25 inspected; no obvious construction artifacts found in the audit pass.
- Corrupted: 25 inspected; 8-10 clear or likely construction artifacts.

## Bad Sample Types

- `self_referential_swap`: replacement makes the subject/object refer to itself.
- `non_entity_or_attribute_swap`: nationality, month, award type, platform, or
  media type swapped under an entity label.
- `no_op_or_near_no_op`: modified statement is unchanged or spelling variant only.
- `wrong_type_swap`: person replaced by title/work/team or organization replaced
  by work.
- `fluency_artifact`: modified statement has an obvious tampering seam.

## Clear Bad / Likely Bad Corrupted Samples

| id | type | note |
|---|---|---|
| `entv1_0528` | self_referential_swap | `Brian Wilson` -> `The Beach Boys`; "The Beach Boys were co-founded by The Beach Boys." |
| `entv1_0366` | non_entity_or_attribute_swap | `California Gurls` -> `2008`; generated a number/date change, not entity swap. |
| `entv1_0437` | wrong_type_swap / fluency_artifact | `Brian Lynch` -> `Puss`; "Puss wrote..." |
| `entv1_0569` | self_referential_swap | movie title replaced by subject entity. |
| `entv1_0495` | self_referential_swap | author replaced by the book title. |
| `entv1_0501` | reversed_role_artifact | "Emmy Awards has been a candidate for Matt Damon." |
| `entv1_0323` | self_referential_swap | `Borussia Dortmund` -> `Schwarzgelben`; nickname becomes subject. |
| `entv1_0548` | non_entity_or_attribute_swap | movie changed to book while recorded entity is unchanged. |
| `entv1_0347` | no_op_or_near_no_op | spelling variant makes statement effectively unchanged. |
| `entv1_0471` | non_entity_or_attribute_swap | month swap, not an entity swap. |

## Borderline Samples

| id | note |
|---|---|
| `entv1_0508` | `Fahrenheit` -> `Fahrenheit 9/11`; original entity extraction is partial. |
| `entv1_0444` | `Legendary` -> `Skull Island`; plausible false claim but entity type is questionable. |
| `entv1_0598` | `South Korea` -> `North Korea`; fluent, but claim wording "technologically advanced" is subjective. |
| `entv1_0409` | `England` -> `France`; likely acceptable, but country/control-of-throne wording needs care. |

## Recommended v2 Post-Filter

Apply a deterministic local post-filter before accepting a corrupted item:

- Reject if `original_entity == new_entity`.
- Reject if `new_entity` does not appear in the modified statement after simple
  normalization.
- Reject if `original_entity` does not appear in the original statement after
  simple normalization.
- Reject if `new_entity` appears in the original statement.
- Reject if `new_entity` equals the original subject or another existing entity
  from the original claim.
- Reject if replacement is numeric/date/month-only.
- Reject if replacement is a generic attribute class such as nationality,
  award type, platform, genre, or media type, unless the family is explicitly
  changed from entity-swap to attribute-swap.
- Reject if the modified statement contains obvious self-reference patterns,
  e.g. `X ... X` after replacing a role filler with the subject.

Then build `entity_corruption_pool_v2_n300.jsonl` from the frozen v1 source
frame and preserve a new v2 attempt log. Do not overwrite v1.

