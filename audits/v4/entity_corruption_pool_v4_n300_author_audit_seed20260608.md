# Entity Pool v4 N=300 Author Audit

Audit date: 2026-06-08

Dataset: `data/entity_corruption_pool_v4_n300.jsonl`

Source frame: `data/frozen/v1/entity_pool_v1.jsonl`

Sample: 50 items, fixed seed `20260608`

Sampling: 25 clean + 25 corrupted

## Summary

v4 passes the author audit for the confirmatory Entity N=300 run. Compared with
v2 and v3, the remaining artifacts are sparse and no longer form the dominant
character of the corrupted set.

Audit outcome:

- Clean: 25 inspected; 0 clear label errors. A few clean FEVER claims are broad
  or awkward, but their true label is not obviously wrong.
- Corrupted: 25 inspected; 2 clear family-purity artifacts; 2 borderline cases.

Decision: use `entity_corruption_pool_v4_n300.jsonl` for the three-judge Entity
N=300 experiment.

## Clear Bad / Likely Bad Corrupted Samples

| id | type | note |
|---|---|---|
| `entv4_0303` | non_entity_role_or_category_swap | `Representatives` -> `Senators`; role/category swap rather than named-entity swap. |
| `entv4_0534` | non_entity_nationality_attribute_swap | `Welsh` -> `Scottish`; adjective/attribute swap rather than named entity. |

## Borderline Samples

| id | note |
|---|---|
| `entv4_0420` | `North American` -> `South American`; geographic adjective/region attribute, but false label is clear. |
| `entv4_0548` | `Central Europe` -> `Eastern Europe`; likely false, but regional classification can be somewhat fuzzy. |

## Attrition Notes

v4 preserves the permanent attempt log and records post-filter attrition:

- Clean: 408 attempts, 300 accepted, 108 rejected.
- Corrupt: 1,493 attempts, 300 accepted, 1,193 rejected.
- New v4 filters caught source broad frames, award categories, language/media
  terms, religion/attribute terms, partial title/common words, and partial
  person-name extractions.

## Decision Rationale

The audit does not show the systematic failure types that made v1/v2 unsafe for
main evaluation. v4 still has a small number of imperfect FEVER-derived
examples, which should be disclosed through attrition and author-audit
artifacts, but it is clean enough to run the preregistered Entity Replication
analysis.
