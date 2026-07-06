from __future__ import annotations

import json
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from .database import create_conversation
    from .database import create_embedding
    from .database import create_message
    from .database import get_conversation
    from .database import get_message
    from .database import list_recent_messages
    from .embeddings import EmbeddingProvider
    from .embeddings import serialize_vector
    from .prompt import assemble_prompt
    from .retrieval import retrieve_relevant_memories
    from .tools import ToolRegistry
    from .tools import build_default_tool_registry
except ImportError:
    from database import create_conversation
    from database import create_embedding
    from database import create_message
    from database import get_conversation
    from database import get_message
    from database import list_recent_messages
    from embeddings import EmbeddingProvider
    from embeddings import serialize_vector
    from prompt import assemble_prompt
    from retrieval import retrieve_relevant_memories
    from tools import ToolRegistry
    from tools import build_default_tool_registry


CHAT_PIPELINE_STAGES = (
    "save_user_message",
    "embed_user_message",
    "retrieve_memories",
    "assemble_prompt",
    "optional_context_expansion",
    "save_assistant_message",
)


@dataclass(frozen=True)
class ChatClientConfig:
    base_url: str
    model: str
    timeout_seconds: float
    use_placeholder: bool


@dataclass(frozen=True)
class GenerationParams:
    temperature: float | None = None
    repeat_penalty: float | None = None

    def as_payload(self) -> dict[str, float]:
        payload: dict[str, float] = {}
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.repeat_penalty is not None:
            payload["repeat_penalty"] = self.repeat_penalty
        return payload


@dataclass(frozen=True)
class ChatOrchestratorConfig:
    rolling_message_count: int
    retrieved_memory_count: int
    retrieval_similarity_threshold: float | None
    default_context_before: int
    default_context_after: int
    max_tool_expansion_passes: int
    default_generation_params: GenerationParams
    system_prompt: str
    database_path: Path | None = None
    knowledge_sources: tuple[dict[str, str], ...] = ()


class ChatRequestError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class LocalChatClient:
    """Adapter for the OpenAI-compatible local model server."""

    def __init__(self, config: ChatClientConfig) -> None:
        self.config = config

    def placeholder_response(self, message: str) -> str:
        if not message.strip():
            return "Send a message and I will echo a placeholder response."

        return f"Placeholder response from {self.config.model}: {message}"

    def complete(self, messages: list[dict[str, Any]], generation_params: GenerationParams | None = None) -> str:
        if self.config.use_placeholder:
            latest_user_message = next(
                (message["content"] for message in reversed(messages) if message["role"] == "user"),
                "",
            )
            return self.placeholder_response(latest_user_message)

        message = self._create_chat_message(messages, generation_params=generation_params)
        return self._extract_content(message)

    def stream_complete(self, messages: list[dict[str, Any]], generation_params: GenerationParams | None = None) -> Any:
        if self.config.use_placeholder:
            text = self.complete(messages, generation_params=generation_params)
            for index in range(0, len(text), 24):
                yield text[index : index + 24]
            return

        yield from self._create_chat_message_stream(messages, generation_params=generation_params)

    def complete_with_tool_expansion(
        self,
        messages: list[dict[str, Any]],
        tool_registry: ToolRegistry,
        max_expansion_passes: int,
        generation_params: GenerationParams | None = None,
    ) -> tuple[str, dict[str, Any]]:
        if self.config.use_placeholder or max_expansion_passes <= 0:
            if generation_params is None or not generation_params.as_payload():
                return self.complete(messages), {"used": False}

            return self.complete(messages, generation_params=generation_params), {"used": False}

        first_message = self._create_chat_message(
            messages,
            tools=tool_registry.definitions(),
            generation_params=generation_params,
        )
        followup_messages, context_expansion = self._build_tool_followup_messages(
            messages,
            first_message,
            tool_registry,
        )
        if followup_messages is None:
            return self._extract_content(first_message), {"used": False}

        final_message = self._create_chat_message(followup_messages, generation_params=generation_params)
        return self._extract_content(final_message), context_expansion

    def stream_with_tool_expansion(
        self,
        messages: list[dict[str, Any]],
        tool_registry: ToolRegistry,
        max_expansion_passes: int,
        generation_params: GenerationParams | None = None,
    ) -> Iterator[dict[str, Any]]:
        if self.config.use_placeholder or max_expansion_passes <= 0:
            content = ""
            for chunk in self.stream_complete(messages, generation_params=generation_params):
                content += chunk
                yield {"type": "delta", "content": chunk}

            yield {"type": "done", "content": content, "context_expansion": {"used": False}}
            return

        content = ""
        first_message: dict[str, Any] | None = None
        for event in self._create_chat_message_stream_events(
            messages,
            tools=tool_registry.definitions(),
            generation_params=generation_params,
        ):
            if event["type"] == "delta":
                content += event["content"]
                yield event
            elif event["type"] == "message":
                first_message = event["message"]

        if first_message is None:
            raise RuntimeError("model server stream did not include an assistant message")

        followup_messages, context_expansion = self._build_tool_followup_messages(
            messages,
            first_message,
            tool_registry,
        )
        if followup_messages is None:
            yield {"type": "done", "content": content, "context_expansion": {"used": False}}
            return

        for event in self._create_chat_message_stream_events(
            followup_messages,
            generation_params=generation_params,
        ):
            if event["type"] == "delta":
                content += event["content"]
                yield event
            elif event["type"] == "message" and not content:
                content = self._extract_content(event["message"])

        yield {"type": "done", "content": content, "context_expansion": context_expansion}

    def _build_tool_followup_messages(
        self,
        messages: list[dict[str, Any]],
        first_message: dict[str, Any],
        tool_registry: ToolRegistry,
    ) -> tuple[list[dict[str, Any]] | None, dict[str, Any]]:
        tool_calls = first_message.get("tool_calls") or []
        if not tool_calls:
            return None, {"used": False}

        tool_call = tool_calls[0]
        execution = tool_registry.execute_tool_call(tool_call)
        followup_messages = [
            *messages,
            {
                "role": "assistant",
                "content": first_message.get("content") or "",
                "tool_calls": [tool_call],
            },
            {
                "role": "tool",
                "tool_call_id": execution.tool_call_id,
                "name": execution.result.tool_name,
                "content": execution.result.model_content(),
            },
        ]

        return followup_messages, execution.result.expansion_payload(execution.tool_call_id)

    def _create_chat_message(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        generation_params: GenerationParams | None = None,
    ) -> dict[str, Any]:
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
        }
        payload.update((generation_params or GenerationParams()).as_payload())
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

    def _create_chat_message_stream(
        self,
        messages: list[dict[str, Any]],
        generation_params: GenerationParams | None = None,
    ) -> Any:
        for event in self._create_chat_message_stream_events(messages, generation_params=generation_params):
            if event["type"] == "delta":
                yield event["content"]

    def _create_chat_message_stream_events(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        generation_params: GenerationParams | None = None,
    ) -> Iterator[dict[str, Any]]:
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.config.model,
            "messages": messages,
            "stream": True,
        }
        payload.update((generation_params or GenerationParams()).as_payload())
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
            content_chunks: list[str] = []
            tool_call_chunks: dict[int, dict[str, Any]] = {}
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data:"):
                        continue

                    payload_text = line.removeprefix("data:").strip()
                    if payload_text == "[DONE]":
                        break

                    try:
                        chunk = json.loads(payload_text)
                        choice = chunk["choices"][0]
                    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
                        raise RuntimeError("model server returned an invalid stream chunk") from error

                    delta = choice.get("delta") or {}
                    content = delta.get("content") or choice.get("text")
                    if content:
                        content_text = str(content)
                        content_chunks.append(content_text)
                        yield {"type": "delta", "content": content_text}

                    for tool_call_delta in delta.get("tool_calls") or []:
                        _merge_tool_call_delta(tool_call_chunks, tool_call_delta)

            yield {
                "type": "message",
                "message": {
                    "role": "assistant",
                    "content": "".join(content_chunks),
                    "tool_calls": _ordered_tool_calls(tool_call_chunks),
                },
            }
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"model server returned HTTP {error.code}: {detail}") from error
        except URLError as error:
            raise RuntimeError(f"could not reach model server: {error.reason}") from error
        except TimeoutError as error:
            raise RuntimeError("model server request timed out") from error

    def _extract_content(self, message: dict[str, Any]) -> str:
        content = message.get("content")
        if content is None:
            return ""

        return str(content).strip()


class ChatOrchestrator:
    def __init__(
        self,
        chat_client: LocalChatClient,
        embedding_provider: EmbeddingProvider,
        config: ChatOrchestratorConfig,
    ) -> None:
        self.chat_client = chat_client
        self.embedding_provider = embedding_provider
        self.config = config
        self.tool_registry = build_default_tool_registry(
            default_context_before=config.default_context_before,
            default_context_after=config.default_context_after,
            sqlite_database_path=config.database_path,
            knowledge_sources=config.knowledge_sources,
        )

    def update_knowledge_sources(self, knowledge_sources: tuple[dict[str, str], ...]) -> None:
        self.config = replace(self.config, knowledge_sources=knowledge_sources)
        self.tool_registry = build_default_tool_registry(
            default_context_before=self.config.default_context_before,
            default_context_after=self.config.default_context_after,
            sqlite_database_path=self.config.database_path,
            knowledge_sources=knowledge_sources,
        )

    def complete_turn(self, payload: dict[str, Any]) -> dict[str, Any]:
        turn = self.prepare_turn(payload)
        assistant_content, context_expansion = self._complete_model_response(turn)
        return self.persist_assistant_response(turn, assistant_content, context_expansion)

    def stream_turn(self, payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
        turn = self.prepare_turn(payload)
        yield {"event": "conversation", "data": {"conversation": turn["conversation"]}}
        yield {"event": "user_message", "data": {"user_message": turn["user_message"]}}

        assistant_content = ""
        context_expansion: dict[str, Any] = {"used": False}
        for event in self._stream_model_response(turn):
            if event["type"] == "delta":
                yield {"event": "delta", "data": {"content": event["content"]}}
            elif event["type"] == "done":
                assistant_content = event["content"]
                context_expansion = event["context_expansion"]

        payload = self.persist_assistant_response(turn, assistant_content, context_expansion)
        yield {"event": "assistant_message", "data": payload}
        yield {"event": "done", "data": {}}

    def prepare_turn(self, payload: dict[str, Any]) -> dict[str, Any]:
        message = str(payload.get("message", "")).strip()
        conversation_id = payload.get("conversation_id")

        if not message:
            raise ChatRequestError("message is required", 400)

        if conversation_id is None:
            title = message[:60] or "New conversation"
            conversation = create_conversation(title)
            conversation_id = conversation["id"]
        else:
            try:
                conversation_id = int(conversation_id)
            except (TypeError, ValueError) as error:
                raise ChatRequestError("conversation_id must be an integer", 400) from error

            conversation = get_conversation(conversation_id)
            if conversation is None:
                raise ChatRequestError("conversation not found", 404)

        user_message = create_message(conversation_id, "user", message)

        try:
            user_message, user_embedding, user_embedding_vector = self.create_embedding_for_message(user_message)
        except RuntimeError as error:
            raise ChatRequestError(str(error), 502) from error

        recent_messages = list_recent_messages(conversation_id, self.config.rolling_message_count)
        rolling_message_ids = {recent_message["id"] for recent_message in recent_messages}
        retrieved_memories = retrieve_relevant_memories(
            conversation_id=conversation_id,
            query_vector=user_embedding_vector,
            exclude_message_ids=rolling_message_ids,
            limit=self.config.retrieved_memory_count,
            similarity_threshold=self.config.retrieval_similarity_threshold,
        )
        model_messages = assemble_prompt(
            system_prompt=self.config.system_prompt,
            recalled_memories=retrieved_memories,
            recent_messages=recent_messages,
            current_user_message_id=user_message["id"],
        )

        return {
            "conversation": conversation,
            "user_message": user_message,
            "user_embedding": user_embedding,
            "recent_messages": recent_messages,
            "rolling_message_ids": rolling_message_ids,
            "retrieved_memories": retrieved_memories,
            "model_messages": model_messages,
            "generation_params": read_generation_params(payload, self.config.default_generation_params),
        }

    def create_embedding_for_message(self, message: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[float]]:
        result = self.embedding_provider.embed(message["content"])
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

    def persist_assistant_response(
        self,
        turn: dict[str, Any],
        assistant_content: str,
        context_expansion: dict[str, Any],
    ) -> dict[str, Any]:
        assistant_content = assistant_content.strip()
        if not assistant_content:
            assistant_content = "(The model returned an empty response.)"

        assistant_message = create_message(turn["conversation"]["id"], "assistant", assistant_content)

        try:
            assistant_message, assistant_embedding, _assistant_embedding_vector = self.create_embedding_for_message(
                assistant_message
            )
        except RuntimeError as error:
            raise ChatRequestError(str(error), 502) from error

        return self.chat_response_payload(turn, assistant_message, assistant_embedding, context_expansion)

    def chat_response_payload(
        self,
        turn: dict[str, Any],
        assistant_message: dict[str, Any],
        assistant_embedding: dict[str, Any],
        context_expansion: dict[str, Any],
    ) -> dict[str, Any]:
        recent_messages = turn["recent_messages"]
        model_messages = turn["model_messages"]
        rolling_message_ids = turn["rolling_message_ids"]
        retrieved_memories = turn["retrieved_memories"]
        generation_params = turn["generation_params"]

        return {
            "conversation": turn["conversation"],
            "user_message": turn["user_message"],
            "assistant_message": assistant_message,
            "embeddings": {
                "user": turn["user_embedding"],
                "assistant": assistant_embedding,
            },
            "context_window": {
                "configured_message_count": self.config.rolling_message_count,
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
                "configured_memory_count": self.config.retrieved_memory_count,
                "similarity_threshold": self.config.retrieval_similarity_threshold,
                "excluded_message_ids": sorted(rolling_message_ids),
            },
            "context_expansion": context_expansion,
            "generation": generation_params.as_payload(),
        }

    def _complete_model_response(self, turn: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        return self.chat_client.complete_with_tool_expansion(
            messages=turn["model_messages"],
            tool_registry=self.tool_registry,
            max_expansion_passes=self.config.max_tool_expansion_passes,
            generation_params=turn["generation_params"],
        )

    def _stream_model_response(self, turn: dict[str, Any]) -> Iterator[dict[str, Any]]:
        yield from self.chat_client.stream_with_tool_expansion(
            messages=turn["model_messages"],
            tool_registry=self.tool_registry,
            max_expansion_passes=self.config.max_tool_expansion_passes,
            generation_params=turn["generation_params"],
        )


def read_generation_params(payload: dict[str, Any], defaults: GenerationParams) -> GenerationParams:
    generation = payload.get("generation")
    if not isinstance(generation, dict):
        generation = {}

    return GenerationParams(
        temperature=read_optional_nonnegative_float(generation.get("temperature"), defaults.temperature),
        repeat_penalty=read_optional_nonnegative_float(generation.get("repeat_penalty"), defaults.repeat_penalty),
    )


def read_optional_nonnegative_float(value: Any, default: float | None) -> float | None:
    if value is None or value == "":
        return default

    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return default


def _merge_tool_call_delta(tool_call_chunks: dict[int, dict[str, Any]], delta: dict[str, Any]) -> None:
    index = int(delta.get("index", len(tool_call_chunks)))
    tool_call = tool_call_chunks.setdefault(
        index,
        {
            "id": "",
            "type": "function",
            "function": {
                "name": "",
                "arguments": "",
            },
        },
    )

    if delta.get("id"):
        tool_call["id"] = delta["id"]
    if delta.get("type"):
        tool_call["type"] = delta["type"]

    function_delta = delta.get("function") or {}
    function = tool_call["function"]
    if function_delta.get("name"):
        function["name"] += function_delta["name"]
    if function_delta.get("arguments"):
        function["arguments"] += function_delta["arguments"]


def _ordered_tool_calls(tool_call_chunks: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    tool_calls = []
    for index in sorted(tool_call_chunks):
        tool_call = tool_call_chunks[index]
        if not tool_call["id"]:
            tool_call["id"] = f"streamed-tool-call-{index}"
        tool_calls.append(tool_call)

    return tool_calls
