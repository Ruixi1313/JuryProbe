#!/usr/bin/env python3
"""Ground-All-Accepts baseline (no risk estimator) vs frozen JuryProbe-Routed.

This baseline grounds every reference-free majority accept without consulting
the consensus-risk estimator.

Two structural facts frame the comparison:

1. In any split labeled HIGH-RISK by the fixed submitted rule,
   JuryProbe-Routed and Ground-All-Accepts are the same policy by definition:
   escalation grounds exactly the reference-free majority accepts. We verify
   this identity split-by-split rather than assuming it.
2. The two policies can differ only in LOW-RISK splits, where JuryProbe stands
   down (zero grounded calls, zero references) while Ground-All-Accepts still
   acquires a reference for every accept.

Strict no-new-API policy: rows are computed only where frozen grounded caches
cover the needed items. Where a grounded verdict is missing, the affected rate
is reported as an interval [missing treated as reject, missing treated as
accept]; grounding an accepted item can only overturn accept -> reject, so for
Ground-All-Accepts FA <= RF FA and TA <= RF TA always hold analytically.

Grounded-cache coverage (frozen artifacts; nothing new is run):
  * Number / Entity: complete 600-item grounded_verifier caches -> exact rows.
  * Attribute: corrupt-side-only legacy cache (296/300) -> exact-or-interval
    false-accept; clean-side true-accept bounded by RF true-accept.
  * Self-Contained Contradiction control: grounded_verifier cache covers all
    RF-majority-accepted items (run_control_grounded_verifier.py) -> exact rows.
  * ObvNumber boundary control: no grounded cache -> exact reference counts
    plus analytic intervals.
  * SciFact: not recomputed here; the retrieval-stress-test policy table is
    already the identity case (the full subset is flagged high-risk, so its
    JuryProbe-Routed rows ARE Ground-All-Accepts rows).
  * FEVER-Refutes: natural false claims carry no trusted reference, so neither
    grounded policy is evaluable there (reference-free diagnostics only).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evaluate_guardrail_policies import (  # noqa: E402
    JUDGES,
    RISK_THRESHOLDS,
    choose_split,
    majority_accept,
    risk_assessment,
    unanimous_true,
)
from scripts.evaluate_cross_family_transfer import load_rf  # noqa: E402
from src.io_utils import load_jsonl  # noqa: E402

GROUNDED_MODES = {"grounded_verifier", "grounded_foil", "grounded"}

# family -> (data, rf_cache, grounded_caches). Same data/rf pairing and family
# naming as evaluate_cross_family_transfer.FAMILIES (both obvious controls share
# the obvious_number rf cache; item ids are disjoint).
FAMILIES = [
    ("Number", "data/number_corruption_pool_v3_n300.jsonl",
     "results/number_corruption_pool_v3_n300_rf.jsonl",
     ["results/guardrail_grounded/number_corruption_pool_v3_n300_grounded_verifier_validated.jsonl"]),
    ("Entity", "data/entity_corruption_pool_v4_n300.jsonl",
     "results/entity_corruption_pool_v4_n300_rf.jsonl",
     ["results/guardrail_grounded/entity_corruption_pool_v4_n300_grounded_verifier_validated.jsonl"]),
    ("Attribute", "data/attribute_corruption_pool_v3_n300.jsonl",
     "results/attribute_corruption_pool_v3_n300_rf.jsonl",
     ["results/attribute_corruption_pool_v3_n300_grounded.jsonl"]),
    ("ObvNumber-Boundary-Control", "data/obvious_number_control_n300.jsonl",
     "results/obvious_number_control_n300_rf.jsonl", []),
    ("ObvContradiction-Control", "data/obvious_contradiction_control_v2_n300.jsonl",
     "results/obvious_number_control_n300_rf.jsonl",
     ["results/guardrail_grounded/obvious_contradiction_control_v2_n300_grounded_verifier.jsonl"]),
]

POLICIES = ("rf_majority", "ground_all_accepts", "juryprobe_routed", "always_grounded")


def load_grounded(paths):
    """item_id -> judge -> verdict from frozen grounded caches (no API)."""
    grounded = defaultdict(dict)
    for path in paths:
        p = ROOT / path
        if not p.exists():
            continue
        for rec in load_jsonl(p):
            if rec.get("mode") in GROUNDED_MODES:
                grounded[rec["item_id"]].setdefault(rec["judge"], rec["verdict"])
    return dict(grounded)


def grounded_majority(grounded, item_id):
    """(accept, complete): grounded-majority accept; complete iff all 3 cached."""
    verdicts = grounded.get(item_id, {})
    if len([j for j in JUDGES if j in verdicts]) < len(JUDGES):
        return None, False
    return majority_accept([verdicts[j] for j in JUDGES]), True


def rate(count, total):
    return count / total if total else 0.0


def evaluate_policy(policy, deployment, rf, grounded, high_risk):
    """One policy on one deployment split. Missing grounded verdicts widen the
    reported rates into [min, max] intervals (missing -> reject / accept)."""
    stats = {
        "corrupt_n": 0, "clean_n": 0,
        "fa_known": 0, "fa_missing": 0,
        "ta_known": 0, "ta_missing": 0,
        "surv_known": 0, "surv_missing": 0,
        "references_acquired": 0,
    }
    for it in deployment:
        rf_verdicts = [rf.get(it["id"], {}).get(j, "parse_fail") for j in JUDGES]
        rf_maj = majority_accept(rf_verdicts)
        rf_unan = unanimous_true(rf_verdicts)

        if policy == "rf_majority":
            escalate = False
        elif policy == "ground_all_accepts":
            escalate = rf_maj
        elif policy == "always_grounded":
            escalate = True
        else:  # juryprobe_routed
            escalate = bool(high_risk and rf_maj)

        if escalate:
            stats["references_acquired"] += 1
            accept, complete = grounded_majority(grounded, it["id"])
        else:
            accept, complete = rf_maj, True

        side = "clean" if not it["is_corrupted"] else "corrupt"
        stats[f"{side}_n"] += 1
        if it["is_corrupted"]:
            if not complete:
                stats["fa_missing"] += 1
                if rf_unan:
                    stats["surv_missing"] += 1
            elif accept:
                stats["fa_known"] += 1
                if rf_unan:
                    stats["surv_known"] += 1
        else:
            if not complete:
                stats["ta_missing"] += 1
            elif accept:
                stats["ta_known"] += 1

    n_c, n_cl = stats["corrupt_n"], stats["clean_n"]
    row = {
        "policy": policy,
        "false_accept_min": rate(stats["fa_known"], n_c),
        "false_accept_max": rate(stats["fa_known"] + stats["fa_missing"], n_c),
        "fa_missing_items": stats["fa_missing"],
        "true_accept_min": rate(stats["ta_known"], n_cl),
        "true_accept_max": rate(stats["ta_known"] + stats["ta_missing"], n_cl),
        "ta_missing_items": stats["ta_missing"],
        "surviving_rf_unanimous_min": rate(stats["surv_known"], n_c),
        "surviving_rf_unanimous_max": rate(stats["surv_known"] + stats["surv_missing"], n_c),
        "references_acquired": stats["references_acquired"],
        "grounded_model_calls": stats["references_acquired"] * len(JUDGES),
    }
    row["false_accept_exact"] = stats["fa_missing"] == 0
    row["true_accept_exact"] = stats["ta_missing"] == 0
    return row


def evaluate_family(name, data_path, rf_path, grounded_paths, seeds,
                    calib_clean, calib_corrupt, permutations):
    items = load_jsonl(ROOT / data_path)
    rf = load_rf(ROOT / rf_path)
    grounded = load_grounded(grounded_paths)
    per_seed = []
    for seed in seeds:
        calibration, deployment = choose_split(items, calib_clean, calib_corrupt, seed)
        risk = risk_assessment(calibration, rf, seed=seed, permutations=permutations)
        rows = {p: evaluate_policy(p, deployment, rf, grounded, risk["high_risk"])
                for p in POLICIES}
        # Identity check: in high-risk splits the two policies escalate the same
        # set and read the same cached verdicts, so every reported field must match.
        identity = None
        if risk["high_risk"]:
            identity = rows["ground_all_accepts"] == {
                **rows["juryprobe_routed"], "policy": "ground_all_accepts"}
        per_seed.append({
            "seed": seed,
            "high_risk": risk["high_risk"],
            "fn_corr": risk["fn_corr"],
            "residual_lift": risk["residual_lift"],
            "p_value": risk["p_value"],
            "identity_gaa_equals_routed": identity,
            "policies": rows,
        })
    return {
        "family": name,
        "data": data_path,
        "rf_cache": rf_path,
        "grounded_caches": grounded_paths,
        "grounded_items_cached": len(grounded),
        "n_splits": len(per_seed),
        "high_risk_splits": sum(1 for s in per_seed if s["high_risk"]),
        "identity_verified_high_splits": sum(
            1 for s in per_seed if s["identity_gaa_equals_routed"] is True),
        "identity_violations": sum(
            1 for s in per_seed if s["identity_gaa_equals_routed"] is False),
        "per_seed": per_seed,
    }


def mean(vals):
    vals = list(vals)
    return sum(vals) / len(vals) if vals else None


def summarize_regime(fam, regime):
    """Aggregate policy metrics over the high- or low-labeled splits."""
    splits = [s for s in fam["per_seed"] if s["high_risk"] == (regime == "high")]
    if not splits:
        return None
    out = {"n_splits": len(splits), "seeds": [s["seed"] for s in splits]}
    for p in POLICIES:
        rows = [s["policies"][p] for s in splits]
        exact_fa = all(r["false_accept_exact"] for r in rows)
        exact_ta = all(r["true_accept_exact"] for r in rows)
        out[p] = {
            "false_accept_mean_min": mean(r["false_accept_min"] for r in rows),
            "false_accept_mean_max": mean(r["false_accept_max"] for r in rows),
            "false_accept_exact": exact_fa,
            "true_accept_mean_min": mean(r["true_accept_min"] for r in rows),
            "true_accept_mean_max": mean(r["true_accept_max"] for r in rows),
            "true_accept_exact": exact_ta,
            "surviving_rf_unanimous_mean_max": mean(
                r["surviving_rf_unanimous_max"] for r in rows),
            "references_acquired_mean": mean(r["references_acquired"] for r in rows),
        }
    return out


def fmt_rate(row_min, row_max, exact, p=3):
    if row_min is None:
        return "NA"
    if exact or abs(row_max - row_min) < 10 ** (-p):
        return f"{row_min:.{p}f}"
    return f"[{row_min:.{p}f}, {row_max:.{p}f}]"


def markdown(results, meta):
    lines = [
        "# Ground-All-Accepts Baseline (No Risk Estimator) vs JuryProbe-Routed",
        "",
        "Ground-All-Accepts grounds every reference-free majority accept without "
        "consulting the consensus-risk estimator. In every split labeled high-risk "
        "by the fixed submitted rule (frozen thresholds) the two policies coincide by "
        "construction (escalation grounds exactly the RF-majority accepts); the "
        "identity is verified split-by-split below, not assumed. The policies can "
        "differ only in low-risk splits, where JuryProbe stands down.",
        "",
        f"Fixed rule: fn_corr>{meta['thresholds']['fn_only_corr']} AND "
        f"residual_lift>{meta['thresholds']['residual_lift']} AND "
        f"perm_p<{meta['thresholds']['perm_p']} (frozen 2026-06-09, never re-fit). "
        f"Splits: seeds {meta['seeds'][0]}-{meta['seeds'][-1]}, "
        f"{meta['calib_clean']}/{meta['calib_corrupt']} calibration, "
        "same scheme as the cross-family transfer table. "
        "No new API calls: frozen grounded caches only; where a cached verdict "
        "does not exist the rate is an interval [missing->reject, missing->accept].",
    ]
    header = ("| Family | Regime (splits) | Policy | False accept | True accept | "
              "Surviving RF-unanimous FA (max) | References / split |")
    sep = "|---|---|---|---:|---:|---:|---:|"
    exact_rows, bound_rows = [], []
    for fam in results:
        for regime in ("high", "low"):
            agg = fam["summary"].get(regime)
            if not agg:
                continue
            for p in POLICIES:
                r = agg[p]
                is_exact = r["false_accept_exact"] and r["true_accept_exact"]
                # An Always-Grounded row with no grounded records at all would be
                # a vacuous [0, 1] bound naming a policy that produced no real
                # outputs; it is omitted from the report entirely.
                if p == "always_grounded" and not is_exact and fam["grounded_items_cached"] == 0:
                    continue
                row = (
                    f"| {fam['family']} | {regime} ({agg['n_splits']}) | {p} | "
                    f"{fmt_rate(r['false_accept_mean_min'], r['false_accept_mean_max'], r['false_accept_exact'])} | "
                    f"{fmt_rate(r['true_accept_mean_min'], r['true_accept_mean_max'], r['true_accept_exact'])} | "
                    f"{r['surviving_rf_unanimous_mean_max']:.3f} | "
                    f"{r['references_acquired_mean']:.1f} |"
                )
                (exact_rows if is_exact else bound_rows).append(row)
    lines += ["", "## Policy results (every grounded verdict read from a real cache; exact)",
              "", header, sep, *exact_rows]
    if bound_rows:
        lines += ["", "## Analytic bounds — NOT policy results",
                  "",
                  "Grounded caches do not cover all items these rows would need; "
                  "rates are intervals [missing -> reject, missing -> accept] and "
                  "must not be quoted as measured policy performance. Reference "
                  "counts are exact.",
                  "", header, sep, *bound_rows]
    lines += [
        "",
        "## Identity verification (high-risk splits)",
        "",
        "| Family | High-risk splits | Identity verified | Violations |",
        "|---|---:|---:|---:|",
    ]
    for fam in results:
        lines.append(
            f"| {fam['family']} | {fam['high_risk_splits']}/{fam['n_splits']} | "
            f"{fam['identity_verified_high_splits']} | {fam['identity_violations']} |")
    lines += [
        "",
        "Grounded caches (rule: a number appears as a policy result only if "
        "every needed verdict is in one of these files):",
        "",
    ]
    for fam in results:
        caches = ", ".join(f"`{c}`" for c in fam["grounded_caches"]) or "(none)"
        lines.append(f"- {fam['family']}: {caches} — {fam['grounded_items_cached']} items cached")
    lines += [
        "",
        "Notes:",
        "",
        "- Number / Entity grounded caches are complete (600 items), so all their "
        "rows are exact. Attribute's frozen grounded cache covers the corrupt side "
        "only (296/300): false-accept columns are exact or tight intervals; "
        "clean-side true-accept under grounding is bounded above by the RF "
        "true-accept (grounding can only overturn accept -> reject).",
        "- The Self-Contained Contradiction control's grounded cache covers every "
        "RF-majority-accepted item, so its Ground-All-Accepts rows are exact "
        "empirical values. The ObvNumber boundary control has no grounded cache; "
        "its Ground-All-Accepts columns are analytic intervals with exact "
        "reference counts. JuryProbe rows in low-risk splits are exact "
        "(identical to rf_majority, zero references).",
        "- SciFact is not recomputed here: its full subset is flagged high-risk, "
        "so the JuryProbe-Routed rows of the retrieval stress test are already "
        "Ground-All-Accepts rows (the identity case). FEVER-Refutes has no "
        "trusted reference, so neither grounded policy is evaluable there.",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="1,2,3,4,5,6,7,8,9,10")
    ap.add_argument("--calib-clean", type=int, default=150)
    ap.add_argument("--calib-corrupt", type=int, default=150)
    ap.add_argument("--permutations", type=int, default=3000)
    ap.add_argument("--out", default="results/ground_all_accepts_baseline_summary.json")
    ap.add_argument("--md-out", default="results/ground_all_accepts_baseline_summary.md")
    args = ap.parse_args()

    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    results = []
    for name, data, rf_cache, grounded_caches in FAMILIES:
        fam = evaluate_family(name, data, rf_cache, grounded_caches, seeds,
                              args.calib_clean, args.calib_corrupt, args.permutations)
        fam["summary"] = {
            "high": summarize_regime(fam, "high"),
            "low": summarize_regime(fam, "low"),
        }
        results.append(fam)
        print(f"{name:28s} high={fam['high_risk_splits']}/{fam['n_splits']} "
              f"identity_ok={fam['identity_verified_high_splits']} "
              f"violations={fam['identity_violations']}")

    meta = {
        "mode": "ground_all_accepts_baseline",
        "thresholds": RISK_THRESHOLDS,
        "seeds": seeds,
        "calib_clean": args.calib_clean,
        "calib_corrupt": args.calib_corrupt,
        "permutations": args.permutations,
        "new_api_calls": 0,
        "provenance_note": (
            "Thresholds frozen in guardrail policy definition v1 (2026-06-09) "
            "and never re-fit; Attribute (frozen 2026-06-11), both obvious "
            "controls, SciFact and FEVER-Refutes were constructed after the "
            "freeze and evaluated under the unchanged rule."),
    }
    output = {**meta, "families": results}
    (ROOT / args.out).write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    (ROOT / args.md_out).write_text(markdown(results, meta))
    print()
    print(markdown(results, meta))


if __name__ == "__main__":
    main()
