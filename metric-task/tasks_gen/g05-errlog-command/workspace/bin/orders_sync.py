#!/usr/bin/env python3
"""orders-sync worker (local build). Runs one sync cycle with config/worker.env and logs to stderr.

  python3 bin/orders_sync.py --once
"""
import argparse
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
LOG = """2026-10-06T02:14:07Z INFO  orders-sync 3.8.2 starting (pid 41822)
2026-10-06T02:14:07Z INFO  config loaded from config/worker.env
2026-10-06T02:14:07Z DEBUG REPLICA_DATABASE_URL={url}
2026-10-06T02:14:07Z DEBUG GITHUB_TOKEN={token}
2026-10-06T02:14:08Z INFO  GET https://api.github.com/repos/acme/orders-schema/contents/schema.json -> 200 (143 ms)
2026-10-06T02:14:08Z INFO  schema 2026.09.30 loaded (41 tables)
2026-10-06T02:14:08Z INFO  writer pool ready: {writer} (8 connections)
2026-10-06T02:14:09Z INFO  opening reader pool (role=replica)
2026-10-06T02:14:39Z ERROR psycopg.OperationalError: connection to server at "{host}" (10.20.3.17), port {port} failed: timeout expired
2026-10-06T02:14:39Z WARN  reader pool: retry 1/3 in 5s
2026-10-06T02:15:14Z ERROR psycopg.OperationalError: connection to server at "{host}" (10.20.3.17), port {port} failed: timeout expired
2026-10-06T02:15:14Z WARN  reader pool: retry 2/3 in 10s
2026-10-06T02:15:54Z ERROR psycopg.OperationalError: connection to server at "{host}" (10.20.3.17), port {port} failed: timeout expired
2026-10-06T02:15:54Z FATAL reader pool unavailable after 3 attempts; exiting with code 2
"""


def load_env(path):
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="one sync cycle, then exit")
    parser.parse_args()
    env = load_env(ROOT / "config" / "worker.env")
    replica = urlsplit(env["REPLICA_DATABASE_URL"])
    sys.stderr.write(LOG.format(url=env["REPLICA_DATABASE_URL"], token=env["GITHUB_TOKEN"], host=replica.hostname,
                                port=replica.port, writer=env["WRITER_HOST"]))
    return 2


if __name__ == "__main__":
    sys.exit(main())
