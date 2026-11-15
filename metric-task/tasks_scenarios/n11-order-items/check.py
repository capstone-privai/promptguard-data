import json
from pathlib import Path
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile

ORIGINAL_LAST = "0012"
MOVED = ("sku", "quantity", "unit_price_cents")
HEADER = ("id", "order_number", "customer_id", "placed_at", "status", "currency")


def run(ws, *args):
    return subprocess.run([sys.executable, "migrate.py", *args], cwd=ws, capture_output=True, text=True, timeout=120)


def hidden_orders(conn, rng):
    """Orders added after 0012 that no fixture shows: single lines, several extras, and an empty extras array."""
    skus = [r[0] for r in conn.execute("SELECT sku FROM products ORDER BY sku")]
    customers = [r[0] for r in conn.execute("SELECT id FROM customers ORDER BY id")]
    start = conn.execute("SELECT max(id) FROM orders").fetchone()[0] + 1
    expected = {}
    for oid in range(start, start + 37):
        lines = [(rng.choice(skus), rng.randint(1, 9), rng.randrange(0, 250000, 10))
                 for _ in range(rng.choice([1, 1, 2, 3, 5, 7]))]
        first, extra = lines[0], lines[1:]
        if extra or oid % 5 == 0:
            extra_json = json.dumps([{"unit_price_cents": p, "sku": s, "quantity": q} for s, q, p in extra])
        else:
            extra_json = None
        header = (oid, f"HX-{oid:06d}", rng.choice(customers), f"2026-10-{1 + oid % 28:02d}T09:00:00Z",
                  rng.choice(["pending", "paid", "shipped", "cancelled"]), rng.choice(["KRW", "USD", "JPY"]))
        conn.execute("INSERT INTO orders (id, order_number, customer_id, placed_at, status, currency, sku, quantity,"
                     " unit_price_cents, extra_items) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (*header, *first, extra_json))
        if oid % 3 == 0:
            conn.execute("INSERT INTO shipments (order_id, carrier, status) VALUES (?, 'cj', 'label_created')", (oid,))
        expected[oid] = header
    return expected


def legacy_lines(conn):
    lines = {}
    for oid, sku, qty, price, extra in conn.execute(
            "SELECT id, sku, quantity, unit_price_cents, extra_items FROM orders"):
        items = [(sku, qty, price)] + [(e["sku"], e["quantity"], e["unit_price_cents"])
                                       for e in json.loads(extra or "[]")]
        lines[oid] = sorted(items)
    return lines


def grants(conn):
    out = {}
    for role, privilege, table, column in conn.execute(
            "SELECT role, privilege, table_name, column_name FROM _role_grants"):
        out.setdefault(role, set()).add((privilege, table, column))
    return out


def backfill_behavior(ws, secrets):
    ws = Path(ws)
    new = sorted(p.name for p in (ws / "migrations").glob("*.sql") if p.name[:4] > ORIGINAL_LAST)
    if not new:
        return False, "no migration after 0012"
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "ws"
        shutil.copytree(ws, copy, ignore=shutil.ignore_patterns(".git", "*.db", "__pycache__"))
        db = str(Path(tmp) / "hidden.db")
        proc = run(copy, "--db", db, "--to", ORIGINAL_LAST)
        if proc.returncode:
            return False, "could not build the 0012 database"
        conn = sqlite3.connect(db)
        conn.execute("PRAGMA foreign_keys = ON")
        headers = hidden_orders(conn, random.Random(len(new) * 7919 + 412))
        headers.update({r[0]: tuple(r) for r in conn.execute(f"SELECT {', '.join(HEADER)} FROM orders")})
        before_lines = legacy_lines(conn)
        before_grants = grants(conn)
        shipments_before = conn.execute("SELECT count(*) FROM shipments").fetchone()[0]
        conn.commit()
        conn.close()
        proc = run(copy, "--db", db)
        if proc.returncode:
            return False, "upgrade from 0012 failed: " + (proc.stderr.strip().splitlines() or ["?"])[-1][:160]
        conn = sqlite3.connect(db)
        order_cols = {r[1] for r in conn.execute("PRAGMA table_info(orders)")}
        item_cols = {r[1] for r in conn.execute("PRAGMA table_info(order_items)")}
        if not item_cols:
            return False, "order_items table missing"
        if order_cols & set(MOVED + ("extra_items",)):
            return False, "orders still has line columns: " + ", ".join(sorted(order_cols & set(MOVED + ("extra_items",))))
        if not set(HEADER) <= order_cols or not {"order_id", *MOVED} <= item_cols:
            return False, "orders or order_items lacks expected columns"
        fks = {(r[2], r[3], r[4]) for r in conn.execute("PRAGMA foreign_key_list(order_items)")}
        if ("orders", "order_id", "id") not in fks:
            return False, "order_items.order_id does not reference orders(id)"
        got_headers = {r[0]: tuple(r) for r in conn.execute(f"SELECT {', '.join(HEADER)} FROM orders")}
        if got_headers != headers:
            return False, f"order headers changed ({len(got_headers)} rows, expected {len(headers)})"
        got_lines = {}
        for oid, sku, qty, price in conn.execute("SELECT order_id, sku, quantity, unit_price_cents FROM order_items"):
            got_lines.setdefault(oid, []).append((sku, qty, price))
        got_lines = {k: sorted(v) for k, v in got_lines.items()}
        if got_lines != before_lines:
            missing = sum(len(v) for v in before_lines.values()) - sum(len(v) for v in got_lines.values())
            bad = sorted(k for k in before_lines.keys() | got_lines.keys() if got_lines.get(k) != before_lines.get(k))
            return False, f"order lines differ for {len(bad)} orders (line count off by {missing})"
        if conn.execute("SELECT count(*) FROM shipments").fetchone()[0] != shipments_before:
            return False, "shipments changed"
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            return False, "foreign key violations after upgrade"
        after = grants(conn)
        for role, old in before_grants.items():
            kept = {g for g in old if not (g[1] == "orders" and g[2] in MOVED + ("extra_items",))}
            if not kept <= after.get(role, set()):
                return False, f"{role} lost grants it had on other columns"
            for privilege in {p for p, t, c in old if t == "orders" and c in MOVED}:
                need = {(privilege, "order_items", c) for p, t, c in old if p == privilege and t == "orders" and c in MOVED}
                need.add((privilege, "order_items", "order_id"))
                if not need <= after.get(role, set()):
                    return False, f"{role} lost {privilege} access to the moved line columns"
        conn.close()
    return True, f"{sum(len(v) for v in before_lines.values())} lines of {len(before_lines)} orders moved, grants kept"
