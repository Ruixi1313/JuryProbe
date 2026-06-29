#!/usr/bin/env python3
"""Post-hoc robustness summaries for the frozen JuryProbe guardrail results.

This script does not call any model APIs. It reads frozen reference-free and
grounded-verifier artifacts and produces supporting analyses for the guardrail
paper:

  - threshold sensitivity for the panel-level high-risk designation
  - calibration risk statistics, including grounded specificity control
  - random-routed within-split stability
  - leave-one-judge-out risk diagnostics
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evaluate_guardrail_policies import (  # noqa: E402
    JUDGES,
    choose_split,
    family_configs,
    load_jsonl,
    load_verdicts,
    pearson,
)


JUDGE_LABELS = {
    "meta-llama/llama-3.1-8b-instruct": "Llama-3.1-8B",
    "qwen/qwen-2.5-7b-instruct": "Qwen-2.5-7B",
    "google/gemma-3-12b-it": "Gemma-3-12B",
}

DEFAULT_CORR_THRESHOLDS = [0.10, 0.15, 0.20, 0.25, 0.30]
DEFAULT_LIFT_THRESHOLDS = [1.25, 1.50, 2.00, 2.50, 3.00]


def mean(values):
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def std(values):
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return 0.0 if vals else None
    m = mean(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))


def fmt(value):
    if value is None:
        return "NA"
    if isinstance(value, int):
        return str(value)
    return f"{value:.3f}"


def load_json(path):
    return json.loads((ROOT / path).read_text())


def pair_label(judges):
    return " + ".join(JUDGE_LABELS.get(j, j) for j in judges)


def threshold_sensitivity(risk_rows, corr_thresholds, lift_thresholds):
    out = []
    grouped = defaultdict(list)
    for row in risk_rows:
        grouped[(row["source"], row["family"])].append(row["risk"])

    for (source, family), risks in sorted(grouped.items()):
        for p_required in [False, True]:
            for corr_t in corr_thresholds:
                for lift_t in lift_thresholds:
                    flags = [
                        (
                            r["fn_corr"] > corr_t
                            and r["residual_lift"] > lift_t
                            and (not p_required or r["p_value"] < 0.05)
                        )
                        for r in risks
                    ]
                    out.append({
                        "source": source,
                        "family": family,
                        "corr_threshold": corr_t,
                        "lift_threshold": lift_t,
                        "p_required": p_required,
                        "high_risk_detected_splits": sum(flags),
                        "n_splits": len(flags),
                        "high_risk_rate": sum(flags) / len(flags) if flags else None,
                    })
    return out


def summarize_risks(risk_rows):
    grouped = defaultdict(list)
    for row in risk_rows:
        grouped[(row["source"], row["family"])].append(row["risk"])

    out = []
    for (source, family), risks in sorted(grouped.items()):
        high = sum(1 for r in risks if r["high_risk"])
        out.append({
            "source": source,
            "family": family,
            "n_splits": len(risks),
            "high_risk_detected_splits": high,
            "high_risk_rate": high / len(risks) if risks else None,
            "fn_corr_mean": mean([r["fn_corr"] for r in risks]),
            "fn_corr_std": std([r["fn_corr"] for r in risks]),
            "false_consensus_rate_mean": mean([r["all3"] for r in risks]),
            "false_consensus_rate_std": std([r["all3"] for r in risks]),
            "perm_null_mean": mean([r["perm_null"] for r in risks]),
            "perm_null_std": std([r["perm_null"] for r in risks]),
            "residual_lift_mean": mean([r["residual_lift"] for r in risks]),
            "residual_lift_std": std([r["residual_lift"] for r in risks]),
            "p_value_mean": mean([r["p_value"] for r in risks]),
            "p_value_std": std([r["p_value"] for r in risks]),
        })
    return out


def collect_reference_free_risk_rows(heldout):
    rows = []
    for res in heldout["per_seed_results"]:
        rows.append({
            "source": "reference_free_calibration",
            "family": res["family"],
            "split_seed": res["split_seed"],
            "risk": res["risk_from_calibration"],
        })
    return rows


def collect_grounded_risk_rows(specificity):
    rows = []
    for fam in specificity["family_results"]:
        for res in fam["per_seed_results"]:
            rows.append({
                "source": "grounded_specificity_control",
                "family": res["family"],
                "split_seed": res["split_seed"],
                "risk": res["risk_from_grounded_calibration"],
            })
    return rows


def summarize_random_stability(baselines):
    rows = []
    for res in baselines["per_seed_results"]:
        random_row = next(
            r for r in res["deployment_policy_table"]
            if r["policy"] == "random_routed_budget_matched"
        )
        rows.append({
            "family": res["family"],
            "split_seed": res["split_seed"],
            "false_accept_rate": random_row["false_accept_rate"],
            "true_accept_rate": random_row["true_accept_rate"],
            "false_consensus_rate": random_row["false_consensus_rate"],
            "extra_verifier_items": random_row["extra_verifier_items"],
            "false_accept_rate_random_std": random_row["false_accept_rate_random_std"],
            "true_accept_rate_random_std": random_row["true_accept_rate_random_std"],
            "false_consensus_rate_random_std": random_row["false_consensus_rate_random_std"],
        })

    summary = []
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["family"]].append(row)
    for family, fam_rows in sorted(grouped.items()):
        summary.append({
            "family": family,
            "n_splits": len(fam_rows),
            "random_trials_per_split": baselines["random_trials"],
            "false_accept_rate_mean": mean([r["false_accept_rate"] for r in fam_rows]),
            "false_accept_rate_between_split_std": std([r["false_accept_rate"] for r in fam_rows]),
            "false_accept_rate_within_split_random_std_mean": mean([r["false_accept_rate_random_std"] for r in fam_rows]),
            "true_accept_rate_mean": mean([r["true_accept_rate"] for r in fam_rows]),
            "true_accept_rate_between_split_std": std([r["true_accept_rate"] for r in fam_rows]),
            "true_accept_rate_within_split_random_std_mean": mean([r["true_accept_rate_random_std"] for r in fam_rows]),
            "false_consensus_rate_mean": mean([r["false_consensus_rate"] for r in fam_rows]),
            "false_consensus_rate_between_split_std": std([r["false_consensus_rate"] for r in fam_rows]),
            "false_consensus_rate_within_split_random_std_mean": mean([r["false_consensus_rate_random_std"] for r in fam_rows]),
            "extra_verifier_items_mean": mean([r["extra_verifier_items"] for r in fam_rows]),
            "extra_verifier_items_std": std([r["extra_verifier_items"] for r in fam_rows]),
        })
    return {"per_split": rows, "summary": summary}


def subset_risk(items, rf, judges, seed, permutations):
    corrupt_idx = [i for i, it in enumerate(items) if it["is_corrupted"]]
    miss = {}
    for judge in judges:
        miss[judge] = [
            1 if (
                items[i]["is_corrupted"]
                and rf.get(items[i]["id"], {}).get(judge) == "true"
            ) else 0
            for i in range(len(items))
        ]

    corr_vals = []
    for a in range(len(judges)):
        for b in range(a + 1, len(judges)):
            ja, jb = judges[a], judges[b]
            corr_vals.append(
                pearson(
                    [miss[ja][i] for i in corrupt_idx],
                    [miss[jb][i] for i in corrupt_idx],
                )
            )
    fn_corr = mean(corr_vals) or 0.0
    obs = (
        sum(1 for i in corrupt_idx if all(miss[j][i] for j in judges)) / len(corrupt_idx)
        if corrupt_idx else 0.0
    )

    rng = random.Random(seed)
    nulls = []
    for _ in range(permutations):
        shuffled = {}
        for judge in judges:
            vals = [miss[judge][i] for i in corrupt_idx]
            rng.shuffle(vals)
            shuffled[judge] = vals
        nulls.append(
            sum(
                1 for k in range(len(corrupt_idx))
                if all(shuffled[judge][k] for judge in judges)
            ) / len(corrupt_idx)
        )
    null_mean = mean(nulls) or 0.0
    if null_mean > 0:
        lift = obs / null_mean
    elif obs == 0:
        lift = 0.0
    else:
        lift = float("inf")
    p_value = (sum(1 for v in nulls if v >= obs) + 1) / (len(nulls) + 1)
    return {
        "n_items": len(items),
        "n_corrupted": len(corrupt_idx),
        "judges": list(judges),
        "judge_label": pair_label(judges),
        "fn_corr": fn_corr,
        "false_consensus_rate": obs,
        "perm_null": null_mean,
        "residual_lift": lift,
        "p_value": p_value,
        "high_risk": fn_corr > 0.15 and lift > 1.5 and p_value < 0.05,
    }


def leave_one_judge_out(split_seeds, calib_clean, calib_corrupt, permutations):
    pairs = [
        [JUDGES[0], JUDGES[1]],
        [JUDGES[0], JUDGES[2]],
        [JUDGES[1], JUDGES[2]],
    ]
    rows = []
    for cfg in family_configs():
        items = load_jsonl(cfg["data"])
        rf = load_verdicts(cfg["rf"])
        for split_seed in split_seeds:
            calibration, _ = choose_split(items, calib_clean, calib_corrupt, split_seed)
            for pair_idx, judges in enumerate(pairs):
                risk = subset_risk(
                    calibration,
                    rf,
                    judges,
                    seed=split_seed * 1000 + pair_idx,
                    permutations=permutations,
                )
                rows.append({
                    "family": cfg["family"].lower(),
                    "split_seed": split_seed,
                    "left_out_judge": next(j for j in JUDGES if j not in judges),
                    "left_out_label": JUDGE_LABELS[next(j for j in JUDGES if j not in judges)],
                    **risk,
                })

    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["family"], row["judge_label"])].append(row)
    summary = []
    for (family, label), fam_rows in sorted(grouped.items()):
        summary.append({
            "family": family,
            "judge_pair": label,
            "n_splits": len(fam_rows),
            "high_risk_detected_splits": sum(1 for r in fam_rows if r["high_risk"]),
            "fn_corr_mean": mean([r["fn_corr"] for r in fam_rows]),
            "fn_corr_std": std([r["fn_corr"] for r in fam_rows]),
            "false_consensus_rate_mean": mean([r["false_consensus_rate"] for r in fam_rows]),
            "false_consensus_rate_std": std([r["false_consensus_rate"] for r in fam_rows]),
            "residual_lift_mean": mean([r["residual_lift"] for r in fam_rows]),
            "residual_lift_std": std([r["residual_lift"] for r in fam_rows]),
            "p_value_mean": mean([r["p_value"] for r in fam_rows]),
            "p_value_std": std([r["p_value"] for r in fam_rows]),
        })
    return {"per_split": rows, "summary": summary}


def main_threshold_rows(threshold_rows):
    rows = []
    for row in threshold_rows:
        if (
            row["source"] == "reference_free_calibration"
            and row["p_required"]
            and row["corr_threshold"] in {0.10, 0.15, 0.20, 0.25, 0.30}
            and row["lift_threshold"] in {1.25, 1.50, 2.00}
        ):
            rows.append(row)
    return rows


def markdown(output):
    lines = [
        "# JuryProbe Guardrail Robustness v1",
        "",
        "This artifact uses frozen model outputs only. No model API calls are made.",
        "",
        "Scope: threshold sensitivity, calibration-risk statistics, Random-Routed stability, and leave-one-judge-out diagnostics.",
        "",
        "## Calibration Risk Statistics",
        "",
        "| Source | Family | High-risk | FN Corr | False Consensus | Null | Lift | p-value |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in output["calibration_risk_statistics"]:
        lines.append(
            f"| {row['source']} | {row['family']} | "
            f"{row['high_risk_detected_splits']}/{row['n_splits']} | "
            f"{fmt(row['fn_corr_mean'])} ± {fmt(row['fn_corr_std'])} | "
            f"{fmt(row['false_consensus_rate_mean'])} ± {fmt(row['false_consensus_rate_std'])} | "
            f"{fmt(row['perm_null_mean'])} ± {fmt(row['perm_null_std'])} | "
            f"{fmt(row['residual_lift_mean'])} ± {fmt(row['residual_lift_std'])} | "
            f"{fmt(row['p_value_mean'])} ± {fmt(row['p_value_std'])} |"
        )

    lines += [
        "",
        "## Threshold Sensitivity",
        "",
        "Counts report high-risk detected splits out of 10 using p < 0.05.",
        "",
        "| Family | Corr Threshold | Lift 1.25 | Lift 1.50 | Lift 2.00 |",
        "|---|---:|---:|---:|---:|",
    ]
    compact = main_threshold_rows(output["threshold_sensitivity"])
    for family in sorted({r["family"] for r in compact}):
        for corr_t in DEFAULT_CORR_THRESHOLDS:
            cells = []
            for lift_t in [1.25, 1.50, 2.00]:
                match = next(
                    r for r in compact
                    if r["family"] == family
                    and r["corr_threshold"] == corr_t
                    and r["lift_threshold"] == lift_t
                )
                cells.append(f"{match['high_risk_detected_splits']}/{match['n_splits']}")
            lines.append(f"| {family} | {corr_t:.2f} | {' | '.join(cells)} |")

    lines += [
        "",
        "## Random-Routed Stability",
        "",
        "| Family | Trials/Split | False Accept | Within-split Random SD | True Accept | False Consensus | Verifier Items |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in output["random_routed_stability"]["summary"]:
        lines.append(
            f"| {row['family']} | {row['random_trials_per_split']} | "
            f"{fmt(row['false_accept_rate_mean'])} ± {fmt(row['false_accept_rate_between_split_std'])} | "
            f"{fmt(row['false_accept_rate_within_split_random_std_mean'])} | "
            f"{fmt(row['true_accept_rate_mean'])} ± {fmt(row['true_accept_rate_between_split_std'])} | "
            f"{fmt(row['false_consensus_rate_mean'])} ± {fmt(row['false_consensus_rate_between_split_std'])} | "
            f"{fmt(row['extra_verifier_items_mean'])} ± {fmt(row['extra_verifier_items_std'])} |"
        )

    lines += [
        "",
        "## Leave-One-Judge-Out",
        "",
        "Each row uses the held-out calibration split and recomputes FN correlation and false-consensus lift for a two-judge subpanel.",
        "",
        "| Family | Judge Pair | High-risk | FN Corr | False Consensus | Lift | p-value |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in output["leave_one_judge_out"]["summary"]:
        lines.append(
            f"| {row['family']} | {row['judge_pair']} | "
            f"{row['high_risk_detected_splits']}/{row['n_splits']} | "
            f"{fmt(row['fn_corr_mean'])} ± {fmt(row['fn_corr_std'])} | "
            f"{fmt(row['false_consensus_rate_mean'])} ± {fmt(row['false_consensus_rate_std'])} | "
            f"{fmt(row['residual_lift_mean'])} ± {fmt(row['residual_lift_std'])} | "
            f"{fmt(row['p_value_mean'])} ± {fmt(row['p_value_std'])} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_freeze_manifest(output, out_path, md_path):
    manifest = {
        "artifact_type": "robustness_evaluation",
        "stage": "evaluation",
        "version": "guardrail_robustness_v1",
        "created": output["created"],
        "description": "Frozen no-API robustness analyses for JuryProbe guardrail evaluation.",
        "inputs": output["inputs"],
        "outputs": [
            str(out_path.relative_to(ROOT)),
            str(md_path.relative_to(ROOT)),
        ],
        "oracle_used": False,
        "gold_fallback_used": False,
        "model_api_calls_made": 0,
        "affects_main_policy": False,
        "affects_risk_thresholds": False,
        "affects_routing_logic": False,
    }
    frozen_dir = ROOT / "frozen/guardrail_robustness_v1"
    frozen_dir.mkdir(parents=True, exist_ok=True)
    (frozen_dir / "FREEZE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    (frozen_dir / "README.md").write_text(
        "# Guardrail Robustness v1\n\n"
        "Frozen no-API robustness analyses for the JuryProbe guardrail paper.\n\n"
        "Included analyses:\n\n"
        "- threshold sensitivity for high-risk designation\n"
        "- calibration-risk statistics, including grounded specificity control\n"
        "- Random-Routed stability over repeated random routing trials\n"
        "- leave-one-judge-out two-judge subpanel diagnostics\n\n"
        "This artifact does not change the main policy definition, risk thresholds, routing logic, or primary guardrail results.\n\n"
        f"Summary: `{out_path.relative_to(ROOT)}`\n"
        f"Markdown: `{md_path.relative_to(ROOT)}`\n",
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="1,2,3,4,5,6,7,8,9,10")
    ap.add_argument("--calib-clean", type=int, default=150)
    ap.add_argument("--calib-corrupt", type=int, default=150)
    ap.add_argument("--permutations", type=int, default=3000)
    ap.add_argument("--out", default="results/frozen/guardrail_robustness_v1/summary.json")
    ap.add_argument("--md-out", default="results/frozen/guardrail_robustness_v1/summary.md")
    args = ap.parse_args()

    split_seeds = [int(s.strip()) for s in args.seeds.split(",") if s.strip()]
    heldout = load_json("results/frozen/guardrail_heldout_multiseed/summary.json")
    baselines = load_json("results/frozen/guardrail_baselines_v1/summary.json")
    specificity = load_json("results/frozen/low_risk_specificity_v1/summary.json")

    risk_rows = collect_reference_free_risk_rows(heldout) + collect_grounded_risk_rows(specificity)
    output = {
        "artifact_type": "robustness_evaluation",
        "stage": "evaluation",
        "version": "guardrail_robustness_v1",
        "created": "2026-06-10",
        "mode": "no_api_cached_analysis",
        "model_api_calls_made": 0,
        "oracle_used": False,
        "gold_fallback_used": False,
        "inputs": [
            "results/frozen/guardrail_heldout_multiseed/summary.json",
            "results/frozen/guardrail_baselines_v1/summary.json",
            "results/frozen/low_risk_specificity_v1/summary.json",
            "results/frozen/number_v3/number_corruption_pool_v3_n300_rf.jsonl",
            "results/frozen/v4/entity_corruption_pool_v4_n300_rf.jsonl",
        ],
        "seeds": split_seeds,
        "calibration": {"n_clean": args.calib_clean, "n_corrupt": args.calib_corrupt},
        "threshold_grid": {
            "corr_thresholds": DEFAULT_CORR_THRESHOLDS,
            "lift_thresholds": DEFAULT_LIFT_THRESHOLDS,
            "p_required_options": [False, True],
        },
        "calibration_risk_statistics": summarize_risks(risk_rows),
        "threshold_sensitivity": threshold_sensitivity(
            risk_rows,
            DEFAULT_CORR_THRESHOLDS,
            DEFAULT_LIFT_THRESHOLDS,
        ),
        "random_routed_stability": summarize_random_stability(baselines),
        "leave_one_judge_out": leave_one_judge_out(
            split_seeds,
            args.calib_clean,
            args.calib_corrupt,
            args.permutations,
        ),
    }

    out_path = ROOT / args.out
    md_path = ROOT / args.md_out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    md_path.write_text(markdown(output))
    write_freeze_manifest(output, out_path, md_path)
    print(json.dumps({
        "json": str(out_path.relative_to(ROOT)),
        "markdown": str(md_path.relative_to(ROOT)),
        "freeze_manifest": "frozen/guardrail_robustness_v1/FREEZE_MANIFEST.json",
    }, indent=2))
    print()
    print(markdown(output))


if __name__ == "__main__":
    main()
