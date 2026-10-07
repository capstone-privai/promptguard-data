import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def load_env(path: Path = ENV_FILE) -> None:
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def connection_settings() -> dict:
    load_env()
    return {
        "host": os.environ["PG_HOST"],
        "port": int(os.environ["PG_PORT"]),
        "user": os.environ["PG_USER"],
        "password": os.environ["PG_PASS"],
    }
