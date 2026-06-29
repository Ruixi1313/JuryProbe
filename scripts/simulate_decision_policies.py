#!/usr/bin/env python3
"""Simulate deployment decision policies from frozen JuryProbe outputs.

This script uses already-collected reference-free judge outputs. It does not
make model calls. "Always Grounded" and the verifier branch of routed policies
are treated as oracle/strong-verifier upper bounds: the final decision equals
the gold label for escalated items.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

JUDGES = [
    "meta-llama/llama-3.1-8b-instruct",
    "qwen/qwen-2.5-7b-instruct",
    "google/gemma-3-12b-it",
]


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_rf_verdicts(path):
    by_item = {}
    for rec in load_jsonl(path):
        by_item.setdefault(rec["item_id"], {})[rec["judge"]] = rec["verdict"]
    return by_item


def gold_accept(item):
    return item["gold"] == "true"


def majority_accept(verdicts):
    return sum(1 for v in verdicts if v == "true") >= 2


def unanimous_true(verdicts):
    return all(v == "true" for v in verdicts)


def unanimous_agreement(verdicts):
    return len(verdicts) == len(JUDGES) and len(set(verdicts)) == 1 and verdicts[0] in {"true", "false"}


def metrics(items, decisions, escalated):
    clean = [it for it in items if not it["is_corrupted"]]
    corrupt = [it for it in items if it["is_corrupted"]]
    false_accept = sum(1 for it in corrupt if decisions[it["id"]]) / len(corrupt)
    true_accept = sum(1 for it in clean if decisions[it["id"]]) / len(clean)
    false_consensus = sum(
        1 for it in corrupt
        if decisions[it["id"]] and decisions.get(f"{it['id']}__unverified_false_consensus", False)
    ) / len(corrupt)
    n_escalated = sum(1 for it in items if escalated[it["id"]])
    return {
        "false_accept": false_accept,
        "true_accept": true_accept,
        "false_consensus": false_consensus,
        "escalation_rate": n_escalated / len(items),
        "extra_verifier_calls": n_escalated,
    }


def simulate(stem, data_path, rf_path, analysis_path):
    items = load_jsonl(data_path)
    rf = load_rf_verdicts(rf_path)
    analysis = json.loads(analysis_path.read_text())
    high_risk = (
        analysis["fn_only_corr"] > 0.15
        and analysis["detectable_residual_lift"] > 1.5
        and analysis["perm_p"] < 0.05
    )

    rows = []
    for policy in [
        "Reference-Free Majority",
        "Reference-Free Unanimous",
        "Always Grounded (Oracle Upper Bound)",
        "JuryProbe-Routed Accept Guardrail",
        "JuryProbe-Routed Agreement Guardrail",
    ]:
        decisions = {}
        escalated = {}
        for it in items:
            verdicts = [rf.get(it["id"], {}).get(j, "parse_fail") for j in JUDGES]
            rf_majority = majority_accept(verdicts)
            rf_unanimous_true = unanimous_true(verdicts)
            rf_agreement = unanimous_agreement(verdicts)

            if policy == "Reference-Free Majority":
                accept = rf_majority
                escalate = False
                unverified_false_consensus = it["is_corrupted"] and rf_unanimous_true
            elif policy == "Reference-Free Unanimous":
                accept = rf_unanimous_true
                escalate = False
                unverified_false_consensus = it["is_corrupted"] and rf_unanimous_true
            elif policy == "Always Grounded (Oracle Upper Bound)":
                accept = gold_accept(it)
                escalate = True
                unverified_false_consensus = False
            elif policy == "JuryProbe-Routed Accept Guardrail":
                escalate = bool(high_risk and rf_majority)
                accept = gold_accept(it) if escalate else rf_majority
                unverified_false_consensus = it["is_corrupted"] and rf_unanimous_true and not escalate
            else:
                escalate = bool(high_risk and rf_agreement)
                accept = gold_accept(it) if escalate else rf_majority
                unverified_false_consensus = it["is_corrupted"] and rf_unanimous_true and not escalate

            decisions[it["id"]] = accept
            decisions[f"{it['id']}__unverified_false_consensus"] = unverified_false_consensus
            escalated[it["id"]] = escalate
        row = {
            "stem": stem,
            "policy": policy,
            "panel_high_risk": high_risk,
            "risk_regime": "high-risk panel" if high_risk else "low-risk panel",
            **metrics(items, decisions, escalated),
        }
        rows.append(row)
    return {
        "stem": stem,
        "n_items": len(items),
        "n_clean": sum(1 for it in items if not it["is_corrupted"]),
        "n_corrupt": sum(1 for it in items if it["is_corrupted"]),
        "risk_definition": {
            "name": "High-Risk Panel",
            "fn_only_corr_gt": 0.15,
            "detectable_residual_lift_gt": 1.5,
            "perm_p_lt": 0.05,
            "note": "Panel-level risk regime, not a sample-level classifier.",
        },
        "routed_policy": {
            "primary_trigger": "panel is high-risk AND reference-free majority would accept",
            "appendix_trigger": "panel is high-risk AND the three reference-free judges unanimously agree",
            "verifier": "oracle/strong-verifier upper bound using gold labels for escalated items",
            "fallback": "reference-free majority for low-risk panels; keep RF reject decisions in high-risk panels",
        },
        "rows": rows,
    }


def markdown_table(results):
    lines = []
    lines.append("| Family | Policy | False Accept | True Accept | False Consensus | Escalation Rate | Extra Verifier Calls |")
    lines.append("|---|---|---:|---:|---:|---:|---:|")
    for result in results:
        family = result["stem"].split("_")[0].title()
        for row in result["rows"]:
            lines.append(
                f"| {family} | {row['policy']} | "
                f"{row['false_accept']:.3f} | {row['true_accept']:.3f} | "
                f"{row['false_consensus']:.3f} | {row['escalation_rate']:.3f} | "
                f"{row['extra_verifier_calls']} |"
            )
    return "\n".join(lines)


def main_markdown_table(results):
    main_policies = {
        "Reference-Free Majority",
        "Reference-Free Unanimous",
        "Always Grounded (Oracle Upper Bound)",
        "JuryProbe-Routed Accept Guardrail",
    }
    lines = []
    lines.append("| Family | Policy | False Accept | True Accept | False Consensus | Extra Verifier Calls |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for result in results:
        family = result["stem"].split("_")[0].title()
        for row in result["rows"]:
            if row["policy"] not in main_policies:
                continue
            lines.append(
                f"| {family} | {row['policy']} | "
                f"{row['false_accept']:.3f} | {row['true_accept']:.3f} | "
                f"{row['false_consensus']:.3f} | {row['extra_verifier_calls']} |"
            )
    return "\n".join(lines)


def qualitative_table():
    return "\n".join([
        "| Policy | False Accept | Extra Verifier Calls |",
        "|---|---|---|",
        "| Reference-Free Majority | High | 0 |",
        "| Reference-Free Unanimous | Medium | 0 |",
        "| Always Grounded | Low | High |",
        "| JuryProbe-Routed Accept Guardrail | Low | Medium |",
    ])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results/policy_simulation_summary.json")
    ap.add_argument("--md-out", default="docs/policy_simulation.md")
    args = ap.parse_args()

    configs = [
        {
            "stem": "number_corruption_pool_v3_n300",
            "data": ROOT / "data/frozen/number_v3/number_corruption_pool_v3_n300.jsonl",
            "rf": ROOT / "results/frozen/number_v3/number_corruption_pool_v3_n300_rf.jsonl",
            "analysis": ROOT / "results/frozen/number_v3/number_corruption_pool_v3_n300_analysis.json",
        },
        {
            "stem": "entity_corruption_pool_v4_n300",
            "data": ROOT / "data/frozen/v4/entity_corruption_pool_v4_n300.jsonl",
            "rf": ROOT / "results/frozen/v4/entity_corruption_pool_v4_n300_rf.jsonl",
            "analysis": ROOT / "results/frozen/v4/entity_corruption_pool_v4_n300_analysis.json",
        },
    ]

    results = [simulate(c["stem"], c["data"], c["rf"], c["analysis"]) for c in configs]
    out_path = ROOT / args.out
    md_path = ROOT / args.md_out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"results": results}, indent=2, ensure_ascii=False) + "\n")

    md = [
        "# JuryProbe Decision-Policy Simulation",
        "",
        "This simulation uses frozen Number v3 and Entity v4 reference-free judge outputs.",
        "`Always Grounded` and the verifier branch of routed policies are oracle/strong-verifier upper bounds using gold labels for escalated items.",
        "",
        "The High-Risk Panel definition is panel-level, not sample-level:",
        "",
        "- FN-only corr > 0.15",
        "- detectable residual lift > 1.5",
        "- permutation p < 0.05",
        "",
        "Primary guardrail policy: `JuryProbe-Routed Accept Guardrail` escalates only when the panel is high-risk and the reference-free majority would accept; otherwise it keeps RF reject decisions. This protects accept decisions while avoiding verifier calls on RF rejects.",
        "",
        "Appendix diagnostic policy: `JuryProbe-Routed Agreement Guardrail` escalates only unanimous agreement cases.",
        "",
        "## Qualitative Guardrail Summary",
        "",
        qualitative_table(),
        "",
        "## Main Policy Results",
        "",
        main_markdown_table(results),
        "",
        "## Full Policy Results",
        "",
        markdown_table(results),
        "",
    ]
    md_path.write_text("\n".join(md))
    print(json.dumps({"json": str(out_path.relative_to(ROOT)), "markdown": str(md_path.relative_to(ROOT))}, indent=2))
    print()
    print(markdown_table(results))


if __name__ == "__main__":
    main()
