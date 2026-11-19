"""SQLite-compatible database interface backed by Neon PostgreSQL when configured.

Existing SQL uses qmark placeholders and SQLite row access. This module preserves
that interface without changing prediction calculations.
"""
import os
import sqlite3
from pathlib import Path

DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
USING_NEON = bool(DATABASE_URL)


class HybridRow(dict):
    """Supports row['column'], dict(row) and row[0]."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class CursorAdapter:
    def __init__(self, cursor):
        self.cursor = cursor

    def fetchone(self):
        row = self.cursor.fetchone()
        return HybridRow(row) if row is not None else None

    def fetchall(self):
        return [HybridRow(r) for r in self.cursor.fetchall()]

    def __iter__(self):
        return (HybridRow(r) for r in self.cursor)


class NeonConnection:
    def __init__(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError('Neon requires psycopg[binary] in backend/requirements.txt') from exc
        self.conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=12)

    def execute(self, query, params=()):
        # All application queries use '?' for parameters, never literal '?' SQL operators.
        cursor = self.conn.execute(query.replace('?', '%s'), params)
        return CursorAdapter(cursor)

    def executescript(self, script):
        for statement in script.split(';'):
            if statement.strip():
                self.conn.execute(statement)

    def __enter__(self):
        return self

    def __exit__(self, typ, value, traceback):
        try:
            if typ is None:
                self.conn.commit()
            else:
                self.conn.rollback()
        finally:
            self.conn.close()
        return False


def connect(sqlite_path):
    if USING_NEON:
        return NeonConnection()
    path = Path(sqlite_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn
