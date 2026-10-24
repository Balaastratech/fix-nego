"""Run the backend pytest suite offline, same recipe as the earlier pin job.

Usage: python run_suite.py <venv-python> <backend-dir> <junit-out-dir> <log>
Strips every *API_KEY/SECRET/TOKEN/CREDENTIAL env var, forces HF offline,
points cloud credentials at a missing file, 20s per-test timeout.
"""

import os
import subprocess
import sys
from pathlib import Path

py, backend, junit, log = sys.argv[1:5]
tmp = Path(junit).with_suffix(".tmp")
tmp.mkdir(parents=True, exist_ok=True)
env = {k: v for k, v in os.environ.items()
       if not any(w in k.upper() for w in ("API_KEY", "SECRET", "TOKEN", "CREDENTIAL"))}
env.update(
    HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HOME=str(tmp / "hf"),
    PYTHONIOENCODING="utf-8", SPEECHBRAIN_ENABLED="False", SPEAKER_RECOGNITION_ENABLED="False",
    GOOGLE_GENAI_USE_VERTEXAI="False", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
    TEMP=str(tmp), TMP=str(tmp), CLOUDSDK_CONFIG=str(tmp / "gcloud"),
    GOOGLE_APPLICATION_CREDENTIALS=str(tmp / "no-credentials.json"),
    GOOGLE_CLOUD_PROJECT="offline-sdk-check", GOOGLE_AUTH_DISABLE_GCE_CHECK="true",
    PYTHONPATH=str(Path(backend).resolve()),
)
# One pytest process per test file: on Windows pytest-timeout can only kill the
# whole process, so a single hang would otherwise hide every later test.
files = sorted(p.relative_to(backend).as_posix() for p in Path(backend, "tests").rglob("test_*.py"))
junit_dir = Path(junit).resolve()
junit_dir.mkdir(parents=True, exist_ok=True)
with open(log, "w", encoding="utf-8") as f:
    for i, test_file in enumerate(files):
        cmd = [py, "-m", "pytest", test_file, "-p", "pytest_timeout", "-p", "pytest_asyncio.plugin",
               "-p", "hypothesis.extra.pytestplugin", "--timeout=20", "-p", "no:cacheprovider",
               f"--basetemp={tmp / f'pytest{i}'}", f"--junitxml={junit_dir / f'{i:02d}.xml'}"]
        f.write(f"\n##### {test_file}\n")
        f.flush()
        try:
            rc = subprocess.run(cmd, cwd=backend, env=env, stdout=f, stderr=subprocess.STDOUT,
                                timeout=900).returncode
        except subprocess.TimeoutExpired:
            rc = "file-timeout"
        f.write(f"##### exit {rc}\n")
        print(test_file, "exit", rc, flush=True)
