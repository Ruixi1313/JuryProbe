#!/usr/bin/env python3
"""Evaluate a frozen second panel on grouped SciFact five-fold cross-fitting."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import statistics
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ENV_FILE = ROOT / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

from scripts.evaluate_guardrail_policies import grounded_prompt  # noqa: E402
from src.io_utils import append_jsonl  # noqa: E402
from src.judges import _call_openrouter, _parse_truth, judge_statement  # noqa: E402

ORIGINAL_PANEL = [
    "meta-llama/llama-3.1-8b-instruct",
    "qwen/qwen-2.5-7b-instruct",
    "google/gemma-3-12b-it",
]
SECOND_PANEL = [
    "meta-llama/llama-3.3-70b-instruct",
    "qwen/qwen-2.5-72b-instruct",
    "google/gemma-2-27b-it",
]
THRESHOLDS = {"fn_corr": 0.15, "lift": 1.5, "p": 0.05}
CLAIMS_PATH = Path("data/scifact_natural_n190.jsonl")
REFERENCES_PATH = Path("data/scifact_retrieval_refs.jsonl")
FOLDS_PATH = Path("frozen/scifact_second_panel_crossfit_v1/folds.json")
PERMUTATIONS = 3000
RF_MODE = "reference_free_second_panel_v1"
GROUNDED_MODE = "grounded_full_abstract_second_panel_v1"


class LatestCache:
    """Append-only cache whose latest record wins, allowing explicit retries."""

    def __init__(self, path: Path):
        self.path = path
        self.records: dict[tuple[str, str, str], dict] = {}
        self.lock = Lock()
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.records[(row["judge"], row["item_id"], row["mode"])] = row

    def get(self, judge: str, item_id: str, mode: str) -> dict | None:
        return self.records.get((judge, item_id, mode))

    def put(self, row: dict) -> None:
        key = (row["judge"], row["item_id"], row["mode"])
        with self.lock:
            append_jsonl(self.path, row)
            self.records[key] = row


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_safe(value):
    """Convert non-finite floats before writing strict JSON artifacts."""
    if isinstance(value, float) and not math.isfinite(value):
        return "inf" if value > 0 else "-inf"
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def valid(verdict: str | None) -> bool:
    return verdict in {"true", "false"}


def call_rf_with_retries(model: str, statement: str, retries: int) -> dict:
    last = None
    for attempt in range(retries + 1):
        result = judge_statement(model, statement)
        last = {
            "verdict": result.verdict,
            "raw_response": result.raw_response,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "attempt": attempt + 1,
        }
        if valid(result.verdict):
            return last
        time.sleep(1.0)
    return last or {"verdict": "parse_fail", "raw_response": "no attempt"}


def call_grounded_with_retries(model: str, reference: str, statement: str,
                               retries: int) -> dict:
    last = None
    for attempt in range(retries + 1):
        try:
            response = _call_openrouter(
                model, grounded_prompt(reference, statement),
                max_tokens=64, temperature=0.0,
            )
            message = response["choices"][0]["message"]["content"]
            usage = response.get("usage", {})
            last = {
                "verdict": _parse_truth(message),
                "raw_response": message,
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "attempt": attempt + 1,
            }
        except Exception as exc:  # noqa: BLE001
            last = {
                "verdict": "parse_fail",
                "raw_response": f"ERROR: {exc}",
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "attempt": attempt + 1,
            }
        if valid(last["verdict"]):
            return last
        time.sleep(1.0)
    return last or {"verdict": "parse_fail", "raw_response": "no attempt"}


def preflight(panel: list[str], retries: int) -> None:
    statement = "The integer 2 is greater than the integer 1."
    failures = []
    print("Transport-only preflight on one non-study statement per model:")
    for model in panel:
        result = call_rf_with_retries(model, statement, retries)
        print(f"  {model}: {result['verdict']}")
        if not valid(result.get("verdict")):
            failures.append(model)
    if failures:
        raise SystemExit(
            "preflight failed; abort the formal experiment without substituting models: "
            + ", ".join(failures)
        )


def run_calls(items: list[dict], panel: list[str], cache: LatestCache, mode: str,
              workers: int, retries: int, grounded: bool = False) -> None:
    todo = []
    for item in items:
        for judge in panel:
            row = cache.get(judge, item["id"], mode)
            if row is None or not valid(row.get("verdict")):
                todo.append((item, judge))
    print(f"{mode}: cached valid={len(items) * len(panel) - len(todo)}, to run={len(todo)}")

    def work(pair: tuple[dict, str]) -> tuple[dict, str, dict]:
        item, judge = pair
        if grounded:
            result = call_grounded_with_retries(
                judge, item["full_abstract"], item["statement"], retries)
        else:
            result = call_rf_with_retries(judge, item["statement"], retries)
        return item, judge, result

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(work, pair) for pair in todo]
        for future in as_completed(futures):
            item, judge, result = future.result()
            cache.put({
                "judge": judge,
                "item_id": item["id"],
                "mode": mode,
                "prior": None,
                "is_corrupted": item["is_corrupted"],
                **result,
            })
            done += 1
            if done % 100 == 0 or done == len(todo):
                print(f"  {done}/{len(todo)}")


def load_cache_verdicts(path: Path, panel: list[str], accepted_modes: set[str]) -> dict:
    verdicts: dict[str, dict[str, str]] = defaultdict(dict)
    for row in load_jsonl(path):
        if row.get("judge") in panel and row.get("mode") in accepted_modes:
            verdicts[row["item_id"]][row["judge"]] = row.get("verdict", "parse_fail")
    return dict(verdicts)


def cache_verdicts(cache: LatestCache, items: list[dict], panel: list[str],
                   mode: str) -> dict:
    verdicts: dict[str, dict[str, str]] = defaultdict(dict)
    for item in items:
        for judge in panel:
            row = cache.get(judge, item["id"], mode)
            verdicts[item["id"]][judge] = row.get("verdict", "missing") if row else "missing"
    return dict(verdicts)


def parse_failures(items: list[dict], verdicts: dict, panel: list[str]) -> dict:
    by_judge = {
        judge: sum(not valid(verdicts.get(item["id"], {}).get(judge)) for item in items)
        for judge in panel
    }
    return {"by_judge": by_judge, "total": sum(by_judge.values())}


def majority(vs: list[str]) -> bool:
    return sum(v == "true" for v in vs) >= 2


def pearson(x: list[int], y: list[int]) -> float:
    if not x:
        return 0.0
    mx, my = statistics.mean(x), statistics.mean(y)
    numerator = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    return numerator / (sx * sy) if sx and sy else 0.0


def risk_assessment(items: list[dict], verdicts: dict, panel: list[str],
                    seed: int, permutations: int) -> dict:
    false_items = [item for item in items if item["is_corrupted"]]
    miss = {
        judge: [int(verdicts[item["id"]][judge] == "true") for item in false_items]
        for judge in panel
    }
    pairwise = [
        pearson(miss[panel[a]], miss[panel[b]])
        for a in range(len(panel)) for b in range(a + 1, len(panel))
    ]
    fn_corr = statistics.mean(pairwise)
    all3_count = sum(all(miss[j][i] for j in panel) for i in range(len(false_items)))
    observed = all3_count / len(false_items)
    rng = random.Random(seed)
    nulls = []
    for _ in range(permutations):
        shuffled = {}
        for judge in panel:
            values = miss[judge][:]
            rng.shuffle(values)
            shuffled[judge] = values
        nulls.append(
            sum(all(shuffled[j][i] for j in panel) for i in range(len(false_items)))
            / len(false_items)
        )
    null_mean = statistics.mean(nulls)
    lift = observed / null_mean if null_mean else (0.0 if observed == 0 else float("inf"))
    p_value = (sum(value >= observed for value in nulls) + 1) / (permutations + 1)
    flagged = (
        fn_corr > THRESHOLDS["fn_corr"]
        and lift > THRESHOLDS["lift"]
        and p_value < THRESHOLDS["p"]
    )
    return {
        "n_false": len(false_items),
        "fn_corr": fn_corr,
        "pairwise_fn_corr": pairwise,
        "all3_count": all3_count,
        "all3_rate": observed,
        "null_mean": null_mean,
        "lift": lift,
        "p_value": p_value,
        "flagged_high_risk": flagged,
        "permutation_seed": seed,
        "permutations": permutations,
    }


def wilson(successes: int, n: int, z: float = 1.959963984540054) -> list[float]:
    if n == 0:
        return [0.0, 1.0]
    p = successes / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return [max(0.0, center - half), min(1.0, center + half)]


def policy_counts(items: list[dict], rf: dict, grounded: dict, panel: list[str],
                  flagged: bool) -> dict:
    counts = {
        "n_false": sum(item["is_corrupted"] for item in items),
        "n_clean": sum(not item["is_corrupted"] for item in items),
        "rf_false_accept": 0,
        "rf_clean_accept": 0,
        "rf_all3_false_consensus": 0,
        "ground_all_false_accept": 0,
        "ground_all_clean_accept": 0,
        "false_accepts_corrected": 0,
        "clean_accepts_lost": 0,
        "references_acquired": 0,
        "juryprobe_false_accept": 0,
        "juryprobe_clean_accept": 0,
        "juryprobe_references": 0,
        "references_avoided_by_juryprobe": 0,
    }
    for item in items:
        rf_votes = [rf[item["id"]][judge] for judge in panel]
        rf_accept = majority(rf_votes)
        if item["is_corrupted"]:
            counts["rf_false_accept"] += rf_accept
            counts["rf_all3_false_consensus"] += all(v == "true" for v in rf_votes)
        else:
            counts["rf_clean_accept"] += rf_accept

        ground_accept = False
        if rf_accept:
            counts["references_acquired"] += 1
            ground_votes = [grounded[item["id"]][judge] for judge in panel]
            ground_accept = majority(ground_votes)
        if item["is_corrupted"]:
            counts["ground_all_false_accept"] += ground_accept
            counts["false_accepts_corrected"] += rf_accept and not ground_accept
        else:
            counts["ground_all_clean_accept"] += ground_accept
            counts["clean_accepts_lost"] += rf_accept and not ground_accept

        juryprobe_accept = ground_accept if flagged and rf_accept else rf_accept
        counts["juryprobe_references"] += int(flagged and rf_accept)
        counts["references_avoided_by_juryprobe"] += int(not flagged and rf_accept)
        if item["is_corrupted"]:
            counts["juryprobe_false_accept"] += juryprobe_accept
        else:
            counts["juryprobe_clean_accept"] += juryprobe_accept
    return counts


def add_rates(counts: dict) -> dict:
    out = dict(counts)
    for prefix, numerator, denominator in [
        ("rf_false_accept", "rf_false_accept", "n_false"),
        ("rf_clean_accept", "rf_clean_accept", "n_clean"),
        ("rf_all3_false_consensus", "rf_all3_false_consensus", "n_false"),
        ("ground_all_false_accept", "ground_all_false_accept", "n_false"),
        ("ground_all_clean_accept", "ground_all_clean_accept", "n_clean"),
        ("false_accept_correction", "false_accepts_corrected", "n_false"),
        ("clean_accept_loss", "clean_accepts_lost", "n_clean"),
        ("juryprobe_false_accept", "juryprobe_false_accept", "n_false"),
        ("juryprobe_clean_accept", "juryprobe_clean_accept", "n_clean"),
    ]:
        n = counts[denominator]
        k = counts[numerator]
        out[f"{prefix}_rate"] = k / n if n else 0.0
        out[f"{prefix}_wilson95"] = wilson(k, n)
    return out


def sum_counts(rows: list[dict]) -> dict:
    keys = [key for key, value in rows[0].items() if isinstance(value, int)]
    return {key: sum(row[key] for row in rows) for key in keys}


def markdown(output: dict) -> str:
    lines = [
        "# SciFact Second-Panel Grouped Cross-Fit",
        "",
        f"Second panel: `{', '.join(output['second_panel'])}`",
        "",
        "| Panel | Flagged folds | RF FA | RF clean accept | RF all-3 FC | Ground-All-RF-Accepts FA | Ground-All-RF-Accepts clean accept | Corrected false | Lost clean | GAA references | JP references | JP references avoided |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key, label in [("original", "Original"), ("second", "Second")]:
        panel = output["panels"][key]
        pooled = panel["out_of_fold"]
        lines.append(
            f"| {label} | {panel['flagged_folds']}/5 | "
            f"{pooled['rf_false_accept_rate']:.3f} ({pooled['rf_false_accept']}/{pooled['n_false']}) | "
            f"{pooled['rf_clean_accept_rate']:.3f} ({pooled['rf_clean_accept']}/{pooled['n_clean']}) | "
            f"{pooled['rf_all3_false_consensus_rate']:.3f} ({pooled['rf_all3_false_consensus']}/{pooled['n_false']}) | "
            f"{pooled['ground_all_false_accept_rate']:.3f} | "
            f"{pooled['ground_all_clean_accept_rate']:.3f} | "
            f"{pooled['false_accepts_corrected']} | {pooled['clean_accepts_lost']} | "
            f"{pooled['references_acquired']} | {pooled['juryprobe_references']} | "
            f"{pooled['references_avoided_by_juryprobe']} |"
        )
    lines.extend([
        "",
        "## Pooled Out-of-Fold Rates and Wilson 95% Intervals",
        "",
        "| Panel | Metric | Events / denominator | Rate | Wilson 95% |",
        "|---|---|---:|---:|---:|",
    ])
    interval_metrics = [
        ("RF false accept", "rf_false_accept", "n_false"),
        ("RF clean accept", "rf_clean_accept", "n_clean"),
        ("RF all-3 false consensus", "rf_all3_false_consensus", "n_false"),
        ("Ground-All-RF-Accepts false accept", "ground_all_false_accept", "n_false"),
        ("Ground-All-RF-Accepts clean accept", "ground_all_clean_accept", "n_clean"),
        ("False accepts corrected", "false_accept_correction", "n_false"),
        ("Clean accepts lost", "clean_accept_loss", "n_clean"),
        ("JuryProbe false accept", "juryprobe_false_accept", "n_false"),
        ("JuryProbe clean accept", "juryprobe_clean_accept", "n_clean"),
    ]
    for key, label in [("original", "Original"), ("second", "Second")]:
        pooled = output["panels"][key]["out_of_fold"]
        for metric_label, prefix, denominator in interval_metrics:
            numerator = {
                "false_accept_correction": "false_accepts_corrected",
                "clean_accept_loss": "clean_accepts_lost",
            }.get(prefix, prefix)
            lo, hi = pooled[f"{prefix}_wilson95"]
            lines.append(
                f"| {label} | {metric_label} | {pooled[numerator]}/{pooled[denominator]} | "
                f"{pooled[f'{prefix}_rate']:.3f} | [{lo:.3f}, {hi:.3f}] |"
            )
    lines.extend(["", "## Fold-Level Calibration", ""])
    for key, label in [("original", "Original"), ("second", "Second")]:
        lines.extend([
            f"### {label} panel",
            "",
            "| Fold | Flagged | FN corr | All-3 count | Lift | p | RF FA | Ground-All-RF-Accepts FA | Corrected false | Lost clean | GAA refs | JP refs |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for row in output["panels"][key]["folds"]:
            risk, policy = row["calibration_risk"], row["deployment"]
            lift = "inf" if math.isinf(risk["lift"]) else f"{risk['lift']:.3f}"
            lines.append(
                f"| {row['fold']} | {int(risk['flagged_high_risk'])} | {risk['fn_corr']:.3f} | "
                f"{risk['all3_count']} | {lift} | {risk['p_value']:.4f} | "
                f"{policy['rf_false_accept']}/{policy['n_false']} | "
                f"{policy['ground_all_false_accept']}/{policy['n_false']} | "
                f"{policy['false_accepts_corrected']} | {policy['clean_accepts_lost']} | "
                f"{policy['references_acquired']} | {policy['juryprobe_references']} |"
            )
        lines.append("")
    lines.extend([
        "## Interpretation Boundary",
        "",
        "A non-flagged fold exercises the stand-down branch; it is not a safety certificate. "
        "Ground-All-RF-Accepts outcomes are actual grounded-panel decisions, never gold-label substitutions.",
    ])
    return "\n".join(lines) + "\n"


def evaluate_panel(name: str, items_by_id: dict[str, dict], folds: dict,
                   rf: dict, grounded: dict, panel: list[str], permutations: int) -> dict:
    fold_results = []
    for fold in folds["folds"]:
        calibration = [items_by_id[item_id] for item_id in fold["calibration_item_ids"]]
        deployment = [items_by_id[item_id] for item_id in fold["deployment_item_ids"]]
        risk = risk_assessment(calibration, rf, panel, fold["fold"], permutations)
        counts = policy_counts(deployment, rf, grounded, panel, risk["flagged_high_risk"])
        fold_results.append({
            "fold": fold["fold"],
            "calibration_risk": risk,
            "deployment": add_rates(counts),
        })
    pooled = add_rates(sum_counts([row["deployment"] for row in fold_results]))
    return {
        "name": name,
        "panel": panel,
        "flagged_folds": sum(row["calibration_risk"]["flagged_high_risk"] for row in fold_results),
        "folds": fold_results,
        "out_of_fold": pooled,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--second-rf-cache", default="results/scifact_second_panel_v1_rf.jsonl")
    ap.add_argument("--second-grounded-cache", default="results/scifact_second_panel_v1_grounded_full_abstract.jsonl")
    ap.add_argument("--original-rf-cache", default="results/scifact_natural_n190_rf.jsonl")
    ap.add_argument("--original-grounded-cache", default="results/scifact_retrieval_grounded.jsonl")
    ap.add_argument("--run-rf", action="store_true")
    ap.add_argument("--run-grounded", action="store_true")
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--out", default="results/scifact_second_panel_crossfit_v1_summary.json")
    ap.add_argument("--md-out", default="results/scifact_second_panel_crossfit_v1_summary.md")
    args = ap.parse_args()

    if (args.preflight or args.run_rf or args.run_grounded) and not os.environ.get("OPENROUTER_API_KEY"):
        raise SystemExit("OPENROUTER_API_KEY is required for model calls")
    if args.preflight:
        preflight(SECOND_PANEL, args.retries)
        if not args.run_rf and not args.run_grounded:
            return

    claims_path = ROOT / CLAIMS_PATH
    references_path = ROOT / REFERENCES_PATH
    folds_path = ROOT / FOLDS_PATH
    claims = load_jsonl(claims_path)
    refs = load_jsonl(references_path)
    refs_by_id = {row["item_id"]: row for row in refs}
    items = []
    for claim in claims:
        ref = refs_by_id[claim["id"]]
        items.append({
            **claim,
            "full_abstract": ref["refs"]["oracle_abstract"]["reference"],
        })
    items_by_id = {item["id"]: item for item in items}
    if len(items) != 380 or len(items_by_id) != 380:
        raise SystemExit("formal experiment requires exactly 380 unique SciFact items")
    if sum(item["is_corrupted"] for item in items) != 190:
        raise SystemExit("formal experiment requires exactly 190 false SciFact items")
    if sum(not item["is_corrupted"] for item in items) != 190:
        raise SystemExit("formal experiment requires exactly 190 clean SciFact items")
    if set(refs_by_id) != set(items_by_id):
        raise SystemExit("claims and reference artifacts contain different item IDs")
    if any(not item["full_abstract"].strip() for item in items):
        raise SystemExit("every formal-study item must have a non-empty full abstract")

    folds = json.loads(folds_path.read_text())
    if set(folds["item_to_fold"]) != set(items_by_id):
        raise SystemExit("fold artifact does not match the SciFact claim IDs")
    if folds.get("claims_sha256") != sha256(claims_path):
        raise SystemExit("SciFact claims changed after the fold artifact was frozen")
    if folds.get("references_sha256") != sha256(references_path):
        raise SystemExit("SciFact references changed after the fold artifact was frozen")
    if len(folds.get("folds", [])) != 5:
        raise SystemExit("formal experiment requires exactly five frozen folds")
    for fold in folds["folds"]:
        counts = (
            fold["n_deployment_clean"], fold["n_deployment_false"],
            fold["n_calibration_clean"], fold["n_calibration_false"],
        )
        if counts != (38, 38, 152, 152):
            raise SystemExit(f"unexpected frozen fold counts in fold {fold['fold']}: {counts}")

    second_rf_cache = LatestCache(ROOT / args.second_rf_cache)
    if args.run_rf:
        run_calls(items, SECOND_PANEL, second_rf_cache, RF_MODE,
                  args.workers, args.retries, grounded=False)
    second_rf = cache_verdicts(second_rf_cache, items, SECOND_PANEL, RF_MODE)
    second_rf_fail = parse_failures(items, second_rf, SECOND_PANEL)
    if second_rf_fail["total"]:
        raise SystemExit(
            f"second-panel RF analysis requires zero missing/parse failures: {second_rf_fail}"
        )

    accepted_items = [
        item for item in items
        if majority([second_rf[item["id"]][judge] for judge in SECOND_PANEL])
    ]
    second_grounded_cache = LatestCache(ROOT / args.second_grounded_cache)
    if args.run_grounded:
        run_calls(accepted_items, SECOND_PANEL, second_grounded_cache, GROUNDED_MODE,
                  args.workers, args.retries, grounded=True)
    second_grounded = cache_verdicts(
        second_grounded_cache, accepted_items, SECOND_PANEL, GROUNDED_MODE)
    second_grounded_fail = parse_failures(accepted_items, second_grounded, SECOND_PANEL)
    if second_grounded_fail["total"]:
        raise SystemExit(
            "second-panel grounded analysis requires zero missing/parse failures: "
            f"{second_grounded_fail}"
        )

    original_rf = load_cache_verdicts(
        ROOT / args.original_rf_cache, ORIGINAL_PANEL, {"reference_free", None})
    original_grounded = load_cache_verdicts(
        ROOT / args.original_grounded_cache,
        ORIGINAL_PANEL, {"grounded_oracle_abstract"})
    original_rf_fail = parse_failures(items, original_rf, ORIGINAL_PANEL)
    original_grounded_needed = [
        item for item in items
        if majority([original_rf.get(item["id"], {}).get(j, "parse_fail") for j in ORIGINAL_PANEL])
    ]
    original_grounded_fail = parse_failures(
        original_grounded_needed, original_grounded, ORIGINAL_PANEL)
    if original_grounded_fail["total"]:
        raise SystemExit(f"original full-abstract cache is incomplete: {original_grounded_fail}")
    # Preserve the submitted convention for the original panel's one cached RF
    # parse failure: it is a non-accept. Its count is reported explicitly.
    for item in items:
        for judge in ORIGINAL_PANEL:
            original_rf.setdefault(item["id"], {}).setdefault(judge, "parse_fail")

    output = {
        "version": "scifact_second_panel_crossfit_v1",
        "claims": str(CLAIMS_PATH),
        "claims_sha256": sha256(claims_path),
        "references": str(REFERENCES_PATH),
        "references_sha256": sha256(references_path),
        "folds": str(FOLDS_PATH),
        "folds_sha256": sha256(folds_path),
        "thresholds": THRESHOLDS,
        "permutations": PERMUTATIONS,
        "original_panel": ORIGINAL_PANEL,
        "second_panel": SECOND_PANEL,
        "parse_failures": {
            "original_rf": original_rf_fail,
            "original_grounded_needed": original_grounded_fail,
            "second_rf": second_rf_fail,
            "second_grounded_needed": second_grounded_fail,
        },
        "panels": {
            "original": evaluate_panel(
                "original", items_by_id, folds, original_rf, original_grounded,
                ORIGINAL_PANEL, PERMUTATIONS),
            "second": evaluate_panel(
                "second", items_by_id, folds, second_rf, second_grounded,
                SECOND_PANEL, PERMUTATIONS),
        },
        "evidence_note": (
            "Ground-All-RF-Accepts uses actual panel verdicts with the benchmark full abstract; "
            "no gold-label substitution is used."
        ),
    }
    out = ROOT / args.out
    md_out = ROOT / args.md_out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(json_safe(output), indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    )
    md_out.write_text(markdown(output))
    print(markdown(output))


if __name__ == "__main__":
    main()
