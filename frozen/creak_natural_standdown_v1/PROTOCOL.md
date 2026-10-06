# CREAK Natural Stand-Down Test v1

## Status

This protocol was frozen after verifying the official dataset schema and class
yield but before running any JuryProbe judge on CREAK.

## Purpose

This is a natural, non-FEVER branch-specificity test. It asks whether the same
three-judge panel and unchanged calibration rule select grounded routing or the
no-routing branch on human-authored entity-commonsense claims. The outcome is
not assumed in advance and will be retained regardless of branch.

## Source and License

The source is the official CREAK development split from repository commit
`5e892b28b6dad3e87769cfc01f00a6577ca44068`. Its SHA-256 is
`de61800bb7d0c07a9d5b8abdf4c1604db21151bdfcb13a284db112a531bf3455`.
The CREAK paper states that the data are CC BY-SA 4.0. Upstream provenance is
recorded in `data/raw/creak/SOURCE.md`.

## Frozen Selection

- Use the official development split only.
- Validate the seven expected fields and labels `true`/`false`.
- Normalize no text and apply no content filter.
- Sort each label pool by upstream example ID.
- Shuffle each label pool independently with Python `random.Random(42)`.
- Sample 300 true and 300 false claims without replacement.
- Map upstream true claims to clean items and false claims to corrupted items.
- Do not include the upstream explanation in the judge input.

The development split contains 691 true and 680 false unique claims, so the
300/300 target is met without attrition or replacement. No model or judge
output participates in selection.

## Frozen Evaluation

Use the submitted three-judge panel, reference-free prompt, binary parser,
majority rule, and risk thresholds. For seeds 1 through 10, split the 300 clean
and 300 false claims into 150/150 calibration and 150/150 deployment sets.
Run 3,000 permutations per split. Report:

- flagged high-risk splits;
- FN-only correlation;
- unanimous false-consensus rate and lift;
- permutation p-value;
- reference-free majority false-accept and true-accept rates;
- verifier calls implied by the selected branch; and
- per-judge parse failures, false-accept rates, and true-accept rates.

## Decision and Interpretation Rules

The result will be reported as observed. A 0/10 result would provide a natural
stand-down example for this panel and rule. An intermediate result would be a
boundary setting. A high result would show that natural CREAK claims also
activate routing and would not support a natural low-risk claim.

No outcome is a formal safety certificate. A not-flagged split means only that
the frozen empirical conjunction was not met on that calibration probe.
