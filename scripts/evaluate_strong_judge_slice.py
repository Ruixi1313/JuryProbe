#!/usr/bin/env python3
"""Evaluate the preregistered Strong Judge Slice v1.

This is a supplementary robustness analysis. It does not affect thresholds,
policy definitions, routing logic, or the primary guardrail tables.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
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
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from src.io_utils import append_jsonl, load_jsonl
from src.judges import _build_statement_prompt, _call_openrouter, _parse_truth, judge_statement

REUSED_REFERENCE_FREE_MODELS = [
    "meta-llama/llama-3.1-8b-instruct",
    "google/gemma-3-12b-it",
]
CAPABILITY_SLICE = [
    "meta-llama/llama-3.1-8b-instruct",
    "google/gemma-3-12b-it",
    "qwen/qwen3-32b",
]
NEW_MODEL_CALLS = ["qwen/qwen3-32b"]
MODELS_TO_ENSURE = CAPABILITY_SLICE
MODE = "reference_free"


def short(model):
    return model.split("/")[-1]


def load_cache(paths):
    by_key = {}
    all_records = []
    for path in paths:
        if not path.exists():
            continue
        for rec in load_jsonl(path):
            if rec.get("mode") != MODE:
                continue
            key = (rec["judge"], rec["item_id"])
            current = by_key.get(key)
            if current is None:
                by_key[key] = rec
            elif current.get("verdict") == "parse_fail" and rec.get("verdict") in {"true", "false"}:
                by_key[key] = rec
            else:
                by_key[key] = rec
            all_records.append(rec)
    return by_key, all_records


def cache_validation(records, models):
    attempts_by_model = {model: 0 for model in models}
    parse_fail_attempts_by_model = {model: 0 for model in models}
    latest = {}
    for rec in records:
        model = rec.get("judge")
        if model not in attempts_by_model:
            continue
        attempts_by_model[model] += 1
        if rec.get("verdict") == "parse_fail":
            parse_fail_attempts_by_model[model] += 1
        latest[(model, rec.get("item_id"))] = rec
    final_parse_fail_by_model = {model: 0 for model in models}
    final_valid_by_model = {model: 0 for model in models}
    for (model, _item_id), rec in latest.items():
        if rec.get("verdict") == "parse_fail":
            final_parse_fail_by_model[model] += 1
        elif rec.get("verdict") in {"true", "false"}:
            final_valid_by_model[model] += 1
    return {
        "attempts_by_model": attempts_by_model,
        "parse_fail_attempts_by_model": parse_fail_attempts_by_model,
        "final_valid_by_model": final_valid_by_model,
        "final_parse_fail_by_model": final_parse_fail_by_model,
        "total_parse_fail_attempts": sum(parse_fail_attempts_by_model.values()),
        "total_final_parse_fail": sum(final_parse_fail_by_model.values()),
    }


def call_with_retries(model, item, retries):
    attempts = []
    for attempt in range(1, retries + 2):
        if model == "qwen/qwen3-32b":
            prompt = _build_statement_prompt(item["statement"]) + "\n\n/no_think"
            try:
                response = _call_openrouter(model, prompt, max_tokens=256, temperature=0.0)
                message = response["choices"][0]["message"].get("content") or ""
                usage = response.get("usage", {})
                verdict = _parse_truth(message)
                raw_response = message
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
            except Exception as exc:
                verdict = "parse_fail"
                raw_response = f"ERROR: {exc}"
                prompt_tokens = 0
                completion_tokens = 0
        else:
            result = judge_statement(model, item["statement"])
            verdict = result.verdict
            raw_response = result.raw_response
            prompt_tokens = result.prompt_tokens
            completion_tokens = result.completion_tokens
        rec = {
            "judge": model,
            "item_id": item["id"],
            "mode": MODE,
            "prior": None,
            "verdict": verdict,
            "raw_response": raw_response,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "attempt": attempt,
        }
        attempts.append(rec)
        if verdict in {"true", "false"}:
            break
    return attempts


def ensure_verdicts(items, cache, output_cache, run_missing, retries, workers):
    raw_parse_fail = {model: 0 for model in MODELS_TO_ENSURE}
    retried = {model: 0 for model in MODELS_TO_ENSURE}
    final_parse_fail = {model: 0 for model in MODELS_TO_ENSURE}
    missing = []
    to_call = []

    for item in items:
        for model in MODELS_TO_ENSURE:
            key = (model, item["id"])
            rec = cache.get(key)
            if rec and rec.get("verdict") in {"true", "false"}:
                continue
            if rec and rec.get("verdict") == "parse_fail":
                raw_parse_fail[model] += 1
            if not run_missing:
                missing.append({"item_id": item["id"], "judge": model})
                continue
            to_call.append((model, item))

    if not to_call:
        return {
            "raw_parse_fail_by_model": raw_parse_fail,
            "retried_by_model": retried,
            "final_parse_fail_by_model": final_parse_fail,
            "missing_items": missing,
        }

    write_lock = Lock()

    def run_one(model_item):
        model, item = model_item
        return model, item, call_with_retries(model, item, retries)

    if workers <= 1:
        iterator = (run_one(model_item) for model_item in to_call)
    else:
        pool = ThreadPoolExecutor(max_workers=workers)
        futures = [pool.submit(run_one, model_item) for model_item in to_call]
        iterator = (future.result() for future in as_completed(futures))

    completed = 0
    try:
        for model, item, attempts in iterator:
            if len(attempts) > 1:
                retried[model] += len(attempts) - 1
            with write_lock:
                for attempt in attempts:
                    append_jsonl(output_cache, attempt)
            best = attempts[-1]
            cache[(model, item["id"])] = best
            if best["verdict"] == "parse_fail":
                final_parse_fail[model] += 1
            completed += 1
            if completed % 25 == 0 or completed == len(to_call):
                print(
                    f"[strong_slice] completed {completed}/{len(to_call)} missing calls",
                    flush=True,
                )
    finally:
        if workers > 1:
            pool.shutdown(wait=True, cancel_futures=False)

    return {
        "raw_parse_fail_by_model": raw_parse_fail,
        "retried_by_model": retried,
        "final_parse_fail_by_model": final_parse_fail,
        "missing_items": missing,
    }


def pearson(x, y):
    n = len(x)
    if n == 0:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sx = sum((a - mx) ** 2 for a in x) ** 0.5
    sy = sum((b - my) ** 2 for b in y) ** 0.5
    return num / (sx * sy) if sx > 0 and sy > 0 else 0.0


def mean_pair(miss, models, idx):
    vals = []
    for a in range(len(models)):
        for b in range(a + 1, len(models)):
            vals.append(pearson(
                [miss[models[a]][i] for i in idx],
                [miss[models[b]][i] for i in idx],
            ))
    return sum(vals) / len(vals) if vals else 0.0


def pairwise_corrs(miss, models, idx):
    rows = {}
    for a in range(len(models)):
        for b in range(a + 1, len(models)):
            label = f"{short(models[a])}__{short(models[b])}"
            rows[label] = pearson(
                [miss[models[a]][i] for i in idx],
                [miss[models[b]][i] for i in idx],
            )
    return rows


def all3(miss, models, idx):
    return sum(1 for i in idx if all(miss[m][i] for m in models)) / len(idx) if idx else 0.0


def majority_accept(verdicts):
    return sum(1 for verdict in verdicts if verdict == "true") >= 2


def perm_lift(miss, models, idx, seed, permutations):
    obs = all3(miss, models, idx)
    rng = random.Random(seed)
    nulls = []
    for _ in range(permutations):
        shuffled = {}
        for model in models:
            vals = [miss[model][i] for i in idx]
            rng.shuffle(vals)
            shuffled[model] = vals
        nulls.append(
            sum(1 for k in range(len(idx)) if all(shuffled[m][k] for m in models)) / len(idx)
        )
    null_mean = sum(nulls) / len(nulls) if nulls else 0.0
    if null_mean > 0:
        lift = obs / null_mean
    elif obs == 0:
        lift = 0.0
    else:
        lift = math.inf
    p_value = (sum(1 for value in nulls if value >= obs) + 1) / (len(nulls) + 1) if nulls else 1.0
    return {
        "false_consensus_rate": obs,
        "perm_null": null_mean,
        "false_consensus_lift": lift,
        "p_value": p_value,
    }


def panel_metrics(items, cache, models, seed, permutations):
    idx_corrupt = [i for i, item in enumerate(items) if item["is_corrupted"]]
    idx_clean = [i for i, item in enumerate(items) if not item["is_corrupted"]]

    verdicts = {
        model: [cache.get((model, item["id"]), {}).get("verdict", "parse_fail") for item in items]
        for model in models
    }
    miss = {
        model: [
            1 if (items[i]["is_corrupted"] and verdicts[model][i] == "true") else 0
            for i in range(len(items))
        ]
        for model in models
    }
    per_judge = {}
    for model in models:
        corrupt_fn = sum(miss[model][i] for i in idx_corrupt) / len(idx_corrupt)
        clean_accept = sum(1 for i in idx_clean if verdicts[model][i] == "true") / len(idx_clean)
        parse_fail = sum(1 for v in verdicts[model] if v == "parse_fail")
        per_judge[model] = {
            "fn_rate_corrupted": corrupt_fn,
            "true_accept_rate_clean": clean_accept,
            "parse_fail_count": parse_fail,
        }

    majority_false_accept = sum(
        1 for i in idx_corrupt
        if majority_accept([verdicts[model][i] for model in models])
    ) / len(idx_corrupt)
    majority_true_accept = sum(
        1 for i in idx_clean
        if majority_accept([verdicts[model][i] for model in models])
    ) / len(idx_clean)

    return {
        "models": models,
        "n_clean": len(idx_clean),
        "n_corrupt": len(idx_corrupt),
        "per_judge": per_judge,
        "fn_only_corr": mean_pair(miss, models, idx_corrupt),
        "pairwise_fn_corr": pairwise_corrs(miss, models, idx_corrupt),
        "rf_majority_false_accept_rate": majority_false_accept,
        "rf_majority_true_accept_rate": majority_true_accept,
        **perm_lift(miss, models, idx_corrupt, seed, permutations),
    }


def markdown(summary):
    lines = [
        "# Strong Judge Slice v1",
        "",
        "Supplementary robustness analysis only. Results are not included in primary guardrail evaluation tables.",
        "",
        "Primary question: Do stronger reference-free judges reduce false consensus risk?",
        "",
        "## Panel Metrics",
        "",
        "| Panel | FN Corr | False Consensus | Lift | p-value | RF Majority False Accept | RF Majority True Accept |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for key, row in summary["panels"].items():
        lines.append(
            f"| {key} | {row['fn_only_corr']:.3f} | "
            f"{row['false_consensus_rate']:.3f} | "
            f"{row['false_consensus_lift']:.3f} | "
            f"{row['p_value']:.4f} | "
            f"{row['rf_majority_false_accept_rate']:.3f} | "
            f"{row['rf_majority_true_accept_rate']:.3f} |"
        )

    lines += [
        "",
        "## Per-judge Metrics",
        "",
        "| Panel | Judge | FN Rate (Corrupted) | True Accept (Clean) | Parse Fail |",
        "|---|---|---:|---:|---:|",
    ]
    for panel, row in summary["panels"].items():
        for model, metrics in row["per_judge"].items():
            lines.append(
                f"| {panel} | {short(model)} | "
                f"{metrics['fn_rate_corrupted']:.3f} | "
                f"{metrics['true_accept_rate_clean']:.3f} | "
                f"{metrics['parse_fail_count']} |"
            )
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-missing", action="store_true")
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--permutations", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=20260609)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--data", default="data/frozen/number_v3/number_corruption_pool_v3_n300.jsonl")
    ap.add_argument("--primary-rf", default="results/frozen/number_v3/number_corruption_pool_v3_n300_rf.jsonl")
    ap.add_argument("--capability-rf", default="results/frozen/strong_judge_slice_v1/number_v3_capability_rf.jsonl")
    ap.add_argument("--out", default="results/frozen/strong_judge_slice_v1/summary.json")
    ap.add_argument("--md-out", default="results/frozen/strong_judge_slice_v1/summary.md")
    args = ap.parse_args()

    if args.run_missing and not os.environ.get("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    items = load_jsonl(ROOT / args.data)
    if args.limit:
        items = items[:args.limit]

    capability_path = ROOT / args.capability_rf
    cache, records = load_cache([ROOT / args.primary_rf, capability_path])

    if args.preflight:
        if not args.run_missing:
            print("ERROR: --preflight requires --run-missing.", file=sys.stderr)
            sys.exit(1)
        item = next((it for it in items if it["is_corrupted"]), items[0])
        results = []
        for model in MODELS_TO_ENSURE:
            rec = cache.get((model, item["id"]))
            if rec and rec.get("verdict") in {"true", "false"}:
                results.append({
                    "judge": model,
                    "item_id": item["id"],
                    "verdict": rec["verdict"],
                    "cached": True,
                })
                continue
            attempts = call_with_retries(model, item, args.retries)
            for attempt in attempts:
                append_jsonl(capability_path, attempt)
            results.append({
                "judge": model,
                "item_id": item["id"],
                "verdict": attempts[-1]["verdict"],
                "cached": False,
                "attempts": len(attempts),
            })
        print(json.dumps({"preflight": results}, indent=2, ensure_ascii=False))
        if any(row["verdict"] not in {"true", "false"} for row in results):
            sys.exit(1)
        return

    call_status = ensure_verdicts(
        items, cache, capability_path, args.run_missing, args.retries, args.workers
    )
    if call_status["missing_items"]:
        status = "missing_model_calls"
    elif sum(call_status["final_parse_fail_by_model"].values()) > 0:
        status = "parse_fail_after_retry"
    else:
        status = "complete"

    panels = {
        "capability_slice": panel_metrics(
            items, cache, CAPABILITY_SLICE, args.seed, args.permutations
        ),
    }
    _, final_records = load_cache([ROOT / args.primary_rf, capability_path])
    summary = {
        "artifact_type": "robustness_evaluation",
        "stage": "evaluation",
        "mode": "strong_judge_slice_v1",
        "status": status,
        "primary_table_inclusion": False,
        "reporting_role": "Robustness evidence only; not included in primary guardrail evaluation tables.",
        "primary_question": "Do stronger reference-free judges reduce false consensus risk?",
        "source_frame": args.data,
        "oracle_used": False,
        "gold_fallback_used": False,
        "run_missing": args.run_missing,
        "retries": args.retries,
        "workers": args.workers,
        "seed": args.seed,
        "permutations": args.permutations,
        "judge_pool": {
            "capability_slice": CAPABILITY_SLICE,
            "reused_reference_free_models": REUSED_REFERENCE_FREE_MODELS,
            "new_model_calls": NEW_MODEL_CALLS,
            "reused_cache_parse_fail_repair_enabled": True,
        },
        "call_status": call_status,
        "cache_validation": cache_validation(final_records, CAPABILITY_SLICE),
        "panels": panels,
        "success_criteria": {
            "threshold_used": False,
            "statement": "No threshold is used to declare success or failure. All outcomes are considered informative.",
        },
        "interpretation_rules": {
            "risk_decreases_with_capability": "Evidence for capability-dependent risk.",
            "risk_remains_high": "Evidence that stronger reference-free judges do not eliminate the problem.",
            "mixed": "Report as inconclusive.",
        },
        "non_use_constraints": [
            "Does not affect risk threshold selection.",
            "Does not affect policy definition.",
            "Does not affect routing logic.",
            "Does not affect main results.",
        ],
    }

    out = ROOT / args.out
    md_out = ROOT / args.md_out
    out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    md_out.write_text(markdown(summary))
    print(json.dumps({"json": args.out, "markdown": args.md_out, "status": status}, indent=2))
    print()
    print(markdown(summary))
    if status != "complete":
        sys.exit(1)


if __name__ == "__main__":
    main()
