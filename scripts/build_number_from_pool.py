#!/usr/bin/env python3
"""Build pool-based Number corruption data.

Frozen input:
  data/frozen/v1/number_pool_v1.jsonl

Output:
  data/number_corruption_pool_<version>_n300.jsonl
  results/number_corruption_pool_<version>_n300_build_attempts.jsonl
  results/number_corruption_pool_<version>_n300_build_manifest.json

Sampling is fixed-seed and pool-based. Number corruption is deterministic local
editing; GPT-4o is used only as a hard-gate validator, not to select the pool.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ENV_FILE = ROOT / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, vv = line.split("=", 1)
            os.environ.setdefault(k.strip(), vv.strip())

from src.judges import _call_openrouter

GPT4O = "openai/gpt-4o"

VAL_CLEAN = """You are the CORRUPTION VALIDATOR. Given ONE claim, return ONLY JSON:
{{"original_supported": true/false, "original_is_atomic_fact": true/false,
  "fluent_no_artifact": true/false, "canonical_value": "<accepted value/range>"}}
- original_supported: is it factually TRUE?
- original_is_atomic_fact: a single precise objectively verifiable claim?
- fluent_no_artifact: fluent, natural English with no tampering artifact.

CLAIM: {claim}"""

VAL_CORRUPT = """You are the CORRUPTION VALIDATOR. Given an ORIGINAL true claim
and a MODIFIED version where exactly one number was changed, return ONLY JSON
with EXACTLY:
{{"original_supported": true/false, "original_is_atomic_fact": true/false,
  "corrupted_is_false": true/false, "within_acceptable_range": true/false,
  "single_number_change_only": true/false, "fluent_no_artifact": true/false,
  "canonical_value": "<accepted value/range>"}}
- original_supported: is the ORIGINAL factually TRUE?
- original_is_atomic_fact: a single precise objectively verifiable claim?
- corrupted_is_false: is the MODIFIED factually FALSE?
- within_acceptable_range: does the MODIFIED number still fall within the
  canonical value or an accepted approximation? If yes, the corruption is not
  usable.
- single_number_change_only: was exactly one number changed, with entities,
  relations, dates other than the target number, and surrounding wording
  preserved?
- fluent_no_artifact: modified reads naturally, no tampering artifact.

ORIGINAL: {original}
MODIFIED: {modified}"""

HEDGES = (
    "about", "approximately", "approx", "roughly", "around", "nearly",
    "almost", "up to", "between", "more than", "over ", "at least", "~",
    "estimated", "or so", "give or take",
)
MONTHS = {
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
}
MONTH_DAYS = {
    "january": 31, "february": 29, "march": 31, "april": 30, "may": 31,
    "june": 30, "july": 31, "august": 31, "september": 30, "october": 31,
    "november": 30, "december": 31,
}
PROPER_CONTEXT_STOPWORDS = {
    "a", "an", "as", "by", "for", "from", "in", "of", "on", "the", "to",
    "was", "were",
}
CAPITALIZED_ADJECTIVE_ALLOWLIST = {
    "african", "american", "australian", "british", "canadian", "chinese",
    "dutch", "english", "european", "french", "german", "indian", "irish",
    "italian", "japanese", "korean", "mexican", "russian", "spanish",
    "swedish",
}


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def append_jsonl(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def strip_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    m = re.search(r"(\{.*\})", text, re.DOTALL)
    return m.group(1) if m else text


def call_json(prompt, max_tokens=300):
    try:
        resp = _call_openrouter(GPT4O, prompt, max_tokens=max_tokens, temperature=0.0)
        return json.loads(strip_json(resp["choices"][0]["message"]["content"])), None
    except Exception as exc:
        return {}, str(exc)


def gate_clean(v):
    return bool(v) and v.get("original_supported") is True and \
        v.get("original_is_atomic_fact") is True and v.get("fluent_no_artifact") is True


def gate_corrupt(v):
    return bool(v) and all(v.get(k) is True for k in (
        "original_supported", "original_is_atomic_fact", "corrupted_is_false",
        "single_number_change_only", "fluent_no_artifact")) and \
        v.get("within_acceptable_range") is False


def reject_reason(v, keys):
    if not v:
        return "validator_parse_or_api_fail"
    failed = [k for k in keys if v.get(k) is not True]
    if v.get("within_acceptable_range") is not False and "within_acceptable_range" in keys:
        failed.append("within_acceptable_range")
    return ",".join(failed) if failed else "accepted"


def is_hedged(statement, post_filter="none"):
    s = " " + statement.lower() + " "
    if post_filter in {"strict_v2", "strict_v3"} and " somewhat " in s:
        return True
    if post_filter == "strict_v3" and " estimate " in s:
        return True
    return any(h in s for h in HEDGES)


def corrupt_number(num, kind):
    raw = str(num).replace(",", "")
    if kind == "year":
        if not re.fullmatch(r"\d{3,4}", raw):
            return "", "unsupported_year_format"
        val = int(raw)
        return str(val + 2 if val % 2 == 0 else val - 2), "year_parity_plus_minus_2"
    if "." in raw or kind == "decimal":
        try:
            val = float(raw)
        except ValueError:
            return "", "unsupported_decimal_format"
        new = val * (1.2 if int(abs(val)) % 2 == 0 else 0.8)
        dp = len(raw.split(".")[1]) if "." in raw else 1
        return f"{new:.{dp}f}", "decimal_20_percent"
    if not re.fullmatch(r"\d+", raw):
        return "", "unsupported_integer_format"
    val = int(raw)
    if val == 0:
        new = 1
    else:
        new = int(round(val * (1.2 if val % 2 == 0 else 0.8)))
        if new == val:
            new = val + 1
    shown = f"{new:,}" if "," in str(num) else str(new)
    return shown, "integer_20_percent"


def replace_at_span(claim, number_obj, shown):
    text = str(number_obj.get("text", ""))
    start = number_obj.get("start")
    end = number_obj.get("end")
    if isinstance(start, int) and isinstance(end, int) and claim[start:end] == text:
        return claim[:start] + shown + claim[end:], ""
    if claim.count(text) == 1:
        return claim.replace(text, shown, 1), "span_mismatch_used_unique_replace"
    return "", "number_span_mismatch_or_not_unique"


def target_context_reason(rec, post_filter="strict_v2"):
    claim = rec.get("claim_text", "")
    number = rec.get("number") or {}
    text = str(number.get("text", ""))
    start = number.get("start")
    end = number.get("end")
    if not isinstance(start, int) or not isinstance(end, int) or claim[start:end] != text:
        return ""

    open_paren = claim.rfind("(", 0, start)
    close_before = claim.rfind(")", 0, start)
    close_after = claim.find(")", end)
    if open_paren > close_before and close_after != -1:
        return "target_number_inside_parenthetical_disambiguator"
    if post_filter == "strict_v3":
        if claim[start - 1:start] == ":" or claim[end:end + 1] == ":":
            return "target_number_in_colon_time_or_title_expression"
        if re.match(r"(?:'s|s)\b", claim[end:], re.I):
            return "target_number_has_decade_or_age_range_suffix"

    before = claim[:start]
    after = claim[end:]
    prev_match = re.search(r"([A-Za-z][A-Za-z'.-]*)\W*$", before)
    next_match = re.search(r"^\W*([A-Za-z][A-Za-z'.-]*)", after)
    prev = prev_match.group(1) if prev_match else ""
    nxt = next_match.group(1) if next_match else ""
    prev_norm = prev.lower()
    next_norm = nxt.lower()

    if prev and prev[0].isupper() and prev_norm not in MONTHS and \
            prev_norm not in PROPER_CONTEXT_STOPWORDS:
        return "target_number_adjacent_to_proper_name_or_model"
    if start == 0 and nxt and nxt[0].isupper() and next_norm not in MONTHS:
        return "target_number_at_start_of_proper_name_or_model"
    if post_filter == "strict_v3" and prev_norm in PROPER_CONTEXT_STOPWORDS and nxt and nxt[0].isupper() and \
            next_norm not in MONTHS and next_norm not in CAPITALIZED_ADJECTIVE_ALLOWLIST:
        return "target_number_begins_proper_title_after_stopword"
    return ""


def source_filter(rec, post_filter="none"):
    claim = rec.get("claim_text", "")
    number = rec.get("number") or {}
    if is_hedged(claim, post_filter):
        return "source_hedged_or_approximate"
    if not number.get("text") or number.get("kind") not in {"year", "integer", "decimal"}:
        return "source_missing_or_unsupported_number"
    if post_filter in {"strict_v2", "strict_v3"}:
        reason = target_context_reason(rec, post_filter)
        if reason:
            return reason
    return ""


def local_post_filter(rec, modified):
    original = rec["claim_text"]
    number = rec.get("number") or {}
    original_number = str(number.get("text", ""))
    if not modified or modified == original:
        return "generated_no_change"
    if original_number and original_number in modified:
        return "original_number_still_in_modified"
    original_nums = re.findall(r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?", original)
    modified_nums = re.findall(r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?", modified)
    if len(original_nums) != len(modified_nums):
        return "number_count_changed"
    diffs = sum(1 for a, b in zip(original_nums, modified_nums) if a != b)
    if diffs != 1:
        return "not_exactly_one_number_changed"
    date_reason = invalid_date_reason(rec, modified)
    if date_reason:
        return date_reason
    return "accepted"


def invalid_date_reason(rec, modified):
    claim = rec.get("claim_text", "")
    number = rec.get("number") or {}
    start = number.get("start")
    if not isinstance(start, int):
        return ""
    before = claim[:start]
    prev_match = re.search(r"([A-Za-z]+)\W*$", before)
    if not prev_match:
        return ""
    month = prev_match.group(1).lower()
    if month not in MONTH_DAYS:
        return ""
    shown = str(number.get("shown_number", ""))
    modified_nums = re.findall(r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?", modified)
    original_nums = re.findall(r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?", claim)
    shown_candidates = [b for a, b in zip(original_nums, modified_nums) if a != b]
    if len(shown_candidates) != 1:
        return ""
    try:
        day = int(shown_candidates[0].replace(",", ""))
    except ValueError:
        return ""
    if day < 1 or day > MONTH_DAYS[month]:
        return "invalid_month_day_after_corruption"
    return ""


def make_stratified_order(records, seed):
    """Fixed deterministic order, locally stratified by length_bin/number_kind."""
    rng = random.Random(seed)
    groups = {}
    for rec in records:
        key = (rec.get("length_bin", "missing"), (rec.get("number") or {}).get("kind", "missing"))
        groups.setdefault(key, []).append(rec)
    for group in groups.values():
        rng.shuffle(group)

    strata = sorted(groups)
    weights = {k: len(groups[k]) for k in strata}
    total = sum(weights.values())
    taken = Counter()
    order = []
    while len(order) < total:
        available = [k for k in strata if taken[k] < weights[k]]
        if not available:
            break
        key = max(available, key=lambda k: (weights[k] / total) - (taken[k] / max(1, len(order))))
        order.append(groups[key][taken[key]])
        taken[key] += 1
    return order


def load_attempts(path):
    processed = set()
    clean, corrupted = [], []
    attempts = []
    if not path.exists():
        return processed, clean, corrupted, attempts
    for rec in load_jsonl(path):
        attempts.append(rec)
        processed.add((rec["role"], rec["source_claim_id"]))
        if rec.get("status") == "accepted":
            if rec["role"] == "clean":
                clean.append(rec["item"])
            else:
                corrupted.append(rec["item"])
    return processed, clean, corrupted, attempts


def final_counts(records, field):
    return dict(Counter(rec.get(field, "missing") for rec in records))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default="data/frozen/v1/number_pool_v1.jsonl")
    ap.add_argument("--pool-version", default="v1")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n-corrupt", type=int, default=300)
    ap.add_argument("--n-clean", type=int, default=300)
    ap.add_argument("--out", default="")
    ap.add_argument("--post-filter", choices=["none", "strict_v2", "strict_v3"], default="none")
    args = ap.parse_args()

    if not os.environ.get("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    pool_path = ROOT / args.pool
    stem = f"number_corruption_pool_{args.pool_version}_n{args.n_corrupt}"
    out_path = ROOT / (args.out or f"data/{stem}.jsonl")
    attempts_path = ROOT / "results" / f"{stem}_build_attempts.jsonl"
    manifest_path = ROOT / "results" / f"{stem}_build_manifest.json"

    if out_path.exists():
        print(f"{out_path.relative_to(ROOT)} exists; delete to rebuild.")
        return

    pool = load_jsonl(pool_path)
    order = make_stratified_order(pool, args.seed)
    clean_order = [rec for i, rec in enumerate(order) if i % 2 == 0]
    corrupt_order = [rec for i, rec in enumerate(order) if i % 2 == 1]
    processed, clean, corrupted, prior_attempts = load_attempts(attempts_path)
    print(f"Pool={pool_path.relative_to(ROOT)} size={len(pool)} seed={args.seed}")
    print(f"Target={args.n_clean} clean + {args.n_corrupt} corrupted")
    if prior_attempts:
        print(f"Resuming from {len(prior_attempts)} logged attempts: "
              f"clean={len(clean)} corrupted={len(corrupted)}")

    for rec in clean_order:
        if len(clean) >= args.n_clean:
            break
        key = ("clean", rec["claim_id"])
        if key in processed:
            continue
        claim = rec["claim_text"]
        source_reason = source_filter(rec, args.post_filter)
        item = None
        v, err = {}, None
        if source_reason:
            accepted = False
            reason = f"source_filter:{source_reason}"
        else:
            v, err = call_json(VAL_CLEAN.format(claim=claim))
            accepted = gate_clean(v)
            reason = "accepted" if accepted else reject_reason(
                v, ["original_supported", "original_is_atomic_fact", "fluent_no_artifact"])
        if accepted:
            number = rec["number"]
            item = {
                "statement": claim,
                "gold": "true",
                "is_corrupted": False,
                "kind": "number",
                "number_kind": number.get("kind"),
                "pool_version": args.pool_version,
                "source_claim_id": rec["claim_id"],
                "fever_id": rec.get("fever_id"),
                "original_statement": claim,
                "original_number": number.get("text"),
                "shown_number": number.get("text"),
                "canonical_value": v.get("canonical_value", ""),
                "length_bin": rec.get("length_bin"),
            }
            clean.append(item)
        append_jsonl(attempts_path, {
            "role": "clean",
            "source_claim_id": rec["claim_id"],
            "status": "accepted" if accepted else "rejected",
            "reason": reason,
            "api_error": err,
            "validator": v,
            "item": item,
        })
        processed.add(key)
        if accepted and (len(clean) + len(corrupted)) % 25 == 0:
            print(f"  accepted clean={len(clean)} corrupted={len(corrupted)}", flush=True)

    for rec in corrupt_order:
        if len(corrupted) >= args.n_corrupt:
            break
        key = ("corrupt", rec["claim_id"])
        if key in processed:
            continue
        claim = rec["claim_text"]
        number = rec.get("number") or {}
        source_reason = source_filter(rec, args.post_filter)
        item = None
        status = "rejected"
        reason = "accepted"
        v, err = {}, None
        generation = {}
        if source_reason:
            reason = f"source_filter:{source_reason}"
        else:
            shown_num, rule = corrupt_number(number.get("text", ""), number.get("kind", ""))
            generation = {
                "original_number": number.get("text", ""),
                "shown_number": shown_num,
                "corruption_rule": rule,
            }
            modified, span_reason = replace_at_span(claim, number, shown_num)
            if span_reason and not modified:
                reason = f"post_filter:{span_reason}"
            else:
                post_reason = local_post_filter(rec, modified)
                if post_reason != "accepted":
                    reason = f"post_filter:{post_reason}"
                else:
                    v, err = call_json(VAL_CORRUPT.format(original=claim, modified=modified))
                    if gate_corrupt(v):
                        status = "accepted"
                        reason = "accepted"
                        item = {
                            "statement": modified,
                            "gold": "false",
                            "is_corrupted": True,
                            "kind": "number",
                            "number_kind": number.get("kind"),
                            "pool_version": args.pool_version,
                            "source_claim_id": rec["claim_id"],
                            "fever_id": rec.get("fever_id"),
                            "original_statement": claim,
                            "original_number": number.get("text"),
                            "shown_number": shown_num,
                            "canonical_value": v.get("canonical_value", ""),
                            "corruption_rule": rule,
                            "length_bin": rec.get("length_bin"),
                        }
                        corrupted.append(item)
                    else:
                        reason = reject_reason(v, [
                            "original_supported", "original_is_atomic_fact",
                            "corrupted_is_false", "within_acceptable_range",
                            "single_number_change_only", "fluent_no_artifact"])
        append_jsonl(attempts_path, {
            "role": "corrupt",
            "source_claim_id": rec["claim_id"],
            "status": status,
            "reason": reason,
            "api_error": err,
            "generation": generation,
            "validator": v,
            "item": item,
        })
        processed.add(key)
        if status == "accepted" and (len(clean) + len(corrupted)) % 25 == 0:
            print(f"  accepted clean={len(clean)} corrupted={len(corrupted)}", flush=True)

    if len(clean) < args.n_clean or len(corrupted) < args.n_corrupt:
        print(f"INCOMPLETE: clean={len(clean)} corrupted={len(corrupted)}. "
              f"Re-run to continue from {attempts_path.relative_to(ROOT)}.")
        return

    items = clean[:args.n_clean] + corrupted[:args.n_corrupt]
    id_prefix = f"num{args.pool_version}_"
    for i, item in enumerate(items):
        item["id"] = f"{id_prefix}{i+1:04d}"
    write_jsonl(out_path, items)

    attempts = load_jsonl(attempts_path)
    attrition = Counter()
    reasons = Counter()
    for att in attempts:
        attrition[f"{att['role']}_attempts"] += 1
        attrition[f"{att['role']}_{att['status']}"] += 1
        if att["status"] != "accepted":
            reasons[f"{att['role']}:{att.get('reason', 'unknown')}"] += 1
    manifest = {
        "dataset": str(out_path.relative_to(ROOT)),
        "pool": str(pool_path.relative_to(ROOT)),
        "pool_version": args.pool_version,
        "seed": args.seed,
        "n_clean": args.n_clean,
        "n_corrupt": args.n_corrupt,
        "sampling": {
            "method": "fixed-seed local-stratified order over (length_bin, number_kind)",
            "class_assignment": "even positions clean, odd positions corrupted",
            "gpt4o_in_sampling": False,
            "gpt4o_role": "hard-gate validation only",
            "local_generation": "deterministic number perturbation",
            "local_post_filter": args.post_filter,
        },
        "attrition": dict(attrition),
        "rejection_reasons": dict(reasons),
        "final_strata": {
            "length_bin": final_counts(items, "length_bin"),
            "number_kind": final_counts(items, "number_kind"),
            "class": dict(Counter("corrupt" if it["is_corrupted"] else "clean" for it in items)),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(json.dumps({
        "dataset": str(out_path.relative_to(ROOT)),
        "clean": args.n_clean,
        "corrupted": args.n_corrupt,
        "attempts": str(attempts_path.relative_to(ROOT)),
        "manifest": str(manifest_path.relative_to(ROOT)),
    }, indent=2))


if __name__ == "__main__":
    main()
