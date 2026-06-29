# JuryProbe Experiment Data Map

Date: 2026-06-10

Purpose: summarize the current experimental evidence before paper drafting.
For each experiment, this memo records why the data is needed, what role it
plays in the paper, and the current result.

## Main Story

JuryProbe is now a guardrail paper, not only a measurement paper.

Core chain:

1. Reference-free factuality judge panels can share correlated false negatives.
2. Agreement can therefore become false consensus rather than independent
   evidence.
3. Grounding collapses the correlated-FN failure mode.
4. JuryProbe uses panel-level risk assessment to route high-risk accept
   decisions to grounded verification.
5. The routed guardrail removes false accepts with fewer verifier calls than
   always-grounded verification.

Metric distinction to preserve:

- FN-only correlation measures dependence.
- False-consensus lift measures consequence.
- The risk signal is panel-level, not a sample-level classifier.

## 1. Source Frame and Pool Freeze

Artifacts:

- `data/frozen/v1/master_claim_pool_v1.jsonl`
- `data/frozen/v1/number_pool_v1.jsonl`
- `data/frozen/v1/entity_pool_v1.jsonl`
- `data/frozen/v1/relation_pool_v1.jsonl`
- `data/frozen/v1/pool_manifest_v1.json`

Why needed:

- Prevents the criticism that Number, Entity, and Relation examples were found
  opportunistically.
- Gives all corruption families the same FEVER SUPPORTS source frame.
- Separates pool construction from judge evaluation.
- Ensures GPT-4o is not involved in pool selection.

Result:

| Quantity | Value |
|---|---:|
| FEVER rows scanned | 145,449 |
| SUPPORTS rows | 80,035 |
| Local-atomic pass | 53,850 |
| Master pool size | 53,850 |
| Number pool size | 4,705 |
| Entity pool size | 48,938 |
| Relation pool size | 774 |
| Pool seed | 42 |

Paper role:

This supports the data-construction paragraph and artifact transparency.
It makes the study look like a reproducible framework rather than a collection
of hand-picked examples.

## 2. Construction Audit and Frozen Datasets

Artifacts:

- `data/frozen/number_v3/number_corruption_pool_v3_n300.jsonl`
- `data/frozen/v4/entity_corruption_pool_v4_n300.jsonl`
- Relation v4 construction artifacts only; no judge evaluation.

Why needed:

- The paper's conclusions rest on corrupted factual claims. If construction
  artifacts are unstable, the judge results are less meaningful.
- Versioned audits show that dataset quality improved before judge evaluation,
  not after seeing desired model results.
- Attrition rates document how much filtering was needed.

Result:

| Family | Final status | Clean accepted | Clean rejected | Corrupt accepted | Corrupt rejected |
|---|---|---:|---:|---:|---:|
| Number v3 | confirmatory | 300 | 394 | 300 | 372 |
| Entity v4 | confirmatory | 300 | 108 | 300 | 1,193 |
| Relation v4 | exploratory only | 300 | not main | 300 | not main |

Important interpretation:

- Number and Entity are the confirmatory families.
- Relation is stopped at construction/audit because relation reversal remained
  definitionally unstable in FEVER.
- Relation should not carry the main conclusion.

Paper role:

This belongs in Dataset Construction / Appendix. In the main text, use it to
say Number and Entity are frozen, audited, fixed-seed datasets.

## 3. Confirmatory Reference-Free Risk Measurement

Artifacts:

- `results/frozen/number_v3/number_corruption_pool_v3_n300_analysis.json`
- `results/frozen/v4/entity_corruption_pool_v4_n300_analysis.json`

Why needed:

- Establishes the problem: reference-free judge panels make correlated false
  negatives.
- Number alone could be dismissed as number-specific; Entity shows the effect
  is not number-specific.
- FN corr and lift jointly identify high-risk panels:
  dependence plus consequence.

Result:

| Family | GPT-4o detectable acc | FN-only corr | Detectable all-3 false consensus | Residual lift | Perm p |
|---|---:|---:|---:|---:|---:|
| Number v3 | 0.787 | 0.402 | 0.159 | 3.13x | 0.0003 |
| Entity v4 | 0.907 | 0.368 | 0.031 | 18.13x | 0.0003 |

Pass interpretation:

- Number replication: PASS.
- Entity replication: PASS.
- Main problem statement is supported across two different corruption families.

Paper role:

This is the first main experimental result: reference-free juries can exhibit
correlated false negatives and false consensus.

## 4. Grounding Collapse / Mechanistic Mitigation

Artifacts:

- Same confirmatory analysis files as above.
- Grounded judge outputs:
  - `results/guardrail_grounded/number_corruption_pool_v3_n300_grounded_verifier_validated.jsonl`
  - `results/guardrail_grounded/entity_corruption_pool_v4_n300_grounded_verifier_validated.jsonl`

Why needed:

- Shows the problem is tied to reference-free judging, not an unavoidable
  property of the items.
- Justifies grounded verification as the escalation target.
- Turns the paper from "problem measurement" into "diagnostic plus mitigation."

Result:

| Family | RF mean corr | Grounded mean corr | RF all-3 | Grounded all-3 | Reduction p |
|---|---:|---:|---:|---:|---:|
| Number v3 | 0.386 | 0.000 | 0.159 | 0.000 | 0.0002 |
| Entity v4 | 0.393 | -0.003 | 0.031 | 0.000 | 0.0002 |

Paper role:

This is the mechanism result: grounding mitigates correlated false negatives.

## 5. Held-out Guardrail Evaluation

Artifacts:

- `results/frozen/guardrail_heldout_multiseed/summary.json`
- `results/frozen/guardrail_heldout_multiseed/summary.md`

Why needed:

- Prevents the criticism that high-risk is defined on the deployment/test set.
- Risk is estimated on calibration; policy is evaluated on held-out deployment.
- 10 split seeds show stability.

Risk result:

| Family | High-risk detected | FN corr | Residual lift | p-value |
|---|---:|---:|---:|---:|
| Number | 10/10 | 0.385 ± 0.028 | 2.602 ± 0.202 | 0.000 ± 0.000 |
| Entity | 10/10 | 0.348 ± 0.062 | 11.439 ± 5.267 | 0.011 ± 0.016 |

Policy result:

| Family | Policy | False accept | True accept | False consensus | Verifier items |
|---|---|---:|---:|---:|---:|
| Number | RF Majority | 0.427 ± 0.029 | 0.581 ± 0.029 | 0.201 ± 0.022 | 0 |
| Number | JuryProbe-Routed | 0.000 ± 0.000 | 0.581 ± 0.029 | 0.000 ± 0.000 | 151.2 ± 4.8 |
| Number | Always Grounded | 0.000 ± 0.000 | 1.000 ± 0.000 | 0.000 ± 0.000 | 300 |
| Entity | RF Majority | 0.119 ± 0.014 | 0.639 ± 0.027 | 0.035 ± 0.011 | 0 |
| Entity | JuryProbe-Routed | 0.000 ± 0.000 | 0.639 ± 0.027 | 0.000 ± 0.000 | 113.7 ± 4.4 |
| Entity | Always Grounded | 0.000 ± 0.000 | 1.000 ± 0.000 | 0.000 ± 0.000 | 300 |

Paper role:

This is the main guardrail result. JuryProbe-Routed removes false accepts and
false consensus while using about half or less of always-grounded verifier
items.

Operational cost metric:

- Number: JuryProbe-Routed uses 453.6 ± 14.3 model calls versus 900.0 for
  Always Grounded, a 49.6% verifier call reduction.
- Entity: JuryProbe-Routed uses 341.1 ± 13.2 model calls versus 900.0 for
  Always Grounded, a 62.1% verifier call reduction.
- Report this as "verifier call reduction," not dollar cost.

## 6. Baseline Guardrail Comparison

Artifacts:

- `results/frozen/guardrail_baselines_v1/summary.json`
- `results/frozen/guardrail_baselines_v1/summary.md`

Why needed:

- Trust or Escalate and related routing work make escalation a known idea.
- The paper must show JuryProbe is not merely "escalate sometimes."
- Disagreement-Routed tests the common strategy: escalate when judges disagree.
- Random-Routed tests whether gains are explained by spending the same verifier
  budget.

Result:

| Family | Policy | False accept | True accept | False consensus | Verifier items |
|---|---|---:|---:|---:|---:|
| Number | Disagreement-Routed | 0.201 ± 0.022 | 0.762 ± 0.029 | 0.201 ± 0.022 | 140.1 ± 6.5 |
| Number | Random-Routed | 0.212 ± 0.013 | 0.792 ± 0.019 | 0.100 ± 0.009 | 151.2 ± 4.8 |
| Number | JuryProbe-Routed | 0.000 ± 0.000 | 0.581 ± 0.029 | 0.000 ± 0.000 | 151.2 ± 4.8 |
| Entity | Disagreement-Routed | 0.035 ± 0.011 | 0.841 ± 0.015 | 0.035 ± 0.011 | 102.0 ± 3.5 |
| Entity | Random-Routed | 0.074 ± 0.008 | 0.776 ± 0.021 | 0.022 ± 0.007 | 113.7 ± 4.4 |
| Entity | JuryProbe-Routed | 0.000 ± 0.000 | 0.639 ± 0.027 | 0.000 ± 0.000 | 113.7 ± 4.4 |

Interpretation:

- Disagreement-Routed cannot catch unanimous false accepts by construction.
- Random-Routed cannot match JuryProbe at the same verifier budget.
- JuryProbe is specifically targeting false consensus, not generic
  uncertainty or disagreement.

Paper role:

This is the key guardrail baseline table.

## 7. Low-risk Specificity Control

Artifacts:

- `results/frozen/low_risk_specificity_v1/summary.json`
- `results/frozen/low_risk_specificity_v1/summary.md`

Why needed:

- Reviewer may ask whether JuryProbe always declares high-risk.
- Specificity control shows that when judges are grounded, the risk signal
  collapses and the system does not alarm.

Result:

| Setting | Family | High-risk detected | FN corr | All-3 FN | Lift | p-value |
|---|---|---:|---:|---:|---:|---:|
| Grounded calibration | Number | 0/10 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 1.000 |
| Grounded calibration | Entity | 0/10 | -0.003 ± 0.002 | 0.000 ± 0.000 | 0.000 ± 0.000 | 1.000 |

Paper role:

This supports specificity: JuryProbe is not an always-on alarm.

## 8. Robustness Checks

Artifacts:

- `results/frozen/guardrail_robustness_v1/summary.json`
- `results/frozen/guardrail_robustness_v1/summary.md`

Why needed:

- Threshold sensitivity defends the choice of corr/lift thresholds.
- Random-Routed stability shows the random baseline is not a lucky draw.
- L1JO checks whether dependence is driven by a single judge; this should stay
  appendix-only because two-judge lift estimates are noisier.

Threshold sensitivity result:

- With p < 0.05, both Number and Entity are 10/10 high-risk for corr thresholds
  0.10, 0.15, 0.20, and 0.25 with lift thresholds 1.25, 1.50, and 2.00.
- Entity drops to 6/10 at corr > 0.30.

Random stability result:

| Family | Trials per split | Random false accept | Within-split random SD |
|---|---:|---:|---:|
| Number | 100 | 0.212 ± 0.013 | 0.023 |
| Entity | 100 | 0.074 ± 0.008 | 0.013 |

L1JO interpretation:

- Positive FN dependence appears across two-judge subpanels.
- Do not place L1JO in the main text.
- Use only as appendix evidence that dependence is not obviously a single-model
  artifact.

Paper role:

Threshold sensitivity and random stability can appear in main or appendix.
L1JO should remain appendix-only.

## 9. Strong Judge Slice

Artifacts:

- `results/frozen/strong_judge_slice_v1/summary.json`
- `results/frozen/strong_judge_slice_v1/summary.md`
- `docs/strong_judge_slice_plan.md`

Why needed:

- Tests whether using stronger reference-free judges removes false consensus.
- Pre-registered as supplementary robustness only.
- Does not affect risk thresholds, policy definition, routing logic, or main
  conclusions.

Judge pool:

- Llama-3.1-8B-Instruct
- Gemma-3-12B-IT
- Qwen3-32B

Result:

| Metric | Value |
|---|---:|
| FN corr | 0.252 |
| False consensus | 0.137 |
| Lift | 2.169 |
| p-value | 0.0003 |
| RF majority false accept | 0.387 |
| RF majority true accept | 0.647 |
| Final parse fail | 0 |

Paper role:

Supplementary robustness: stronger reference-free judges may reduce risk, but
do not eliminate correlated false consensus.

## 10. Evaluation Artifact Transparency

Artifacts:

- `results/guardrail_grounded/validated_cache_manifest.json`

Why needed:

- Shows grounded verifier outputs are complete and not silently replaced by
  oracle/gold labels.
- Documents retry and final parse-fail behavior.

Result:

| Family | Raw parse fail | Retried | Final parse fail |
|---|---:|---:|---:|
| Number | 7 | 7 | 0 |
| Entity | 8 | 8 | 0 |

Paper role:

Use in appendix or reproducibility section. Important sentence: no oracle or
gold fallback is used in guardrail evaluation.

## What Should Be Main Text vs Appendix

Main text:

- Source frame summary.
- Number and Entity confirmatory results.
- Grounding collapse.
- Held-out JuryProbe-Routed policy table.
- Baseline comparison against RF Majority, RF Unanimous, Disagreement-Routed,
  Random-Routed, and Always Grounded.
- Specificity control.

Appendix:

- Construction audit histories and attrition.
- Threshold sensitivity.
- Random-Routed stability details.
- Strong Judge Slice.
- L1JO, with cautious wording.
- Parse-fail and cache-validation manifest.

## Current Evidence Claim

The current evidence supports this claim:

Cheap reference-free factuality judge panels can exhibit correlated false
negatives, causing false consensus on corrupted claims. JuryProbe estimates this
panel-level risk from calibration data and routes high-risk accept decisions to
grounded verification. Across Number and Entity, this removes false accepts in
held-out deployment splits while requiring substantially fewer grounded verifier
items than always-grounded verification. The effect is not explained by ordinary
disagreement routing or budget-matched random routing, and the risk signal does
not fire in grounded low-risk controls.
