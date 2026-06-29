#!/usr/bin/env python3
"""Run held-out JuryProbe guardrail evaluation over multiple split seeds."""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evaluate_guardrail_policies import evaluate_config, family_configs


def mean(values):
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def std(values):
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return 0.0 if vals else None
    m = mean(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))


def aggregate(results):
    grouped = defaultdict(list)
    risk_grouped = defaultdict(list)
    for res in results:
        fam = res["family"]
        risk_grouped[fam].append(res["risk_from_calibration"])
        for row in res["deployment_policy_table"]:
            grouped[(fam, row["policy"])].append(row)

    policy_summary = []
    for (fam, policy), rows in sorted(grouped.items()):
        metrics = {}
        for key in [
            "false_accept_rate",
            "true_accept_rate",
            "false_consensus_rate",
            "extra_verifier_items",
            "extra_verifier_calls",
            "model_calls",
        ]:
            vals = [row[key] for row in rows]
            metrics[f"{key}_mean"] = mean(vals)
            metrics[f"{key}_std"] = std(vals)
        policy_summary.append({
            "family": fam,
            "policy": policy,
            "n_seeds": len(rows),
            **metrics,
            "all_complete": all(row["status"] == "complete" for row in rows),
            "missing_grounded_items_total": sum(row["missing_grounded_items"] for row in rows),
        })

    risk_summary = []
    for fam, risks in sorted(risk_grouped.items()):
        high_risk_count = sum(1 for r in risks if r["high_risk"])
        risk_summary.append({
            "family": fam,
            "n_seeds": len(risks),
            "high_risk_detected_splits": high_risk_count,
            "n_splits": len(risks),
            "high_risk_rate": high_risk_count / len(risks),
            "fn_corr_mean": mean([r["fn_corr"] for r in risks]),
            "fn_corr_std": std([r["fn_corr"] for r in risks]),
            "residual_lift_mean": mean([r["residual_lift"] for r in risks]),
            "residual_lift_std": std([r["residual_lift"] for r in risks]),
            "p_value_mean": mean([r["p_value"] for r in risks]),
            "p_value_std": std([r["p_value"] for r in risks]),
        })
    return {"risk_summary": risk_summary, "policy_summary": policy_summary}


def fmt(value):
    return "NA" if value is None else f"{value:.3f}"


def markdown_tables(agg):
    lines = [
        "# JuryProbe Held-out Multi-seed Guardrail Evaluation",
        "",
        "Policy definition: `docs/guardrail_policy_definition_v1.md`.",
        "",
        "All results use held-out evaluation: risk is estimated on calibration and policies are evaluated on deployment.",
        "",
        "## Calibration Risk Stability",
        "",
        "| Family | Seeds | High-risk Detected | High-risk Rate | FN Corr | Residual Lift | p-value |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in agg["risk_summary"]:
        lines.append(
            f"| {row['family']} | {row['n_seeds']} | "
            f"{row['high_risk_detected_splits']}/{row['n_splits']} | "
            f"{row['high_risk_rate']:.3f} | "
            f"{fmt(row['fn_corr_mean'])} ± {fmt(row['fn_corr_std'])} | "
            f"{fmt(row['residual_lift_mean'])} ± {fmt(row['residual_lift_std'])} | "
            f"{fmt(row['p_value_mean'])} ± {fmt(row['p_value_std'])} |"
        )

    lines += [
        "",
        "## Deployment Policy Results",
        "",
        "| Family | Policy | False Accept | True Accept | False Consensus | Extra Verifier Items | Model Calls |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in agg["policy_summary"]:
        lines.append(
            f"| {row['family']} | {row['policy']} | "
            f"{fmt(row['false_accept_rate_mean'])} ± {fmt(row['false_accept_rate_std'])} | "
            f"{fmt(row['true_accept_rate_mean'])} ± {fmt(row['true_accept_rate_std'])} | "
            f"{fmt(row['false_consensus_rate_mean'])} ± {fmt(row['false_consensus_rate_std'])} | "
            f"{fmt(row['extra_verifier_items_mean'])} ± {fmt(row['extra_verifier_items_std'])} | "
            f"{fmt(row['model_calls_mean'])} ± {fmt(row['model_calls_std'])} |"
        )
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="1,2,3,4,5,6,7,8,9,10")
    ap.add_argument("--calib-clean", type=int, default=150)
    ap.add_argument("--calib-corrupt", type=int, default=150)
    ap.add_argument("--permutations", type=int, default=3000)
    ap.add_argument("--out", default="results/guardrail_heldout_multiseed/summary.json")
    ap.add_argument("--md-out", default="results/guardrail_heldout_multiseed/summary.md")
    args = ap.parse_args()

    seeds = [int(s.strip()) for s in args.seeds.split(",") if s.strip()]
    all_results = []
    for seed in seeds:
        run_args = argparse.Namespace(
            seed=seed,
            calib_clean=args.calib_clean,
            calib_corrupt=args.calib_corrupt,
            permutations=args.permutations,
            run_grounded=False,
        )
        for cfg in family_configs():
            print(f"[seed {seed}] {cfg['family']}", flush=True)
            all_results.append(evaluate_config(cfg, "heldout", run_args))

    agg = aggregate(all_results)
    output = {
        "policy_definition": "docs/guardrail_policy_definition_v1.md",
        "mode": "heldout_multiseed",
        "seeds": seeds,
        "calibration": {"n_clean": args.calib_clean, "n_corrupt": args.calib_corrupt},
        "oracle_used": False,
        "gold_fallback_used": False,
        "risk_estimated_on": "calibration",
        "policy_evaluated_on": "deployment",
        "per_seed_results": all_results,
        **agg,
    }

    out = ROOT / args.out
    md = ROOT / args.md_out
    out.parent.mkdir(parents=True, exist_ok=True)
    md.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    md.write_text(markdown_tables(agg))
    print(json.dumps({"json": str(out.relative_to(ROOT)), "markdown": str(md.relative_to(ROOT))}, indent=2))
    print()
    print(markdown_tables(agg))


if __name__ == "__main__":
    main()
