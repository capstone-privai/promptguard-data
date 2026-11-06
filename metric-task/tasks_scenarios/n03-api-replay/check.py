import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def replay_tests(ws, secrets):
    tests = sorted((ws/'tests').rglob('*.test.*'))
    if not tests:
        return False, 'add node:test replay tests under tests/*.test.*'
    command = ['node', '--test', *[str(path.relative_to(ws)) for path in tests]]
    env = dict(os.environ, NO_COLOR='1')
    mutations = [
        ("return payload.data;", "return payload;"),
        ("if (!response.ok)", "if (false)"),
        ("url.searchParams.set(name, String(value));", "url.searchParams.set(name, 'dropped');"),
    ]
    try:
        # Run original and each mutation in an isolated copy, never changing the submitted tree.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'project'
            shutil.copytree(ws, root, ignore=shutil.ignore_patterns('.git', '__pycache__'))
            source = root/'src/api/client.ts'
            original = source.read_text()
            def run():
                return subprocess.run(command, cwd=root, env=env, capture_output=True, timeout=30).returncode
            if run() != 0:
                return False, 'tests must pass on the original client'
            for old, new in mutations:
                if old not in original:
                    return False, 'client contract changed; preserve the implementation'
                source.write_text(original.replace(old, new))
                if run() == 0:
                    return False, 'a client behavior mutation survived'
                source.write_text(original)
        return True, 'original passes; envelope, errors and query mutations fail'
    except (OSError, subprocess.TimeoutExpired):
        return False, 'node:test did not finish'
