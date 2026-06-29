#!/usr/bin/env python3
"""Day 1 sanity check for JuryProbe.

Verifies whether LLM judges behave like independent voters.

Reads pairwise items from `data/sample_pairs_30.jsonl`. Runs each item through
3 judges in two modes: independent (each judge sees only the pair) and
sequential (judges 2 and 3 see prior verdicts). Every raw judge call is
cached in `results/raw_outputs.jsonl`, so reruns are free.

Outputs:
  results/raw_outputs.jsonl   - one record per judge call
  results/error_vectors.csv   - per-item binary error vector for each judge
  results/summary.json        - the standardized summary schema
"""
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ENV_FILE = ROOT / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from src.judges import judge_pair
from src.correlation import (
    per_judge_accuracy, pairwise_error_correlation, error_vectors,
    false_consensus_rate,
)
from src.io_utils import load_jsonl, RawCache, write_jsonl

DATA = ROOT / "data" / "hidden_corruption_24.jsonl"
OUT_DIR = ROOT / "results"
RAW_CACHE = OUT_DIR / "raw_outputs.jsonl"
ERROR_CSV = OUT_DIR / "error_vectors.csv"
SUMMARY_JSON = OUT_DIR / "summary.json"

JUDGES = [
    "meta-llama/llama-3.1-8b-instruct",
    "qwen/qwen-2.5-7b-instruct",
    "google/gemma-3-12b-it",
]


def collect_verdicts(items, mode: str, cache: RawCache):
    """For each item, query each judge in `mode` ('independent'|'sequential')."""
    verdicts = {j: [] for j in JUDGES}
    for item in items:
        prior = []
        for j in JUDGES:
            prior_for_call = prior if mode == "sequential" else None
            cached = cache.get(j, item["id"], mode, prior_for_call)
            if cached is None:
                v = judge_pair(j, item["prompt"],
                               item["candidate_a"], item["candidate_b"],
                               prior_verdicts=prior_for_call)
                rec = {
                    "judge": j, "item_id": item["id"], "mode": mode,
                    "prior": prior_for_call,
                    "verdict": v.verdict, "raw_response": v.raw_response,
                    "prompt_tokens": v.prompt_tokens,
                    "completion_tokens": v.completion_tokens,
                }
                cache.put(rec)
                verdict = v.verdict
            else:
                verdict = cached["verdict"]
            verdicts[j].append(verdict)
            prior.append(verdict)
    return verdicts


def corr_matrix(verdicts, ground_truth):
    """Return labels + dense matrix for serialization."""
    labels = list(verdicts.keys())
    corrs = pairwise_error_correlation(verdicts, ground_truth)
    n = len(labels)
    m = [[0.0] * n for _ in range(n)]
    for i in range(n):
        m[i][i] = 1.0
    for (a, b), v in corrs.items():
        i, j = labels.index(a), labels.index(b)
        m[i][j] = v
        m[j][i] = v
    return labels, m


def write_error_vectors(verdicts_ind, verdicts_seq, ground_truth, path):
    errs_ind = error_vectors(verdicts_ind, ground_truth)
    errs_seq = error_vectors(verdicts_seq, ground_truth)
    fields = ["item_idx"]
    for j in JUDGES:
        fields.append(f"{j}__ind")
    for j in JUDGES:
        fields.append(f"{j}__seq")
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(fields)
        for i in range(len(ground_truth)):
            row = [i]
            for j in JUDGES:
                row.append(errs_ind[j][i])
            for j in JUDGES:
                row.append(errs_seq[j][i])
            w.writerow(row)


def main():
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY not set. Copy .env.template to .env "
              "and fill it in.", file=sys.stderr)
        sys.exit(1)

    OUT_DIR.mkdir(exist_ok=True)
    items = load_jsonl(DATA)
    ground_truth = [it["gold"] for it in items]
    cache = RawCache(RAW_CACHE)
    print(f"Loaded {len(items)} items; cache has {len(cache)} prior calls.")

    print("\n--- Independent cascade ---")
    v_ind = collect_verdicts(items, "independent", cache)
    accs_ind = per_judge_accuracy(v_ind, ground_truth)
    corrs_ind = pairwise_error_correlation(v_ind, ground_truth)
    fc_ind = false_consensus_rate(v_ind, ground_truth)
    for j, a in accs_ind.items():
        print(f"  {j:<50}  acc={a:.3f}")
    avg_corr_ind = sum(corrs_ind.values()) / len(corrs_ind) if corrs_ind else 0.0
    max_corr_ind = max(corrs_ind.values()) if corrs_ind else 0.0
    print(f"  avg pairwise error corr: {avg_corr_ind:.3f}   "
          f"max pair corr: {max_corr_ind:.3f}   "
          f"false consensus rate: {fc_ind:.3f}")

    print("\n--- Sequential cascade ---")
    v_seq = collect_verdicts(items, "sequential", cache)
    accs_seq = per_judge_accuracy(v_seq, ground_truth)
    corrs_seq = pairwise_error_correlation(v_seq, ground_truth)
    fc_seq = false_consensus_rate(v_seq, ground_truth)
    for j, a in accs_seq.items():
        print(f"  {j:<50}  acc={a:.3f}")
    avg_corr_seq = sum(corrs_seq.values()) / len(corrs_seq) if corrs_seq else 0.0
    print(f"  avg pairwise error corr: {avg_corr_seq:.3f}   "
          f"false consensus rate: {fc_seq:.3f}")

    write_error_vectors(v_ind, v_seq, ground_truth, ERROR_CSV)

    errs_ind = error_vectors(v_ind, ground_truth)
    total_error_count = sum(sum(vec) for vec in errs_ind.values())
    error_rates = {j: 1.0 - accs_ind[j] for j in JUDGES}
    judges_in_band = [j for j, r in error_rates.items() if 0.10 <= r <= 0.40]

    n_calls = len(JUDGES) * len(items)
    n_parse_fail = sum(1 for j in JUDGES for v in v_ind[j] if v == "parse_fail")

    ind_labels, ind_matrix = corr_matrix(v_ind, ground_truth)
    seq_labels, seq_matrix = corr_matrix(v_seq, ground_truth)

    # Layer 1: infrastructure - did the pipeline return valid verdicts?
    infra_pass = n_parse_fail == 0

    # Layer 2: signal - is there a measurable, non-trivial error structure?
    sig_total_errors = total_error_count >= 8
    sig_error_band = len(judges_in_band) >= 2
    sig_corr = avg_corr_ind > 0.05
    sig_fc = fc_ind > 0.05
    signal_pass = sig_total_errors and sig_error_band and sig_corr and sig_fc

    pass_seq = avg_corr_seq > avg_corr_ind

    summary = {
        "n_examples": len(items),
        "judges": JUDGES,
        "independent": {
            "accuracy_by_judge": accs_ind,
            "error_rate_by_judge": error_rates,
            "total_error_count": total_error_count,
            "judges_in_10_40_band": judges_in_band,
            "error_corr_labels": ind_labels,
            "error_corr_matrix": ind_matrix,
            "avg_pairwise_correlation": avg_corr_ind,
            "max_pairwise_correlation": max_corr_ind,
            "false_consensus_rate": fc_ind,
        },
        "sequential": {
            "accuracy_by_stage": accs_seq,
            "error_corr_labels": seq_labels,
            "error_corr_matrix": seq_matrix,
            "avg_pairwise_correlation": avg_corr_seq,
            "false_consensus_rate": fc_seq,
        },
        "infrastructure_pass": {
            "no_parse_failures": infra_pass,
            "parse_fail_calls": n_parse_fail,
            "total_calls": n_calls,
            "pass": infra_pass,
        },
        "signal_pass": {
            "total_error_count_ge_8": sig_total_errors,
            "two_judges_error_rate_10_40": sig_error_band,
            "mean_error_corr_gt_0_05": sig_corr,
            "false_consensus_gt_5pct": sig_fc,
            "pass": signal_pass,
        },
        "sequential_amplification": {
            "sequential_corr_gt_independent": pass_seq,
            "independent_avg_corr": avg_corr_ind,
            "sequential_avg_corr": avg_corr_seq,
        },
        "pass": infra_pass and signal_pass,
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2))

    def mark(ok):
        return "PASS" if ok else "FAIL"

    print("\n" + "=" * 64)
    print("Layer 1 - Infrastructure pass")
    print("=" * 64)
    print(f"  no parse failures:                          "
          f"{mark(infra_pass)}  ({n_parse_fail}/{n_calls} failed)")

    print("\n" + "=" * 64)
    print("Layer 2 - Signal pass")
    print("=" * 64)
    short_band = ", ".join(j.split("/")[-1] for j in judges_in_band) or "-"
    print(f"  total error count >= 8:                     "
          f"{mark(sig_total_errors)}  ({total_error_count})")
    print(f"  >=2 judges with error rate in [10%,40%]:    "
          f"{mark(sig_error_band)}  ({len(judges_in_band)}: {short_band})")
    print(f"  mean error correlation > 0.05:              "
          f"{mark(sig_corr)}  ({avg_corr_ind:.3f})")
    print(f"  false consensus rate > 5%:                  "
          f"{mark(sig_fc)}  ({fc_ind:.3f})")

    print("\n" + "=" * 64)
    print("Bonus - Sequential amplification (ICTAI signal)")
    print("=" * 64)
    print(f"  sequential corr > independent corr:         "
          f"{mark(pass_seq)}  ({avg_corr_seq:.3f} vs {avg_corr_ind:.3f})")

    print(f"\ninfrastructure_pass = {infra_pass}")
    print(f"signal_pass         = {signal_pass}")
    print(f"\nWrote {SUMMARY_JSON.relative_to(ROOT)}")
    print(f"Wrote {ERROR_CSV.relative_to(ROOT)}")
    print(f"Cached calls: {len(cache)} -> {RAW_CACHE.relative_to(ROOT)}")

    if infra_pass and not signal_pass:
        print("\nInfra OK but no signal: judges too strong or items not hard "
              "enough - NOT evidence the project is unviable.")
        print("Next step: swap in JudgeBench / HaluEval / TruthfulQA-style "
              "items where judges actually err.")


if __name__ == "__main__":
    main()
