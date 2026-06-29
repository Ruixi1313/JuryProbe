#!/usr/bin/env python3
"""Build an Attribute candidate pool from the frozen FEVER master frame.

This is a family-specific construction frame added after the original Phase-0
pool freeze. It does not modify `pool_manifest_v1.json`; instead it derives a
separate Attribute pool from the frozen master claim pool and records its own
pool-freeze manifest.

Attribute candidates replace a non-entity descriptive attribute of the same
subject, such as nationality, occupation, genre, language, or type.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


ATTRIBUTE_PATTERNS_BROAD = [
    (
        "language",
        re.compile(
            r"\b(?P<value>English[- ]language|French[- ]language|Spanish[- ]language|"
            r"Japanese[- ]language|German[- ]language|Italian[- ]language|"
            r"Chinese[- ]language|Korean[- ]language|Hindi[- ]language|"
            r"Tamil[- ]language|Russian[- ]language|Portuguese[- ]language|"
            r"Arabic[- ]language|Mandarin[- ]language|Bengali[- ]language|"
            r"Telugu[- ]language|Persian[- ]language|Latin[- ]language)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "type",
        re.compile(
            r"\b(?P<value>public university|private university|liberal arts college|"
            r"research university|professional wrestler|professional footballer|"
            r"professional basketball player|professional baseball player)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "genre",
        re.compile(
            r"\b(?P<value>black comedy|romantic comedy|science fiction|"
            r"comedy|drama|thriller|horror|documentary|animated|romance|"
            r"action|adventure|fantasy|crime|mystery|western|musical)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "occupation",
        re.compile(
            r"\b(?P<value>actor|actress|singer|writer|author|director|"
            r"filmmaker|producer|composer|musician|novelist|poet|politician|"
            r"footballer|basketball player|baseball player|tennis player|"
            r"journalist|comedian)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "nationality",
        re.compile(
            r"\b(?P<value>American|British|Canadian|French|German|Indian|"
            r"Italian|Japanese|Chinese|Australian|Spanish|Russian|Mexican|"
            r"Swedish|Korean|English|Irish|Dutch|Brazilian|Norwegian|Danish|"
            r"Polish|Turkish|Greek|Scottish|Welsh|Israeli)\b",
            re.IGNORECASE,
        ),
    ),
]

ATTRIBUTE_PATTERNS_STRICT = [
    (
        "language",
        re.compile(
            r"\b(?:is|was|are|were)\s+(?:an?\s+)?(?P<value>"
            r"English[- ]language|French[- ]language|Spanish[- ]language|"
            r"Japanese[- ]language|German[- ]language|Italian[- ]language|"
            r"Chinese[- ]language|Korean[- ]language|Hindi[- ]language|"
            r"Tamil[- ]language|Russian[- ]language|Portuguese[- ]language|"
            r"Arabic[- ]language|Mandarin[- ]language|Bengali[- ]language|"
            r"Telugu[- ]language|Persian[- ]language|Latin[- ]language)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "type",
        re.compile(
            r"\b(?:is|was|are|were)\s+(?:an?\s+)?(?P<value>"
            r"public university|private university|liberal arts college|"
            r"research university|professional wrestler|professional footballer|"
            r"professional basketball player|professional baseball player)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "genre",
        re.compile(
            r"\b(?:is|was|are|were)\s+(?:an?\s+)?(?:American|British|Canadian|"
            r"French|German|Indian|Italian|Japanese|Chinese|Australian|Spanish|"
            r"Russian|Mexican|Swedish|Korean|English|Irish|Dutch|Brazilian|"
            r"Israeli)?\s*(?P<value>black comedy|romantic comedy|science fiction|"
            r"comedy|drama|thriller|horror|documentary|animated|romance|action|"
            r"adventure|fantasy|crime|mystery|western|musical)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "occupation",
        re.compile(
            r"\b(?:is|was|are|were|works as|worked as)\s+(?:an?\s+)?"
            r"(?:American|British|Canadian|French|German|Indian|Italian|Japanese|"
            r"Chinese|Australian|Spanish|Russian|Mexican|Swedish|Korean|English|"
            r"Irish|Dutch|Brazilian|Israeli)?\s*(?P<value>actor|actress|singer|"
            r"writer|author|director|filmmaker|producer|composer|musician|"
            r"novelist|poet|politician|footballer|basketball player|"
            r"baseball player|tennis player|journalist|comedian)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "nationality",
        re.compile(
            r"\b(?:is|was|are|were|becomes|became|born)\s+(?:an?\s+)?"
            r"(?P<value>American|British|Canadian|French|German|Indian|Italian|"
            r"Japanese|Chinese|Australian|Spanish|Russian|Mexican|Swedish|"
            r"Korean|English|Irish|Dutch|Brazilian|Norwegian|Danish|Polish|"
            r"Turkish|Greek|Scottish|Welsh|Israeli)\b",
            re.IGNORECASE,
        ),
    ),
]

SOURCE_FILTERS = [
    ("question_or_semicolon", re.compile(r"[?;]")),
    ("list_like_history_frame", re.compile(r"\bincludes\b.*,\s+.*,\s+", re.IGNORECASE)),
    ("metalinguistic_term_frame", re.compile(r"\b(?:word|term|name)\b", re.IGNORECASE)),
    ("broad_there_is_frame", re.compile(r"^\s*There (?:is|are)\b", re.IGNORECASE)),
    ("called_frame", re.compile(r"\bcalled\b", re.IGNORECASE)),
]


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).strip().lower())


def source_filter(claim: str) -> str:
    for reason, rx in SOURCE_FILTERS:
        if rx.search(claim):
            return reason
    return ""


def surrounding_frame(claim: str, start: int, end: int, width: int = 40) -> str:
    return claim[max(0, start - width): min(len(claim), end + width)]


def extract_attribute_candidates(rec: dict, max_per_claim: int, context_mode: str) -> list[dict]:
    claim = rec["claim_text"]
    reason = source_filter(claim)
    if reason:
        return []

    patterns = ATTRIBUTE_PATTERNS_STRICT if context_mode == "strict" else ATTRIBUTE_PATTERNS_BROAD
    seen_spans = set()
    out = []
    for attribute_type, rx in patterns:
        for match in rx.finditer(claim):
            start, end = match.span("value")
            value = match.group("value")
            span = (start, end)
            if span in seen_spans:
                continue
            seen_spans.add(span)
            out.append({
                "attribute_type": attribute_type,
                "attribute_text": value,
                "attribute_start": start,
                "attribute_end": end,
                "attribute_frame": surrounding_frame(claim, start, end),
            })
            if len(out) >= max_per_claim:
                return out
    return out


def make_attribute_record(rec: dict, attr: dict, index: int) -> dict:
    base_claim_id = rec["claim_id"]
    return {
        **rec,
        "claim_id": f"{base_claim_id}:attr{index}",
        "base_claim_id": base_claim_id,
        "has_attribute": True,
        "attribute": attr,
    }


def counts(records: list[dict], field: str) -> dict:
    return dict(Counter(rec.get(field, "missing") for rec in records))


def nested_counts(records: list[dict], key: str) -> dict:
    return dict(Counter((rec.get("attribute") or {}).get(key, "missing") for rec in records))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", default="data/frozen/v1/master_claim_pool_v1.jsonl")
    ap.add_argument("--version", default="v1")
    ap.add_argument("--max-per-claim", type=int, default=1)
    ap.add_argument("--out-dir", default="data/frozen/attribute_v1")
    ap.add_argument("--context-mode", choices=["broad", "strict"], default="broad")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    master_path = ROOT / args.master
    out_dir = ROOT / args.out_dir
    pool_path = out_dir / f"attribute_pool_{args.version}.jsonl"
    manifest_path = out_dir / f"attribute_pool_manifest_{args.version}.json"
    if (pool_path.exists() or manifest_path.exists()) and not args.force:
        raise SystemExit(f"{pool_path.relative_to(ROOT)} already exists; use --force to rebuild.")

    attrition = Counter()
    master = load_jsonl(master_path)
    attribute_pool = []
    for rec in master:
        attrition["master_records"] += 1
        attrs = extract_attribute_candidates(rec, args.max_per_claim, args.context_mode)
        if not attrs:
            attrition["no_attribute_candidate"] += 1
            continue
        attrition["has_attribute_candidate"] += 1
        for idx, attr in enumerate(attrs, start=1):
            attribute_pool.append(make_attribute_record(rec, attr, idx))

    write_jsonl(pool_path, attribute_pool)
    manifest = {
        "manifest_type": "pool_freeze",
        "artifact_type": "pool_freeze",
        "stage": "construction",
        "family": "attribute",
        "source": "FEVER",
        "source_frame": str(master_path.relative_to(ROOT)),
        "version": args.version,
        "attribute_pool_size": len(attribute_pool),
        "files": {
            "attribute_pool": str(pool_path.relative_to(ROOT)),
            "attribute_pool_manifest": str(manifest_path.relative_to(ROOT)),
        },
        "filters": {
            "source_label": "SUPPORTS inherited from master frame",
            "gpt4o_in_pool_selection": False,
            "max_attribute_candidates_per_claim": args.max_per_claim,
            "context_mode": args.context_mode,
            "attribute_definition": (
                "non-entity descriptive attribute of the same subject, including "
                "nationality, occupation, genre, language, or type"
            ),
            "source_rejects": [reason for reason, _ in SOURCE_FILTERS],
        },
        "attrition": dict(attrition),
        "strata": {
            "length_bin": counts(attribute_pool, "length_bin"),
            "attribute_type": nested_counts(attribute_pool, "attribute_type"),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(json.dumps({
        "attribute_pool": str(pool_path.relative_to(ROOT)),
        "attribute_pool_size": len(attribute_pool),
        "manifest": str(manifest_path.relative_to(ROOT)),
    }, indent=2))


if __name__ == "__main__":
    main()
