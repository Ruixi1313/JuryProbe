#!/usr/bin/env python3
"""Parameterized utility analysis of the conditional operating regime.

Derive break-even boundaries from measured policy rates, with no new API calls.

Utility model (per deployment claim; stream of V claims, corrupted fraction pi):

    U(P) = v_TP * TP(P) - c_FA * FP(P) - c_ref * Refs(P) - c_LLM(P) - c_cal(P)/V

  TP(P)   = (1 - pi) * TA_P      true accepts per claim
  FP(P)   = pi * FA_P            false accepts per claim
  Refs(P)                        trusted references acquired per claim
  c_LLM(P)                       judge-call cost per claim (measured; ~1e-5 USD)
  c_cal(P)                       one-time calibration cost (JuryProbe only:
                                 300 labeled items + ~900 RF calls), amortized
  v_TP, c_FA, c_ref              deployment-dependent value/cost parameters

Break-even (JuryProbe-Routed vs an alternative ALT), with sign conventions
dTP = TP(ALT) - TP(JP), dFP = FP(JP) - FP(ALT), dRefs = Refs(ALT) - Refs(JP),
dLLM = c_LLM(JP) - c_LLM(ALT):

    JuryProbe preferred  <=>  c_ref > [ v_TP*dTP + c_FA*dFP + dLLM + c_cal/V ] / dRefs

All boundaries are linear and closed-form; nothing is fitted. Reported as
c_ref* = A*v_TP + B*c_FA + small terms, with A = dTP/dRefs, B = dFP/dRefs.

Inputs: results/ground_all_accepts_baseline_summary.json (Number / Entity /
Contradiction control; means over the same 10 frozen splits) and
results/scifact_retrieval_grounded_summary.json (reference-quality variants).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BASELINE = ROOT / "results/ground_all_accepts_baseline_summary.json"
SCIFACT = ROOT / "results/scifact_retrieval_grounded_summary.json"
OUT_JSON = ROOT / "results/utility_analysis_summary.json"
OUT_MD = ROOT / "results/utility_analysis_summary.md"

DEPLOY_N = 300          # deployment items per split (baseline families)
PI_MEASURED = 0.5       # corrupted fraction in the frozen splits
COST_PER_CALL = 0.0034 / 900   # USD per judge call (posted Change 3 logs)
CAL_LABELED_ITEMS = 300        # one-time labeled calibration probe (labels)
CAL_LLM_USD = 900 * COST_PER_CALL  # one-time calibration RF calls


def llm_calls_per_claim(policy, refs_per_claim):
    """Judge calls per deployment claim. RF-based policies run the 3-judge RF
    panel on every claim plus 3 grounded calls per acquired reference;
    Always-Grounded runs only the 3 grounded calls."""
    if policy == "always_grounded":
        return 3.0
    return 3.0 + 3.0 * refs_per_claim


def fam_rows(baseline, family, regime, pi):
    fam = next(f for f in baseline["families"] if f["family"] == family)
    agg = fam["summary"]["high" if regime == "high" else "low"]
    rows = {}
    for p, r in agg.items():
        if p in ("n_splits", "seeds"):
            continue
        if not (r["false_accept_exact"] and r["true_accept_exact"]):
            continue  # only exact empirical rows enter the utility model
        refs = r["references_acquired_mean"] / DEPLOY_N
        rows[p] = {
            "TA": r["true_accept_mean_min"], "FA": r["false_accept_mean_min"],
            "TP": (1 - pi) * r["true_accept_mean_min"],
            "FP": pi * r["false_accept_mean_min"],
            "Refs": refs,
            "cLLM": COST_PER_CALL * llm_calls_per_claim(p, refs),
        }
    per_seed = [s for s in fam["per_seed"] if s["high_risk"] == (regime == "high")]
    return rows, per_seed


def breakeven(rows, jp, alt, cal_on_jp=True):
    """c_ref* = A*v_TP + B*c_FA + (dLLM + c_cal/V)/dRefs; JP preferred when
    c_ref exceeds it (dRefs > 0)."""
    dTP = rows[alt]["TP"] - rows[jp]["TP"]
    dFP = rows[jp]["FP"] - rows[alt]["FP"]
    dRefs = rows[alt]["Refs"] - rows[jp]["Refs"]
    dLLM = rows[jp]["cLLM"] - rows[alt]["cLLM"]
    if abs(dRefs) < 1e-12:
        return None
    return {
        "jp": jp, "alt": alt,
        "A_vTP": dTP / dRefs, "B_cFA": dFP / dRefs,
        "dLLM_term_usd": dLLM / dRefs,
        "cal_term": (f"+ c_cal/(V*{dRefs:.3f})" if cal_on_jp else ""),
        "dTP": dTP, "dFP": dFP, "dRefs": dRefs, "dLLM_usd": dLLM,
    }


def per_seed_constants(per_seed, jp, alt, pi):
    A, B = [], []
    for s in per_seed:
        rows = {}
        for p in (jp, alt):
            r = s["policies"][p]
            if not (r["false_accept_exact"] and r["true_accept_exact"]):
                return None
            refs = r["references_acquired"] / DEPLOY_N
            rows[p] = {"TP": (1 - pi) * r["true_accept_min"],
                       "FP": pi * r["false_accept_min"], "Refs": refs,
                       "cLLM": COST_PER_CALL * llm_calls_per_claim(p, refs)}
        be = breakeven(rows, jp, alt)
        if be:
            A.append(be["A_vTP"])
            B.append(be["B_cFA"])
    if not A:
        return None
    out = []
    if max(A) - min(A) > 1e-9:
        out.append(f"A {min(A):.3g}..{max(A):.3g}")
    if max(B) - min(B) > 1e-9:
        out.append(f"B {min(B):.3g}..{max(B):.3g}")
    return ", ".join(out) if out else "stable across splits"


def be_str(be, direction=">"):
    terms = []
    if abs(be["A_vTP"]) > 1e-9:
        terms.append((be["A_vTP"], f"{abs(be['A_vTP']):.3f}*v_TP"))
    if abs(be["B_cFA"]) > 1e-9:
        terms.append((be["B_cFA"], f"{abs(be['B_cFA']):.4f}*c_FA"))
    if abs(be["dLLM_term_usd"]) > 1e-12:
        terms.append((be["dLLM_term_usd"], f"{abs(be['dLLM_term_usd']):.2e} USD"))
    if not terms:
        terms = [(0.0, "0")]
    s = ""
    for i, (val, txt) in enumerate(terms):
        if i == 0:
            s = ("-" if val < 0 else "") + txt
        else:
            s += (" - " if val < 0 else " + ") + txt
    return f"c_ref {direction} {s} {be['cal_term']}".rstrip()


def fmt_rows(rows, pi):
    lines = [f"| Policy | TA | FA | TP (pi={pi}) | FP | Refs/claim | c_LLM/claim (USD) |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for p, r in rows.items():
        lines.append(f"| {p} | {r['TA']:.3f} | {r['FA']:.3f} | {r['TP']:.3f} | "
                     f"{r['FP']:.4f} | {r['Refs']:.3f} | {r['cLLM']:.2e} |")
    return lines


def scifact_rows(pi):
    d = json.loads(SCIFACT.read_text())
    conds = d["conditions"]
    pol = d["end_to_end_policy"]
    routed = pol["juryprobe_routed"]
    def mk(fa, ta, refs, policy):
        return {"TA": ta, "FA": fa, "TP": (1 - pi) * ta, "FP": pi * fa,
                "Refs": refs, "cLLM": COST_PER_CALL * llm_calls_per_claim(policy, refs)}
    rows = {"rf_majority": mk(pol["reference_free_majority"]["false_accept_rate"],
                              pol["reference_free_majority"]["true_accept_rate"], 0.0,
                              "rf_majority")}
    for cond in ("oracle_sentence", "oracle_abstract", "bm25_1", "bm25_3"):
        rows[f"routed_{cond}"] = mk(routed[cond]["false_accept_rate"],
                                    routed[cond]["true_accept_rate"],
                                    routed[cond]["references_acquired"] / 380,
                                    "juryprobe_routed")
        rows[f"always_grounded_{cond}"] = mk(conds[cond]["policy_majority_false_accept"],
                                             conds[cond]["clean_true_accept"], 1.0,
                                             "always_grounded")
    return rows


def main():
    pi = PI_MEASURED
    baseline = json.loads(BASELINE.read_text())
    report = {"model": "U(P) = v_TP*TP - c_FA*FP - c_ref*Refs - c_LLM - c_cal/V",
              "pi_measured": pi, "cost_per_call_usd": COST_PER_CALL,
              "c_cal": f"{CAL_LABELED_ITEMS} labeled items + {CAL_LLM_USD:.4f} USD RF calls",
              "families": {}, "scifact": {}}
    md = [
        "# Parameterized Utility Analysis (A8)",
        "",
        "Per deployment claim (stream of V claims, corrupted fraction pi):",
        "",
        "```",
        "U(P) = v_TP*TP(P) - c_FA*FP(P) - c_ref*Refs(P) - c_LLM(P) - c_cal(P)/V",
        "```",
        "",
        f"TP = (1-pi)*TA, FP = pi*FA with pi = {pi} as measured on the frozen",
        "balanced splits (reweight TP/FP for other stream mixes; class-conditional",
        "rates assumed stable). c_LLM uses the posted Change-3 log cost of",
        f"{COST_PER_CALL:.2e} USD per judge call. c_cal applies to JuryProbe only:",
        f"{CAL_LABELED_ITEMS} labeled calibration items (labels, not references)",
        f"plus {CAL_LLM_USD:.4f} USD of one-time RF calls, amortized over V.",
        "",
        "**Break-even.** With dTP = TP(ALT)-TP(JP), dFP = FP(JP)-FP(ALT),",
        "dRefs = Refs(ALT)-Refs(JP) > 0, dLLM = c_LLM(JP)-c_LLM(ALT):",
        "",
        "```",
        "JuryProbe preferred over ALT  <=>",
        "c_ref > [ v_TP*dTP + c_FA*dFP + dLLM + c_cal/V ] / dRefs",
        "```",
        "",
        "All constants below are measured; nothing is fitted.",
        "",
    ]

    cases = [("Number", "high"), ("Entity", "high"),
             ("ObvContradiction-Control", "low")]
    for family, regime in cases:
        rows, per_seed = fam_rows(baseline, family, regime, pi)
        md += [f"## {family} ({'high-risk' if regime == 'high' else 'not flagged'} "
               f"in all 10 splits)", ""]
        md += fmt_rows(rows, pi) + [""]
        fam_out = {"rows": rows, "breakevens": []}
        if regime == "high":
            md += ["JuryProbe-Routed and Ground-All-Accepts are identical here "
                   "(verified identity); alternatives compared: Always-Grounded, "
                   "and reference-free majority (direction reversed: routing is "
                   "worthwhile only when c_ref is BELOW that line).", ""]
            alts = [("juryprobe_routed", "always_grounded", False)]
        else:
            alts = [("juryprobe_routed", "ground_all_accepts", False),
                    ("juryprobe_routed", "always_grounded", False)]
        for jp, alt, _ in alts:
            if jp not in rows or alt not in rows:
                md.append(f"- {jp} vs {alt}: skipped (non-exact row).")
                continue
            be = breakeven(rows, jp, alt)
            fam_out["breakevens"].append(be)
            spread = per_seed_constants(per_seed, jp, alt, pi)
            md.append(f"- **{jp}** preferred over **{alt}** iff {be_str(be)}"
                      + (f"  (split range: {spread})" if spread else ""))
        # routing-worthwhile line vs RF: rf preferred over jp iff c_ref > line,
        # so jp is preferred iff c_ref < the SAME line (inequality flips, the
        # constants do not change sign).
        if "rf_majority" in rows and "juryprobe_routed" in rows and regime == "high":
            r = breakeven(rows, "rf_majority", "juryprobe_routed", cal_on_jp=False)
            r["cal_term"] = "- c_cal/(V*%.3f)" % r["dRefs"]
            md.append(f"- **juryprobe_routed** preferred over **rf_majority** iff "
                      f"{be_str(r, '<')} (routing worthwhile below this line).")
            fam_out["breakevens"].append({**r, "direction": "jp_below_line"})
        md.append("")
        report["families"][family] = fam_out

    # Worked amortization example ------------------------------------------
    md += [
        "## Amortization of c_cal",
        "",
        f"c_cal = {CAL_LABELED_ITEMS}*c_label + {CAL_LLM_USD:.4f} USD. If a label",
        "costs about as much as a reference (c_label ~ c_ref), the calibration",
        "term shifts the Number break-even by 300*c_ref/(V*0.496): ~6% of c_ref",
        "at V = 10^4 claims, ~0.6% at V = 10^5 — visible at small volume,",
        "negligible at scale. dLLM terms are ~1e-6 USD per reference saved and",
        "matter only if references cost about as little as a judge call.",
        "",
    ]

    # SciFact reference-quality variant --------------------------------------
    try:
        srows = scifact_rows(pi)
        report["scifact"] = srows
        md += ["## Reference-quality variant (SciFact, full frozen subset)", "",
               "Same model; reference quality itself varies. Routed acquires "
               "references for RF-accepted items only (153/380); Always-Grounded "
               "for every claim.", ""]
        md += fmt_rows(srows, pi) + [""]
        for cond in ("oracle_sentence", "bm25_3"):
            be = breakeven(srows, f"routed_{cond}", f"always_grounded_{cond}")
            md.append(f"- **routed_{cond}** preferred over **always_grounded_{cond}** "
                      f"iff {be_str(be)}")
        md.append("")
    except Exception as exc:
        md += [f"(SciFact variant skipped: {exc})", ""]

    md += [
        "## Assumptions and scope",
        "",
        "- Linear, risk-neutral utility; per-claim additivity; no distribution-free",
        "  guarantee is implied.",
        "- TA/FA are class-conditional rates measured on balanced 150/150 splits;",
        "  TP/FP reweighting by pi assumes those rates are stable in the class mix.",
        "- Break-even constants are point estimates from 10-split means; split-level",
        "  ranges are shown. Rates are specific to the evaluated panel, families,",
        "  and reference sources; recalibration is required after any model,",
        "  prompt, retrieval, or data change.",
        "",
    ]

    OUT_JSON.write_text(json.dumps(report, indent=2) + "\n")
    OUT_MD.write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
