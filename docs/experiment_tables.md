# JuryProbe Experiment Tables

Date: 2026-06-08

## Source Frame

| Artifact | Value |
|---|---:|
| Source | FEVER SUPPORTS |
| Pool version | v1 |
| Seed | 42 |
| FEVER rows scanned | 145,449 |
| SUPPORTS rows | 80,035 |
| Local-atomic pass | 53,850 |
| Master pool size | 53,850 |
| Number pool size | 4,705 |
| Entity pool size | 48,938 |
| Relation pool size | 774 |
| GPT-4o in pool selection | No |

Files:

- `data/frozen/v1/master_claim_pool_v1.jsonl`
- `data/frozen/v1/number_pool_v1.jsonl`
- `data/frozen/v1/entity_pool_v1.jsonl`
- `data/frozen/v1/relation_pool_v1.jsonl`
- `data/frozen/v1/pool_manifest_v1.json`

## Confirmatory Datasets

| Family | Final version | Source pool | N clean | N corrupt | Post-filter | Audit | Judge eval |
|---|---:|---|---:|---:|---|---|---|
| Number | v3 | `number_pool_v1` | 300 | 300 | strict_v3 | PASS | Yes |
| Entity | v4 | `entity_pool_v1` | 300 | 300 | strict_v4 | PASS | Yes |
| Relation | v4 stopped | `relation_pool_v1` | 300 | 300 | strict_v4 | FAIL / exploratory only | No |

## Construction Audit History

| Family | Version | Decision | Main audit reason |
|---|---:|---|---|
| Number | v1 | Fail | Target numbers inside entity/model/work-title strings, e.g. `Boeing 707`, `50 Cent`, parenthetical film disambiguators |
| Number | v2 | Fail | Remaining title/time numbers, decade suffixes, soft estimate framing, invalid dates after corruption |
| Number | v3 | Pass | No recurring construction artifacts in 50-item audit |
| Entity | v1 | Fail | Self-reference, wrong-type swaps, non-entity attributes, no-op/near-no-op swaps |
| Entity | v2 | Fail | Language/media/attribute swaps; not-decisively-false corruptions |
| Entity | v3 | Fail | Partial-title words, award categories, broad frames that could remain true |
| Entity | v4 | Pass | Sparse residual imperfections, no dominant systematic artifact |
| Relation | v1 | Fail | Hyphenated modifiers, comparative/ranking `after`, expansion artifacts, source false positives |
| Relation | v2 | Fail | Idiom/count artifacts such as `rose to fame -> fell to fame` and `ended after games -> before games` |
| Relation | v3 | Fail | Broad `another` frames and awkward merge/split formation frames |
| Relation | v4 | Fail | Category-membership and `enabled ... to -> prevented ... to` artifacts still appear |

## Final Construction Attrition

| Family | Version | Clean attempts | Clean accepted | Clean rejected | Corrupt attempts | Corrupt accepted | Corrupt rejected |
|---|---:|---:|---:|---:|---:|---:|---:|
| Number | v3 | 694 | 300 | 394 | 672 | 300 | 372 |
| Entity | v4 | 408 | 300 | 108 | 1,493 | 300 | 1,193 |

## Final Dataset Strata

| Family | Version | Length strata | Family strata |
|---|---:|---|---|
| Number | v3 | short 408; medium 184; long 8 | year 342; integer 258 |
| Entity | v4 | short 458; medium 137; long 5 | multi-token proper noun 355; work-like 87; person-like 65; single-token proper noun 64; place-like 19; organization-like 10 |

## Confirmatory Judge Results

| Family | GPT-4o oracle acc | Corrupted | Detectable | FN-only corr | Detectable all-3 FC | Residual lift | Perm p | Grounded corr | Grounded all-3 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Number v3 | 0.787 | 300 | 214 | 0.402 | 0.159 | 3.13x | 0.0003 | 0.000 | 0.000 |
| Entity v4 | 0.907 | 300 | 286 | 0.368 | 0.031 | 18.13x | 0.0003 | -0.003 | 0.000 |

## Grounding Collapse

| Family | RF mean corr | Grounded mean corr | Corr reduction | Corr p_lower | RF all-3 | Grounded all-3 | All-3 reduction | All-3 p_lower |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Number v3 | 0.386 | 0.000 | 0.386 | 0.0002 | 0.159 | 0.000 | 0.159 | 0.0002 |
| Entity v4 | 0.393 | -0.003 | 0.397 | 0.0002 | 0.031 | 0.000 | 0.031 | 0.0002 |

## Interpretation Locks

- Main conclusion rests on Number + Entity only.
- Relation is construction/audit evidence for why relation reversal is not yet a stable confirmatory family in open-domain FEVER.
- GPT-4o is not used for source-pool selection.
- GPT-4o validator is used after fixed-seed local sampling for construction gates.
- GPT-4o detectability is analysis-only and does not participate in item selection.
