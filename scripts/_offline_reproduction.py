"""Execute one cached evaluator with network access disabled."""
from __future__ import annotations

import os
from pathlib import Path
import runpy
import sys


def deny_network(event, args):
    if event in {"socket.connect", "socket.connect_ex", "socket.getaddrinfo", "subprocess.Popen", "os.system"}:
        raise RuntimeError("Offline reproduction forbids network access and child processes")


def main():
    root = Path(__file__).resolve().parents[1]
    target = (root / sys.argv[1]).resolve()
    if root not in target.parents or target.suffix != ".py":
        raise SystemExit("Evaluator must be a Python file inside the reproduction workspace")
    os.environ.pop("OPENROUTER_API_KEY", None)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "scripts"))
    sys.addaudithook(deny_network)
    sys.argv = [str(target), *sys.argv[2:]]
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
