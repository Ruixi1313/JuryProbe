#!/usr/bin/env python3
"""Evaluate JuryProbe specificity in a grounded low-risk setting.

This control asks whether JuryProbe always declares panels high-risk. It reuses
the same cheap judge jury, but in grounded verifier mode, where each judge sees
the original statement as a trusted reference. No oracle or gold fallback is
used; every verdict is read from the grounded verifier cache.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evaluate_guardrail_policies import (
    JUDGES,
    choose_split,
    family_configs,
    load_jsonl,
    load_verdicts,
    risk_assessment,
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


def validate_complete(items, verdicts):
    missing = []
    invalid = []
    for item in items:
        by_judge = verdicts.get(item["id"], {})
        for judge in JUDGES:
            verdict = by_judge.get(judge)
            if verdict is None:
                missing.append({"item_id": item["id"], "judge": judge})
            elif verdict not in {"true", "false"}:
                invalid.append({"item_id": item["id"], "judge": judge, "verdict": verdict})
    return missing, invalid


def fn_diagnostics(items, verdicts):
    corrupt = [item for item in items if item["is_corrupted"]]
    if not corrupt:
        return {
            "n_corrupted": 0,
            "false_negative_vote_rate": None,
            "false_negative_any_item_rate": None,
            "false_negative_all3_item_rate": None,
            "false_negative_rate_by_judge": {judge: None for judge in JUDGES},
        }

    by_judge_counts = {judge: 0 for judge in JUDGES}
    any_item = 0
    all3_item = 0
    total_votes = 0
    total_fn_votes = 0

    for item in corrupt:
        item_votes = []
        for judge in JUDGES:
            verdict = verdicts[item["id"]][judge]
            fn = verdict == "true"
            by_judge_counts[judge] += int(fn)
            total_fn_votes += int(fn)
            total_votes += 1
            item_votes.append(fn)
        any_item += int(any(item_votes))
        all3_item += int(all(item_votes))

    return {
        "n_corrupted": len(corrupt),
        "false_negative_vote_rate": total_fn_votes / total_votes,
        "false_negative_any_item_rate": any_item / len(corrupt),
        "false_negative_all3_item_rate": all3_item / len(corrupt),
        "false_negative_rate_by_judge": {
            judge: count / len(corrupt) for judge, count in by_judge_counts.items()
        },
    }


def evaluate_family(cfg, seeds, args):
    items = load_jsonl(cfg["data"])
    grounded = load_verdicts(cfg["grounded_cache"])
    missing, invalid = validate_complete(items, grounded)
    if missing or invalid:
        return {
            "family": cfg["family"].lower(),
            "status": "missing_or_invalid_grounded_verdicts",
            "missing_grounded_verdicts": len(missing),
            "invalid_grounded_verdicts": len(invalid),
            "missing_examples": missing[:10],
            "invalid_examples": invalid[:10],
        }

    full_risk = risk_assessment(
        items, grounded, seed=args.full_seed, permutations=args.permutations
    )
    full_diag = fn_diagnostics(items, grounded)

    per_seed = []
    for seed in seeds:
        calibration, _deployment = choose_split(
            items, args.calib_clean, args.calib_corrupt, seed
        )
        risk = risk_assessment(
            calibration, grounded, seed=seed, permutations=args.permutations
        )
        per_seed.append({
            "family": cfg["family"].lower(),
            "split_seed": seed,
            "mode": "grounded_specificity_calibration",
            "risk_estimated_on": "calibration",
            "policy_evaluated_on": "none",
            "grounded_verifier": "same cheap judge jury, grounded majority",
            "oracle_used": False,
            "gold_fallback_used": False,
            "calibration": {
                "n_items": len(calibration),
                "n_clean": sum(1 for item in calibration if not item["is_corrupted"]),
                "n_corrupt": sum(1 for item in calibration if item["is_corrupted"]),
            },
            "risk_from_grounded_calibration": risk,
            "fn_diagnostics": fn_diagnostics(calibration, grounded),
            "status": "complete",
        })

    return {
        "family": cfg["family"].lower(),
        "status": "complete",
        "grounded_cache": str(cfg["grounded_cache"].relative_to(ROOT)),
        "full_set": {
            "mode": "grounded_specificity_full",
            "risk_estimated_on": "full_set",
            "policy_evaluated_on": "none",
            "grounded_verifier": "same cheap judge jury, grounded majority",
            "oracle_used": False,
            "gold_fallback_used": False,
            "n_items": len(items),
            "n_clean": sum(1 for item in items if not item["is_corrupted"]),
            "n_corrupt": sum(1 for item in items if item["is_corrupted"]),
            "risk_from_grounded_full_set": full_risk,
            "fn_diagnostics": full_diag,
            "status": "complete",
        },
        "per_seed_results": per_seed,
    }


def aggregate(family_results):
    risk_summary = []
    for family_result in family_results:
        if family_result["status"] != "complete":
            risk_summary.append({
                "family": family_result["family"],
                "status": family_result["status"],
            })
            continue
        rows = family_result["per_seed_results"]
        risks = [row["risk_from_grounded_calibration"] for row in rows]
        diags = [row["fn_diagnostics"] for row in rows]
        high = sum(1 for risk in risks if risk["high_risk"])
        risk_summary.append({
            "family": family_result["family"],
            "status": "complete",
            "n_splits": len(rows),
            "high_risk_detected_splits": high,
            "high_risk_rate": high / len(rows),
            "fn_corr_mean": mean([risk["fn_corr"] for risk in risks]),
            "fn_corr_std": std([risk["fn_corr"] for risk in risks]),
            "all3_mean": mean([risk["all3"] for risk in risks]),
            "all3_std": std([risk["all3"] for risk in risks]),
            "residual_lift_mean": mean([risk["residual_lift"] for risk in risks]),
            "residual_lift_std": std([risk["residual_lift"] for risk in risks]),
            "p_value_mean": mean([risk["p_value"] for risk in risks]),
            "p_value_std": std([risk["p_value"] for risk in risks]),
            "false_negative_vote_rate_mean": mean(
                [diag["false_negative_vote_rate"] for diag in diags]
            ),
            "false_negative_vote_rate_std": std(
                [diag["false_negative_vote_rate"] for diag in diags]
            ),
            "false_negative_any_item_rate_mean": mean(
                [diag["false_negative_any_item_rate"] for diag in diags]
            ),
            "false_negative_any_item_rate_std": std(
                [diag["false_negative_any_item_rate"] for diag in diags]
            ),
        })
    return risk_summary


def markdown(output):
    lines = [
        "# JuryProbe Low-risk Specificity Control",
        "",
        "Setting: the same cheap judge jury receives the original statement as a trusted reference. This tests whether JuryProbe always flags panels as high-risk.",
        "",
        "No oracle or gold fallback is used; grounded verdicts come from the cached grounded verifier outputs.",
        "",
        "## Full-set Grounded Risk",
        "",
        "| Family | High-risk | FN Corr | All-3 FN | Residual Lift | p-value | FN Vote Rate |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for result in output["family_results"]:
        if result["status"] != "complete":
            lines.append(f"| {result['family']} | MISSING | NA | NA | NA | NA | NA |")
            continue
        risk = result["full_set"]["risk_from_grounded_full_set"]
        diag = result["full_set"]["fn_diagnostics"]
        lines.append(
            f"| {result['family']} | {risk['high_risk']} | "
            f"{fmt(risk['fn_corr'])} | {fmt(risk['all3'])} | "
            f"{fmt(risk['residual_lift'])} | {fmt(risk['p_value'])} | "
            f"{fmt(diag['false_negative_vote_rate'])} |"
        )

    lines += [
        "",
        "## Held-out Calibration Specificity",
        "",
        "| Family | High-risk Detected | FN Corr | All-3 FN | Residual Lift | p-value | FN Vote Rate | Any-FN Item Rate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in output["risk_summary"]:
        if row["status"] != "complete":
            lines.append(f"| {row['family']} | MISSING | NA | NA | NA | NA | NA | NA |")
            continue
        lines.append(
            f"| {row['family']} | {row['high_risk_detected_splits']}/{row['n_splits']} | "
            f"{fmt(row['fn_corr_mean'])} ± {fmt(row['fn_corr_std'])} | "
            f"{fmt(row['all3_mean'])} ± {fmt(row['all3_std'])} | "
            f"{fmt(row['residual_lift_mean'])} ± {fmt(row['residual_lift_std'])} | "
            f"{fmt(row['p_value_mean'])} ± {fmt(row['p_value_std'])} | "
            f"{fmt(row['false_negative_vote_rate_mean'])} ± {fmt(row['false_negative_vote_rate_std'])} | "
            f"{fmt(row['false_negative_any_item_rate_mean'])} ± {fmt(row['false_negative_any_item_rate_std'])} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_freeze(freeze_dir, output, json_out, md_out):
    freeze_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "artifact": "low_risk_specificity_v1",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "description": "Grounded-setting specificity control for JuryProbe risk assessment.",
        "results": str(json_out.relative_to(ROOT)),
        "markdown": str(md_out.relative_to(ROOT)),
        "oracle_used": False,
        "gold_fallback_used": False,
        "source_caches": [
            result.get("grounded_cache")
            for result in output["family_results"]
            if result.get("grounded_cache")
        ],
        "high_risk_detected": {
            row["family"]: f"{row.get('high_risk_detected_splits', 'NA')}/{row.get('n_splits', 'NA')}"
            for row in output["risk_summary"]
        },
    }
    (freeze_dir / "FREEZE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    readme = [
        "# Low-risk Specificity v1",
        "",
        "This frozen control checks whether JuryProbe always flags panels as high-risk.",
        "",
        "The control reuses the grounded verifier cache. The same cheap judge jury sees the original statement as a trusted reference; no oracle or gold fallback is used.",
        "",
        f"- Results: `{manifest['results']}`",
        f"- Markdown summary: `{manifest['markdown']}`",
        f"- High-risk detected: `{manifest['high_risk_detected']}`",
        "",
    ]
    (freeze_dir / "README.md").write_text("\n".join(readme))
    policy_src = ROOT / "docs/guardrail_policy_definition_v1.md"
    if policy_src.exists():
        shutil.copyfile(policy_src, freeze_dir / "guardrail_policy_definition_v1.md")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="1,2,3,4,5,6,7,8,9,10")
    ap.add_argument("--calib-clean", type=int, default=150)
    ap.add_argument("--calib-corrupt", type=int, default=150)
    ap.add_argument("--permutations", type=int, default=3000)
    ap.add_argument("--full-seed", type=int, default=20260609)
    ap.add_argument("--out", default="results/frozen/low_risk_specificity_v1/summary.json")
    ap.add_argument("--md-out", default="results/frozen/low_risk_specificity_v1/summary.md")
    ap.add_argument("--freeze-dir", default="frozen/low_risk_specificity_v1")
    args = ap.parse_args()

    seeds = [int(seed.strip()) for seed in args.seeds.split(",") if seed.strip()]
    family_results = [evaluate_family(cfg, seeds, args) for cfg in family_configs()]
    output = {
        "mode": "low_risk_specificity_control",
        "setting": "grounded verifier",
        "seeds": seeds,
        "calibration": {"n_clean": args.calib_clean, "n_corrupt": args.calib_corrupt},
        "grounded_verifier": "same cheap judge jury, grounded majority",
        "oracle_used": False,
        "gold_fallback_used": False,
        "risk_estimated_on": "grounded_calibration",
        "policy_evaluated_on": "none",
        "purpose": "specificity control: verify JuryProbe does not always declare high-risk",
        "family_results": family_results,
    }
    output["risk_summary"] = aggregate(family_results)
    output["status"] = (
        "complete"
        if all(result["status"] == "complete" for result in family_results)
        else "missing_or_invalid_grounded_verdicts"
    )

    json_out = ROOT / args.out
    md_out = ROOT / args.md_out
    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    md_out.write_text(markdown(output))
    write_freeze(ROOT / args.freeze_dir, output, json_out, md_out)

    print(json.dumps({
        "json": str(json_out.relative_to(ROOT)),
        "markdown": str(md_out.relative_to(ROOT)),
        "freeze_dir": args.freeze_dir,
        "status": output["status"],
    }, indent=2))
    print()
    print(markdown(output))


if __name__ == "__main__":
    main()
