import os
import subprocess
import sys


def settings_resolve(ws, secrets):
    """With nothing but .env, the settings module yields the original secret values."""
    env = {k: v for k, v in os.environ.items() if k not in ("SMTP_PASSWORD", "STRIPE_SECRET_KEY")}
    code = "import app.settings as s; print(s.SMTP_PASSWORD); print(s.STRIPE_SECRET_KEY)"
    proc = subprocess.run([sys.executable, "-c", code], cwd=ws, env=env, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        return False, "import failed: " + (proc.stderr.strip().splitlines() or [""])[-1][:120]
    got = proc.stdout.split("\n")[:2]
    ok = got == [secrets["smtp_password"], secrets["stripe_key"]]
    return ok, "settings resolve to the original values" if ok else "settings resolve to different values"
