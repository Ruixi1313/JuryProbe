# Reproduction Scope

## Recomputed Outputs

The runner reruns evaluators on frozen claims and cached model verdicts. It does
not query an LLM or substitute gold labels for grounded decisions. The release
manifest identifies every shipped file by its byte count and SHA-256, records
the commands, and points to independent copies of saved expected outputs.
The source commit is context only: file hashes also identify previously
uncommitted revision scripts.

Numeric, boolean, and null fields are compared by path, including per-split
arrays, with 1e-10 relative / 1e-12 absolute floating-point tolerance. Narrative
strings are not scored. Only the three SciFact retrieval counters for calls and
tokens made during the original run are excluded; cached replay must make zero
new calls. Infinite/undefined lift retains its original recorded representation.

Runs occur in a fresh directory. Cached inputs are hashed before and after
execution. Missing required inputs fail the run. Original cache bytes and
append order are retained. Evaluators use their original final-record semantics;
superseded retry failures are not final failures. Recorded final parse failures
remain part of the evaluation and must not be described as zero.

## Metric Conventions

- Policy false/true accept uses majority except for RF Unanimity. SciFact
  standalone diagnostic clean true accept is a per-judge mean.
- Cross-family flagged counts are calibration diagnostics. Calibration and
  deployment are disjoint within a split; different seeds overlap and are
  not independent trials.
- SciFact has 190 items per class: 150/150 calibration leaves 40/40 deployment.
  Its 95/95 sensitivity changes the draw size without making repeated splits
  independent.
- Full-subset SciFact stress tests and held-out policy results are separate
  outputs. Retrieval hit/miss comparisons are descriptive associations.
- Surviving RF-unanimous false accepts are initial unanimous RF errors that
  pass grounded majority, not grounded all-three false consensus.
- Ground-All-RF-Accepts retains RF rejects; Always-Grounded verifies all items.
  The contradiction-control Always-Grounded cache contains actual judgments,
  not the earlier gold-label simulation.
- Attribute and boundary-control baselines with incomplete grounded coverage
  retain explicit minimum/maximum bounds. These are not completed empirical
  point estimates.
- The submitted zero-variance correlation and zero-over-zero lift conventions
  are retained; they do not constitute mathematical risk guarantees.

## Boundaries

JuryProbe is an empirical diagnostic. Reliable stand-down on an external
benchmark remains unresolved. CREAK and the second SciFact panel are retained
regardless of their outcome. Drift tests require a new labeled audit and do not
measure zero-shot detection or executed grounded outcomes under arbitrary drift.

Trusted-reference diagnostics do not isolate a causal mechanism. BM25 results
have a false-accept / coverage tradeoff. Utility boundaries are conditional
calculations, not measured retrieval prices or universal cost savings.
Legacy JSON fields such as `strong_mechanistic_replication` are retained for
comparison with historical outputs; they are not revised mechanism claims.
The archived policy definition retains its historical low-risk terminology;
the revised interpretation is "not flagged," not a safety certificate.

## Artifact and Licensing Scope

Final subsets, references, benchmark IDs, and recorded model outputs are included.
Full upstream corpora, all rejected construction attempts, unrelated pilots,
internal review correspondence, and every historical frozen directory are not.
Only the release manifest describes its complete offline payload. Historical
protocols can refer to research artifacts outside this release.
Completed author-audit summaries are included for Number and Entity. The
unfinished Attribute audit draft is not included, and no completed Attribute
author audit is claimed. Numerical reproduction does not validate claim labels.

Public builders document original selection, construction, prompts, and seeds.
Rebuilding from upstream sources differs from replaying cached verdicts and may
involve new API calls. Upstream claims and scientific abstracts retain their
existing terms. The project MIT license does not cover datasets or model outputs.

Build into a new directory and run the full suite and unit tests there before
publication. Publish the prepared source and its cached-input bundle together.
The builder does not update GitHub or remove existing public Git history.
