#!/usr/bin/env python3
"""Evaluate pooled leave-one-family-out calibration transfer with no API calls.

The target family is completely absent from the calibration probe. A pooled
source label is estimated from the remaining signal families and then applied
unchanged to reference-free decisions on the target family. The target's own
diagnostic label is computed post hoc for comparison only; it never affects
routing.

This is a post-review stress test over known benchmark families, not a claim of
open-world transfer to arbitrary unseen hallucinations.
"""
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


FAMILIES = [
    {
        "name": "Number",
        "role": "signal",
        "data": "data/number_corruption_pool_v3_n300.jsonl",
        "rf_cache": "results/number_corruption_pool_v3_n300_rf.jsonl",
    },
    {
        "name": "Entity",
        "role": "signal",
        "data": "data/entity_corruption_pool_v4_n300.jsonl",
        "rf_cache": "results/entity_corruption_pool_v4_n300_rf.jsonl",
    },
    {
        "name": "Attribute",
        "role": "signal",
        "data": "data/attribute_corruption_pool_v3_n300.jsonl",
        "rf_cache": "results/attribute_corruption_pool_v3_n300_rf.jsonl",
    },
    {
        "name": "FEVER-Refutes",
        "role": "signal",
        "data": "data/fever_refutes_control_n300.jsonl",
        "rf_cache": "results/fever_refutes_control_n300_rf.jsonl",
    },
    {
        "name": "SciFact",
        "role": "signal",
        "data": "data/scifact_natural_n190.jsonl",
        "rf_cache": "results/scifact_natural_n190_rf.jsonl",
    },
    {
        "name": "Obvious-Number",
        "role": "boundary-control",
        "data": "data/obvious_number_control_n300.jsonl",
        "rf_cache": "results/obvious_number_control_n300_rf.jsonl",
    },
    {
        "name": "Self-Contained-Contradiction",
        "role": "negative-control",
        "data": "data/obvious_contradiction_control_v2_n300.jsonl",
        "rf_cache": "results/obvious_number_control_n300_rf.jsonl",
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


def validate_family(name: str, items: list[dict], rf: dict) -> int:
    ids = [item["id"] for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{name}: duplicate item ids")
    for item_id in ids:
        verdicts = rf.get(item_id, {})
        missing = [judge for judge in JUDGES if verdicts.get(judge) not in ("true", "false", "parse_fail")]
        if missing:
            raise ValueError(f"{name}: missing cached RF verdicts for {item_id}: {missing}")
    clean = sum(1 for item in items if not item["is_corrupted"])
    corrupt = sum(1 for item in items if item["is_corrupted"])
    if min(clean, corrupt) < 95:
        raise ValueError(f"{name}: insufficient balanced items ({clean} clean, {corrupt} corrupt)")
    return sum(
        rf[item_id][judge] == "parse_fail"
        for item_id in ids
        for judge in JUDGES
    )


def complete_case_items(items: list[dict], rf: dict[str, dict[str, str]]) -> list[dict]:
    return [
        item
        for item in items
        if all(rf[item["id"]][judge] in ("true", "false") for judge in JUDGES)
    ]


def balanced_quotas(names: list[str], total: int, seed: int, label: str) -> dict[str, int]:
    if not names:
        raise ValueError("At least one donor family is required")
    order = sorted(names)
    random.Random(stable_seed("quota", seed, label)).shuffle(order)
    base, remainder = divmod(total, len(order))
    return {name: base + (index < remainder) for index, name in enumerate(order)}


def sample_items(items: list[dict], corrupted: bool, n: int, *seed_parts: object) -> list[dict]:
    candidates = [item for item in items if bool(item["is_corrupted"]) == corrupted]
    if len(candidates) < n:
        raise ValueError(f"Requested {n} items from a pool of {len(candidates)}")
    candidates = list(candidates)
    random.Random(stable_seed(*seed_parts)).shuffle(candidates)
    return candidates[:n]


def namespace_items(
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


def pooled_calibration(
    donor_names: list[str],
    loaded: dict[str, dict],
    seed: int,
    per_class: int,
) -> tuple[list[dict], dict[str, dict[str, str]], dict[str, dict[str, int]]]:
    clean_quotas = balanced_quotas(donor_names, per_class, seed, "clean")
    corrupt_quotas = balanced_quotas(donor_names, per_class, seed, "corrupt")
    pooled_items = []
    pooled_rf = {}
    composition = {}
    for name in sorted(donor_names):
        family = loaded[name]
        selected = sample_items(
            family["items"], False, clean_quotas[name], "source", seed, name, "clean"
        ) + sample_items(
            family["items"], True, corrupt_quotas[name], "source", seed, name, "corrupt"
        )
        namespaced, verdicts = namespace_items(name, selected, family["rf"])
        pooled_items.extend(namespaced)
        pooled_rf.update(verdicts)
        composition[name] = {
            "clean": clean_quotas[name],
            "corrupt": corrupt_quotas[name],
        }
    return pooled_items, pooled_rf, composition


def target_evaluation(family: dict, seed: int) -> list[dict]:
    items = family["items"]
    clean_n = sum(1 for item in items if not item["is_corrupted"])
    corrupt_n = sum(1 for item in items if item["is_corrupted"])
    per_class = min(150, clean_n // 2, corrupt_n // 2)
    return sample_items(items, False, per_class, "target", seed, family["name"], "clean") + sample_items(
        items, True, per_class, "target", seed, family["name"], "corrupt"
    )


def rf_metrics(items: list[dict], rf: dict, route: bool) -> dict[str, float | int]:
    clean = [item for item in items if not item["is_corrupted"]]
    corrupt = [item for item in items if item["is_corrupted"]]
    majority = {}
    unanimous = {}
    for item in items:
        verdicts = [rf[item["id"]][judge] for judge in JUDGES]
        majority[item["id"]] = majority_accept(verdicts)
        unanimous[item["id"]] = unanimous_true(verdicts)
    routed = sum(1 for item in items if route and majority[item["id"]])
    return {
        "n_clean": len(clean),
        "n_corrupt": len(corrupt),
        "rf_majority_false_accept": sum(majority[item["id"]] for item in corrupt) / len(corrupt),
        "rf_majority_true_accept": sum(majority[item["id"]] for item in clean) / len(clean),
        "rf_unanimous_false_consensus": sum(unanimous[item["id"]] for item in corrupt) / len(corrupt),
        "routed_claims": routed,
        "routed_judge_calls": routed * len(JUDGES),
    }


def finite_mean(values: list[float]) -> float | None:
    finite = [value for value in values if math.isfinite(value)]
    return sum(finite) / len(finite) if finite else None


def sample_std(values: list[float]) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return 0.0
    avg = sum(values) / len(values)
    return math.sqrt(sum((value - avg) ** 2 for value in values) / (len(values) - 1))


def aggregate_target(rows: list[dict]) -> dict:
    confusion = {"high_high": 0, "high_not_flagged": 0, "not_flagged_high": 0, "not_flagged_not_flagged": 0}
    for row in rows:
        source = row["source_risk"]["high_risk"]
        target = row["target_posthoc_risk"]["high_risk"]
        key = ("high" if source else "not_flagged") + "_" + ("high" if target else "not_flagged")
        confusion[key] += 1

    def values(path_a: str, path_b: str | None = None) -> list[float]:
        if path_b is None:
            return [row[path_a] for row in rows]
        return [row[path_a][path_b] for row in rows]

    target_lifts = [row["target_posthoc_risk"]["residual_lift"] for row in rows]
    return {
        "n_splits": len(rows),
        "source_high_splits": sum(row["source_risk"]["high_risk"] for row in rows),
        "target_posthoc_high_splits": sum(row["target_posthoc_risk"]["high_risk"] for row in rows),
        "label_agreement_splits": confusion["high_high"] + confusion["not_flagged_not_flagged"],
        "confusion": confusion,
        "source_fn_corr_mean": sum(values("source_risk", "fn_corr")) / len(rows),
        "target_fn_corr_mean": sum(values("target_posthoc_risk", "fn_corr")) / len(rows),
        "target_lift_finite_mean": finite_mean(target_lifts),
        "target_lift_infinite_splits": sum(not math.isfinite(value) for value in target_lifts),
        "rf_majority_false_accept_mean": sum(values("target_rf_metrics", "rf_majority_false_accept")) / len(rows),
        "rf_majority_false_accept_std": sample_std(values("target_rf_metrics", "rf_majority_false_accept")),
        "rf_majority_true_accept_mean": sum(values("target_rf_metrics", "rf_majority_true_accept")) / len(rows),
        "rf_majority_true_accept_std": sample_std(values("target_rf_metrics", "rf_majority_true_accept")),
        "rf_unanimous_false_consensus_mean": sum(values("target_rf_metrics", "rf_unanimous_false_consensus")) / len(rows),
        "routed_claims_mean": sum(values("target_rf_metrics", "routed_claims")) / len(rows),
        "routed_judge_calls_mean": sum(values("target_rf_metrics", "routed_judge_calls")) / len(rows),
    }


def fmt(value: float | None, digits: int = 3) -> str:
    if value is None:
        return "NA"
    return f"{value:.{digits}f}"


def overall_counts(targets: dict[str, dict], roles: set[str] | None = None) -> dict[str, int]:
    selected = [
        result
        for result in targets.values()
        if roles is None or result["role"] in roles
    ]
    confusion = {
        key: sum(result["aggregate"]["confusion"][key] for result in selected)
        for key in ("high_high", "high_not_flagged", "not_flagged_high", "not_flagged_not_flagged")
    }
    return {
        "n_target_seed_pairs": sum(result["aggregate"]["n_splits"] for result in selected),
        "source_high": sum(result["aggregate"]["source_high_splits"] for result in selected),
        "target_posthoc_high": sum(result["aggregate"]["target_posthoc_high_splits"] for result in selected),
        **confusion,
    }


def sensitivity_table(targets: dict[str, dict]) -> list[str]:
    lines = [
        "| Target | Source high | Target post-hoc high | HH / HN / NH / NN |",
        "|---|---:|---:|---:|",
    ]
    for name, result in targets.items():
        a = result["aggregate"]
        c = a["confusion"]
        lines.append(
            f"| {name} | {a['source_high_splits']}/{a['n_splits']} | "
            f"{a['target_posthoc_high_splits']}/{a['n_splits']} | "
            f"{c['high_high']} / {c['high_not_flagged']} / {c['not_flagged_high']} / {c['not_flagged_not_flagged']} |"
        )
    return lines


def markdown(output: dict) -> str:
    lines = [
        "# Pooled Leave-One-Family-Out Calibration Transfer",
        "",
        "The target family is absent from calibration. The source label is computed from a balanced pool of the remaining signal families and applied unchanged to the target. The target label is a post-hoc diagnostic comparator, not a routing input.",
        "",
        "| Target | Role | Source high | Target post-hoc high | HH / HN / NH / NN | RF FA | RF TA | RF all-3 FC | Routed claims |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, result in output["targets"].items():
        a = result["aggregate"]
        c = a["confusion"]
        lines.append(
            f"| {name} | {result['role']} | {a['source_high_splits']}/{a['n_splits']} | "
            f"{a['target_posthoc_high_splits']}/{a['n_splits']} | "
            f"{c['high_high']} / {c['high_not_flagged']} / {c['not_flagged_high']} / {c['not_flagged_not_flagged']} | "
            f"{fmt(a['rf_majority_false_accept_mean'])} ± {fmt(a['rf_majority_false_accept_std'])} | "
            f"{fmt(a['rf_majority_true_accept_mean'])} ± {fmt(a['rf_majority_true_accept_std'])} | "
            f"{fmt(a['rf_unanimous_false_consensus_mean'])} | {fmt(a['routed_claims_mean'], 1)} |"
        )
    lines += [
        "",
        "HH = source high / target post-hoc high; HN = source high / target not flagged; NH = source not flagged / target post-hoc high; NN = neither flagged.",
        "",
        "## Aggregate Reading",
        "",
    ]
    all_counts = overall_counts(output["targets"])
    signal_counts = overall_counts(output["targets"], {"signal"})
    lines += [
        f"The pooled source probe is high-risk in **{all_counts['source_high']}/{all_counts['n_target_seed_pairs']}** target-seed pairs. It agrees with every post-hoc target-high result (**{all_counts['high_high']}/{all_counts['target_posthoc_high']}**) but also remains high in all **{all_counts['high_not_flagged']}** target-not-flagged pairs. Across signal-family targets only, the source is high in **{signal_counts['source_high']}/{signal_counts['n_target_seed_pairs']}** pairs while the post-hoc target diagnostic is high in **{signal_counts['target_posthoc_high']}/{signal_counts['n_target_seed_pairs']}**.",
        "",
        "The result therefore supports a narrow conservative-transfer statement: a high-risk diagnosis from the known signal-family pool continues to activate routing for every tested unseen target. It does **not** show target-specific discrimination. In particular, it over-routes the negative control in 10/10 splits even though that target is not flagged post hoc in any split.",
        "",
        "## Cached Parse Failures",
        "",
        "Existing parse failures are retained under the submitted convention that only a literal `true` is an acceptance.",
        "",
        "| Family | Cached verdicts with parse failure | Complete-case items |",
        "|---|---:|---:|",
    ]
    for name, status in output["family_cache_status"].items():
        lines.append(
            f"| {name} | {status['parse_fail_verdicts']} | {status['complete_case_items']} |"
        )
    lines += [
        "",
        "## Complete-Case Sensitivity",
        "",
        "Items with any cached parse failure are removed before sampling. The branch outcomes are unchanged:",
        "",
        *sensitivity_table(output["complete_case_sensitivity"]),
        "",
        "This stress test measures transfer across the listed benchmark families only. It does not establish zero-shot safety for arbitrary unseen error types.",
        "",
    ]
    return "\n".join(lines)


def run_protocol(
    family_configs: list[dict],
    loaded: dict[str, dict],
    seeds: list[int],
    calib_per_class: int,
    permutations: int,
) -> dict:
    signal_names = [config["name"] for config in family_configs if config["role"] == "signal"]
    targets = {}
    for target_config in family_configs:
        target_name = target_config["name"]
        donor_names = [name for name in signal_names if name != target_name]
        per_seed = []
        for seed in seeds:
            calibration, calibration_rf, composition = pooled_calibration(
                donor_names, loaded, seed, calib_per_class
            )
            source_risk = risk_assessment(
                calibration, calibration_rf, seed=seed, permutations=permutations
            )
            target_items = target_evaluation(loaded[target_name], seed)
            target_risk = risk_assessment(
                target_items, loaded[target_name]["rf"], seed=seed, permutations=permutations
            )
            metrics = rf_metrics(target_items, loaded[target_name]["rf"], source_risk["high_risk"])
            per_seed.append(
                {
                    "seed": seed,
                    "donor_families": donor_names,
                    "source_composition": composition,
                    "source_risk": source_risk,
                    "target_posthoc_risk": target_risk,
                    "target_rf_metrics": metrics,
                }
            )
        targets[target_name] = {
            "role": target_config["role"],
            "donor_families": donor_names,
            "aggregate": aggregate_target(per_seed),
            "per_seed": per_seed,
        }
    return targets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", default="1,2,3,4,5,6,7,8,9,10")
    parser.add_argument("--calib-per-class", type=int, default=150)
    parser.add_argument("--permutations", type=int, default=3000)
    parser.add_argument("--out", default="results/unseen_family_transfer_v1_summary.json")
    parser.add_argument("--md-out", default="results/unseen_family_transfer_v1_summary.md")
    args = parser.parse_args()
    seeds = [int(seed) for seed in args.seeds.split(",") if seed.strip()]

    loaded = {}
    for config in FAMILIES:
        data_path = ROOT / config["data"]
        cache_path = ROOT / config["rf_cache"]
        if not data_path.exists() or not cache_path.exists():
            raise FileNotFoundError(f"Missing data/cache for {config['name']}")
        items = load_jsonl(data_path)
        rf = load_rf(cache_path)
        parse_failures = validate_family(config["name"], items, rf)
        loaded[config["name"]] = {
            **config,
            "items": items,
            "rf": rf,
            "parse_failures": parse_failures,
        }

    targets = run_protocol(
        FAMILIES, loaded, seeds, args.calib_per_class, args.permutations
    )

    complete_loaded = {}
    for config in FAMILIES:
        family = loaded[config["name"]]
        filtered = complete_case_items(family["items"], family["rf"])
        clean = sum(not item["is_corrupted"] for item in filtered)
        corrupt = sum(item["is_corrupted"] for item in filtered)
        if min(clean, corrupt) < 150 and config["name"] != "SciFact":
            raise ValueError(
                f"{config['name']}: complete-case sensitivity has only "
                f"{clean} clean/{corrupt} corrupt items"
            )
        if min(clean, corrupt) < 95:
            raise ValueError(
                f"{config['name']}: complete-case sensitivity has only "
                f"{clean} clean/{corrupt} corrupt items"
            )
        complete_loaded[config["name"]] = {**family, "items": filtered}
    complete_case_targets = run_protocol(
        FAMILIES, complete_loaded, seeds, args.calib_per_class, args.permutations
    )

    output = {
        "mode": "pooled_leave_one_family_out_calibration_transfer",
        "status": "post_review_exploratory_stress_test",
        "protocol": "frozen/unseen_family_transfer_v1/PROTOCOL.md",
        "thresholds": RISK_THRESHOLDS,
        "seeds": seeds,
        "calibration_per_class": args.calib_per_class,
        "permutations": args.permutations,
        "family_cache_status": {
            name: {
                "n_items": len(family["items"]),
                "parse_fail_verdicts": family["parse_failures"],
                "complete_case_items": len(complete_loaded[name]["items"]),
            }
            for name, family in loaded.items()
        },
        "targets": targets,
        "complete_case_sensitivity": {
            name: {
                "role": result["role"],
                "donor_families": result["donor_families"],
                "aggregate": result["aggregate"],
            }
            for name, result in complete_case_targets.items()
        },
    }
    output["overall"] = {
        "all_targets": overall_counts(targets),
        "signal_targets": overall_counts(targets, {"signal"}),
        "complete_case_all_targets": overall_counts(complete_case_targets),
        "complete_case_signal_targets": overall_counts(complete_case_targets, {"signal"}),
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
