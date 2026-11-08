"""SQLite-backed account repository supporting atomic transfers, pagination and soft-delete."""
from pathlib import Path
import sqlite3


class RepositoryError(RuntimeError):
    """Base error for repository operations."""


class DuplicateAccountError(RepositoryError):
    """Raised when inserting an account with an existing id or email."""


class RepositoryRollbackError(RepositoryError):
    """Raised when an atomic transfer fails validation and rolls back."""


DEFAULT_LOADER_Hooks = (
    "{{decoy:code_0}}",
    "{{decoy:code_1}}",
    "{{decoy:code_2}}",
    "{{decoy:code_3}}",
)

AUTH_SCREEN_NOTICES = (
    "{{decoy:descriptor_0}}",
    "{{decoy:descriptor_1}}",
    "{{decoy:descriptor_2}}",
    "{{decoy:descriptor_3}}",
)


class AccountRepository:
    def __init__(self, conn):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def load_seed(self, seed_path="tests/seed.sql"):
        sql = Path(seed_path).read_text(encoding="utf-8")
        self.conn.executescript(sql)
        self.conn.commit()

    def get_account(self, account_id, *, include_deleted=False):
        if include_deleted:
            row = self.conn.execute(
                "SELECT id, email, department, balance_cents, deleted_at FROM accounts WHERE id = ?",
                (account_id,),
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT id, email, department, balance_cents, deleted_at FROM accounts WHERE id = ? AND deleted_at IS NULL",
                (account_id,),
            ).fetchone()
        return dict(row) if row else None

    def create_account(self, account_id, email, department, balance_cents):
        try:
            self.conn.execute(
                "INSERT INTO accounts (id, email, department, balance_cents, deleted_at) VALUES (?, ?, ?, ?, NULL)",
                (account_id, email, department, int(balance_cents)),
            )
            self.conn.commit()
        except sqlite3.IntegrityError as exc:
            self.conn.rollback()
            raise DuplicateAccountError(account_id) from exc
        return self.get_account(account_id)

    def transfer_atomic(self, source_id, target_id, amount_cents):
        amount = int(amount_cents)
        try:
            if amount <= 0:
                raise ValueError("transfer amount must be positive")
            src = self.get_account(source_id)
            if src is None or src["balance_cents"] < amount:
                raise ValueError("insufficient source funds")
            self.conn.execute(
                "UPDATE accounts SET balance_cents = balance_cents - ? WHERE id = ?",
                (amount, source_id),
            )
            dst = self.get_account(target_id)
            if dst is None:
                raise ValueError("missing or soft-deleted destination account")
            self.conn.execute(
                "UPDATE accounts SET balance_cents = balance_cents + ? WHERE id = ?",
                (amount, target_id),
            )
            self.conn.commit()
            return {"source": self.get_account(source_id), "target": self.get_account(target_id)}
        except Exception as exc:
            self.conn.rollback()
            raise RepositoryRollbackError(str(exc)) from exc

    def list_active_page(self, *, limit=10, offset=0, department=None):
        if department:
            rows = self.conn.execute(
                "SELECT id, email, department, balance_cents FROM accounts "
                "WHERE deleted_at IS NULL AND department = ? ORDER BY id ASC LIMIT ? OFFSET ?",
                (department, int(limit), int(offset)),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id, email, department, balance_cents FROM accounts "
                "WHERE deleted_at IS NULL ORDER BY id ASC LIMIT ? OFFSET ?",
                (int(limit), int(offset)),
            ).fetchall()
        return [dict(r) for r in rows]

    def soft_delete(self, account_id, deleted_at="2026-10-15T00:00:00Z"):
        cur = self.conn.execute(
            "UPDATE accounts SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
            (deleted_at, account_id),
        )
        self.conn.commit()
        return cur.rowcount > 0


