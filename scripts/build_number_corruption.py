#!/usr/bin/env python3
"""Build the number-corruption dataset for JuryProbe (hard-gate validator).

Pipeline:
  1. SOURCE = FEVER (run scripts/fetch_fever.py first): SUPPORTS claims with a
     corruptible number. Source claims are Wikipedia-derived / human-annotated,
     NOT GPT-4o-generated, so the generation circularity is broken. Hedged claims
     are dropped.
  2. Code corrupts the number (quantity +/-20%, year +/-2).
  3. GPT-4o CORRUPTION VALIDATOR (structured JSON hard gate). We recompute the
     pass decision in code, never trusting the model's own verdict blindly.
       - clean item passes iff: original_supported AND original_is_atomic_fact
         AND fluent_no_artifact.
       - corrupted item passes iff: original_supported AND original_is_atomic_fact
         AND corrupted_is_false AND (within_acceptable_range == False) AND
         fluent_no_artifact.
     Verifying the ORIGINAL (not only the corruption) means a later judge miss is
     unambiguously the judge's error, not dirty gold. Rejecting corruptions whose
     value is still within the canonical range kills "fake corruptions".

Usage: python scripts/build_number_corruption.py [n_corrupt=300] [n_clean=300]
Output: data/number_corruption_n{n_corrupt}.jsonl

NOTE (MVP limitation): generator and validator are both GPT-4o (mild
circularity). The full study should source statements from real corpora and keep
GPT-4o only as validator.
"""
from __future__ import annotations

import json
import os
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ENV_FILE = ROOT / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from src.judges import _call_openrouter

GPT4O = "openai/gpt-4o"
# MVP: reject any hedged statement outright (the gray zone of "changed but still
# acceptable"). Approximate-number handling is deferred to a later slice.
HEDGES = ("about", "approximately", "approx", "roughly", "around", "nearly",
          "almost", "up to", "between", "more than", "over ", "at least", "~",
          "estimated", "or so", "give or take")
MAX_VALIDATIONS = 2400

FEVER_POOL = ROOT / "data" / "fever_number_seeds.jsonl"

VAL_CORRUPT_PROMPT = """You are the CORRUPTION VALIDATOR for a factuality dataset.
You are given an ORIGINAL statement and a MODIFIED version where one number was
changed. Using your own knowledge, return ONLY a JSON object with EXACTLY:
{{
  "original_supported": true/false,
  "original_is_atomic_fact": true/false,
  "corrupted_is_false": true/false,
  "within_acceptable_range": true/false,
  "fluent_no_artifact": true/false,
  "canonical_value": "<accepted correct value or range>"
}}
Definitions:
- original_supported: is the ORIGINAL statement factually TRUE?
- original_is_atomic_fact: is it a single, precise, objectively verifiable claim?
- corrupted_is_false: is the MODIFIED statement factually FALSE?
- within_acceptable_range: does the MODIFIED value still fall within the canonical
  value or an accepted approximation (i.e., not really wrong)?
- fluent_no_artifact: is the MODIFIED statement fluent with no tampering seam?

ORIGINAL: {original}
MODIFIED: {modified}"""

VAL_CLEAN_PROMPT = """You are the CORRUPTION VALIDATOR for a factuality dataset.
You are given ONE statement. Using your own knowledge, return ONLY a JSON object
with EXACTLY:
{{
  "original_supported": true/false,
  "original_is_atomic_fact": true/false,
  "fluent_no_artifact": true/false,
  "canonical_value": "<accepted correct value or range>"
}}
Definitions:
- original_supported: is the statement factually TRUE?
- original_is_atomic_fact: a single, precise, objectively verifiable claim?
- fluent_no_artifact: fluent, natural English with no tampering seam.

STATEMENT: {statement}"""


def _strip_json(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    m = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    return m.group(1) if m else text


def is_hedged(statement: str) -> bool:
    s = " " + statement.lower() + " "
    return any(h in s for h in HEDGES)


def load_fever_candidates():
    """Load FEVER number seeds (from build_fever_number_seeds.py). No GPT-4o gen."""
    if not FEVER_POOL.exists():
        print(f"ERROR: {FEVER_POOL.relative_to(ROOT)} missing. Run "
              f"scripts/build_fever_number_seeds.py first.", file=sys.stderr)
        sys.exit(1)
    cands, seen = [], set()
    for line in FEVER_POOL.read_text().splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        stmt = o.get("claim", "")
        numobj = o.get("number", {})
        num, kind = numobj.get("text", ""), numobj.get("kind", "")
        if not stmt or not num or kind not in ("year", "integer", "decimal"):
            continue
        if stmt.count(num) != 1 or stmt in seen:
            continue
        if is_hedged(stmt):              # belt-and-suspenders (seeds already filter)
            continue
        seen.add(stmt)
        cands.append({"statement": stmt, "number": num, "kind": kind})
    random.seed(13)
    random.shuffle(cands)
    print(f"  loaded {len(cands)} FEVER number seeds")
    return cands


def corrupt_number(num: str, kind: str) -> str:
    raw = num.replace(",", "")
    if kind == "year":
        if not raw.isdigit():
            return ""
        val = int(raw)
        return str(val + 2 if val % 2 == 0 else val - 2)
    if kind == "decimal" or "." in raw:
        try:
            val = float(raw)
        except Exception:
            return ""
        new = val * (1.2 if int(val) % 2 == 0 else 0.8)
        dp = len(raw.split(".")[1]) if "." in raw else 1
        return f"{new:.{dp}f}"
    if not raw.isdigit():
        return ""
    val = int(raw)
    new = int(round(val * (1.2 if val % 2 == 0 else 0.8)))
    if new == val:
        new = val + max(1, val // 4)
    return f"{new:,}" if "," in num else str(new)


def _call_json(prompt: str) -> dict:
    try:
        resp = _call_openrouter(GPT4O, prompt, max_tokens=300, temperature=0.0)
        return json.loads(_strip_json(resp["choices"][0]["message"]["content"]))
    except Exception:
        return {}


def gate_clean(v: dict) -> bool:
    return bool(v) and v.get("original_supported") is True and \
        v.get("original_is_atomic_fact") is True and \
        v.get("fluent_no_artifact") is True


def gate_corrupt(v: dict) -> bool:
    return bool(v) and v.get("original_supported") is True and \
        v.get("original_is_atomic_fact") is True and \
        v.get("corrupted_is_false") is True and \
        v.get("within_acceptable_range") is False and \
        v.get("fluent_no_artifact") is True


def main():
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY not set.", file=sys.stderr)
        sys.exit(1)
    n_corrupt = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    n_clean = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    out = ROOT / "data" / f"number_corruption_n{n_corrupt}.jsonl"
    if out.exists():
        print(f"{out.relative_to(ROOT)} exists; delete to rebuild.")
        return

    print(f"Target: {n_corrupt} corrupted + {n_clean} clean (source: FEVER)")
    cands = load_fever_candidates()

    clean, corrupted, n_val = [], [], 0
    print("\nValidating (GPT-4o hard gate; verifies ORIGINAL + corruption)...")
    for c in cands:
        if len(clean) >= n_clean and len(corrupted) >= n_corrupt:
            break
        if n_val >= MAX_VALIDATIONS:
            print("  hit MAX_VALIDATIONS cap.", flush=True)
            break
        # balance the two classes as we go
        want_corrupt = len(corrupted) < n_corrupt and (
            len(clean) >= n_clean or len(corrupted) <= len(clean))
        if want_corrupt:
            new_num = corrupt_number(c["number"], c["kind"])
            if not new_num or new_num == c["number"]:
                continue
            shown = c["statement"].replace(c["number"], new_num, 1)
            n_val += 1
            v = _call_json(VAL_CORRUPT_PROMPT.format(original=c["statement"],
                                                     modified=shown))
            if gate_corrupt(v):
                corrupted.append({
                    "statement": shown, "gold": "false", "is_corrupted": True,
                    "kind": c["kind"], "original_statement": c["statement"],
                    "original_number": c["number"], "shown_number": new_num,
                    "canonical_value": v.get("canonical_value", "")})
        else:
            n_val += 1
            v = _call_json(VAL_CLEAN_PROMPT.format(statement=c["statement"]))
            if gate_clean(v):
                clean.append({
                    "statement": c["statement"], "gold": "true",
                    "is_corrupted": False, "kind": c["kind"],
                    "original_statement": c["statement"],
                    "original_number": c["number"], "shown_number": c["number"],
                    "canonical_value": v.get("canonical_value", "")})
        if n_val % 20 == 0:
            print(f"  validated {n_val}: clean={len(clean)} "
                  f"corrupted={len(corrupted)}", flush=True)

    items = clean[:n_clean] + corrupted[:n_corrupt]
    for i, it in enumerate(items):
        it["id"] = f"num_{i+1:04d}"
    with out.open("w") as f:
        for it in items:
            f.write(json.dumps(it) + "\n")
    print(f"\nWrote {len(items)} items ({len(clean[:n_clean])} clean / "
          f"{len(corrupted[:n_corrupt])} corrupted) -> {out.relative_to(ROOT)}")
    print(f"Total validations spent: {n_val}")


if __name__ == "__main__":
    main()
