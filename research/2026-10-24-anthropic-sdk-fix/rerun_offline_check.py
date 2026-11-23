"""Re-run the offline Claude adapter check on the SDK range the app allows.

Usage (from the app's top folder, any Python 3.11+):
    python research/2026-10-24-anthropic-sdk-fix/rerun_offline_check.py
    python research/2026-10-24-anthropic-sdk-fix/rerun_offline_check.py "anthropic==1.17.0"

For each SDK spec (default: the floor 0.39.0 and the newest the requirements
allow, ">=0.39.0,<3") it builds a throwaway venv, installs only that SDK plus
pytest/pytest-asyncio/hypothesis/pydantic-settings, runs
backend/tests/test_anthropic_sdk_compat.py, then check_task_management.py (the
task-management project's two Claude call shapes). Both swap the SDK's HTTP
client for an in-memory transport and use a placeholder key, and every
*API_KEY/SECRET/TOKEN/CREDENTIAL env var is stripped here: no network call to
Anthropic, no spend. The venvs go in the git-ignored folder .venv-sdk-check/
in the app's top folder, which the script removes at the end. One run at a
time (lock file .venv-sdk-check.lock); a second run exits 2 with
"OFFLINE CHECK BUSY".

Pass line (exit 0):
    OFFLINE CHECK PASS: 18/18 on anthropic <ver>, <ver> (+ task-management calls)
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parents[2]
BACKEND = APP / "backend"
TEST = "tests/test_anthropic_sdk_compat.py"
EXPECTED = 18
LOCK_STALE_S = 30 * 60  # a run takes ~2-5 min; older locks are a killed run's
DEFAULT_SPECS = ["anthropic==0.39.0", "anthropic>=0.39.0,<3"]
EXTRAS = ["pytest>=8.0.0", "pytest-asyncio>=0.23.0", "hypothesis>=6.0.0", "pydantic-settings"]


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", **kw)


def check(spec: str, root: Path, env: dict[str, str]) -> tuple[bool, str]:
    venv = root / re.sub(r"[^A-Za-z0-9.]+", "_", spec)
    r = run([sys.executable, "-m", "venv", "--clear", str(venv)])
    if r.returncode:
        return False, f"venv failed: {r.stderr.strip()[-400:]}"
    py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    r = run([str(py), "-m", "pip", "install", "-q", "--disable-pip-version-check", spec, *EXTRAS])
    if r.returncode:
        return False, f"pip failed: {r.stderr.strip()[-400:]}"
    ver = run([str(py), "-c", "import anthropic; print(anthropic.__version__)"]).stdout.strip()
    r = run([str(py), "-m", "pytest", TEST, "-q", "-p", "no:cacheprovider",
             f"--basetemp={root / 'pt'}"], cwd=BACKEND, env=env)
    out = r.stdout + r.stderr
    passed = re.search(r"(\d+) passed", out)
    n = int(passed.group(1)) if passed else 0
    ok = r.returncode == 0 and n == EXPECTED and not re.search(r"\d+ (failed|error)", out)
    tail = "\n".join(l for l in out.splitlines() if re.search(r"\d+ (passed|failed|error)", l))[-600:]
    # Same venv: the task-management project's two Claude calls (shapes of its
    # app/routes/ai.py on claude-haiku-4-5), also offline.
    tm = run([str(py), str(Path(__file__).with_name("check_task_management.py"))], env=env)
    tm_ok = tm.returncode == 0 and "PASS anthropic" in tm.stdout
    tm_line = (tm.stdout.strip().splitlines() or [tm.stderr.strip()[-300:]])[-1]
    print(f"--- {spec} -> anthropic {ver}: {'PASS' if ok else 'FAIL'} ({n}/{EXPECTED})\n{tail}\n"
          f"    task-management: {tm_line}", flush=True)
    return ok and tm_ok, ver


def main() -> int:
    specs = sys.argv[1:] or DEFAULT_SPECS
    env = {k: v for k, v in os.environ.items()
           if not any(w in k.upper() for w in ("API_KEY", "SECRET", "TOKEN", "CREDENTIAL"))}
    env.update(PYTHONPATH=str(BACKEND), PYTHONIOENCODING="utf-8")
    # Scratch venvs live in a git-ignored folder inside this app copy, never in
    # a shared temp folder; the delete names that folder literally (relative to
    # the app's top folder) so the cleanup can only touch what this run made.
    os.chdir(APP)
    # One run at a time: two runs sharing the folder delete each other's venvs
    # (seen 23-11: a parallel run's pip install failed mid-way). A lock older
    # than LOCK_STALE_S is a killed run's leftover and is taken over.
    lock = APP / ".venv-sdk-check.lock"
    try:
        if lock.exists() and time.time() - lock.stat().st_mtime > LOCK_STALE_S:
            lock.unlink()
        os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        print(f"OFFLINE CHECK BUSY: another run holds {lock.name}; run again after it ends")
        return 2
    results = []
    try:
        shutil.rmtree(".venv-sdk-check", ignore_errors=True)
        root = APP / ".venv-sdk-check"
        root.mkdir(exist_ok=True)  # a killed run's leftover is reused; venv --clear resets it
        for spec in specs:
            results.append(check(spec, root, env))
    finally:
        os.chdir(APP)
        shutil.rmtree(".venv-sdk-check", ignore_errors=True)
        lock.unlink(missing_ok=True)
    vers = ", ".join(v for _, v in results)
    if all(ok for ok, _ in results):
        print(f"OFFLINE CHECK PASS: {EXPECTED}/{EXPECTED} on anthropic {vers} (+ task-management calls)")
        return 0
    print(f"OFFLINE CHECK FAIL: {results}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
