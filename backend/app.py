from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Flask, jsonify, request
from flask_cors import CORS

try:
    from .database import create_conversation
    from .database import create_embedding
    from .database import create_message
    from .database import get_message
    from .database import get_conversation
    from .database import init_db
    from .database import list_conversations
    from .database import list_messages
    from .database import list_recent_messages
    from .config import load_config
    from .embeddings import build_embedding_provider
    from .embeddings import serialize_vector
    from .prompt import assemble_prompt
    from .retrieval import retrieve_relevant_memories
    from .tools import CONTEXT_TOOL_DEFINITION
    from .tools import CONTEXT_TOOL_NAME
    from .tools import execute_context_tool
    from .tools import get_context_around_message
except ImportError:
    from database import create_conversation
    from database import create_embedding
    from database import create_message
    from database import get_message
    from database import get_conversation
    from database import init_db
    from database import list_conversations
    from database import list_messages
    from database import list_recent_messages
    from config import load_config
    from embeddings import build_embedding_provider
    from embeddings import serialize_vector
    from prompt import assemble_prompt
    from retrieval import retrieve_relevant_memories
    from tools import CONTEXT_TOOL_DEFINITION
    from tools import CONTEXT_TOOL_NAME
    from tools import execute_context_tool
    from tools import get_context_around_message


@dataclass(frozen=True)
class ChatClientConfig:
    base_url: str
    model: str
    timeout_seconds: float
    use_placeholder: bool


class LocalChatClient:
    """Adapter for the future OpenAI-compatible llama.cpp client."""

    def __init__(self, config: ChatClientConfig) -> None:
        self.config = config

    def placeholder_response(self, message: str) -> str:
        if not message.strip():
            return "Send a message and I will echo a placeholder response."

        return f"Placeholder response from {self.config.model}: {message}"

    def complete(self, messages: list[dict[str, str]]) -> str:
        if self.config.use_placeholder:
            latest_user_message = next(
                (message["content"] for message in reversed(messages) if message["role"] == "user"),
                "",
            )
            return self.placeholder_response(latest_user_message)

        message = self._create_chat_message(messages)
        return self._extract_content(message)

    def complete_with_tool_expansion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        default_context_before: int,
        default_context_after: int,
        max_expansion_passes: int,
    ) -> tuple[str, dict[str, Any]]:
        if self.config.use_placeholder or max_expansion_passes <= 0:
            return self.complete(messages), {"used": False}

        first_message = self._create_chat_message(messages, tools=tools)
        tool_calls = first_message.get("tool_calls") or []
        if not tool_calls:
            return self._extract_content(first_message), {"used": False}

        tool_call = tool_calls[0]
        function = tool_call.get("function") or {}
        if function.get("name") != CONTEXT_TOOL_NAME:
            return self._extract_content(first_message), {"used": False, "error": "unsupported tool call"}

        try:
            arguments = json.loads(function.get("arguments") or "{}")
            tool_result = execute_context_tool(arguments, default_context_before, default_context_after)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            tool_result = {"error": f"invalid tool arguments: {error}"}

        tool_call_id = tool_call.get("id") or "context-expansion"
        followup_messages = [
            *messages,
            {
                "role": "assistant",
                "content": first_message.get("content") or "",
                "tool_calls": [tool_call],
            },
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": CONTEXT_TOOL_NAME,
                "content": json.dumps(tool_result),
            },
        ]
        final_message = self._create_chat_message(followup_messages)

        return self._extract_content(final_message), {
            "used": "error" not in tool_result,
            "tool_name": CONTEXT_TOOL_NAME,
            "tool_call_id": tool_call_id,
            "result": tool_result,
        }

    def _create_chat_message(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"model server returned HTTP {error.code}: {detail}") from error
        except URLError as error:
            raise RuntimeError(f"could not reach model server: {error.reason}") from error
        except TimeoutError as error:
            raise RuntimeError("model server request timed out") from error

        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError("model server response did not include an assistant message") from error

        return message

    def _extract_content(self, message: dict[str, Any]) -> str:
        content = message.get("content")
        if content is None:
            return ""

        return str(content).strip()


def create_app() -> Flask:
    config = load_config()
    app = Flask(__name__)
    app.config["ASSOCIATIVE_CHAT"] = config
    CORS(app, resources={r"/api/*": {"origins": config.frontend_origin}})
    init_db(config.database_path)

    chat_client = LocalChatClient(
        ChatClientConfig(
            base_url=config.model_endpoint_url,
            model=config.model_name,
            timeout_seconds=config.model_timeout_seconds,
            use_placeholder=config.use_placeholder_chat,
        )
    )
    rolling_message_count = config.rolling_message_count
    retrieved_memory_count = config.retrieved_memory_count
    retrieval_similarity_threshold = config.retrieval_similarity_threshold
    default_context_before = config.default_context_before
    default_context_after = config.default_context_after
    max_tool_expansion_passes = config.max_tool_expansion_passes
    system_prompt = config.system_prompt
    embedding_provider = build_embedding_provider(config)

    def create_embedding_for_message(message: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[float]]:
        result = embedding_provider.embed(message["content"])
        embedding = create_embedding(
            message_id=message["id"],
            provider=result.provider,
            model=result.model,
            vector=serialize_vector(result.vector),
        )
        refreshed_message = get_message(message["id"])
        if refreshed_message is None:
            raise RuntimeError("message disappeared after embedding creation")

        return refreshed_message, embedding, result.vector

    @app.get("/api/health")
    def health() -> tuple[dict[str, str], int]:
        return {"status": "ok"}, 200

    @app.get("/api/conversations")
    def conversations_index():
        return jsonify({"conversations": list_conversations()})

    @app.post("/api/conversations")
    def conversations_create():
        payload = request.get_json(silent=True) or {}
        conversation = create_conversation(payload.get("title"))
        return jsonify({"conversation": conversation}), 201

    @app.get("/api/conversations/<int:conversation_id>/messages")
    def messages_index(conversation_id: int):
        if get_conversation(conversation_id) is None:
            return jsonify({"error": "conversation not found"}), 404

        return jsonify({"messages": list_messages(conversation_id)})

    @app.post("/api/conversations/<int:conversation_id>/messages")
    def messages_create(conversation_id: int):
        payload = request.get_json(silent=True) or {}
        role = str(payload.get("role", "")).strip()
        content = str(payload.get("content", "")).strip()

        if role not in {"system", "user", "assistant", "tool"}:
            return jsonify({"error": "role must be one of system, user, assistant, tool"}), 400

        if not content:
            return jsonify({"error": "content is required"}), 400

        try:
            message = create_message(conversation_id, role, content)
        except ValueError:
            return jsonify({"error": "conversation not found"}), 404

        try:
            message, embedding, _embedding_vector = create_embedding_for_message(message)
        except RuntimeError as error:
            return jsonify({"error": str(error), "message": message}), 502

        return jsonify({"message": message, "embedding": embedding}), 201

    @app.get("/api/tools/context-around-message/<int:message_id>")
    def context_around_message(message_id: int):
        before = read_request_int("before", default_context_before)
        after = read_request_int("after", default_context_after)
        context = get_context_around_message(message_id, before=before, after=after)

        if context is None:
            return jsonify({"error": "message not found"}), 404

        return jsonify({"context": context})

    @app.post("/api/chat")
    def chat():
        payload = request.get_json(silent=True) or {}
        message = str(payload.get("message", "")).strip()
        conversation_id = payload.get("conversation_id")

        if not message:
            return jsonify({"error": "message is required"}), 400

        if conversation_id is None:
            title = message[:60] or "New conversation"
            conversation = create_conversation(title)
            conversation_id = conversation["id"]
        else:
            try:
                conversation_id = int(conversation_id)
            except (TypeError, ValueError):
                return jsonify({"error": "conversation_id must be an integer"}), 400

            conversation = get_conversation(conversation_id)
            if conversation is None:
                return jsonify({"error": "conversation not found"}), 404

        user_message = create_message(conversation_id, "user", message)

        try:
            user_message, user_embedding, user_embedding_vector = create_embedding_for_message(user_message)
        except RuntimeError as error:
            return jsonify({"error": str(error), "user_message": user_message}), 502

        recent_messages = list_recent_messages(conversation_id, rolling_message_count)
        rolling_message_ids = {recent_message["id"] for recent_message in recent_messages}
        retrieved_memories = retrieve_relevant_memories(
            conversation_id=conversation_id,
            query_vector=user_embedding_vector,
            exclude_message_ids=rolling_message_ids,
            limit=retrieved_memory_count,
            similarity_threshold=retrieval_similarity_threshold,
        )
        model_messages = assemble_prompt(
            system_prompt=system_prompt,
            recalled_memories=retrieved_memories,
            recent_messages=recent_messages,
            current_user_message_id=user_message["id"],
        )

        try:
            assistant_content, context_expansion = chat_client.complete_with_tool_expansion(
                messages=model_messages,
                tools=[CONTEXT_TOOL_DEFINITION],
                default_context_before=default_context_before,
                default_context_after=default_context_after,
                max_expansion_passes=max_tool_expansion_passes,
            )
        except RuntimeError as error:
            return jsonify({"error": str(error), "user_message": user_message}), 502

        if not assistant_content:
            assistant_content = "(The model returned an empty response.)"

        assistant_message = create_message(conversation_id, "assistant", assistant_content)

        try:
            assistant_message, assistant_embedding, _assistant_embedding_vector = create_embedding_for_message(
                assistant_message
            )
        except RuntimeError as error:
            return jsonify({"error": str(error), "assistant_message": assistant_message}), 502

        return jsonify(
            {
                "conversation": conversation,
                "user_message": user_message,
                "assistant_message": assistant_message,
                "embeddings": {
                    "user": user_embedding,
                    "assistant": assistant_embedding,
                },
                "context_window": {
                    "configured_message_count": rolling_message_count,
                    "recent_message_count": len(recent_messages),
                    "message_ids": [message["id"] for message in recent_messages],
                },
                "prompt": {
                    "message_count": len(model_messages),
                    "used_recalled_memories": bool(retrieved_memories),
                    "recalled_memory_count": len(retrieved_memories),
                },
                "retrieved_memories": retrieved_memories,
                "retrieval": {
                    "configured_memory_count": retrieved_memory_count,
                    "similarity_threshold": retrieval_similarity_threshold,
                    "excluded_message_ids": sorted(rolling_message_ids),
                },
                "context_expansion": context_expansion,
            }
        )

    return app


def read_request_int(name: str, default: int) -> int:
    raw_value = request.args.get(name)
    if raw_value is None:
        return default

    try:
        return max(0, int(raw_value))
    except ValueError:
        return default


app = create_app()


if __name__ == "__main__":
    app_config = app.config["ASSOCIATIVE_CHAT"]
    app.run(host="0.0.0.0", port=app_config.port, debug=True)
