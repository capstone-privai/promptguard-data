"""Validates config/integrations.json before deploy."""
import json
import sys
from pathlib import Path

path = Path("config/integrations.json")
try:
    config = json.loads(path.read_text())
except json.JSONDecodeError as e:
    print(f"ERROR: {path}: {e.msg} at line {e.lineno} column {e.colno}")
    sys.exit(1)
missing = [k for k in ("slack", "sentry", "pagerduty", "retry") if k not in config]
if missing:
    print("ERROR: missing sections: " + ", ".join(missing))
    sys.exit(1)
print("OK: integrations config is valid")
