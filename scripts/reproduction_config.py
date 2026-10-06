"""Explicit inputs and commands for the public, cached reproduction release."""
from __future__ import annotations


def job(name, script, output, *, args=(), expected=None, suite="core", ignore=()):
    return dict(name=name, script="scripts/" + script + ".py", args=list(args),
                output=output, expected=expected or output, suite=suite,
                ignore=list(ignore))


JOBS = [
    job("number_diagnostic", "analyze_dataset", "results/number_corruption_pool_v3_n300_analysis.json",
        args=["number_corruption_pool_v3_n300"]),
    job("entity_diagnostic", "analyze_dataset", "results/entity_corruption_pool_v4_n300_analysis.json",
        args=["entity_corruption_pool_v4_n300"]),
    job("attribute_diagnostic", "analyze_dataset", "results/attribute_corruption_pool_v3_n300_analysis.json",
        args=["attribute_corruption_pool_v3_n300"]),
    job("heldout_routing", "evaluate_guardrail_multiseed", "results/guardrail_heldout_multiseed/summary.json"),
    job("routing_baselines", "evaluate_guardrail_baselines", "results/guardrail_baselines_v1/summary.json"),
    job("ground_all_accepts", "evaluate_ground_all_accepts_baseline", "results/ground_all_accepts_baseline_summary.json"),
    job("cross_family", "evaluate_cross_family_transfer", "results/cross_family_transfer_summary.json"),
    job("scifact_calibration_sensitivity", "reproduce_scifact_sensitivity", "results/scifact_calib_sensitivity_95x95.json"),
    job("negative_control", "evaluate_low_risk_control_rf", "results/obvious_contradiction_control_v2_n300_low_risk_summary.json",
        args=["--data", "data/obvious_contradiction_control_v2_n300.jsonl",
              "--family", "ObvContradiction-Control-v2",
              "--out", "results/obvious_contradiction_control_v2_n300_low_risk_summary.json",
              "--md-out", "results/obvious_contradiction_control_v2_n300_low_risk_summary.md"]),
    job("scifact_references", "run_scifact_retrieval_grounded", "results/scifact_retrieval_grounded_summary.json",
        args=["--cache-only"], ignore=["new_api_calls_this_run", "prompt_tokens_this_run", "completion_tokens_this_run"]),
    job("scifact_heldout", "evaluate_scifact_heldout_policy", "results/scifact_heldout_policy_summary.json"),
    job("utility", "evaluate_utility_analysis", "results/utility_analysis_summary.json"),
    job("creak", "evaluate_low_risk_control_rf", "results/creak_natural_standdown_v1_n300_summary.json", suite="extended",
        args=["--data", "data/creak_natural_standdown_v1_n300.jsonl",
              "--rf-cache", "results/creak_natural_standdown_v1_n300_rf.jsonl",
              "--family", "CREAK-Natural-Standdown-v1",
              "--out", "results/creak_natural_standdown_v1_n300_summary.json",
              "--md-out", "results/creak_natural_standdown_v1_n300_summary.md"]),
    job("second_panel", "evaluate_scifact_second_panel_crossfit", "results/scifact_second_panel_crossfit_v1_summary.json", suite="extended"),
    job("distribution_shift", "evaluate_distribution_shift_recalibration", "results/distribution_shift_recalibration_v1_summary.json", suite="extended"),
    job("distribution_shift_complete_case", "evaluate_distribution_shift_recalibration", "results/distribution_shift_recalibration_v1_complete_case.json", suite="extended",
        args=["--complete-case", "--role-size", "94", "--audit-sizes", "25,50,94",
              "--out", "results/distribution_shift_recalibration_v1_complete_case.json",
              "--md-out", "results/distribution_shift_recalibration_v1_complete_case.md"]),
    job("unseen_family", "evaluate_unseen_family_transfer", "results/unseen_family_transfer_v1_summary.json", suite="extended"),
    job("threshold_sensitivity", "analyze_threshold_sensitivity", "results/threshold_sensitivity_analysis.json", suite="extended"),
    job("capability_slice", "evaluate_strong_judge_slice", "results/frozen/strong_judge_slice_v1/summary.json", suite="extended"),
]

STEMS = ["number_corruption_pool_v3_n300", "entity_corruption_pool_v4_n300", "attribute_corruption_pool_v3_n300"]
INPUTS = [f"data/{stem}.jsonl" for stem in STEMS]
INPUTS += [f"results/{stem}_{kind}.jsonl" for stem in STEMS for kind in ("rf", "gpt4o", "grounded")]
INPUTS += [
    "data/frozen/number_v3/number_corruption_pool_v3_n300.jsonl",
    "data/frozen/v4/entity_corruption_pool_v4_n300.jsonl",
    "results/frozen/number_v3/number_corruption_pool_v3_n300_rf.jsonl",
    "results/frozen/v4/entity_corruption_pool_v4_n300_rf.jsonl",
    "results/guardrail_grounded/number_corruption_pool_v3_n300_grounded_verifier_validated.jsonl",
    "results/guardrail_grounded/entity_corruption_pool_v4_n300_grounded_verifier_validated.jsonl",
    "results/guardrail_grounded/validated_cache_manifest.json",
    "data/obvious_number_control_n300.jsonl",
    "data/obvious_contradiction_control_v2_n300.jsonl",
    "results/obvious_number_control_n300_rf.jsonl",
    "results/guardrail_grounded/obvious_contradiction_control_v2_n300_grounded_verifier.jsonl",
    "data/fever_refutes_control_n300.jsonl",
    "data/fever_refutes_control_n300.manifest.json",
    "results/fever_refutes_control_n300_rf.jsonl",
    "data/scifact_natural_n190.jsonl",
    "data/scifact_natural_n190.manifest.json",
    "data/scifact_natural_n190_grounded.jsonl",
    "data/scifact_natural_n190_grounded.manifest.json",
    "data/scifact_retrieval_refs.jsonl",
    "data/scifact_retrieval_refs.manifest.json",
    "results/scifact_natural_n190_rf.jsonl",
    "results/scifact_natural_n190_grounded_rf.jsonl",
    "results/scifact_retrieval_grounded.jsonl",
    "data/creak_natural_standdown_v1_n300.jsonl",
    "data/creak_natural_standdown_v1_n300.manifest.json",
    "results/creak_natural_standdown_v1_n300_rf.jsonl",
    "results/scifact_second_panel_v1_rf.jsonl",
    "results/scifact_second_panel_v1_grounded_full_abstract.jsonl",
    "results/frozen/strong_judge_slice_v1/number_v3_capability_rf.jsonl",
]

PUBLIC_SCRIPTS = sorted({j["script"] for j in JOBS} | {
    "scripts/_offline_reproduction.py", "scripts/reproduce.py",
    "scripts/reproduction_config.py", "scripts/build_public_release.py",
    "scripts/evaluate_guardrail_policies.py", "scripts/foil_grounded.py",
    "scripts/build_fever_claim_pool.py", "scripts/build_number_from_pool.py",
    "scripts/build_entity_from_pool.py", "scripts/build_attribute_pool.py",
    "scripts/build_attribute_from_pool.py", "scripts/build_natural_family.py",
    "scripts/build_fever_refutes_control.py", "scripts/build_obvious_number_control.py",
    "scripts/build_creak_natural_standdown.py", "scripts/build_scifact_grounded_refs.py",
    "scripts/build_scifact_retrieval_refs.py", "scripts/build_scifact_grouped_folds.py",
    "scripts/run_control_grounded_verifier.py", "scripts/run_scifact_grounded.py",
    "scripts/validate_grounded_cache.py", "scripts/summarize_author_audit.py",
    "scripts/reproduce_scifact_sensitivity.py",
})

PUBLIC_FILES = PUBLIC_SCRIPTS + [
    "src/__init__.py", "src/correlation.py", "src/io_utils.py", "src/judges.py",
    "README.md", "LICENSE", "CITATION.cff", "requirements.txt",
    "docs/reproducibility.md", "docs/guardrail_policy_definition_v1.md",
    "tests/test_reproduction.py",
    "frozen/creak_natural_standdown_v1/PROTOCOL.md",
    "frozen/distribution_shift_recalibration_v1/PROTOCOL.md",
    "frozen/unseen_family_transfer_v1/PROTOCOL.md",
    "frozen/scifact_second_panel_crossfit_v1/PROTOCOL.md",
    "frozen/scifact_second_panel_crossfit_v1/FREEZE_MANIFEST.json",
    "frozen/scifact_second_panel_crossfit_v1/folds.json",
    "audits/v3/number_corruption_pool_v3_n300_author_audit_seed20260608.md",
    "audits/v4/entity_corruption_pool_v4_n300_author_audit_seed20260608.md",
]
