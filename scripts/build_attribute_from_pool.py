#!/usr/bin/env python3
"""Build pool-based Attribute Substitution corruption data.

Frozen input:
  data/frozen/attribute_v1/attribute_pool_v1.jsonl

Output:
  data/attribute_corruption_pool_<version>_n300.jsonl
  results/attribute_corruption_pool_<version>_n300_build_attempts.jsonl
  results/attribute_corruption_pool_<version>_n300_build_manifest.json

Sampling is fixed-seed and pool-based. Attribute corruption is deterministic
local editing; GPT-4o is used only as a hard-gate validator, not to choose the
pool or invent replacements.
"""
from __future__ import annotations

import argparse
import hashlib
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
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

from src.judges import _call_openrouter

GPT4O = "openai/gpt-4o"

VAL_CLEAN = """You are the CORRUPTION VALIDATOR. Given ONE claim, return ONLY JSON:
{{"original_supported": true/false, "original_is_atomic_fact": true/false,
  "fluent_no_artifact": true/false}}
- original_supported: is it factually TRUE?
- original_is_atomic_fact: a single precise verifiable claim?
- fluent_no_artifact: fluent, natural English with no artifact.

CLAIM: {claim}"""

VAL_CORRUPT = """You are the CORRUPTION VALIDATOR. Given an ORIGINAL true claim
and a MODIFIED version where exactly one non-entity descriptive attribute was
changed, return ONLY JSON with EXACTLY:
{{"original_supported": true/false, "original_is_atomic_fact": true/false,
  "corrupted_is_false": true/false, "target_is_non_entity_attribute": true/false,
  "single_attribute_change_only": true/false, "fluent_no_artifact": true/false}}
- original_supported: is the ORIGINAL factually TRUE?
- original_is_atomic_fact: a single precise verifiable claim?
- corrupted_is_false: is the MODIFIED clearly factually FALSE? If it could
  still be true, merely uncertain, or too broad to verify as false, return false.
- target_is_non_entity_attribute: was the changed span a descriptive attribute
  such as nationality, occupation, genre, language, or type, not a named entity?
- single_attribute_change_only: was exactly one attribute changed, with named
  entities, numbers, dates, relations, and surrounding wording preserved?
- fluent_no_artifact: modified reads naturally, no tampering seam.

ORIGINAL: {original}
MODIFIED: {modified}
ORIGINAL_ATTRIBUTE: {original_attribute}
NEW_ATTRIBUTE: {new_attribute}
ATTRIBUTE_TYPE: {attribute_type}"""

NUM_RE = re.compile(r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?")

REPLACEMENTS = {
    "nationality": [
        "American", "British", "Canadian", "French", "German", "Indian",
        "Italian", "Japanese", "Chinese", "Australian", "Spanish", "Russian",
        "Mexican", "Swedish", "Korean", "Irish", "Dutch", "Brazilian",
        "Norwegian", "Danish", "Polish", "Turkish", "Greek", "Scottish",
        "Welsh", "Israeli",
    ],
    "occupation": [
        "actor", "singer", "director", "musician", "writer", "author",
        "artist", "athlete", "journalist", "composer", "novelist", "poet",
        "politician", "footballer", "basketball player", "baseball player",
        "tennis player", "comedian", "filmmaker", "producer",
    ],
    "genre": [
        "comedy", "drama", "thriller", "horror", "documentary", "animated",
        "romance", "action", "adventure", "fantasy", "science fiction",
        "crime", "mystery", "western", "musical",
    ],
    "language": [
        "English-language", "French-language", "Spanish-language",
        "Japanese-language", "German-language", "Italian-language",
        "Chinese-language", "Korean-language", "Hindi-language",
        "Tamil-language", "Russian-language", "Portuguese-language",
        "Arabic-language", "Mandarin-language", "Bengali-language",
        "Telugu-language", "Persian-language", "Latin-language",
    ],
    "type": [
        "public university", "private university", "liberal arts college",
        "research university", "professional wrestler", "professional footballer",
        "professional basketball player", "professional baseball player",
        "professional tennis player",
    ],
}

PREFERRED_REPLACEMENTS = {
    "nationality": {
        "american": "British",
        "british": "Canadian",
        "canadian": "British",
        "french": "German",
        "german": "French",
        "indian": "Japanese",
        "italian": "British",
        "japanese": "Chinese",
        "chinese": "Japanese",
        "australian": "British",
        "spanish": "French",
        "russian": "German",
        "mexican": "Canadian",
        "swedish": "Danish",
        "korean": "Japanese",
        "irish": "British",
        "dutch": "German",
        "brazilian": "Mexican",
        "norwegian": "Danish",
        "danish": "Swedish",
        "polish": "German",
        "turkish": "Greek",
        "greek": "Turkish",
        "scottish": "Welsh",
        "welsh": "Scottish",
        "israeli": "Italian",
    },
    "occupation": {
        "actor": "singer",
        "actress": "singer",
        "singer": "director",
        "writer": "singer",
        "author": "actor",
        "director": "actor",
        "filmmaker": "musician",
        "producer": "actor",
        "composer": "actor",
        "musician": "actor",
        "novelist": "singer",
        "poet": "actor",
        "politician": "singer",
        "footballer": "basketball player",
        "basketball player": "footballer",
        "baseball player": "tennis player",
        "tennis player": "baseball player",
        "journalist": "singer",
        "comedian": "director",
    },
    "genre": {
        "black comedy": "thriller",
        "romantic comedy": "drama",
        "science fiction": "musical",
        "comedy": "drama",
        "drama": "thriller",
        "thriller": "drama",
        "horror": "drama",
        "documentary": "horror",
        "animated": "documentary",
        "romance": "crime",
        "action": "musical",
        "adventure": "documentary",
        "fantasy": "crime",
        "crime": "romance",
        "mystery": "musical",
        "western": "science fiction",
        "musical": "horror",
    },
    "language": {
        "english language": "French-language",
        "english-language": "French-language",
        "french language": "English-language",
        "french-language": "English-language",
        "spanish language": "French-language",
        "spanish-language": "French-language",
        "japanese language": "English-language",
        "japanese-language": "English-language",
        "german language": "French-language",
        "german-language": "French-language",
        "italian language": "English-language",
        "italian-language": "English-language",
        "chinese language": "Japanese-language",
        "chinese-language": "Japanese-language",
        "korean language": "Japanese-language",
        "korean-language": "Japanese-language",
        "hindi language": "Tamil-language",
        "hindi-language": "Tamil-language",
        "tamil language": "Hindi-language",
        "tamil-language": "Hindi-language",
    },
    "type": {
        "public university": "private university",
        "private university": "public university",
        "liberal arts college": "research university",
        "research university": "liberal arts college",
        "professional wrestler": "professional footballer",
        "professional footballer": "professional basketball player",
        "professional basketball player": "professional footballer",
        "professional baseball player": "professional tennis player",
    },
}

BROAD_OR_ARTIFACT_FRAMES = [
    ("there_is_named_frame", re.compile(r"^\s*There (?:is|are)\b", re.IGNORECASE)),
    ("called_frame", re.compile(r"\bcalled\b", re.IGNORECASE)),
    ("named_frame", re.compile(r"\bnamed\b", re.IGNORECASE)),
    ("has_attribute_in_title_frame", re.compile(r"\b(?:song|album|film|book|novel)\s+titled\b", re.IGNORECASE)),
]


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def strip_json(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    return match.group(1) if match else text


def call_json(prompt: str, max_tokens: int = 300) -> tuple[dict, str | None]:
    try:
        resp = _call_openrouter(GPT4O, prompt, max_tokens=max_tokens, temperature=0.0)
        return json.loads(strip_json(resp["choices"][0]["message"]["content"])), None
    except Exception as exc:
        return {}, str(exc)


def gate_clean(v: dict) -> bool:
    return bool(v) and v.get("original_supported") is True and \
        v.get("original_is_atomic_fact") is True and v.get("fluent_no_artifact") is True


def gate_corrupt(v: dict) -> bool:
    return bool(v) and all(v.get(k) is True for k in (
        "original_supported", "original_is_atomic_fact", "corrupted_is_false",
        "target_is_non_entity_attribute", "single_attribute_change_only",
        "fluent_no_artifact",
    ))


def reject_reason(v: dict, keys: list[str]) -> str:
    if not v:
        return "validator_parse_or_api_fail"
    failed = [key for key in keys if v.get(key) is not True]
    return ",".join(failed) if failed else "accepted"


def norm(text: str) -> str:
    text = str(text).lower().replace("\u2019", "'").replace("`", "'")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def match_case(original: str, replacement: str) -> str:
    if not original:
        return replacement
    if original.isupper():
        return replacement.upper()
    if original[0].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement[:1].lower() + replacement[1:]


def previous_word(claim: str, start: int) -> str:
    match = re.search(r"([A-Za-z]+)\W*$", claim[:start])
    return match.group(1).lower() if match else ""


def starts_with_vowel_sound(text: str) -> bool:
    return bool(re.match(r"^[aeiou]", norm(text)))


def article_matches(article: str, replacement: str) -> bool:
    if article == "an":
        return starts_with_vowel_sound(replacement)
    if article == "a":
        return not starts_with_vowel_sound(replacement)
    return True


def rotate_by_key(values: list[str], key: str) -> list[str]:
    if not values:
        return values
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    offset = int(digest[:8], 16) % len(values)
    return values[offset:] + values[:offset]


def candidate_replacements(
    attribute_type: str,
    original: str,
    claim: str,
    start: int,
    policy: str,
    source_key: str,
) -> list[tuple[str, str]]:
    article = previous_word(claim, start)
    values = REPLACEMENTS.get(attribute_type, [])
    if not values:
        return []
    original_norm = norm(original)
    out = []

    if policy == "preferred":
        preferred = PREFERRED_REPLACEMENTS.get(attribute_type, {}).get(original_norm)
        if preferred and norm(preferred) != original_norm and article_matches(article, preferred):
            out.append((match_case(original, preferred), f"{attribute_type}_preferred_replacement"))

    ordered = values if policy == "preferred" else rotate_by_key(values, source_key)
    for candidate in ordered:
        if norm(candidate) == original_norm:
            continue
        if not article_matches(article, candidate):
            continue
        shown = match_case(original, candidate)
        if any(norm(shown) == norm(prev[0]) for prev in out):
            continue
        rule = (
            f"{attribute_type}_article_aware_replacement"
            if policy == "preferred"
            else f"{attribute_type}_balanced_v3_replacement"
        )
        out.append((shown, rule))
    return out


def replacement_for(
    attribute_type: str,
    original: str,
    claim: str,
    start: int,
    policy: str,
    source_key: str,
    pair_counts: Counter | None = None,
    pair_cap: int = 0,
) -> tuple[str, str]:
    candidates = candidate_replacements(attribute_type, original, claim, start, policy, source_key)
    if not candidates:
        return "", "no_distinct_replacement"
    for shown, rule in candidates:
        pair = (norm(original), norm(shown))
        if pair_cap > 0 and pair_counts is not None and pair_counts[pair] >= pair_cap:
            continue
        return shown, rule
    return "", "replacement_pair_cap_exhausted"


def replace_attribute(
    rec: dict,
    policy: str = "preferred",
    pair_counts: Counter | None = None,
    pair_cap: int = 0,
) -> tuple[dict, str]:
    claim = rec["claim_text"]
    attr = rec.get("attribute") or {}
    start = attr.get("attribute_start")
    end = attr.get("attribute_end")
    original = str(attr.get("attribute_text", ""))
    attribute_type = str(attr.get("attribute_type", ""))
    if not isinstance(start, int) or not isinstance(end, int) or claim[start:end] != original:
        return {}, "attribute_span_mismatch"
    source_key = rec.get("claim_id") or rec.get("base_claim_id") or claim
    new_attr, rule = replacement_for(
        attribute_type,
        original,
        claim,
        start,
        policy,
        source_key,
        pair_counts=pair_counts,
        pair_cap=pair_cap,
    )
    if not new_attr:
        return {}, rule
    modified = claim[:start] + new_attr + claim[end:]
    return {
        "corrupted": modified,
        "original_attribute": original,
        "new_attribute": new_attr,
        "attribute_type": attribute_type,
        "corruption_rule": rule,
    }, ""


def extract_numbers(text: str) -> list[str]:
    return NUM_RE.findall(text)


def broad_or_artifact_reason(claim: str) -> str:
    for reason, rx in BROAD_OR_ARTIFACT_FRAMES:
        if rx.search(claim):
            return reason
    return ""


def local_post_filter(rec: dict, generation: dict) -> str:
    original = rec["claim_text"]
    modified = str(generation.get("corrupted", "")).strip()
    original_attr = str(generation.get("original_attribute", "")).strip()
    new_attr = str(generation.get("new_attribute", "")).strip()
    if not modified or modified == original:
        return "generated_no_change"
    if not original_attr or not new_attr:
        return "missing_attribute_metadata"
    if norm(original_attr) == norm(new_attr):
        return "same_attribute"
    if extract_numbers(original) != extract_numbers(modified):
        return "number_changed"
    attr = rec.get("attribute") or {}
    start = attr.get("attribute_start")
    end = attr.get("attribute_end")
    original_without_target = (
        original[:start] + original[end:]
        if isinstance(start, int) and isinstance(end, int)
        else original
    )
    if f" {norm(new_attr)} " in f" {norm(original_without_target)} ":
        return "new_attribute_already_elsewhere_in_original"
    artifact_reason = broad_or_artifact_reason(original)
    if artifact_reason:
        return f"source_filter:{artifact_reason}"
    if original[attr.get("attribute_start"):attr.get("attribute_end")] != original_attr:
        return "attribute_span_mismatch"
    entity_texts = rec.get("entity_texts") or []
    for ent in entity_texts:
        if norm(ent) == norm(original_attr):
            continue
        if norm(ent) and f" {norm(ent)} " not in f" {norm(modified)} ":
            return "named_entity_removed_or_changed"
    return "accepted"


def source_filter(rec: dict, post_filter: str) -> str:
    if post_filter == "none":
        return ""
    claim = rec["claim_text"]
    reason = broad_or_artifact_reason(claim)
    if reason:
        return reason
    attr = rec.get("attribute") or {}
    attribute_type = attr.get("attribute_type")
    attribute_text = norm(attr.get("attribute_text", ""))
    if post_filter in {"strict_v2", "strict_v3"}:
        if attribute_type == "genre" and attribute_text in {"action", "adventure", "fantasy"}:
            return "genre_term_often_used_as_modifier_or_broad_category"
        if attribute_type == "occupation" and attribute_text in {"writer", "author", "producer"}:
            return "occupation_term_often_broad_or_multi_role"
    if post_filter == "strict_v3":
        attr = rec.get("attribute") or {}
        start = attr.get("attribute_start")
        end = attr.get("attribute_end")
        after = claim[end:end + 30].lower() if isinstance(end, int) else ""
        before = claim[max(0, start - 30):start].lower() if isinstance(start, int) else ""
        if attribute_type == "nationality" and attribute_text in {"english", "scottish", "welsh"}:
            return "nationality_term_can_be_language_or_regional_modifier"
        if attribute_type == "occupation" and re.match(r"\s+of\b", after):
            return "occupation_followed_by_of_phrase"
        if attribute_type == "genre" and re.match(r"\s+(?:duo|novelist|writer|author|band)\b", after):
            return "genre_modifies_non_work_head_noun"
        if attribute_type == "genre" and re.search(r"\banything to do with\s+$", before):
            return "genre_in_non_attribute_activity_frame"
        if attribute_type == "genre" and re.match(
            r"\s+(?:american|british|canadian|french|german|indian|italian|"
            r"japanese|chinese|australian|spanish|russian|mexican|swedish|"
            r"korean|english|irish|dutch|brazilian|israeli)\b",
            after,
        ):
            return "genre_before_nationality_modifier"
    return ""


def make_stratified_order(records: list[dict], seed: int) -> list[dict]:
    """Fixed deterministic order, locally stratified by attribute_type/length_bin."""
    rng = random.Random(seed)
    groups = {}
    for rec in records:
        attr = rec.get("attribute") or {}
        key = (attr.get("attribute_type", "missing"), rec.get("length_bin", "missing"))
        groups.setdefault(key, []).append(rec)
    for group in groups.values():
        rng.shuffle(group)

    strata = sorted(groups)
    weights = {key: len(groups[key]) for key in strata}
    total = sum(weights.values())
    taken = Counter()
    order = []
    while len(order) < total:
        available = [key for key in strata if taken[key] < weights[key]]
        if not available:
            break
        key = max(
            available,
            key=lambda k: (weights[k] / total) - (taken[k] / max(1, len(order))),
        )
        order.append(groups[key][taken[key]])
        taken[key] += 1
    return order


def load_attempts(path: Path) -> tuple[set[tuple[str, str]], list[dict], list[dict], list[dict]]:
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


def accepted_replacement_counts(corrupted: list[dict]) -> Counter:
    counts = Counter()
    for item in corrupted:
        original = item.get("original_attribute", "")
        shown = item.get("shown_attribute", "")
        if original and shown:
            counts[(norm(original), norm(shown))] += 1
    return counts


def final_counts(records: list[dict], field: str) -> dict:
    return dict(Counter(rec.get(field, "missing") for rec in records))


def item_base(rec: dict, args: argparse.Namespace) -> dict:
    attr = rec.get("attribute") or {}
    return {
        "kind": "attribute",
        "pool_version": args.pool_version,
        "source_claim_id": rec["claim_id"],
        "base_claim_id": rec.get("base_claim_id"),
        "fever_id": rec.get("fever_id"),
        "attribute_type": attr.get("attribute_type"),
        "entity_type": rec.get("entity_type"),
        "length_bin": rec.get("length_bin"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default="data/frozen/attribute_v1/attribute_pool_v1.jsonl")
    ap.add_argument("--pool-version", default="v1")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n-corrupt", type=int, default=300)
    ap.add_argument("--n-clean", type=int, default=300)
    ap.add_argument("--out", default="")
    ap.add_argument("--post-filter", choices=["none", "strict_v2", "strict_v3"], default="none")
    ap.add_argument(
        "--replacement-policy",
        choices=["preferred", "balanced_v3"],
        default="preferred",
    )
    ap.add_argument(
        "--replacement-pair-cap",
        type=int,
        default=0,
        help="0 disables pair caps; v3 uses this to avoid template concentration.",
    )
    args = ap.parse_args()

    if not os.environ.get("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    pool_path = ROOT / args.pool
    stem = f"attribute_corruption_pool_{args.pool_version}_n{args.n_corrupt}"
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
    pair_counts = accepted_replacement_counts(corrupted)
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
        item = None
        claim = rec["claim_text"]
        source_reason = source_filter(rec, args.post_filter)
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
            attr = rec.get("attribute") or {}
            item = {
                **item_base(rec, args),
                "statement": claim,
                "gold": "true",
                "is_corrupted": False,
                "original_statement": claim,
                "original_attribute": attr.get("attribute_text"),
                "shown_attribute": attr.get("attribute_text"),
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
        item = None
        status = "rejected"
        reason = "accepted"
        v, err = {}, None
        source_reason = source_filter(rec, args.post_filter)
        generation = {}
        if source_reason:
            reason = f"source_filter:{source_reason}"
        else:
            generation, gen_reason = replace_attribute(
                rec,
                policy=args.replacement_policy,
                pair_counts=pair_counts,
                pair_cap=args.replacement_pair_cap,
            )
            reason = gen_reason or "accepted"
            if generation:
                post_reason = local_post_filter(rec, generation)
                if post_reason != "accepted":
                    reason = f"post_filter:{post_reason}"
                else:
                    shown = generation["corrupted"]
                    v, err = call_json(VAL_CORRUPT.format(
                        original=rec["claim_text"],
                        modified=shown,
                        original_attribute=generation["original_attribute"],
                        new_attribute=generation["new_attribute"],
                        attribute_type=generation["attribute_type"],
                    ))
                    if gate_corrupt(v):
                        status = "accepted"
                        reason = "accepted"
                        item = {
                            **item_base(rec, args),
                            "statement": shown,
                            "gold": "false",
                            "is_corrupted": True,
                            "original_statement": rec["claim_text"],
                            "original_attribute": generation["original_attribute"],
                            "shown_attribute": generation["new_attribute"],
                            "corruption_rule": generation["corruption_rule"],
                        }
                        corrupted.append(item)
                        pair_counts[(norm(generation["original_attribute"]), norm(generation["new_attribute"]))] += 1
                    else:
                        reason = reject_reason(v, [
                            "original_supported", "original_is_atomic_fact",
                            "corrupted_is_false", "target_is_non_entity_attribute",
                            "single_attribute_change_only", "fluent_no_artifact"])
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
    id_prefix = f"attr{args.pool_version}_"
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
        "manifest_type": "build_manifest",
        "artifact_type": "build_manifest",
        "stage": "construction",
        "family": "attribute",
        "dataset": str(out_path.relative_to(ROOT)),
        "pool": str(pool_path.relative_to(ROOT)),
        "pool_version": args.pool_version,
        "seed": args.seed,
        "n_clean": args.n_clean,
        "n_corrupt": args.n_corrupt,
        "sampling": {
            "method": "fixed-seed local-stratified order over (attribute_type, length_bin)",
            "class_assignment": "even positions clean, odd positions corrupted",
            "gpt4o_in_sampling": False,
            "gpt4o_role": "hard-gate validation only",
            "local_generation": "deterministic attribute substitution",
            "local_post_filter": args.post_filter,
            "replacement_policy": args.replacement_policy,
            "replacement_pair_cap": args.replacement_pair_cap,
        },
        "attrition": dict(attrition),
        "rejection_reasons": dict(reasons),
        "final_strata": {
            "length_bin": final_counts(items, "length_bin"),
            "attribute_type": final_counts(items, "attribute_type"),
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
