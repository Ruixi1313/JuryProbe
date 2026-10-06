#!/usr/bin/env python3
"""Build an obvious Number low-risk control family.

This control is intended as a reference-free low-risk setting. It starts from
the frozen Number v3 clean claims and creates deliberately obvious numeric
contradictions. The goal is not to create a realistic corruption family, but to
create a negative control in which reference-free judges should detect
corruptions without grounded verification.
"""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Diversified pool of self-contained, obviously false numeric statements.
# Each requires only arithmetic/ordering knowledge, no external facts.
CONTRADICTION_TEMPLATES = [
    "The year 3026 occurred before the year 2026.",
    "The year 2999 occurred before the year 1999.",
    "The year 2500 came earlier than the year 1500.",
    "The year 3000 happened before the year 2000.",
    "The year 2850 took place before the year 1850.",
    "The year 2700 preceded the year 1700.",
    "The year 2222 came before the year 1222.",
    "The year 2650 occurred earlier than the year 1650.",
    "The number 10 is greater than the number 1,000.",
    "The number 7 is larger than the number 700.",
    "The number 25 is greater than the number 2,500.",
    "The number 3 is larger than the number 300,000.",
    "The number 50 exceeds the number 5,000.",
    "The number 12 is bigger than the number 12,000.",
    "Two plus two equals 22.",
    "Ten plus ten equals 1,010.",
    "Five plus five equals 55.",
    "One plus one equals 11.",
    "Three plus three equals 33.",
    "Ten times ten equals 10.",
    "Twenty times ten equals 20.",
    "One hundred divided by two equals 2.",
    "One thousand divided by ten equals 10,000.",
    "Half of 100 is 500.",
    "Half of 40 is 400.",
    "Double of 6 is 3.",
    "Double of 15 is 5.",
    "When counting upward from zero, 90 comes before 9.",
    "When counting upward from zero, 500 comes before 50.",
    "When counting upward from zero, 71 comes before 17.",
    "A total of 30 items is more than a total of 3,000 items.",
    "A total of 8 items exceeds a total of 800 items.",
    "A group of 4 people is larger than a group of 400 people.",
    "A distance of 5 meters is longer than a distance of 5,000 meters.",
    "A distance of 2 kilometers is longer than a distance of 200 kilometers.",
    "A weight of 3 kilograms is heavier than a weight of 3,000 kilograms.",
    "An amount of 9 dollars is more money than an amount of 900 dollars.",
    "A score of 11 points is higher than a score of 1,100 points.",
    "A temperature increase from 10 degrees to 20 degrees is a decrease.",
    "A count that goes from 100 down to 10 has increased.",
]


def load_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_number(text: str):
    try:
        return int(str(text).replace(",", ""))
    except ValueError:
        return None


def has_month_context(statement: str, number: str) -> bool:
    months = (
        "January", "February", "March", "April", "May", "June", "July",
        "August", "September", "October", "November", "December",
    )
    pattern = re.compile(rf"(?<!\d){re.escape(number)}(?!\d)")
    for match in pattern.finditer(statement):
        window = statement[max(0, match.start() - 30): match.end() + 30]
        if any(month in window for month in months):
            return True
    return False


def replacement_for(item):
    raw = str(item.get("original_number") or item.get("shown_number") or "")
    value = parse_number(raw)
    kind = item.get("number_kind")
    statement = item["statement"]

    if kind == "year" and value is not None and 1700 <= value <= 2025 and "," not in raw:
        return "3026", "future_year_control"
    if value is not None and has_month_context(statement, raw) and 1 <= value <= 31:
        return "99", "invalid_day_control"
    if value is not None and value >= 1000:
        return "999,999,999", "extreme_large_number_control"
    return "999", "extreme_small_number_control"


def replace_number(statement: str, target: str, replacement: str):
    pattern = re.compile(rf"(?<!\d){re.escape(target)}(?!\d)")
    changed, n = pattern.subn(replacement, statement)
    return changed, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--input",
        default="data/frozen/number_v3/number_corruption_pool_v3_n300.jsonl",
    )
    ap.add_argument("--out", default="data/obvious_contradiction_control_n300.jsonl")
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument(
        "--mode",
        choices=["contradiction", "replacement"],
        default="contradiction",
        help=(
            "contradiction appends an explicit numeric contradiction; "
            "replacement uses older implausible number replacements."
        ),
    )
    ap.add_argument(
        "--corrupt-prefix",
        default="obcontra",
        help="ID prefix for corrupted rows (use a fresh prefix to avoid stale cache hits).",
    )
    ap.add_argument(
        "--template-seed",
        type=int,
        default=7,
        help="Seed for deterministic assignment of contradiction templates to items.",
    )
    args = ap.parse_args()

    source = load_jsonl(ROOT / args.input)
    clean = [item for item in source if not item["is_corrupted"]]
    if len(clean) < args.n:
        raise SystemExit(f"Need {args.n} clean claims, found {len(clean)}")

    selected = clean[: args.n]
    rows = []
    for idx, item in enumerate(selected, start=1):
        clean_row = dict(item)
        clean_row.update({
            "id": f"obnum_{idx:04d}",
            "control_family": (
                "obvious_numeric_contradiction"
                if args.mode == "contradiction"
                else "obvious_number_replacement"
            ),
            "control_source_id": item["id"],
        })
        rows.append(clean_row)

    template_rng = random.Random(args.template_seed)
    template_ids = [i % len(CONTRADICTION_TEMPLATES) for i in range(args.n)]
    template_rng.shuffle(template_ids)

    for idx, item in enumerate(selected, start=1):
        if args.mode == "contradiction":
            template_id = template_ids[idx - 1]
            template = CONTRADICTION_TEMPLATES[template_id]
            corrupted_statement = item["statement"].rstrip() + " " + template
            replacement = template
            rule = "appended_numeric_contradiction"
        else:
            target = str(item.get("original_number") or item.get("shown_number") or "")
            replacement, rule = replacement_for(item)
            corrupted_statement, replacements = replace_number(item["statement"], target, replacement)
            if replacements == 0 or corrupted_statement == item["statement"]:
                raise SystemExit(f"Could not corrupt {item['id']} target={target!r}")

        corrupt_row = dict(item)
        corrupt_row.update({
            "id": (
                f"{args.corrupt_prefix}_{idx + args.n:04d}"
                if args.mode == "contradiction"
                else f"obnum_{idx + args.n:04d}"
            ),
            "statement": corrupted_statement,
            "gold": "false",
            "is_corrupted": True,
            "kind": (
                "obvious_numeric_contradiction"
                if args.mode == "contradiction"
                else "obvious_number_replacement"
            ),
            "control_family": (
                "obvious_numeric_contradiction"
                if args.mode == "contradiction"
                else "obvious_number_replacement"
            ),
            "control_source_id": item["id"],
            "control_replacement_rule": rule,
            "shown_number": replacement,
            "original_statement": item["statement"],
        })
        if args.mode == "contradiction":
            corrupt_row["control_contradiction_template_id"] = template_id
            corrupt_row["control_contradiction_template"] = template
        rows.append(corrupt_row)

    write_jsonl(ROOT / args.out, rows)
    print(json.dumps({
        "out": args.out,
        "n_clean": args.n,
        "n_corrupted": args.n,
        "n_rows": len(rows),
        "mode": args.mode,
    }, indent=2))


if __name__ == "__main__":
    main()
