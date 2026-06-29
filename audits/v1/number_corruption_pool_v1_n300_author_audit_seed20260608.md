# Number Corruption Pool v1 N=300 Author Audit

Date: 2026-06-08

Dataset: `data/number_corruption_pool_v1_n300.jsonl`

Source frame: `data/frozen/v1/number_pool_v1.jsonl`

Sampling seed: 42

Audit sample seed: 20260608

Audit size: 50 items (25 clean, 25 corrupted)

## Verdict

FAIL for confirmatory freeze/evaluation.

The construction is mostly fluent and validator attrition is reasonable, but the
audit found a recurring family-definition problem: several target "numbers" are
inside entity names, model names, or work-title disambiguators. These are not the
clean numeric-value substitutions needed for the Number family.

## Bad Sample Types

- Entity/model number artifact:
  - `The Boeing 707` -> `The Boeing 566`
  - `The Boeing 777` -> `The Boeing 622`
  - `50 Cent` -> `60 Cent`
- Work-title/disambiguator artifact:
  - `Persuasion (2007 film)` -> `Persuasion (2005 film)`
  - `Sicario (2015 film)` -> `Sicario (2013 film)`
  - `Sunflower (1970 film)` appears in the clean side and would be unsafe for
    corrupted construction.
- Soft or weak factual framing:
  - `Teen Wolf is somewhat based on the 1985 film of the same name.`

## Construction Decision

Do not run judge evaluation on v1.

Create v2 with deterministic post-filters that reject:

- target numbers inside parenthetical title/disambiguator spans;
- target numbers adjacent to proper-name/model-number context;
- source claims containing `somewhat`.

Preserve this v1 dataset, attempt log, and manifest as construction/audit
history.
