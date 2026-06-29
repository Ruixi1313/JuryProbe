#!/usr/bin/env python3
"""Foil-effect experiment (C5): same facts, reference vs reference-free.

Reference-free (already run): judge sees ONE statement, says true/false. Judges
co-miss corruptions (residual all-3 lift 3.3x on the GPT-4o-detectable subset).

Foil/pairwise (this script): judge sees BOTH the original (true) and corrupted
(false) versions of the SAME fact, randomized A/B, and picks which is factually
correct. The reference (the other candidate) is now present. If the correlation
collapses toward 0 and all-3 unanimous-wrong drops toward the independence
baseline, the correlated failure is TRIGGERED by the absence of a reference --
the load-bearing distinction from Kohli (whose tasks all had a foil).

Reuses the 300 corrupted items (each has original_statement + corrupted
statement) and the cached GPT-4o difficulty oracle for the matched detectable
subset. Same 3 small judges.

Usage: python scripts/foil_mode.py [n_corrupt=300]
"""
from __future__ import annotations

import json
import os
import random
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

from src.judges import _call_openrouter, _parse_verdict
from src.io_utils import load_jsonl, RawCache

JUDGES = [
    "meta-llama/llama-3.1-8b-instruct",
    "qwen/qwen-2.5-7b-instruct",
    "google/gemma-3-12b-it",
]
REF_JUDGE = "openai/gpt-4o"
MODE = "pairwise_foil"
random.seed(23)


def judge_pair_factual(model, a, b):
    prompt = (
        "You are checking which of two statements is factually correct.\n\n"
        f"Statement A: {a}\n\nStatement B: {b}\n\n"
        "Exactly one is factually correct. Which one? Respond with ONLY 'A' or 'B'.\n\n"
        "Your answer:")
    try:
        r = _call_openrouter(model, prompt)
        return _parse_verdict(r["choices"][0]["message"]["content"])
    except Exception as e:
        return "parse_fail"


def pearson(x, y):
    n = len(x)
    if n == 0:
        return 0.0
    mx, my = sum(x) / n, sum(y) / n
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sx = sum((a - mx) ** 2 for a in x) ** 0.5
    sy = sum((b - my) ** 2 for b in y) ** 0.5
    return num / (sx * sy) if sx > 0 and sy > 0 else 0.0


def mean_pairwise(err, idx):
    js = list(err.keys())
    vals = []
    for a in range(len(js)):
        for b in range(a + 1, len(js)):
            vals.append(pearson([err[js[a]][i] for i in idx],
                                [err[js[b]][i] for i in idx]))
    return sum(vals) / len(vals) if vals else 0.0


def all3_wrong(err, idx):
    if not idx:
        return 0.0
    return sum(1 for i in idx if all(err[j][i] for j in JUDGES)) / len(idx)


def perm_residual(err, idx, B=3000):
    obs = all3_wrong(err, idx)
    perms = []
    for _ in range(B):
        sh = {}
        for j in JUDGES:
            vals = [err[j][i] for i in idx]
            random.shuffle(vals)
            sh[j] = vals
        perms.append(sum(1 for k in range(len(idx)) if all(sh[j][k] for j in JUDGES)) / len(idx))
    pm = sum(perms) / len(perms)
    p = (sum(1 for v in perms if v >= obs) + 1) / (len(perms) + 1)
    return obs, pm, (obs / pm if pm > 0 else float("inf")), p


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    data = ROOT / "data" / f"number_corruption_n{n}.jsonl"
    cache = RawCache(ROOT / "results" / f"foil_n{n}_raw.jsonl")
    gpt_cache = RawCache(ROOT / "results" / f"n{n}_gpt4o_difficulty.jsonl")
    items = [it for it in load_jsonl(data) if it["is_corrupted"]]
    print(f"{len(items)} corrupted facts -> pairwise foil (original vs corrupted)")

    # assign A/B per item (which letter holds the CORRECT/original statement)
    err = {j: [] for j in JUDGES}
    detectable = []
    for it in items:
        orig = it.get("original_statement") or ""
        corr = it["statement"]
        if not orig:
            for j in JUDGES:
                err[j].append(0)
            detectable.append(False)
            continue
        gold_letter = "A" if random.random() < 0.5 else "B"
        a_txt, b_txt = (orig, corr) if gold_letter == "A" else (corr, orig)
        for j in JUDGES:
            c = cache.get(j, it["id"], MODE, None)
            if c is None:
                v = judge_pair_factual(j, a_txt, b_txt)
                cache.put({"judge": j, "item_id": it["id"], "mode": MODE,
                           "prior": None, "verdict": v, "gold_letter": gold_letter,
                           "raw_response": "", "prompt_tokens": 0, "completion_tokens": 0})
            else:
                v = c["verdict"]
                gold_letter = c.get("gold_letter", gold_letter)
            err[j].append(0 if v == gold_letter else 1)
        gc = gpt_cache.get(REF_JUDGE, it["id"], MODE.replace("pairwise_foil", "reference_free"), None)
        detectable.append(bool(gc) and gc["verdict"] == it["gold"])

    all_idx = list(range(len(items)))
    det_idx = [i for i in all_idx if detectable[i]]

    print("\n--- Foil (pairwise) per-judge error rate (picked corrupted) ---")
    for j in JUDGES:
        er = sum(err[j]) / len(err[j])
        print(f"  {j.split('/')[-1]:<22} err={er:.3f}")

    for label, idx in [("ALL corrupted", all_idx),
                       ("GPT-4o-detectable (matched)", det_idx)]:
        mc = mean_pairwise(err, idx)
        obs, pm, lift, p = perm_residual(err, idx)
        print(f"\n[{label}] n={len(idx)}")
        print(f"  mean pairwise error corr = {mc:.3f}")
        print(f"  all-3 unanimous-wrong obs={obs:.3f}  perm-null={pm:.3f}  "
              f"residual-lift={lift:.2f}x  p={p:.4f}")

    print("\n--- COMPARISON (reference-free vs foil, detectable subset) ---")
    print("  reference-free: FN-corr 0.361 | all-3 FC 0.140 | residual-lift 3.33x")
    mc = mean_pairwise(err, det_idx)
    obs, pm, lift, p = perm_residual(err, det_idx)
    print(f"  foil/pairwise : corr {mc:.3f} | all-3 {obs:.3f} | residual-lift {lift:.2f}x (p={p:.4f})")
    verdict = ("FOIL EFFECT STRONG -> C5 load-bearing"
               if (mc < 0.15 and lift < 1.8) else
               "foil effect weak -> keep reference-free as main, foil as ablation")
    print(f"\n  => {verdict}")
    (ROOT / "results" / f"foil_n{n}_summary.json").write_text(json.dumps({
        "n": len(items), "n_detectable": len(det_idx),
        "foil_mean_corr_detectable": mean_pairwise(err, det_idx),
        "foil_all3_detectable": all3_wrong(err, det_idx),
        "per_judge_err": {j: sum(err[j]) / len(err[j]) for j in JUDGES},
        "verdict": verdict}, indent=2))
    print(f"\nWrote results/foil_n{n}_summary.json")


if __name__ == "__main__":
    main()
