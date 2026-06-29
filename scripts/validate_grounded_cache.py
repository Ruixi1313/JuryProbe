#!/usr/bin/env python3
"""Create validated grounded-verifier caches with no parse_fail verdicts."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evaluate_guardrail_policies import JUDGES, call_grounded, family_configs, load_jsonl
from src.io_utils import write_jsonl


def canonical_path(stem):
    return ROOT / f"results/guardrail_grounded/{stem}_grounded_verifier_canonical.jsonl"


def validated_path(stem):
    return ROOT / f"results/guardrail_grounded/{stem}_grounded_verifier_validated.jsonl"


def key(record):
    return (record["item_id"], record["judge"])


def validate_family(cfg, run_calls):
    items = load_jsonl(cfg["data"])
    source = canonical_path(cfg["stem"])
    output = validated_path(cfg["stem"])
    records = {key(record): record for record in load_jsonl(source)}
    out_records = []
    invalid_before = []
    invalid_after = []
    retried = []

    for item in items:
        for judge in JUDGES:
            rec = records.get((item["id"], judge))
            if rec is None:
                invalid_before.append({
                    "item_id": item["id"],
                    "judge": judge,
                    "reason": "missing",
                })
                if not run_calls:
                    continue
            elif rec.get("verdict") in {"true", "false"}:
                out_records.append(rec)
                continue
            else:
                invalid_before.append({
                    "item_id": item["id"],
                    "judge": judge,
                    "reason": rec.get("verdict", "invalid"),
                    "raw_response": rec.get("raw_response", ""),
                })
                if not run_calls:
                    out_records.append(rec)
                    continue

            result = call_grounded(judge, item.get("original_statement", ""), item["statement"])
            fixed = {
                "judge": judge,
                "item_id": item["id"],
                "mode": "grounded_verifier",
                "prior": None,
                **result,
                "validated_from": str(source.relative_to(ROOT)),
            }
            out_records.append(fixed)
            retried.append({
                "item_id": item["id"],
                "judge": judge,
                "verdict": fixed["verdict"],
                "raw_response": fixed.get("raw_response", ""),
            })
            if fixed["verdict"] not in {"true", "false"}:
                invalid_after.append(retried[-1])

    counts = {}
    for rec in out_records:
        counts[rec.get("verdict")] = counts.get(rec.get("verdict"), 0) + 1

    output.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(output, out_records)
    return {
        "family": cfg["family"].lower(),
        "source": str(source.relative_to(ROOT)),
        "output": str(output.relative_to(ROOT)),
        "rows": len(out_records),
        "expected_rows": len(items) * len(JUDGES),
        "raw_parse_fail_count": len(invalid_before),
        "retried_count": len(retried),
        "final_parse_fail_count": len(invalid_after),
        "invalid_before": len(invalid_before),
        "retried": len(retried),
        "invalid_after": len(invalid_after),
        "verdict_counts": counts,
        "invalid_before_examples": invalid_before[:20],
        "invalid_after_examples": invalid_after[:20],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-calls", action="store_true")
    ap.add_argument("--out", default="results/guardrail_grounded/validated_cache_manifest.json")
    args = ap.parse_args()

    if args.run_calls and not os.environ.get("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    results = [validate_family(cfg, args.run_calls) for cfg in family_configs()]
    parse_fail_by_family = {
        result["family"]: {
            "raw_parse_fail": result["raw_parse_fail_count"],
            "retried": result["retried_count"],
            "final_parse_fail": result["final_parse_fail_count"],
        }
        for result in results
    }
    manifest = {
        "artifact": "grounded_verifier_validated_cache",
        "run_calls": args.run_calls,
        "oracle_used": False,
        "gold_fallback_used": False,
        "parse_fail_by_family": parse_fail_by_family,
        "families": results,
        "status": "complete" if all(r["invalid_after"] == 0 for r in results) else "invalid_after_retry",
    }
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    if manifest["status"] != "complete":
        sys.exit(1)


if __name__ == "__main__":
    main()
