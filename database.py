"""SQLite persistence for drafts and an audit trail."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator
from config import load_settings


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(load_settings().database_path, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connection() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subreddit TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                reddit_url TEXT,
                created_at TEXT NOT NULL,
                published_at TEXT
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                details TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)


def create_draft(subreddit: str, title: str, body: str) -> int:
    with connection() as db:
        cur = db.execute(
            "INSERT INTO drafts(subreddit,title,body,created_at) VALUES(?,?,?,?)",
            (subreddit, title, body, now_iso()),
        )
        draft_id = int(cur.lastrowid)
        db.execute(
            "INSERT INTO audit_log(action,details,created_at) VALUES(?,?,?)",
            ("draft_created", f"draft_id={draft_id}; subreddit={subreddit}", now_iso()),
        )
        return draft_id


def get_draft(draft_id: int):
    with connection() as db:
        row = db.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
        return dict(row) if row else None


def list_drafts(limit: int = 20):
    with connection() as db:
        rows = db.execute(
            "SELECT * FROM drafts ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]


def claim_draft(draft_id: int) -> bool:
    """Atomically reserve a draft so repeated button clicks cannot double-submit."""
    with connection() as db:
        cur = db.execute(
            "UPDATE drafts SET status='publishing' WHERE id=? AND status='draft'",
            (draft_id,),
        )
        if cur.rowcount == 1:
            db.execute(
                "INSERT INTO audit_log(action,details,created_at) VALUES(?,?,?)",
                ("publishing", f"draft_id={draft_id}", now_iso()),
            )
            return True
        return False


def mark_published(draft_id: int, url: str) -> None:
    with connection() as db:
        cur = db.execute(
            """UPDATE drafts SET status='published', reddit_url=?, published_at=?
               WHERE id=? AND status='publishing'""",
            (url, now_iso(), draft_id),
        )
        if cur.rowcount != 1:
            raise ValueError("Draft is missing or is no longer publishable")
        db.execute(
            "INSERT INTO audit_log(action,details,created_at) VALUES(?,?,?)",
            ("published", f"draft_id={draft_id}; url={url}", now_iso()),
        )


def mark_failed(draft_id: int, reason: str) -> None:
    with connection() as db:
        db.execute(
            "UPDATE drafts SET status='failed' WHERE id=? AND status='publishing'",
            (draft_id,),
        )
        db.execute(
            "INSERT INTO audit_log(action,details,created_at) VALUES(?,?,?)",
            ("publish_failed", f"draft_id={draft_id}; reason={reason[:300]}", now_iso()),
        )
