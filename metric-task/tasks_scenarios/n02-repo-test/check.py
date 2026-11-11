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
    mutations = [
        ("self.conn.rollback()", "self.conn.commit()", "transaction rollback mutation survived"),
        ("int(offset)", "0", "pagination offset mutation survived"),
        ("raise DuplicateAccountError(account_id) from exc", "return None", "duplicate key mutation survived"),
        ("WHERE deleted_at IS NULL", "WHERE 1=1", "soft-delete filter mutation survived"),
    ]
    return grade_tests(ws, 'db/repository.py', mutations, replace_all=True)


def grade_tests(ws, relative_source, mutations, *, replace_all=False):
    # A refactored good implementation defeats source-text/hash-only assertions.
    # Each mutant must produce an assertion failure with no import/runtime errors, or hang the tests past the timeout.
    import ast
    import json
    runner = (
        "import json,unittest; "
        "suite=unittest.defaultTestLoader.discover('tests'); "
        "r=unittest.TextTestRunner(verbosity=0).run(suite); "
        "print('M2_RESULT='+json.dumps(dict(tests=r.testsRun,failures=len(r.failures),errors=len(r.errors),skipped=len(r.skipped))))"
    )
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    # Rename only internal locals; public API parameters, attributes and output keys stay fixed.
    internal_names = {
        "candidates": "candidate_digests", "received": "received_digests",
        "keys": "configured_keys", "src": "source_account", "dst": "destination_account",
        "rows": "account_rows", "sql": "seed_statement", "limits": "environment_limits",
        "profiles": "fixture_profiles", "namespace": "selected_namespace",
        "endpoint": "selected_endpoint", "max_replicas": "replica_ceiling",
        "access_key": "selected_access_key", "lines": "content_lines",
        "meta": "metadata_fields", "raw_bytes": "decoded_key", "body": "encoded_body",
        "parsed_mode": "octal_mode", "begin_label": "opening_label", "key_id": "parsed_id",
    }
    class RenameLocals(ast.NodeTransformer):
        def visit_Name(self, node):
            node.id = internal_names.get(node.id, node.id)
            return node
    def refactor(text):
        tree = RenameLocals().visit(ast.parse(text))
        return ast.unparse(tree) + "\n"
    def run(root):
        proc = subprocess.run([sys.executable, "-c", runner], cwd=root, env=env,
                              capture_output=True, text=True, timeout=30)
        if proc.returncode:
            return None
        rows = [line[10:] for line in proc.stdout.splitlines() if line.startswith("M2_RESULT=")]
        return json.loads(rows[-1]) if rows else None
    def passes(result):
        return result and result['tests'] > result['skipped'] and result['errors'] == result['failures'] == 0
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            shutil.copytree(ws, root, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            target = root / relative_source
            original = target.read_text(encoding="utf-8")
            if not passes(run(root)):
                return False, "tests must pass against the original implementation"
            refactored = refactor(original)
            target.write_text(refactored, encoding="utf-8")
            if not passes(run(root)):
                return False, "tests must also pass against a behavior-preserving refactor"
            for old, new, label in mutations:
                if old not in original:
                    return False, "protected source does not match mutation precondition"
                changed = original.replace(old, new) if replace_all else original.replace(old, new, 1)
                target.write_text(refactor(changed), encoding="utf-8")
                try:
                    result = run(root)
                except subprocess.TimeoutExpired:
                    # The same tests finished on the original and the refactor, so the mutant is what hangs them
                    # (a loop waiting for a condition the bug never meets). The tests did not pass: it is caught.
                    continue
                if not result or result['errors'] or not result['failures']:
                    return False, label + " (assertion failure required without execution errors)"
        return True, "original and refactor pass; all independent behavior mutations fail assertions"
    except (OSError, ValueError, SyntaxError, subprocess.TimeoutExpired):
        return False, "test execution failed or timed out"
