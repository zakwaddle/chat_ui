from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from typing import Any

try:
    from .database import get_message
    from .database import list_messages_after
    from .database import list_messages_before
    from .database import get_database_path
    from .sqlite_explorer import SQLiteExplorerError
    from .sqlite_explorer import describe_table
    from .sqlite_explorer import list_available_databases
    from .sqlite_explorer import list_tables
    from .sqlite_explorer import preview_rows
    from .sqlite_explorer import resolve_database_source
    from .sqlite_explorer import run_read_only_query
    from .sqlite_explorer import search_database
    from .sqlite_explorer import search_table
except ImportError:
    from database import get_message
    from database import list_messages_after
    from database import list_messages_before
    from database import get_database_path
    from sqlite_explorer import SQLiteExplorerError
    from sqlite_explorer import describe_table
    from sqlite_explorer import list_available_databases
    from sqlite_explorer import list_tables
    from sqlite_explorer import preview_rows
    from sqlite_explorer import resolve_database_source
    from sqlite_explorer import run_read_only_query
    from sqlite_explorer import search_database
    from sqlite_explorer import search_table


CONTEXT_TOOL_NAME = "get_context_around_message"
KNOWLEDGE_SOURCES_TOOL_NAME = "list_knowledge_sources"
SQLITE_LIST_TABLES_TOOL_NAME = "list_tables"
SQLITE_DESCRIBE_TABLE_TOOL_NAME = "describe_table"
SQLITE_SAMPLE_ROWS_TOOL_NAME = "sample_rows"
SQLITE_SEARCH_TABLE_TOOL_NAME = "search_table"
SQLITE_SEARCH_DATABASE_TOOL_NAME = "search_database"
SQLITE_READ_ONLY_QUERY_TOOL_NAME = "run_read_only_query"


@dataclass(frozen=True)
class ToolMetadata:
    name: str
    description: str
    permission: str
    destructive: bool = False


@dataclass(frozen=True)
class ToolExecutionContext:
    default_context_before: int
    default_context_after: int
    sqlite_database_path: Path | None = None
    knowledge_sources: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class ToolExecutionResult:
    tool_name: str
    ok: bool
    content: dict[str, Any]
    error: str | None = None
    permission: str | None = None

    def model_content(self) -> str:
        return json.dumps(self.content)

    def expansion_payload(self, tool_call_id: str) -> dict[str, Any]:
        payload = {
            "used": self.ok,
            "tool_name": self.tool_name,
            "tool_call_id": tool_call_id,
            "result": self.content,
        }
        if self.error:
            payload["error"] = self.error
        if self.permission:
            payload["permission"] = self.permission

        return payload


@dataclass(frozen=True)
class ToolCallExecution:
    tool_call_id: str
    tool_call: dict[str, Any]
    result: ToolExecutionResult


@dataclass(frozen=True)
class RegisteredTool:
    metadata: ToolMetadata
    definition: dict[str, Any]
    executor: Callable[[dict[str, Any], ToolExecutionContext], dict[str, Any]]


class ToolRegistry:
    def __init__(self, context: ToolExecutionContext) -> None:
        self.context = context
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, tool: RegisteredTool) -> None:
        self._tools[tool.metadata.name] = tool

    def definitions(self) -> list[dict[str, Any]]:
        return [tool.definition for tool in self._tools.values()]

    def metadata(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.metadata.name,
                "description": tool.metadata.description,
                "permission": tool.metadata.permission,
                "destructive": tool.metadata.destructive,
            }
            for tool in self._tools.values()
        ]

    def execute_tool_call(self, tool_call: dict[str, Any]) -> ToolCallExecution:
        tool_call_id = tool_call.get("id") or "tool-call"
        function = tool_call.get("function") or {}
        tool_name = str(function.get("name") or "")
        tool = self._tools.get(tool_name)

        if tool is None:
            return ToolCallExecution(
                tool_call_id=tool_call_id,
                tool_call=tool_call,
                result=ToolExecutionResult(
                    tool_name=tool_name or "unknown",
                    ok=False,
                    content={"error": "unsupported tool call", "tool_name": tool_name},
                    error="unsupported tool call",
                ),
            )

        try:
            arguments = json.loads(function.get("arguments") or "{}")
            content = tool.executor(arguments, self.context)
        except json.JSONDecodeError as error:
            content = {"error": f"invalid tool arguments: {error}"}
        except (KeyError, TypeError, ValueError) as error:
            content = {"error": f"invalid tool arguments: {error}"}

        error_message = content.get("error") if isinstance(content, dict) else None
        return ToolCallExecution(
            tool_call_id=tool_call_id,
            tool_call=tool_call,
            result=ToolExecutionResult(
                tool_name=tool.metadata.name,
                ok=not error_message,
                content=content,
                error=error_message,
                permission=tool.metadata.permission,
            ),
        )

CONTEXT_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": CONTEXT_TOOL_NAME,
        "description": "Return messages surrounding a target message from the same conversation.",
        "parameters": {
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "integer",
                    "description": "The target message id to expand around.",
                },
                "before": {
                    "type": "integer",
                    "description": "Maximum number of messages before the target message.",
                    "default": 3,
                    "minimum": 0,
                },
                "after": {
                    "type": "integer",
                    "description": "Maximum number of messages after the target message.",
                    "default": 3,
                    "minimum": 0,
                },
            },
            "required": ["message_id"],
        },
    },
}

SQLITE_DATABASE_PATH_PROPERTY = {
    "type": "string",
    "description": "Optional absolute path to a SQLite database. Prefer source_id when a known knowledge source is available.",
}

SQLITE_SOURCE_ID_PROPERTY = {
    "type": "string",
    "description": "Optional knowledge source id from list_knowledge_sources. Omit source_id and database_path to inspect the active chat database.",
}

KNOWLEDGE_SOURCES_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": KNOWLEDGE_SOURCES_TOOL_NAME,
        "description": "List available SQLite knowledge sources with ids, descriptions, paths, and read permissions.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
}

SQLITE_LIST_TABLES_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": SQLITE_LIST_TABLES_TOOL_NAME,
        "description": "List tables and views in a SQLite database, including row counts for tables.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_id": SQLITE_SOURCE_ID_PROPERTY,
                "database_path": SQLITE_DATABASE_PATH_PROPERTY,
            },
        },
    },
}

SQLITE_DESCRIBE_TABLE_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": SQLITE_DESCRIBE_TABLE_TOOL_NAME,
        "description": "Describe columns and row count for one SQLite table or view.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_id": SQLITE_SOURCE_ID_PROPERTY,
                "database_path": SQLITE_DATABASE_PATH_PROPERTY,
                "table_name": {
                    "type": "string",
                    "description": "Name of the table or view to describe.",
                },
            },
            "required": ["table_name"],
        },
    },
}

SQLITE_SAMPLE_ROWS_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": SQLITE_SAMPLE_ROWS_TOOL_NAME,
        "description": "Return a bounded preview of rows from a SQLite table or view.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_id": SQLITE_SOURCE_ID_PROPERTY,
                "database_path": SQLITE_DATABASE_PATH_PROPERTY,
                "table_name": {
                    "type": "string",
                    "description": "Name of the table or view to sample.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of rows to return. Values are clamped to a safe bound.",
                    "default": 25,
                    "minimum": 1,
                    "maximum": 100,
                },
            },
            "required": ["table_name"],
        },
    },
}

SQLITE_SEARCH_TABLE_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": SQLITE_SEARCH_TABLE_TOOL_NAME,
        "description": "Search text-like columns in a SQLite table with a safe LIKE query.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_id": SQLITE_SOURCE_ID_PROPERTY,
                "database_path": SQLITE_DATABASE_PATH_PROPERTY,
                "table_name": {
                    "type": "string",
                    "description": "Name of the table or view to search.",
                },
                "query": {
                    "type": "string",
                    "description": "Text to search for.",
                },
                "columns": {
                    "type": "array",
                    "description": "Optional specific columns to search.",
                    "items": {"type": "string"},
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of rows to return. Values are clamped to a safe bound.",
                    "default": 25,
                    "minimum": 1,
                    "maximum": 100,
                },
            },
            "required": ["table_name", "query"],
        },
    },
}

SQLITE_SEARCH_DATABASE_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": SQLITE_SEARCH_DATABASE_TOOL_NAME,
        "description": "Search across text-like columns in all tables of a SQLite database using plain natural-language text. Use this for common searches before writing SQL.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_id": SQLITE_SOURCE_ID_PROPERTY,
                "database_path": SQLITE_DATABASE_PATH_PROPERTY,
                "query": {
                    "type": "string",
                    "description": "Natural-language text to search for, such as 'Henry birthday' or 'messages about embeddings'.",
                },
                "tables": {
                    "type": "array",
                    "description": "Optional table names to restrict the search.",
                    "items": {"type": "string"},
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of matches to return across the database. Values are clamped to a safe bound.",
                    "default": 25,
                    "minimum": 1,
                    "maximum": 50,
                },
            },
            "required": ["query"],
        },
    },
}

SQLITE_READ_ONLY_QUERY_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": SQLITE_READ_ONLY_QUERY_TOOL_NAME,
        "description": "Run one read-only SELECT or WITH query against a SQLite database. Mutation, ATTACH, and PRAGMA statements are rejected.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_id": SQLITE_SOURCE_ID_PROPERTY,
                "database_path": SQLITE_DATABASE_PATH_PROPERTY,
                "sql": {
                    "type": "string",
                    "description": "A single SELECT or WITH query.",
                },
                "params": {
                    "type": "array",
                    "description": "Optional positional query parameters.",
                    "items": {
                        "type": ["string", "number", "boolean", "null"],
                    },
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum rows fetched from the result. Values are clamped to a safe bound.",
                    "default": 100,
                    "minimum": 1,
                    "maximum": 200,
                },
            },
            "required": ["sql"],
        },
    },
}


def get_context_around_message(
    message_id: int,
    before: int = 3,
    after: int = 3,
) -> dict[str, Any] | None:
    target_message = get_message(message_id)
    if target_message is None:
        return None

    before_count = max(0, before)
    after_count = max(0, after)
    messages = [
        *list_messages_before(message_id, before_count),
        target_message,
        *list_messages_after(message_id, after_count),
    ]

    return {
        "target_message_id": message_id,
        "conversation_id": target_message["conversation_id"],
        "before": before_count,
        "after": after_count,
        "messages": [_format_context_message(message) for message in messages],
    }


def _format_context_message(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "message_id": message["id"],
        "role": message["role"],
        "content": message["content"],
        "created_at": message["created_at"],
    }


def execute_context_tool(arguments: dict[str, Any], default_before: int, default_after: int) -> dict[str, Any]:
    message_id = int(arguments["message_id"])
    before = _read_nonnegative_int(arguments.get("before"), default_before)
    after = _read_nonnegative_int(arguments.get("after"), default_after)
    context = get_context_around_message(message_id, before=before, after=after)

    if context is None:
        return {
            "error": "message not found",
            "message_id": message_id,
        }

    return context


def execute_context_tool_from_registry(
    arguments: dict[str, Any],
    context: ToolExecutionContext,
) -> dict[str, Any]:
    return execute_context_tool(
        arguments,
        default_before=context.default_context_before,
        default_after=context.default_context_after,
    )


def execute_sqlite_list_tables_tool(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    return _execute_sqlite_tool(lambda database_path: list_tables(database_path), arguments, context)


def execute_knowledge_sources_tool(_arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    return {
        "sources": list_available_databases(context.sqlite_database_path, context.knowledge_sources),
    }


def execute_sqlite_describe_table_tool(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    return _execute_sqlite_tool(
        lambda database_path: describe_table(database_path, str(arguments["table_name"]).strip()),
        arguments,
        context,
    )


def execute_sqlite_sample_rows_tool(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    return _execute_sqlite_tool(
        lambda database_path: preview_rows(
            database_path,
            str(arguments["table_name"]).strip(),
            limit=_read_positive_int(arguments.get("limit"), 25),
        ),
        arguments,
        context,
    )


def execute_sqlite_search_table_tool(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    raw_columns = arguments.get("columns")
    columns = raw_columns if isinstance(raw_columns, list) else None
    return _execute_sqlite_tool(
        lambda database_path: search_table(
            database_path,
            str(arguments["table_name"]).strip(),
            str(arguments["query"]).strip(),
            columns=columns,
            limit=_read_positive_int(arguments.get("limit"), 25),
        ),
        arguments,
        context,
    )


def execute_sqlite_search_database_tool(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    raw_tables = arguments.get("tables")
    tables = raw_tables if isinstance(raw_tables, list) else None
    return _execute_sqlite_tool(
        lambda database_path: search_database(
            database_path,
            str(arguments["query"]).strip(),
            tables=tables,
            limit=_read_positive_int(arguments.get("limit"), 25),
        ),
        arguments,
        context,
    )


def execute_sqlite_read_only_query_tool(arguments: dict[str, Any], context: ToolExecutionContext) -> dict[str, Any]:
    raw_params = arguments.get("params")
    params = raw_params if isinstance(raw_params, list) else []
    return _execute_sqlite_tool(
        lambda database_path: run_read_only_query(
            database_path,
            str(arguments["sql"]),
            params=params,
            limit=_read_positive_int(arguments.get("limit"), 100),
        ),
        arguments,
        context,
    )


def _execute_sqlite_tool(
    operation: Callable[[Path], dict[str, Any]],
    arguments: dict[str, Any],
    context: ToolExecutionContext,
) -> dict[str, Any]:
    try:
        return operation(_read_database_path(arguments, context))
    except SQLiteExplorerError as error:
        return {"error": str(error)}


def _read_database_path(arguments: dict[str, Any], context: ToolExecutionContext) -> Path:
    raw_source_id = str(arguments.get("source_id") or "").strip()
    if raw_source_id:
        source = resolve_database_source(raw_source_id, context.sqlite_database_path, context.knowledge_sources)
        return Path(source["path"])

    raw_path = str(arguments.get("database_path") or "").strip()
    if raw_path:
        return Path(raw_path)
    if context.sqlite_database_path is not None:
        return context.sqlite_database_path
    return get_database_path()


def build_default_tool_registry(
    default_context_before: int,
    default_context_after: int,
    sqlite_database_path: Path | None = None,
    knowledge_sources: tuple[dict[str, str], ...] = (),
) -> ToolRegistry:
    registry = ToolRegistry(
        ToolExecutionContext(
            default_context_before=default_context_before,
            default_context_after=default_context_after,
            sqlite_database_path=sqlite_database_path,
            knowledge_sources=knowledge_sources,
        )
    )
    registry.register(
        RegisteredTool(
            metadata=ToolMetadata(
                name=CONTEXT_TOOL_NAME,
                description="Return messages surrounding a target message from the same conversation.",
                permission="conversation.read",
                destructive=False,
            ),
            definition=CONTEXT_TOOL_DEFINITION,
            executor=execute_context_tool_from_registry,
        )
    )
    registry.register(
        RegisteredTool(
            metadata=ToolMetadata(
                name=KNOWLEDGE_SOURCES_TOOL_NAME,
                description="List available SQLite knowledge sources.",
                permission="sqlite.read",
                destructive=False,
            ),
            definition=KNOWLEDGE_SOURCES_TOOL_DEFINITION,
            executor=execute_knowledge_sources_tool,
        )
    )
    registry.register(
        RegisteredTool(
            metadata=ToolMetadata(
                name=SQLITE_LIST_TABLES_TOOL_NAME,
                description="List tables and views in a SQLite database.",
                permission="sqlite.read",
                destructive=False,
            ),
            definition=SQLITE_LIST_TABLES_TOOL_DEFINITION,
            executor=execute_sqlite_list_tables_tool,
        )
    )
    registry.register(
        RegisteredTool(
            metadata=ToolMetadata(
                name=SQLITE_DESCRIBE_TABLE_TOOL_NAME,
                description="Describe columns and row count for a SQLite table or view.",
                permission="sqlite.read",
                destructive=False,
            ),
            definition=SQLITE_DESCRIBE_TABLE_TOOL_DEFINITION,
            executor=execute_sqlite_describe_table_tool,
        )
    )
    registry.register(
        RegisteredTool(
            metadata=ToolMetadata(
                name=SQLITE_SAMPLE_ROWS_TOOL_NAME,
                description="Preview rows from a SQLite table or view.",
                permission="sqlite.read",
                destructive=False,
            ),
            definition=SQLITE_SAMPLE_ROWS_TOOL_DEFINITION,
            executor=execute_sqlite_sample_rows_tool,
        )
    )
    registry.register(
        RegisteredTool(
            metadata=ToolMetadata(
                name=SQLITE_SEARCH_TABLE_TOOL_NAME,
                description="Search text-like columns in a SQLite table.",
                permission="sqlite.read",
                destructive=False,
            ),
            definition=SQLITE_SEARCH_TABLE_TOOL_DEFINITION,
            executor=execute_sqlite_search_table_tool,
        )
    )
    registry.register(
        RegisteredTool(
            metadata=ToolMetadata(
                name=SQLITE_SEARCH_DATABASE_TOOL_NAME,
                description="Search text-like columns across a SQLite database using natural-language text.",
                permission="sqlite.read",
                destructive=False,
            ),
            definition=SQLITE_SEARCH_DATABASE_TOOL_DEFINITION,
            executor=execute_sqlite_search_database_tool,
        )
    )
    registry.register(
        RegisteredTool(
            metadata=ToolMetadata(
                name=SQLITE_READ_ONLY_QUERY_TOOL_NAME,
                description="Run one safe read-only SELECT or WITH query against SQLite.",
                permission="sqlite.read",
                destructive=False,
            ),
            definition=SQLITE_READ_ONLY_QUERY_TOOL_DEFINITION,
            executor=execute_sqlite_read_only_query_tool,
        )
    )
    return registry


def _read_nonnegative_int(value: Any, default: int) -> int:
    if value is None:
        return default

    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _read_positive_int(value: Any, default: int) -> int:
    if value is None:
        return default

    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default
