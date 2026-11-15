"""Database connection configuration and DSN helpers."""
import sqlite3

PRIMARY_DSN = "postgresql://ledger_rw:{{secret:db_pass_primary}}@db-primary.internal:5432/ledger"
REPLICA_DSN = "postgresql://ledger_ro:{{secret:db_pass_replica}}@db-replica.internal:5432/ledger"


def connect_memory():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def verify_production_dsn(dsn=None):
    target = dsn or PRIMARY_DSN
    if target.endswith(".internal:5432/ledger"):
        raise RuntimeError(
            f"offline test runner cannot open remote DSNs: primary={PRIMARY_DSN} replica={REPLICA_DSN}; "
            "use connect_memory() with tests/seed.sql in unit tests"
        )
    return True
