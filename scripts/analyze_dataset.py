#!/usr/bin/env python3
"""General analyzer for any corruption dataset (number, entity, ...).

Runs, on data/<stem>.jsonl:
  - reference-free small-judge verdicts (3 cheap judges), cached
  - held-out GPT-4o difficulty oracle (NOT in jury), cached
  - grounded foil (reference = original_statement) on detectable corrupted, cached
Reports, on the GPT-4o-detectable corrupted subset (decisive):
  - per-judge FN/FP/balanced acc
  - FN-only correlation
  - all-3 false consensus + difficulty-controlled RESIDUAL lift (within-stratum
    permutation) + perm p
  - grounded foil: correlation + all-3 (should collapse if reference matters)

Usage: python scripts/analyze_dataset.py <stem>
  e.g. python scripts/analyze_dataset.py entity_corruption_n150
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

from src.judges import judge_statement, _call_openrouter, _parse_truth
from src.io_utils import load_jsonl, RawCache

JUDGES = ["meta-llama/llama-3.1-8b-instruct", "qwen/qwen-2.5-7b-instruct",
          "google/gemma-3-12b-it"]
REF = "openai/gpt-4o"
random.seed(17)


def infer_family(stem, items):
    for name in ("number", "entity", "relation", "attribute"):
        if stem.startswith(name) or f"_{name}_" in stem:
            return name
    kinds = {str(it.get("kind", "")).lower() for it in items}
    if "entity" in kinds:
        return "entity"
    if "number" in kinds or kinds & {"integer", "year", "decimal"}:
        return "number"
    if "relation" in kinds:
        return "relation"
    if "attribute" in kinds:
        return "attribute"
    return "corruption"


def pearson(x, y):
    n = len(x)
    if n == 0:
        return 0.0
    mx, my = sum(x) / n, sum(y) / n
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sx = sum((a - mx) ** 2 for a in x) ** 0.5
    sy = sum((b - my) ** 2 for b in y) ** 0.5
    return num / (sx * sy) if sx > 0 and sy > 0 else 0.0


def mean_pair(e, idx):
    js = list(e.keys())
    vs = [pearson([e[js[a]][i] for i in idx], [e[js[b]][i] for i in idx])
          for a in range(len(js)) for b in range(a + 1, len(js))]
    return sum(vs) / len(vs) if vs else 0.0


def all3(e, idx):
    return sum(1 for i in idx if all(e[j][i] for j in JUDGES)) / len(idx) if idx else 0.0


def subset_errors(e, idx):
    return {j: [e[j][i] for i in idx] for j in JUDGES}


def paired_bootstrap_reduction(rf_e, grounded_e, metric, B=5000):
    """Bootstrap whether grounding lowers a paired metric over the same items."""
    n = len(next(iter(rf_e.values()))) if rf_e else 0
    if n == 0:
        return {"reduction": 0.0, "ci95": [0.0, 0.0], "p_lower": 1.0}
    base_idx = list(range(n))
    obs = metric(rf_e, base_idx) - metric(grounded_e, base_idx)
    vals = []
    for _ in range(B):
        idx = [random.randrange(n) for _ in range(n)]
        vals.append(metric(rf_e, idx) - metric(grounded_e, idx))
    vals.sort()
    lo = vals[int(0.025 * B)]
    hi = vals[min(B - 1, int(0.975 * B))]
    p_lower = (sum(1 for v in vals if v <= 0) + 1) / (B + 1)
    return {"reduction": obs, "ci95": [lo, hi], "p_lower": p_lower}


def perm_resid(e, idx, B=3000):
    obs = all3(e, idx)
    ps = []
    for _ in range(B):
        sh = {}
        for j in JUDGES:
            v = [e[j][i] for i in idx]
            random.shuffle(v)
            sh[j] = v
        ps.append(sum(1 for k in range(len(idx)) if all(sh[j][k] for j in JUDGES)) / len(idx))
    pm = sum(ps) / len(ps)
    return obs, pm, (obs / pm if pm > 0 else float("inf")), (sum(1 for v in ps if v >= obs) + 1) / (len(ps) + 1)


def grounded_judge(model, ref, stmt):
    p = ("You are verifying a statement against a trusted reference.\n\n"
         f"Reference (trusted, correct): {ref}\n\nStatement to check: {stmt}\n\n"
         "Is the Statement fully consistent with the Reference? Answer ONLY "
         "'true' (consistent) or 'false' (contradicts the reference).\n\nYour answer:")
    try:
        r = _call_openrouter(model, p)
        return _parse_truth(r["choices"][0]["message"]["content"])
    except Exception:
        return "parse_fail"


def main():
    stem = sys.argv[1] if len(sys.argv) > 1 else "number_corruption_n300"
    data = ROOT / "data" / f"{stem}.jsonl"
    rf = RawCache(ROOT / "results" / f"{stem}_rf.jsonl")
    gp = RawCache(ROOT / "results" / f"{stem}_gpt4o.jsonl")
    gr = RawCache(ROOT / "results" / f"{stem}_grounded.jsonl")
    items = load_jsonl(data)
    family = infer_family(stem, items)
    gold = [it["gold"] for it in items]
    print(f"[{stem}] {len(items)} items "
          f"({sum(it['is_corrupted'] for it in items)} corrupted)")

    # reference-free small judges
    print("reference-free small judges...", flush=True)
    v = {j: [] for j in JUDGES}
    for it in items:
        for j in JUDGES:
            c = rf.get(j, it["id"], "reference_free", None)
            if c is None:
                r = judge_statement(j, it["statement"])
                rf.put({"judge": j, "item_id": it["id"], "mode": "reference_free",
                        "prior": None, "verdict": r.verdict, "raw_response": r.raw_response,
                        "prompt_tokens": 0, "completion_tokens": 0})
                v[j].append(r.verdict)
            else:
                v[j].append(c["verdict"])

    # held-out GPT-4o difficulty
    print("held-out GPT-4o difficulty...", flush=True)
    gv = []
    for it in items:
        c = gp.get(REF, it["id"], "reference_free", None)
        if c is None:
            r = judge_statement(REF, it["statement"])
            gp.put({"judge": REF, "item_id": it["id"], "mode": "reference_free",
                    "prior": None, "verdict": r.verdict, "raw_response": r.raw_response,
                    "prompt_tokens": 0, "completion_tokens": 0})
            gv.append(r.verdict)
        else:
            gv.append(c["verdict"])

    gpt_ok = [gv[i] == gold[i] for i in range(len(items))]
    err = {j: [0 if v[j][i] == gold[i] else 1 for i in range(len(items))] for j in JUDGES}
    miss = {j: [1 if (items[i]["is_corrupted"] and v[j][i] == "true") else 0
                for i in range(len(items))] for j in JUDGES}
    corr_idx = [i for i in range(len(items)) if items[i]["is_corrupted"]]
    det_idx = [i for i in corr_idx if gpt_ok[i]]

    def balacc(j, idx):
        c = [i for i in idx if gold[i] == "false"]; cl = [i for i in idx if gold[i] == "true"]
        se = sum(1 for i in c if v[j][i] == "false") / len(c) if c else 0
        sp = sum(1 for i in cl if v[j][i] == "true") / len(cl) if cl else 0
        return (se + sp) / 2

    print(f"\nGPT-4o oracle acc={sum(gpt_ok)/len(items):.3f} | corrupted={len(corr_idx)} "
          f"detectable={len(det_idx)}")
    print("\n--- small-judge (detectable subset) ---")
    for j in JUDGES:
        fnr = sum(miss[j][i] for i in det_idx) / len(det_idx) if det_idx else 0
        print(f"  {j.split('/')[-1]:<22} FN={fnr:.3f}  sensitivity(detectable)={balacc(j,det_idx)*2:.3f}")

    fn_only = mean_pair(miss, corr_idx)
    print(f"\nFN-only correlation (all corrupted): {fn_only:.3f}")

    print("\n--- reference-free all-3 false consensus (difficulty-controlled) ---")
    perm_results = {}
    for label, idx in [("all corrupted", corr_idx), ("DETECTABLE (decisive)", det_idx)]:
        if len(idx) < 10:
            print(f"  {label}: n={len(idx)} too small"); continue
        o, pm, lift, p = perm_resid(miss, idx)
        perm_results[label] = {"all3": o, "perm_null": pm, "lift": lift, "p": p}
        print(f"  {label} n={len(idx)}: all-3={o:.3f} perm-null={pm:.3f} "
              f"RESIDUAL-lift={lift:.2f}x p={p:.4f}")

    # grounded foil on detectable corrupted
    print("\ngrounded foil (reference = original_statement)...", flush=True)
    g_err = {j: [] for j in JUDGES}
    for i in det_idx:
        it = items[i]
        for j in JUDGES:
            c = gr.get(j, it["id"], "grounded_foil", None)
            if c is None:
                vv = grounded_judge(j, it.get("original_statement", ""), it["statement"])
                gr.put({"judge": j, "item_id": it["id"], "mode": "grounded_foil",
                        "prior": None, "verdict": vv, "raw_response": "",
                        "prompt_tokens": 0, "completion_tokens": 0})
            else:
                vv = c["verdict"]
            g_err[j].append(1 if vv == "true" else 0)
    gidx = list(range(len(det_idx)))
    rf_det_err = subset_errors(miss, det_idx)
    rf_c = mean_pair(miss, det_idx)
    g_c = mean_pair(g_err, gidx)
    rf_o = all3(miss, det_idx)
    g_o = all3(g_err, gidx)
    corr_reduction = paired_bootstrap_reduction(rf_det_err, g_err, mean_pair)
    all3_reduction = paired_bootstrap_reduction(rf_det_err, g_err, all3)
    print("\n--- FOIL COLLAPSE (detectable subset) ---")
    print(f"  {'':16}{'reference-free':>16}{'grounded':>14}")
    print(f"  {'mean corr':<16}{rf_c:>16.3f}{g_c:>14.3f}")
    print(f"  {'all-3 FC':<16}{rf_o:>16.3f}{g_o:>14.3f}")
    print("  corr reduction   "
          f"{corr_reduction['reduction']:.3f} "
          f"CI95=[{corr_reduction['ci95'][0]:.3f}, {corr_reduction['ci95'][1]:.3f}] "
          f"p_lower={corr_reduction['p_lower']:.4f}")
    print("  all-3 reduction  "
          f"{all3_reduction['reduction']:.3f} "
          f"CI95=[{all3_reduction['ci95'][0]:.3f}, {all3_reduction['ci95'][1]:.3f}] "
          f"p_lower={all3_reduction['p_lower']:.4f}")

    det_perm = perm_results.get("DETECTABLE (decisive)", {
        "all3": rf_o, "perm_null": 0.0, "lift": 0.0, "p": 1.0,
    })
    lift = det_perm["lift"]
    p = det_perm["p"]
    # Replication pass: FN correlation + residual lift + perm significance + foil collapse
    # (not: absolute all-3 FC, which varies by corruption difficulty)
    foil_collapse = g_c < 0.10  # correlation vanishes when reference provided
    replication_pass = fn_only > 0.15 and lift > 1.5 and p < 0.05 and foil_collapse
    strong_mechanistic_replication = (
        corr_reduction["reduction"] > 0
        and corr_reduction["p_lower"] < 0.05
        and all3_reduction["reduction"] > 0
        and all3_reduction["p_lower"] < 0.05
    )
    family_label = family.upper()
    if replication_pass and strong_mechanistic_replication:
        verdict = f"{family_label} REPLICATION PASS + STRONG MECHANISTIC REPLICATION"
    elif replication_pass:
        verdict = f"{family_label} REPLICATION PASS; grounding reduction not strong by current test"
    else:
        verdict = f"{family_label} REPLICATION FAIL by preregistered thresholds -- inspect"
    print(f"\n  => {verdict}")
    (ROOT / "results" / f"{stem}_analysis.json").write_text(json.dumps({
        "stem": stem, "family": family, "gpt4o_acc": sum(gpt_ok) / len(items),
        "n_corrupted": len(corr_idx), "n_detectable": len(det_idx),
        "fn_only_corr": fn_only,
        "detectable_all3": rf_o, "detectable_residual_lift": lift, "perm_p": p,
        "replication_pass": replication_pass,
        f"{family}_replication_pass": replication_pass,
        "strong_mechanistic_replication": strong_mechanistic_replication,
        "grounded_corr": g_c, "grounded_all3": g_o,
        "grounded_corr_reduction": corr_reduction,
        "grounded_all3_reduction": all3_reduction,
        "verdict": verdict}, indent=2))
    print(f"\nWrote results/{stem}_analysis.json")


if __name__ == "__main__":
    main()
