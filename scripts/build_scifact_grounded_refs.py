#!/usr/bin/env python3
"""Attach benchmark-annotated evidence sentences to the SciFact claim subset.

References are drawn from published scientific abstracts, not constructed as
minimal edits of the claims. Some evidence sentences require abstract context;
these references support a trusted-reference diagnostic, not a safety guarantee.

This script joins each item in the SciFact natural family back to its SciFact
claim record, pulls the gold evidence sentences from the cited corpus abstract,
and writes one grounded record per item with a `reference` field. NO API calls:
it only reads the cached SciFact release. The grounded judge run is a separate
step (scripts/foil_grounded-style judge_grounded on this reference).

Reference construction (label-blind, symmetric across clean/corrupt):
  * For each evidence doc cited by the claim, take exactly the annotated evidence
    sentence indices from that doc's abstract (corpus.jsonl).
  * Concatenate the deduped evidence sentences in order -> the trusted reference.
  * Clean (SUPPORTED) claims get their SUPPORT evidence; corrupt (CONTRADICTED)
    claims get their CONTRADICT evidence. The reference is the gold annotation in
    both cases; no model participates.

Usage:
  python scripts/build_scifact_grounded_refs.py \
      --family data/scifact_natural_n190.jsonl \
      --out data/scifact_natural_n190_grounded.jsonl
"""
from __future__ import annotations

import argparse
import io
import json
import statistics as st
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCIFACT_TAR = ROOT / "data" / "raw" / "scifact_data.tar.gz"


def load_scifact_release():
    """Return (claims_by_id, abstract_by_doc_id) from the cached SciFact tar."""
    tf = tarfile.open(SCIFACT_TAR, "r:gz")
    claims = {}
    for member in ["data/claims_train.jsonl", "data/claims_dev.jsonl"]:
        for line in tf.extractfile(member).read().decode().splitlines():
            if line.strip():
                r = json.loads(line)
                claims[str(r["id"])] = r
    abstracts = {}
    for line in tf.extractfile("data/corpus.jsonl").read().decode().splitlines():
        if line.strip():
            d = json.loads(line)
            abstracts[int(d["doc_id"])] = d["abstract"]
    return claims, abstracts


def evidence_reference(claim_rec, abstracts):
    """Deduped, ordered gold evidence sentences for one claim -> reference string."""
    sents = []
    n_docs = 0
    for doc_id, groups in (claim_rec.get("evidence") or {}).items():
        abstract = abstracts.get(int(doc_id)) or []
        used_doc = False
        for group in groups:
            for idx in group.get("sentences", []):
                if 0 <= idx < len(abstract):
                    sents.append(abstract[idx].strip())
                    used_doc = True
        if used_doc:
            n_docs += 1
    seen = set()
    ordered = []
    for s in sents:
        if s and s not in seen:
            seen.add(s)
            ordered.append(s)
    return " ".join(ordered), len(ordered), n_docs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", default="data/scifact_natural_n190.jsonl")
    ap.add_argument("--out", default="data/scifact_natural_n190_grounded.jsonl")
    args = ap.parse_args()

    claims, abstracts = load_scifact_release()
    family = [json.loads(l) for l in (ROOT / args.family).read_text().splitlines() if l.strip()]

    records = []
    missing = []
    for it in family:
        cid = it["source_claim_id"].replace("scifact_", "")
        rec = claims.get(cid)
        if rec is None:
            missing.append(it["id"])
            continue
        reference, n_sent, n_docs = evidence_reference(rec, abstracts)
        if not reference:
            missing.append(it["id"])
            continue
        records.append({
            "item_id": it["id"],
            "statement": it["statement"],
            "reference": reference,
            "gold": it["gold"],
            "is_corrupted": it["is_corrupted"],
            "source_claim_id": it["source_claim_id"],
            "n_evidence_sentences": n_sent,
            "n_evidence_docs": n_docs,
            "reference_word_len": len(reference.split()),
        })

    out_path = ROOT / args.out
    with out_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    corrupt = [r for r in records if r["is_corrupted"]]
    clean = [r for r in records if not r["is_corrupted"]]
    lens = [r["reference_word_len"] for r in records]
    manifest = {
        "family": args.family,
        "output": args.out,
        "n_family_items": len(family),
        "n_with_reference": len(records),
        "n_missing_reference": len(missing),
        "missing_ids": missing,
        "n_clean": len(clean),
        "n_corrupt": len(corrupt),
        "reference_word_len": {
            "min": min(lens), "median": int(st.median(lens)), "max": max(lens),
            "mean": round(st.mean(lens), 1),
        },
        "reference_source": "SciFact gold evidence sentences from cited corpus abstracts (no model in construction)",
    }
    out_path.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
