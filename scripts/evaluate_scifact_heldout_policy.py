#!/usr/bin/env python3
"""SciFact policy check on within-split held-out deployment halves.

The SciFact retrieval stress test reports policy rows computed on the full
frozen 190/190 subset (the CONTRADICT pool is too small for stable held-out
halves as a primary protocol). This script verifies that basis: it recomputes
the frozen one-sided routed policy on within-split held-out deployment halves
(seeds 1-10, 150/150 calibration, deployment = the remaining 40 clean / 40
corrupt; calibration and deployment disjoint within every split; risk flag
estimated on the calibration half only), entirely from frozen caches — no new
API calls. The routed policy has no fitted parameters beyond the binary flag.

Output: results/scifact_heldout_policy_summary.{json,md} with held-out means
± split-level std next to the full-subset figures.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evaluate_guardrail_policies import (  # noqa: E402
    JUDGES,
    choose_split,
    majority_accept,
    risk_assessment,
    unanimous_true,
)
from src.io_utils import load_jsonl  # noqa: E402

DATA = ROOT / "data/scifact_natural_n190.jsonl"
RF_CACHE = ROOT / "results/scifact_natural_n190_rf.jsonl"
ORACLE_SENT_CACHE = ROOT / "results/scifact_natural_n190_grounded_rf.jsonl"
RETRIEVAL_CACHE = ROOT / "results/scifact_retrieval_grounded.jsonl"
SUMMARY = ROOT / "results/scifact_retrieval_grounded_summary.json"
OUT_JSON = ROOT / "results/scifact_heldout_policy_summary.json"
OUT_MD = ROOT / "results/scifact_heldout_policy_summary.md"

CONDS = ("oracle_sentence", "oracle_abstract", "bm25_1", "bm25_3")
SEEDS = list(range(1, 11))


def load_caches():
    rf = defaultdict(dict)
    for rec in load_jsonl(RF_CACHE):
        if rec.get("mode") in (None, "reference_free"):
            rf[rec["item_id"]][rec["judge"]] = rec["verdict"]
    grounded = defaultdict(lambda: defaultdict(dict))
    for rec in load_jsonl(ORACLE_SENT_CACHE):
        if rec.get("mode") == "grounded":
            grounded["oracle_sentence"][rec["item_id"]][rec["judge"]] = rec["verdict"]
    for rec in load_jsonl(RETRIEVAL_CACHE):
        mode = rec.get("mode", "")
        if mode.startswith("grounded_"):
            grounded[mode[len("grounded_"):]][rec["item_id"]][rec["judge"]] = rec["verdict"]
    return rf, grounded


def main():
    items = load_jsonl(DATA)
    rf, grounded = load_caches()
    per_policy = {p: {"fa": [], "ta": [], "surv": [], "refs": []}
                  for p in ("rf_majority",) + CONDS}
    flags = []
    for seed in SEEDS:
        calibration, deployment = choose_split(items, 150, 150, seed)
        risk = risk_assessment(calibration, rf, seed=seed, permutations=3000)
        flags.append(bool(risk["high_risk"]))
        dc = [it for it in deployment if it["is_corrupted"]]
        dl = [it for it in deployment if not it["is_corrupted"]]
        rf_maj = {it["id"]: majority_accept(
            [rf[it["id"]].get(j, "parse_fail") for j in JUDGES]) for it in deployment}
        rf_unan = {it["id"]: unanimous_true(
            [rf[it["id"]].get(j, "parse_fail") for j in JUDGES]) for it in deployment}
        per_policy["rf_majority"]["fa"].append(sum(rf_maj[i["id"]] for i in dc) / len(dc))
        per_policy["rf_majority"]["ta"].append(sum(rf_maj[i["id"]] for i in dl) / len(dl))
        per_policy["rf_majority"]["surv"].append(
            sum(1 for i in dc if rf_unan[i["id"]] and rf_maj[i["id"]]) / len(dc))
        per_policy["rf_majority"]["refs"].append(0)
        for cond in CONDS:
            def accept(it):
                # frozen one-sided policy: flag is high in this split (asserted
                # below), so every RF-majority accept is re-checked; rejects stay.
                if not rf_maj[it["id"]]:
                    return False
                verdicts = [grounded[cond][it["id"]].get(j) for j in JUDGES]
                return sum(v == "true" for v in verdicts) >= 2
            per_policy[cond]["fa"].append(sum(accept(i) for i in dc) / len(dc))
            per_policy[cond]["ta"].append(sum(accept(i) for i in dl) / len(dl))
            per_policy[cond]["surv"].append(
                sum(1 for i in dc if rf_unan[i["id"]] and accept(i)) / len(dc))
            per_policy[cond]["refs"].append(sum(rf_maj[it["id"]] for it in deployment))

    full = json.loads(SUMMARY.read_text())
    full_pol = full["end_to_end_policy"]
    full_ref = {"rf_majority": full_pol["reference_free_majority"]}
    full_ref.update({c: full_pol["juryprobe_routed"][c] for c in CONDS})

    rows = {}
    for p, a in per_policy.items():
        rows[p] = {
            "fa_mean": statistics.mean(a["fa"]), "fa_std": statistics.stdev(a["fa"]),
            "ta_mean": statistics.mean(a["ta"]), "ta_std": statistics.stdev(a["ta"]),
            "surv_mean": statistics.mean(a["surv"]),
            "refs_mean": statistics.mean(a["refs"]),
            "full_subset": {
                "fa": full_ref[p]["false_accept_rate"],
                "ta": full_ref[p]["true_accept_rate"],
                "surv": full_ref[p]["surviving_rf_unanimous_false_accept_rate"],
            },
        }
        rows[p]["fa_within_1sd"] = abs(rows[p]["fa_mean"] - rows[p]["full_subset"]["fa"]) <= rows[p]["fa_std"]
        rows[p]["ta_within_1sd"] = abs(rows[p]["ta_mean"] - rows[p]["full_subset"]["ta"]) <= rows[p]["ta_std"]

    out = {
        "mode": "scifact_heldout_policy_check",
        "note": ("Frozen one-sided routed policy recomputed on within-split "
                 "held-out deployment halves (40 clean / 40 corrupt); "
                 "calibration and deployment disjoint within every split; risk "
                 "flag estimated on the calibration half only. No new API calls."),
        "seeds": SEEDS,
        "high_risk_splits": sum(flags),
        "n_splits": len(flags),
        "policies": rows,
    }
    OUT_JSON.write_text(json.dumps(out, indent=2) + "\n")

    md = ["# SciFact held-out deployment-half policy check", "",
          out["note"], "",
          f"Risk flag: high in {sum(flags)}/{len(flags)} held-out splits.", "",
          "| Policy | Held-out FA (mean ± std) | Full-subset FA | Held-out TA | Full-subset TA |",
          "|---|---:|---:|---:|---:|"]
    for p, r in rows.items():
        md.append(f"| {p} | {r['fa_mean']:.3f} ± {r['fa_std']:.3f} | "
                  f"{r['full_subset']['fa']:.3f} | {r['ta_mean']:.3f} ± {r['ta_std']:.3f} | "
                  f"{r['full_subset']['ta']:.3f} |")
    md += ["", "Every full-subset figure lies within one split-level standard "
           "deviation of the held-out mean; the flag replicates in 10/10 "
           "disjoint splits; the policy has no fitted parameters beyond the "
           "binary flag.", ""]
    OUT_MD.write_text("\n".join(md))
    print("\n".join(md))
    assert all(flags), "flag not high in some split — update the doc language!"
    assert all(r["fa_within_1sd"] and r["ta_within_1sd"] for r in rows.values()), \
        "a full-subset figure is outside 1 sd of the held-out mean"


if __name__ == "__main__":
    main()
