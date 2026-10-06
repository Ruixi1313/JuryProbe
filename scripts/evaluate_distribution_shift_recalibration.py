#!/usr/bin/env python3
"""Run the frozen zero-API distribution-shift recalibration stress test."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evaluate_guardrail_policies import (  # noqa: E402
    JUDGES,
    RISK_THRESHOLDS,
    majority_accept,
    risk_assessment,
    unanimous_true,
)
from src.io_utils import load_jsonl  # noqa: E402


CONTROL = {
    "name": "Self-Contained-Contradiction",
    "data": "data/obvious_contradiction_control_v2_n300.jsonl",
    "rf_cache": "results/obvious_number_control_n300_rf.jsonl",
}

TARGETS = [
    {
        "name": "Number",
        "data": "data/number_corruption_pool_v3_n300.jsonl",
        "rf_cache": "results/number_corruption_pool_v3_n300_rf.jsonl",
    },
    {
        "name": "Entity",
        "data": "data/entity_corruption_pool_v4_n300.jsonl",
        "rf_cache": "results/entity_corruption_pool_v4_n300_rf.jsonl",
    },
    {
        "name": "SciFact",
        "data": "data/scifact_natural_n190.jsonl",
        "rf_cache": "results/scifact_natural_n190_rf.jsonl",
    },
]


def stable_seed(*parts: object) -> int:
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def load_rf(path: Path) -> dict[str, dict[str, str]]:
    by_item: dict[str, dict[str, str]] = defaultdict(dict)
    for rec in load_jsonl(path):
        if rec.get("mode") not in (None, "reference_free"):
            continue
        by_item[rec["item_id"]][rec["judge"]] = rec["verdict"]
    return dict(by_item)


def load_family(config: dict, required_per_class: int, complete_case: bool) -> dict:
    items = load_jsonl(ROOT / config["data"])
    rf = load_rf(ROOT / config["rf_cache"])
    ids = [item["id"] for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{config['name']}: duplicate item ids")
    missing = []
    parse_failures = 0
    for item_id in ids:
        for judge in JUDGES:
            verdict = rf.get(item_id, {}).get(judge)
            if verdict not in ("true", "false", "parse_fail"):
                missing.append((item_id, judge))
            elif verdict == "parse_fail":
                parse_failures += 1
    if missing:
        raise ValueError(f"{config['name']}: missing {len(missing)} cached verdicts")
    complete_items = [
        item
        for item in items
        if all(rf[item["id"]][judge] in ("true", "false") for judge in JUDGES)
    ]
    excluded_items = len(items) - len(complete_items)
    if complete_case:
        items = complete_items
    clean = [item for item in items if not item["is_corrupted"]]
    corrupt = [item for item in items if item["is_corrupted"]]
    if min(len(clean), len(corrupt)) < required_per_class:
        raise ValueError(
            f"{config['name']}: requires at least {required_per_class} items per class; "
            f"found {len(clean)} clean/{len(corrupt)} corrupt"
        )
    return {
        **config,
        "items": items,
        "rf": rf,
        "clean": clean,
        "corrupt": corrupt,
        "parse_failures": parse_failures,
        "complete_case_excluded_items": excluded_items,
    }


def shuffled(items: list[dict], *seed_parts: object) -> list[dict]:
    values = list(items)
    random.Random(stable_seed(*seed_parts)).shuffle(values)
    return values


def namespace(
    family_name: str,
    items: list[dict],
    rf: dict[str, dict[str, str]],
) -> tuple[list[dict], dict[str, dict[str, str]]]:
    namespaced_items = []
    namespaced_rf = {}
    for item in items:
        cloned = copy.deepcopy(item)
        cloned["source_item_id"] = item["id"]
        cloned["source_family"] = family_name
        cloned["id"] = f"{family_name}::{item['id']}"
        namespaced_items.append(cloned)
        namespaced_rf[cloned["id"]] = rf[item["id"]]
    return namespaced_items, namespaced_rf


def mix_count(total: int, proportion: float) -> int:
    return int(total * proportion + 0.5)


def combine(
    selections: list[tuple[str, list[dict], dict[str, dict[str, str]]]],
) -> tuple[list[dict], dict[str, dict[str, str]]]:
    items = []
    rf = {}
    for family_name, selected, verdicts in selections:
        namespaced_items, namespaced_rf = namespace(family_name, selected, verdicts)
        items.extend(namespaced_items)
        rf.update(namespaced_rf)
    return items, rf


def split_pools(control: dict, target: dict, seed: int, role_size: int) -> dict:
    control_clean = shuffled(control["clean"], "drift", seed, "control", "clean")
    control_corrupt = shuffled(control["corrupt"], "drift", seed, "control", "corrupt")
    target_corrupt = shuffled(target["corrupt"], "drift", seed, target["name"], "corrupt")
    return {
        "initial_clean": control_clean[:95],
        "evaluation_clean": control_clean[95:95 + role_size],
        "audit_clean": control_clean[95 + role_size:95 + 2 * role_size],
        "initial_control_corrupt": control_corrupt[:95],
        "evaluation_control_corrupt": control_corrupt[95:95 + role_size],
        "audit_control_corrupt": control_corrupt[95 + role_size:95 + 2 * role_size],
        "evaluation_target_corrupt": target_corrupt[:role_size],
        "audit_target_corrupt": target_corrupt[role_size:2 * role_size],
    }


def take_mixture(
    control_items: list[dict],
    target_items: list[dict],
    total: int,
    proportion: float,
) -> tuple[list[dict], int, int]:
    target_n = mix_count(total, proportion)
    control_n = total - target_n
    return control_items[:control_n] + target_items[:target_n], control_n, target_n


def rf_metrics(items: list[dict], rf: dict[str, dict[str, str]]) -> dict:
    clean = [item for item in items if not item["is_corrupted"]]
    corrupt = [item for item in items if item["is_corrupted"]]
    majority = {}
    unanimous = {}
    for item in items:
        verdicts = [rf[item["id"]][judge] for judge in JUDGES]
        majority[item["id"]] = majority_accept(verdicts)
        unanimous[item["id"]] = unanimous_true(verdicts)
    return {
        "n_clean": len(clean),
        "n_corrupt": len(corrupt),
        "rf_majority_false_accept": sum(majority[item["id"]] for item in corrupt) / len(corrupt),
        "rf_majority_true_accept": sum(majority[item["id"]] for item in clean) / len(clean),
        "rf_unanimous_false_consensus": sum(unanimous[item["id"]] for item in corrupt) / len(corrupt),
        "majority_accepts": sum(majority.values()),
    }


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def sample_std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = mean(values)
    return math.sqrt(sum((value - avg) ** 2 for value in values) / (len(values) - 1))


def finite_mean(values: list[float]) -> float | None:
    finite = [value for value in values if math.isfinite(value)]
    return mean(finite) if finite else None


def aggregate(rows: list[dict]) -> dict:
    lifts = [row["recalibration_risk"]["residual_lift"] for row in rows]
    return {
        "n_splits": len(rows),
        "initial_flagged_splits": sum(row["initial_risk"]["high_risk"] for row in rows),
        "recalibration_flagged_splits": sum(row["recalibration_risk"]["high_risk"] for row in rows),
        "fn_corr_mean": mean([row["recalibration_risk"]["fn_corr"] for row in rows]),
        "lift_finite_mean": finite_mean(lifts),
        "lift_infinite_splits": sum(not math.isfinite(value) for value in lifts),
        "p_value_mean": mean([row["recalibration_risk"]["p_value"] for row in rows]),
        "rf_false_accept_mean": mean([row["evaluation_metrics"]["rf_majority_false_accept"] for row in rows]),
        "rf_false_accept_std": sample_std([row["evaluation_metrics"]["rf_majority_false_accept"] for row in rows]),
        "rf_true_accept_mean": mean([row["evaluation_metrics"]["rf_majority_true_accept"] for row in rows]),
        "rf_unanimous_fc_mean": mean([row["evaluation_metrics"]["rf_unanimous_false_consensus"] for row in rows]),
        "routed_claims_after_recalibration_mean": mean([
            row["evaluation_metrics"]["majority_accepts"]
            if row["recalibration_risk"]["high_risk"] else 0
            for row in rows
        ]),
    }


def fmt(value: float | None, digits: int = 3) -> str:
    if value is None:
        return "NA"
    return f"{value:.{digits}f}"


def markdown(output: dict) -> str:
    lines = [
        "# Distribution-Shift Recalibration Stress Test v1",
        "",
        "The initial calibration uses only the negative control. The shifted stream introduces a previously absent target corruption family. A separate labeled audit then recomputes the unchanged risk rule.",
        "",
        "| Target | Target share | Audit corrupt | Initial flagged | Recalibration flagged | FN corr | Lift | Stale RF FA | Stale all-3 FC | Routed claims after recalibration |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for target_name, target in output["targets"].items():
        for condition in target["conditions"]:
            a = condition["aggregate"]
            lift = fmt(a["lift_finite_mean"])
            if a["lift_infinite_splits"]:
                lift += f" (+inf in {a['lift_infinite_splits']})"
            lines.append(
                f"| {target_name} | {condition['target_proportion']:.0%} | "
                f"{condition['audit_per_class']} | {a['initial_flagged_splits']}/{a['n_splits']} | "
                f"{a['recalibration_flagged_splits']}/{a['n_splits']} | {fmt(a['fn_corr_mean'])} | "
                f"{lift} | {fmt(a['rf_false_accept_mean'])} ± {fmt(a['rf_false_accept_std'])} | "
                f"{fmt(a['rf_unanimous_fc_mean'])} | {fmt(a['routed_claims_after_recalibration_mean'], 1)} |"
            )
    lines += [
        "",
        "The stale RF columns describe the shifted evaluation stream while the initial stand-down label remains fixed. The routed-claims column is a branch-activation count only; no grounded outcome is inferred.",
        "",
        "## Interpretation",
        "",
        output["interpretation"],
        "",
        "This post-review stress test evaluates listed benchmark shifts after a new labeled audit. It does not establish zero-shot safety under arbitrary open-world drift.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", default="1,2,3,4,5,6,7,8,9,10")
    parser.add_argument("--proportions", default="0,0.1,0.25,0.5,1.0")
    parser.add_argument("--audit-sizes", default="25,50,95")
    parser.add_argument("--role-size", type=int, default=95)
    parser.add_argument("--complete-case", action="store_true")
    parser.add_argument("--permutations", type=int, default=3000)
    parser.add_argument("--out", default="results/distribution_shift_recalibration_v1_summary.json")
    parser.add_argument("--md-out", default="results/distribution_shift_recalibration_v1_summary.md")
    args = parser.parse_args()

    seeds = [int(value) for value in args.seeds.split(",") if value.strip()]
    proportions = [float(value) for value in args.proportions.split(",") if value.strip()]
    audit_sizes = [int(value) for value in args.audit_sizes.split(",") if value.strip()]
    if args.role_size > 95 or args.role_size < 1:
        raise ValueError("Role size must be between 1 and 95")
    if max(audit_sizes) > args.role_size or min(audit_sizes) < 1:
        raise ValueError("Audit sizes must be between 1 and the role size")
    if min(proportions) < 0 or max(proportions) > 1:
        raise ValueError("Target proportions must be in [0, 1]")

    control = load_family(
        CONTROL,
        required_per_class=95 + 2 * args.role_size,
        complete_case=args.complete_case,
    )
    targets = [
        load_family(
            config,
            required_per_class=2 * args.role_size,
            complete_case=args.complete_case,
        )
        for config in TARGETS
    ]
    output_targets = {}

    for target in targets:
        condition_rows: dict[tuple[float, int], list[dict]] = defaultdict(list)
        for seed in seeds:
            pools = split_pools(control, target, seed, args.role_size)
            initial_items, initial_rf = combine([
                (control["name"], pools["initial_clean"], control["rf"]),
                (control["name"], pools["initial_control_corrupt"], control["rf"]),
            ])
            initial_risk = risk_assessment(
                initial_items,
                initial_rf,
                seed=stable_seed("initial", seed) % (2**32),
                permutations=args.permutations,
            )

            for proportion in proportions:
                evaluation_corrupt, eval_control_n, eval_target_n = take_mixture(
                    pools["evaluation_control_corrupt"],
                    pools["evaluation_target_corrupt"],
                    args.role_size,
                    proportion,
                )
                evaluation_items, evaluation_rf = combine([
                    (control["name"], pools["evaluation_clean"], control["rf"]),
                    (control["name"], evaluation_corrupt[:eval_control_n], control["rf"]),
                    (target["name"], evaluation_corrupt[eval_control_n:], target["rf"]),
                ])
                evaluation_metrics = rf_metrics(evaluation_items, evaluation_rf)

                for audit_size in audit_sizes:
                    audit_corrupt, audit_control_n, audit_target_n = take_mixture(
                        pools["audit_control_corrupt"],
                        pools["audit_target_corrupt"],
                        audit_size,
                        proportion,
                    )
                    audit_items, audit_rf = combine([
                        (control["name"], pools["audit_clean"][:audit_size], control["rf"]),
                        (control["name"], audit_corrupt[:audit_control_n], control["rf"]),
                        (target["name"], audit_corrupt[audit_control_n:], target["rf"]),
                    ])
                    recalibration_risk = risk_assessment(
                        audit_items,
                        audit_rf,
                        seed=stable_seed("audit", target["name"], seed, proportion, audit_size) % (2**32),
                        permutations=args.permutations,
                    )
                    condition_rows[(proportion, audit_size)].append({
                        "seed": seed,
                        "initial_risk": initial_risk,
                        "target_proportion": proportion,
                        "evaluation_composition": {
                            "control_corrupt": eval_control_n,
                            "target_corrupt": eval_target_n,
                        },
                        "evaluation_metrics": evaluation_metrics,
                        "audit_per_class": audit_size,
                        "audit_composition": {
                            "control_corrupt": audit_control_n,
                            "target_corrupt": audit_target_n,
                        },
                        "recalibration_risk": recalibration_risk,
                    })

        conditions = []
        for (proportion, audit_size), rows in sorted(condition_rows.items()):
            conditions.append({
                "target_proportion": proportion,
                "audit_per_class": audit_size,
                "aggregate": aggregate(rows),
                "per_seed": rows,
            })
        output_targets[target["name"]] = {
            "n_items": len(target["items"]),
            "parse_fail_verdicts": target["parse_failures"],
            "complete_case_excluded_items": target["complete_case_excluded_items"],
            "conditions": conditions,
        }

    initial_flags = [
        condition["aggregate"]["initial_flagged_splits"]
        for target in output_targets.values()
        for condition in target["conditions"]
    ]
    if any(initial_flags):
        interpretation = (
            "The initial negative-control probe is not uniformly unflagged at the 95-item calibration size. "
            "Results must therefore be read as a calibration-size sensitivity rather than a clean stand-down-to-recalibration transition."
        )
    else:
        interpretation = (
            "The initial negative-control probe selects the no-routing branch in every seed. "
            "The table shows how stale reference-free risk and subsequent branch activation change as unseen target errors enter a separately audited stream."
        )

    output = {
        "mode": "distribution_shift_recalibration_stress_test",
        "status": "post_review_exploratory_stress_test",
        "protocol": "frozen/distribution_shift_recalibration_v1/PROTOCOL.md",
        "thresholds": RISK_THRESHOLDS,
        "seeds": seeds,
        "target_proportions": proportions,
        "initial_calibration_per_class": 95,
        "evaluation_per_class": args.role_size,
        "audit_sizes_per_class": audit_sizes,
        "permutations": args.permutations,
        "complete_case": args.complete_case,
        "control_parse_fail_verdicts": control["parse_failures"],
        "control_complete_case_excluded_items": control["complete_case_excluded_items"],
        "targets": output_targets,
        "interpretation": interpretation,
    }
    out_path = ROOT / args.out
    md_path = ROOT / args.md_out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    md_path.write_text(markdown(output))
    print(markdown(output))


if __name__ == "__main__":
    main()
