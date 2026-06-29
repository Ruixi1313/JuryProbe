# Entity Pool v3 N=300 Author Audit

Audit date: 2026-06-08

Dataset: `data/entity_corruption_pool_v3_n300.jsonl`

Source frame: `data/frozen/v1/entity_pool_v1.jsonl`

Sample: 50 items, fixed seed `20260608`

Sampling: 25 clean + 25 corrupted

## Summary

v3 improves over v2. The stricter post-filter correctly records attrition for
language/media/placeholder/broad-frame cases, and the inspected corrupted items
are mostly clear entity swaps with false labels.

Audit outcome:

- Clean: 25 inspected; 0 clear label errors. Several FEVER claims are broad or
  awkward, but the clean label is not obviously wrong.
- Corrupted: 25 inspected; 5 clear or likely construction artifacts; 2
  additional borderline artifacts.

Recommendation: keep v3 as a traceable improved artifact, but do not use it as
the confirmatory Entity dataset. Add a v4 post-filter before the three-judge
run.

## Clear Bad / Likely Bad Corrupted Samples

| id | type | note |
|---|---|---|
| `entv3_0347` | possibly_true_or_not_decisively_false | The Dodgers' 1955 World Series championship did feature the Yankees; corrupted claim is likely true. |
| `entv3_0409` | partial_title_or_common_word_swap | `Girl` -> `Boy` inside `Got a Girl`; partial title word, not a clean named-entity swap. |
| `entv3_0495` | partial_title_or_common_word_swap | `Anything` -> `Everything` inside an album title; partial word substitution. |
| `entv3_0508` | non_entity_award_category_swap | `Best Actor` -> `Best Actress`; award category swap, not named entity. |
| `entv3_0471` | possibly_true_or_not_decisively_false | Jason Bourne is also a spy-film series; corrupted claim is true or not cleanly false. |

## Borderline Samples

| id | note |
|---|---|
| `entv3_0574` | `Ellen` -> `Oprah Winfrey`; original entity is a partial first-name extraction. |
| `entv3_0366` | `Novacane` -> `Channel Orange`; work swap is false, but changes song/album subtype. |

## Additional Full-Dataset Spot Checks

Tail inspection exposed two more systematic cases not in the fixed audit sample:

- `Christian` -> `Buddhist` in `Costa Rica is a ... country`: religion
  attribute, not entity.
- `Resident Evil` -> `Silent Hill` in `Games are part of the ... series`:
  modified claim is too broad and likely true.

## Recommended v4 Post-Filter

Extend the deterministic local filter:

- Reject religion/adjective attribute terms such as `Christian`, `Buddhist`,
  `Muslim`, `Hindu`, `Jewish`, etc.
- Reject award-category swaps such as `Best Actor`, `Best Actress`, and
  supporting-actor/actress variants.
- Reject common partial-title tokens such as `Girl`, `Boy`, `Anything`,
  `Everything` when they are used as the swapped entity.
- Reject broad frames that can remain true after entity replacement, e.g.
  `is a series of spy films`, `championship featured`, and `Games are part of
  the ... series`.

Then build `entity_corruption_pool_v4_n300.jsonl` from the same frozen v1 source
frame with the same seed. Run the same 50-item author audit before any judge
evaluation.
