#!/usr/bin/env python3
"""Verify and replay frozen results in an isolated, network-disabled workspace."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_relative(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or not path.parts:
        raise ValueError(f"Unsafe artifact path: {name}")
    return path


def numeric_leaves(obj, path=()):
    """Record all numeric, boolean, and null fields, including per-split arrays."""
    out = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            out.update(numeric_leaves(value, (*path, key)))
    elif isinstance(obj, list):
        for key, value in enumerate(obj):
            out.update(numeric_leaves(value, (*path, key)))
    elif obj is None or isinstance(obj, (bool, int, float)):
        out[path] = obj
    return out


def compare_numbers(expected, actual, ignored=()):
    expected = numeric_leaves(expected)
    actual = numeric_leaves(actual)
    errors = []
    checked = 0
    for path, old in expected.items():
        if path and path[0] in ignored:
            continue
        checked += 1
        label = ".".join(str(p) for p in path)
        if path not in actual:
            errors.append(f"{label}: missing")
            continue
        new = actual[path]
        if old is None or isinstance(old, bool):
            same = type(old) is type(new) and old == new
        elif isinstance(new, (int, float)) and not isinstance(new, bool):
            same = old == new or math.isclose(old, new, rel_tol=1e-10, abs_tol=1e-12)
        else:
            same = False
        if not same:
            errors.append(f"{label}: expected {old!r}, got {new!r}")
    if not checked:
        errors.append("No numeric fields were checked")
    return checked, errors


def unpack_verified(bundle, records, destination):
    seen = set()
    with tarfile.open(bundle, "r:gz") as archive:
        for member in archive:
            safe_relative(member.name)
            if not member.isfile() or member.name in seen or member.name not in records:
                raise ValueError(f"Unexpected archive member: {member.name}")
            record = records[member.name]
            if member.size != record["bytes"]:
                raise ValueError(f"Size mismatch: {member.name}")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"Unreadable archive member: {member.name}")
            data = stream.read()
            if digest(data) != record["sha256"]:
                raise ValueError(f"Hash mismatch: {member.name}")
            target = destination / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            seen.add(member.name)
    if seen != set(records):
        raise ValueError(f"Missing archive members: {sorted(set(records) - seen)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=["core", "all"], default="core")
    parser.add_argument("--only", help="Comma-separated job names; dependencies remain the caller's responsibility")
    parser.add_argument("--output-dir", type=Path, help="New, empty destination; defaults to a temporary directory")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    manifest_path = ROOT / "reproducibility/release_manifest.json"
    if not manifest_path.is_file():
        raise SystemExit("Release bundle absent. Maintainer: run scripts/build_public_release.py --output-dir PATH first.")
    manifest = json.loads(manifest_path.read_text())
    for name, record in manifest["source_files"].items():
        safe_relative(name)
        if digest((ROOT / name).read_bytes()) != record["sha256"]:
            raise SystemExit(f"Source hash mismatch: {name}")
    bundle = ROOT / manifest["bundle"]["path"]
    if digest(bundle.read_bytes()) != manifest["bundle"]["sha256"]:
        raise SystemExit("Cached-input bundle hash mismatch")
    if args.output_dir:
        work = args.output_dir.resolve()
        if work.exists():
            raise SystemExit("Output directory must not already exist; existing results are never overwritten")
        work.mkdir(parents=True)
    else:
        work = Path(tempfile.mkdtemp(prefix="juryprobe-reproduced-"))
    for name in manifest["source_files"]:
        target = work / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    unpack_verified(bundle, manifest["artifact_files"], work)
    print(f"Verified {len(manifest['source_files'])} source files and {len(manifest['artifact_files'])} cached artifacts", flush=True)
    print(f"Workspace: {work}", flush=True)
    if args.verify_only:
        return
    selected = set(args.only.split(",")) if args.only else None
    known = {j["name"] for j in manifest["jobs"]}
    if selected and selected - known:
        raise SystemExit(f"Unknown jobs: {sorted(selected - known)}")
    jobs = [j for j in manifest["jobs"] if (j["name"] in selected if selected else args.suite == "all" or j["suite"] == "core")]
    env = dict(os.environ)
    env.pop("OPENROUTER_API_KEY", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONHASHSEED"] = "0"
    report = {"bundle_sha256": manifest["bundle"]["sha256"], "jobs": [], "network": "disabled"}
    failures = []
    for job in jobs:
        print(f"RUN {job['name']}", flush=True)
        log = work / "logs" / (job["name"] + ".log")
        log.parent.mkdir(exist_ok=True)
        # A successful no-op must not pass by leaving the bundled summary intact.
        (work / job["output"]).unlink(missing_ok=True)
        start = time.monotonic()
        with log.open("w") as handle:
            proc = subprocess.run([sys.executable, "scripts/_offline_reproduction.py", job["script"], *job["args"]],
                                  cwd=work, env=env, stdout=handle, stderr=subprocess.STDOUT)
        errors = []
        checked = 0
        if proc.returncode:
            errors = [f"Evaluator exited {proc.returncode}; see {log}"]
        else:
            try:
                actual = json.loads((work / job["output"]).read_text())
                expected = json.loads((work / job["snapshot"]).read_text())
                checked, errors = compare_numbers(expected, actual, job["ignore"])
                if actual.get("new_api_calls_this_run", 0) != 0:
                    errors.append("Evaluator reported new API calls")
            except (OSError, ValueError) as exc:
                errors = [str(exc)]
        entry = dict(name=job["name"], passed=not errors, numeric_fields=checked,
                     seconds=round(time.monotonic() - start, 2), errors=errors)
        report["jobs"].append(entry)
        print(f"{'FAIL' if errors else 'PASS'} {job['name']}: {checked} numeric fields, {entry['seconds']}s", flush=True)
        if errors:
            failures.append(job["name"])
            print("\n".join(errors[:12]), flush=True)
    # Detect a cache miss that a legacy API wrapper may have caught as parse_fail.
    changed = [name for name, rec in manifest["artifact_files"].items()
               if name.startswith(("data/", "results/")) and name not in {j["output"] for j in manifest["jobs"]}
               and digest((work / name).read_bytes()) != rec["sha256"]]
    if changed:
        failures.append("input_mutation")
    report["changed_inputs"] = changed
    report["passed"] = not failures
    (work / "reproduction_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"RESULT: {len(jobs) - len([f for f in failures if f != 'input_mutation'])}/{len(jobs)} jobs passed; changed inputs: {len(changed)}", flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
