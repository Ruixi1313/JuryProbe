#!/usr/bin/env python3
"""Summarize author-audit codes in a markdown audit file."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

VALID_CODE = "VALID"
BLANK_CODE = "BLANK"


def parse_codes(path: Path) -> list[str]:
    codes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*-\s+audit_code:\s*(.*)\s*$", line)
        if not match:
            continue
        code = match.group(1).strip()
        codes.append(code if code else BLANK_CODE)
    return codes


def gate_for_counts(counts: Counter) -> str:
    bad_counts = Counter({
        code: count
        for code, count in counts.items()
        if code not in {VALID_CODE, BLANK_CODE}
    })
    bad_total = sum(bad_counts.values())
    max_bad_type = max(bad_counts.values(), default=0)
    if counts.get(BLANK_CODE, 0):
        return "PENDING"
    if bad_total <= 5:
        return "GREEN"
    if 6 <= bad_total <= 8 and max_bad_type < 5:
        return "YELLOW"
    return "RED"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("audit_file")
    args = ap.parse_args()

    path = Path(args.audit_file)
    codes = parse_codes(path)
    counts = Counter(codes)
    bad_total = sum(
        count for code, count in counts.items()
        if code not in {VALID_CODE, BLANK_CODE}
    )
    summary = {
        "audit_file": str(path),
        "n_items": len(codes),
        "counts": dict(counts),
        "bad_total": bad_total,
        "max_bad_type_count": max(
            [
                count for code, count in counts.items()
                if code not in {VALID_CODE, BLANK_CODE}
            ],
            default=0,
        ),
        "gate": gate_for_counts(counts),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
