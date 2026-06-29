"""IO + caching helpers.

`load_pairs` / `save_pairs` read and write the input benchmark JSONL.

`RawCache` stores one record per judge call so reruns skip API calls. Keyed
by (judge, item_id, cascade_mode, prior_verdicts) so independent and
sequential passes don't collide and re-running after a crash is free.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


def load_jsonl(path: Path) -> List[Dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def append_jsonl(path: Path, record: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def write_jsonl(path: Path, records: Iterable[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _cache_key(judge: str, item_id: int, mode: str,
               prior: Optional[List[str]]) -> Tuple:
    return (judge, item_id, mode, tuple(prior) if prior else ())


class RawCache:
    """Append-only on disk; in-memory lookup."""

    def __init__(self, path: Path):
        self.path = path
        self._mem: Dict[Tuple, Dict] = {}
        if path.exists():
            for r in load_jsonl(path):
                self._mem[_cache_key(
                    r["judge"], r["item_id"], r["mode"], r.get("prior")
                )] = r

    def get(self, judge: str, item_id: int, mode: str,
            prior: Optional[List[str]]) -> Optional[Dict]:
        return self._mem.get(_cache_key(judge, item_id, mode, prior))

    def put(self, record: Dict) -> None:
        key = _cache_key(record["judge"], record["item_id"],
                         record["mode"], record.get("prior"))
        if key in self._mem:
            return
        self._mem[key] = record
        append_jsonl(self.path, record)

    def __len__(self) -> int:
        return len(self._mem)
