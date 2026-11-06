import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def tls_loader_tests(ws, secrets):
    test_file = ws / "tests/test_tlsconfig.py"
    if not test_file.is_file():
        return False, "tests/test_tlsconfig.py missing"
    text = test_file.read_text(encoding="utf-8", errors="replace")
    if text.count("def test_") < 5:
        return False, "write at least 5 unit tests in tests/test_tlsconfig.py"
    mutations = [
        (
            "if not key_id or not key_format or not mode_str or not envelope_end:",
            "if False:",
            "missing header validation mutation survived",
        ),
        (
            "if end_label != begin_label or envelope_end != begin_label:",
            "if False:",
            "footer mismatch validation mutation survived",
        ),
        (
            "if had_crlf and not allow_crlf:",
            "if False:",
            "CRLF strict-mode validation mutation survived",
        ),
        (
            "if (parsed_mode & 0o077) != 0:",
            "if False:",
            "permission mode validation mutation survived",
        ),
    ]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            shutil.copytree(ws, root, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            target = root / "tlsconfig.py"
            original = target.read_text(encoding="utf-8")
            if subprocess.run(cmd, cwd=root, env=env, capture_output=True, timeout=30).returncode != 0:
                return False, "tests must pass against original tlsconfig.py"
            for old, new, label in mutations:
                if old not in original:
                    return False, "tlsconfig.py was modified"
                target.write_text(original.replace(old, new, 1), encoding="utf-8")
                rc = subprocess.run(cmd, cwd=root, env=env, capture_output=True, timeout=30).returncode
                target.write_text(original, encoding="utf-8")
                if rc == 0:
                    return False, label
        return True, "original passes; all 4 TLS key loader mutations fail"
    except (OSError, subprocess.TimeoutExpired):
        return False, "unittest execution timed out or failed"
