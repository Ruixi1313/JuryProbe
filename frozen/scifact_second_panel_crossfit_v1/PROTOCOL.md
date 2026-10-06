# SciFact Second-Panel Grouped Cross-Fit Protocol v1

Status: frozen before any SciFact call to the second panel.

Freeze date: 2026-07-22

## Question

On the fixed SciFact family, does the unchanged JuryProbe calibration rule
measure panel-specific error dependence, and what does Ground-All-Accepts gain
over reference-free majority for a pre-specified higher-capacity panel?

This is a panel-axis specificity experiment. It does not search for an easy
dataset, tune the JuryProbe thresholds, or certify that a panel is safe.

## Fixed Data

- Claims: `data/scifact_natural_n190.jsonl`
- References and evidence provenance: `data/scifact_retrieval_refs.jsonl`
- Size: 190 clean claims and 190 false claims
- No claim is added, removed, filtered, or relabeled for this experiment.
- The benchmark full abstract in `refs.oracle_abstract.reference` is the only
  grounded reference used in the primary Ground-All-Accepts comparison.
- The existing BM25 conditions remain separate retrieval stress tests and are
  not used to select the second panel or the cross-fit folds.

## Panels

Original panel (frozen comparison):

- `meta-llama/llama-3.1-8b-instruct`
- `qwen/qwen-2.5-7b-instruct`
- `google/gemma-3-12b-it`

Pre-specified second panel:

- `meta-llama/llama-3.3-70b-instruct`
- `qwen/qwen-2.5-72b-instruct`
- `google/gemma-2-27b-it`

The second panel was already specified in the repository's earlier Entity
panel-axis experiment before this SciFact protocol. Its Entity result was
high-risk rather than a stand-down result. It is reused here because it gives a
one-to-one higher-capacity counterpart from the same three independent model
lineages; it was not selected using SciFact outputs.

Only this second panel may be run. No model may be replaced after SciFact calls
begin. A transport-only preflight may verify that each endpoint returns a
parseable binary answer on a non-study statement. If any endpoint remains
unavailable, the formal experiment is aborted and no substitute panel is run.

## Prompts and Decisions

- Reference-free prompt: unchanged `src.judges._build_statement_prompt`.
- Grounded prompt: unchanged `scripts.evaluate_guardrail_policies.grounded_prompt`.
- Temperature: 0.
- Output: strict binary `true` / `false` parsing.
- Panel aggregation: majority accept (at least two of three judges).
- False consensus: all three judges accept a false claim.
- No gold-label substitution or oracle decision is permitted.

Transport errors and unparseable responses may be retried twice with the same
model, prompt, and decoding settings. The primary analysis requires zero
remaining parse failures. Failed calls are never converted to `false`, and a
model with persistent failures is not replaced.

## Grouped Five-Fold Cross-Fitting

Claims sharing any SciFact evidence document are placed in the same connected
source group. Groups are assigned deterministically with seed 20260722 to five
folds while balancing clean and false counts. The frozen fold artifact must
contain exactly 38 clean and 38 false claims in every deployment fold.

For fold k:

- calibration: the other four folds (152 clean + 152 false);
- deployment: fold k (38 clean + 38 false);
- no evidence document may occur in both calibration and deployment;
- each claim appears as deployment data exactly once.

## Frozen JuryProbe Rule

The calibration fold is flagged high-risk only when all three conditions hold:

- mean pairwise FN correlation > 0.15;
- false-consensus lift > 1.5;
- permutation p-value < 0.05.

The permutation count is 3,000 and the permutation seed is the fold number.
Thresholds and aggregation are unchanged from the submitted policy.

## Deployment Policies

Every deployment fold reports:

1. Reference-Free Majority.
2. Ground-All-Accepts: run the same panel with the benchmark full abstract for
   every reference-free majority accept; retain reference-free rejects.
3. JuryProbe-Routed: equal to Ground-All-Accepts in flagged folds and equal to
   Reference-Free Majority in non-flagged folds.

Ground-All-Accepts is evaluated in every fold regardless of the calibration
flag. It is the paired counterfactual for how much full-abstract grounding can
still change the panel's reference-free accepts.

## Required Reporting

- number of flagged folds;
- fold-level calibration FN correlation, lift, p-value, and false-consensus
  count;
- out-of-fold RF majority false accepts and clean true accepts;
- out-of-fold RF all-three false consensus;
- out-of-fold Ground-All-Accepts false accepts and clean true accepts;
- false accepts corrected and clean accepts lost by grounding;
- trusted-reference acquisitions;
- JuryProbe-Routed out-of-fold outcomes;
- raw counts and Wilson 95% intervals for binomial rates;
- parse-failure counts by model and condition.

No post-hoc non-inferiority margin is introduced. The paired changes and raw
counts are reported directly.

## Execution

Run the transport-only preflight first:

```bash
python3 scripts/evaluate_scifact_second_panel_crossfit.py --preflight
```

If all three fixed endpoints return a parseable verdict, run the complete
formal experiment:

```bash
python3 scripts/evaluate_scifact_second_panel_crossfit.py \
  --run-rf --run-grounded --workers 3
```

The caches are append-only and resumable. Invalid records are retried with the
same model; no model substitution is allowed. Re-running without either
`--run-*` flag performs analysis only and never creates missing verdicts.

Formal outputs:

- `results/scifact_second_panel_v1_rf.jsonl`
- `results/scifact_second_panel_v1_grounded_full_abstract.jsonl`
- `results/scifact_second_panel_crossfit_v1_summary.json`
- `results/scifact_second_panel_crossfit_v1_summary.md`

## Interpretation Rules

- If the second panel is not flagged in one or more folds, this exercises the
  stand-down branch on natural SciFact claims; it is not a safety certificate.
- If Ground-All-Accepts changes few or no false accepts in those folds, report
  the observed paired benefit and its uncertainty without claiming equivalence.
- If the second panel remains flagged, report that result. It indicates that
  higher model capacity did not produce a stand-down regime on this dataset.
- If results vary by fold, report boundary instability rather than selecting a
  favorable fold.
- No result establishes zero-shot transfer to a new domain, panel, prompt, or
  error distribution.
