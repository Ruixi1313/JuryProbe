"""Tests of release integrity, numeric comparisons, and offline isolation."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from reproduce import compare_numbers, digest, unpack_verified
from build_public_release import write_archive


class ReproductionTests(unittest.TestCase):
    def test_numeric_change_and_missing_value_fail(self):
        count, errors = compare_numbers({"fa": 0.138, "rows": [42, None]}, {"fa": 0, "rows": [42]})
        self.assertEqual(count, 3)
        self.assertEqual(len(errors), 2)

    def test_boolean_is_not_a_numeric_substitute(self):
        self.assertTrue(compare_numbers({"flag": True}, {"flag": 1})[1])

    def test_runtime_cost_exclusion_is_narrow(self):
        expected = {"new_api_calls_this_run": 12, "fa": 0.14}
        self.assertFalse(compare_numbers(expected, {"new_api_calls_this_run": 0, "fa": 0.14}, ["new_api_calls_this_run"])[1])
        self.assertTrue(compare_numbers(expected, {"new_api_calls_this_run": 0, "fa": 0}, ["new_api_calls_this_run"])[1])

    def test_deterministic_archives_and_hash_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            payload = b'{"label":"false"}\n'
            files = {"data/test.jsonl": payload}
            a, b = folder / "a.tar.gz", folder / "b.tar.gz"
            write_archive(a, files)
            write_archive(b, files)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            records = {"data/test.jsonl": {"bytes": len(payload), "sha256": digest(payload)}}
            unpack_verified(a, records, folder / "out")
            self.assertEqual((folder / "out/data/test.jsonl").read_bytes(), payload)
            records["data/test.jsonl"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "Hash mismatch"):
                unpack_verified(a, records, folder / "bad")

    def test_archive_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "bad.tar.gz"
            write_archive(archive, {"../escape": b"x"})
            with self.assertRaisesRegex(ValueError, "Unsafe artifact path"):
                unpack_verified(archive, {}, Path(folder) / "out")

    def test_successful_noop_cannot_reuse_an_old_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            release = Path(folder) / "release"
            (release / "scripts").mkdir(parents=True)
            (release / "reproducibility").mkdir()
            sources = {"scripts/" + name: (ROOT / "scripts" / name).read_bytes()
                       for name in ("reproduce.py", "_offline_reproduction.py")}
            sources["scripts/noop.py"] = b"pass\n"
            for name, payload in sources.items():
                (release / name).write_bytes(payload)
            artifacts = {"results/test.json": b'{"fa":0.14}',
                         "reproducibility/expected/test.json": b'{"fa":0.14}'}
            bundle = release / "reproducibility/cached_inputs.tar.gz"
            write_archive(bundle, artifacts)
            records = lambda files: {name: {"sha256": digest(data), "bytes": len(data)}
                                     for name, data in files.items()}
            manifest = {"source_files": records(sources), "artifact_files": records(artifacts),
                        "bundle": {"path": "reproducibility/cached_inputs.tar.gz",
                                   "sha256": digest(bundle.read_bytes())},
                        "jobs": [{"name": "test", "script": "scripts/noop.py", "args": [],
                                  "output": "results/test.json", "suite": "core", "ignore": [],
                                  "snapshot": "reproducibility/expected/test.json"}]}
            (release / "reproducibility/release_manifest.json").write_text(json.dumps(manifest))
            work = Path(folder) / "work"
            p = subprocess.run([sys.executable, str(release / "scripts/reproduce.py"),
                                "--output-dir", str(work)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            report = json.loads((work / "reproduction_report.json").read_text())
            self.assertFalse(report["jobs"][0]["passed"])
            self.assertIn("No such file", report["jobs"][0]["errors"][0])

    def test_network_and_child_processes_are_blocked(self):
        worker = ROOT / "scripts/_offline_reproduction.py"
        for operation in ("import socket; socket.getaddrinfo('example.com', 443)",
                          "import subprocess; subprocess.run([sys.executable, '-V'])"):
            with self.subTest(operation=operation):
                code = ("import sys; sys.path.insert(0, sys.argv[1]); "
                        "from _offline_reproduction import deny_network; "
                        "sys.addaudithook(deny_network); " + operation)
                p = subprocess.run([sys.executable, "-c", code, str(worker.parent)], capture_output=True, text=True)
                self.assertNotEqual(p.returncode, 0)
                self.assertIn("Offline reproduction forbids", p.stderr)


if __name__ == "__main__":
    unittest.main()
