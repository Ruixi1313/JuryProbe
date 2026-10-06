#!/usr/bin/env python3
"""Threshold sensitivity / rule ablation for the consensus-risk decision rule.

Recomputes per-split risk statistics (fn_corr, residual lift, permutation p)
for all families from cached RF verdicts (no API calls), then reports:
  1. per-family ranges of each statistic across splits;
  2. the invariance region: how far each threshold can move (others fixed)
     without changing ANY split-level high/low-risk decision;
  3. single-statistic ablations at the default thresholds.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evaluate_guardrail_policies import (  # noqa: E402
    JUDGES,
    RISK_THRESHOLDS,
    choose_split,
    risk_assessment,
)
from src.io_utils import RawCache, load_jsonl  # noqa: E402

FAMILIES = {
    # family -> (data, rf_cache, expected_regime)
    "number": (
        "data/frozen/number_v3/number_corruption_pool_v3_n300.jsonl",
        "results/number_corruption_pool_v3_n300_rf.jsonl",
        "high",
    ),
    "entity": (
        "data/entity_corruption_pool_v4_n300.jsonl",
        "results/entity_corruption_pool_v4_n300_rf.jsonl",
        "high",
    ),
    # NOTE: attribute excluded from pooled analysis — the paper's attribute
    # risk protocol uses the GPT-4o-detectable subset (see
    # attribute_corruption_pool_v3_n300_analysis.json, n_detectable=296);
    # a naive full-pool split recomputation is not faithful to it.
    "obvious_contradiction_control_v2": (
        "data/obvious_contradiction_control_v2_n300.jsonl",
        "results/obvious_number_control_n300_rf.jsonl",
        "low",
    ),
}


def load_rf(items, cache_path):
    cache = RawCache(ROOT / cache_path)
    rf = {}
    for item in items:
        rf[item["id"]] = {}
        for judge in JUDGES:
            rec = cache.get(judge, item["id"], "reference_free", None)
            if rec is None:
                raise SystemExit(f"missing verdict {cache_path} {item['id']} {judge}")
            rf[item["id"]][judge] = rec["verdict"]
    return rf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="1,2,3,4,5,6,7,8,9,10")
    ap.add_argument("--permutations", type=int, default=3000)
    ap.add_argument("--calib-clean", type=int, default=150)
    ap.add_argument("--calib-corrupt", type=int, default=150)
    ap.add_argument("--out", default="results/threshold_sensitivity_analysis.json")
    ap.add_argument("--md-out", default="results/threshold_sensitivity_analysis.md")
    args = ap.parse_args()
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]

    stats = {}
    for family, (data, cache, regime) in FAMILIES.items():
        items = load_jsonl(ROOT / data)
        rf = load_rf(items, cache)
        rows = []
        for seed in seeds:
            calibration, _ = choose_split(items, args.calib_clean, args.calib_corrupt, seed)
            risk = risk_assessment(calibration, rf, seed=seed, permutations=args.permutations)
            rows.append(risk)
        stats[family] = {"regime": regime, "per_seed": rows}
        print(f"{family}: corr [{min(r['fn_corr'] for r in rows):.3f}, "
              f"{max(r['fn_corr'] for r in rows):.3f}]  "
              f"lift [{min(r['residual_lift'] for r in rows):.3f}, "
              f"{max(r['residual_lift'] for r in rows):.3f}]  "
              f"p [{min(r['p_value'] for r in rows):.4f}, "
              f"{max(r['p_value'] for r in rows):.4f}]  "
              f"high-risk {sum(r['high_risk'] for r in rows)}/{len(rows)}")

    high = [r for f in stats.values() if f["regime"] == "high" for r in f["per_seed"]]
    low = [r for f in stats.values() if f["regime"] == "low" for r in f["per_seed"]]

    def decisions(corr_t, lift_t, p_t):
        def rule(r):
            return r["fn_corr"] > corr_t and r["residual_lift"] > lift_t and r["p_value"] < p_t
        errors_high = sum(1 for r in high if not rule(r))
        errors_low = sum(1 for r in low if rule(r))
        return errors_high, errors_low

    d = RISK_THRESHOLDS
    base = decisions(d["fn_only_corr"], d["residual_lift"], d["perm_p"])

    # Invariance ranges (vary one threshold, others at defaults, decisions unchanged)
    inv = {}
    # corr threshold: rule fires only if corr > t; low-risk splits have lift=0/p=1
    # so any t keeps them low; high splits need t < min(corr | high)
    inv["fn_only_corr"] = {"min": 0.0, "max": min(r["fn_corr"] for r in high)}
    inv["residual_lift"] = {"min": 0.0, "max": min(r["residual_lift"] for r in high)}
    inv["perm_p"] = {
        "min": max(r["p_value"] for r in high),
        "max": min(r["p_value"] for r in low),
    }

    # single-statistic ablations at defaults
    abl = {
        "corr_only>0.15": (
            sum(1 for r in high if not r["fn_corr"] > 0.15),
            sum(1 for r in low if r["fn_corr"] > 0.15),
        ),
        "lift_only>1.5": (
            sum(1 for r in high if not r["residual_lift"] > 1.5),
            sum(1 for r in low if r["residual_lift"] > 1.5),
        ),
        "p_only<0.05": (
            sum(1 for r in high if not r["p_value"] < 0.05),
            sum(1 for r in low if r["p_value"] < 0.05),
        ),
        "conjunction (paper)": base,
    }

    md = [
        "# Threshold Sensitivity and Rule Ablation",
        "",
        f"High-risk splits pooled: {len(high)} (number, entity x seeds); "
        f"low-risk splits: {len(low)} (obvious-contradiction control v2).",
        "",
        "## Per-family statistic ranges",
        "",
        "| Family | Regime | FN Corr min/max | Lift min/max | p min/max | High-risk |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for fam, f in stats.items():
        rows = f["per_seed"]
        md.append(
            f"| {fam} | {f['regime']} | "
            f"{min(r['fn_corr'] for r in rows):.3f} / {max(r['fn_corr'] for r in rows):.3f} | "
            f"{min(r['residual_lift'] for r in rows):.2f} / {max(r['residual_lift'] for r in rows):.2f} | "
            f"{min(r['p_value'] for r in rows):.4f} / {max(r['p_value'] for r in rows):.4f} | "
            f"{sum(r['high_risk'] for r in rows)}/{len(rows)} |"
        )
    md += [
        "",
        "## Decision-invariance ranges (vary one threshold, all split decisions unchanged)",
        "",
        "| Threshold | Default | Invariant range |",
        "|---|---:|---|",
        f"| fn_only_corr | {d['fn_only_corr']} | any value in [0.00, {inv['fn_only_corr']['max']:.3f}) |",
        f"| residual_lift | {d['residual_lift']} | any value in [0.00, {inv['residual_lift']['max']:.2f}) |",
        f"| perm_p | {d['perm_p']} | any value in ({inv['perm_p']['min']:.4f}, {inv['perm_p']['max']:.4f}) |",
        "",
        "## Single-statistic ablation (errors at default thresholds)",
        "",
        "| Rule | Missed high-risk | False high-risk (control) |",
        "|---|---:|---:|",
    ]
    for name, (eh, el) in abl.items():
        md.append(f"| {name} | {eh}/{len(high)} | {el}/{len(low)} |")
    md.append("")

    out = {
        "thresholds_default": d,
        "per_family": {
            fam: {"regime": f["regime"], "per_seed": f["per_seed"]}
            for fam, f in stats.items()
        },
        "invariance": inv,
        "ablation_errors": {k: {"missed_high": v[0], "false_high": v[1]} for k, v in abl.items()},
    }
    (ROOT / args.out).write_text(json.dumps(out, indent=2) + "\n")
    (ROOT / args.md_out).write_text("\n".join(md))
    print()
    print("\n".join(md))


if __name__ == "__main__":
    main()
