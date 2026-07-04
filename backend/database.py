from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE_PATH = BASE_DIR / "data" / "associative_chat.sqlite3"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def estimate_tokens(content: str) -> int:
    return max(1, (len(content.strip()) + 3) // 4)


def get_database_path() -> Path:
    return Path(os.getenv("DATABASE_PATH", DEFAULT_DATABASE_PATH))


@contextmanager
def connect(database_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = database_path or get_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db(database_path: Path | None = None) -> None:
    with connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant', 'tool')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                token_estimate INTEGER NOT NULL,
                embedding_id INTEGER,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
                FOREIGN KEY (embedding_id) REFERENCES embeddings(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL UNIQUE,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                vector TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
                ON messages (conversation_id, created_at, id);
            """
        )


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def create_conversation(title: str | None = None) -> dict[str, Any]:
    created_at = utc_now()
    clean_title = title.strip() if title else "New conversation"

    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO conversations (title, created_at) VALUES (?, ?)",
            (clean_title, created_at),
        )
        row = connection.execute(
            "SELECT id, title, created_at FROM conversations WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()

    return row_to_dict(row)


def list_conversations() -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT
                conversations.id,
                conversations.title,
                conversations.created_at,
                COUNT(messages.id) AS message_count
            FROM conversations
            LEFT JOIN messages ON messages.conversation_id = conversations.id
            GROUP BY conversations.id
            ORDER BY conversations.created_at DESC, conversations.id DESC
            """
        ).fetchall()

    return [row_to_dict(row) for row in rows]


def get_conversation(conversation_id: int) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT id, title, created_at FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()

    return row_to_dict(row) if row else None


def create_message(conversation_id: int, role: str, content: str) -> dict[str, Any]:
    if get_conversation(conversation_id) is None:
        raise ValueError("conversation not found")

    created_at = utc_now()
    token_estimate = estimate_tokens(content)

    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO messages
                (conversation_id, role, content, created_at, token_estimate, embedding_id)
            VALUES (?, ?, ?, ?, ?, NULL)
            """,
            (conversation_id, role, content, created_at, token_estimate),
        )
        row = connection.execute(
            """
            SELECT id, conversation_id, role, content, created_at, token_estimate, embedding_id
            FROM messages
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()

    return row_to_dict(row)


def list_messages(conversation_id: int) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, conversation_id, role, content, created_at, token_estimate, embedding_id
            FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (conversation_id,),
        ).fetchall()

    return [row_to_dict(row) for row in rows]


def create_embedding(
    message_id: int,
    provider: str,
    model: str,
    vector: str,
) -> dict[str, Any]:
    created_at = utc_now()

    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO embeddings (message_id, provider, model, vector, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (message_id, provider, model, vector, created_at),
        )
        embedding_id = cursor.lastrowid
        connection.execute(
            "UPDATE messages SET embedding_id = ? WHERE id = ?",
            (embedding_id, message_id),
        )
        row = connection.execute(
            "SELECT id, message_id, provider, model, vector, created_at FROM embeddings WHERE id = ?",
            (embedding_id,),
        ).fetchone()

    return row_to_dict(row)
