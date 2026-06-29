#!/usr/bin/env python3
"""Stream FEVER train.jsonl and extract SUPPORTS claims with a corruptible number.

Breaks the generation circularity: source claims are FEVER (Wikipedia-derived,
human-annotated), not GPT-4o-generated. GPT-4o is used only as validator later.

Filter: label == SUPPORTS, claim contains exactly one usable number token
(a 4-digit year 1000-2099 -> kind 'year', or an integer with >=2 digits ->
kind 'quantity') that appears exactly once in the claim.

Output: data/fever_supports_numeric.jsonl  {statement, number, kind}
Usage: python scripts/fetch_fever.py [limit=4000]
"""
from __future__ import annotations

import json
import re
import ssl
import sys
import urllib.request
from pathlib import Path

try:
    import certifi
    SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL = ssl.create_default_context()

ROOT = Path(__file__).resolve().parents[1]
URL = "https://fever.ai/download/fever/train.jsonl"
OUT = ROOT / "data" / "fever_supports_numeric.jsonl"
NUM = re.compile(r"\d[\d,]*")


def pick_number(claim: str):
    """Return (token, kind) for a single safe corruptible number, else None."""
    year, quantity = None, None
    for t in NUM.findall(claim):
        if claim.count(t) != 1:
            continue
        raw = t.replace(",", "")
        if not raw.isdigit():
            continue
        if len(raw) == 4 and 1000 <= int(raw) <= 2099:
            year = year or (t, "year")
        elif len(raw) >= 2:
            quantity = quantity or (t, "quantity")
    return year or quantity


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    OUT.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(URL, headers={"User-Agent": "juryprobe/0.1"})
    seen, kept, n_lines = set(), 0, 0
    with urllib.request.urlopen(req, timeout=60, context=SSL) as resp, \
            OUT.open("w") as f:
        for raw_line in resp:
            n_lines += 1
            try:
                obj = json.loads(raw_line.decode("utf-8"))
            except Exception:
                continue
            if obj.get("label") != "SUPPORTS":
                continue
            claim = (obj.get("claim") or "").strip()
            if not claim or claim in seen:
                continue
            picked = pick_number(claim)
            if not picked:
                continue
            seen.add(claim)
            f.write(json.dumps({"statement": claim, "number": picked[0],
                                "kind": picked[1]}) + "\n")
            kept += 1
            if kept % 500 == 0:
                print(f"  kept {kept} (scanned {n_lines} lines)", flush=True)
            if kept >= limit:
                break
    print(f"Wrote {kept} candidate claims -> {OUT.relative_to(ROOT)} "
          f"(scanned {n_lines} lines)")


if __name__ == "__main__":
    main()
