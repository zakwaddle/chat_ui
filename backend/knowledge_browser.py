from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from .database import connect
    from .memory_layers import list_future_memory_layers
    from .sqlite_explorer import list_available_databases
except ImportError:
    from database import connect
    from memory_layers import list_future_memory_layers
    from sqlite_explorer import list_available_databases


def build_knowledge_browser(
    database_path: Path | None = None,
    knowledge_sources: tuple[dict[str, str], ...] | list[dict[str, str]] = (),
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    databases = list_available_databases(database_path, knowledge_sources)
    sections = [
        build_conversation_section(),
        build_memory_section(),
        build_database_section(databases),
        build_archive_section(databases),
        build_tool_results_section(tools or []),
    ]

    return {
        "sections": sections,
        "total_items": sum(section["count"] for section in sections),
    }


def build_conversation_section(limit: int = 25) -> dict[str, Any]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT
                conversations.id,
                conversations.title,
                conversations.created_at,
                COUNT(messages.id) AS message_count,
                MAX(messages.created_at) AS latest_message_at,
                (
                    SELECT content
                    FROM messages
                    WHERE messages.conversation_id = conversations.id
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                ) AS latest_message
            FROM conversations
            LEFT JOIN messages ON messages.conversation_id = conversations.id
            GROUP BY conversations.id
            ORDER BY COALESCE(latest_message_at, conversations.created_at) DESC, conversations.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    items = [
        {
            "id": f"conversation:{row['id']}",
            "kind": "conversation",
            "title": row["title"],
            "subtitle": f"{row['message_count']} messages",
            "preview": row["latest_message"] or "No messages yet.",
            "conversation_id": row["id"],
            "created_at": row["created_at"],
            "updated_at": row["latest_message_at"] or row["created_at"],
        }
        for row in rows
    ]

    return {
        "id": "conversations",
        "title": "Conversations",
        "description": "Recent chat threads and their latest message.",
        "count": len(items),
        "items": items,
    }


def build_memory_section() -> dict[str, Any]:
    layers = list_future_memory_layers()
    items = []
    with connect() as connection:
        for layer in layers:
            table_name = layer["table_name"]
            row = connection.execute(f"SELECT COUNT(*) AS count FROM {quote_identifier(table_name)}").fetchone()
            latest = connection.execute(
                f"SELECT * FROM {quote_identifier(table_name)} ORDER BY created_at DESC, id DESC LIMIT 1"
            ).fetchone()
            latest_content = latest_preview(dict(latest)) if latest else "No records yet."
            count = int(row["count"])
            items.append(
                {
                    "id": f"memory:{table_name}",
                    "kind": "memory_table",
                    "title": layer["name"],
                    "subtitle": f"{count} records",
                    "preview": latest_content,
                    "table_name": table_name,
                    "row_count": count,
                    "description": layer["purpose"],
                }
            )

    return {
        "id": "memories",
        "title": "Memories",
        "description": "Structured memory tables in the active chat database.",
        "count": len(items),
        "items": items,
    }


def build_database_section(databases: list[dict[str, Any]]) -> dict[str, Any]:
    items = [
        {
            "id": f"database:{database['id']}",
            "kind": "sqlite_database",
            "title": database["name"],
            "subtitle": f"{database['id']} · {database['type']}",
            "preview": database["description"],
            "source_id": database["id"],
            "path": database["path"],
            "exists": database["exists"],
            "size_bytes": database["size_bytes"],
            "permission": database["permission"],
        }
        for database in databases
    ]

    return {
        "id": "sqlite_databases",
        "title": "SQLite Databases",
        "description": "Chat, registered, and discovered SQLite sources.",
        "count": len(items),
        "items": items,
    }


def build_archive_section(databases: list[dict[str, Any]]) -> dict[str, Any]:
    archive_items = []
    for database in databases:
        text = " ".join(
            str(database.get(key) or "")
            for key in ("id", "name", "description", "path")
        ).lower()
        if "archive" not in text and database["type"] != "external":
            continue
        archive_items.append(
            {
                "id": f"archive:{database['id']}",
                "kind": "archive_database",
                "title": database["name"],
                "subtitle": database["id"],
                "preview": database["description"],
                "source_id": database["id"],
                "path": database["path"],
                "exists": database["exists"],
            }
        )

    return {
        "id": "archives",
        "title": "Imported Archives",
        "description": "Registered or discovered archive-like databases.",
        "count": len(archive_items),
        "items": archive_items,
    }


def build_tool_results_section(tools: list[dict[str, Any]], limit: int = 25) -> dict[str, Any]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, conversation_id, content, created_at, token_estimate
            FROM messages
            WHERE role = 'tool'
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    recent_results = [
        {
            "id": f"tool_result:{row['id']}",
            "kind": "tool_result",
            "title": tool_result_title(row["content"], row["id"]),
            "subtitle": f"conversation {row['conversation_id']}",
            "preview": row["content"],
            "message_id": row["id"],
            "conversation_id": row["conversation_id"],
            "created_at": row["created_at"],
            "token_estimate": row["token_estimate"],
        }
        for row in rows
    ]
    available_tools = [
        {
            "id": f"tool:{tool['name']}",
            "kind": "available_tool",
            "title": tool["name"],
            "subtitle": tool["permission"],
            "preview": tool["description"],
            "destructive": tool["destructive"],
        }
        for tool in tools
    ]

    return {
        "id": "tool_results",
        "title": "Tool Results",
        "description": "Recent persisted tool messages and currently registered tools.",
        "count": len(recent_results) + len(available_tools),
        "items": [*recent_results, *available_tools],
    }


def latest_preview(row: dict[str, Any]) -> str:
    for key in ("content", "summary", "label", "title"):
        value = row.get(key)
        if value:
            return str(value)

    metadata = row.get("metadata")
    if metadata:
        return str(metadata)

    return json.dumps(row, default=str)


def tool_result_title(content: str, message_id: int) -> str:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, dict):
        tool_name = parsed.get("tool_name") or parsed.get("name")
        if tool_name:
            return str(tool_name)

    return f"Tool message {message_id}"


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
