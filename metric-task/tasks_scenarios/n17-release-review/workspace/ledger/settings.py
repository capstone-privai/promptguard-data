"""Server settings, read once from the environment at startup (see docs/api.md)."""
import os
from dataclasses import dataclass

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


@dataclass(frozen=True)
class Settings:
    db_url: str
    page_size_default: int
    page_size_max: int
    log_level: str
    currency: str


def load(environ=None):
    env = os.environ if environ is None else environ
    if "LEDGER_DATABASE_URL" not in env:
        raise RuntimeError("LEDGER_DATABASE_URL is required")
    log_level = env.get("LEDGER_LOG_LEVEL", "INFO").upper()
    if log_level not in LOG_LEVELS:
        raise RuntimeError(f"LEDGER_LOG_LEVEL must be one of {', '.join(LOG_LEVELS)}")
    return Settings(
        db_url=env["LEDGER_DATABASE_URL"],
        page_size_default=int(env.get("LEDGER_PAGE_SIZE", "20")),
        page_size_max=int(env.get("LEDGER_PAGE_SIZE_MAX", "100")),
        log_level=log_level,
        currency=env.get("LEDGER_DEFAULT_CURRENCY", "KRW"),
    )
