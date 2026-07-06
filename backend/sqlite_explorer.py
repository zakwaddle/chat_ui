from __future__ import annotations

import sqlite3
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote

try:
    from .database import DEFAULT_DATABASE_PATH
except ImportError:
    from database import DEFAULT_DATABASE_PATH


SQLITE_EXTENSIONS = {".db", ".sqlite", ".sqlite3"}
MAX_PREVIEW_LIMIT = 100
MAX_QUERY_LIMIT = 200
WRITE_SQL_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|ATTACH|DETACH|REPLACE|CREATE|VACUUM|REINDEX|ANALYZE)\b",
    re.IGNORECASE,
)
PRAGMA_PATTERN = re.compile(r"\bPRAGMA\b", re.IGNORECASE)


class SQLiteExplorerError(ValueError):
    pass


def list_available_databases(config_database_path: Path | None = None) -> list[dict[str, Any]]:
    candidates: dict[Path, dict[str, Any]] = {}

    active_path = (config_database_path or DEFAULT_DATABASE_PATH).expanduser().resolve()
    candidates[active_path] = {
        "name": active_path.name,
        "path": str(active_path),
        "description": "Active chat database",
        "exists": active_path.exists(),
        "size_bytes": active_path.stat().st_size if active_path.exists() else 0,
    }

    for directory in database_search_directories(active_path):
        if not directory.exists() or not directory.is_dir():
            continue
        for path in directory.iterdir():
            if path.suffix.lower() not in SQLITE_EXTENSIONS:
                continue
            resolved_path = path.resolve()
            candidates.setdefault(
                resolved_path,
                {
                    "name": resolved_path.name,
                    "path": str(resolved_path),
                    "description": "SQLite database",
                    "exists": resolved_path.exists(),
                    "size_bytes": resolved_path.stat().st_size if resolved_path.exists() else 0,
                },
            )

    return sorted(candidates.values(), key=lambda database: (not database["exists"], database["name"].lower()))


def inspect_database(database_path: str | Path) -> dict[str, Any]:
    path = normalize_database_path(database_path)
    with read_only_connection(path) as connection:
        tables = list_tables_for_connection(connection)

    return {"database": database_metadata(path), "tables": tables}


def describe_table(database_path: str | Path, table_name: str) -> dict[str, Any]:
    path = normalize_database_path(database_path)
    with read_only_connection(path) as connection:
        ensure_table_exists(connection, table_name)
        columns = [
            {
                "cid": row["cid"],
                "name": row["name"],
                "type": row["type"] or "",
                "not_null": bool(row["notnull"]),
                "default_value": row["dflt_value"],
                "primary_key": bool(row["pk"]),
            }
            for row in connection.execute(f"PRAGMA table_info({quote_identifier(table_name)})").fetchall()
        ]
        row_count = count_rows(connection, table_name)

    return {"database": database_metadata(path), "table": table_name, "columns": columns, "row_count": row_count}


def preview_rows(database_path: str | Path, table_name: str, limit: int = 25) -> dict[str, Any]:
    path = normalize_database_path(database_path)
    clean_limit = clamp_preview_limit(limit)
    with read_only_connection(path) as connection:
        ensure_table_exists(connection, table_name)
        columns = [row["name"] for row in connection.execute(f"PRAGMA table_info({quote_identifier(table_name)})")]
        rows = [
            {key: serialize_cell(value) for key, value in dict(row).items()}
            for row in connection.execute(f"SELECT * FROM {quote_identifier(table_name)} LIMIT ?", (clean_limit,)).fetchall()
        ]
        row_count = count_rows(connection, table_name)

    return {
        "database": database_metadata(path),
        "table": table_name,
        "columns": columns,
        "rows": rows,
        "row_count": row_count,
        "limit": clean_limit,
    }


def list_tables(database_path: str | Path) -> dict[str, Any]:
    return inspect_database(database_path)


def search_table(
    database_path: str | Path,
    table_name: str,
    query: str,
    columns: list[str] | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    path = normalize_database_path(database_path)
    search_text = str(query or "").strip()
    if not search_text:
        raise SQLiteExplorerError("search query is required")

    clean_limit = clamp_preview_limit(limit)
    with read_only_connection(path) as connection:
        ensure_table_exists(connection, table_name)
        column_info = table_columns(connection, table_name)
        available_columns = [column["name"] for column in column_info]
        searchable_columns = normalize_search_columns(column_info, columns)
        if not searchable_columns:
            raise SQLiteExplorerError(f"table has no searchable columns: {table_name}")

        like_value = f"%{escape_like_value(search_text)}%"
        where_clause = " OR ".join(f"{quote_identifier(column)} LIKE ? ESCAPE '\\'" for column in searchable_columns)
        rows = [
            {key: serialize_cell(value) for key, value in dict(row).items()}
            for row in connection.execute(
                f"SELECT * FROM {quote_identifier(table_name)} WHERE {where_clause} LIMIT ?",
                [*(like_value for _column in searchable_columns), clean_limit],
            ).fetchall()
        ]

    return {
        "database": database_metadata(path),
        "table": table_name,
        "query": search_text,
        "columns": available_columns,
        "searched_columns": searchable_columns,
        "rows": rows,
        "limit": clean_limit,
    }


def run_read_only_query(database_path: str | Path, sql: str, params: list[Any] | None = None, limit: int = 100) -> dict[str, Any]:
    path = normalize_database_path(database_path)
    statement = validate_read_only_sql(sql)
    clean_limit = clamp_query_limit(limit)
    query_params = params if isinstance(params, list) else []

    with read_only_connection(path) as connection:
        connection.set_authorizer(read_only_authorizer)
        try:
            cursor = connection.execute(statement, query_params)
            rows = cursor.fetchmany(clean_limit)
        finally:
            connection.set_authorizer(None)

    columns = [description[0] for description in cursor.description or []]
    return {
        "database": database_metadata(path),
        "sql": statement,
        "columns": columns,
        "rows": [{key: serialize_cell(value) for key, value in dict(row).items()} for row in rows],
        "limit": clean_limit,
        "truncated": len(rows) >= clean_limit,
    }


def normalize_database_path(database_path: str | Path) -> Path:
    raw_path = Path(str(database_path or "").strip()).expanduser()
    if not str(raw_path):
        raise SQLiteExplorerError("database path is required")

    path = raw_path.resolve()
    if not path.exists():
        raise SQLiteExplorerError(f"database not found: {path}")
    if not path.is_file():
        raise SQLiteExplorerError(f"database path is not a file: {path}")

    return path


@contextmanager
def read_only_connection(path: Path) -> Iterator[sqlite3.Connection]:
    uri = f"file:{quote(str(path))}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        yield connection
    except sqlite3.DatabaseError as error:
        raise SQLiteExplorerError(f"unable to inspect SQLite database: {error}") from error
    finally:
        try:
            connection.close()
        except UnboundLocalError:
            pass


def list_tables_for_connection(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT name, type, sql
        FROM sqlite_schema
        WHERE type IN ('table', 'view')
          AND name NOT LIKE 'sqlite_%'
        ORDER BY type, name
        """
    ).fetchall()

    return [
        {
            "name": row["name"],
            "type": row["type"],
            "row_count": count_rows(connection, row["name"]) if row["type"] == "table" else None,
            "sql": row["sql"] or "",
        }
        for row in rows
    ]


def ensure_table_exists(connection: sqlite3.Connection, table_name: str) -> None:
    row = connection.execute(
        """
        SELECT name
        FROM sqlite_schema
        WHERE type IN ('table', 'view')
          AND name = ?
        """,
        (table_name,),
    ).fetchone()
    if row is None:
        raise SQLiteExplorerError(f"table not found: {table_name}")


def table_columns(connection: sqlite3.Connection, table_name: str) -> list[dict[str, Any]]:
    return [
        {
            "cid": row["cid"],
            "name": row["name"],
            "type": row["type"] or "",
            "not_null": bool(row["notnull"]),
            "default_value": row["dflt_value"],
            "primary_key": bool(row["pk"]),
        }
        for row in connection.execute(f"PRAGMA table_info({quote_identifier(table_name)})").fetchall()
    ]


def count_rows(connection: sqlite3.Connection, table_name: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) AS count FROM {quote_identifier(table_name)}").fetchone()
    return int(row["count"])


def quote_identifier(identifier: str) -> str:
    if not identifier:
        raise SQLiteExplorerError("identifier is required")
    return '"' + identifier.replace('"', '""') + '"'


def clamp_preview_limit(limit: int) -> int:
    try:
        parsed_limit = int(limit)
    except (TypeError, ValueError):
        parsed_limit = 25
    return max(1, min(MAX_PREVIEW_LIMIT, parsed_limit))


def clamp_query_limit(limit: int) -> int:
    try:
        parsed_limit = int(limit)
    except (TypeError, ValueError):
        parsed_limit = 100
    return max(1, min(MAX_QUERY_LIMIT, parsed_limit))


def normalize_search_columns(column_info: list[dict[str, Any]], columns: list[str] | None = None) -> list[str]:
    available = {column["name"]: column for column in column_info}
    if columns:
        requested_columns = [str(column).strip() for column in columns if str(column).strip()]
        unknown_columns = [column for column in requested_columns if column not in available]
        if unknown_columns:
            raise SQLiteExplorerError(f"unknown search columns: {', '.join(unknown_columns)}")
        return requested_columns

    text_columns = [
        column["name"]
        for column in column_info
        if any(token in column["type"].upper() for token in ("TEXT", "CHAR", "CLOB", "VARCHAR"))
    ]
    return text_columns or [column["name"] for column in column_info if "BLOB" not in column["type"].upper()]


def escape_like_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def validate_read_only_sql(sql: str) -> str:
    statement = str(sql or "").strip()
    if not statement:
        raise SQLiteExplorerError("SQL query is required")
    if "\x00" in statement:
        raise SQLiteExplorerError("SQL query contains an invalid null byte")
    if WRITE_SQL_PATTERN.search(statement):
        raise SQLiteExplorerError("SQL query must be read-only")
    if PRAGMA_PATTERN.search(statement):
        raise SQLiteExplorerError("PRAGMA statements are not allowed through this tool")
    if not re.match(r"^\s*(SELECT|WITH)\b", statement, re.IGNORECASE):
        raise SQLiteExplorerError("SQL query must begin with SELECT or WITH")
    if has_multiple_sql_statements(statement):
        raise SQLiteExplorerError("SQL query must contain exactly one statement")

    return statement.rstrip(";").strip()


def has_multiple_sql_statements(statement: str) -> bool:
    in_single_quote = False
    in_double_quote = False
    in_bracket_quote = False
    in_line_comment = False
    in_block_comment = False
    semicolon_count = 0
    index = 0

    while index < len(statement):
        char = statement[index]
        next_char = statement[index + 1] if index + 1 < len(statement) else ""

        if in_line_comment:
            if char in "\r\n":
                in_line_comment = False
            index += 1
            continue
        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
                index += 2
                continue
            index += 1
            continue
        if in_single_quote:
            if char == "'" and next_char == "'":
                index += 2
                continue
            if char == "'":
                in_single_quote = False
            index += 1
            continue
        if in_double_quote:
            if char == '"' and next_char == '"':
                index += 2
                continue
            if char == '"':
                in_double_quote = False
            index += 1
            continue
        if in_bracket_quote:
            if char == "]":
                in_bracket_quote = False
            index += 1
            continue

        if char == "-" and next_char == "-":
            in_line_comment = True
            index += 2
            continue
        if char == "/" and next_char == "*":
            in_block_comment = True
            index += 2
            continue
        if char == "'":
            in_single_quote = True
        elif char == '"':
            in_double_quote = True
        elif char == "[":
            in_bracket_quote = True
        elif char == ";":
            semicolon_count += 1
            if statement[index + 1 :].strip():
                return True
        index += 1

    return semicolon_count > 1


def read_only_authorizer(action_code: int, _arg1: str | None, _arg2: str | None, _database: str | None, _source: str | None) -> int:
    denied_actions = {
        sqlite3.SQLITE_INSERT,
        sqlite3.SQLITE_UPDATE,
        sqlite3.SQLITE_DELETE,
        sqlite3.SQLITE_ALTER_TABLE,
        sqlite3.SQLITE_CREATE_INDEX,
        sqlite3.SQLITE_CREATE_TABLE,
        sqlite3.SQLITE_CREATE_TEMP_INDEX,
        sqlite3.SQLITE_CREATE_TEMP_TABLE,
        sqlite3.SQLITE_CREATE_TEMP_TRIGGER,
        sqlite3.SQLITE_CREATE_TEMP_VIEW,
        sqlite3.SQLITE_CREATE_TRIGGER,
        sqlite3.SQLITE_CREATE_VIEW,
        sqlite3.SQLITE_DROP_INDEX,
        sqlite3.SQLITE_DROP_TABLE,
        sqlite3.SQLITE_DROP_TEMP_INDEX,
        sqlite3.SQLITE_DROP_TEMP_TABLE,
        sqlite3.SQLITE_DROP_TEMP_TRIGGER,
        sqlite3.SQLITE_DROP_TEMP_VIEW,
        sqlite3.SQLITE_DROP_TRIGGER,
        sqlite3.SQLITE_DROP_VIEW,
        sqlite3.SQLITE_ATTACH,
        sqlite3.SQLITE_DETACH,
        sqlite3.SQLITE_PRAGMA,
    }
    return sqlite3.SQLITE_DENY if action_code in denied_actions else sqlite3.SQLITE_OK


def serialize_cell(value: Any) -> Any:
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    return value


def database_metadata(path: Path) -> dict[str, Any]:
    return {
        "name": path.name,
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
    }


def database_search_directories(active_path: Path) -> list[Path]:
    return [
        active_path.parent,
        DEFAULT_DATABASE_PATH.parent,
        Path.cwd(),
    ]
