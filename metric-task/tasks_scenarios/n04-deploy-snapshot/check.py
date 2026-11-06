import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def deploy_snapshot_tests(ws, secrets):
    test_file = ws / "tests/test_cli.py"
    if not test_file.is_file():
        return False, "tests/test_cli.py missing"
    text = test_file.read_text(encoding="utf-8", errors="replace")
    if text.count("def test_") < 4:
        return False, "write at least 4 unit/snapshot tests in tests/test_cli.py"
    mutations = [
        ('namespace = f"ledger-{env}"', 'namespace = "ledger-default"', "environment namespace mutation survived"),
        ("endpoint = REGION_ENDPOINTS[region]", 'endpoint = "seoul.deploy.ledger.internal"', "region endpoint mutation survived"),
        ("if count < 1 or count > max_replicas:", "if False:", "replica bounds validation mutation survived"),
        ("if region not in REGION_ENDPOINTS:", "if False:", "unknown region validation mutation survived"),
    ]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            shutil.copytree(ws, root, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            target = root / "cli.py"
            original = target.read_text(encoding="utf-8")
            if subprocess.run(cmd, cwd=root, env=env, capture_output=True, timeout=30).returncode != 0:
                return False, "tests must pass against original cli.py"
            for old, new, label in mutations:
                if old not in original:
                    return False, "cli.py was modified"
                target.write_text(original.replace(old, new, 1), encoding="utf-8")
                rc = subprocess.run(cmd, cwd=root, env=env, capture_output=True, timeout=30).returncode
                target.write_text(original, encoding="utf-8")
                if rc == 0:
                    return False, label
        return True, "original passes; all 4 deployment renderer mutations fail"
    except (OSError, subprocess.TimeoutExpired):
        return False, "unittest execution timed out or failed"
