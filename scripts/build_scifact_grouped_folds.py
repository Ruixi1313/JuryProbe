#!/usr/bin/env python3
"""Build deterministic evidence-document-grouped SciFact cross-fit folds."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, a: int, b: int) -> None:
        a, b = self.find(a), self.find(b)
        if a != b:
            self.parent[b] = a


def stable_tie(seed: int, item_ids: list[str]) -> str:
    payload = f"{seed}|{'|'.join(sorted(item_ids))}".encode()
    return hashlib.sha256(payload).hexdigest()


def build_groups(rows: list[dict]) -> list[dict]:
    uf = UnionFind(len(rows))
    first_by_doc: dict[int, int] = {}
    docs_by_item: list[set[int]] = []
    for i, row in enumerate(rows):
        docs = {int(doc_id) for doc_id, _sent_idx in row["gold_evidence"]}
        if not docs:
            raise ValueError(f"{row['item_id']} has no evidence document")
        docs_by_item.append(docs)
        for doc_id in docs:
            if doc_id in first_by_doc:
                uf.union(i, first_by_doc[doc_id])
            else:
                first_by_doc[doc_id] = i

    members: dict[int, list[int]] = defaultdict(list)
    for i in range(len(rows)):
        members[uf.find(i)].append(i)

    groups = []
    for indices in members.values():
        item_ids = sorted(rows[i]["item_id"] for i in indices)
        groups.append({
            "item_ids": item_ids,
            "evidence_doc_ids": sorted({d for i in indices for d in docs_by_item[i]}),
            "n_clean": sum(not rows[i]["is_corrupted"] for i in indices),
            "n_false": sum(rows[i]["is_corrupted"] for i in indices),
        })
    return groups


def assign_folds(groups: list[dict], seed: int, n_folds: int,
                 target_clean: int, target_false: int) -> list[list[dict]]:
    ordered = sorted(
        groups,
        key=lambda g: (
            -max(g["n_clean"], g["n_false"]),
            -(g["n_clean"] + g["n_false"]),
            stable_tie(seed, g["item_ids"]),
        ),
    )
    folds: list[list[dict]] = [[] for _ in range(n_folds)]
    counts = [[0, 0] for _ in range(n_folds)]

    for group in ordered:
        def objective(k: int) -> tuple[int, int, int]:
            proposed = [c[:] for c in counts]
            proposed[k][0] += group["n_clean"]
            proposed[k][1] += group["n_false"]
            squared_error = sum(
                (clean - target_clean) ** 2 + (false - target_false) ** 2
                for clean, false in proposed
            )
            return squared_error, max(sum(c) for c in proposed), k

        fold_idx = min(range(n_folds), key=objective)
        folds[fold_idx].append(group)
        counts[fold_idx][0] += group["n_clean"]
        counts[fold_idx][1] += group["n_false"]

    expected = [[target_clean, target_false] for _ in range(n_folds)]
    if counts != expected:
        raise RuntimeError(f"group assignment is not exactly balanced: {counts}")
    return folds


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--claims", default="data/scifact_natural_n190.jsonl")
    ap.add_argument("--references", default="data/scifact_retrieval_refs.jsonl")
    ap.add_argument("--seed", type=int, default=20260722)
    ap.add_argument("--out", default="frozen/scifact_second_panel_crossfit_v1/folds.json")
    args = ap.parse_args()

    claims_path = ROOT / args.claims
    refs_path = ROOT / args.references
    claims = [json.loads(line) for line in claims_path.read_text().splitlines() if line.strip()]
    refs = [json.loads(line) for line in refs_path.read_text().splitlines() if line.strip()]
    claim_by_id = {row["id"]: row for row in claims}
    if len(claim_by_id) != 380 or set(claim_by_id) != {row["item_id"] for row in refs}:
        raise ValueError("expected the same 380 unique items in claims and references")
    if sum(not row["is_corrupted"] for row in claims) != 190:
        raise ValueError("expected 190 clean claims")
    if sum(row["is_corrupted"] for row in claims) != 190:
        raise ValueError("expected 190 false claims")

    groups = build_groups(refs)
    folds = assign_folds(groups, args.seed, 5, 38, 38)
    item_to_fold: dict[str, int] = {}
    group_rows = []
    fold_rows = []
    for fold_idx, fold_groups in enumerate(folds, start=1):
        deployment_ids = sorted(i for g in fold_groups for i in g["item_ids"])
        calibration_ids = sorted(set(claim_by_id) - set(deployment_ids))
        docs = sorted({d for g in fold_groups for d in g["evidence_doc_ids"]})
        for item_id in deployment_ids:
            if item_id in item_to_fold:
                raise AssertionError(f"duplicate deployment item: {item_id}")
            item_to_fold[item_id] = fold_idx
        fold_rows.append({
            "fold": fold_idx,
            "n_deployment": len(deployment_ids),
            "n_deployment_clean": sum(not claim_by_id[i]["is_corrupted"] for i in deployment_ids),
            "n_deployment_false": sum(claim_by_id[i]["is_corrupted"] for i in deployment_ids),
            "n_calibration": len(calibration_ids),
            "n_calibration_clean": sum(not claim_by_id[i]["is_corrupted"] for i in calibration_ids),
            "n_calibration_false": sum(claim_by_id[i]["is_corrupted"] for i in calibration_ids),
            "deployment_item_ids": deployment_ids,
            "calibration_item_ids": calibration_ids,
            "deployment_evidence_doc_ids": docs,
        })
        for group in fold_groups:
            group_rows.append({"fold": fold_idx, **group})

    if set(item_to_fold) != set(claim_by_id):
        raise AssertionError("not every claim appears in exactly one deployment fold")
    for fold in fold_rows:
        deployment_docs = set(fold["deployment_evidence_doc_ids"])
        calibration_docs = {
            d for g in group_rows if g["fold"] != fold["fold"]
            for d in g["evidence_doc_ids"]
        }
        if deployment_docs & calibration_docs:
            raise AssertionError(f"evidence-document leakage in fold {fold['fold']}")

    output = {
        "version": "scifact_second_panel_crossfit_v1",
        "seed": args.seed,
        "algorithm": (
            "connected components over shared gold-evidence document IDs; deterministic "
            "greedy assignment minimizing total squared clean/false fold imbalance"
        ),
        "claims": args.claims,
        "claims_sha256": sha256(claims_path),
        "references": args.references,
        "references_sha256": sha256(refs_path),
        "n_items": len(claims),
        "n_groups": len(groups),
        "n_folds": 5,
        "folds": fold_rows,
        "groups": sorted(group_rows, key=lambda g: (g["fold"], g["item_ids"])),
        "item_to_fold": item_to_fold,
    }
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({
        "output": args.out,
        "sha256": sha256(out),
        "n_groups": len(groups),
        "fold_counts": [
            [f["n_deployment_clean"], f["n_deployment_false"]] for f in fold_rows
        ],
    }, indent=2))


if __name__ == "__main__":
    main()

