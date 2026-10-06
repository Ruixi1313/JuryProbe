#!/usr/bin/env python3
"""Build the FEVER-REFUTES natural low-risk control dataset.

Purpose: a *natural* (non-synthetic) counterpart to the Self-Contained
Contradiction Control. Clean claims are FEVER SUPPORTS; corrupted claims are
FEVER REFUTES, i.e. naturally occurring false claims written by FEVER
annotators, not template corruptions of true claims.

Design rules (pre-specified, label-blind, symmetric):
  1. Both sides pass the identical local_atomic_candidate filter used to build
     master_claim_pool_v1 (6-35 words, no '?'/';', at most one '.', no hedge
     terms). No other content filter is applied to either side.
  2. Global dedupe by exact claim text across both labels.
  3. REFUTES side is sampled first (fixed seed); the SUPPORTS side is then
     sampled to match the REFUTES length-bin distribution exactly, so any
     panel-behavior difference is not driven by claim length.
  4. No model participates in item selection.

Output: data/fever_refutes_control_n300.jsonl (300 clean + 300 corrupted),
schema-compatible with entity_corruption_pool_v4_n300.jsonl so it plugs
directly into scripts/evaluate_low_risk_control_rf.py.

Usage (requires network access to fever.ai):
  python scripts/build_fever_refutes_control.py --seed 42
"""
from __future__ import annotations

import argparse
import json
import random
import re
import ssl
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

try:
    import certifi
    SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL = ssl.create_default_context()

ROOT = Path(__file__).resolve().parents[1]
FEVER_URL = "https://fever.ai/download/fever/train.jsonl"

# Identical to build_fever_claim_pool.py (pre-specified there; reused verbatim).
HEDGE_RE = re.compile(
    r"\b(about|approximately|approx\.?|around|roughly|nearly|almost|"
    r"over|under|more than|less than|at least|at most|up to|between|from)\b",
    re.IGNORECASE,
)


def length_bin(n_words: int) -> str:
    if n_words <= 10:
        return "short"
    if n_words <= 18:
        return "medium"
    return "long"


def local_atomic_candidate(claim: str) -> bool:
    words = claim.split()
    if len(words) < 6 or len(words) > 35:
        return False
    if claim.count("?") or claim.count(";"):
        return False
    if claim.count(".") > 1:
        return False
    if HEDGE_RE.search(claim):
        return False
    return True


def stream_fever():
    req = urllib.request.Request(FEVER_URL, headers={"User-Agent": "juryprobe/0.1"})
    with urllib.request.urlopen(req, timeout=60, context=SSL) as resp:
        for raw in resp:
            try:
                yield json.loads(raw.decode("utf-8"))
            except Exception:
                continue


def collect(max_scan: int = 0):
    """Single pass; identical label-blind filters applied to both labels."""
    attrition = Counter()
    seen = set()
    by_label = {"SUPPORTS": [], "REFUTES": []}
    for row in stream_fever():
        attrition["fever_rows_scanned"] += 1
        if max_scan and attrition["fever_rows_scanned"] > max_scan:
            break
        label = str(row.get("label", "")).upper()
        if label not in by_label:
            attrition["other_label"] += 1
            continue
        claim = (row.get("claim") or "").strip()
        if not claim:
            attrition["empty_claim"] += 1
            continue
        if claim in seen:
            attrition["duplicate_claim"] += 1
            continue
        seen.add(claim)
        if not local_atomic_candidate(claim):
            attrition[f"local_atomic_reject_{label.lower()}"] += 1
            continue
        attrition[f"local_atomic_pass_{label.lower()}"] += 1
        by_label[label].append({"fever_id": row.get("id"), "claim": claim})
    return by_label, attrition


def sample_matched(by_label, n_per_side, seed):
    rng = random.Random(seed)
    refutes_pool = list(by_label["REFUTES"])
    rng.shuffle(refutes_pool)
    refutes = refutes_pool[:n_per_side]
    if len(refutes) < n_per_side:
        raise SystemExit(f"Only {len(refutes)} REFUTES candidates after filters; "
                         f"need {n_per_side}.")

    target = Counter(length_bin(len(r["claim"].split())) for r in refutes)
    supports_by_bin = defaultdict(list)
    for r in by_label["SUPPORTS"]:
        supports_by_bin[length_bin(len(r["claim"].split()))].append(r)
    supports = []
    for b, k in sorted(target.items()):
        pool = supports_by_bin[b]
        if len(pool) < k:
            raise SystemExit(f"SUPPORTS pool has {len(pool)} '{b}' claims; need {k}.")
        rng.shuffle(pool)
        supports.extend(pool[:k])
    rng.shuffle(supports)
    return supports, refutes


def make_item(rec, idx, is_corrupted):
    claim = rec["claim"]
    return {
        "statement": claim,
        "gold": "false" if is_corrupted else "true",
        "is_corrupted": is_corrupted,
        "kind": "fever_refutes",
        "pool_version": "v1",
        "source_claim_id": f"fever_{rec['fever_id']}",
        "fever_id": rec["fever_id"],
        "original_statement": claim,
        "fever_label": "REFUTES" if is_corrupted else "SUPPORTS",
        "length_bin": length_bin(len(claim.split())),
        "id": f"fevref_{idx:04d}",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n-per-side", type=int, default=300)
    ap.add_argument("--max-scan", type=int, default=0,
                    help="0 means scan the full FEVER stream.")
    ap.add_argument("--out", default="data/fever_refutes_control_n300.jsonl")
    args = ap.parse_args()

    by_label, attrition = collect(args.max_scan)
    supports, refutes = sample_matched(by_label, args.n_per_side, args.seed)

    items = []
    for i, rec in enumerate(supports):
        items.append(make_item(rec, i + 1, is_corrupted=False))
    for j, rec in enumerate(refutes):
        items.append(make_item(rec, args.n_per_side + j + 1, is_corrupted=True))

    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    manifest = {
        "dataset": "fever_refutes_control",
        "version": "v1",
        "seed": args.seed,
        "n_clean": len(supports),
        "n_corrupted": len(refutes),
        "design": {
            "clean_source": "FEVER train SUPPORTS",
            "corrupted_source": "FEVER train REFUTES (natural false claims, "
                                "no synthetic corruption)",
            "filters": "identical label-blind local_atomic filter on both "
                       "sides (6-35 words, no ?/;, <=1 period, no hedge terms); "
                       "global dedupe by claim text",
            "matching": "SUPPORTS sampled to match REFUTES length-bin "
                        "distribution exactly",
            "model_in_selection": False,
        },
        "length_bins": dict(Counter(i["length_bin"] for i in items
                                    if i["is_corrupted"])),
        "attrition": dict(attrition),
        "output": str(out_path.relative_to(ROOT)),
    }
    manifest_path = out_path.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
