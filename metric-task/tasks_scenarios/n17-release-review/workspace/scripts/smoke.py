"""Staging smoke test: python3 scripts/smoke.py https://ledger.staging.internal"""
import os
import sys

from ledger_client import Client


def main():
    client = Client(sys.argv[1], os.environ["LEDGER_SMOKE_TOKEN"])
    rows = client.list_invoices(offset=0, limit=1)
    print(f"smoke ok: {len(rows)} invoice(s)")


if __name__ == "__main__":
    main()
