#!/usr/bin/env python3
"""Non-oracle retrieval -> grounded judging stress test.

The original reference-free prompt is used in the no-reference condition; one
frozen grounded prompt is used unchanged across all oracle and retrieved-reference
conditions. Reports both a STANDALONE verifier diagnostic (every item grounded)
and the deployed end-to-end frozen JuryProbe-Routed policy (one-sided accept
protection), plus retrieval quality stratified by whether BM25 actually retrieved
the gold evidence (retrieval hit vs miss). Hit/miss strata are descriptive
associations, not randomized reference-content interventions.

This is positioned as a STRESS TEST of the trusted-reference layer, not a new
retrieval-augmented method: BM25 is a deliberately simple, unsupervised retriever,
and trusted-reference performance is expected to depend on retrieval quality.

Conditions:
  reference_free  : no reference (read from existing RF cache)
  oracle_sentence : gold evidence sentence(s)      (reuses existing grounded cache)
  oracle_abstract : full abstract(s) with the gold  (new grounded calls)
  bm25_1          : top-1 BM25 sentence, claim-only  (new grounded calls)
  bm25_3          : top-3 BM25 sentences             (new grounded calls)

FC lift uses the same permutation-null construction as risk_assessment, with
seed 17 and 100000 permutations on the full subset. Cross-family split means
have a different aggregation scope and use 3000 permutations per split.
Resumable: new verdicts cached to results/scifact_retrieval_grounded.jsonl.

Usage:
  python3 scripts/run_scifact_retrieval_grounded.py
"""
from __future__ import annotations

import argparse
import json
import os
import random
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

# condition -> (cache_path, mode, needs_api)
CONDITIONS = {
    "oracle_sentence": ("results/scifact_natural_n190_grounded_rf.jsonl", "grounded", False),
    "oracle_abstract": ("results/scifact_retrieval_grounded.jsonl", "grounded_oracle_abstract", True),
    "bm25_1": ("results/scifact_retrieval_grounded.jsonl", "grounded_bm25_1", True),
    "bm25_3": ("results/scifact_retrieval_grounded.jsonl", "grounded_bm25_3", True),
}


def judge_grounded(model, reference, statement):
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


# ---------------- statistics ----------------
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


def fc_lift(miss, n, seed=17, permutations=100000):
    """Permutation-null lift (same procedure as risk_assessment.residual_lift).

    Uses a large permutation count so the reported aggregate lift is stable (the
    3000-perm setting used for per-split screening carries visible sampling noise
    at this obs rate; here the estimate converges to the analytic independence
    null = product of per-judge marginal false-accept rates).
    """
    obs = all3_rate(miss, n)
    rng = random.Random(seed)
    nulls = []
    for _ in range(permutations):
        shuffled = {}
        for j in JUDGES:
            vals = list(miss[j])
            rng.shuffle(vals)
            shuffled[j] = vals
        nulls.append(sum(1 for k in range(n) if all(shuffled[j][k] for j in JUDGES)) / n if n else 0.0)
    null_mean = sum(nulls) / len(nulls) if nulls else 0.0
    if null_mean > 0:
        lift = obs / null_mean
    elif obs == 0:
        lift = 0.0
    else:
        lift = float("inf")
    p = (sum(1 for v in nulls if v >= obs) + 1) / (len(nulls) + 1) if nulls else 1.0
    return obs, null_mean, lift, p


# ---------------- verdict sourcing ----------------
def load_rf(path):
    rf = defaultdict(dict)
    for rec in load_jsonl(path):
        if rec.get("mode") not in (None, "reference_free"):
            continue
        rf[rec["item_id"]][rec["judge"]] = rec["verdict"]
    return dict(rf)


def run_condition(cond, items, cache, mode, needs_api, retry=1):
    """Ensure grounded verdicts exist for every (item, judge) in this condition."""
    calls = ptok = ctok = 0
    if not needs_api:
        return calls, ptok, ctok
    total = len(items) * len(JUDGES)
    done = 0
    for it in items:
        ref = it["refs"][cond]["reference"]
        for judge in JUDGES:
            cached = cache.get(judge, it["item_id"], mode, None)
            if cached is None:
                verdict, raw = "parse_fail", ""
                for _ in range(retry + 1):
                    try:
                        verdict, raw, pt, ct = judge_grounded(judge, ref, it["statement"])
                        ptok += pt
                        ctok += ct
                        calls += 1
                    except Exception as e:  # noqa: BLE001
                        verdict, raw = "parse_fail", f"error:{e}"
                    if verdict != "parse_fail":
                        break
                    time.sleep(1.0)
                cache.put({
                    "judge": judge, "item_id": it["item_id"], "mode": mode,
                    "prior": None, "verdict": verdict, "raw_response": raw[:200],
                    "condition": cond, "is_corrupted": it["is_corrupted"],
                })
            done += 1
            if done % 90 == 0:
                print(f"    [{cond}] {done}/{total} (new API={calls})", file=sys.stderr)
    return calls, ptok, ctok


def verdict_getter(cond, items, rf):
    """Return fn(item_id, judge) -> verdict for a condition."""
    if cond == "reference_free":
        return lambda iid, j: rf.get(iid, {}).get(j, "parse_fail")
    cache_path, mode, _ = CONDITIONS[cond]
    cache = RawCache(ROOT / cache_path)

    def get(iid, j):
        rec = cache.get(j, iid, mode, None)
        return rec["verdict"] if rec else "parse_fail"
    return get


# ---------------- analysis ----------------
def analyze_condition(cond, items, get, refs_by_id):
    corrupt = [it for it in items if it["is_corrupted"]]
    clean = [it for it in items if not it["is_corrupted"]]
    n = len(corrupt)

    miss = {j: [] for j in JUDGES}
    for it in corrupt:
        for j in JUDGES:
            miss[j].append(1 if get(it["item_id"], j) == "true" else 0)

    obs, null_mean, lift, p = fc_lift(miss, n)

    # majority-vote policy false accept on corrupt
    pol_fa = 0
    for it in corrupt:
        votes = sum(1 for j in JUDGES if get(it["item_id"], j) == "true")
        if votes >= 2:
            pol_fa += 1

    # clean true-accept (per judge-item)
    acc = tot = 0
    for it in clean:
        for j in JUDGES:
            if get(it["item_id"], j) == "true":
                acc += 1
            tot += 1

    # parse fails over all items
    pf = ptot = 0
    for it in items:
        for j in JUDGES:
            if get(it["item_id"], j) == "parse_fail":
                pf += 1
            ptot += 1

    result = {
        "n_corrupt": n, "n_clean": len(clean),
        "all3_false_consensus": round(obs, 4),
        "perm_null_mean": round(null_mean, 6),
        "fc_lift": (None if lift == float("inf") else round(lift, 3)),
        "fc_lift_infinite": lift == float("inf"),
        "perm_p": round(p, 4),
        "fn_corr": round(mean_pairwise(miss), 4),
        "per_judge_false_accept": {j: round(sum(miss[j]) / n, 4) for j in JUDGES},
        "policy_majority_false_accept": round(pol_fa / n, 4),
        "clean_true_accept": round(acc / tot, 4) if tot else 0.0,
        "parse_fail_rate": round(pf / ptot, 4) if ptot else 0.0,
    }
    # reference tokens + recall (only for conditions with a refs entry)
    if cond in ("oracle_sentence", "oracle_abstract", "bm25_1", "bm25_3"):
        toks = [it["refs"][cond]["n_tokens"] for it in items]
        result["mean_reference_tokens"] = round(sum(toks) / len(toks), 1)
        rec_all = sum(it["refs"][cond]["recall"] for it in items) / len(items)
        rec_c = sum(it["refs"][cond]["recall"] for it in corrupt) / n
        result["any_evidence_recall_all"] = round(rec_all, 3)
        result["any_evidence_recall_corrupt"] = round(rec_c, 3)
        if cond in ("bm25_1", "bm25_3"):
            cmp_all = sum(1 for it in items if it["refs"][cond]["hit_complete"]) / len(items)
            cmp_c = sum(1 for it in corrupt if it["refs"][cond]["hit_complete"]) / n
            result["complete_rationale_recall_all"] = round(cmp_all, 3)
            result["complete_rationale_recall_corrupt"] = round(cmp_c, 3)

    # BM25 hit/miss stratification (corrupt side)
    if cond in ("bm25_1", "bm25_3"):
        strata = {}
        for label, want_hit in [("retrieval_hit", True), ("retrieval_miss", False)]:
            sub = [it for it in corrupt if it["refs"][cond]["hit"] == want_hit]
            ns = len(sub)
            sub_miss = {j: [1 if get(it["item_id"], j) == "true" else 0 for it in sub] for j in JUDGES}
            a3 = all3_rate(sub_miss, ns) if ns else 0.0
            polfa = sum(1 for it in sub if sum(1 for j in JUDGES if get(it["item_id"], j) == "true") >= 2)
            strata[label] = {
                "n": ns,
                "all3_false_consensus": round(a3, 4),
                "all3_count": sum(1 for k in range(ns) if all(sub_miss[j][k] for j in JUDGES)),
                "policy_majority_false_accept": round(polfa / ns, 4) if ns else 0.0,
                "policy_false_accept_count": polfa,
            }
        result["stratified"] = strata
    return result


# ---------------- end-to-end frozen routing policy ----------------
def majority_accept(verdicts):
    return sum(1 for v in verdicts if v == "true") >= 2


def unanimous_true(verdicts):
    return len(verdicts) == len(JUDGES) and all(v == "true" for v in verdicts)


def panel_risk_high(items, rf):
    """Frozen consensus-risk rule on the full SciFact RF panel (fn>0.15, lift>1.5, p<0.05)."""
    corrupt = [it for it in items if it["is_corrupted"]]
    n = len(corrupt)
    miss = {j: [1 if rf.get(it["item_id"], {}).get(j) == "true" else 0 for it in corrupt]
            for j in JUDGES}
    fn = mean_pairwise(miss)
    obs, null_mean, lift, p = fc_lift(miss, n)
    high = (fn > 0.15) and (lift > 1.5) and (p < 0.05)
    return high, {"fn_corr": round(fn, 4), "fc_lift": (None if lift == float("inf") else round(lift, 3)),
                  "perm_p": round(p, 4), "high_risk": high}


def policy_metrics(items, decisions):
    corrupt = [it for it in items if it["is_corrupted"]]
    clean = [it for it in items if not it["is_corrupted"]]
    fa = sum(1 for it in corrupt if decisions[it["item_id"]]["accept"]) / len(corrupt)
    ta = sum(1 for it in clean if decisions[it["item_id"]]["accept"]) / len(clean)
    # Corrupt items that were unanimously accepted by the RF panel AND still accepted
    # after routing. This is a DEPLOYED-POLICY survival count -- NOT the standalone
    # grounded all-3 false-consensus metric (which is measured separately per
    # condition). Named explicitly to avoid conflating the two.
    surviving = sum(1 for it in corrupt if decisions[it["item_id"]]["rf_unanimous_true"]
                    and decisions[it["item_id"]]["accept"])
    esc = sum(1 for it in items if decisions[it["item_id"]]["escalated"])
    return {
        "false_accept_rate": round(fa, 4),
        "true_accept_rate": round(ta, 4),
        "surviving_rf_unanimous_false_accept_rate": round(surviving / len(corrupt), 4),
        "surviving_rf_unanimous_false_accept_count": surviving,
        "references_acquired": esc,   # retrieval fires only on escalated (RF-accepted) items
        "extra_verifier_items": esc,
        "grounded_model_calls": esc * len(JUDGES),
    }


def end_to_end_policies(items, rf, high_risk):
    """Reproduce the paper's frozen policies; routed = one-sided accept protection.

    RF baselines are condition-independent. For each grounded reference condition we
    run JuryProbe-Routed: escalate = high_risk AND rf_majority; on escalation the
    final accept is the grounded majority (which can only overturn accept->reject).
    """
    getters = {}  # condition -> grounded verdict getter

    def rf_decisions(kind):
        dec = {}
        for it in items:
            rv = [rf.get(it["item_id"], {}).get(j, "parse_fail") for j in JUDGES]
            accept = unanimous_true(rv) if kind == "unanimous" else majority_accept(rv)
            dec[it["item_id"]] = {"accept": accept, "rf_unanimous_true": unanimous_true(rv),
                                  "escalated": False}
        return dec

    out = {
        "reference_free_majority": policy_metrics(items, rf_decisions("majority")),
        "reference_free_unanimous": policy_metrics(items, rf_decisions("unanimous")),
        "juryprobe_routed": {},
    }
    for cond in ["oracle_sentence", "oracle_abstract", "bm25_1", "bm25_3"]:
        get = verdict_getter(cond, items, rf)
        dec = {}
        for it in items:
            rv = [rf.get(it["item_id"], {}).get(j, "parse_fail") for j in JUDGES]
            rf_maj = majority_accept(rv)
            escalate = bool(high_risk and rf_maj)
            if escalate:
                gv = [get(it["item_id"], j) for j in JUDGES]
                accept = majority_accept(gv)
            else:
                accept = rf_maj
            dec[it["item_id"]] = {"accept": accept, "rf_unanimous_true": unanimous_true(rv),
                                  "escalated": escalate}
        out["juryprobe_routed"][cond] = policy_metrics(items, dec)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refs", default="data/scifact_retrieval_refs.jsonl")
    ap.add_argument("--rf-cache", default="results/scifact_natural_n190_rf.jsonl")
    ap.add_argument("--out", default="results/scifact_retrieval_grounded_summary.json")
    ap.add_argument("--cache-only", action="store_true",
                    help="Require every recorded verdict; never call or retry a model")
    args = ap.parse_args()

    items = load_jsonl(ROOT / args.refs)
    refs_by_id = {it["item_id"]: it["refs"] for it in items}
    rf = load_rf(ROOT / args.rf_cache)

    total_calls = total_pt = total_ct = 0
    for cond, (cache_path, mode, needs_api) in CONDITIONS.items():
        if args.cache_only:
            cache = RawCache(ROOT / cache_path)
            missing = [(it["item_id"], judge) for it in items for judge in JUDGES
                       if cache.get(judge, it["item_id"], mode, None) is None]
            if missing:
                raise SystemExit(f"{cond}: {len(missing)} missing cached verdicts")
            print(f"[{cond}] cache-only: {len(items) * len(JUDGES)} verdicts", file=sys.stderr)
            continue
        if not needs_api:
            print(f"[{cond}] reuse existing cache ({mode})", file=sys.stderr)
            continue
        cache = RawCache(ROOT / cache_path)
        print(f"[{cond}] grounded judging {len(items)}x{len(JUDGES)} (cached skipped)...",
              file=sys.stderr)
        c, pt, ct = run_condition(cond, items, cache, mode, needs_api)
        total_calls += c
        total_pt += pt
        total_ct += ct
        print(f"[{cond}] new API calls={c} (pt={pt}, ct={ct})", file=sys.stderr)

    # --- Standalone verifier diagnostic: how each reference condition behaves if
    # EVERY item is grounded. NOT the deployed policy (see end_to_end below). ---
    conditions_out = {}
    order = ["reference_free", "oracle_sentence", "oracle_abstract", "bm25_1", "bm25_3"]
    for cond in order:
        get = verdict_getter(cond, items, rf)
        conditions_out[cond] = analyze_condition(cond, items, get, refs_by_id)

    # --- End-to-end deployed policy: frozen JuryProbe-Routed one-sided protection ---
    high_risk, risk_summary = panel_risk_high(items, rf)
    policy = end_to_end_policies(items, rf, high_risk)

    result = {
        "mode": "scifact_non_oracle_retrieval_grounded",
        "reference_source": "claim-only BM25 over corpus-provided abstract sentences",
        "judges": JUDGES,
        "prompt_note": ("The original reference-free prompt is used in the no-reference "
                        "condition; one frozen grounded prompt is used unchanged across all "
                        "oracle and retrieved-reference conditions."),
        "fc_lift_null": ("same stratified permutation-null construction as risk_assessment "
                         "(seed 17), with 100000 permutations for stable lift reporting"),
        "panel_risk": risk_summary,
        "verifier_diagnostic_note": ("`conditions` reports STANDALONE grounded behaviour "
                                     "(every item grounded) as a verifier diagnostic; it is "
                                     "NOT the deployed policy."),
        "conditions": conditions_out,
        "end_to_end_policy": {
            "note": ("Frozen JuryProbe-Routed policy: all claims first pass the RF panel; "
                     "SciFact is flagged high-risk by the fixed rule; ONLY RF-accepted claims "
                     "trigger BM25 retrieval + grounded re-check; final accept requires the "
                     "grounded panel to also accept (one-sided accept protection, so routed "
                     "true-accept can never exceed RF coverage). `references_acquired` counts "
                     "items that actually triggered retrieval."),
            **policy,
        },
        "new_api_calls_this_run": total_calls,
        "prompt_tokens_this_run": total_pt,
        "completion_tokens_this_run": total_ct,
    }
    (ROOT / args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
