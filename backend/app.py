from __future__ import annotations

import json
from typing import Any

from flask import Flask, Response, jsonify, request, stream_with_context
from flask_cors import CORS

try:
    from .database import create_conversation
    from .database import create_message
    from .database import get_conversation
    from .database import init_db
    from .database import list_conversations
    from .database import list_messages
    from .chat import ChatClientConfig
    from .chat import ChatOrchestrator
    from .chat import ChatOrchestratorConfig
    from .chat import ChatRequestError
    from .chat import GenerationParams
    from .chat import LocalChatClient
    from .config import load_config
    from .embeddings import build_embedding_provider
    from .tools import get_context_around_message
except ImportError:
    from database import create_conversation
    from database import create_message
    from database import get_conversation
    from database import init_db
    from database import list_conversations
    from database import list_messages
    from chat import ChatClientConfig
    from chat import ChatOrchestrator
    from chat import ChatOrchestratorConfig
    from chat import ChatRequestError
    from chat import GenerationParams
    from chat import LocalChatClient
    from config import load_config
    from embeddings import build_embedding_provider
    from tools import get_context_around_message


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
    embedding_provider = build_embedding_provider(config)
    chat_orchestrator = ChatOrchestrator(
        chat_client=chat_client,
        embedding_provider=embedding_provider,
        config=ChatOrchestratorConfig(
            rolling_message_count=config.rolling_message_count,
            retrieved_memory_count=config.retrieved_memory_count,
            retrieval_similarity_threshold=config.retrieval_similarity_threshold,
            default_context_before=config.default_context_before,
            default_context_after=config.default_context_after,
            max_tool_expansion_passes=config.max_tool_expansion_passes,
            default_generation_params=GenerationParams(
                temperature=config.model_temperature,
                repeat_penalty=config.model_repeat_penalty,
            ),
            system_prompt=config.system_prompt,
        )
    )

    def encode_stream_event(event: str, data: dict[str, Any]) -> str:
        return json.dumps({"event": event, "data": data}) + "\n"

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
            message, embedding, _embedding_vector = chat_orchestrator.create_embedding_for_message(message)
        except RuntimeError as error:
            return jsonify({"error": str(error), "message": message}), 502

        return jsonify({"message": message, "embedding": embedding}), 201

    @app.get("/api/tools/context-around-message/<int:message_id>")
    def context_around_message(message_id: int):
        before = read_request_int("before", config.default_context_before)
        after = read_request_int("after", config.default_context_after)
        context = get_context_around_message(message_id, before=before, after=after)

        if context is None:
            return jsonify({"error": "message not found"}), 404

        return jsonify({"context": context})

    @app.post("/api/chat")
    def chat():
        payload = request.get_json(silent=True) or {}

        try:
            response_payload = chat_orchestrator.complete_turn(payload)
        except ChatRequestError as error:
            return jsonify({"error": error.message}), error.status_code
        except RuntimeError as error:
            return jsonify({"error": str(error)}), 502

        return jsonify(response_payload)

    @app.post("/api/chat/stream")
    def chat_stream():
        payload = request.get_json(silent=True) or {}

        @stream_with_context
        def generate():
            try:
                for event in chat_orchestrator.stream_turn(payload):
                    yield encode_stream_event(event["event"], event["data"])
            except ChatRequestError as error:
                yield encode_stream_event("error", {"error": error.message})
            except RuntimeError as error:
                yield encode_stream_event("error", {"error": str(error)})

        return Response(generate(), mimetype="application/x-ndjson")

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
