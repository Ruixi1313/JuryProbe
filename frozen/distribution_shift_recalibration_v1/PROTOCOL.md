# Distribution-Shift Recalibration Stress Test v1

## Status

This protocol was frozen before running the analysis. It is a post-review,
zero-API stress test over cached reference-free judge verdicts. It does not
provide a guarantee for arbitrary open-world shifts.

## Question

The submitted policy fixes one panel-level risk label before deployment. This
stress test asks what happens when a panel initially stands down on a negative
control but the error stream later contains an increasing proportion of a
previously absent high-risk family. It then measures whether periodic labeled
recalibration reactivates the same frozen routing rule.

## Frozen Inputs

The initial calibration source is Self-Contained Contradiction Control v2. The
three shift targets are Number v3, Entity v4, and SciFact Natural v1. All judge
verdicts come from the existing reference-free caches for the submitted
three-judge panel.

No grounded verdict is used. No model is called. Item text is not inspected or
filtered during this analysis.

## Fixed Rule

The risk rule and implementation are unchanged:

- mean pairwise FN-only correlation greater than 0.15;
- false-consensus lift greater than 1.5; and
- permutation p-value less than 0.05, using 3,000 permutations.

All three conditions must hold. The submitted conventions for parse failures,
zero-variance correlations, and zero permutation-null means are retained.

## Sampling Design

The analysis uses seeds 1 through 10. Within every target and seed, samples are
drawn without replacement and assigned to mutually exclusive roles.

1. Initial calibration uses 95 clean and 95 corrupted negative-control items.
2. The shifted evaluation stream contains 95 clean negative-control items and
   95 corrupted items.
3. A separate recalibration audit contains an equal number of clean
   negative-control and corrupted items. Audit sizes are 25, 50, and 95 per
   class.

The corrupted evaluation and audit samples contain target-family proportions
of 0%, 10%, 25%, 50%, and 100%. Clean items remain from the negative control so
that the stress test changes the corruption family rather than both classes at
once. Target and control quotas are rounded deterministically to the nearest
integer. Sampling is deterministic under a SHA-256-derived seed.

The maximum audit and evaluation sizes are 95 per class because SciFact has 190
items per class. This permits disjoint 95-item target audit and evaluation
samples at 100% contamination.

## Reported Quantities

For each target, contamination level, audit size, and seed, report:

- whether the initial control calibration is flagged;
- reference-free majority false-accept rate and unanimous false-consensus rate
  in the shifted evaluation stream while the initial label remains fixed;
- the FN-only correlation, false-consensus lift, permutation p-value, and risk
  decision on the separate recalibration audit; and
- the number of evaluation-stream majority accepts that would be routed after
  recalibration.

Results are summarized as the number of high-risk decisions over 10 seeds.
Cached parse failures are reported and a complete-case sensitivity analysis is
run if any branch outcome changes near a threshold.

## Interpretation Boundary

A positive result means that the unchanged empirical rule can detect the
listed benchmark shifts after receiving a new labeled audit probe. It does not
show zero-shot discrimination before recalibration, prove that the audit window
is representative, or guarantee detection of arbitrary future error types.
