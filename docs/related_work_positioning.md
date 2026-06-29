# Related Work Positioning Memo

Date: 2026-06-09

Purpose: keep JuryProbe's guardrail contribution clearly separated from nearby
work. This is a positioning memo, not final paper prose.

## Claim Boundary

Do not claim:

- "First guardrail for LLM judges."
- "First to show LLM judges are correlated."
- "First selective evaluation method for LLM judging."

Preferred claim:

JuryProbe uses correlated false negatives and false-consensus lift to identify
when cheap reference-free factuality judge agreement should be routed to
grounded verification.

## Nearby Work

| Work | What it does | Overlap with JuryProbe | JuryProbe distinction |
|---|---|---|---|
| Trust or Escalate | Selectively trusts LLM judges or escalates to stronger models / humans to guarantee human agreement. | Very close to the guardrail framing: cheap judge then escalation. | Its risk signal is judge confidence / simulated annotators and its target is human agreement in selective evaluation. JuryProbe's risk signal is panel-level FN-only correlation plus false-consensus lift, targeting shared false negatives in reference-free factuality. |
| PoLL / Replacing Judges with Juries | Uses a panel of smaller LLM evaluators as a cheaper alternative to a single large judge. | Cheap judge jury setup is similar. | PoLL argues panels can be useful. JuryProbe asks when panel agreement is unsafe and should be routed to grounding. |
| FActScore | Decomposes long-form generation into atomic facts and checks support against reliable knowledge sources. | Factuality and grounding are directly relevant. | FActScore is a factual precision evaluator, not a judge-jury risk diagnostic. It does not study correlated false negatives, false-consensus lift, or routing from reference-free judging. |
| SAFE / Long-form factuality | Uses search-augmented LLM agents to evaluate whether facts are supported by search results. | Grounded factuality verification is related. | SAFE is a grounded factuality evaluator. JuryProbe decides when a cheap reference-free jury should be upgraded to grounded verification. |
| No Free Labels | Shows LLM judges struggle to evaluate questions they cannot answer and that human references improve judge-human agreement. | The importance of references / grounding is close. | It is not a multi-judge panel study, does not measure false-consensus lift, and does not propose a correlated-FN guardrail routing policy. |
| False Negative Problem of Input-conflicting Hallucination | Studies false negative bias in context-grounded factuality discrimination. | The false-negative concept is related. | It is not a reference-free judge jury setting and does not study correlated misses across multiple judges or routing to grounding. |
| UDA / pairwise LLM-as-a-Judge false consensus | Reported as related to consensus-driven optimization and misleading judge consensus. | The phrase "false consensus" may overlap. | Needs exact citation verification before paper use. Based on the described overlap, it concerns pairwise judge debiasing / Elo-style alignment, not reference-free factuality guardrails or grounding collapse. |

## Differentiating Sentence

Existing work covers cheap judge panels, selective trust/escalation, grounded
factuality verification, references improving judge accuracy, LLM false
negative tendencies, and misleading judge consensus. JuryProbe combines these
threads in a different deployment problem: detecting panel-level correlated
false negatives in cheap reference-free factuality judging, then routing risky
accept decisions to grounded verification.

## Guardrail Framing

Main flow:

```text
Reference-Free Claim
        |
        v
Cheap Judge Jury
        |
        v
JuryProbe Risk Assessment
  - FN-only correlation
  - false-consensus lift
        |
        v
Low Risk -> keep RF majority
        |
        v
High Risk
        |
        v
RF majority accept -> grounding / strong verifier
RF reject          -> keep reject
        |
        v
Final Decision
```

Key language:

- "High-Risk Panel" is a panel-level risk regime, not a sample-level classifier.
- JuryProbe protects accept decisions.
- Routing is triggered by the combination of panel risk and a reference-free
  accept decision.
- Extra verifier calls should be reported directly instead of turning them into
  a cost estimate.

## Most Important Distinction

The closest work is Trust or Escalate.

Use this contrast:

- Trust or Escalate: confidence-calibrated selective evaluation for human
  agreement.
- JuryProbe: correlation-based risk assessment for shared false negatives in
  reference-free factuality, with routing to grounded verification.
