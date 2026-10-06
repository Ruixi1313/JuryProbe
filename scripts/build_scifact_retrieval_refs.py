#!/usr/bin/env python3
"""Non-oracle retrieval references for the SciFact grounded stress test.

This script builds a fixed, unsupervised, claim-only BM25
retriever over the SciFact corpus and materialises one `reference` per item per
condition, so the SAME frozen grounded judges (scripts/run_scifact_retrieval_grounded.py)
can be run unchanged across all conditions.

Conditions (all built here; oracle_sentence reuses the existing grounded cache):
  * oracle_sentence : the gold evidence sentence(s)            (recall = 1 by def)
  * oracle_abstract : the full abstract(s) containing the gold  (recall = 1 by def)
  * bm25_1          : top-1 BM25 sentence (claim-only query)
  * bm25_3          : top-3 BM25 sentences concatenated in rank order

Pre-registration (label-blind, symmetric, no result-driven choices):
  * Retriever: Okapi BM25 (k1=1.5, b=0.75), lowercased \\w+ tokens, NO stopword
    removal, over the flat pool of corpus-provided abstract sentences (SciFact's
    own sentence segmentation -- no custom splitter).
  * Query = claim text ONLY. No label, gold-doc-id, or evidence annotation is
    used for retrieval. Annotations are used SOLELY to score post-hoc recall.
  * k in {1, 3}, both fixed in advance and both reported.
  * Retrieved@3 concatenates top-3 sentences in BM25 rank order.
  * Identical pipeline on clean/corrupt sides.

NO API calls. Output: data/scifact_retrieval_refs.jsonl (one record per item, all
conditions) + a manifest with retrieval-quality stats.

Usage:
  python3 scripts/build_scifact_retrieval_refs.py
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics as st
import tarfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCIFACT_TAR = ROOT / "data" / "raw" / "scifact_data.tar.gz"

BM25_K1 = 1.5
BM25_B = 0.75
TOKEN_RE = re.compile(r"\w+")


def tokenize(text: str):
    return TOKEN_RE.findall(text.lower())


def load_scifact_release():
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


class BM25:
    """Minimal deterministic Okapi BM25 over a flat sentence pool."""

    def __init__(self, docs_tokens):
        self.N = len(docs_tokens)
        self.doc_len = [len(t) for t in docs_tokens]
        self.avgdl = sum(self.doc_len) / self.N if self.N else 0.0
        self.tf = []  # per-doc term->count
        df = defaultdict(int)
        self.postings = defaultdict(list)  # term -> [doc_idx,...]
        for i, toks in enumerate(docs_tokens):
            counts = defaultdict(int)
            for w in toks:
                counts[w] += 1
            self.tf.append(counts)
            for w in counts:
                df[w] += 1
                self.postings[w].append(i)
        self.idf = {
            w: math.log((self.N - n + 0.5) / (n + 0.5) + 1.0) for w, n in df.items()
        }

    def top_k(self, query, k):
        q = tokenize(query)
        scores = defaultdict(float)
        for w in q:
            if w not in self.idf:
                continue
            idf = self.idf[w]
            for i in self.postings[w]:
                f = self.tf[i][w]
                denom = f + BM25_K1 * (1 - BM25_B + BM25_B * self.doc_len[i] / self.avgdl)
                scores[i] += idf * (f * (BM25_K1 + 1)) / denom
        # deterministic: higher score first, ties broken by lower pool index
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        return [i for i, _ in ranked[:k]]


def gold_evidence_set(claim_rec):
    """All annotated (doc_id, sent_idx) evidence pairs for one claim (flattened)."""
    pairs = set()
    for doc_id, groups in (claim_rec.get("evidence") or {}).items():
        for group in groups:
            for idx in group.get("sentences", []):
                pairs.add((int(doc_id), int(idx)))
    return pairs


def rationale_groups(claim_rec):
    """One frozenset of (doc_id, sent_idx) per annotated rationale group.

    SciFact rationales can span multiple sentences; a group is 'complete' only if
    ALL of its sentences are retrieved. Used to separate any-evidence recall from
    complete-rationale recall.
    """
    groups = []
    for doc_id, gs in (claim_rec.get("evidence") or {}).items():
        for group in gs:
            pairs = frozenset((int(doc_id), int(idx)) for idx in group.get("sentences", []))
            if pairs:
                groups.append(pairs)
    return groups


def oracle_sentence_ref(claim_rec, abstracts):
    sents, seen = [], set()
    for doc_id, groups in (claim_rec.get("evidence") or {}).items():
        abs = abstracts.get(int(doc_id)) or []
        for group in groups:
            for idx in group.get("sentences", []):
                if 0 <= idx < len(abs):
                    s = abs[idx].strip()
                    if s and s not in seen:
                        seen.add(s)
                        sents.append(s)
    return " ".join(sents)


def oracle_abstract_ref(claim_rec, abstracts):
    docs, seen = [], set()
    for doc_id in (claim_rec.get("evidence") or {}):
        if doc_id in seen:
            continue
        seen.add(doc_id)
        abs_ = abstracts.get(int(doc_id)) or []
        joined = " ".join(s.strip() for s in abs_ if s.strip())
        if joined:
            docs.append(joined)
    return " ".join(docs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", default="data/scifact_natural_n190.jsonl")
    ap.add_argument("--out", default="data/scifact_retrieval_refs.jsonl")
    args = ap.parse_args()

    claims, abstracts = load_scifact_release()

    # Flat sentence pool with provenance (label-blind: entire corpus, no filtering)
    pool_tokens, prov, texts = [], [], []
    for doc_id in sorted(abstracts):
        for sidx, sent in enumerate(abstracts[doc_id]):
            s = sent.strip()
            if not s:
                continue
            prov.append((doc_id, sidx))
            texts.append(s)
            pool_tokens.append(tokenize(s))
    print(f"Sentence pool: {len(pool_tokens)} sentences from {len(abstracts)} abstracts")
    bm25 = BM25(pool_tokens)

    family = [json.loads(l) for l in (ROOT / args.family).read_text().splitlines() if l.strip()]

    records = []
    agg = {k: 0 for k in ("any1", "any3", "cmp1", "cmp3",
                          "any1_c", "any3_c", "cmp1_c", "cmp3_c")}
    n_corrupt = 0
    missing = []
    for it in family:
        cid = it["source_claim_id"].replace("scifact_", "")
        rec = claims.get(cid)
        if rec is None:
            missing.append(it["id"])
            continue
        gold = gold_evidence_set(rec)
        groups = rationale_groups(rec)

        top3 = bm25.top_k(it["statement"], 3)
        top3_prov = [prov[i] for i in top3]
        top3_text = [texts[i] for i in top3]

        def any_hit(k):
            return any(p in gold for p in top3_prov[:k])

        def complete_hit(k):
            got = set(top3_prov[:k])
            return any(g <= got for g in groups)

        any1, any3 = any_hit(1), any_hit(3)
        cmp1, cmp3 = complete_hit(1), complete_hit(3)

        refs = {
            "oracle_sentence": {
                "reference": oracle_sentence_ref(rec, abstracts),
                "recall": 1.0, "hit": True,
            },
            "oracle_abstract": {
                "reference": oracle_abstract_ref(rec, abstracts),
                "recall": 1.0, "hit": True,
            },
            "bm25_1": {
                "reference": " ".join(top3_text[:1]),
                "retrieved": [list(p) for p in top3_prov[:1]],
                # 'hit'/'recall' = any-evidence@1 (primary stratifier)
                "hit": any1, "recall": 1.0 if any1 else 0.0,
                "hit_any": any1, "hit_complete": cmp1,
            },
            "bm25_3": {
                "reference": " ".join(top3_text[:3]),
                "retrieved": [list(p) for p in top3_prov[:3]],
                "hit": any3, "recall": 1.0 if any3 else 0.0,
                "hit_any": any3, "hit_complete": cmp3,
            },
        }
        for c in refs:
            refs[c]["n_tokens"] = len(refs[c]["reference"].split())

        records.append({
            "item_id": it["id"],
            "statement": it["statement"],
            "gold": it["gold"],
            "is_corrupted": it["is_corrupted"],
            "source_claim_id": it["source_claim_id"],
            "gold_evidence": [list(p) for p in sorted(gold)],
            "rationale_groups": [sorted(list(g)) for g in groups],
            "refs": refs,
        })

        agg["any1"] += any1; agg["any3"] += any3
        agg["cmp1"] += cmp1; agg["cmp3"] += cmp3
        if it["is_corrupted"]:
            n_corrupt += 1
            agg["any1_c"] += any1; agg["any3_c"] += any3
            agg["cmp1_c"] += cmp1; agg["cmp3_c"] += cmp3

    out_path = ROOT / args.out
    with out_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n = len(records)
    n_clean = n - n_corrupt

    def tok_stats(cond):
        vals = [r["refs"][cond]["n_tokens"] for r in records]
        return {"min": min(vals), "median": int(st.median(vals)),
                "max": max(vals), "mean": round(st.mean(vals), 1)}

    manifest = {
        "family": args.family,
        "output": args.out,
        "n_items": n, "n_clean": n_clean, "n_corrupt": n_corrupt,
        "n_missing": len(missing), "missing_ids": missing,
        "retriever": {
            "type": "Okapi BM25",
            "implementation": "custom pure-Python (no external library); IDF="
                              "ln((N-n+0.5)/(n+0.5)+1); no stemming/stopwords",
            "k1": BM25_K1, "b": BM25_B,
            "tokenizer": "lowercased regex \\w+ (drops punctuation); no stopword "
                         "removal; no stemming",
            "tie_breaking": "deterministic: higher score first, ties broken by "
                            "lower sentence-pool index",
            "pool": "corpus-provided abstract sentences (SciFact-native segmentation)",
            "query": "claim text only; no label/gold-doc-id/annotation used for retrieval",
            "pool_size_sentences": len(pool_tokens),
        },
        "evidence_matching": "gold hit = retrieved (doc_id, sentence_idx) matches an "
                             "annotated evidence pair EXACTLY (both use SciFact-native "
                             "segmentation, so no string-normalization ambiguity)",
        "retrieval_quality": {
            "any_evidence_recall_at_1_all": round(agg["any1"] / n, 3),
            "any_evidence_recall_at_3_all": round(agg["any3"] / n, 3),
            "any_evidence_recall_at_1_corrupt": round(agg["any1_c"] / n_corrupt, 3),
            "any_evidence_recall_at_3_corrupt": round(agg["any3_c"] / n_corrupt, 3),
            "complete_rationale_recall_at_1_all": round(agg["cmp1"] / n, 3),
            "complete_rationale_recall_at_3_all": round(agg["cmp3"] / n, 3),
            "complete_rationale_recall_at_1_corrupt": round(agg["cmp1_c"] / n_corrupt, 3),
            "complete_rationale_recall_at_3_corrupt": round(agg["cmp3_c"] / n_corrupt, 3),
        },
        "reference_tokens": {c: tok_stats(c) for c in
                             ["oracle_sentence", "oracle_abstract", "bm25_1", "bm25_3"]},
        "note": ("Annotations used SOLELY for post-hoc recall scoring, never for "
                 "retrieval. k in {1,3} fixed in advance; both reported."),
    }
    out_path.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
