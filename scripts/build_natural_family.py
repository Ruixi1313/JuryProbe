#!/usr/bin/env python3
"""Build true/false claim families from non-FEVER fact-verification benchmarks.

Use the identical label-blind pipeline as build_fever_refutes_control.py so the new
families plug straight into evaluate_low_risk_control_rf.py and
evaluate_cross_family_transfer.py.

Supported sources (different domains / provenance from FEVER's Wikipedia):
  * scifact : allenai SciFact. clean = SUPPORTED scientific claims,
              corrupt = CONTRADICTED scientific claims (biomedical domain).
  * liar    : LIAR (PolitiFact). clean = true/mostly-true statements,
              corrupt = false/pants-fire statements (political domain).
              NOTE: LIAR labels are journalistic verdicts on often context-laden
              political claims, not self-contained verifiable facts; treat this
              family as a noisy robustness probe, not a clean factuality test.

Design rules (pre-specified, label-blind, symmetric; same as FEVER-Refutes):
  1. Identical local_atomic_candidate filter on both sides (6-35 words, no ?/;,
     <=1 period, no hedge terms).
  2. Global dedupe by exact claim text across both labels.
  3. Corrupt (false) side sampled first (fixed seed); clean side sampled to match
     the corrupt length-bin distribution exactly.
  4. No model participates in item selection.

Usage:
  python scripts/build_natural_family.py --source scifact --n-per-side 200 --seed 42
  python scripts/build_natural_family.py --source liar    --n-per-side 300 --seed 42
"""
from __future__ import annotations

import argparse
import io
import json
import random
import re
import ssl
import tarfile
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

try:
    import certifi
    SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL = ssl.create_default_context()

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

HEDGE_RE = re.compile(
    r"\b(about|approximately|approx\.?|around|roughly|nearly|almost|"
    r"over|under|more than|less than|at least|at most|up to|between|from)\b",
    re.IGNORECASE,
)

SCIFACT_TAR = "https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz"
LIAR_BASE = "https://raw.githubusercontent.com/thiagorainmaker77/liar_dataset/master/"


def length_bin(n_words: int) -> str:
    if n_words <= 10:
        return "short"
    if n_words <= 18:
        return "medium"
    return "long"


def local_atomic_candidate(claim: str) -> bool:
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


def _fetch(url: str, cache_name: str) -> bytes:
    RAW.mkdir(parents=True, exist_ok=True)
    cache = RAW / cache_name
    if cache.exists():
        return cache.read_bytes()
    req = urllib.request.Request(url, headers={"User-Agent": "juryprobe/0.1"})
    data = urllib.request.urlopen(req, timeout=180, context=SSL).read()
    cache.write_bytes(data)
    return data


# ---------------- source adapters: return {"true": [...], "false": [...]} ------
# each record dict: {"src_id": str, "claim": str}

def load_scifact():
    raw = _fetch(SCIFACT_TAR, "scifact_data.tar.gz")
    tf = tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz")
    by_label = {"true": [], "false": []}
    for member in ["data/claims_train.jsonl", "data/claims_dev.jsonl"]:
        rows = [json.loads(l) for l in tf.extractfile(member).read().decode().splitlines() if l.strip()]
        for r in rows:
            ev = r.get("evidence") or {}
            labs = {a.get("label") for anns in ev.values() for a in anns}
            claim = (r.get("claim") or "").strip()
            if not ev:
                continue  # NEI
            if "SUPPORT" in labs and "CONTRADICT" not in labs:
                by_label["true"].append({"src_id": str(r.get("id")), "claim": claim})
            elif "CONTRADICT" in labs and "SUPPORT" not in labs:
                by_label["false"].append({"src_id": str(r.get("id")), "claim": claim})
    return by_label


def load_liar():
    by_label = {"true": [], "false": []}
    keep = {"true": "true", "mostly-true": "true", "false": "false", "pants-fire": "false"}
    for split in ["train.tsv", "valid.tsv", "test.tsv"]:
        txt = _fetch(LIAR_BASE + split, f"liar_{split}").decode("utf-8", errors="replace")
        for line in txt.splitlines():
            cols = line.split("\t")
            if len(cols) < 3:
                continue
            label = cols[1].strip().lower()
            if label not in keep:
                continue
            claim = cols[2].strip()
            by_label[keep[label]].append({"src_id": cols[0].strip(), "claim": claim})
    return by_label


SOURCES = {
    "scifact": (load_scifact, "scifact", "biomedical"),
    "liar": (load_liar, "liar", "political"),
}


def filter_and_dedupe(by_label):
    attrition = Counter()
    seen = set()
    out = {"true": [], "false": []}
    # iterate false first so corrupt side keeps priority on dedupe collisions
    for label in ["false", "true"]:
        for rec in by_label[label]:
            claim = rec["claim"].strip()
            attrition[f"raw_{label}"] += 1
            if not claim:
                attrition["empty"] += 1
                continue
            if claim in seen:
                attrition["duplicate"] += 1
                continue
            seen.add(claim)
            if not local_atomic_candidate(claim):
                attrition[f"atomic_reject_{label}"] += 1
                continue
            attrition[f"atomic_pass_{label}"] += 1
            out[label].append(rec)
    return out, attrition


def sample_matched(pool, n_per_side, seed):
    rng = random.Random(seed)
    false_pool = list(pool["false"])
    rng.shuffle(false_pool)
    corrupt = false_pool[:n_per_side]
    if len(corrupt) < n_per_side:
        raise SystemExit(f"Only {len(corrupt)} false candidates after filters; need {n_per_side}.")
    target = Counter(length_bin(len(r["claim"].split())) for r in corrupt)
    true_by_bin = defaultdict(list)
    for r in pool["true"]:
        true_by_bin[length_bin(len(r["claim"].split()))].append(r)
    clean = []
    for b, k in sorted(target.items()):
        avail = true_by_bin[b]
        if len(avail) < k:
            raise SystemExit(f"true pool has {len(avail)} '{b}' claims; need {k}.")
        rng.shuffle(avail)
        clean.extend(avail[:k])
    rng.shuffle(clean)
    return clean, corrupt


def make_item(rec, idx, is_corrupted, source, prefix):
    claim = rec["claim"]
    return {
        "statement": claim,
        "gold": "false" if is_corrupted else "true",
        "is_corrupted": is_corrupted,
        "kind": f"{source}_natural",
        "pool_version": "v1",
        "source_dataset": source,
        "source_claim_id": f"{source}_{rec['src_id']}",
        "source_label": "false" if is_corrupted else "true",
        "original_statement": claim,
        "length_bin": length_bin(len(claim.split())),
        "id": f"{prefix}_{idx:04d}",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, choices=sorted(SOURCES))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n-per-side", type=int, default=200)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    loader, source, domain = SOURCES[args.source]
    by_label = loader()
    pool, attrition = filter_and_dedupe(by_label)
    clean, corrupt = sample_matched(pool, args.n_per_side, args.seed)

    prefix = {"scifact": "scifact", "liar": "liar"}[source]
    items = []
    for i, rec in enumerate(clean):
        items.append(make_item(rec, i + 1, False, source, prefix))
    for j, rec in enumerate(corrupt):
        items.append(make_item(rec, args.n_per_side + j + 1, True, source, prefix))

    out = ROOT / (args.out or f"data/{source}_natural_n{args.n_per_side}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    manifest = {
        "dataset": f"{source}_natural",
        "domain": domain,
        "version": "v1",
        "seed": args.seed,
        "n_clean": len(clean),
        "n_corrupted": len(corrupt),
        "design": {
            "clean_source": f"{source} true/supported claims (natural)",
            "corrupted_source": f"{source} false/contradicted claims (natural, no synthetic corruption)",
            "filters": "identical label-blind local_atomic filter on both sides; global dedupe",
            "matching": "true side sampled to match false length-bin distribution",
            "model_in_selection": False,
        },
        "length_bins_corrupt": dict(Counter(i["length_bin"] for i in items if i["is_corrupted"])),
        "attrition": dict(attrition),
        "output": str(out.relative_to(ROOT)),
    }
    out.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
