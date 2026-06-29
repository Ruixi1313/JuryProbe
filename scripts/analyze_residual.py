#!/usr/bin/env python3
"""Difficulty-controlled residual analysis for the N=300 reference-free run.

The raw all-3 false-consensus lift is confounded by shared item DIFFICULTY:
if a fact is obscure, all small judges miss the corruption because none KNOW it
(shared ignorance), not because of a shared BIAS. Following Kohli (2026), we
separate the two with a held-out strong judge (GPT-4o, NOT in the jury) as the
difficulty signal, then a within-stratum permutation test for the residual.

Decisive question: on corrupted items that GPT-4o DETECTS (verifiable, not just
obscure) AND where the small judges are individually competent, do the small
judges still co-miss the corruption above the independence baseline?

Reuses cached small-judge verdicts (results/mvp_n300_raw_outputs.jsonl); adds one
held-out GPT-4o reference-free pass (cached).

Usage: python scripts/analyze_residual.py [n_corrupt=300]
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

from src.judges import judge_statement
from src.io_utils import load_jsonl, RawCache

JUDGES = [
    "meta-llama/llama-3.1-8b-instruct",
    "qwen/qwen-2.5-7b-instruct",
    "google/gemma-3-12b-it",
]
REF_JUDGE = "openai/gpt-4o"          # held-out difficulty oracle, NOT in jury
MODE = "reference_free"
random.seed(11)


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


def ci(xs, lo=2.5, hi=97.5):
    s = sorted(v for v in xs if v is not None)
    if not s:
        return (None, None)
    g = lambda p: s[min(len(s) - 1, max(0, int(round(p / 100 * (len(s) - 1)))))]
    return (g(lo), g(hi))


def all3_miss_rate(miss_by_judge, idx):
    if not idx:
        return 0.0
    return sum(1 for i in idx if all(miss_by_judge[j][i] for j in JUDGES)) / len(idx)


def perm_residual_all3(miss_by_judge, idx, strata, B=3000):
    """Within-stratum permutation: shuffle each judge's miss vector inside each
    difficulty stratum (preserves per-judge rate + difficulty), break cross-judge
    alignment. Returns (observed, perm_mean, perm_ci, lift, p)."""
    obs = all3_miss_rate(miss_by_judge, idx)
    # group indices by stratum
    groups = {}
    for i in idx:
        groups.setdefault(strata[i], []).append(i)
    perms = []
    for _ in range(B):
        shuffled = {j: dict() for j in JUDGES}
        for g_idx in groups.values():
            for j in JUDGES:
                vals = [miss_by_judge[j][i] for i in g_idx]
                random.shuffle(vals)
                for i, v in zip(g_idx, vals):
                    shuffled[j][i] = v
        cnt = sum(1 for i in idx if all(shuffled[j][i] for j in JUDGES))
        perms.append(cnt / len(idx))
    pm = sum(perms) / len(perms)
    p = (sum(1 for v in perms if v >= obs) + 1) / (len(perms) + 1)
    lift = obs / pm if pm > 0 else float("inf")
    return obs, pm, ci(perms), lift, p


def bal_acc(verd, gold, idx):
    cor = [i for i in idx if gold[i] == "false"]
    cln = [i for i in idx if gold[i] == "true"]
    sens = sum(1 for i in cor if verd[i] == "false") / len(cor) if cor else 0.0
    spec = sum(1 for i in cln if verd[i] == "true") / len(cln) if cln else 0.0
    return (sens + spec) / 2


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    data = ROOT / "data" / f"number_corruption_n{n}.jsonl"
    small_cache = RawCache(ROOT / "results" / f"mvp_n{n}_raw_outputs.jsonl")
    gpt_cache = RawCache(ROOT / "results" / f"n{n}_gpt4o_difficulty.jsonl")
    items = load_jsonl(data)
    gold = [it["gold"] for it in items]

    # small-judge verdicts (must be cached already)
    v = {j: [] for j in JUDGES}
    for it in items:
        for j in JUDGES:
            c = small_cache.get(j, it["id"], MODE, None)
            v[j].append(c["verdict"] if c else "parse_fail")

    # held-out GPT-4o difficulty pass
    print("Held-out GPT-4o reference-free pass (difficulty oracle)...", flush=True)
    gv = []
    for k, it in enumerate(items):
        c = gpt_cache.get(REF_JUDGE, it["id"], MODE, None)
        if c is None:
            r = judge_statement(REF_JUDGE, it["statement"])
            gpt_cache.put({"judge": REF_JUDGE, "item_id": it["id"], "mode": MODE,
                           "prior": None, "verdict": r.verdict,
                           "raw_response": r.raw_response, "prompt_tokens": 0,
                           "completion_tokens": 0})
            gv.append(r.verdict)
        else:
            gv.append(c["verdict"])
        if (k + 1) % 100 == 0:
            print(f"  {k+1}/{len(items)}", flush=True)

    gpt_correct = [gv[i] == gold[i] for i in range(len(items))]
    gpt_acc = sum(gpt_correct) / len(items)

    # error vectors (1=wrong) over all items, and miss vectors on corrupted
    err = {j: [0 if v[j][i] == gold[i] else 1 for i in range(len(items))] for j in JUDGES}
    miss = {j: [1 if (items[i]["is_corrupted"] and v[j][i] == "true") else 0
                for i in range(len(items))] for j in JUDGES}

    corr_idx = [i for i in range(len(items)) if items[i]["is_corrupted"]]
    # detectable = GPT-4o detected the corruption on this corrupted item
    detect_idx = [i for i in corr_idx if gpt_correct[i]]
    obscure_idx = [i for i in corr_idx if not gpt_correct[i]]

    fn = {j: sum(miss[j][i] for i in corr_idx) / len(corr_idx) for j in JUDGES}

    def indep_all3(idx):
        rates = [sum(miss[j][i] for i in idx) / len(idx) for j in JUDGES] if idx else [0, 0, 0]
        return rates[0] * rates[1] * rates[2]

    # FN-only correlation (corrupted subset)
    fn_err = {j: [miss[j][i] for i in corr_idx] for j in JUDGES}
    fn_corr = mean_pairwise(fn_err)

    # difficulty strata for permutation: detectable vs obscure
    strata = {i: ("detect" if gpt_correct[i] else "obscure") for i in range(len(items))}

    print("\n" + "=" * 64)
    print(f"Held-out GPT-4o accuracy (difficulty oracle): {gpt_acc:.3f}")
    print(f"Corrupted items: {len(corr_idx)}  |  GPT-4o-detectable: "
          f"{len(detect_idx)}  |  obscure: {len(obscure_idx)}")
    print("=" * 64)

    print("\n--- Small-judge balanced accuracy by stratum ---")
    all_idx = list(range(len(items)))
    det_all = [i for i in all_idx if gpt_correct[i]]
    obs_all = [i for i in all_idx if not gpt_correct[i]]
    for j in JUDGES:
        print(f"  {j.split('/')[-1]:<22} overall={bal_acc(v[j],gold,all_idx):.3f}  "
              f"detectable={bal_acc(v[j],gold,det_all):.3f}  "
              f"obscure={bal_acc(v[j],gold,obs_all):.3f}")

    print(f"\nFN-only mean correlation (corrupted subset): {fn_corr:.3f}")

    print("\n--- all-3 false consensus: raw vs difficulty-controlled residual ---")
    for label, idx in [("ALL corrupted", corr_idx),
                       ("GPT-4o-DETECTABLE corrupted (decisive)", detect_idx),
                       ("obscure corrupted", obscure_idx)]:
        if len(idx) < 10:
            print(f"  {label}: n={len(idx)} too small")
            continue
        obs = all3_miss_rate(miss, idx)
        ind = indep_all3(idx)
        naive_lift = obs / ind if ind > 0 else float("inf")
        # residual within the SAME stratum set (permute within detect/obscure split)
        o, pm, pci, rlift, p = perm_residual_all3(miss, idx, strata)
        print(f"  {label}: n={len(idx)}")
        print(f"     all-3 miss obs={obs:.3f}  naive-indep={ind:.4f}  naive-lift={naive_lift:.1f}x")
        print(f"     perm-null={pm:.3f} CI[{pci[0]:.3f},{pci[1]:.3f}]  "
              f"RESIDUAL-lift={rlift:.2f}x  perm-p={p:.4f}")

    summary = {
        "gpt4o_acc": gpt_acc, "n_corrupted": len(corr_idx),
        "n_detectable": len(detect_idx), "n_obscure": len(obscure_idx),
        "fn_only_correlation": fn_corr, "fn_rate_by_judge": fn,
    }
    (ROOT / "results" / f"n{n}_residual_summary.json").write_text(
        json.dumps(summary, indent=2))
    print(f"\nWrote results/n{n}_residual_summary.json")
    print(f"GPT-4o cache: {len(gpt_cache)} calls")


if __name__ == "__main__":
    main()
