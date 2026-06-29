#!/usr/bin/env python3
"""Build pool-based Entity Swap corruption data.

Frozen input:
  data/entity_pool_v1.jsonl

Output:
  data/entity_corruption_pool_v1_n300.jsonl
  results/entity_corruption_pool_v1_n300_build_attempts.jsonl
  results/entity_corruption_pool_v1_n300_build_manifest.json

Sampling is fixed-seed and pool-based. GPT-4o is used only after sampling for
generation and hard-gate validation, not to choose the item pool.
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

SWAP_PROMPT = """Here is a TRUE factual claim from FEVER. Replace EXACTLY ONE
named entity from the allowed entity list with a DIFFERENT, plausible entity of
the SAME TYPE so that the claim becomes FALSE. Change NOTHING else: no numbers,
relations, verbs, dates, or surrounding wording.

The replacement entity must NOT already appear anywhere in the original claim.
Do NOT replace a person with a work/title/team, or a work/title/team with a
person. Do NOT replace a named entity with a year, month, nationality adjective,
genre, platform, award category, or generic attribute.

Allowed named entities: {entities}

Return ONLY JSON:
{{"corrupted": "<claim with one allowed entity swapped>",
  "original_entity": "<entity from the allowed list>",
  "new_entity": "<replacement entity>"}}

Claim: {claim}"""

VAL_CORRUPT = """You are the CORRUPTION VALIDATOR. Given an ORIGINAL true claim
and a MODIFIED version with one entity swapped, return ONLY JSON with EXACTLY:
{{"original_supported": true/false, "original_is_atomic_fact": true/false,
  "corrupted_is_false": true/false, "single_change_only": true/false,
  "fluent_no_artifact": true/false}}
- original_supported: is the ORIGINAL factually TRUE?
- original_is_atomic_fact: a single precise verifiable claim?
- corrupted_is_false: is the MODIFIED now factually FALSE (the new entity is wrong)?
- single_change_only: was exactly ONE entity changed, nothing else?
- fluent_no_artifact: modified reads naturally, no tampering seam?

ORIGINAL: {original}
MODIFIED: {modified}"""

VAL_CORRUPT_STRICT = """You are the CORRUPTION VALIDATOR. Given an ORIGINAL true
claim and a MODIFIED version with one entity swapped, return ONLY JSON with
EXACTLY:
{{"original_supported": true/false, "original_is_atomic_fact": true/false,
  "corrupted_is_false": true/false, "single_change_only": true/false,
  "fluent_no_artifact": true/false}}
- original_supported: is the ORIGINAL factually TRUE?
- original_is_atomic_fact: a single precise verifiable claim? Reject vague,
  broad, or many-entities-could-fit claims.
- corrupted_is_false: is the MODIFIED clearly factually FALSE? If it could
  still be true, is merely uncertain, or is too broad to verify as false,
  return false for this field.
- single_change_only: was exactly ONE named entity changed, nothing else?
- fluent_no_artifact: modified reads naturally, no tampering seam?

ORIGINAL: {original}
MODIFIED: {modified}"""

VAL_CLEAN = """You are the CORRUPTION VALIDATOR. Given ONE claim, return ONLY JSON:
{{"original_supported": true/false, "original_is_atomic_fact": true/false,
  "fluent_no_artifact": true/false}}
- original_supported: is it factually TRUE?
- original_is_atomic_fact: a single precise verifiable claim?
- fluent_no_artifact: fluent, no artifact.

CLAIM: {claim}"""

VAL_CLEAN_STRICT = """You are the CORRUPTION VALIDATOR. Given ONE claim, return
ONLY JSON:
{{"original_supported": true/false, "original_is_atomic_fact": true/false,
  "fluent_no_artifact": true/false}}
- original_supported: is it factually TRUE?
- original_is_atomic_fact: a single precise verifiable claim? Reject vague,
  broad, or many-entities-could-fit claims.
- fluent_no_artifact: fluent, no artifact.

CLAIM: {claim}"""


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
        "single_change_only", "fluent_no_artifact"))


MONTHS = {
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
}
GENERIC_ATTRIBUTES = {
    "actor", "actress", "singer", "director", "writer", "author", "book",
    "film", "movie", "album", "song", "series", "game", "novel", "play",
    "american", "british", "french", "german", "indian", "japanese",
    "canadian", "australian", "chinese", "italian", "spanish", "russian",
    "swedish", "korean", "mexican", "brazilian", "grammy", "emmy",
}
LANGUAGE_TERMS = {
    "arabic", "aramaic", "bengali", "cantonese", "english", "french",
    "german", "greek", "hebrew", "hindi", "italian", "japanese", "korean",
    "latin", "mandarin", "persian", "portuguese", "russian", "spanish",
    "tamil", "telugu", "urdu",
}
MEDIA_OR_PLATFORM_TERMS = {
    "radio", "television", "tv", "uk tv", "us tv", "netflix", "hulu",
    "streaming", "broadcast",
}
NATIONALITY_TERMS = {
    "american", "australian", "bengali", "british", "canadian", "chinese",
    "democratic", "french", "german", "indian", "italian", "japanese",
    "mexican", "republican", "russian", "south korean", "spanish", "swedish",
}
GENERIC_HEAD_NOUNS = {
    "actor", "actress", "author", "category", "director", "film", "genre",
    "language", "medium", "movie", "office", "personality", "president",
    "role", "senator", "show", "territory", "writer",
}
ROLE_OR_OFFICE_TERMS = {
    "general secretary", "president", "prime minister", "senator",
    "secretary of state",
}
INVALID_PLACEHOLDERS = {"abcd"}
BROAD_OR_AMBIGUOUS_FRAMES = {
    "general secretary is a rank",
    "has been in a movie",
    "is an american actor and film director",
    "was hospitalized during his childhood",
    "was hospitalized during her childhood",
    "worked on a comedy show",
}
RELIGION_TERMS = {
    "buddhist", "catholic", "christian", "christianity", "hindu", "hinduism",
    "islam", "islamic", "jewish", "judaism", "muslim", "protestant",
}
AWARD_CATEGORY_TERMS = {
    "best actor", "best actress", "best supporting actor",
    "best supporting actress",
}
PARTIAL_TITLE_TERMS = {"anything", "boy", "everything", "girl"}
BROAD_OR_AMBIGUOUS_FRAMES_V4 = {
    "championship featured",
    "games are part of the",
    "games are part of",
    "is a series of spy films",
    "is a spy film series",
}


def norm_text(text):
    text = str(text).lower().replace("\u2019", "'").replace("`", "'")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def contains_norm(haystack, needle):
    needle_norm = norm_text(needle)
    if not needle_norm:
        return False
    return f" {needle_norm} " in f" {norm_text(haystack)} "


def count_norm(haystack, needle):
    needle_norm = norm_text(needle)
    if not needle_norm:
        return 0
    return f" {norm_text(haystack)} ".count(f" {needle_norm} ")


def local_post_filter(rec, generation, modified):
    original = rec["claim_text"]
    allowed = rec.get("entity_texts") or []
    original_entity = str(generation.get("original_entity", "")).strip()
    new_entity = str(generation.get("new_entity", "")).strip()
    if not modified or modified == original:
        return "generated_no_change"
    if not original_entity or not new_entity:
        return "missing_entity_metadata"
    if norm_text(original_entity) == norm_text(new_entity):
        return "same_entity"
    if not any(norm_text(original_entity) == norm_text(ent) for ent in allowed):
        return "original_entity_not_in_allowed_list"
    if not contains_norm(original, original_entity):
        return "original_entity_not_in_original"
    if not contains_norm(modified, new_entity):
        return "new_entity_not_in_modified"
    if contains_norm(original, new_entity):
        return "new_entity_already_in_original"
    if contains_norm(modified, original_entity):
        return "original_entity_still_in_modified"
    if count_norm(modified, new_entity) != 1:
        return "new_entity_not_unique_in_modified"
    if re.fullmatch(r"\d+(?:[/-]\d+)*", norm_text(new_entity)):
        return "replacement_is_number_or_date"
    if norm_text(new_entity) in MONTHS:
        return "replacement_is_month"
    if norm_text(new_entity) in GENERIC_ATTRIBUTES:
        return "replacement_is_generic_attribute"
    return "accepted"


def generic_entity_reason(text):
    raw = str(text).strip()
    norm = norm_text(raw)
    if not norm:
        return "missing_entity_text"
    if norm in LANGUAGE_TERMS:
        return "language_term"
    if norm in MEDIA_OR_PLATFORM_TERMS:
        return "media_or_platform_term"
    if norm in MONTHS:
        return "month_term"
    if norm in GENERIC_ATTRIBUTES:
        return "generic_attribute"
    if norm in INVALID_PLACEHOLDERS:
        return "placeholder_entity"
    if norm in ROLE_OR_OFFICE_TERMS:
        return "role_or_office_term"
    if any(norm.startswith(f"{role} of ") for role in ROLE_OR_OFFICE_TERMS):
        return "role_or_office_phrase"
    words = set(norm.split())
    if words & NATIONALITY_TERMS and words & GENERIC_HEAD_NOUNS:
        return "nationality_or_attribute_phrase"
    if words & {"tv", "radio", "television"}:
        return "media_type_phrase"
    if {"democratic", "senator"} <= words or {"republican", "senator"} <= words:
        return "party_title_phrase"
    return ""


def generic_entity_reason_v4(text):
    reason = generic_entity_reason(text)
    if reason:
        return reason
    norm = norm_text(text)
    if norm in RELIGION_TERMS:
        return "religion_or_attribute_term"
    if norm in AWARD_CATEGORY_TERMS:
        return "award_category_term"
    if norm in PARTIAL_TITLE_TERMS:
        return "partial_title_or_common_word"
    return ""


def broad_or_ambiguous_frame_reason(original, modified):
    text = norm_text(f"{original} {modified}")
    for pattern in BROAD_OR_AMBIGUOUS_FRAMES:
        if pattern in text:
            return "broad_or_ambiguous_frame"
    if original.strip().endswith(".") and not modified.strip().endswith("."):
        return "punctuation_or_fluency_artifact"
    return ""


def broad_or_ambiguous_frame_reason_v4(original, modified):
    reason = broad_or_ambiguous_frame_reason(original, modified)
    if reason:
        return reason
    text = norm_text(f"{original} {modified}")
    for pattern in BROAD_OR_AMBIGUOUS_FRAMES_V4:
        if pattern in text:
            return "broad_or_ambiguous_frame_v4"
    return ""


def local_post_filter_v3(rec, generation, modified):
    base = local_post_filter(rec, generation, modified)
    if base != "accepted":
        return base
    original = rec["claim_text"]
    original_entity = str(generation.get("original_entity", "")).strip()
    new_entity = str(generation.get("new_entity", "")).strip()
    for role, entity in (("original", original_entity), ("replacement", new_entity)):
        reason = generic_entity_reason(entity)
        if reason:
            return f"{role}_entity_is_{reason}"
    reason = broad_or_ambiguous_frame_reason(original, modified)
    if reason:
        return reason
    return "accepted"


def local_post_filter_v4(rec, generation, modified):
    base = local_post_filter(rec, generation, modified)
    if base != "accepted":
        return base
    original = rec["claim_text"]
    original_entity = str(generation.get("original_entity", "")).strip()
    new_entity = str(generation.get("new_entity", "")).strip()
    for role, entity in (("original", original_entity), ("replacement", new_entity)):
        reason = generic_entity_reason_v4(entity)
        if reason:
            return f"{role}_entity_is_{reason}"
    if (
        len(original_entity.split()) == 1
        and re.search(rf"\b{re.escape(original_entity)}\s+[A-Z][A-Za-z]+\b", original)
    ):
        return "original_entity_is_partial_person_name"
    reason = broad_or_ambiguous_frame_reason_v4(original, modified)
    if reason:
        return reason
    return "accepted"


def source_frame_filter_v4(claim):
    text = norm_text(claim)
    for pattern in BROAD_OR_AMBIGUOUS_FRAMES_V4:
        if pattern in text:
            return "source_broad_or_ambiguous_frame_v4"
    return ""


def reject_reason(v, keys):
    if not v:
        return "validator_parse_or_api_fail"
    failed = [k for k in keys if v.get(k) is not True]
    return ",".join(failed) if failed else "accepted"


def make_stratified_order(records, seed):
    """Fixed deterministic order, locally stratified by length_bin/entity_type."""
    rng = random.Random(seed)
    groups = {}
    for rec in records:
        key = (rec.get("length_bin", "missing"), rec.get("entity_type", "missing"))
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
        # Weighted deficit scheduling keeps the order proportional but fixed.
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
    ap.add_argument("--pool", default="data/entity_pool_v1.jsonl")
    ap.add_argument("--pool-version", default="v1")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n-corrupt", type=int, default=300)
    ap.add_argument("--n-clean", type=int, default=300)
    ap.add_argument("--out", default="")
    ap.add_argument(
        "--post-filter",
        choices=["none", "strict_v2", "strict_v3", "strict_v4"],
        default="none",
    )
    args = ap.parse_args()

    if not os.environ.get("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    pool_path = ROOT / args.pool
    stem = f"entity_corruption_pool_{args.pool_version}_n{args.n_corrupt}"
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
        v, err = call_json(VAL_CLEAN.format(claim=claim))
        accepted = gate_clean(v)
        item = None
        if accepted:
            item = {
                "statement": claim,
                "gold": "true",
                "is_corrupted": False,
                "kind": "entity",
                "pool_version": args.pool_version,
                "source_claim_id": rec["claim_id"],
                "fever_id": rec.get("fever_id"),
                "original_statement": claim,
                "entity_type": rec.get("entity_type"),
                "length_bin": rec.get("length_bin"),
            }
            clean.append(item)
        append_jsonl(attempts_path, {
            "role": "clean",
            "source_claim_id": rec["claim_id"],
            "status": "accepted" if accepted else "rejected",
            "reason": "accepted" if accepted else reject_reason(
                v, ["original_supported", "original_is_atomic_fact", "fluent_no_artifact"]),
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
        if args.post_filter == "strict_v4":
            source_reason = source_frame_filter_v4(claim)
            if source_reason:
                append_jsonl(attempts_path, {
                    "role": "corrupt",
                    "source_claim_id": rec["claim_id"],
                    "status": "rejected",
                    "reason": f"post_filter:{source_reason}",
                    "api_error": None,
                    "generation": {},
                    "validator": {},
                    "item": None,
                })
                processed.add(key)
                continue
        entities = ", ".join(rec.get("entity_texts") or [])
        s, gen_err = call_json(SWAP_PROMPT.format(claim=claim, entities=entities))
        shown = str(s.get("corrupted", "")).strip()
        item = None
        status = "rejected"
        reason = "generation_parse_or_api_fail"
        v, val_err = {}, None
        if shown and shown != claim:
            if args.post_filter == "strict_v4":
                post_reason = local_post_filter_v4(rec, s, shown)
            elif args.post_filter == "strict_v3":
                post_reason = local_post_filter_v3(rec, s, shown)
            elif args.post_filter == "strict_v2":
                post_reason = local_post_filter(rec, s, shown)
            else:
                post_reason = "accepted"
            if post_reason != "accepted":
                reason = f"post_filter:{post_reason}"
            else:
                corrupt_prompt = (
                    VAL_CORRUPT_STRICT
                    if args.post_filter in {"strict_v3", "strict_v4"} else VAL_CORRUPT
                )
                v, val_err = call_json(corrupt_prompt.format(original=claim, modified=shown))
            if post_reason == "accepted" and gate_corrupt(v):
                status = "accepted"
                reason = "accepted"
                item = {
                    "statement": shown,
                    "gold": "false",
                    "is_corrupted": True,
                    "kind": "entity",
                    "pool_version": args.pool_version,
                    "source_claim_id": rec["claim_id"],
                    "fever_id": rec.get("fever_id"),
                    "original_statement": claim,
                    "original_entity": s.get("original_entity", ""),
                    "new_entity": s.get("new_entity", ""),
                    "entity_type": rec.get("entity_type"),
                    "length_bin": rec.get("length_bin"),
                }
                corrupted.append(item)
            elif post_reason == "accepted":
                reason = reject_reason(v, [
                    "original_supported", "original_is_atomic_fact", "corrupted_is_false",
                    "single_change_only", "fluent_no_artifact"])
        elif shown == claim:
            reason = "generated_no_change"
        append_jsonl(attempts_path, {
            "role": "corrupt",
            "source_claim_id": rec["claim_id"],
            "status": status,
            "reason": reason,
            "api_error": gen_err or val_err,
            "generation": s,
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
    id_prefix = f"ent{args.pool_version}_"
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
            "method": "fixed-seed local-stratified order over (length_bin, entity_type)",
            "class_assignment": "even positions clean, odd positions corrupted",
            "gpt4o_in_sampling": False,
            "gpt4o_role": "generation and hard-gate validation only",
            "local_post_filter": args.post_filter,
        },
        "attrition": dict(attrition),
        "rejection_reasons": dict(reasons),
        "final_strata": {
            "length_bin": final_counts(items, "length_bin"),
            "entity_type": final_counts(items, "entity_type"),
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
