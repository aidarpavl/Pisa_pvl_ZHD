"""Деректер қоры: SQLite (әдепкі) немесе PostgreSQL (DATABASE_URL берілсе).

Streamlit Cloud-та файлдық жүйе уақытша, сондықтан тұрақты жұмыс үшін
secrets.toml ішіне DATABASE_URL (Supabase / Neon PostgreSQL) қойыңыз.
"""
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime

_lock = threading.Lock()


def _database_url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        try:
            import streamlit as st
            url = st.secrets.get("DATABASE_URL")
        except Exception:
            url = None
    return url


DB_URL = _database_url()
IS_PG = bool(DB_URL) and DB_URL.startswith(("postgres://", "postgresql://"))
SQLITE_PATH = os.environ.get("SQLITE_PATH", "pisa_platform.db")


def _connect():
    if IS_PG:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        return conn
    conn = sqlite3.connect(SQLITE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_conn():
    with _lock:
        conn = _connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _q(sql):
    return sql.replace("?", "%s") if IS_PG else sql


def _row(r):
    return dict(r) if r is not None else None


def query(sql, params=()):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(_q(sql), params)
        return [_row(r) for r in cur.fetchall()]


def query_one(sql, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql, params=()):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(_q(sql), params)
        return cur.rowcount


def insert(sql, params=()):
    """INSERT ... орындап, жаңа жолдың id-ін қайтарады."""
    sql = sql.rstrip().rstrip(";") + " RETURNING id"
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(_q(sql), params)
        row = cur.fetchone()
        return dict(row)["id"]


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


PK = "SERIAL PRIMARY KEY" if IS_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS users (
    id {PK},
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS courses (
    id {PK},
    title TEXT NOT NULL,
    description TEXT,
    owner_id INTEGER,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS modules (
    id {PK},
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    position INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS lessons (
    id {PK},
    module_id INTEGER NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    position INTEGER DEFAULT 0,
    stepik_lesson_id INTEGER
);
CREATE TABLE IF NOT EXISTS steps (
    id {PK},
    lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    position INTEGER DEFAULT 0,
    type TEXT NOT NULL,
    content TEXT NOT NULL,
    points REAL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS classes (
    id {PK},
    name TEXT NOT NULL,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    teacher_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    join_code TEXT UNIQUE NOT NULL,
    is_open INTEGER DEFAULT 1,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS enrollments (
    id {PK},
    class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    joined_at TEXT,
    UNIQUE (class_id, student_id)
);
CREATE TABLE IF NOT EXISTS submissions (
    id {PK},
    step_id INTEGER NOT NULL REFERENCES steps(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    class_id INTEGER REFERENCES classes(id) ON DELETE CASCADE,
    answer TEXT,
    score REAL DEFAULT 0,
    max_score REAL DEFAULT 0,
    status TEXT,
    teacher_comment TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_sub_student ON submissions(student_id, step_id);
"""


def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        for stmt in SCHEMA.split(";"):
            if stmt.strip():
                cur.execute(stmt)


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False)


def loads(s, default=None):
    try:
        return json.loads(s) if s else default
    except Exception:
        return default
