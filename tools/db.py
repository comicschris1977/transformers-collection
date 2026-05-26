"""
SQLite database layer for the Transformers collection.
"""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "collection.db"

STATUS_MAP = {
    "yes": "owned",
    "want": "want",
    "pordered": "preordered",
    "ordered": "ordered",
}

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS figures (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    line        TEXT,
    status      TEXT NOT NULL DEFAULT 'want',
    rank        INTEGER,
    retailer    TEXT,
    notes       TEXT,
    combiner    TEXT,
    is_wrecker  INTEGER NOT NULL DEFAULT 0,
    image_url   TEXT,
    added_at    TEXT NOT NULL DEFAULT (date('now'))
);
"""

MIGRATE_SQL = [
    "ALTER TABLE figures ADD COLUMN image_url TEXT",
    "ALTER TABLE figures ADD COLUMN ebay_avg_price REAL",
    "ALTER TABLE figures ADD COLUMN ebay_sold_count INTEGER",
    "ALTER TABLE figures ADD COLUMN ebay_updated_at TEXT",
]


def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with _conn() as con:
        con.execute(CREATE_SQL)
        for sql in MIGRATE_SQL:
            try:
                con.execute(sql)
            except sqlite3.OperationalError:
                pass  # column already exists


def _row_to_dict(row):
    if row is None:
        return None
    d = dict(row)
    d["is_wrecker"] = bool(d["is_wrecker"])
    return d


# ── Read ────────────────────────────────────────────────────────────────────

def get_figure(figure_id: int):
    with _conn() as con:
        row = con.execute("SELECT * FROM figures WHERE id = ?", (figure_id,)).fetchone()
    return _row_to_dict(row)


def list_figures(status=None, line=None, combiner=None, wrecker=None, min_rank=None, max_rank=None):
    clauses, params = [], []
    if status:
        clauses.append("LOWER(status) = LOWER(?)")
        params.append(status)
    if line:
        clauses.append("LOWER(line) LIKE LOWER(?)")
        params.append(f"%{line}%")
    if combiner:
        clauses.append("LOWER(combiner) LIKE LOWER(?)")
        params.append(f"%{combiner}%")
    if wrecker is not None:
        clauses.append("is_wrecker = ?")
        params.append(1 if wrecker else 0)
    if min_rank is not None:
        clauses.append("rank >= ?")
        params.append(min_rank)
    if max_rank is not None:
        clauses.append("rank <= ?")
        params.append(max_rank)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM figures {where} ORDER BY name COLLATE NOCASE"
    with _conn() as con:
        rows = con.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def search_figures(query: str):
    q = f"%{query}%"
    sql = """
        SELECT * FROM figures
        WHERE name LIKE ? OR line LIKE ? OR combiner LIKE ? OR notes LIKE ?
        ORDER BY name COLLATE NOCASE
    """
    with _conn() as con:
        rows = con.execute(sql, (q, q, q, q)).fetchall()
    return [_row_to_dict(r) for r in rows]


# ── Write ───────────────────────────────────────────────────────────────────

def add_figure(name, line=None, status="want", rank=None, retailer=None,
               notes=None, combiner=None, is_wrecker=False):
    sql = """
        INSERT INTO figures (name, line, status, rank, retailer, notes, combiner, is_wrecker)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    with _conn() as con:
        cur = con.execute(sql, (name, line, status, rank, retailer, notes, combiner, int(is_wrecker)))
        return cur.lastrowid


def edit_figure(figure_id: int, *, clear_fields=None, **kwargs):
    """
    Update figure fields.

    - Pass field=value to set a value.
    - By default, value=None means "leave alone" (so callers can pass
      partial kwargs safely).
    - Pass clear_fields=["notes", "retailer"] to explicitly NULL out columns.
    """
    allowed = {"name", "line", "status", "rank", "retailer", "notes", "combiner", "is_wrecker", "image_url"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    for field in (clear_fields or ()):
        if field in allowed:
            updates[field] = None
    if "is_wrecker" in updates and updates["is_wrecker"] is not None:
        updates["is_wrecker"] = int(updates["is_wrecker"])
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    sql = f"UPDATE figures SET {set_clause} WHERE id = ?"
    with _conn() as con:
        cur = con.execute(sql, (*updates.values(), figure_id))
        return cur.rowcount > 0


def delete_figure(figure_id: int):
    with _conn() as con:
        cur = con.execute("DELETE FROM figures WHERE id = ?", (figure_id,))
        return cur.rowcount > 0


def set_image_url(figure_id: int, url: str):
    with _conn() as con:
        con.execute("UPDATE figures SET image_url = ? WHERE id = ?", (url, figure_id))


def stats():
    sql = """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status='owned' THEN 1 ELSE 0 END) as owned,
            SUM(CASE WHEN status='want' THEN 1 ELSE 0 END) as want,
            SUM(CASE WHEN status='preordered' THEN 1 ELSE 0 END) as preordered,
            SUM(CASE WHEN status='ordered' THEN 1 ELSE 0 END) as ordered,
            SUM(is_wrecker) as wreckers,
            ROUND(AVG(CASE WHEN rank IS NOT NULL THEN rank END), 1) as avg_rank
        FROM figures
    """
    with _conn() as con:
        row = con.execute(sql).fetchone()
    return dict(row)
