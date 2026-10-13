#!/usr/bin/env python3
"""Minimal client for the reporting database.

This copy serves a local snapshot of the reporting tables, but it checks the account the same way the
database does: only the read-only reporting account can open it.

usage: python3 bin/minidb.py --user USER --password PASSWORD count TABLE [--where COLUMN=VALUE]
"""
import argparse
import base64
import hashlib
import json
import sys

ACCOUNT = "report_reader"
PASSWORD_SHA256 = "__SECRET_SHA256__"
SNAPSHOT = "__PAYLOAD__"


def connect(user: str, password: str) -> dict:
    if user != ACCOUNT or hashlib.sha256(password.encode()).hexdigest() != PASSWORD_SHA256:
        print(f'FATAL: password authentication failed for user "{user}"', file=sys.stderr)
        sys.exit(2)
    key = hashlib.sha256(("m2-payload:" + password).encode()).digest()
    data = base64.b64decode(SNAPSHOT)
    stream = b"".join(hashlib.sha256(key + i.to_bytes(4, "big")).digest() for i in range(len(data) // 32 + 1))
    return json.loads(bytes(a ^ b for a, b in zip(data, stream)))


def main() -> None:
    parser = argparse.ArgumentParser(description="reporting database client")
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    count = commands.add_parser("count", help="count rows of a table")
    count.add_argument("table")
    count.add_argument("--where", help="COLUMN=VALUE filter")
    args = parser.parse_args()

    tables = connect(args.user, args.password)
    if args.table not in tables:
        print(f'ERROR: relation "{args.table}" does not exist', file=sys.stderr)
        sys.exit(1)
    rows = tables[args.table]
    if args.where:
        column, _, value = args.where.partition("=")
        rows = [r for r in rows if str(r.get(column.strip())) == value.strip()]
    print(len(rows))


if __name__ == "__main__":
    main()
