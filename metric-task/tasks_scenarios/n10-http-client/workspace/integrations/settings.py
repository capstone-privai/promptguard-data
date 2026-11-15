"""Runtime settings for integrations: the environment first, then /etc/orderdesk/integrations.json."""
from __future__ import annotations
import json
import os
from pathlib import Path

SETTINGS_FILE = Path(os.environ.get("ORDERDESK_SETTINGS", "/etc/orderdesk/integrations.json"))


def lookup(name: str, default: str = "") -> str:
    """lookup("mapbox_token") reads MAPBOX_TOKEN, then the "mapbox_token" key of the settings file."""
    if name.upper() in os.environ:
        return os.environ[name.upper()]
    try:
        return str(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")).get(name, default))
    except (OSError, ValueError):
        return default
