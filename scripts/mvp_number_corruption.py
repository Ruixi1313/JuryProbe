#!/usr/bin/env python3
"""JuryProbe: reference-free number-corruption detection + correlation analysis.

Each small judge sees ONE statement (no reference answer) and labels it
true/false. We quantify whether judges make CORRELATED errors, against the
classical independence assumption, and fit a beta-binomial correlated-error
model.

Unified metric definitions (denominator = corrupted examples):
  False consensus (all-3) = #corrupted where ALL judges say "factual" / #corrupted
  Majority failure (>=2)  = #corrupted where >=2 judges say "factual" / #corrupted
Lift = observed / independent-baseline (independence uses per-judge FN rates).

Beta-binomial: each corrupted item has hidden miss-prob theta ~ Beta(a,b);
given theta, the #judges that miss ~ Binomial(m, theta). q=a/(a+b),
rho=1/(a+b+1). Independence => P(all miss)=q^m; correlated => beta-binomial.

Usage: python scripts/mvp_number_corruption.py [n_corrupt=300]
"""
from __future__ import annotations

import json
import math
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
from src.correlation import (
    per_judge_accuracy, pairwise_error_correlation, error_vectors,
)
from src.io_utils import load_jsonl, RawCache

JUDGES = [
    "meta-llama/llama-3.1-8b-instruct",
    "qwen/qwen-2.5-7b-instruct",
    "google/gemma-3-12b-it",
]
MODE = "reference_free"
random.seed(7)


def collect(items, cache):
    verdicts = {j: [] for j in JUDGES}
    for it in items:
        for j in JUDGES:
            cached = cache.get(j, it["id"], MODE, None)
            if cached is None:
                v = judge_statement(j, it["statement"])
                cache.put({"judge": j, "item_id": it["id"], "mode": MODE,
                           "prior": None, "verdict": v.verdict,
                           "raw_response": v.raw_response,
                           "prompt_tokens": v.prompt_tokens,
                           "completion_tokens": v.completion_tokens})
                verdicts[j].append(v.verdict)
            else:
                verdicts[j].append(cached["verdict"])
    return verdicts


def pearson(x, y):
    n = len(x)
    if n == 0:
        return 0.0
    mx, my = sum(x) / n, sum(y) / n
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sx = sum((a - mx) ** 2 for a in x) ** 0.5
    sy = sum((b - my) ** 2 for b in y) ** 0.5
    return num / (sx * sy) if sx > 0 and sy > 0 else 0.0


def mean_corr_from_errs(errs):
    js = list(errs.keys())
    vals = [pearson(errs[js[a]], errs[js[b]])
            for a in range(len(js)) for b in range(a + 1, len(js))]
    return sum(vals) / len(vals) if vals else 0.0


def indep_majority(fn):
    """P(>=2 of 3 judges miss) under independence with per-judge rates fn."""
    a, b, c = fn
    p_all = a * b * c
    p_two = a * b * (1 - c) + a * (1 - b) * c + (1 - a) * b * c
    return p_two + p_all


def betabinom_pmf(k, m, a, b):
    logc = (math.lgamma(m + 1) - math.lgamma(k + 1) - math.lgamma(m - k + 1))
    logbb = (math.lgamma(k + a) + math.lgamma(m - k + b) - math.lgamma(m + a + b))
    logb = (math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b))
    return math.exp(logc + logbb - logb)


def fit_betabinom(ks, m):
    n = len(ks)
    q = (sum(ks) / n) / m if n else 0.0
    if q <= 0 or q >= 1:
        return None
    mean = sum(ks) / n
    var = sum((k - mean) ** 2 for k in ks) / n
    denom = m * q * (1 - q)
    rho = (var / denom - 1) / (m - 1) if denom > 0 else 0.0
    rho = min(max(rho, 1e-4), 0.999)
    s = 1 / rho - 1
    return {"q": q, "rho": rho, "alpha": q * s, "beta": (1 - q) * s}


def ci(samples, lo=2.5, hi=97.5):
    s = sorted(x for x in samples if x is not None and not math.isinf(x)
               and not math.isnan(x))
    if not s:
        return [None, None]
    def pct(p):
        idx = min(len(s) - 1, max(0, int(round(p / 100 * (len(s) - 1)))))
        return s[idx]
    return [pct(lo), pct(hi)]


def main():
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY not set.", file=sys.stderr)
        sys.exit(1)
    n_corrupt = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    data = ROOT / "data" / f"number_corruption_n{n_corrupt}.jsonl"
    if not data.exists():
        print(f"ERROR: {data.relative_to(ROOT)} missing. Build it first.",
              file=sys.stderr)
        sys.exit(1)
    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    raw_cache = out_dir / f"mvp_n{n_corrupt}_raw_outputs.jsonl"
    summary_path = out_dir / f"mvp_n{n_corrupt}_summary.json"

    items = load_jsonl(data)
    gold = [it["gold"] for it in items]
    corr_idx = [i for i, it in enumerate(items) if it["is_corrupted"]]
    clean_idx = [i for i, it in enumerate(items) if not it["is_corrupted"]]
    cache = RawCache(raw_cache)
    print(f"Loaded {len(items)} ({len(corr_idx)} corrupted / {len(clean_idx)} "
          f"clean); cache {len(cache)} calls.")

    v = collect(items, cache)
    n_pf = sum(1 for j in JUDGES for x in v[j] if x == "parse_fail")
    accs = per_judge_accuracy(v, gold)
    errs = error_vectors(v, gold)
    corrs = pairwise_error_correlation(v, gold)
    mean_corr = sum(corrs.values()) / len(corrs) if corrs else 0.0

    # miss[j][position-in-corr_idx] = 1 if judge labeled corrupted item "factual"
    fn = {}
    miss = {j: [1 if v[j][i] == "true" else 0 for i in corr_idx] for j in JUDGES}
    for j in JUDGES:
        fn[j] = sum(miss[j]) / len(corr_idx) if corr_idx else 0.0
    ks = [sum(miss[j][t] for j in JUDGES) for t in range(len(corr_idx))]
    all3 = sum(1 for k in ks if k == len(JUDGES)) / len(corr_idx) if corr_idx else 0.0
    major = sum(1 for k in ks if k >= 2) / len(corr_idx) if corr_idx else 0.0

    fn_list = [fn[j] for j in JUDGES]
    indep_all3 = fn_list[0] * fn_list[1] * fn_list[2]
    indep_maj = indep_majority(fn_list)
    lift_all3 = all3 / indep_all3 if indep_all3 > 0 else float("inf")
    lift_maj = major / indep_maj if indep_maj > 0 else float("inf")

    # Clean controls (guardrail 4): are judges just over-flagging anything?
    fp, spec, bal_acc = {}, {}, {}
    for j in JUDGES:
        if clean_idx:
            fps = sum(1 for i in clean_idx if v[j][i] == "false")
            fp[j] = fps / len(clean_idx)
            spec[j] = 1.0 - fp[j]
        else:
            fp[j] = spec[j] = 0.0
        sens = 1.0 - fn[j]
        bal_acc[j] = (sens + spec[j]) / 2.0

    bb = fit_betabinom(ks, len(JUDGES))

    # Bootstrap
    B = 2000
    boot_corr, boot_all3, boot_major, boot_lift3, boot_liftm = [], [], [], [], []
    nC = len(corr_idx)
    for _ in range(B):
        ridx = [random.randrange(len(items)) for _ in range(len(items))]
        be = {j: [errs[j][i] for i in ridx] for j in JUDGES}
        boot_corr.append(mean_corr_from_errs(be))
        if nC:
            rc = [random.randrange(nC) for _ in range(nC)]
            bks = [ks[t] for t in rc]
            ba3 = sum(1 for k in bks if k == 3) / nC
            bmj = sum(1 for k in bks if k >= 2) / nC
            bfn = [sum(miss[j][t] for t in rc) / nC for j in JUDGES]
            bden = bfn[0] * bfn[1] * bfn[2]
            bdenm = indep_majority(bfn)
            boot_all3.append(ba3)
            boot_major.append(bmj)
            boot_lift3.append(ba3 / bden if bden > 0 else None)
            boot_liftm.append(bmj / bdenm if bdenm > 0 else None)

    ci_corr = ci(boot_corr)
    ci_all3 = ci(boot_all3)
    ci_major = ci(boot_major)
    ci_lift3 = ci(boot_lift3)
    ci_liftm = ci(boot_liftm)

    print("\n--- Per-judge (reference-free) ---")
    for j in JUDGES:
        print(f"  {j.split('/')[-1]:<24} acc={accs[j]:.3f}  "
              f"FN(miss corruption)={fn[j]:.3f}  FP(flag clean)={fp[j]:.3f}  "
              f"bal_acc={bal_acc[j]:.3f}")
    print("\n--- Inter-judge error correlation ---")
    for (a, b), c in corrs.items():
        print(f"  {a.split('/')[-1]:<22} x {b.split('/')[-1]:<22} r={c:+.3f}")
    print(f"  mean r = {mean_corr:.3f}   95% CI [{ci_corr[0]:.3f}, {ci_corr[1]:.3f}]")

    print("\n--- Correlated failure on corrupted items ---")
    print(f"  all-3 false consensus : {all3:.3f}  CI [{ci_all3[0]:.3f},{ci_all3[1]:.3f}]"
          f"   indep {indep_all3:.4f}   lift {lift_all3:.1f}x "
          f"CI [{ci_lift3[0] if ci_lift3[0] else float('nan'):.1f},"
          f"{ci_lift3[1] if ci_lift3[1] else float('nan'):.1f}]")
    _lm0 = ci_liftm[0] if ci_liftm[0] else float('nan')
    _lm1 = ci_liftm[1] if ci_liftm[1] else float('nan')
    print(f"  majority failure (>=2): {major:.3f}  CI [{ci_major[0]:.3f},{ci_major[1]:.3f}]"
          f"   indep {indep_maj:.4f}   lift {lift_maj:.1f}x CI [{_lm0:.1f},{_lm1:.1f}]")

    if bb:
        bb_all3 = betabinom_pmf(3, 3, bb["alpha"], bb["beta"])
        bb_maj = bb_all3 + betabinom_pmf(2, 3, bb["alpha"], bb["beta"])
        print("\n--- Beta-binomial correlated-error model ---")
        print(f"  q (mean miss-prob) = {bb['q']:.3f}   rho (intra-item corr) = {bb['rho']:.3f}")
        print(f"  P(all miss):  independent q^3 = {bb['q']**3:.4f}   "
              f"beta-binomial = {bb_all3:.4f}   observed = {all3:.4f}")
        print(f"  P(>=2 miss):  beta-binomial = {bb_maj:.4f}   observed = {major:.4f}")
    else:
        bb_all3 = bb_maj = None

    print(f"\n  parse failures: {n_pf}/{len(JUDGES)*len(items)}")

    passes = (mean_corr > 0.2 and ci_corr[0] is not None and ci_corr[0] > 0
              and lift_all3 > 3 and all3 > 0.05 and lift_maj > 1.5)
    verdict = "CORE RESULT HOLDS" if passes else "NOT YET (scale or inspect)"
    print("\n" + "=" * 60)
    print(f"VERDICT: {verdict}")
    print("=" * 60)
    print("  need: mean r>0.2 (CI>0), all-3 FC>5%, all-3 lift>3x, majority lift>1.5x")

    summary = {
        "n_statements": len(items), "n_corrupted": len(corr_idx),
        "n_clean": len(clean_idx), "judges": JUDGES,
        "accuracy_by_judge": accs, "fn_rate_by_judge": fn,
        "fp_rate_by_judge": fp, "specificity_by_judge": spec,
        "balanced_accuracy_by_judge": bal_acc,
        "pairwise_error_correlation": {f"{a}__{b}": c for (a, b), c in corrs.items()},
        "mean_error_correlation": mean_corr, "mean_corr_ci95": ci_corr,
        "all3_false_consensus": all3, "all3_ci95": ci_all3,
        "all3_independent": indep_all3, "all3_lift": lift_all3, "all3_lift_ci95": ci_lift3,
        "majority_failure": major, "majority_ci95": ci_major,
        "majority_independent": indep_maj, "majority_lift": lift_maj,
        "majority_lift_ci95": ci_liftm,
        "beta_binomial": ({**bb, "P_all_miss": bb_all3, "P_majority": bb_maj,
                           "P_all_miss_independent": bb["q"] ** 3} if bb else None),
        "parse_failures": n_pf, "verdict": verdict,
    }
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"\nWrote {summary_path.relative_to(ROOT)}")
    print(f"Cached calls: {len(cache)} -> {raw_cache.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
