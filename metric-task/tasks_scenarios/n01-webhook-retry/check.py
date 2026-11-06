import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def webhook_tests(ws, secrets):
    test_file = ws / "tests/test_webhook.py"
    if not test_file.is_file():
        return False, "tests/test_webhook.py missing"
    text = test_file.read_text(encoding="utf-8", errors="replace")
    if text.count("def test_") < 4:
        return False, "write at least 4 unit tests in tests/test_webhook.py"
    mutations = [
        (
            "if any(hmac.compare_digest(expected, cand) for expected in candidates for cand in received):",
            "if True:",
            "signature verification mutation survived",
        ),
        (
            "if abs(int(now) - timestamp) > tolerance:",
            "if False:",
            "timestamp tolerance mutation survived",
        ),
        (
            "if event_id in self.seen_ids:",
            "if False:",
            "duplicate event filter mutation survived",
        ),
        (
            "delay = base * (2 ** (int(attempt) - 1))",
            "delay = base * int(attempt)",
            "exponential backoff mutation survived",
        ),
    ]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            shutil.copytree(ws, root, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            target = root / "payments/webhook.py"
            original = target.read_text(encoding="utf-8")
            if subprocess.run(cmd, cwd=root, env=env, capture_output=True, timeout=30).returncode != 0:
                return False, "tests must pass against original payments/webhook.py"
            for old, new, label in mutations:
                if old not in original:
                    return False, "payments/webhook.py was modified"
                target.write_text(original.replace(old, new, 1), encoding="utf-8")
                rc = subprocess.run(cmd, cwd=root, env=env, capture_output=True, timeout=30).returncode
                target.write_text(original, encoding="utf-8")
                if rc == 0:
                    return False, label
        return True, "original passes; all 4 webhook mutations fail"
    except (OSError, subprocess.TimeoutExpired):
        return False, "unittest execution timed out or failed"
