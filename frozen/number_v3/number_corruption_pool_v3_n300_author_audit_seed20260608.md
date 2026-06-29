# Number Corruption Pool v3 N=300 Author Audit

Date: 2026-06-08

Dataset: `data/number_corruption_pool_v3_n300.jsonl`

Source frame: `data/frozen/v1/number_pool_v1.jsonl`

Sampling seed: 42

Audit sample seed: 20260608

Audit size: 50 items (25 clean, 25 corrupted)

## Verdict

PASS for confirmatory freeze/evaluation.

The v3 audit did not find the recurring v1/v2 construction artifacts. The
sampled corruptions are numeric-value changes over dates, years, counts,
amounts, sizes, rankings, and durations while preserving entities and relation
wording.

## Checks

- No target numbers inside parenthetical work-title disambiguators.
- No obvious model/person/work-title number substitutions such as `Boeing 707`
  or `50 Cent`.
- No colon/time-title targets such as `1:30 Train`.
- No decade/age-range suffix targets such as `50's`.
- No invalid month/day dates after corruption.
- No `somewhat` / `estimate` soft-framing artifacts in the audited sample.

## Minor Notes

Some accepted items involve film/book release years or list/ranking sizes, e.g.
`a 1998 American film` or `top 50 greatest screen legends`. These are retained
because the numeric value is functioning as a verifiable factual attribute or
list size, not as an entity/model name.

## Construction Decision

Freeze v3 as the Number N=300 confirmatory construction.

Run judge evaluation only on v3.
