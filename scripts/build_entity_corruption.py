#!/usr/bin/env python3
"""Build the ENTITY-SWAP corruption dataset (generalization beyond numbers).

Source = FEVER SUPPORTS claims with a named entity. Corruption = GPT-4o swaps
exactly ONE named entity for a plausible, same-type but INCORRECT entity so the
claim becomes false. GPT-4o hard-gate validator (recomputed in code):
  clean   passes iff original_supported AND original_is_atomic_fact AND fluent.
  corrupt passes iff original_supported AND original_is_atomic_fact AND
          corrupted_is_false AND single_change_only AND fluent.

Output: data/entity_corruption_n{n}.jsonl  (same schema as number dataset, with
original_statement for the grounded-foil test).

Usage:
  python scripts/build_entity_corruption.py [n_corrupt=150] [n_clean=150]
  python scripts/build_entity_corruption.py 300 300 data/entity_corruption_n150.jsonl
"""
from __future__ import annotations

import json
import os
import re
import ssl
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ENV_FILE = ROOT / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, vv = line.split("=", 1)
            os.environ.setdefault(k.strip(), vv.strip())

from src.judges import _call_openrouter

try:
    import certifi
    SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL = ssl.create_default_context()

GPT4O = "openai/gpt-4o"
FEVER_URL = "https://fever.ai/download/fever/train.jsonl"
MAX_OPS = 1600
CAP_RE = re.compile(r"\b([A-Z][a-z]{2,})\b")

SWAP_PROMPT = """Here is a TRUE factual claim. Replace EXACTLY ONE named entity
(person, place, organization, work, team, etc.) with a DIFFERENT, plausible
entity OF THE SAME TYPE so that the claim becomes FALSE. Change NOTHING else
(no other words, no numbers). Return ONLY JSON:
{{"corrupted": "<claim with one entity swapped>", "original_entity": "<x>", "new_entity": "<y>"}}

Claim: {claim}"""

VAL_CORRUPT = """You are the CORRUPTION VALIDATOR. Given an ORIGINAL true claim and
a MODIFIED version with one entity swapped, return ONLY JSON with EXACTLY:
{{"original_supported": true/false, "original_is_atomic_fact": true/false,
  "corrupted_is_false": true/false, "single_change_only": true/false,
  "fluent_no_artifact": true/false}}
- original_supported: is the ORIGINAL factually TRUE?
- original_is_atomic_fact: a single precise verifiable claim?
- corrupted_is_false: is the MODIFIED now factually FALSE (the new entity is wrong)?
- single_change_only: was exactly ONE entity changed, nothing else?
- fluent_no_artifact: modified reads naturally, no tampering seam?

ORIGINAL: {original}
MODIFIED: {modified}"""

VAL_CLEAN = """You are the CORRUPTION VALIDATOR. Given ONE claim, return ONLY JSON:
{{"original_supported": true/false, "original_is_atomic_fact": true/false,
  "fluent_no_artifact": true/false}}
- original_supported: is it factually TRUE?
- original_is_atomic_fact: a single precise verifiable claim?
- fluent_no_artifact: fluent, no artifact.

CLAIM: {claim}"""


def _strip(t):
    t = t.strip()
    t = re.sub(r"^```(?:json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    m = re.search(r"(\{.*\})", t, re.DOTALL)
    return m.group(1) if m else t


def _json(prompt, mt=300, temp=0.0):
    try:
        r = _call_openrouter(GPT4O, prompt, max_tokens=mt, temperature=temp)
        return json.loads(_strip(r["choices"][0]["message"]["content"]))
    except Exception:
        return {}


def stream_fever():
    req = urllib.request.Request(FEVER_URL, headers={"User-Agent": "juryprobe/0.1"})
    with urllib.request.urlopen(req, timeout=60, context=SSL) as resp:
        for raw in resp:
            try:
                yield json.loads(raw.decode("utf-8"))
            except Exception:
                continue


def has_interior_entity(claim):
    words = claim.split()
    if len(words) < 6:
        return False
    # a capitalized proper-noun token that is NOT the first word
    return any(CAP_RE.fullmatch(w.strip(".,;:'\"")) for w in words[1:])


def gate_clean(v):
    return bool(v) and v.get("original_supported") is True and \
        v.get("original_is_atomic_fact") is True and v.get("fluent_no_artifact") is True


def gate_corrupt(v):
    return bool(v) and all(v.get(k) is True for k in (
        "original_supported", "original_is_atomic_fact", "corrupted_is_false",
        "single_change_only", "fluent_no_artifact"))


def main():
    n_corrupt = int(sys.argv[1]) if len(sys.argv) > 1 else 150
    n_clean = int(sys.argv[2]) if len(sys.argv) > 2 else 150
    seed = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    if seed and not seed.is_absolute():
        seed = ROOT / seed
    out = ROOT / "data" / f"entity_corruption_n{n_corrupt}.jsonl"
    if out.exists():
        print(f"{out.relative_to(ROOT)} exists; delete to rebuild.")
        return

    seed_items = []
    if seed:
        seed_items = [json.loads(line) for line in seed.read_text().splitlines() if line.strip()]
    clean = [it for it in seed_items if not it.get("is_corrupted")]
    corrupted = [it for it in seed_items if it.get("is_corrupted")]
    if len(clean) > n_clean or len(corrupted) > n_corrupt:
        raise ValueError("Seed already exceeds requested clean/corrupted target")

    ops, seen = 0, set()
    new_items = []
    for it in seed_items:
        seen.add((it.get("original_statement") or it.get("statement") or "").strip())
        seen.add((it.get("statement") or "").strip())

    print(f"Target: {n_corrupt} corrupted + {n_clean} clean (entity swap, FEVER)")
    if seed_items:
        print(f"Seed: {seed.relative_to(ROOT)} with {len(clean)} clean + "
              f"{len(corrupted)} corrupted; extending only the remainder.")
    for row in stream_fever():
        if len(clean) >= n_clean and len(corrupted) >= n_corrupt:
            break
        if ops >= MAX_OPS:
            print("  hit MAX_OPS cap."); break
        if str(row.get("label", "")).upper() != "SUPPORTS":
            continue
        claim = (row.get("claim") or "").strip()
        if not claim or claim in seen or not has_interior_entity(claim):
            continue
        seen.add(claim)
        want_corrupt = len(corrupted) < n_corrupt and (
            len(clean) >= n_clean or len(corrupted) <= len(clean))
        if want_corrupt:
            ops += 1
            s = _json(SWAP_PROMPT.format(claim=claim))
            shown = str(s.get("corrupted", "")).strip()
            if not shown or shown == claim:
                continue
            ops += 1
            v = _json(VAL_CORRUPT.format(original=claim, modified=shown))
            if gate_corrupt(v):
                item = {"statement": shown, "gold": "false",
                        "is_corrupted": True, "kind": "entity",
                        "original_statement": claim,
                        "original_entity": s.get("original_entity", ""),
                        "new_entity": s.get("new_entity", "")}
                corrupted.append(item)
                new_items.append(item)
        else:
            ops += 1
            v = _json(VAL_CLEAN.format(claim=claim))
            if gate_clean(v):
                item = {"statement": claim, "gold": "true",
                        "is_corrupted": False, "kind": "entity",
                        "original_statement": claim}
                clean.append(item)
                new_items.append(item)
        if ops % 20 == 0:
            print(f"  ops {ops}: clean={len(clean)} corrupted={len(corrupted)}", flush=True)

    items = seed_items + new_items if seed_items else clean[:n_clean] + corrupted[:n_corrupt]
    for i, it in enumerate(items):
        it.setdefault("id", f"ent_{i+1:04d}")
    with out.open("w") as f:
        for it in items:
            f.write(json.dumps(it) + "\n")
    print(f"\nWrote {len(items)} ({len(clean[:n_clean])} clean / "
          f"{len(corrupted[:n_corrupt])} corrupted) -> {out.relative_to(ROOT)}  ops={ops}")


if __name__ == "__main__":
    main()
