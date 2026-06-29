# JuryProbe

JuryProbe tests whether LLM judges behave like independent voters. We measure
inter-judge error correlation, false consensus, and the effect of sequential
cascading on correlation.

**Thesis (Day 1):** *Agreement is not independence.* If LLM judges' errors are
correlated, classical jury-theorem guarantees (Condorcet, wisdom of crowds)
do not apply, and the marginal value of additional judges drops faster than
independence theory predicts.

## Core Contributions (target paper)

1. First systematic measurement of inter-judge error correlation across
   multiple LLM families and task types.
2. Quantification of correlation growth across cascade depth in sequential
   vs. independent designs.
3. A corrected expected-accuracy formula for LLM-as-Judge ensembles that
   accounts for empirical error correlation.

## Project Layout

```
JuryProbe/
├── requirements.txt
├── .env.template
├── .gitignore
├── README.md
├── src/
│   ├── judges.py            # OpenRouter judge wrappers
│   ├── correlation.py       # accuracy / error vectors / Pearson / false consensus
│   └── io_utils.py          # jsonl IO and raw-call disk cache
├── scripts/
│   └── day1_sanity.py       # 30 pairs × 3 judges × {independent, sequential}
├── data/
│   └── sample_pairs_30.jsonl   # demo benchmark (gitignored)
└── results/
    ├── raw_outputs.jsonl    # every judge call cached for reproducibility
    ├── error_vectors.csv    # per-item binary error vector for each judge
    └── summary.json         # standardized run summary
```

## Artifact Manifests

Pool manifests, build manifests, and evaluation manifests are tracked separately.

Pool manifests record the source frame, pool sizes, attrition, strata counts,
and fixed seed. Build manifests record accepted/rejected examples, reject
reasons, construction rules, and post-filter/audit versions. Evaluation
manifests record grounded verifier details, raw/retried/final `parse_fail`
counts, and whether oracle or gold-label fallback was used.

```text
Construction
├── pool_freeze
└── build_freeze

Evaluation
├── evaluation
└── evaluation_cache_validation
```

## Setup

```bash
cd path/to/JuryProbe
cp .env.template .env          # then add OPENROUTER_API_KEY
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Day 1 Sanity Check

```bash
python scripts/day1_sanity.py
```

Pass criteria (all must hold on the independent pass):

- mean accuracy > 60%
- mean error correlation > 0.05
- any pair correlation > 0.10
- false consensus rate > 5%
- sequential correlation > independent correlation (bonus)

Expected runtime: ~3-5 minutes. Expected cost: ~$0.50.

Reruns are free: every judge call is written to `results/raw_outputs.jsonl`
and re-used on subsequent invocations.

## summary.json Schema

```json
{
  "n_examples": 30,
  "judges": ["model_a", "model_b", "model_c"],
  "independent": {
    "accuracy_by_judge": {"...": 0.0},
    "error_corr_labels": ["..."],
    "error_corr_matrix": [[1.0]],
    "avg_pairwise_correlation": 0.0,
    "max_pairwise_correlation": 0.0,
    "false_consensus_rate": 0.0
  },
  "sequential": {
    "accuracy_by_stage": {"...": 0.0},
    "error_corr_labels": ["..."],
    "error_corr_matrix": [[1.0]],
    "avg_pairwise_correlation": 0.0,
    "false_consensus_rate": 0.0
  },
  "pass_criteria": {"...": true},
  "pass": true
}
```

## Pivot Plan

If correlation stays low across larger benchmarks, the thesis is unstable.
Re-use the same `raw_outputs.jsonl` for a calibration study instead of
restarting from zero.

Working title for the pivot: *LLM Judge Calibration under Task Difficulty.*
