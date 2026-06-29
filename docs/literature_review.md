# Literature Review v1

Date: 2026-06-10

Purpose: define the related-work frame for JuryProbe before drafting the paper.
This memo is intentionally organized around four literature categories rather
than a long undifferentiated citation list.

## Core Related-work Frame

JuryProbe should be positioned as a guardrail paper for reference-free
factuality judge panels.

Preferred contribution claim:

JuryProbe uses panel-level correlated false negatives and false-consensus lift
to decide when cheap reference-free factuality judge agreement should be routed
to grounded verification.

Do not claim:

- first guardrail for LLM judges
- first LLM-as-a-judge paper
- first work to show LLM judge errors are correlated
- first factuality verification method

Preserve this metric distinction:

- FN-only correlation measures dependence.
- False-consensus lift measures consequence.
- The risk signal is panel-level, not a sample-level classifier.

## Four Literature Categories

### 2.1 LLM-as-a-Judge

Purpose in paper:

- Establish what LLM judges are.
- Explain why LLM-as-a-judge evaluation is important and widely used.
- Motivate why judge panels/juries are a natural deployment setting.

Core citations:

- Zheng et al. 2023, MT-Bench Judge
- Zheng et al. 2023, Chatbot Arena
- Wang et al. 2023, "PandaLM: An Automatic Evaluation Benchmark for LLM Instruction Tuning Optimization"
- Zhu et al. 2023, "JudgeLM: Fine-tuned Large Language Models are Scalable Judges"
- Verga et al. 2024, "Replacing Judges with Juries" / PoLL

What to say:

Recent work uses LLMs as scalable judges for open-ended model outputs, including
prompted judges, fine-tuned judges, and panels of diverse smaller judges. PoLL
is especially relevant because it frames small-model panels as a practical
alternative to a single expensive judge.

JuryProbe distinction:

This literature asks whether LLM judges or judge panels can approximate human
evaluation cheaply and scalably. JuryProbe asks when panel agreement itself is
unsafe in reference-free factuality because the judges may share false-negative
blind spots.

Transition:

LLM Judge -> LLM Jury -> Judge Dependence.

### 2.2 Judge Correlation and Dependence

Purpose in paper:

- Explain why independence matters for judge panels.
- Establish that correlated LLM judge errors are a known and important problem.
- Create the conceptual bridge from "jury" to "effective independent votes."

Core citation:

- Kohli 2026, "Nine Judges, Two Effective Votes: Correlated Errors Undermine
  LLM Evaluation Panels"

Optional background:

- Condorcet jury theorem and correlated-vote / effective-sample-size literature
  if the paper needs theory background.

What to say:

Kohli shows that nominally large LLM judge panels can provide far fewer
effective independent votes because models make the same mistakes on the same
items. This is the most important related work for the independence claim.

JuryProbe distinction:

Kohli = judge independence and effective votes.

JuryProbe = reference-free factuality guardrail.

Kohli studies whether additional judges provide additional independent votes;
JuryProbe studies whether agreement from a reference-free factuality jury should
be trusted at all.

JuryProbe narrows the failure mode to correlated false negatives on corrupted
factual claims, measures false-consensus lift as the consequence of dependence,
shows grounding collapse, and evaluates a routed accept-protection policy.

### 2.3 Factuality Verification and Grounding

Purpose in paper:

- Explain why grounding is a reasonable mitigation.
- Show that factuality evaluation and hallucination detection are established
  research areas.
- Motivate grounded verification as the escalation target.

Core citations:

- Min et al. 2023, "FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation"
- Wei et al. 2024, "Long-form factuality in large language models" / SAFE
- Manakul et al. 2023, "SelfCheckGPT: Zero-Resource Black-Box Hallucination Detection for Generative Large Language Models"
- Li et al. 2023, "HaluEval: A Large-Scale Hallucination Evaluation Benchmark for Large Language Models"

What to say:

Factuality work studies hallucination detection, atomic fact decomposition,
sampling-based self-consistency, retrieval/search grounding, and supported-fact
metrics. FActScore and SAFE are especially important because they make
grounding and atomic fact support central to factuality evaluation. HaluEval
shows that LLMs struggle to recognize hallucinations, while external knowledge
and reasoning can help.

JuryProbe distinction:

These works study factuality evaluation or grounded verification. JuryProbe
studies when a reference-free judge jury should be upgraded to grounded
verification. The contribution is the routing signal and guardrail policy, not
a new factuality verifier.

Key sentence:

Existing work studies factuality and grounding, but not the deployment question
"when should a cheap reference-free jury be routed to grounded verification?"

### 2.4 Selective Evaluation and Escalation

Purpose in paper:

- Situate JuryProbe as a guardrail / routing method.
- Acknowledge that selective trust, abstention, and escalation are existing
  ideas.
- Distinguish uncertainty/disagreement-based routing from false-consensus
  routing.

Core citations:

- Jung et al. 2024, "Trust or Escalate: LLM Judges with Provable Guarantees for Human Agreement"
- Geifman and El-Yaniv 2017, "Selective Classification for Deep Neural Networks"
- Geifman and El-Yaniv 2019, "SelectiveNet: A Deep Neural Network with an Integrated Reject Option"

What to say:

Selective prediction methods trade coverage for lower risk by abstaining or
escalating uncertain cases. Trust or Escalate brings this idea into LLM judging:
it estimates judge confidence and selectively escalates to stronger models or
humans to guarantee human agreement.

JuryProbe distinction:

They = uncertainty / confidence / disagreement.

JuryProbe = false consensus.

Trust or Escalate routes based on estimated uncertainty and targets human
agreement. JuryProbe routes based on measured false-consensus risk and targets
factual correctness.

JuryProbe does not route because judges disagree or because a single judge is
uncertain. It routes because calibration reveals a high-risk panel whose
reference-free accept decisions can reflect correlated false negatives.

Key sentence:

Disagreement-based escalation cannot catch unanimous false acceptance by
construction; JuryProbe targets the case where agreement is the risk signal.

Future-work boundary:

While this work focuses on factuality judgments with verifiable references,
extending risk-aware routing to planning, forecasting, and strategic
decision-making remains an important direction for future work.

## Related Work Matrix

This table is a draft positioning matrix for the paper. It should be used to
show that prior work covers important pieces of the problem, but not the full
combination targeted by JuryProbe.

| Work | LLM Judge Panel | Factuality | Grounded Verification | Selective Escalation | Consensus-Risk Routing |
|---|---:|---:|---:|---:|---:|
| Kohli 2026 | ✓ | ✗ | ✗ | ✗ | Partial |
| Trust or Escalate | ✓ | ✗ | Partial | ✓ | ✗ |
| PoLL | ✓ | ✗ | ✗ | ✗ | ✗ |
| SAFE / LongFact | ✗ | ✓ | ✓ | ✗ | ✗ |
| FActScore | ✗ | ✓ | ✓ | ✗ | ✗ |
| HaluEval | ✗ | ✓ | ✗ | ✗ | ✗ |
| **JuryProbe** | **✓** | **✓** | **✓** | **✓** | **✓** |

Table notes:

- The table uses narrow paper-level roles rather than claiming that a work has
  no internal decision process of any kind.
- "Consensus-Risk Routing" means using measured correlated-failure risk (e.g.,
  FN correlation and false-consensus lift) to route reference-free jury accept
  decisions to grounded verification.
- "Partial" for Kohli means it studies correlated judge errors and lost
  effective votes, but does not use false-consensus risk to route factuality
  decisions.
- "Partial" for Trust or Escalate means it escalates to stronger models or
  humans, but not to reference-grounded factual verification.

## Six Papers to Read First

1. Kohli 2026, "Nine Judges, Two Effective Votes"
   - Role: strongest judge-dependence comparison.
   - Read for: effective votes, correlated judge errors, Condorcet null framing.
   - Distinguish: JuryProbe is a reference-free factuality guardrail.

2. Jung et al. 2024, "Trust or Escalate"
   - Role: closest guardrail / escalation framework.
   - Read for: selective evaluation, confidence estimation, cascaded escalation.
   - Distinguish: JuryProbe routes false-consensus risk, not uncertainty.

3. Verga et al. 2024, PoLL
   - Role: cheap judge jury setup.
   - Read for: why multiple small judges are attractive.
   - Distinguish: JuryProbe asks when small-judge agreement is unsafe.

4. Min et al. 2023, FActScore
   - Role: atomic factuality and reliable-source support.
   - Read for: factual precision and atomic facts.
   - Distinguish: JuryProbe is not a factuality metric; it routes to grounding.

5. Wei et al. 2024, SAFE / LongFact
   - Role: search-augmented grounded factuality verification.
   - Read for: grounding as scalable factuality evaluation.
   - Distinguish: JuryProbe decides when to invoke grounded verification.

6. Li et al. 2023, HaluEval
   - Role: hallucination recognition benchmark.
   - Read for: LLM difficulty recognizing hallucination and benefit of external
     knowledge/reasoning.
   - Distinguish: JuryProbe measures correlated false accepts by judge panels.

## Source Links

- MT-Bench / Chatbot Arena: https://arxiv.org/abs/2306.05685
- PandaLM: https://arxiv.org/abs/2306.05087
- JudgeLM: https://arxiv.org/abs/2310.17631
- PoLL: https://arxiv.org/abs/2404.18796
- Kohli: https://arxiv.org/abs/2605.29800
- Trust or Escalate: https://arxiv.org/abs/2407.18370
- FActScore: https://arxiv.org/abs/2305.14251
- SAFE / LongFact: https://arxiv.org/abs/2403.18802
- SelfCheckGPT: https://arxiv.org/abs/2303.08896
- HaluEval: https://arxiv.org/abs/2305.11747
- Selective Classification: https://arxiv.org/abs/1705.08500
- SelectiveNet: https://arxiv.org/abs/1901.09192
