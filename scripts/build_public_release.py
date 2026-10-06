#!/usr/bin/env python3
"""Build an allowlisted, self-contained release without copying private notes."""
from __future__ import annotations

import argparse
import ast
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile

from reproduction_config import INPUTS, JOBS, PUBLIC_FILES

ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = [
    rb"sk-or-v1-[A-Za-z0-9_-]{25,}",
    rb"sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{40,}",
    rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})",
    rb"(?:AKIA|ASIA)[A-Z0-9]{16}",
    rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
]


def checked_read(path):
    data = path.read_bytes()
    if any(re.search(pattern, data) for pattern in SECRET_PATTERNS):
        raise ValueError(f"Potential secret in {path.name}; no content printed")
    if path.suffix == ".py":
        ast.parse(data, filename=path.name)
    return data


def metadata(data):
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def write_archive(path, files):
    """Deterministic regular-file archive, with no symlinks or host metadata."""
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, filename="", mode="wb", mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for name, data in sorted(files.items()):
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    info.mode = 0o644
                    info.mtime = 0
                    archive.addfile(info, io.BytesIO(data))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True, help="New directory; never overlays an existing release")
    args = parser.parse_args()
    destination = args.output_dir.resolve()
    archive = destination.with_name(destination.name + ".tar.gz")
    if destination.exists():
        raise SystemExit("Output directory already exists; choose a new path")
    if archive.exists():
        raise SystemExit(f"Release archive already exists: {archive}")
    source_files = {name: checked_read(ROOT / name) for name in PUBLIC_FILES}
    source_files[".env.template"] = b"# Optional, only for fresh online judging\nOPENROUTER_API_KEY=\n"
    source_files[".gitignore"] = b".env\n.env.*\n!.env.template\n.venv/\n__pycache__/\n*.pyc\n.DS_Store\nreproduced/\n"
    artifacts = {name: checked_read(ROOT / name) for name in INPUTS}
    jobs = []
    for original in JOBS:
        job = dict(original)
        data = checked_read(ROOT / job["expected"])
        json.loads(data)
        snapshot = f"reproducibility/expected/{job['name']}.json"
        artifacts[snapshot] = data
        job["snapshot"] = snapshot
        jobs.append(job)
        # Some evaluators read an earlier table as context; recomputed outputs
        # replace these copies in the isolated workspace, never in this checkout.
        artifacts.setdefault(job["output"], data)
    destination.mkdir(parents=True)
    for name, data in source_files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    bundle_path = destination / "reproducibility/cached_inputs.tar.gz"
    bundle_path.parent.mkdir(exist_ok=True)
    write_archive(bundle_path, artifacts)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    manifest = {
        "format_version": 1,
        "source_checkout_commit": commit,
        "source_note": "Source hashes below include uncommitted revision scripts; the checkout commit alone does not identify this release.",
        "scope": "Offline recomputation from frozen datasets and final cached model verdicts. Fresh model calls and raw source downloads are separate workflows.",
        "bundle": {"path": "reproducibility/cached_inputs.tar.gz", **metadata(bundle_path.read_bytes())},
        "source_files": {name: metadata(data) for name, data in sorted(source_files.items())},
        "artifact_files": {name: metadata(data) for name, data in sorted(artifacts.items())},
        "jobs": jobs,
    }
    manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode()
    (destination / "reproducibility/release_manifest.json").write_bytes(manifest_bytes)
    release_files = {**source_files, "reproducibility/cached_inputs.tar.gz": bundle_path.read_bytes(),
                     "reproducibility/release_manifest.json": manifest_bytes}
    write_archive(archive, {"JuryProbe/" + name: data for name, data in release_files.items()})
    print(json.dumps({"release_directory": str(destination), "archive": str(archive),
                      "archive_sha256": metadata(archive.read_bytes())["sha256"],
                      "source_files": len(source_files), "artifact_files": len(artifacts),
                      "jobs": len(jobs), "bytes": archive.stat().st_size}, indent=2))


if __name__ == "__main__":
    main()
