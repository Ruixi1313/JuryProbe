# Strong Judge Slice Plan v1

Status: preregistered supplementary robustness analysis.

## Primary Question

Do stronger reference-free judges reduce false consensus risk?

## Role in the Paper

The Strong Judge Slice is a supplementary robustness analysis. It does not
affect:

- risk threshold selection
- policy definition
- routing logic
- main results

Results from the Strong Judge Slice are reported as robustness evidence only
and are not included in the primary guardrail evaluation tables.

## Experimental Scope

Number is selected as the primary capability slice because it exhibits a
substantially higher false-consensus event rate, providing greater statistical
power for detecting capacity-dependent effects.

Entity is reserved as an optional cross-family validation slice and will only be
executed if additional robustness analysis is required.

## Source Frame

Primary slice:

- Family: Number
- Dataset: `data/frozen/number_v3/number_corruption_pool_v3_n300.jsonl`
- Size: 300 clean + 300 corrupted
- Source frame: frozen Number v3

## Judge Pool

Capability slice:

- `meta-llama/llama-3.1-8b-instruct`
- `google/gemma-3-12b-it`
- `qwen/qwen3-32b`

Reference-free verdicts for `meta-llama/llama-3.1-8b-instruct` and
`google/gemma-3-12b-it` are reused from the frozen Number v3 RF cache. New model
calls are made for `qwen/qwen3-32b`; if a reused RF verdict is `parse_fail`, it
may be repaired with the same reference-free prompt and recorded in the
Strong Judge Slice cache.

Execution gate:

- The capability-slice judge list was fixed before any model calls were run.
- No execution manifest may retain `to be specified` for the capability slice.
- The finalized capability slice is written into the freeze manifest before
  evaluation begins.

## Metrics

We report:

- FN-only correlation
- false-consensus rate
- false-consensus lift
- RF majority false accept rate
- per-judge FN rate

No threshold is used to declare success or failure. All outcomes are considered
informative.

## Interpretation Rules

If false-consensus risk decreases with model capability, interpret this as
evidence for capability-dependent risk.

If false-consensus risk remains high, interpret this as evidence that stronger
reference-free judges do not eliminate the problem.

If results are mixed, report the slice as inconclusive.

## Non-use Constraints

The Strong Judge Slice must not be used to tune or revise:

- JuryProbe high-risk thresholds
- grounded-verifier policy
- RF majority / unanimous baselines
- JuryProbe-Routed logic
- main Number or Entity conclusions
