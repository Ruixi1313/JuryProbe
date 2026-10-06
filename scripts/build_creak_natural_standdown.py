#!/usr/bin/env python3
"""Build the frozen 300/300 CREAK natural stand-down dataset."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SHA256 = "de61800bb7d0c07a9d5b8abdf4c1604db21151bdfcb13a284db112a531bf3455"
EXPECTED_FIELDS = {
    "ex_id",
    "sentence",
    "explanation",
    "label",
    "entity",
    "en_wiki_pageid",
    "entity_mention_loc",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def select(rows: list[dict], label: str, n: int, seed: int) -> list[dict]:
    candidates = sorted(
        (row for row in rows if row["label"] == label),
        key=lambda row: row["ex_id"],
    )
    rng = random.Random(seed)
    rng.shuffle(candidates)
    if len(candidates) < n:
        raise ValueError(f"Only {len(candidates)} {label} examples; requested {n}")
    return candidates[:n]


def transform(row: dict, index: int, corrupted: bool) -> dict:
    return {
        "id": f"creakv1_{index:04d}",
        "statement": row["sentence"],
        "gold": "false" if corrupted else "true",
        "is_corrupted": corrupted,
        "kind": "creak_natural",
        "pool_version": "v1",
        "source_dataset": "creak",
        "source_split": "dev",
        "source_claim_id": row["ex_id"],
        "source_label": row["label"],
        "source_entity": row["entity"],
        "source_wikipedia_page_id": row["en_wiki_pageid"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/raw/creak/dev.json")
    parser.add_argument("--out", default="data/creak_natural_standdown_v1_n300.jsonl")
    parser.add_argument("--manifest", default="data/creak_natural_standdown_v1_n300.manifest.json")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--per-class", type=int, default=300)
    args = parser.parse_args()

    input_path = ROOT / args.input
    observed_sha = sha256(input_path)
    if observed_sha != EXPECTED_SHA256:
        raise ValueError(
            f"Unexpected CREAK dev SHA-256: {observed_sha}; expected {EXPECTED_SHA256}"
        )
    rows = load_jsonl(input_path)
    if any(set(row) != EXPECTED_FIELDS for row in rows):
        raise ValueError("CREAK schema differs from the frozen seven-field schema")
    if any(row["label"] not in {"true", "false"} for row in rows):
        raise ValueError("Unexpected CREAK label")
    ids = [row["ex_id"] for row in rows]
    claims = [row["sentence"].strip().lower() for row in rows]
    if len(ids) != len(set(ids)) or len(claims) != len(set(claims)):
        raise ValueError("CREAK dev contains duplicate IDs or normalized claims")

    clean_source = select(rows, "true", args.per_class, args.seed)
    false_source = select(rows, "false", args.per_class, args.seed)
    built = [
        transform(row, index + 1, corrupted=False)
        for index, row in enumerate(clean_source)
    ] + [
        transform(row, args.per_class + index + 1, corrupted=True)
        for index, row in enumerate(false_source)
    ]

    out_path = ROOT / args.out
    manifest_path = ROOT / args.manifest
    write_jsonl(out_path, built)
    manifest = {
        "dataset": "CREAK natural stand-down v1",
        "protocol": "frozen/creak_natural_standdown_v1/PROTOCOL.md",
        "source": args.input,
        "source_sha256": observed_sha,
        "source_repository": "https://github.com/yasumasaonoe/creak",
        "source_commit": "5e892b28b6dad3e87769cfc01f00a6577ca44068",
        "source_counts": dict(Counter(row["label"] for row in rows)),
        "source_unique_ids": len(set(ids)),
        "source_unique_normalized_claims": len(set(claims)),
        "selection": {
            "split": "dev",
            "seed": args.seed,
            "per_class": args.per_class,
            "replacement": False,
            "content_filter": None,
            "model_assisted_selection": False,
            "explanation_in_judge_input": False,
        },
        "output": args.out,
        "output_sha256": sha256(out_path),
        "output_counts": {
            "clean": sum(not row["is_corrupted"] for row in built),
            "false": sum(row["is_corrupted"] for row in built),
        },
        "builder": "scripts/build_creak_natural_standdown.py",
        "builder_sha256": sha256(Path(__file__)),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
