#!/usr/bin/env python3
"""Evaluate reference-free branch specificity for a JuryProbe family.

The script runs the standard reference-free judge panel, estimates consensus
risk on held-out calibration splits, and reports which routing branch is
selected. It does not assume that the evaluated family is low-risk.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ENV_FILE = ROOT / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

from scripts.evaluate_guardrail_policies import (  # noqa: E402
    JUDGES,
    choose_split,
    majority_accept,
    risk_assessment,
    unanimous_true,
)
from src.io_utils import RawCache, load_jsonl  # noqa: E402
from src.judges import judge_statement  # noqa: E402


def mean(values):
    vals = [value for value in values if value is not None]
    return sum(vals) / len(vals) if vals else None


def std(values):
    vals = [value for value in values if value is not None]
    if len(vals) < 2:
        return 0.0 if vals else None
    avg = mean(vals)
    return math.sqrt(sum((value - avg) ** 2 for value in vals) / (len(vals) - 1))


def fmt(value):
    return "NA" if value is None else f"{value:.3f}"


def load_or_run_rf(items, cache_path, run, workers=1):
    cache = RawCache(cache_path)
    rf = defaultdict(dict)
    todo = []
    for item in items:
        for judge in JUDGES:
            cached = cache.get(judge, item["id"], "reference_free", None)
            if cached is None:
                if not run:
                    raise SystemExit(
                        f"Missing RF verdict for item={item['id']} judge={judge}. "
                        "Rerun with --run-rf."
                    )
                todo.append((item, judge))
            else:
                rf[item["id"]][judge] = cached["verdict"]

    def run_one(pair):
        item, judge = pair
        return item, judge, judge_statement(judge, item["statement"])

    lock = Lock()
    if todo:
        print(f"cached: {sum(len(values) for values in rf.values())}  to run: {len(todo)}")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(run_one, pair) for pair in todo]
            for completed, future in enumerate(as_completed(futures), start=1):
                item, judge, result = future.result()
                record = {
                    "judge": judge,
                    "item_id": item["id"],
                    "mode": "reference_free",
                    "prior": None,
                    "verdict": result.verdict,
                    "raw_response": result.raw_response,
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                }
                with lock:
                    cache.put(record)
                rf[item["id"]][judge] = result.verdict
                if completed % 100 == 0 or completed == len(todo):
                    print(f"  {completed}/{len(todo)}")
    return dict(rf)


def judge_sanity(items, rf):
    clean = [item for item in items if not item["is_corrupted"]]
    corrupt = [item for item in items if item["is_corrupted"]]
    output = {}
    for judge in JUDGES:
        verdicts = [rf.get(item["id"], {}).get(judge) for item in items]
        output[judge] = {
            "parse_fail": sum(verdict not in ("true", "false") for verdict in verdicts),
            "false_accept_rate": sum(
                rf.get(item["id"], {}).get(judge) == "true" for item in corrupt
            ) / len(corrupt),
            "true_accept_rate": sum(
                rf.get(item["id"], {}).get(judge) == "true" for item in clean
            ) / len(clean),
        }
    return output


def rf_verdicts(rf, item):
    return [rf.get(item["id"], {}).get(judge, "parse_fail") for judge in JUDGES]


def compute_deployment_metrics(items, rf, risk):
    clean = [item for item in items if not item["is_corrupted"]]
    corrupt = [item for item in items if item["is_corrupted"]]
    rf_majority_accepts = {}
    rf_unanimous_accepts = {}
    for item in items:
        verdicts = rf_verdicts(rf, item)
        rf_majority_accepts[item["id"]] = majority_accept(verdicts)
        rf_unanimous_accepts[item["id"]] = unanimous_true(verdicts)

    juryprobe_escalated = {
        item["id"]: bool(risk["high_risk"] and rf_majority_accepts[item["id"]])
        for item in items
    }

    # In the intended low-risk setting, JuryProbe uses RF majority directly.
    # If a split unexpectedly becomes high-risk, we still report the number of
    # accepts that would require grounded verification, without calling it.
    if risk["high_risk"]:
        juryprobe_accept = {
            item["id"]: None if juryprobe_escalated[item["id"]] else rf_majority_accepts[item["id"]]
            for item in items
        }
    else:
        juryprobe_accept = {
            item["id"]: rf_majority_accepts[item["id"]]
            for item in items
        }

    complete = all(value is not None for value in juryprobe_accept.values())
    false_accept = None
    true_accept = None
    residual_fc = None
    if complete:
        false_accept = sum(1 for item in corrupt if juryprobe_accept[item["id"]]) / len(corrupt)
        true_accept = sum(1 for item in clean if juryprobe_accept[item["id"]]) / len(clean)
        residual_fc = sum(
            1 for item in corrupt
            if rf_unanimous_accepts[item["id"]] and juryprobe_accept[item["id"]]
        ) / len(corrupt)

    rf_false_accept = sum(1 for item in corrupt if rf_majority_accepts[item["id"]]) / len(corrupt)
    rf_true_accept = sum(1 for item in clean if rf_majority_accepts[item["id"]]) / len(clean)
    rf_residual_fc = sum(
        1 for item in corrupt
        if rf_unanimous_accepts[item["id"]] and rf_majority_accepts[item["id"]]
    ) / len(corrupt)
    extra_items = sum(1 for value in juryprobe_escalated.values() if value)

    return {
        "status": "complete" if complete else "requires_grounded_for_high_risk_split",
        "rf_majority_false_accept_rate": rf_false_accept,
        "rf_majority_true_accept_rate": rf_true_accept,
        "rf_majority_residual_fc_rate": rf_residual_fc,
        "juryprobe_false_accept_rate": false_accept,
        "juryprobe_true_accept_rate": true_accept,
        "juryprobe_residual_fc_rate": residual_fc,
        "juryprobe_extra_verifier_items": extra_items,
        "juryprobe_extra_verifier_calls": extra_items * len(JUDGES),
    }


def evaluate(items, rf, seeds, args):
    per_seed = []
    for seed in seeds:
        calibration, deployment = choose_split(
            items, args.calib_clean, args.calib_corrupt, seed
        )
        risk = risk_assessment(
            calibration, rf, seed=seed, permutations=args.permutations
        )
        metrics = compute_deployment_metrics(deployment, rf, risk)
        per_seed.append({
            "split_seed": seed,
            "calibration": {
                "n_clean": sum(1 for item in calibration if not item["is_corrupted"]),
                "n_corrupt": sum(1 for item in calibration if item["is_corrupted"]),
            },
            "deployment": {
                "n_clean": sum(1 for item in deployment if not item["is_corrupted"]),
                "n_corrupt": sum(1 for item in deployment if item["is_corrupted"]),
            },
            "risk_from_calibration": risk,
            "deployment_metrics": metrics,
        })
    return per_seed


def aggregate(per_seed):
    risks = [row["risk_from_calibration"] for row in per_seed]
    metrics = [row["deployment_metrics"] for row in per_seed]
    # residual_lift can be +inf when the permutation null is 0 but observed
    # all-3 false consensus is positive; aggregate over finite values and
    # report the number of infinite splits separately.
    finite_lifts = [r["residual_lift"] for r in risks if math.isfinite(r["residual_lift"])]
    return {
        "n_splits": len(per_seed),
        "high_risk_detected_splits": sum(1 for risk in risks if risk["high_risk"]),
        "fn_corr_mean": mean([risk["fn_corr"] for risk in risks]),
        "fn_corr_std": std([risk["fn_corr"] for risk in risks]),
        "all3_mean": mean([risk["all3"] for risk in risks]),
        "all3_std": std([risk["all3"] for risk in risks]),
        "residual_lift_mean": mean(finite_lifts),
        "residual_lift_std": std(finite_lifts),
        "residual_lift_infinite_splits": len(risks) - len(finite_lifts),
        "p_value_mean": mean([risk["p_value"] for risk in risks]),
        "p_value_std": std([risk["p_value"] for risk in risks]),
        "rf_false_accept_mean": mean([m["rf_majority_false_accept_rate"] for m in metrics]),
        "rf_false_accept_std": std([m["rf_majority_false_accept_rate"] for m in metrics]),
        "rf_true_accept_mean": mean([m["rf_majority_true_accept_rate"] for m in metrics]),
        "rf_true_accept_std": std([m["rf_majority_true_accept_rate"] for m in metrics]),
        "juryprobe_false_accept_mean": mean([m["juryprobe_false_accept_rate"] for m in metrics]),
        "juryprobe_false_accept_std": std([m["juryprobe_false_accept_rate"] for m in metrics]),
        "juryprobe_true_accept_mean": mean([m["juryprobe_true_accept_rate"] for m in metrics]),
        "juryprobe_true_accept_std": std([m["juryprobe_true_accept_rate"] for m in metrics]),
        "juryprobe_verifier_calls_mean": mean([m["juryprobe_extra_verifier_calls"] for m in metrics]),
        "juryprobe_verifier_calls_std": std([m["juryprobe_extra_verifier_calls"] for m in metrics]),
    }


def markdown(output):
    summary = output["summary"]
    lines = [
        "# Reference-Free Branch-Specificity Evaluation",
        "",
        "This evaluation reports whether the frozen JuryProbe calibration rule selects grounded routing or the no-routing branch.",
        "",
        "| Family | Splits | High-risk Detected | FN Corr | All-3 FC | Lift | p-value | RF False Accept | RF True Accept | JuryProbe Calls |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        (
            f"| {output['family']} | {summary['n_splits']} | "
            f"{summary['high_risk_detected_splits']}/{summary['n_splits']} | "
            f"{fmt(summary['fn_corr_mean'])} ± {fmt(summary['fn_corr_std'])} | "
            f"{fmt(summary['all3_mean'])} ± {fmt(summary['all3_std'])} | "
            f"{fmt(summary['residual_lift_mean'])} ± {fmt(summary['residual_lift_std'])} | "
            f"{fmt(summary['p_value_mean'])} ± {fmt(summary['p_value_std'])} | "
            f"{fmt(summary['rf_false_accept_mean'])} ± {fmt(summary['rf_false_accept_std'])} | "
            f"{fmt(summary['rf_true_accept_mean'])} ± {fmt(summary['rf_true_accept_std'])} | "
            f"{fmt(summary['juryprobe_verifier_calls_mean'])} ± {fmt(summary['juryprobe_verifier_calls_std'])} |"
        ),
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/obvious_contradiction_control_n300.jsonl")
    ap.add_argument("--rf-cache", default="results/obvious_number_control_n300_rf.jsonl")
    ap.add_argument("--family", default="Obvious-Contradiction-Control")
    ap.add_argument("--run-rf", action="store_true")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--seeds", default="1,2,3,4,5,6,7,8,9,10")
    ap.add_argument("--calib-clean", type=int, default=150)
    ap.add_argument("--calib-corrupt", type=int, default=150)
    ap.add_argument("--permutations", type=int, default=3000)
    ap.add_argument("--out", default="results/obvious_contradiction_control_n300_low_risk_summary.json")
    ap.add_argument("--md-out", default="results/obvious_contradiction_control_n300_low_risk_summary.md")
    args = ap.parse_args()

    if args.run_rf and not os.environ.get("OPENROUTER_API_KEY"):
        raise SystemExit("OPENROUTER_API_KEY is not set. Add it to .env or the environment.")

    items = load_jsonl(ROOT / args.data)
    if args.workers < 1:
        raise SystemExit("--workers must be at least 1")
    rf = load_or_run_rf(items, ROOT / args.rf_cache, args.run_rf, args.workers)
    sanity = judge_sanity(items, rf)
    print(json.dumps({"judge_sanity": sanity}, indent=2))
    seeds = [int(seed.strip()) for seed in args.seeds.split(",") if seed.strip()]
    per_seed = evaluate(items, rf, seeds, args)
    output = {
        "family": args.family,
        "data": args.data,
        "rf_cache": args.rf_cache,
        "mode": "reference_free_branch_specificity",
        "purpose": "test which branch the frozen consensus-risk rule selects on the evaluated family",
        "seeds": seeds,
        "permutations": args.permutations,
        "judge_sanity": sanity,
        "per_seed_results": per_seed,
        "summary": aggregate(per_seed),
    }

    out = ROOT / args.out
    md_out = ROOT / args.md_out
    out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    md_out.write_text(markdown(output))
    print(json.dumps({"json": args.out, "markdown": args.md_out}, indent=2))
    print()
    print(markdown(output))


if __name__ == "__main__":
    main()
