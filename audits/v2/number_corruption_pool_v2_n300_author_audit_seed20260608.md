# Number Corruption Pool v2 N=300 Author Audit

Date: 2026-06-08

Dataset: `data/number_corruption_pool_v2_n300.jsonl`

Source frame: `data/frozen/v1/number_pool_v1.jsonl`

Sampling seed: 42

Audit sample seed: 20260608

Audit size: 50 items (25 clean, 25 corrupted)

## Verdict

FAIL for confirmatory freeze/evaluation.

v2 successfully removes the large v1 problem of parenthetical work-title
disambiguators and obvious model/person-name numbers. The remaining failures are
more localized and suitable for deterministic post-filtering.

## Bad Sample Types

- Title/time-form numbers not caught by v2:
  - `Before We Go was previously titled 1:30 Train.`
  - `Tracy Morgan co-starred in 30 Rock.`
- Soft or approximate framing:
  - `Dallol, Ethiopia does not have an official estimate for the settlement's
    2005 population.`
- Decade/age-range notation:
  - `Henrietta Maria of France died in her 50's.`
- Invalid date after corruption:
  - `August 30, 2012` -> `August 36, 2012`

## Construction Decision

Do not run judge evaluation on v2.

Create v3 with deterministic post-filters that reject:

- target numbers in colon/time-like expressions;
- target numbers followed by decade suffixes such as `50's` / `1990s`;
- target numbers at the start of proper-title spans after stopwords, e.g.
  `in 30 Rock`;
- claims containing `estimate`;
- corruptions that produce invalid month/day dates.

Preserve v1 and v2 as construction/audit history only.
