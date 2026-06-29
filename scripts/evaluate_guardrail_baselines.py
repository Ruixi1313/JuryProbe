#!/usr/bin/env python3
"""Evaluate guardrail baselines over held-out splits.

Policies:
  - rf_majority
  - rf_unanimous
  - disagreement_routed
  - random_routed_budget_matched
  - juryprobe_routed
  - always_grounded

Random-routed samples the same number of deployment items as JuryProbe-Routed
routes. Sampling from RF-accept items with the same budget is degenerate in the
current high-risk setting because JuryProbe-Routed routes all RF-majority-accept
items.
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

from scripts.evaluate_guardrail_policies import (
    JUDGES,
    GroundedStore,
    choose_split,
    family_configs,
    load_jsonl,
    load_verdicts,
    majority_accept,
    risk_assessment,
    unanimous_true,
)


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
    return "NA" if value is None else f"{value:.3f}"


def rf_verdicts(rf, item):
    return [rf.get(item["id"], {}).get(j, "parse_fail") for j in JUDGES]


def rf_majority_accept(rf, item):
    return majority_accept(rf_verdicts(rf, item))


def rf_unanimous_true(rf, item):
    return unanimous_true(rf_verdicts(rf, item))


def rf_disagrees(rf, item):
    verdicts = rf_verdicts(rf, item)
    valid = [v for v in verdicts if v in {"true", "false"}]
    return len(valid) != len(JUDGES) or len(set(valid)) > 1


def grounded_accept(store, item):
    verdicts = store.item_verdicts(item, run_grounded=False)
    if verdicts is None:
        return None
    return majority_accept(verdicts)


def compute_metrics(items, decisions, escalated):
    missing = [it["id"] for it in items if decisions[it["id"]] is None]
    extra = sum(1 for it in items if escalated[it["id"]])
    if missing:
        return {
            "status": "missing_grounded",
            "missing_grounded_items": len(set(missing)),
            "false_accept_rate": None,
            "true_accept_rate": None,
            "false_consensus_rate": None,
            "extra_verifier_items": extra,
            "extra_verifier_calls": extra,
            "model_calls": extra * len(JUDGES),
        }

    clean = [it for it in items if not it["is_corrupted"]]
    corrupt = [it for it in items if it["is_corrupted"]]
    false_accept = sum(1 for it in corrupt if decisions[it["id"]]) / len(corrupt)
    true_accept = sum(1 for it in clean if decisions[it["id"]]) / len(clean)
    false_consensus = sum(
        1 for it in corrupt
        if rf_unanimous_true(compute_metrics.rf, it) and decisions[it["id"]]
    ) / len(corrupt)
    return {
        "status": "complete",
        "missing_grounded_items": 0,
        "false_accept_rate": false_accept,
        "true_accept_rate": true_accept,
        "false_consensus_rate": false_consensus,
        "extra_verifier_items": extra,
        "extra_verifier_calls": extra,
        "model_calls": extra * len(JUDGES),
    }


def evaluate_policy(items, rf, store, risk, policy, rng=None, budget=None):
    decisions = {}
    escalated = {}
    if policy == "random_routed_budget_matched":
        assert rng is not None and budget is not None
        sample_size = min(budget, len(items))
        routed_ids = {it["id"] for it in rng.sample(items, sample_size)}
    else:
        routed_ids = set()

    for it in items:
        rf_majority = rf_majority_accept(rf, it)
        if policy == "rf_majority":
            escalate = False
            accept = rf_majority
        elif policy == "rf_unanimous":
            escalate = False
            accept = rf_unanimous_true(rf, it)
        elif policy == "always_grounded":
            escalate = True
            accept = grounded_accept(store, it)
        elif policy == "juryprobe_routed":
            escalate = bool(risk["high_risk"] and rf_majority)
            accept = grounded_accept(store, it) if escalate else rf_majority
        elif policy == "disagreement_routed":
            escalate = rf_disagrees(rf, it)
            accept = grounded_accept(store, it) if escalate else rf_majority
        elif policy == "random_routed_budget_matched":
            escalate = it["id"] in routed_ids
            accept = grounded_accept(store, it) if escalate else rf_majority
        else:
            raise ValueError(policy)
        decisions[it["id"]] = accept
        escalated[it["id"]] = escalate

    compute_metrics.rf = rf
    return {"policy": policy, **compute_metrics(items, decisions, escalated)}


def juryprobe_budget(items, rf, risk):
    if not risk["high_risk"]:
        return 0
    return sum(1 for it in items if rf_majority_accept(rf, it))


def evaluate_split(cfg, split_seed, args):
    items = load_jsonl(cfg["data"])
    rf = load_verdicts(cfg["rf"])
    calibration, deployment = choose_split(
        items, args.calib_clean, args.calib_corrupt, split_seed
    )
    risk = risk_assessment(
        calibration, rf, seed=split_seed, permutations=args.permutations
    )
    store = GroundedStore(cfg["grounded_cache"], cfg["legacy_grounded"])
    budget = juryprobe_budget(deployment, rf, risk)

    rows = []
    for policy in [
        "rf_majority",
        "rf_unanimous",
        "disagreement_routed",
        "juryprobe_routed",
        "always_grounded",
    ]:
        rows.append(evaluate_policy(deployment, rf, store, risk, policy))

    random_rows = []
    for trial in range(args.random_trials):
        rng = random.Random(args.random_seed_base + split_seed * 100000 + trial)
        random_rows.append(
            evaluate_policy(
                deployment, rf, store, risk,
                "random_routed_budget_matched",
                rng=rng,
                budget=budget,
            )
        )
    rows.append(average_random_rows(random_rows))

    return {
        "family": cfg["family"].lower(),
        "split_seed": split_seed,
        "mode": "heldout",
        "calibration": {
            "n_clean": args.calib_clean,
            "n_corrupt": args.calib_corrupt,
        },
        "deployment": {
            "n_clean": sum(1 for it in deployment if not it["is_corrupted"]),
            "n_corrupt": sum(1 for it in deployment if it["is_corrupted"]),
        },
        "grounded_verifier": "same cheap judge jury, grounded majority",
        "oracle_used": False,
        "gold_fallback_used": False,
        "risk_estimated_on": "calibration",
        "policy_evaluated_on": "deployment",
        "risk_from_calibration": risk,
        "random_routed": {
            "sampling_frame": "all deployment items",
            "budget_matched_to": "juryprobe_routed extra verifier items",
            "random_trials": args.random_trials,
            "note": "RF-accept-only sampling with the same budget is degenerate because JuryProbe-Routed routes all RF-majority-accept items in high-risk panels.",
        },
        "deployment_policy_table": rows,
        "missing_grounded_items": max(row["missing_grounded_items"] for row in rows),
        "status": "complete" if all(row["status"] == "complete" for row in rows) else "missing_grounded",
    }


def average_random_rows(rows):
    out = {
        "policy": "random_routed_budget_matched",
        "status": "complete" if all(r["status"] == "complete" for r in rows) else "missing_grounded",
        "missing_grounded_items": sum(r["missing_grounded_items"] for r in rows),
    }
    for key in [
        "false_accept_rate",
        "true_accept_rate",
        "false_consensus_rate",
        "extra_verifier_items",
        "extra_verifier_calls",
        "model_calls",
    ]:
        vals = [r[key] for r in rows]
        out[key] = mean(vals)
        out[f"{key}_random_std"] = std(vals)
    return out


def aggregate(results):
    grouped = defaultdict(list)
    risk_grouped = defaultdict(list)
    for res in results:
        risk_grouped[res["family"]].append(res["risk_from_calibration"])
        for row in res["deployment_policy_table"]:
            grouped[(res["family"], row["policy"])].append(row)

    risk_summary = []
    for family, risks in sorted(risk_grouped.items()):
        high = sum(1 for r in risks if r["high_risk"])
        risk_summary.append({
            "family": family,
            "high_risk_detected_splits": high,
            "n_splits": len(risks),
            "high_risk_rate": high / len(risks),
            "fn_corr_mean": mean([r["fn_corr"] for r in risks]),
            "fn_corr_std": std([r["fn_corr"] for r in risks]),
            "residual_lift_mean": mean([r["residual_lift"] for r in risks]),
            "residual_lift_std": std([r["residual_lift"] for r in risks]),
            "p_value_mean": mean([r["p_value"] for r in risks]),
            "p_value_std": std([r["p_value"] for r in risks]),
        })

    policy_summary = []
    for (family, policy), rows in sorted(grouped.items()):
        summary = {
            "family": family,
            "policy": policy,
            "n_splits": len(rows),
            "all_complete": all(r["status"] == "complete" for r in rows),
            "missing_grounded_items_total": sum(r["missing_grounded_items"] for r in rows),
        }
        for key in [
            "false_accept_rate",
            "true_accept_rate",
            "false_consensus_rate",
            "extra_verifier_items",
            "extra_verifier_calls",
            "model_calls",
        ]:
            vals = [r[key] for r in rows]
            summary[f"{key}_mean"] = mean(vals)
            summary[f"{key}_std"] = std(vals)
        policy_summary.append(summary)
    return {"risk_summary": risk_summary, "policy_summary": policy_summary}


def markdown(agg):
    lines = [
        "# JuryProbe Guardrail Baseline Evaluation",
        "",
        "Held-out 10-split evaluation. Risk is estimated on calibration; policies are evaluated on deployment.",
        "",
        "Disagreement-Routed is the strongest simple disagreement-based escalation baseline: it escalates every non-unanimous reference-free panel decision.",
        "",
        "Random-Routed is budget-matched to JuryProbe-Routed and samples from all deployment items. It tests whether gains are explained merely by spending the same number of grounded verifier calls.",
        "",
        "## Calibration Risk",
        "",
        "| Family | High-risk Detected | FN Corr | Residual Lift | p-value |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in agg["risk_summary"]:
        lines.append(
            f"| {row['family']} | {row['high_risk_detected_splits']}/{row['n_splits']} | "
            f"{fmt(row['fn_corr_mean'])} ± {fmt(row['fn_corr_std'])} | "
            f"{fmt(row['residual_lift_mean'])} ± {fmt(row['residual_lift_std'])} | "
            f"{fmt(row['p_value_mean'])} ± {fmt(row['p_value_std'])} |"
        )
    lines += [
        "",
        "## Policy Baselines",
        "",
        "| Family | Policy | False Accept | True Accept | False Consensus | Extra Verifier Items | Model Calls |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    order = {
        "rf_majority": 0,
        "rf_unanimous": 1,
        "disagreement_routed": 2,
        "random_routed_budget_matched": 3,
        "juryprobe_routed": 4,
        "always_grounded": 5,
    }
    rows = sorted(agg["policy_summary"], key=lambda r: (r["family"], order.get(r["policy"], 99)))
    for row in rows:
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
    ap.add_argument("--random-trials", type=int, default=100)
    ap.add_argument("--random-seed-base", type=int, default=20260609)
    ap.add_argument("--out", default="results/guardrail_baselines_v1/summary.json")
    ap.add_argument("--md-out", default="results/guardrail_baselines_v1/summary.md")
    args = ap.parse_args()

    seeds = [int(s.strip()) for s in args.seeds.split(",") if s.strip()]
    results = []
    for seed in seeds:
        for cfg in family_configs():
            print(f"[seed {seed}] {cfg['family']}", flush=True)
            results.append(evaluate_split(cfg, seed, args))

    agg = aggregate(results)
    output = {
        "mode": "heldout_baselines_multiseed",
        "seeds": seeds,
        "calibration": {"n_clean": args.calib_clean, "n_corrupt": args.calib_corrupt},
        "random_trials": args.random_trials,
        "oracle_used": False,
        "gold_fallback_used": False,
        "risk_estimated_on": "calibration",
        "policy_evaluated_on": "deployment",
        "per_seed_results": results,
        **agg,
    }
    out = ROOT / args.out
    md = ROOT / args.md_out
    out.parent.mkdir(parents=True, exist_ok=True)
    md.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    md.write_text(markdown(agg))
    print(json.dumps({"json": str(out.relative_to(ROOT)), "markdown": str(md.relative_to(ROOT))}, indent=2))
    print()
    print(markdown(agg))


if __name__ == "__main__":
    main()
