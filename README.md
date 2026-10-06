# JuryProbe

An empirical consensus-risk diagnostic with calibration-based routing for
reference-free factuality judge panels.

Paper: [JuryProbe: An Empirical Consensus-Risk Diagnostic for Routing
Reference-Free Factuality Judge Panels to Grounded Verification](https://arxiv.org/abs/2608.20607).

JuryProbe measures dependence among false-negative judge errors and excess
unanimous false acceptance. Its frozen rule activates accept-conditioned
grounding when FN-only correlation > 0.15, false-consensus lift > 1.5, and
permutation p < 0.05. In flagged settings, JuryProbe-Routed and
Ground-All-RF-Accepts are identical: grounding supplies the policy improvement;
the diagnostic determines whether that policy is activated.

Number was the threshold-development setting. Entity and subsequent families
were evaluated with the frozen rule. A not-flagged result is not a safety
certificate, and reliable stand-down on an external benchmark remains unresolved.
Grounded results are trusted-reference best-case diagnostics or explicitly
identified retrieved-reference stress tests.

## Offline Reproduction

Use Python 3.10 or later. Cached reproduction uses only the Python standard
library and requires no API key, model download, or network connection.
The prepared release includes `reproducibility/cached_inputs.tar.gz` and its
SHA-256 manifest. If these are absent from a checkout, it is not the complete
reproduction release; the maintainer instructions below create them.

```bash
git clone https://github.com/Ruixi1313/JuryProbe.git
cd JuryProbe
python3 scripts/reproduce.py --suite core --output-dir /tmp/juryprobe-core-run
python3 scripts/reproduce.py --suite all --output-dir /tmp/juryprobe-all-run
```

Choose a new output directory each time. The runner verifies source and artifact
hashes, copies exact inputs into an isolated workspace, disables network access,
recomputes results, and compares all recorded numeric, boolean, and null fields
against saved reference outputs. Missing inputs, numerical mismatches, evaluator
failures, or changes to cached inputs result in a nonzero exit status. Logs,
regenerated tables, and `reproduction_report.json` go to the isolated workspace.
This verifies calculations from recorded model verdicts, not that future model
API calls will return identical responses. Original-run API/token counters are
excluded from numerical comparison as documented below.

The core suite covers:

- Number, Entity, and Attribute reference-free and grounded diagnostics;
- ten-split routing and disagreement/random baselines;
- Ground-All-RF-Accepts and the reference-free contradiction control;
- seven-family diagnostics and SciFact 95/95 calibration sensitivity;
- SciFact rationale/full-abstract/BM25 and held-out policy results;
- conditional utility calculations using measured policy outcomes.

The full suite additionally covers CREAK, grouped SciFact second-panel folds,
distribution shift and complete-case sensitivity, leave-one-family-out
calibration, threshold sensitivity, and the earlier Number capability slice.
Boundary and negative outcomes are included.

```bash
python3 scripts/reproduce.py --verify-only
python3 -m unittest discover -s tests -v
```

See [scope and conventions](docs/reproducibility.md) for aggregation definitions,
missing-verdict handling, and limitations.

## Fresh Data and Model Calls

Data construction and fresh judging are separate workflows: upstream data and
provider models can change, and new judging incurs API costs. Install
`requirements.txt` for optional `certifi` support and configure
`OPENROUTER_API_KEY` locally. Never commit an actual key.

The original panel is Llama-3.1-8B-Instruct, Qwen-2.5-7B-Instruct, and
Gemma-3-12B-IT. Prompts, model identifiers, decoding settings, seeds, and cache
namespaces are in the scripts and protocols. SciFact retrieval uses frozen
claim-only BM25 references; cached reproduction recomputes recall and verifier
outcomes from these references. Rebuilding the index separately requires the
upstream SciFact corpus.

## Maintainer Packaging

From the full research checkout containing the original data and caches:

```bash
python3 scripts/build_public_release.py --output-dir /tmp/juryprobe-release
python3 /tmp/juryprobe-release/scripts/reproduce.py --suite all
```

The builder uses explicit lists in `scripts/reproduction_config.py`, scans
selected content for common credential formats, preserves input bytes, and
generates a deterministic source archive beside the release directory.

The release contains only reproduction code, methods documentation, selected
audit/protocol records, tests, licensing/citation metadata, and the frozen-input
bundle. Each included path is listed in the release manifest.

Packaging does not push commits, publish releases, or rewrite Git history.
Publish only this allowlisted release, not the full research checkout. Files
removed from a current tree may remain visible in existing Git history.

## License

Original code and associated documentation are covered by the [MIT License](LICENSE),
copyright (c) 2026 Tianxin Zhou and Ruixi Lin. The paper, datasets, model outputs,
and third-party materials are excluded from that grant. FEVER-derived excerpts
retain their [upstream terms](https://fever.ai/download/fever/license.html).
SciFact and CREAK materials retain their upstream terms; bundling does not
relicense them under MIT. The optional `certifi` dependency retains its own license.
The legacy `scripts/build_fever_number_seeds.py` is excluded from the release
and MIT grant pending upstream provenance clarification.

## Citation

If you use JuryProbe in research, please cite the paper:

```bibtex
@article{zhou2026juryprobe,
  title = {JuryProbe: An Empirical Consensus-Risk Diagnostic for Routing Reference-Free Factuality Judge Panels to Grounded Verification},
  author = {Zhou, Tianxin and Lin, Ruixi},
  journal = {Transactions on Machine Learning Research},
  year = {2026},
  eprint = {2608.20607},
  archivePrefix = {arXiv},
  primaryClass = {cs.CL},
  doi = {10.48550/arXiv.2608.20607},
  url = {https://arxiv.org/abs/2608.20607}
}
```

Machine-readable citation metadata is available in [CITATION.cff](CITATION.cff).
Citation is a scholarly request, not an additional condition of the MIT License.
