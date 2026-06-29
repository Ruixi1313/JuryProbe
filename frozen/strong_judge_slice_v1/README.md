# Strong Judge Slice v1

Status: complete supplementary robustness analysis.

Artifact type: `robustness_evaluation`. Stage: `evaluation`. Pool manifests, build
manifests, and evaluation manifests are tracked separately.

Primary question:

Do stronger reference-free judges reduce false consensus risk?

Scope:

- Primary family: Number
- Dataset: `data/frozen/number_v3/number_corruption_pool_v3_n300.jsonl`
- Size: 300 clean + 300 corrupted
- Entity is reserved as optional cross-family validation if additional
  robustness analysis is required.

Non-use constraints:

- does not affect risk threshold selection
- does not affect policy definition
- does not affect routing logic
- does not affect main results
- reported as robustness evidence only; not included in primary guardrail
  evaluation tables

Judge pool:

- Capability slice: `meta-llama/llama-3.1-8b-instruct`,
  `google/gemma-3-12b-it`, `qwen/qwen3-32b`
- Reference-free verdicts for `meta-llama/llama-3.1-8b-instruct` and
  `google/gemma-3-12b-it` are reused from the frozen Number v3 RF cache. New
  model calls are made for `qwen/qwen3-32b`; reused-cache `parse_fail` verdicts
  may be repaired with the same reference-free prompt and recorded in the
  Strong Judge Slice cache.
- Execution gate: the capability-slice judge list was fixed in the freeze
  manifest before any model calls were run; no execution manifest may retain
  `to be specified`.

Metrics:

- FN-only correlation
- false-consensus rate
- false-consensus lift
- RF majority false accept rate
- per-judge FN rate

No threshold is used to declare success or failure. All outcomes are considered
informative.

Plan document:

- `docs/strong_judge_slice_plan.md`

Frozen outputs:

- `results/frozen/strong_judge_slice_v1/summary.json`
- `results/frozen/strong_judge_slice_v1/summary.md`
- `results/frozen/strong_judge_slice_v1/number_v3_capability_rf.jsonl`

Result summary:

- FN-only correlation: 0.252
- False-consensus rate: 0.137
- False-consensus lift: 2.169
- p-value: 0.0003
- RF majority false accept: 0.387
- RF majority true accept: 0.647
- Final parse_fail: 0 for all capability-slice judges

Note: qwen3 preliminary attempts could enter reasoning-only mode under the
default prompt. The final cache repairs those attempts with `/no_think`; the
final evaluated cache has 600 valid verdicts and 0 final `parse_fail` for
`qwen/qwen3-32b`.
