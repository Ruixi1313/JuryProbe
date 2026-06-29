#!/usr/bin/env python3
"""Build versioned FEVER claim pools for JuryProbe.

Phase 0 pool-first pipeline:
  FEVER SUPPORTS -> master_claim_pool_v1.jsonl
                 -> number_pool_v1.jsonl
                 -> entity_pool_v1.jsonl
                 -> relation_pool_v1.jsonl
                 -> pool_manifest_v1.json

This script intentionally uses only local, pre-specified filters. GPT-4o should
not participate in item selection; it is reserved for downstream corruption
validation and difficulty/detectability analysis.

Usage:
  python scripts/build_fever_claim_pool.py --seed 42
"""
from __future__ import annotations

import argparse
import json
import random
import re
import ssl
import urllib.request
from collections import Counter
from pathlib import Path

try:
    import certifi
    SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL = ssl.create_default_context()

ROOT = Path(__file__).resolve().parents[1]
FEVER_URL = "https://fever.ai/download/fever/train.jsonl"

NUM_RE = re.compile(
    r"(?<![\w./-])"
    r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)"
    r"(?:\s?(%|percent))?"
    r"(?![\w./-])",
    re.IGNORECASE,
)
HEDGE_RE = re.compile(
    r"\b(about|approximately|approx\.?|around|roughly|nearly|almost|"
    r"over|under|more than|less than|at least|at most|up to|between|from)\b",
    re.IGNORECASE,
)
BAD_NUM_CONTEXT_RE = re.compile(
    r"\b(version|episode|season|chapter|volume|model|iphone|playstation|"
    r"windows|macos|html|usb|http|gdp|isbn)\b",
    re.IGNORECASE,
)
ENTITY_TOKEN = r"(?:[A-Z][a-z]+(?:-[A-Z][a-z]+)?|[A-Z]{2,})"
ENTITY_RE = re.compile(
    rf"\b{ENTITY_TOKEN}(?:\s+(?:of|the|and|&|de|la|von|{ENTITY_TOKEN}))*\b"
)
ENTITY_STOP = {
    "The", "A", "An", "In", "On", "At", "By", "For", "From", "With",
    "This", "That", "It", "He", "She", "They", "His", "Her", "Their",
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
}
MONTHS = {
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December",
}
RELATION_PATTERNS = [
    ("increase_decrease", re.compile(
        r"\b(increased|decreased|increases|decreases|rose|fell|rises|falls|"
        r"grew|declined|expanded|contracted)\b", re.I)),
    ("cause_prevent", re.compile(
        r"\b(caused|causes|led to|leads to|resulted in|results in|"
        r"prevented|prevents|stopped|stops|enabled|enables)\b", re.I)),
    ("defeat_win_loss", re.compile(
        r"\b(defeated|defeats|beat|beats|lost to|loses to|won against|"
        r"wins against|was defeated by|were defeated by)\b", re.I)),
    ("before_after", re.compile(
        r"\b(before|after|preceded|precedes|followed by)\b", re.I)),
    ("support_oppose", re.compile(
        r"\b(supported|supports|opposed|opposes|endorsed|endorses|"
        r"criticized|criticizes)\b", re.I)),
    ("acquire_reverse", re.compile(
        r"\b(acquired|acquires|bought|buys|purchased|purchases|"
        r"was acquired by|were acquired by|merged with)\b", re.I)),
]


def stream_fever():
    req = urllib.request.Request(FEVER_URL, headers={"User-Agent": "juryprobe/0.1"})
    with urllib.request.urlopen(req, timeout=60, context=SSL) as resp:
        for raw in resp:
            try:
                yield json.loads(raw.decode("utf-8"))
            except Exception:
                continue


def evidence_stub(row):
    out = []
    for group in row.get("evidence") or []:
        for item in group:
            if isinstance(item, list) and len(item) >= 4 and item[2] is not None:
                out.append({"wiki_url": item[2], "sentence_id": item[3]})
    uniq = [dict(t) for t in {tuple(sorted(d.items())) for d in out}]
    return uniq[:4]


def length_bin(n_words):
    if n_words <= 10:
        return "short"
    if n_words <= 18:
        return "medium"
    return "long"


def local_atomic_candidate(claim):
    words = claim.split()
    if len(words) < 6 or len(words) > 35:
        return False
    if claim.count("?") or claim.count(";"):
        return False
    if claim.count(".") > 1:
        return False
    if HEDGE_RE.search(claim):
        return False
    return True


def normalize_num(text):
    return float(text.replace(",", ""))


def classify_number(text):
    raw = text.replace(",", "")
    if raw.isdigit():
        n = int(raw)
        if 1000 <= n <= 2099 and len(raw) == 4:
            return "year"
        return "integer"
    return "decimal"


def extract_number(claim):
    matches = list(NUM_RE.finditer(claim))
    if not matches:
        return None
    usable = []
    for m in matches:
        text = m.group(1)
        try:
            value = normalize_num(text)
        except Exception:
            continue
        if value < 10:
            continue
        window = claim[max(0, m.start(1) - 40): min(len(claim), m.end(1) + 40)]
        near = claim[max(0, m.start(1) - 5): min(len(claim), m.end(1) + 5)]
        if BAD_NUM_CONTEXT_RE.search(window):
            continue
        if any(sym in near for sym in ["-", "\u2013", "\u2014", " to "]):
            continue
        usable.append({
            "text": text,
            "value": value,
            "kind": classify_number(text),
            "start": m.start(1),
            "end": m.end(1),
        })
    return usable[0] if len(usable) == 1 else None


def extract_entities(claim):
    entities = []
    for m in ENTITY_RE.finditer(claim):
        text = m.group(0).strip()
        if text in ENTITY_STOP:
            continue
        if text.startswith("The ") and text.split()[1] in MONTHS:
            continue
        if m.start() == 0 and len(text.split()) == 1:
            continue
        if text.lower() in {"true", "false"}:
            continue
        entities.append({"text": text, "start": m.start(), "end": m.end()})
    seen = set()
    deduped = []
    for ent in entities:
        if ent["text"] not in seen:
            seen.add(ent["text"])
            deduped.append(ent)
    return deduped


def classify_entity(claim, entities):
    if not entities:
        return "none"
    text = entities[0]["text"]
    low = text.lower()
    window = claim[max(0, entities[0]["start"] - 50): entities[0]["end"] + 50].lower()
    if any(x in low for x in ["university", "college", "school", "company",
                              "corporation", "inc", "ltd", "fc", "club",
                              "party", "association", "agency"]):
        return "organization_like"
    if any(x in low for x in ["states", "kingdom", "republic", "city", "county",
                              "province", "island", "river", "mount"]):
        return "place_like"
    if re.search(r"\b(born|actor|actress|singer|writer|author|director|player|"
                 r"president|minister|coach|member|son|daughter)\b", window):
        return "person_like"
    if re.search(r"\b(album|film|movie|novel|book|song|series|show|episode)\b", window):
        return "work_like"
    if len(text.split()) >= 2:
        return "multi_token_proper_noun"
    return "single_token_proper_noun"


def overlaps_entity(span, entities):
    start, end = span
    return any(start < ent["end"] and end > ent["start"] for ent in entities)


def detect_relation(claim, entities):
    for name, rx in RELATION_PATTERNS:
        for m in rx.finditer(claim):
            if not overlaps_entity(m.span(), entities):
                return name
    return "none"


def make_record(row, pool_rank):
    claim = (row.get("claim") or "").strip()
    words = claim.split()
    number = extract_number(claim)
    entities = extract_entities(claim)
    relation_type = detect_relation(claim, entities)
    fever_id = row.get("id")
    return {
        "claim_id": f"fever_{fever_id}",
        "fever_id": fever_id,
        "source": "FEVER",
        "label": "SUPPORTS",
        "pool_rank": pool_rank,
        "claim_text": claim,
        "claim_length": len(words),
        "length_bin": length_bin(len(words)),
        "has_number": number is not None,
        "has_entity": bool(entities),
        "has_relation": relation_type != "none",
        "number": number,
        "entity_texts": [e["text"] for e in entities],
        "entity_type": classify_entity(claim, entities),
        "relation_type": relation_type,
        "evidence_stub": evidence_stub(row),
    }


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def counts(records, field):
    return dict(Counter(rec.get(field, "missing") for rec in records))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v1")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--master-limit", type=int, default=0,
                    help="0 means keep all locally atomic FEVER SUPPORTS claims.")
    ap.add_argument("--max-scan", type=int, default=0,
                    help="0 means scan the full FEVER stream.")
    args = ap.parse_args()

    attrition = Counter()
    candidates = []
    seen_claims = set()
    for row in stream_fever():
        attrition["fever_rows_scanned"] += 1
        if args.max_scan and attrition["fever_rows_scanned"] > args.max_scan:
            break
        if str(row.get("label", "")).upper() != "SUPPORTS":
            attrition["non_supports"] += 1
            continue
        attrition["supports_rows"] += 1
        claim = (row.get("claim") or "").strip()
        if not claim:
            attrition["empty_claim"] += 1
            continue
        if claim in seen_claims:
            attrition["duplicate_claim"] += 1
            continue
        seen_claims.add(claim)
        if not local_atomic_candidate(claim):
            attrition["local_atomic_reject"] += 1
            continue
        attrition["local_atomic_pass"] += 1
        candidates.append(row)

    if args.master_limit > 0:
        rng = random.Random(args.seed)
        rng.shuffle(candidates)
        selected_rows = candidates[:args.master_limit]
        selection = "shuffle local-atomic candidates with fixed seed, then take master-limit"
    else:
        selected_rows = candidates
        selection = "keep all local-atomic candidates; fixed seed is used downstream for sampling"
    master = [make_record(row, i + 1) for i, row in enumerate(selected_rows)]
    number_pool = [rec for rec in master if rec["has_number"]]
    entity_pool = [rec for rec in master if rec["has_entity"]]
    relation_pool = [rec for rec in master if rec["has_relation"]]

    data_dir = ROOT / "data"
    master_path = data_dir / f"master_claim_pool_{args.version}.jsonl"
    number_path = data_dir / f"number_pool_{args.version}.jsonl"
    entity_path = data_dir / f"entity_pool_{args.version}.jsonl"
    relation_path = data_dir / f"relation_pool_{args.version}.jsonl"
    manifest_path = data_dir / f"pool_manifest_{args.version}.json"

    write_jsonl(master_path, master)
    write_jsonl(number_path, number_pool)
    write_jsonl(entity_path, entity_pool)
    write_jsonl(relation_path, relation_pool)

    manifest = {
        "source": "FEVER",
        "version": args.version,
        "seed": args.seed,
        "master_pool_size": len(master),
        "number_pool_size": len(number_pool),
        "entity_pool_size": len(entity_pool),
        "relation_pool_size": len(relation_pool),
        "files": {
            "master": str(master_path.relative_to(ROOT)),
            "number": str(number_path.relative_to(ROOT)),
            "entity": str(entity_path.relative_to(ROOT)),
            "relation": str(relation_path.relative_to(ROOT)),
        },
        "filters": {
            "source_label": "SUPPORTS",
            "local_atomic": {
                "min_words": 6,
                "max_words": 35,
                "rejects": ["multiple periods", "question marks", "semicolons",
                            "hedged approximate claims"],
            },
            "selection": selection,
            "gpt4o_in_pool_selection": False,
        },
        "attrition": dict(attrition),
        "strata": {
            "master_length_bin": counts(master, "length_bin"),
            "number_kind": dict(Counter(
                rec["number"]["kind"] for rec in number_pool if rec.get("number")
            )),
            "entity_type": counts(entity_pool, "entity_type"),
            "relation_type": counts(relation_pool, "relation_type"),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(json.dumps({
        "master_pool_size": len(master),
        "number_pool_size": len(number_pool),
        "entity_pool_size": len(entity_pool),
        "relation_pool_size": len(relation_pool),
        "manifest": str(manifest_path.relative_to(ROOT)),
    }, indent=2))


if __name__ == "__main__":
    main()
