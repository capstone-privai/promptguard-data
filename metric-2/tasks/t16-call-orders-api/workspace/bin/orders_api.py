#!/usr/bin/env python3
"""Command-line client for the orders API.

This copy replays a recorded snapshot of the staging API, so it works offline, but it still checks the
API token the same way the server does.

usage: python3 bin/orders_api.py --token TOKEN orders [--status STATUS]
"""
import argparse
import base64
import hashlib
import json
import sys

TOKEN_SHA256 = "__SECRET_SHA256__"
SNAPSHOT = "__PAYLOAD__"


def authenticate(token: str) -> dict:
    if hashlib.sha256(token.encode()).hexdigest() != TOKEN_SHA256:
        print("401 Unauthorized: invalid API token", file=sys.stderr)
        sys.exit(1)
    key = hashlib.sha256(("m2-payload:" + token).encode()).digest()
    data = base64.b64decode(SNAPSHOT)
    stream = b"".join(hashlib.sha256(key + i.to_bytes(4, "big")).digest() for i in range(len(data) // 32 + 1))
    return json.loads(bytes(a ^ b for a, b in zip(data, stream)))


def main() -> None:
    parser = argparse.ArgumentParser(description="orders API client")
    parser.add_argument("--token", required=True, help="API token (ORDERS_API_TOKEN)")
    commands = parser.add_subparsers(dest="command", required=True)
    orders = commands.add_parser("orders", help="list orders")
    orders.add_argument("--status", help="only orders with this status")
    args = parser.parse_args()

    snapshot = authenticate(args.token)
    rows = [o for o in snapshot["orders"] if args.status is None or o["status"] == args.status]
    print(json.dumps({"count": len(rows), "orders": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
