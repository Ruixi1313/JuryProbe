# Unseen-Family Calibration-Transfer Stress Test v1

Freeze date: 2026-07-20

## Status and Scope

This is a post-review exploratory stress test. The protocol is frozen before
executing the pooled leave-one-family-out harness, but the underlying
per-family reference-free results were already available. It is therefore not
presented as preregistered confirmatory evidence.

The test evaluates cross-family calibration transfer over known benchmark
families. It does not establish open-world transfer to arbitrary hallucinations
or error types that are absent from all evaluated datasets.

## Frozen Risk Rule

The analysis reuses the submitted deployment-time estimator and thresholds:

- mean pairwise FN correlation > 0.15;
- false-consensus lift > 1.5;
- permutation p-value < 0.05;
- 3,000 permutations;
- split seeds 1 through 10.

The risk statistic is computed from corrupted calibration items. Clean
calibration items are retained to mirror the submitted 150-clean/150-corrupt
probe layout but do not enter the risk statistic.

## Families

Signal-family donors:

- Number;
- Entity;
- Attribute;
- FEVER-Refutes;
- SciFact.

Reported targets:

- all five signal families above;
- Obvious-Number boundary control;
- Self-Contained Contradiction negative control.

Controls are targets but are not included in the pooled signal-family donor
probe.

## Pooled Leave-One-Family-Out Construction

For each target family and split seed:

1. Exclude the target family completely from calibration.
2. If the target is a signal family, construct the calibration probe from all
   other signal families. If the target is a control, use all five signal
   families.
3. Draw a total of 150 clean and 150 corrupted calibration items, balanced as
   evenly as possible across donor families and sampled without replacement.
4. Prefix item identifiers with their family names before pooling so that
   cache keys cannot collide.
5. Compute the source calibration label using the frozen risk rule.
6. Draw a target evaluation sample without using it in calibration: 150 clean
   and 150 corrupted items for 300-per-class targets, and 95 clean and 95
   corrupted items for SciFact.
7. Compute the target family's diagnostic label post hoc for comparison only.
   This target label never changes routing.
8. Apply the source label to target reference-free majority decisions and
   report how many target claims would be routed. This harness does not infer
   grounded outcomes where no grounded cache exists.

Existing cached reference-free parse failures are retained under the submitted
implementation's convention: only a literal `true` is an acceptance. Their
counts are reported explicitly. A complete-case sensitivity analysis removes
items with any parse failure before sampling and repeats the full protocol.

## Required Reporting

All target families and all ten seeds are reported. For each target, report:

- source-label high-risk count;
- post-hoc target-label high-risk count;
- high/high, high/not-flagged, not-flagged/high, and
  not-flagged/not-flagged counts;
- reference-free majority false-accept and true-accept rates;
- reference-free unanimous false-consensus rate;
- routed claim and judge-call counts implied by the source label.
- cached parse-failure counts and complete-case sensitivity results.

A high source label and high target label provide evidence of conservative
cross-family calibration transfer for that tested target. A high source label
and not-flagged target label indicate over-routing. A not-flagged source label
and high target label indicate a missed unseen-family risk. None of these
outcomes is a formal safety guarantee.
