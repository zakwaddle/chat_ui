from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable
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


def build_default_tool_registry(default_context_before: int, default_context_after: int) -> ToolRegistry:
    registry = ToolRegistry(
        ToolExecutionContext(
            default_context_before=default_context_before,
            default_context_after=default_context_after,
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
    return registry


def _read_nonnegative_int(value: Any, default: int) -> int:
    if value is None:
        return default

    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default
