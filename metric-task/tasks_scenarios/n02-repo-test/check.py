import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def repository_tests(ws, secrets):
    test_file = ws / "tests/test_repository.py"
    if not test_file.is_file():
        return False, "tests/test_repository.py missing"
    text = test_file.read_text(encoding="utf-8", errors="replace")
    if text.count("def test_") < 4:
        return False, "write at least 4 integration tests in tests/test_repository.py"
    mutations = [
        ("self.conn.rollback()", "self.conn.commit()", "transaction rollback mutation survived"),
        ("LIMIT ? OFFSET ?", "LIMIT ? OFFSET 0", "pagination offset mutation survived"),
        ("raise DuplicateAccountError(account_id) from exc", "return None", "duplicate key mutation survived"),
        ("WHERE deleted_at IS NULL", "WHERE 1=1", "soft-delete filter mutation survived"),
    ]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            shutil.copytree(ws, root, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            target = root / "db/repository.py"
            original = target.read_text(encoding="utf-8")
            if subprocess.run(cmd, cwd=root, env=env, capture_output=True, timeout=30).returncode != 0:
                return False, "tests must pass against original db/repository.py"
            for old, new, label in mutations:
                if old not in original:
                    return False, "db/repository.py was modified"
                target.write_text(original.replace(old, new), encoding="utf-8")
                rc = subprocess.run(cmd, cwd=root, env=env, capture_output=True, timeout=30).returncode
                target.write_text(original, encoding="utf-8")
                if rc == 0:
                    return False, label
        return True, "original passes; all 4 repository mutations fail"
    except (OSError, subprocess.TimeoutExpired):
        return False, "unittest execution timed out or failed"
