# JuryProbe

JuryProbe is a consensus-risk guardrail for reference-free factuality judge
panels. It tests when agreement among inexpensive LLM judges should be treated
as reliable evidence, and when high-risk accept decisions should be routed to
grounded verification with trusted references.

The project supports the paper:

**JuryProbe: A Consensus-Risk Guardrail for Reference-Free Factuality Judge
Panels**

## Overview

JuryProbe studies a failure mode in model-based factuality evaluation:
reference-free judge panels can unanimously accept corrupted claims when their
false-negative errors are correlated. The project measures this risk using:

- **FN-only correlation**, which measures dependence among judge failures.
- **False-consensus lift**, which measures excess unanimous false acceptance
  relative to an independent-error baseline.
- **Grounding collapse**, which tests whether the same judge panel stops
  producing false consensus when trusted references are provided.
- **JuryProbe-Routed**, a held-out guardrail policy that routes high-risk
  reference-free majority accepts to grounded verification.

The main confirmatory analyses use audited **Number** and **Entity** corruption
families. **Attribute** is retained as a replication family, and **Relation**
was excluded before main judge evaluation because audits identified unstable
construction artifacts.

## Repository Layout

```text
JuryProbe/
├── src/                    # Core judge and correlation utilities
├── scripts/                # Data construction, judging, analysis, and policy evaluation
├── docs/                   # Method notes, policy definitions, and table sources
├── audits/                 # Author audit records for corruption-family construction
├── frozen/                 # Frozen manifests and audit summaries for reported artifacts
├── results/                # Tracked summary markdown files only
├── .env.template           # Local API-key template; copy to .env
└── requirements.txt
```

Large or sensitive artifacts are intentionally not tracked:

- `.env` and other local secrets
- raw FEVER-derived datasets in `data/`
- raw model outputs and large JSON/JSONL result files in `results/`
- temporary working directories in `tmp/`
- submission PDFs/ZIPs and local reference PDFs

## Setup

Create a local environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy the environment template and add your OpenRouter key locally:

```bash
cp .env.template .env
```

The `.env` file is ignored by git. Do not commit real API keys.

## Main Workflow

The full project was run as a frozen, staged pipeline. The scripts are kept in
the repository so the construction and evaluation logic can be inspected and
rerun locally when the required data and API access are available.

### 1. Build FEVER claim pools

```bash
python scripts/build_fever_claim_pool.py --seed 42
```

This constructs fixed FEVER-supported claim pools for downstream corruption
families. Pool construction uses local, pre-specified filters; GPT-4o is not
used to select the initial pool.

### 2. Construct corruption-family datasets

Representative builders:

```bash
python scripts/build_number_from_pool.py
python scripts/build_entity_from_pool.py
python scripts/build_attribute_from_pool.py
python scripts/build_relation_from_pool.py
```

Number and Entity are the confirmatory families used for the main
consensus-risk, grounding-collapse, and guardrail-policy evaluations. Attribute
is used as replication evidence. Relation was explored but excluded from main
evaluation after audit.

### 3. Run reference-free and grounded judging

Reference-free judging evaluates each claim without a trusted reference.
Grounded verification evaluates the same claim with a trusted reference using
the same judge panel. The relevant judge wrapper is in:

```text
src/judges.py
```

The main judge panel consists of:

- Llama-3.1-8B-Instruct
- Qwen-2.5-7B-Instruct
- Gemma-3-12B-IT

### 4. Estimate consensus risk

Consensus risk is estimated from corrupted calibration items using FN-only
correlation, false-consensus lift, and a permutation-test p-value. Core
utilities are in:

```text
src/correlation.py
scripts/analyze_dataset.py
scripts/analyze_residual.py
```

### 5. Evaluate JuryProbe-Routed

The held-out policy evaluation separates risk estimation from deployment
evaluation. Risk is estimated on calibration splits, and policies are evaluated
on held-out deployment splits.

```bash
python scripts/evaluate_guardrail_multiseed.py
```

The evaluated policies include:

- Reference-Free Majority
- Reference-Free Unanimity
- Disagreement-Routed
- Random-Routed
- JuryProbe-Routed
- Always Grounded

Tracked summary tables are stored as markdown files under `results/`.

### 6. Robustness checks

Additional checks include threshold sensitivity, grounded specificity,
random-routing stability, grounded evaluation integrity, Attribute replication,
and a capability-varied judge-panel slice.

Representative scripts:

```text
scripts/analyze_guardrail_robustness.py
scripts/evaluate_low_risk_specificity.py
scripts/evaluate_strong_judge_slice.py
scripts/validate_grounded_cache.py
```

## Frozen Artifacts

The `frozen/` directory records the manifests and audit summaries used to
support the reported paper results. These files are intended as lightweight,
reviewable records of what was frozen before downstream evaluation.

The raw datasets and raw model outputs are not included in git by default
because they are large and may contain cached model responses. The tracked
markdown summaries in `results/` provide the reported aggregate tables.

## Security Notes

- Real API keys belong only in local `.env` files.
- `.env`, raw datasets, raw model outputs, and temporary workspaces are ignored.
- The repository reads `OPENROUTER_API_KEY` from the environment; keys are not
  hard-coded in source files.

## Minimal Verification

To check that the tracked Python files parse:

```bash
python3 -m py_compile src/*.py scripts/*.py
```
