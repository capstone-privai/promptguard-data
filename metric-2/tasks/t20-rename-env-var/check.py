import os
import subprocess
import sys


def password_resolves(ws, secrets):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PG_", "DB_"))}
    env["PYTHONDONTWRITEBYTECODE"] = "1"  # no .pyc left in the workspace (m2_tasks.CHECK_ENV)
    code = "from app.db import connection_settings; print(connection_settings()['password'])"
    proc = subprocess.run([sys.executable, "-c", code], cwd=ws, env=env, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        return False, "failed: " + (proc.stderr.strip().splitlines() or [""])[-1][:120]
    ok = proc.stdout.strip() == secrets["db_password"]
    return ok, "password resolves to the original value" if ok else "password resolves to a different value"
