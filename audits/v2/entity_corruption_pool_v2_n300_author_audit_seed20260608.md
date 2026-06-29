# Entity Pool v2 N=300 Author Audit

Audit date: 2026-06-08

Dataset: `data/entity_corruption_pool_v2_n300.jsonl`

Source frame: `data/frozen/v1/entity_pool_v1.jsonl`

Sample: 50 items, fixed seed `20260608`

Sampling: 25 clean + 25 corrupted

## Summary

v2 is substantially cleaner than v1: the strict local filter removed the
self-referential swaps, no-op swaps, missing replacement metadata, and many
wrong-type replacements observed in v1. However, the author audit still finds
systematic quality issues in the corrupted half.

Audit outcome:

- Clean: 25 inspected; 0 clear label errors. 2-3 are low-specificity FEVER
  claims, but still usable as clean items.
- Corrupted: 25 inspected; 8 clear or likely construction artifacts; 3
  additional borderline artifacts.

Recommendation: keep v2 as a traceable intermediate artifact, but do not run
the three-judge confirmatory Entity experiment on v2. Add a stricter v3
post-filter and repeat the author audit before judge evaluation.

## Bad Sample Types

- `non_entity_language_or_attribute_swap`: language, nationality, medium, or
  generic category was treated as a named entity.
- `possibly_true_or_not_decisively_false`: corrupted statement may still be
  true, or is too broad for a clean false label.
- `placeholder_or_invented_entity`: replacement is an artificial placeholder
  rather than a plausible named entity.
- `fluency_or_frame_artifact`: modified claim has an obvious construction seam.

## Clear Bad / Likely Bad Corrupted Samples

| id | type | note |
|---|---|---|
| `entv2_0420` | non_entity_language_or_attribute_swap | `Tamil` -> `Telugu`; language attribute swap, not entity swap. |
| `entv2_0528` | possibly_true_or_not_decisively_false | Lisa Kudrow has HBO comedy-show associations; corrupted claim is not decisively false. |
| `entv2_0501` | non_entity_language_or_attribute_swap | `Hebrew` -> `Arabic`; language attribute swap. |
| `entv2_0444` | possibly_true_or_not_decisively_false | Paul McCartney being hospitalized during childhood is too broad / not decisively false. |
| `entv2_0598` | possibly_true_or_not_decisively_false | Xi Jinping did rise to a general secretary role; corrupted claim is likely true. |
| `entv2_0508` | possibly_true_or_not_decisively_false | Steven Spielberg can be described as an American actor and film director; not cleanly false. |
| `entv2_0471` | placeholder_or_invented_entity | `LGBT` -> `ABCD`; artificial acronym placeholder, not a plausible entity. |
| `entv2_0531` | non_entity_language_or_attribute_swap | `TV` -> `radio`; medium/type swap, not entity swap. |

## Borderline Samples

| id | note |
|---|---|
| `entv2_0355` | Replacement preserves "Democratic Senator" before Chuck Grassley, creating a role/party artifact. |
| `entv2_0569` | `Europe` -> `Albania`; probably false, but geographic frame becomes awkward. |
| `entv2_0534` | `Pakistan` -> `The Andes`; false, but modified sentence has a visible fluency artifact. |

## Recommended v3 Post-Filter

Apply a stricter deterministic post-filter before validator acceptance:

- Reject if `original_entity` or `new_entity` is a language, nationality
  adjective, media type, platform-as-medium, role, office, or generic
  attribute.
- Reject placeholder replacements such as artificial all-caps acronyms.
- Reject broad clean/corrupted frames where many entities could make the claim
  true, e.g. "has been in a movie", "worked on a comedy show", or generic
  childhood/hospitalization claims.
- Tighten validator wording so `corrupted_is_false` means clearly false, not
  merely less likely or uncertain.

Then build `entity_corruption_pool_v3_n300.jsonl` from the same frozen v1 source
frame with the same seed. Preserve the v2 attempt log and manifest; do not
overwrite v1 or v2.
