#!/usr/bin/env python3
"""Apply the numbered SQL migrations in migrations/ to an orderdesk SQLite database.

    python3 migrate.py                        # upgrade orderdesk.db to the latest migration
    python3 migrate.py --db dev.db --to 0007  # stop after 0007
    python3 migrate.py --status               # applied and pending migrations
    python3 migrate.py --check                # replay every migration on a scratch database and verify it

Production runs on PostgreSQL; local development and CI use SQLite through this script. Each file runs in one
transaction with foreign keys enforced. Role statements (CREATE ROLE / ALTER ROLE / DROP ROLE) are not SQLite
syntax, so they are recorded in the _roles and _role_grants tables, and after every migration each granted
column must still exist.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import sqlite3

ROOT = Path(__file__).resolve().parent
MIGRATIONS = ROOT / "migrations"
FILE_NAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")
ROLE_STATEMENT = re.compile(r"(?:CREATE|ALTER|DROP)\s+ROLE\b", re.I)
TRANSACTION = re.compile(r"(?:BEGIN|COMMIT|END|ROLLBACK|SAVEPOINT|RELEASE)\b", re.I)
FK_OFF = re.compile(r"^--\s*migrate:\s*foreign_keys\s*=\s*off\s*$", re.I | re.M)
CREATE_ROLE = re.compile(r"CREATE\s+ROLE\s+(\w+)\s+(?:WITH\s+)?(LOGIN|NOLOGIN)\s+PASSWORD\s+'((?:[^']|'')*)'"
                         r"(?:\s+GRANT\s+(.+))?\Z", re.I | re.S)
ALTER_ROLE = re.compile(r"ALTER\s+ROLE\s+(\w+)\s+(GRANT|REVOKE)\s+(.+)\Z", re.I | re.S)
DROP_ROLE = re.compile(r"DROP\s+ROLE\s+(\w+)\Z", re.I)
GRANT_ITEM = re.compile(r"\s*(SELECT|INSERT|UPDATE|DELETE)\s*\(([^)]*)\)\s+ON\s+(\w+)\s*", re.I)

BOOKKEEPING = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS _roles (
    name TEXT PRIMARY KEY,
    login INTEGER NOT NULL,
    password_sha256 TEXT NOT NULL,
    created_in TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS _role_grants (
    role TEXT NOT NULL REFERENCES _roles(name) ON DELETE CASCADE,
    privilege TEXT NOT NULL,
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    granted_in TEXT NOT NULL,
    PRIMARY KEY (role, privilege, table_name, column_name)
);
"""


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Migration:
    version: str
    slug: str
    path: Path

    @property
    def name(self) -> str:
        return self.path.name

    def text(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def checksum(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class Statement:
    sql: str
    line: int


def discover(directory: Path = MIGRATIONS) -> list[Migration]:
    found = []
    for path in sorted(directory.glob("*.sql")):
        match = FILE_NAME.match(path.name)
        if not match:
            raise MigrationError(f"{path.name}: migration files are named NNNN_snake_case.sql")
        found.append(Migration(match.group(1), match.group(2), path))
    for expected, migration in enumerate(found, 1):
        if int(migration.version) != expected:
            raise MigrationError(f"{migration.name}: expected version {expected:04d}; numbers must be contiguous")
    return found


def split_statements(text: str) -> list[Statement]:
    """Split at top-level semicolons. Quoted text, -- and /* */ comments and CREATE TRIGGER ... BEGIN ... END
    bodies stay whole; comments are dropped."""
    out: list[Statement] = []
    buf: list[str] = []
    start = None
    line, i, depth, n = 1, 0, 0, len(text)
    while i < n:
        ch = text[i]
        if text.startswith("--", i):
            end = text.find("\n", i)
            i = n if end < 0 else end
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                raise MigrationError(f"line {line}: unterminated /* comment")
            line += text.count("\n", i, end + 2)
            i = end + 2
            continue
        if ch in "'\"":
            end = i + 1
            while True:
                end = text.find(ch, end)
                if end < 0:
                    raise MigrationError(f"line {line}: unterminated {ch} quote")
                if text.startswith(ch * 2, end):
                    end += 2
                    continue
                break
            start = line if start is None else start
            buf.append(text[i:end + 1])
            line += text.count("\n", i, end + 1)
            i = end + 1
            continue
        if ch.isalpha() or ch == "_":
            end = i
            while end < n and (text[end].isalnum() or text[end] == "_"):
                end += 1
            word = text[i:end].upper()
            start = line if start is None else start
            if word == "BEGIN" and re.match(r"\s*CREATE\s+(?:TEMP\w*\s+)?TRIGGER\b", "".join(buf), re.I):
                depth += 1
            elif word == "END" and depth:
                depth -= 1
            buf.append(text[i:end])
            i = end
            continue
        if ch == ";" and not depth:
            sql = "".join(buf).strip()
            if sql:
                out.append(Statement(sql, start))
            buf, start = [], None
            i += 1
            continue
        if ch == "\n":
            line += 1
        elif not ch.isspace() and start is None:
            start = line
        buf.append(ch)
        i += 1
    if "".join(buf).strip():
        raise MigrationError(f"line {start}: statement is missing its terminating semicolon")
    return out


def parse_grants(text: str, where: str) -> list[tuple[str, str, str]]:
    """'SELECT (id, sku) ON orders, UPDATE (status) ON orders' -> [(privilege, table, column), ...]"""
    grants, pos = [], 0
    while True:
        match = GRANT_ITEM.match(text, pos)
        if not match:
            raise MigrationError(f"{where}: cannot read the grant list near {text[pos:pos + 40]!r}")
        columns = [c.strip() for c in match.group(2).split(",") if c.strip()]
        if not columns:
            raise MigrationError(f"{where}: {match.group(1)} on {match.group(3)} names no columns")
        grants += [(match.group(1).upper(), match.group(3), column) for column in columns]
        pos = match.end()
        if pos == len(text):
            return grants
        if text[pos] != ",":
            raise MigrationError(f"{where}: expected ',' between grants near {text[pos:pos + 40]!r}")
        pos += 1


def apply_role(conn: sqlite3.Connection, statement: Statement, where: str) -> None:
    sql = statement.sql
    if match := CREATE_ROLE.match(sql):
        name, login, password, grants = match.groups()
        if conn.execute("SELECT 1 FROM _roles WHERE name = ?", (name,)).fetchone():
            raise MigrationError(f"{where}: role {name} already exists")
        digest = hashlib.sha256(password.replace("''", "'").encode()).hexdigest()
        conn.execute("INSERT INTO _roles VALUES (?, ?, ?, ?)", (name, login.upper() == "LOGIN", digest, where))
        for privilege, table, column in parse_grants(grants, where) if grants else []:
            conn.execute("INSERT OR IGNORE INTO _role_grants VALUES (?, ?, ?, ?, ?)",
                         (name, privilege, table, column, where))
    elif match := ALTER_ROLE.match(sql):
        name, action, grants = match.groups()
        if not conn.execute("SELECT 1 FROM _roles WHERE name = ?", (name,)).fetchone():
            raise MigrationError(f"{where}: role {name} does not exist")
        for privilege, table, column in parse_grants(grants, where):
            if action.upper() == "GRANT":
                conn.execute("INSERT OR IGNORE INTO _role_grants VALUES (?, ?, ?, ?, ?)",
                             (name, privilege, table, column, where))
            else:
                conn.execute("DELETE FROM _role_grants WHERE role = ? AND privilege = ? AND table_name = ?"
                             " AND column_name = ?", (name, privilege, table, column))
    elif match := DROP_ROLE.match(sql):
        if not conn.execute("DELETE FROM _roles WHERE name = ?", (match.group(1),)).rowcount:
            raise MigrationError(f"{where}: role {match.group(1)} does not exist")
    else:
        raise MigrationError(f"{where}: unsupported role statement: {sql[:80]}")


def table_columns(conn: sqlite3.Connection, table: str) -> set[str] | None:
    rows = conn.execute("SELECT name FROM pragma_table_info(?)", (table,)).fetchall()
    return {r[0] for r in rows} or None


def statement_at(granted_in: str) -> str:
    """The statement a grant came from, for the error report."""
    file_name, _, line = granted_in.rpartition(":")
    for statement in split_statements((MIGRATIONS / file_name).read_text(encoding="utf-8")):
        if statement.line == int(line):
            return statement.sql
    return "(statement not found; was the file edited after it was applied?)"


def grant_problems(conn: sqlite3.Connection) -> list[str]:
    problems, sources = [], {}
    rows = conn.execute("SELECT role, privilege, table_name, column_name, granted_in FROM _role_grants"
                        " ORDER BY role, table_name, column_name, privilege").fetchall()
    for role, privilege, table, column, granted_in in rows:
        columns = table_columns(conn, table)
        if columns is None:
            reason = f"table {table} does not exist"
        elif column not in columns:
            reason = f"column {table}.{column} does not exist"
        else:
            continue
        problems.append(f"  {role}: {privilege} on {table}.{column}: {reason} (granted in {granted_in})")
        sources.setdefault(granted_in, statement_at(granted_in))
    if problems:
        problems.append("granting statements:")
        problems += [f"  {where}:\n    " + "\n    ".join(sql.splitlines()) for where, sql in sources.items()]
    return problems


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(BOOKKEEPING)
    return conn


def apply(conn: sqlite3.Connection, migration: Migration) -> None:
    """Run one file in a transaction. A file with the line `-- migrate: foreign_keys=off` runs with enforcement
    off (SQLite cannot change it inside a transaction); the foreign key check below still has to pass."""
    text = migration.text()
    statements = split_statements(text)
    fk_off = bool(FK_OFF.search(text))
    if fk_off:
        conn.execute("PRAGMA foreign_keys = OFF")
    try:
        _apply(conn, migration, statements)
    finally:
        if fk_off:
            conn.execute("PRAGMA foreign_keys = ON")


def _apply(conn: sqlite3.Connection, migration: Migration, statements: list[Statement]) -> None:
    conn.execute("BEGIN")
    try:
        for statement in statements:
            where = f"{migration.name}:{statement.line}"
            if ROLE_STATEMENT.match(statement.sql):
                apply_role(conn, statement, where)
                continue
            if TRANSACTION.match(statement.sql):
                raise MigrationError(f"{where}: migrate.py manages transactions; remove {statement.sql.split()[0]}")
            try:
                conn.execute(statement.sql)
            except sqlite3.Error as exc:
                raise MigrationError(f"{where}: {exc}\n    {statement.sql}") from exc
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            shown = ", ".join(f"{t} rowid {r} -> {p}" for t, r, p, _ in violations[:5])
            raise MigrationError(f"{migration.name}: {len(violations)} foreign key violation(s): {shown}")
        problems = grant_problems(conn)
        if problems:
            raise MigrationError(f"{migration.name}: role grants refer to missing columns\n" + "\n".join(problems))
        conn.execute("INSERT INTO schema_migrations VALUES (?, ?, ?, ?)",
                     (migration.version, migration.name, migration.checksum(),
                      datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
        try:
            conn.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            raise MigrationError(f"{migration.name}: deferred constraint failed at commit: {exc}") from exc
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def applied(conn: sqlite3.Connection) -> dict[str, str]:
    return dict(conn.execute("SELECT version, checksum FROM schema_migrations"))


def upgrade(path: str, target: str | None) -> list[str]:
    migrations = discover()
    if target and target not in {m.version for m in migrations}:
        raise MigrationError(f"--to {target}: no such migration")
    conn = connect(path)
    done = applied(conn)
    ran = []
    for migration in migrations:
        if migration.version in done:
            if done[migration.version] != migration.checksum():
                raise MigrationError(f"{migration.name} was edited after it was applied; add a new migration instead")
        else:
            apply(conn, migration)
            ran.append(migration.name)
        if migration.version == target:
            break
    conn.close()
    return ran


def status(path: str) -> list[str]:
    conn = connect(path)
    done = applied(conn)
    lines = []
    for migration in discover():
        state = "pending"
        if migration.version in done:
            state = "applied" if done[migration.version] == migration.checksum() else "applied, file changed since"
        lines.append(f"{migration.name:40s} {state}")
    conn.close()
    return lines


def check() -> list[str]:
    migrations = discover()
    conn = connect(":memory:")
    for migration in migrations:
        apply(conn, migration)
    result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise MigrationError(f"integrity_check: {result}")
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'"
                                          " AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '\\_%' ESCAPE '\\'"
                                          " AND name != 'schema_migrations' ORDER BY name")]
    lines = [f"ok: {len(migrations)} migrations replayed on a scratch database"]
    for table in tables:
        count = conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
        lines.append(f"  {table:24s} {count:6d} rows")
    for role, grants in conn.execute("SELECT r.name, count(g.role) FROM _roles AS r LEFT JOIN _role_grants AS g"
                                     " ON g.role = r.name GROUP BY r.name ORDER BY r.name"):
        lines.append(f"  role {role:19s} {grants:6d} column grants")
    conn.close()
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=str(ROOT / "orderdesk.db"))
    parser.add_argument("--to", metavar="VERSION")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        print("\n".join(check()))
    elif args.status:
        print("\n".join(status(args.db)))
    else:
        ran = upgrade(args.db, args.to)
        print("\n".join(f"applied {name}" for name in ran) or "already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
