"""SQLite helpers. Pretty much all the persistence lives here."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from app.core.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  id            INTEGER PRIMARY KEY,
  file_path     TEXT NOT NULL,
  sha256        TEXT NOT NULL UNIQUE,
  doc_type      TEXT,
  vendor        TEXT,
  invoice_no    TEXT,
  issue_date    TEXT,
  due_date      TEXT,
  currency      TEXT,
  net_amount    REAL,
  vat_amount    REAL,
  vat_rate      REAL,
  gross_amount  REAL,
  category      TEXT,
  status        TEXT NOT NULL,
  review_reason TEXT,
  note          TEXT,
  model_used    TEXT,
  raw_json      TEXT,
  created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS vendor_rules (
  vendor_normalized TEXT PRIMARY KEY,
  category          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_invoice_no
  ON documents (invoice_no);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(documents)").fetchall()}
    if "note" not in cols:
        conn.execute("ALTER TABLE documents ADD COLUMN note TEXT")


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


def get_by_sha(sha256: str) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE sha256 = ?", (sha256,)
        ).fetchone()
        return dict(row) if row else None


def get_by_invoice_no(
    invoice_no: str,
    vendor: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Find an existing row with the same invoice number (optionally same vendor)."""
    key = (invoice_no or "").strip()
    if not key:
        return None
    with connect() as conn:
        if vendor and vendor.strip():
            row = conn.execute(
                """
                SELECT * FROM documents
                WHERE lower(trim(invoice_no)) = lower(trim(?))
                  AND lower(trim(coalesce(vendor, ''))) = lower(trim(?))
                ORDER BY id DESC LIMIT 1
                """,
                (key, vendor.strip()),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT * FROM documents
                WHERE lower(trim(invoice_no)) = lower(trim(?))
                ORDER BY id DESC LIMIT 1
                """,
                (key,),
            ).fetchone()
        return dict(row) if row else None


def delete_by_sha(sha256: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM documents WHERE sha256 = ?", (sha256,))


def delete_document(doc_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        return cur.rowcount > 0


def clear_all() -> int:
    """Wipe invoices + vendor rules. Returns how many invoice rows went away."""
    with connect() as conn:
        cur = conn.execute("SELECT COUNT(*) AS n FROM documents")
        n = int(cur.fetchone()["n"])
        conn.execute("DELETE FROM documents")
        conn.execute("DELETE FROM vendor_rules")
        return n


def get_document(doc_id: int) -> Optional[dict[str, Any]]:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()
        return dict(row) if row else None


def list_documents(
    status: Optional[str] = None,
    category: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if category:
        clauses.append("category = ?")
        params.append(category)
    if date_from:
        clauses.append("issue_date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("issue_date <= ?")
        params.append(date_to)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT * FROM documents {where} ORDER BY created_at DESC, id DESC"
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def insert_document(fields: dict[str, Any]) -> int:
    cols = ", ".join(fields.keys())
    placeholders = ", ".join("?" for _ in fields)
    with connect() as conn:
        cur = conn.execute(
            f"INSERT INTO documents ({cols}) VALUES ({placeholders})",
            tuple(fields.values()),
        )
        return int(cur.lastrowid)


def update_document(doc_id: int, fields: dict[str, Any]) -> Optional[dict[str, Any]]:
    if not fields:
        return get_document(doc_id)
    sets = ", ".join(f"{k} = ?" for k in fields)
    with connect() as conn:
        conn.execute(
            f"UPDATE documents SET {sets} WHERE id = ?",
            (*fields.values(), doc_id),
        )
    return get_document(doc_id)


def save_document(fields: dict[str, Any], replace_id: Optional[int] = None) -> int:
    """Insert, or update replace_id in place (keeps the same document id)."""
    if replace_id is not None:
        # sha256 is UNIQUE — if another row holds this sha, drop it first
        sha = fields.get("sha256")
        if sha:
            with connect() as conn:
                conn.execute(
                    "DELETE FROM documents WHERE sha256 = ? AND id != ?",
                    (sha, replace_id),
                )
        update_document(replace_id, fields)
        return replace_id
    return insert_document(fields)


def get_vendor_category(vendor_normalized: str) -> Optional[str]:
    with connect() as conn:
        row = conn.execute(
            "SELECT category FROM vendor_rules WHERE vendor_normalized = ?",
            (vendor_normalized,),
        ).fetchone()
        return row["category"] if row else None


def upsert_vendor_rule(vendor_normalized: str, category: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO vendor_rules (vendor_normalized, category)
            VALUES (?, ?)
            ON CONFLICT(vendor_normalized) DO UPDATE SET category = excluded.category
            """,
            (vendor_normalized, category),
        )


init_db()
