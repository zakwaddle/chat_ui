from __future__ import annotations

from typing import Any

try:
    from .database import get_message
    from .database import list_messages_after
    from .database import list_messages_before
except ImportError:
    from database import get_message
    from database import list_messages_after
    from database import list_messages_before


CONTEXT_TOOL_NAME = "get_context_around_message"

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


def _read_nonnegative_int(value: Any, default: int) -> int:
    if value is None:
        return default

    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default
