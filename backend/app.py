from __future__ import annotations

import os
from dataclasses import dataclass

from flask import Flask, jsonify, request
from flask_cors import CORS

try:
    from .database import create_conversation
    from .database import create_message
    from .database import get_conversation
    from .database import init_db
    from .database import list_conversations
    from .database import list_messages
    from .database import utc_now
except ImportError:
    from database import create_conversation
    from database import create_message
    from database import get_conversation
    from database import init_db
    from database import list_conversations
    from database import list_messages
    from database import utc_now


@dataclass(frozen=True)
class ChatClientConfig:
    base_url: str
    model: str


class LocalChatClient:
    """Adapter for the future OpenAI-compatible llama.cpp client."""

    def __init__(self, config: ChatClientConfig) -> None:
        self.config = config

    def placeholder_response(self, message: str) -> str:
        if not message.strip():
            return "Send a message and I will echo a placeholder response."

        return f"Placeholder response from {self.config.model}: {message}"


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": os.getenv("FRONTEND_ORIGIN", "*")}})
    init_db()

    chat_client = LocalChatClient(
        ChatClientConfig(
            base_url=os.getenv("MODEL_ENDPOINT_URL", "http://localhost:8080/v1"),
            model=os.getenv("MODEL_NAME", "local-placeholder-model"),
        )
    )

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

        return jsonify({"message": message}), 201

    @app.post("/api/chat")
    def chat():
        payload = request.get_json(silent=True) or {}
        message = str(payload.get("message", "")).strip()

        if not message:
            return jsonify({"error": "message is required"}), 400

        now = utc_now()

        return jsonify(
            {
                "id": now,
                "role": "assistant",
                "content": chat_client.placeholder_response(message),
                "created_at": now,
            }
        )

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
