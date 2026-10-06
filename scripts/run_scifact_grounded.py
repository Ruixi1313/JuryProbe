#!/usr/bin/env python3
"""Grounded judging of SciFact claims with benchmark-annotated evidence.

SciFact references come from published scientific abstracts rather than
minimal edits of the claims. This is a trusted-reference diagnostic of
individual errors and unanimous false consensus, not causal isolation.

Same 3-judge panel and the exact D.1 grounded prompt as scripts/foil_grounded.py;
only the reference source differs (SciFact evidence sentence, not a minimal pair).
Resumable: verdicts cached to results/scifact_natural_n190_grounded_rf.jsonl
(mode "grounded"). Reference-free comparison numbers are read from the existing
results/scifact_natural_n190_rf.jsonl cache; no RF re-judging.

Usage:
  python scripts/run_scifact_grounded.py
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections import defaultdict
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

from src.judges import _call_openrouter, _parse_truth  # noqa: E402
from src.io_utils import RawCache, load_jsonl  # noqa: E402

JUDGES = [
    "meta-llama/llama-3.1-8b-instruct",
    "qwen/qwen-2.5-7b-instruct",
    "google/gemma-3-12b-it",
]
MODE = "grounded"


def judge_grounded(model, reference, statement):
    """Exact Appendix D.1 grounded consistency prompt (as in foil_grounded.py)."""
    prompt = (
        "You are verifying a statement against a trusted reference.\n\n"
        f"Reference (trusted, correct): {reference}\n\n"
        f"Statement to check: {statement}\n\n"
        "Is the Statement fully consistent with the Reference? "
        "Answer ONLY 'true' (consistent) or 'false' (it contradicts the reference).\n\n"
        "Your answer:")
    r = _call_openrouter(model, prompt)
    msg = r["choices"][0]["message"]["content"]
    usage = r.get("usage", {})
    return (_parse_truth(msg), msg, usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0))


def pearson(x, y):
    n = len(x)
    if n == 0:
        return 0.0
    mx, my = sum(x) / n, sum(y) / n
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sx = sum((a - mx) ** 2 for a in x) ** 0.5
    sy = sum((b - my) ** 2 for b in y) ** 0.5
    return num / (sx * sy) if sx > 0 and sy > 0 else 0.0


def mean_pairwise(miss):
    js = list(miss.keys())
    vals = [pearson(miss[js[a]], miss[js[b]])
            for a in range(len(js)) for b in range(a + 1, len(js))]
    return sum(vals) / len(vals) if vals else 0.0


def all3_rate(miss, n):
    return sum(1 for i in range(n) if all(miss[j][i] for j in JUDGES)) / n if n else 0.0


def load_rf(path):
    rf = defaultdict(dict)
    for rec in load_jsonl(path):
        if rec.get("mode") not in (None, "reference_free"):
            continue
        rf[rec["item_id"]][rec["judge"]] = rec["verdict"]
    return dict(rf)


def run(items, cache, retry=1):
    total = len(items) * len(JUDGES)
    done = 0
    calls = 0
    ptok = ctok = 0
    for it in items:
        for judge in JUDGES:
            cached = cache.get(judge, it["item_id"], MODE, None)
            if cached is None:
                verdict = "parse_fail"
                raw = ""
                for attempt in range(retry + 1):
                    try:
                        verdict, raw, pt, ct = judge_grounded(
                            judge, it["reference"], it["statement"])
                        ptok += pt
                        ctok += ct
                        calls += 1
                    except Exception as e:  # noqa: BLE001
                        verdict, raw = "parse_fail", f"error:{e}"
                    if verdict != "parse_fail":
                        break
                    time.sleep(1.0)
                cache.put({
                    "judge": judge,
                    "item_id": it["item_id"],
                    "mode": MODE,
                    "prior": None,
                    "verdict": verdict,
                    "raw_response": raw[:200],
                    "is_corrupted": it["is_corrupted"],
                    "reference_word_len": it["reference_word_len"],
                })
            done += 1
            if done % 60 == 0:
                print(f"  {done}/{total} judge calls done "
                      f"(new API calls={calls})", file=sys.stderr)
    return calls, ptok, ctok


def grounded_verdict(cache, item_id, judge):
    rec = cache.get(judge, item_id, MODE, None)
    return rec["verdict"] if rec else "parse_fail"


def analyze(items, cache, rf):
    corrupt = [it for it in items if it["is_corrupted"]]
    clean = [it for it in items if not it["is_corrupted"]]

    # miss = accepts a corrupted (false) claim as true (a false negative)
    def miss_vectors(get_verdict):
        miss = {j: [] for j in JUDGES}
        for it in corrupt:
            for j in JUDGES:
                miss[j].append(1 if get_verdict(it["item_id"], j) == "true" else 0)
        return miss

    g_miss = miss_vectors(lambda iid, j: grounded_verdict(cache, iid, j))
    rf_miss = miss_vectors(lambda iid, j: rf.get(iid, {}).get(j, "parse_fail"))
    n = len(corrupt)

    # accept rate on clean (correct acceptance)
    def accept_rate(get_verdict):
        acc = 0
        tot = len(clean) * len(JUDGES)
        for it in clean:
            for j in JUDGES:
                if get_verdict(it["item_id"], j) == "true":
                    acc += 1
        return acc / tot if tot else 0.0

    def parse_fail_rate(get_verdict):
        pf = 0
        tot = len(items) * len(JUDGES)
        for it in items:
            for j in JUDGES:
                if get_verdict(it["item_id"], j) == "parse_fail":
                    pf += 1
        return pf / tot if tot else 0.0

    g_get = lambda iid, j: grounded_verdict(cache, iid, j)
    rf_get = lambda iid, j: rf.get(iid, {}).get(j, "parse_fail")

    return {
        "n_corrupt": n,
        "n_clean": len(clean),
        "reference_free": {
            "fn_corr": mean_pairwise(rf_miss),
            "all3_false_consensus": all3_rate(rf_miss, n),
            "per_judge_accept_on_corrupt": {
                j: sum(rf_miss[j]) / n for j in JUDGES},
            "clean_true_accept": accept_rate(rf_get),
            "parse_fail_rate": parse_fail_rate(rf_get),
        },
        "grounded": {
            "fn_corr": mean_pairwise(g_miss),
            "all3_false_consensus": all3_rate(g_miss, n),
            "per_judge_accept_on_corrupt": {
                j: sum(g_miss[j]) / n for j in JUDGES},
            "clean_true_accept": accept_rate(g_get),
            "parse_fail_rate": parse_fail_rate(g_get),
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grounded-data", default="data/scifact_natural_n190_grounded.jsonl")
    ap.add_argument("--rf-cache", default="results/scifact_natural_n190_rf.jsonl")
    ap.add_argument("--cache", default="results/scifact_natural_n190_grounded_rf.jsonl")
    ap.add_argument("--out", default="results/scifact_grounded_summary.json")
    args = ap.parse_args()

    items = load_jsonl(ROOT / args.grounded_data)
    cache = RawCache(ROOT / args.cache)
    rf = load_rf(ROOT / args.rf_cache)

    print(f"Grounded judging: {len(items)} items x {len(JUDGES)} judges "
          f"= {len(items) * len(JUDGES)} calls (cached ones skipped)...",
          file=sys.stderr)
    calls, ptok, ctok = run(items, cache)
    print(f"New API calls: {calls} (prompt_tok={ptok}, completion_tok={ctok})",
          file=sys.stderr)

    result = analyze(items, cache, rf)
    result["mode"] = "scifact_grounded_vs_reference_free"
    result["reference_source"] = "SciFact gold evidence sentences (non-minimal-pair, entailment)"
    result["new_api_calls_this_run"] = calls
    result["prompt_tokens_this_run"] = ptok
    result["completion_tokens_this_run"] = ctok
    (ROOT / args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
