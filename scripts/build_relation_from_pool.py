#!/usr/bin/env python3
"""Build pool-based Relation Reversal corruption data.

Frozen input:
  data/frozen/v1/relation_pool_v1.jsonl

Output:
  data/relation_corruption_pool_<version>_n300.jsonl
  results/relation_corruption_pool_<version>_n300_build_attempts.jsonl
  results/relation_corruption_pool_<version>_n300_build_manifest.json

Sampling is fixed-seed and pool-based. Relation corruption is produced by
deterministic local reversal rules; GPT-4o is used only as a hard-gate
validator, not to choose items or invent corruptions.
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
  "fluent_no_artifact": true/false}}
- original_supported: is it factually TRUE?
- original_is_atomic_fact: a single precise verifiable claim?
- fluent_no_artifact: fluent, no artifact.

CLAIM: {claim}"""

VAL_CORRUPT = """You are the CORRUPTION VALIDATOR. Given an ORIGINAL true claim
and a MODIFIED version where a semantic relation was reversed or contradicted,
return ONLY JSON with EXACTLY:
{{"original_supported": true/false, "original_is_atomic_fact": true/false,
  "corrupted_is_false": true/false, "single_relation_change_only": true/false,
  "fluent_no_artifact": true/false}}
- original_supported: is the ORIGINAL factually TRUE?
- original_is_atomic_fact: a single precise verifiable claim?
- corrupted_is_false: is the MODIFIED clearly factually FALSE? If it could
  still be true, merely uncertain, or too broad to verify as false, return false.
- single_relation_change_only: was exactly one relation word/phrase changed,
  with entities, numbers, dates, and surrounding wording preserved?
- fluent_no_artifact: modified reads naturally, no tampering seam.

ORIGINAL: {original}
MODIFIED: {modified}"""

NUM_RE = re.compile(r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?")

SOURCE_FILTERS = {
    "before_after": [
        ("named_after_idiom", re.compile(r"\bnamed after\b", re.I)),
        ("made_after_idiom", re.compile(r"\bmade after\b", re.I)),
    ],
    "increase_decrease": [
        ("grew_up_idiom", re.compile(r"\bgrew up\b", re.I)),
        ("contracted_disease_idiom", re.compile(
            r"\bcontracted\s+(?:typhoid|fever|disease|illness|infection)\b", re.I)),
        ("declined_to_idiom", re.compile(r"\bdeclined to\b", re.I)),
    ],
    "cause_prevent": [
        ("noun_causes_frame", re.compile(r"\b(social|political|various)\s+causes\b", re.I)),
    ],
    "acquire_reverse": [
        ("acquired_love_or_taste", re.compile(r"\bacquired\s+a\s+(?:love|taste)\b", re.I)),
    ],
}
SOURCE_FILTERS_STRICT_V2 = {
    "before_after": [
        ("comparative_ranking_after", re.compile(
            r"\b(?:second|third|fourth)[-\s]+(?:longest|largest|highest|biggest|"
            r"opening|grossing)\b.*\bafter\b|\bcame in second after\b",
            re.I)),
    ],
    "support_oppose": [
        ("hyphenated_relation_modifier", re.compile(
            r"-\s*(?:endorsed|supported|opposed|criticized)\b", re.I)),
        ("vague_others_frame", re.compile(r"\b(?:opposed|supported)\s+others\b", re.I)),
    ],
    "increase_decrease": [
        ("expanded_to_artifact", re.compile(r"\bexpanded to\b", re.I)),
    ],
}
SOURCE_FILTERS_STRICT_V3 = {
    "before_after": [
        ("count_or_schedule_after_frame", re.compile(
            r"\bended after\s+\d+\b.*\bgames\b", re.I)),
    ],
    "increase_decrease": [
        ("rose_fell_to_fame_idiom", re.compile(
            r"\b(?:rose|rises|fell|falls)\s+to\s+(?:fame|prominence)\b", re.I)),
        ("rose_to_rank_frame", re.compile(
            r"\b(?:rose|rises)\s+to\s+(?:the\s+)?rank\b", re.I)),
        ("falls_in_category_frame", re.compile(
            r"\bfalls?\s+in\s+(?:the\s+)?.*category\b", re.I)),
    ],
}
SOURCE_FILTERS_STRICT_V4 = {
    "before_after": [
        ("naming_after_paraphrase", re.compile(r"\bgiven a name after\b", re.I)),
        ("ordinal_most_ranking_after", re.compile(
            r"\b(?:second|third|fourth)[-\s]+most\b.*\bafter\b", re.I)),
        ("broad_another_before_after_frame", re.compile(
            r"\bcame\s+(?:before|after)\s+another\b", re.I)),
    ],
    "acquire_reverse": [
        ("merged_with_to_form_frame", re.compile(
            r"\bmerged with\b.*\bto\s+(?:form|establish)\b", re.I)),
    ],
}
SOURCE_FILTERS_STRICT_V5 = {
    "before_after": [
        ("after_a_while_idiom", re.compile(r"\bafter a while\b", re.I)),
    ],
    "cause_prevent": [
        ("enabled_to_frame", re.compile(r"\benabled\b.*\bto\b", re.I)),
    ],
    "increase_decrease": [
        ("falls_within_category_frame", re.compile(r"\bfalls?\s+within\b", re.I)),
    ],
}

REVERSALS = {
    "before_after": [
        (r"\bfollowed by\b", "preceded by"),
        (r"\bpreceded\b", "followed"),
        (r"\bprecedes\b", "follows"),
        (r"\bbefore\b", "after"),
        (r"\bafter\b", "before"),
    ],
    "defeat_win_loss": [
        (r"\bwas defeated by\b", "defeated"),
        (r"\bwere defeated by\b", "defeated"),
        (r"\bwon against\b", "lost to"),
        (r"\bwins against\b", "loses to"),
        (r"\blost to\b", "defeated"),
        (r"\bloses to\b", "defeats"),
        (r"\bdefeated\b", "lost to"),
        (r"\bdefeats\b", "loses to"),
        (r"\bbeat\b", "lost to"),
        (r"\bbeats\b", "loses to"),
    ],
    "support_oppose": [
        (r"\bwas strongly opposed by\b", "was strongly supported by"),
        (r"\bopposed to\b", "supportive of"),
        (r"\bsupported\b", "opposed"),
        (r"\bsupports\b", "opposes"),
        (r"\bopposed\b", "supported"),
        (r"\bopposes\b", "supports"),
        (r"\bendorsed\b", "opposed"),
        (r"\bendorses\b", "opposes"),
        (r"\bcriticized\b", "supported"),
        (r"\bcriticizes\b", "supports"),
    ],
    "cause_prevent": [
        (r"\bcan be prevented by\b", "can be caused by"),
        (r"\bprevented by\b", "caused by"),
        (r"\bprevented\b", "caused"),
        (r"\bprevents\b", "causes"),
        (r"\bstopped\b", "caused"),
        (r"\bstops\b", "causes"),
        (r"\benabled\b", "prevented"),
        (r"\benables\b", "prevents"),
        (r"\bresulted in\b", "prevented"),
        (r"\bresults in\b", "prevents"),
        (r"\bled to\b", "prevented"),
        (r"\bleads to\b", "prevents"),
        (r"\bcaused\b", "prevented"),
        (r"\bcauses\b", "prevents"),
    ],
    "increase_decrease": [
        (r"\bincreased\b", "decreased"),
        (r"\bincreases\b", "decreases"),
        (r"\bdecreased\b", "increased"),
        (r"\bdecreases\b", "increases"),
        (r"\brose\b", "fell"),
        (r"\brises\b", "falls"),
        (r"\bfell\b", "rose"),
        (r"\bfalls\b", "rises"),
        (r"\bexpanded\b", "contracted"),
        (r"\bexpands\b", "contracts"),
        (r"\bcontracted\b", "expanded"),
        (r"\bcontracts\b", "expands"),
        (r"\bgrew\b", "declined"),
        (r"\bdeclined\b", "grew"),
    ],
    "acquire_reverse": [
        (r"\bwas acquired by\b", "acquired"),
        (r"\bwere acquired by\b", "acquired"),
        (r"\bacquired\b", "sold"),
        (r"\bacquires\b", "sells"),
        (r"\bbought\b", "sold"),
        (r"\bbuys\b", "sells"),
        (r"\bpurchased\b", "sold"),
        (r"\bpurchases\b", "sells"),
        (r"\bmerged with\b", "split from"),
    ],
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
        "single_relation_change_only", "fluent_no_artifact"))


def reject_reason(v, keys):
    if not v:
        return "validator_parse_or_api_fail"
    failed = [k for k in keys if v.get(k) is not True]
    return ",".join(failed) if failed else "accepted"


def norm_text(text):
    text = str(text).lower().replace("\u2019", "'").replace("`", "'")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def contains_norm(haystack, needle):
    needle_norm = norm_text(needle)
    if not needle_norm:
        return False
    return f" {needle_norm} " in f" {norm_text(haystack)} "


def extract_numbers(text):
    return NUM_RE.findall(text)


def source_filter(rec, post_filter="none"):
    claim = rec["claim_text"]
    for reason, rx in SOURCE_FILTERS.get(rec.get("relation_type"), []):
        if rx.search(claim):
            return reason
    if post_filter in {"strict_v2", "strict_v3", "strict_v4", "strict_v5"}:
        for reason, rx in SOURCE_FILTERS_STRICT_V2.get(rec.get("relation_type"), []):
            if rx.search(claim):
                return reason
    if post_filter in {"strict_v3", "strict_v4", "strict_v5"}:
        for reason, rx in SOURCE_FILTERS_STRICT_V3.get(rec.get("relation_type"), []):
            if rx.search(claim):
                return reason
    if post_filter in {"strict_v4", "strict_v5"}:
        for reason, rx in SOURCE_FILTERS_STRICT_V4.get(rec.get("relation_type"), []):
            if rx.search(claim):
                return reason
    if post_filter == "strict_v5":
        for reason, rx in SOURCE_FILTERS_STRICT_V5.get(rec.get("relation_type"), []):
            if rx.search(claim):
                return reason
    return ""


def match_case(original, replacement):
    if not original:
        return replacement
    if original[0].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def reverse_relation(rec, preserve_case=False):
    claim = rec["claim_text"]
    relation_type = rec.get("relation_type")
    for pattern, replacement in REVERSALS.get(relation_type, []):
        rx = re.compile(pattern, re.I)
        m = rx.search(claim)
        if not m:
            continue
        original_relation = m.group(0)
        if preserve_case:
            replacement = match_case(original_relation, replacement)
        modified = claim[:m.start()] + replacement + claim[m.end():]
        return {
            "corrupted": modified,
            "original_relation": original_relation,
            "new_relation": replacement,
            "transform_pattern": pattern,
        }, ""
    return {}, "no_reversal_rule_match"


def local_post_filter(rec, generation):
    original = rec["claim_text"]
    modified = str(generation.get("corrupted", "")).strip()
    original_relation = str(generation.get("original_relation", "")).strip()
    new_relation = str(generation.get("new_relation", "")).strip()
    if not modified or modified == original:
        return "generated_no_change"
    if not original_relation or not new_relation:
        return "missing_relation_metadata"
    if norm_text(original_relation) == norm_text(new_relation):
        return "same_relation"
    if not contains_norm(original, original_relation):
        return "original_relation_not_in_original"
    if not contains_norm(modified, new_relation):
        return "new_relation_not_in_modified"
    if extract_numbers(original) != extract_numbers(modified):
        return "number_changed"
    for ent in rec.get("entity_texts") or []:
        if not contains_norm(modified, ent):
            return "entity_removed_or_changed"
    return "accepted"


def make_stratified_order(records, seed):
    rng = random.Random(seed)
    groups = {}
    for rec in records:
        key = (rec.get("relation_type", "missing"), rec.get("length_bin", "missing"))
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


def item_base(rec, args):
    return {
        "kind": "relation",
        "pool_version": args.pool_version,
        "source_claim_id": rec["claim_id"],
        "fever_id": rec.get("fever_id"),
        "relation_type": rec.get("relation_type"),
        "entity_type": rec.get("entity_type"),
        "length_bin": rec.get("length_bin"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default="data/frozen/v1/relation_pool_v1.jsonl")
    ap.add_argument("--pool-version", default="v1")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n-corrupt", type=int, default=300)
    ap.add_argument("--n-clean", type=int, default=300)
    ap.add_argument("--out", default="")
    ap.add_argument(
        "--post-filter",
        choices=["none", "strict_v2", "strict_v3", "strict_v4", "strict_v5"],
        default="none",
    )
    args = ap.parse_args()

    if not os.environ.get("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    pool_path = ROOT / args.pool
    stem = f"relation_corruption_pool_{args.pool_version}_n{args.n_corrupt}"
    out_path = ROOT / (args.out or f"data/{stem}.jsonl")
    attempts_path = ROOT / "results" / f"{stem}_build_attempts.jsonl"
    manifest_path = ROOT / "results" / f"{stem}_build_manifest.json"

    if out_path.exists():
        print(f"{out_path.relative_to(ROOT)} exists; delete to rebuild.")
        return

    pool = load_jsonl(pool_path)
    order = make_stratified_order(pool, args.seed)
    processed, clean, corrupted, prior_attempts = load_attempts(attempts_path)
    print(f"Pool={pool_path.relative_to(ROOT)} size={len(pool)} seed={args.seed}")
    print(f"Target={args.n_clean} clean + {args.n_corrupt} corrupted")
    if prior_attempts:
        print(f"Resuming from {len(prior_attempts)} logged attempts: "
              f"clean={len(clean)} corrupted={len(corrupted)}")

    for rec in order:
        if len(corrupted) >= args.n_corrupt:
            break
        key = ("corrupt", rec["claim_id"])
        if key in processed:
            continue
        item = None
        status = "rejected"
        reason = "accepted"
        v, val_err = {}, None
        preserve_case = args.post_filter in {
            "strict_v2", "strict_v3", "strict_v4", "strict_v5",
        }
        source_reason = source_filter(rec, post_filter=args.post_filter)
        if source_reason:
            reason = f"source_filter:{source_reason}"
            generation = {}
        else:
            generation, gen_reason = reverse_relation(rec, preserve_case=preserve_case)
            reason = gen_reason or "accepted"
            if generation:
                post_reason = local_post_filter(rec, generation)
                if post_reason != "accepted":
                    reason = f"post_filter:{post_reason}"
                else:
                    shown = generation["corrupted"]
                    v, val_err = call_json(VAL_CORRUPT.format(
                        original=rec["claim_text"], modified=shown))
                    if gate_corrupt(v):
                        status = "accepted"
                        reason = "accepted"
                        item = {
                            **item_base(rec, args),
                            "statement": shown,
                            "gold": "false",
                            "is_corrupted": True,
                            "original_statement": rec["claim_text"],
                            "original_relation": generation["original_relation"],
                            "new_relation": generation["new_relation"],
                            "transform_pattern": generation["transform_pattern"],
                        }
                        corrupted.append(item)
                    else:
                        reason = reject_reason(v, [
                            "original_supported", "original_is_atomic_fact",
                            "corrupted_is_false", "single_relation_change_only",
                            "fluent_no_artifact"])
        append_jsonl(attempts_path, {
            "role": "corrupt",
            "source_claim_id": rec["claim_id"],
            "status": status,
            "reason": reason,
            "api_error": val_err,
            "generation": generation,
            "validator": v,
            "item": item,
        })
        processed.add(key)
        if status == "accepted" and (len(clean) + len(corrupted)) % 25 == 0:
            print(f"  accepted clean={len(clean)} corrupted={len(corrupted)}", flush=True)

    corrupt_source_ids = {it["source_claim_id"] for it in corrupted}
    for rec in order:
        if len(clean) >= args.n_clean:
            break
        key = ("clean", rec["claim_id"])
        if key in processed:
            continue
        if rec["claim_id"] in corrupt_source_ids:
            continue
        source_reason = source_filter(rec, post_filter=args.post_filter)
        if source_reason:
            append_jsonl(attempts_path, {
                "role": "clean",
                "source_claim_id": rec["claim_id"],
                "status": "rejected",
                "reason": f"source_filter:{source_reason}",
                "api_error": None,
                "validator": {},
                "item": None,
            })
            processed.add(key)
            continue
        claim = rec["claim_text"]
        v, err = call_json(VAL_CLEAN.format(claim=claim))
        accepted = gate_clean(v)
        item = None
        if accepted:
            item = {
                **item_base(rec, args),
                "statement": claim,
                "gold": "true",
                "is_corrupted": False,
                "original_statement": claim,
                "source_overlap_with_corrupt": False,
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

    for rec in order:
        if len(clean) >= args.n_clean:
            break
        if rec["claim_id"] not in corrupt_source_ids:
            continue
        key = ("clean", rec["claim_id"])
        if key in processed:
            continue
        source_reason = source_filter(rec, post_filter=args.post_filter)
        if source_reason:
            append_jsonl(attempts_path, {
                "role": "clean",
                "source_claim_id": rec["claim_id"],
                "status": "rejected",
                "reason": f"source_filter:{source_reason}",
                "api_error": None,
                "validator": {},
                "overlap_fill": True,
                "item": None,
            })
            processed.add(key)
            continue
        claim = rec["claim_text"]
        v, err = call_json(VAL_CLEAN.format(claim=claim))
        accepted = gate_clean(v)
        item = None
        if accepted:
            item = {
                **item_base(rec, args),
                "statement": claim,
                "gold": "true",
                "is_corrupted": False,
                "original_statement": claim,
                "source_overlap_with_corrupt": True,
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
            "overlap_fill": True,
            "item": item,
        })
        processed.add(key)
        if accepted and (len(clean) + len(corrupted)) % 25 == 0:
            print(f"  accepted clean={len(clean)} corrupted={len(corrupted)}", flush=True)

    if len(clean) < args.n_clean or len(corrupted) < args.n_corrupt:
        print(f"INCOMPLETE: clean={len(clean)} corrupted={len(corrupted)}. "
              f"Re-run to continue from {attempts_path.relative_to(ROOT)}.")
        return

    items = clean[:args.n_clean] + corrupted[:args.n_corrupt]
    clean_ids = {it["source_claim_id"] for it in clean[:args.n_clean]}
    corrupt_ids = {it["source_claim_id"] for it in corrupted[:args.n_corrupt]}
    source_overlap_count = len(clean_ids & corrupt_ids)
    id_prefix = f"rel{args.pool_version}_"
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
            "method": "fixed-seed local-stratified order over (relation_type, length_bin)",
            "class_assignment": (
                "corrupt accepted first; clean uses remaining source ids, "
                "then overlap fill if needed"
            ),
            "source_overlap_count": source_overlap_count,
            "gpt4o_in_sampling": False,
            "gpt4o_role": "hard-gate validation only",
            "corruption_generation": "deterministic local relation reversal rules",
            "post_filter": args.post_filter,
        },
        "attrition": dict(attrition),
        "rejection_reasons": dict(reasons),
        "final_strata": {
            "length_bin": final_counts(items, "length_bin"),
            "relation_type": final_counts(items, "relation_type"),
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
