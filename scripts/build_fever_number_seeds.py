#!/usr/bin/env python3
"""FEVER number-seed builder.

Extracts clean FEVER SUPPORTS claims that are SUITABLE for number corruption.
This script does NOT corrupt anything and does NOT call any judge/validator -- it
only produces a candidate pool. Gold reliability is enforced downstream by the
GPT-4o validator gate in build_number_corruption.py.

Strict rules (conservative first pass):
  - label == SUPPORTS
  - claim has EXACTLY ONE number token
  - no hedge words (about/approximately/around/.../up to/between/from)
  - the number is not a range and not a version/episode/model-style id
  - numeric value >= 10 (drop tiny ordinal/title noise)
  - claim has >= 6 words

Source note: the upstream snippet used `datasets.load_dataset("fever", ...)`.
This venv has no `datasets`, and the direct FEVER train.jsonl
(https://fever.ai/download/fever/train.jsonl) streams fine, so we read that
directly. All extraction RULES are preserved; only the loader differs.

Usage:
  python scripts/build_fever_number_seeds.py --limit 1200 \
      --out data/fever_number_seeds.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import urllib.request
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
BAD_CONTEXT_RE = re.compile(
    r"\b(version|episode|season|chapter|volume|model|iphone|playstation|"
    r"windows|macos|html|usb|http|gdp|isbn)\b",
    re.IGNORECASE,
)


def normalize_num(text: str) -> float:
    return float(text.replace(",", ""))


def classify_number(text: str) -> str:
    raw = text.replace(",", "")
    if raw.isdigit():
        n = int(raw)
        if 1000 <= n <= 2099 and len(raw) == 4:
            return "year"
        return "integer"
    return "decimal"


def is_bad_numeric_context(claim: str, start: int, end: int) -> bool:
    window = claim[max(0, start - 40): min(len(claim), end + 40)]
    if HEDGE_RE.search(claim):
        return True
    if BAD_CONTEXT_RE.search(window):
        return True
    near = claim[max(0, start - 5): min(len(claim), end + 5)]
    if any(sym in near for sym in ["\u2013", "\u2014", " - ", " to "]):
        return True
    return False


def extract_unique_number(claim: str):
    matches = list(NUM_RE.finditer(claim))
    if len(matches) != 1:
        return None
    m = matches[0]
    num_text = m.group(1)
    try:
        value = normalize_num(num_text)
    except Exception:
        return None
    if value < 10:
        return None
    if is_bad_numeric_context(claim, m.start(1), m.end(1)):
        return None
    return {"text": num_text, "value": value, "kind": classify_number(num_text),
            "start": m.start(1), "end": m.end(1)}


def evidence_stub(row: dict):
    """Compact evidence pointers from FEVER train.jsonl nested evidence lists."""
    out = []
    for group in (row.get("evidence") or []):
        for item in group:
            # item ~ [annotation_id, evidence_id, wiki_url, sentence_id]
            if isinstance(item, list) and len(item) >= 4 and item[2] is not None:
                out.append({"wiki_url": item[2], "sentence_id": item[3]})
    # dedup, cap
    uniq = [dict(t) for t in {tuple(sorted(d.items())) for d in out}]
    return uniq[:4]


def stream_fever():
    req = urllib.request.Request(FEVER_URL, headers={"User-Agent": "juryprobe/0.1"})
    with urllib.request.urlopen(req, timeout=60, context=SSL) as resp:
        for raw in resp:
            try:
                yield json.loads(raw.decode("utf-8"))
            except Exception:
                continue


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=1200)
    ap.add_argument("--out", default="data/fever_number_seeds.jsonl")
    args = ap.parse_args()

    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    seen_ids, seen_claims, kept, scanned = set(), set(), 0, 0

    with out_path.open("w", encoding="utf-8") as f:
        for row in stream_fever():
            scanned += 1
            if str(row.get("label", "")).upper() != "SUPPORTS":
                continue
            fid = row.get("id")
            if fid in seen_ids:
                continue
            seen_ids.add(fid)
            claim = (row.get("claim") or "").strip()
            if not claim or len(claim.split()) < 6 or claim in seen_claims:
                continue
            num = extract_unique_number(claim)
            if num is None:
                continue
            seen_claims.add(claim)
            f.write(json.dumps({
                "source": "FEVER", "fever_id": fid, "label": "SUPPORTS",
                "claim": claim, "number": num,
                "evidence_stub": evidence_stub(row),
            }, ensure_ascii=False) + "\n")
            kept += 1
            if kept % 200 == 0:
                print(f"  kept {kept} (scanned {scanned})", flush=True)
            if kept >= args.limit:
                break

    print(json.dumps({"out": str(out_path.relative_to(ROOT)), "kept": kept,
                      "scanned": scanned, "seen_ids": len(seen_ids)}, indent=2))


if __name__ == "__main__":
    main()
