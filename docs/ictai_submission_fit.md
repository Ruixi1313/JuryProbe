# ICTAI Submission Fit Memo

Date: 2026-06-10

Purpose: adapt JuryProbe for IEEE ICTAI as a guardrail / AI-tool paper rather
than a measurement-only paper.

## ICTAI 2026 Facts Checked

Source: official ICTAI 2026 website.

- Conference: 38th IEEE International Conference on Tools with Artificial
  Intelligence.
- Dates/location: 2-4 November 2026, Boca Raton, FL, USA.
- Paper submission deadline: June 30, 2026.
- Review: double-blind.
- Full paper: maximum 8 pages.
- Short paper: maximum 5 pages.
- IEEE template is mandatory.
- Accepted papers presented at the conference will be submitted for publication
  to IEEE Xplore.

Scope signals from CFP:

- ICTAI emphasizes the "creation and exchange of ideas" related to AI across
  academia, industry, and government.
- It explicitly focuses on transfer into practical tools, intelligent systems,
  and AI applications.
- It covers specifying, developing, and evaluating theoretical underpinnings and
  applied mechanisms of AI-based components of computer tools.
- Relevant topic categories for JuryProbe:
  - Natural Language Processing / Large Language Models
  - AI and Societal Impact: trustworthy AI
  - AI and Decision Systems: decision guidance and collaborative decisions
  - Uncertainty in AI
  - Machine Learning: preference/ranking, ensemble learning

## Fit Assessment

JuryProbe is a good ICTAI fit if presented as:

> A practical guardrail framework for deciding when cheap reference-free LLM
> factuality judge panels should be routed to grounded verification.

JuryProbe is a weaker ICTAI fit if presented as:

> A measurement study showing LLM judge errors are correlated.

Reason:

ICTAI's identity is "Tools with Artificial Intelligence." The paper should
therefore emphasize an actionable mechanism, policy, and evaluation protocol,
not only the empirical discovery.

## Required Reframing

### Title

Current skeleton title is measurement-oriented:

> JuryProbe: Correlated False Negatives in Reference-Free LLM Factuality Judging

ICTAI-oriented title:

> JuryProbe: A Consensus-Risk Guardrail for Reference-Free LLM Factuality Judges

Alternative:

> JuryProbe: Routing Risky LLM Judge Consensus to Grounded Factual Verification

### Abstract

The abstract should lead with the guardrail problem:

- Cheap LLM judge juries are attractive.
- Agreement is often treated as confidence.
- In reference-free factuality, agreement can be false consensus.
- JuryProbe estimates panel-level correlated-failure risk.
- High-risk accept decisions are routed to grounded verification.
- Held-out results show false accepts drop to zero with fewer verifier calls
  than always-grounded verification.

Do not lead with:

- "We measure inter-judge correlation..."
- "We show LLM judges are not independent..."

Those are supporting facts, not the ICTAI-facing contribution.

### Contributions

Recommended contribution list:

1. A consensus-risk guardrail for reference-free LLM factuality judge panels.
2. Panel-level risk metrics combining FN-only correlation and
   false-consensus lift.
3. A frozen FEVER-based construction pipeline for Number and Entity corruption
   families with audit and attrition artifacts.
4. A held-out routed policy evaluation showing that JuryProbe-Routed removes
   false accepts while using substantially fewer grounded verifier calls than
   Always Grounded.
5. Baseline and specificity analyses showing the effect is not explained by
   disagreement routing, random routing, or an always-on alarm.

## What to Add to the Paper

### Algorithm Box

Add an Algorithm 1:

`JuryProbe-Routed Accept Protection`

Inputs:

- calibration probe
- reference-free judge outputs
- FN-corr threshold
- lift threshold
- permutation p-value threshold
- deployment item
- grounded verifier

Steps:

1. Estimate panel risk on calibration only.
2. If panel is low-risk, use RF majority.
3. If panel is high-risk and RF majority rejects, keep reject.
4. If panel is high-risk and RF majority accepts, route to grounded verifier.
5. Return grounded majority as final accept/reject.

Why:

ICTAI likes tools/mechanisms. A concrete algorithm makes JuryProbe feel like a
deployable guardrail rather than a measurement result.

### System/Workflow Figure

Add a simple first-page or method figure:

Reference-free claim -> cheap judge jury -> JuryProbe risk assessment ->
low-risk accept/reject or high-risk accept escalation -> grounded verifier ->
final decision.

Why:

This directly communicates "what should people do after learning this?"

### Resource Metric

Keep "Extra Verifier Calls" and "Verifier Items" rather than vague "cost."

Why:

ICTAI reviewers will likely appreciate operational metrics, but exact dollar
cost is model/vendor dependent.

Add "Verifier Call Reduction" relative to Always Grounded:

- Number: 453.6 routed model calls vs. 900.0 always-grounded calls, a 49.6%
  reduction.
- Entity: 341.1 routed model calls vs. 900.0 always-grounded calls, a 62.1%
  reduction.

Use the phrase "verifier call reduction" rather than "cost reduction."

### Calibration Risk Table

Place a compact calibration risk table in the main text before policy results.
It should report high-risk detected splits, FN correlation, false-consensus
rate, permuted null rate, lift, and p-value over the 10 held-out calibration
splits.

Why:

It makes clear that the high-risk regime is estimated before deployment policy
evaluation and that JuryProbe's risk signal combines dependence and consequence.

### Main Baseline Table

The guardrail table should include:

- RF Majority
- RF Unanimous
- Disagreement-Routed
- Random-Routed
- JuryProbe-Routed
- Always Grounded

Why:

Trust or Escalate makes selective escalation a known idea. The paper must show
JuryProbe's routing signal is not generic disagreement or generic budget.

### Specificity Control

Keep the grounded low-risk specificity result in main or near-main text.

Why:

It shows JuryProbe is not an always-escalate alarm.

### Related Work Matrix

Place the related-work matrix at the end of Related Work as Table 1:

> Positioning of JuryProbe relative to related work.

Then transition:

> Unlike prior work, JuryProbe combines judge panels, factuality-oriented
> verification, grounded escalation, and consensus-risk routing in a single
> guardrail framework.

## What Not to Add

- Do not revive Relation as a main experiment.
- Do not add more judge families as main evidence.
- Do not make L1JO a main-text result.
- Do not overemphasize Condorcet / jury theorem theory; use it as motivation
  only.
- Do not claim "first guardrail for LLM judges."

## Recommended Main Paper Structure

1. Introduction
   - Guardrail problem: agreement is not enough in reference-free factuality.
   - What users should do: route risky accept decisions to grounding.

2. Related Work
   - LLM-as-a-Judge
   - Judge dependence
   - Factuality and grounding
   - Selective escalation
   - Table 1 positioning matrix

3. JuryProbe Method
   - Risk metrics: FN corr, false-consensus lift, permutation p-value.
   - Algorithm 1: routed accept protection.
   - Grounded verifier definition.

4. Data Construction
   - FEVER source frame.
   - Number and Entity frozen datasets.
   - Audits and attrition summarized, details in appendix.

5. Experiments
   - Problem: Number and Entity risk measurement.
   - Mitigation: grounding collapse.
   - Guardrail: held-out routed policy.
   - Baselines: disagreement and random.
   - Specificity: grounded low-risk control.

6. Discussion and Limitations
   - When to use JuryProbe.
   - Limits: FEVER, binary factuality, relation exploratory, reference
     availability.
   - Future work: planning, forecasting, strategic decisions.

7. Reproducibility
   - Frozen pools, build manifests, evaluation manifests.
   - Double-blind-safe artifact statement.

## Page-budget Recommendation

ICTAI full paper limit is 8 pages, so keep the main text tight:

- Introduction: 0.9 page
- Related Work + matrix: 1.0 page
- Method: 1.2 pages
- Data Construction: 0.8 page
- Experiments/Results: 2.8 pages
- Discussion/Limitations/Reproducibility: 0.8 page
- References: outside or inside limit depending final template settings; verify
  before formatting.

Appendix/supplementary material should carry:

- detailed construction audits
- threshold sensitivity
- Random-Routed stability details
- Strong Judge Slice
- L1JO
- parse-fail/retry manifest

## Double-blind Checklist

- Remove author names and affiliations.
- Do not link to a non-anonymous GitHub repository in the submitted version.
- If artifacts are mentioned, use anonymized filenames or an anonymous archive.
- Avoid self-identifying paths such as local usernames.
- Do not include `.env` or API/provider-specific private details.

## Bottom Line

No new core experiment is needed for ICTAI. The required change is framing:

JuryProbe should be written as a practical trustworthy-AI guardrail for
LLM-based factuality judging, with correlated false negatives as the diagnostic
that triggers grounded escalation.
