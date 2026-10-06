#!/usr/bin/env python3
"""Ground the negative control's RF-majority-accepted items (real verifier).

Fills the grounded-verifier cache for the Self-Contained Contradiction control
so the Ground-All-Accepts baseline row on the control is a fully empirical
comparison rather than an analytic interval.

Scope: exactly the items a Ground-All-Accepts policy could ever escalate —
RF-majority-accepted items (union over splits; accept status is per-item).
Same three judges, same grounded prompt, same cache format as the frozen
guardrail verifier caches (mode = grounded_verifier). Idempotent: cached
verdicts are never re-requested.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evaluate_guardrail_policies import (  # noqa: E402
    JUDGES,
    GroundedStore,
    majority_accept,
)
from scripts.evaluate_cross_family_transfer import load_rf  # noqa: E402
from src.io_utils import load_jsonl  # noqa: E402

DATA = ROOT / "data/obvious_contradiction_control_v2_n300.jsonl"
RF_CACHE = ROOT / "results/obvious_number_control_n300_rf.jsonl"
OUT = ROOT / "results/guardrail_grounded/obvious_contradiction_control_v2_n300_grounded_verifier.jsonl"


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true",
                    help="Ground every control item (enables a real Always-Grounded "
                         "row for the utility analysis), not just RF-majority accepts.")
    args = ap.parse_args()

    items = load_jsonl(DATA)
    rf = load_rf(RF_CACHE)
    needed = items if args.all else [
        it for it in items
        if majority_accept([rf.get(it["id"], {}).get(j, "parse_fail") for j in JUDGES])
    ]
    n_clean = sum(1 for it in needed if not it["is_corrupted"])
    print(f"RF-majority-accepted items: {len(needed)} "
          f"(clean {n_clean}, corrupt {len(needed) - n_clean}) "
          f"-> up to {len(needed) * len(JUDGES)} grounded calls")

    store = GroundedStore(OUT, [])
    done = calls = fails = 0
    for it in needed:
        for judge in JUDGES:
            existing = store.get_existing(judge, it)
            if existing:
                done += 1
                continue
            verdict = store.get_or_call(judge, it, run_grounded=True)
            calls += 1
            if verdict not in ("true", "false"):
                fails += 1
                print(f"  parse_fail: {judge} {it['id']}", file=sys.stderr)
        if (needed.index(it) + 1) % 25 == 0:
            print(f"  {needed.index(it) + 1}/{len(needed)} items "
                  f"(cached {done}, new calls {calls}, parse_fails {fails})", flush=True)
    print(f"DONE: cached {done}, new calls {calls}, parse_fails {fails}")
    print(f"cache: {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
