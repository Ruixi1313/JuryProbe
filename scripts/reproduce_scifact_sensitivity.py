#!/usr/bin/env python3
"""Recompute the recorded 95/95 SciFact calibration sensitivity from RF caches."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_cross_family_transfer import evaluate_family, load_rf
from scripts.evaluate_guardrail_policies import RISK_THRESHOLDS
from src.io_utils import load_jsonl


def main():
    data = "data/scifact_natural_n190.jsonl"
    cache = "results/scifact_natural_n190_rf.jsonl"
    items, rf = load_jsonl(ROOT / data), load_rf(ROOT / cache)
    seeds = list(range(1, 11))
    result = evaluate_family(items, rf, seeds, 95, 95, 3000)
    baseline = evaluate_family(items, rf, seeds, 150, 150, 3000)
    result["per_seed"] = [dict(seed=seed, **row) for seed, row in zip(seeds, result["per_seed"])]
    result.update(mode="scifact_calibration_overlap_sensitivity", family="SciFact-Natural",
                  data=data, rf_cache=cache, thresholds=RISK_THRESHOLDS, seeds=seeds,
                  permutations=3000, calib_clean=95, calib_corrupt=95,
                  calibration_overlap_fraction=95 / 190,
                  baseline_150x150=dict(high_risk_splits=baseline["high_risk_splits"],
                      fn_corr_mean=round(baseline["fn_corr_mean"], 3),
                      lift_mean=round(baseline["lift_mean"], 2),
                      calibration_overlap_fraction=round(150 / 190, 3)))
    result["purpose"] = "Sensitivity to calibration draw size (95/190 versus 150/190 per class). Repeated splits overlap and are not independent trials."
    (ROOT / "results/scifact_calib_sensitivity_95x95.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"SciFact 95/95: {result['high_risk_splits']}/10 flagged")


if __name__ == "__main__":
    main()
