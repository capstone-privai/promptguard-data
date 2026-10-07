"""Checks that the worker's .env points at the port deploy/redis.conf listens on."""
import re
import sys
from pathlib import Path

env = {}
for line in Path(".env").read_text().splitlines():
    if "=" in line and not line.lstrip().startswith("#"):
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()

conf_port = re.search(r"^port\s+(\d+)", Path("deploy/redis.conf").read_text(), re.M).group(1)
missing = [k for k in ("REDIS_HOST", "REDIS_PORT", "REDIS_PASSWORD") if not env.get(k)]
if missing:
    print("FAIL: missing " + ", ".join(missing))
    sys.exit(1)
if env["REDIS_PORT"] != conf_port:
    print(f"FAIL: REDIS_PORT={env['REDIS_PORT']} but redis.conf listens on {conf_port}")
    sys.exit(1)
print("OK: REDIS_PORT matches redis.conf")
