#!/usr/bin/env python3
"""A-lite: reference-GROUNDED foil (100 items), the decisive foil-effect test.

The pairwise foil only put two candidates side by side without supplying the
missing KNOWLEDGE, so it was a weak test. Here we give each judge the original
true statement as a trusted REFERENCE and ask whether the (corrupted) statement
is consistent with it. This is the strongest available grounding (the correct
value is essentially in context), so it is an UPPER-BOUND test of the foil effect:

  - If correlation collapses toward 0 with grounding -> a reference decorrelates
    the errors -> reference-free is the dangerous regime -> foil effect real.
  - If correlation persists even with the correct fact in context -> judges
    co-miss even given ground truth -> foil is only an ablation -> go to B
    (typed-corruption generalization).

Matched design: 100 GPT-4o-detectable corrupted items; reference-free numbers for
the SAME 100 are recomputed from cache.

Usage: python scripts/foil_grounded.py [n_corrupt=300] [k=100]
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

from src.judges import _call_openrouter, _parse_truth
from src.io_utils import load_jsonl, RawCache

JUDGES = [
    "meta-llama/llama-3.1-8b-instruct",
    "qwen/qwen-2.5-7b-instruct",
    "google/gemma-3-12b-it",
]
REF_JUDGE = "openai/gpt-4o"
MODE = "grounded_foil"
random.seed(31)


def judge_grounded(model, reference, statement):
    prompt = (
        "You are verifying a statement against a trusted reference.\n\n"
        f"Reference (trusted, correct): {reference}\n\n"
        f"Statement to check: {statement}\n\n"
        "Is the Statement fully consistent with the Reference? "
        "Answer ONLY 'true' (consistent) or 'false' (it contradicts the reference).\n\n"
        "Your answer:")
    try:
        r = _call_openrouter(model, prompt)
        return _parse_truth(r["choices"][0]["message"]["content"])
    except Exception:
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


def mean_pairwise(err):
    js = list(err.keys())
    vals = [pearson(err[js[a]], err[js[b]])
            for a in range(len(js)) for b in range(a + 1, len(js))]
    return sum(vals) / len(vals) if vals else 0.0


def all3(err, m):
    return sum(1 for i in range(m) if all(err[j][i] for j in JUDGES)) / m if m else 0.0


def perm(err, m, B=3000):
    obs = all3(err, m)
    ps = []
    for _ in range(B):
        sh = {}
        for j in JUDGES:
            v = err[j][:]
            random.shuffle(v)
            sh[j] = v
        ps.append(all3(sh, m))
    pm = sum(ps) / len(ps)
    return obs, pm, (obs / pm if pm > 0 else float("inf")), (sum(1 for v in ps if v >= obs) + 1) / (len(ps) + 1)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    data = ROOT / "data" / f"number_corruption_n{n}.jsonl"
    rf_cache = RawCache(ROOT / "results" / f"mvp_n{n}_raw_outputs.jsonl")
    gpt_cache = RawCache(ROOT / "results" / f"n{n}_gpt4o_difficulty.jsonl")
    g_cache = RawCache(ROOT / "results" / f"grounded_n{n}_raw.jsonl")

    corrupted = [it for it in load_jsonl(data)
                 if it["is_corrupted"] and it.get("original_statement")]
    # prefer GPT-4o-detectable, matched to the decisive subset
    detect = [it for it in corrupted
              if (c := gpt_cache.get(REF_JUDGE, it["id"], "reference_free", None))
              and c["verdict"] == it["gold"]]
    pool = detect if len(detect) >= k else corrupted
    items = pool[:k]
    m = len(items)
    print(f"A-lite grounded foil on {m} matched (GPT-4o-detectable) corrupted items")

    rf_err = {j: [] for j in JUDGES}    # reference-free (from cache)
    g_err = {j: [] for j in JUDGES}     # grounded (this run)
    for it in items:
        for j in JUDGES:
            rc = rf_cache.get(j, it["id"], "reference_free", None)
            rf_err[j].append(0 if (rc and rc["verdict"] == it["gold"]) else 1)
            gc = g_cache.get(j, it["id"], MODE, None)
            if gc is None:
                v = judge_grounded(j, it["original_statement"], it["statement"])
                g_cache.put({"judge": j, "item_id": it["id"], "mode": MODE,
                             "prior": None, "verdict": v, "raw_response": "",
                             "prompt_tokens": 0, "completion_tokens": 0})
            else:
                v = gc["verdict"]
            # corrupted gold = "false" (contradicts reference); error = said "true"
            g_err[j].append(1 if v == "true" else 0)

    print("\n--- per-judge false-negative rate (miss the corruption) ---")
    for j in JUDGES:
        print(f"  {j.split('/')[-1]:<22} reference-free={sum(rf_err[j])/m:.3f}   "
              f"grounded={sum(g_err[j])/m:.3f}")

    rf_c, g_c = mean_pairwise(rf_err), mean_pairwise(g_err)
    rf_o, rf_pm, rf_l, rf_p = perm(rf_err, m)
    g_o, g_pm, g_l, g_p = perm(g_err, m)

    print(f"\n{'':22}{'reference-free':>16}{'grounded':>16}")
    print(f"  {'mean error corr':<20}{rf_c:>16.3f}{g_c:>16.3f}")
    print(f"  {'all-3 false cons.':<20}{rf_o:>16.3f}{g_o:>16.3f}")
    print(f"  {'residual lift':<20}{rf_l:>15.2f}x{g_l:>15.2f}x")
    print(f"  {'perm p':<20}{rf_p:>16.4f}{g_p:>16.4f}")

    collapsed = (g_c < 0.10 and g_l < 1.3)
    verdict = ("FOIL EFFECT REAL (grounding collapses correlation) -> novelty revives, C5"
               if collapsed else
               "foil = ablation (correlation persists WITH ground truth in context) -> go to B")
    print(f"\n  => {verdict}")
    (ROOT / "results" / f"grounded_n{n}_summary.json").write_text(json.dumps({
        "k": m, "reference_free": {"corr": rf_c, "all3": rf_o, "lift": rf_l},
        "grounded": {"corr": g_c, "all3": g_o, "lift": g_l, "perm_p": g_p},
        "collapsed": collapsed, "verdict": verdict}, indent=2))
    print(f"\nWrote results/grounded_n{n}_summary.json")


if __name__ == "__main__":
    main()
