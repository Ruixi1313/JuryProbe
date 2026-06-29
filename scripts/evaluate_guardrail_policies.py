#!/usr/bin/env python3
"""Evaluate JuryProbe guardrail policies with a real grounded verifier.

The guardrail protects accept decisions:

  if panel is low-risk:
      use reference-free majority
  if panel is high-risk:
      RF majority accept -> grounded verifier
      RF majority reject -> keep reject

The grounded verifier uses the same cheap judge jury with the original statement
as a trusted reference. The final grounded decision is majority vote.

Modes:
  full    : estimate panel risk on the full frozen dataset and report policies
            on the full set. This is the first main-table version.
  heldout : estimate panel risk on a labeled calibration probe and report
            policies only on the held-out deployment split.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
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

from src.io_utils import RawCache, load_jsonl
from src.judges import _call_openrouter, _parse_truth

JUDGES = [
    "meta-llama/llama-3.1-8b-instruct",
    "qwen/qwen-2.5-7b-instruct",
    "google/gemma-3-12b-it",
]
MODE = "grounded_verifier"
RISK_THRESHOLDS = {"fn_only_corr": 0.15, "residual_lift": 1.5, "perm_p": 0.05}


def load_verdicts(path):
    by_item = {}
    for rec in load_jsonl(path):
        by_item.setdefault(rec["item_id"], {})[rec["judge"]] = rec["verdict"]
    return by_item


def majority_accept(verdicts):
    return sum(1 for v in verdicts if v == "true") >= 2


def unanimous_true(verdicts):
    return len(verdicts) == len(JUDGES) and all(v == "true" for v in verdicts)


def pearson(x, y):
    n = len(x)
    if n == 0:
        return 0.0
    mx, my = sum(x) / n, sum(y) / n
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sx = sum((a - mx) ** 2 for a in x) ** 0.5
    sy = sum((b - my) ** 2 for b in y) ** 0.5
    return num / (sx * sy) if sx > 0 and sy > 0 else 0.0


def mean_pair(miss, idx):
    vals = []
    for a in range(len(JUDGES)):
        for b in range(a + 1, len(JUDGES)):
            ja, jb = JUDGES[a], JUDGES[b]
            vals.append(pearson([miss[ja][i] for i in idx], [miss[jb][i] for i in idx]))
    return sum(vals) / len(vals) if vals else 0.0


def all3(miss, idx):
    return sum(1 for i in idx if all(miss[j][i] for j in JUDGES)) / len(idx) if idx else 0.0


def risk_assessment(items, rf, seed=17, permutations=3000):
    """Estimate panel-level risk on a labeled calibration probe."""
    corr_idx = [i for i, it in enumerate(items) if it["is_corrupted"]]
    miss = {}
    for j in JUDGES:
        miss[j] = [
            1 if (items[i]["is_corrupted"] and rf.get(items[i]["id"], {}).get(j) == "true") else 0
            for i in range(len(items))
        ]
    fn_corr = mean_pair(miss, corr_idx)
    obs = all3(miss, corr_idx)

    rng = random.Random(seed)
    nulls = []
    for _ in range(permutations):
        shuffled = {}
        for j in JUDGES:
            vals = [miss[j][i] for i in corr_idx]
            rng.shuffle(vals)
            shuffled[j] = vals
        nulls.append(sum(1 for k in range(len(corr_idx)) if all(shuffled[j][k] for j in JUDGES)) / len(corr_idx))
    null_mean = sum(nulls) / len(nulls) if nulls else 0.0
    if null_mean > 0:
        lift = obs / null_mean
    elif obs == 0:
        lift = 0.0
    else:
        lift = float("inf")
    p = (sum(1 for v in nulls if v >= obs) + 1) / (len(nulls) + 1) if nulls else 1.0
    high_risk = (
        fn_corr > RISK_THRESHOLDS["fn_only_corr"]
        and lift > RISK_THRESHOLDS["residual_lift"]
        and p < RISK_THRESHOLDS["perm_p"]
    )
    return {
        "n_items": len(items),
        "n_corrupted": len(corr_idx),
        "fn_corr": fn_corr,
        "all3": obs,
        "perm_null": null_mean,
        "residual_lift": lift,
        "p_value": p,
        "high_risk": high_risk,
        "risk_regime": "high-risk panel" if high_risk else "low-risk panel",
        "thresholds": RISK_THRESHOLDS,
    }


def grounded_prompt(ref, stmt):
    return (
        "You are verifying a statement against a trusted reference.\n\n"
        f"Reference (trusted, correct): {ref}\n\n"
        f"Statement to check: {stmt}\n\n"
        "Is the Statement fully consistent with the Reference? Answer ONLY "
        "'true' (consistent) or 'false' (contradicts the reference).\n\nYour answer:"
    )


def call_grounded(model, ref, stmt):
    try:
        resp = _call_openrouter(model, grounded_prompt(ref, stmt), max_tokens=64, temperature=0.0)
        msg = resp["choices"][0]["message"]["content"]
        usage = resp.get("usage", {})
        return {
            "verdict": _parse_truth(msg),
            "raw_response": msg,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
        }
    except Exception as exc:
        return {
            "verdict": "parse_fail",
            "raw_response": f"ERROR: {exc}",
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }


class GroundedStore:
    def __init__(self, write_path, seed_paths):
        self.cache = RawCache(write_path)
        self.seed_caches = [RawCache(path) for path in seed_paths if path.exists()]

    def get_existing(self, judge, item):
        cached = self.cache.get(judge, item["id"], MODE, None)
        if cached:
            return cached
        for seed in self.seed_caches:
            legacy = seed.get(judge, item["id"], "grounded_foil", None)
            if legacy:
                rec = {
                    "judge": judge,
                    "item_id": item["id"],
                    "mode": MODE,
                    "prior": None,
                    "verdict": legacy["verdict"],
                    "raw_response": legacy.get("raw_response", ""),
                    "prompt_tokens": legacy.get("prompt_tokens", 0),
                    "completion_tokens": legacy.get("completion_tokens", 0),
                    "source_cache": str(seed.path.relative_to(ROOT)),
                }
                self.cache.put(rec)
                return rec
        return None

    def get_or_call(self, judge, item, run_grounded):
        existing = self.get_existing(judge, item)
        if existing:
            return existing["verdict"]
        if not run_grounded:
            return None
        result = call_grounded(judge, item.get("original_statement", ""), item["statement"])
        self.cache.put({
            "judge": judge,
            "item_id": item["id"],
            "mode": MODE,
            "prior": None,
            **result,
        })
        return result["verdict"]

    def item_verdicts(self, item, run_grounded):
        verdicts = []
        missing = False
        for judge in JUDGES:
            verdict = self.get_or_call(judge, item, run_grounded)
            if verdict is None:
                missing = True
            verdicts.append(verdict or "missing")
        return None if missing else verdicts


def choose_split(items, calib_clean, calib_corrupt, seed):
    rng = random.Random(seed)
    clean = [it for it in items if not it["is_corrupted"]]
    corrupt = [it for it in items if it["is_corrupted"]]
    rng.shuffle(clean)
    rng.shuffle(corrupt)
    calibration = clean[:calib_clean] + corrupt[:calib_corrupt]
    deployment = clean[calib_clean:] + corrupt[calib_corrupt:]
    return calibration, deployment


def policy_grounded_item_ids(items, rf, risk, policy):
    needed = set()
    for it in items:
        verdicts = [rf.get(it["id"], {}).get(j, "parse_fail") for j in JUDGES]
        rf_majority = majority_accept(verdicts)
        if policy == "Always Grounded":
            needed.add(it["id"])
        elif policy == "JuryProbe-Routed" and risk["high_risk"] and rf_majority:
            needed.add(it["id"])
    return needed


def policy_rows(items, rf, grounded_store, risk, run_grounded):
    rows = []
    policies = [
        "Reference-Free Majority",
        "Reference-Free Unanimous",
        "Always Grounded",
        "JuryProbe-Routed",
    ]
    by_id = {it["id"]: it for it in items}
    for policy in policies:
        decisions = {}
        escalated = {}
        needed_grounded = policy_grounded_item_ids(items, rf, risk, policy)
        missing_grounded = []
        for it in items:
            rf_verdicts = [rf.get(it["id"], {}).get(j, "parse_fail") for j in JUDGES]
            rf_majority = majority_accept(rf_verdicts)
            rf_unanimous_true = unanimous_true(rf_verdicts)

            if policy == "Reference-Free Majority":
                escalate = False
                accept = rf_majority
            elif policy == "Reference-Free Unanimous":
                escalate = False
                accept = rf_unanimous_true
            elif policy == "Always Grounded":
                escalate = True
                verdicts = grounded_store.item_verdicts(it, run_grounded)
                if verdicts is None:
                    missing_grounded.append(it["id"])
                    accept = None
                else:
                    accept = majority_accept(verdicts)
            else:
                escalate = bool(risk["high_risk"] and rf_majority)
                if escalate:
                    verdicts = grounded_store.item_verdicts(it, run_grounded)
                    if verdicts is None:
                        missing_grounded.append(it["id"])
                        accept = None
                    else:
                        accept = majority_accept(verdicts)
                else:
                    accept = rf_majority

            decisions[it["id"]] = {
                "accept": accept,
                "rf_unanimous_true": rf_unanimous_true,
                "escalated": escalate,
            }
            escalated[it["id"]] = escalate
        complete = not missing_grounded
        rows.append({
            "policy": policy_name(policy),
            "status": "complete" if complete else "missing_grounded",
            "missing_grounded_items": len(set(missing_grounded)),
            **compute_metrics(items, decisions, escalated, complete),
        })
    return rows


def policy_name(policy):
    return {
        "Reference-Free Majority": "rf_majority",
        "Reference-Free Unanimous": "rf_unanimous",
        "Always Grounded": "always_grounded",
        "JuryProbe-Routed": "juryprobe_routed",
    }[policy]


def compute_metrics(items, decisions, escalated, complete):
    if not complete:
        extra = sum(1 for it in items if escalated[it["id"]])
        return {
            "false_accept_rate": None,
            "true_accept_rate": None,
            "false_consensus_rate": None,
            "extra_verifier_items": extra,
            "extra_verifier_calls": extra,
            "model_calls": extra * len(JUDGES),
        }
    clean = [it for it in items if not it["is_corrupted"]]
    corrupt = [it for it in items if it["is_corrupted"]]
    false_accept = sum(1 for it in corrupt if decisions[it["id"]]["accept"]) / len(corrupt)
    true_accept = sum(1 for it in clean if decisions[it["id"]]["accept"]) / len(clean)
    false_consensus = sum(
        1 for it in corrupt
        if decisions[it["id"]]["rf_unanimous_true"] and decisions[it["id"]]["accept"]
    ) / len(corrupt)
    extra = sum(1 for it in items if escalated[it["id"]])
    return {
        "false_accept_rate": false_accept,
        "true_accept_rate": true_accept,
        "false_consensus_rate": false_consensus,
        "extra_verifier_items": extra,
        "extra_verifier_calls": extra,
        "model_calls": extra * len(JUDGES),
    }


def family_configs():
    number_validated = ROOT / "results/guardrail_grounded/number_corruption_pool_v3_n300_grounded_verifier_validated.jsonl"
    number_canonical = ROOT / "results/guardrail_grounded/number_corruption_pool_v3_n300_grounded_verifier_canonical.jsonl"
    entity_validated = ROOT / "results/guardrail_grounded/entity_corruption_pool_v4_n300_grounded_verifier_validated.jsonl"
    entity_canonical = ROOT / "results/guardrail_grounded/entity_corruption_pool_v4_n300_grounded_verifier_canonical.jsonl"
    return [
        {
            "family": "Number",
            "stem": "number_corruption_pool_v3_n300",
            "data": ROOT / "data/frozen/number_v3/number_corruption_pool_v3_n300.jsonl",
            "rf": ROOT / "results/frozen/number_v3/number_corruption_pool_v3_n300_rf.jsonl",
            "legacy_grounded": [ROOT / "results/frozen/number_v3/number_corruption_pool_v3_n300_grounded.jsonl"],
            "grounded_cache": number_validated if number_validated.exists() else number_canonical,
        },
        {
            "family": "Entity",
            "stem": "entity_corruption_pool_v4_n300",
            "data": ROOT / "data/frozen/v4/entity_corruption_pool_v4_n300.jsonl",
            "rf": ROOT / "results/frozen/v4/entity_corruption_pool_v4_n300_rf.jsonl",
            "legacy_grounded": [ROOT / "results/frozen/v4/entity_corruption_pool_v4_n300_grounded.jsonl"],
            "grounded_cache": entity_validated if entity_validated.exists() else entity_canonical,
        },
    ]


def evaluate_config(cfg, mode, args):
    items = load_jsonl(cfg["data"])
    rf = load_verdicts(cfg["rf"])
    if mode == "heldout":
        calibration, deployment = choose_split(items, args.calib_clean, args.calib_corrupt, args.seed)
    else:
        calibration, deployment = items, items
    risk = risk_assessment(calibration, rf, seed=args.seed, permutations=args.permutations)
    store = GroundedStore(cfg["grounded_cache"], cfg["legacy_grounded"])
    rows = policy_rows(deployment, rf, store, risk, run_grounded=args.run_grounded)
    missing_total = max((row["missing_grounded_items"] for row in rows), default=0)
    risk_source = "calibration" if mode == "heldout" else "full_set"
    eval_source = "deployment" if mode == "heldout" else "full_set"
    return {
        "family": cfg["family"].lower(),
        "stem": cfg["stem"],
        "mode": mode,
        "split_seed": args.seed,
        "grounded_verifier": "same cheap judge jury, grounded majority",
        "oracle_used": False,
        "gold_fallback_used": False,
        "risk_estimated_on": risk_source,
        "policy_evaluated_on": eval_source,
        "calibration": {
            "n_items": len(calibration),
            "n_clean": sum(1 for it in calibration if not it["is_corrupted"]),
            "n_corrupt": sum(1 for it in calibration if it["is_corrupted"]),
        },
        "deployment": {
            "n_items": len(deployment),
            "n_clean": sum(1 for it in deployment if not it["is_corrupted"]),
            "n_corrupt": sum(1 for it in deployment if it["is_corrupted"]),
        },
        "grounded_verifier_details": {
            "judges": JUDGES,
            "decision_rule": "grounded majority",
            "cache": str(cfg["grounded_cache"].relative_to(ROOT)),
            "oracle_fallback": False,
            "gold_fallback": False,
        },
        "risk_from_calibration": risk,
        "deployment_policy_table": rows,
        "missing_grounded_items": missing_total,
        "status": "complete" if missing_total == 0 else "missing_grounded",
    }


def markdown_table(results):
    lines = [
        "| Split | Family | Policy | False Accept | True Accept | False Consensus | Extra Verifier Items | Extra Verifier Calls | Model Calls |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for res in results:
        split = "Full set" if res["mode"] == "full" else "Held-out"
        for row in res["deployment_policy_table"]:
            fa = fmt(row["false_accept_rate"])
            ta = fmt(row["true_accept_rate"])
            fc = fmt(row["false_consensus_rate"])
            lines.append(
                f"| {split} | {res['family']} | {row['policy']} | "
                f"{fa} | {ta} | {fc} | {row['extra_verifier_items']} | "
                f"{row['extra_verifier_calls']} | "
                f"{row['model_calls']} |"
            )
    return "\n".join(lines)


def fmt(value):
    return "MISSING" if value is None else f"{value:.3f}"


def write_outputs(results, out_path, md_path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"results": results}, indent=2, ensure_ascii=False) + "\n")
    md = [
        "# JuryProbe Real Grounded Guardrail Evaluation",
        "",
        "Grounded verifier: the same three cheap judges are given the original statement as a trusted reference; grounded majority determines accept/reject.",
        "",
        "Risk assessment is panel-level, not sample-level. The routed policy protects accept decisions:",
        "",
        "```text",
        "if panel low-risk: RF majority",
        "if panel high-risk and RF majority accept: grounded verifier",
        "if panel high-risk and RF majority reject: keep reject",
        "```",
        "",
        markdown_table(results),
        "",
    ]
    md_path.write_text("\n".join(md))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["full", "heldout", "both"], default="both")
    ap.add_argument("--run-grounded", action="store_true")
    ap.add_argument("--seed", type=int, default=20260609)
    ap.add_argument("--calib-clean", type=int, default=150)
    ap.add_argument("--calib-corrupt", type=int, default=150)
    ap.add_argument("--permutations", type=int, default=3000)
    ap.add_argument("--out", default="results/guardrail_policy_real_grounded.json")
    ap.add_argument("--md-out", default="docs/guardrail_policy_real_grounded.md")
    args = ap.parse_args()

    if args.run_grounded and not os.environ.get("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    modes = ["full", "heldout"] if args.mode == "both" else [args.mode]
    results = []
    for mode in modes:
        for cfg in family_configs():
            print(f"[{mode}] {cfg['family']}...", flush=True)
            results.append(evaluate_config(cfg, mode, args))

    write_outputs(results, ROOT / args.out, ROOT / args.md_out)
    print(json.dumps({"json": args.out, "markdown": args.md_out}, indent=2))
    print()
    print(markdown_table(results))


if __name__ == "__main__":
    main()
