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
    from .llama_manager import LlamaManagerConfig
    from .llama_manager import LlamaManagerError
    from .llama_manager import LlamaServerManager
    from .sqlite_explorer import SQLiteExplorerError
    from .sqlite_explorer import describe_table
    from .sqlite_explorer import inspect_database
    from .sqlite_explorer import list_available_databases
    from .sqlite_explorer import preview_rows
    from .tools import get_context_around_message
    from .voice import WhisperConfig
    from .voice import WhisperCppTranscriber
    from .voice import VoiceTranscriptionError
    from .voice import normalize_audio_suffix
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
    from llama_manager import LlamaManagerConfig
    from llama_manager import LlamaManagerError
    from llama_manager import LlamaServerManager
    from sqlite_explorer import SQLiteExplorerError
    from sqlite_explorer import describe_table
    from sqlite_explorer import inspect_database
    from sqlite_explorer import list_available_databases
    from sqlite_explorer import preview_rows
    from tools import get_context_around_message
    from voice import WhisperConfig
    from voice import WhisperCppTranscriber
    from voice import VoiceTranscriptionError
    from voice import normalize_audio_suffix


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
    voice_transcriber = WhisperCppTranscriber(
        WhisperConfig(
            executable_path=config.whisper_executable_path,
            model_path=config.whisper_model_path,
            ffmpeg_path=config.whisper_ffmpeg_path,
            timeout_seconds=config.whisper_timeout_seconds,
            language=config.whisper_language,
        )
    )
    llama_manager = LlamaServerManager(
        LlamaManagerConfig(
            server_path=config.llama_server_path,
            models_dir=config.llama_models_dir,
            default_model_path=config.llama_default_model_path,
            embedding_model_path=config.embedding_model_path,
            host=config.llama_host,
            port=config.llama_port,
            context_size=config.llama_context_size,
            batch_size=config.llama_batch_size,
            gpu_layers=config.llama_gpu_layers,
            threads=config.llama_threads,
            model_name=config.model_name,
            temperature=config.model_temperature,
            repeat_penalty=config.model_repeat_penalty,
            endpoint_url=config.model_endpoint_url,
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

    @app.get("/api/tools")
    def tools_index():
        return jsonify({"tools": chat_orchestrator.tool_registry.metadata()})

    @app.get("/api/sqlite/databases")
    def sqlite_databases():
        return jsonify({"databases": list_available_databases(config.database_path)})

    @app.get("/api/sqlite/schema")
    def sqlite_schema():
        database_path = request.args.get("path", "")
        try:
            return jsonify(inspect_database(database_path))
        except SQLiteExplorerError as error:
            return jsonify({"error": str(error)}), 400

    @app.get("/api/sqlite/tables/<path:table_name>")
    def sqlite_table(table_name: str):
        database_path = request.args.get("path", "")
        try:
            return jsonify(describe_table(database_path, table_name))
        except SQLiteExplorerError as error:
            return jsonify({"error": str(error)}), 400

    @app.get("/api/sqlite/tables/<path:table_name>/rows")
    def sqlite_table_rows(table_name: str):
        database_path = request.args.get("path", "")
        limit = read_request_int("limit", 25)
        try:
            return jsonify(preview_rows(database_path, table_name, limit=limit))
        except SQLiteExplorerError as error:
            return jsonify({"error": str(error)}), 400

    @app.get("/api/llama/models")
    def llama_models():
        return jsonify(llama_manager.list_models())

    @app.get("/api/llama/status")
    def llama_status():
        return jsonify(llama_manager.status())

    @app.post("/api/llama/start")
    def llama_start():
        payload = request.get_json(silent=True) or {}
        try:
            return jsonify(llama_manager.start(payload))
        except LlamaManagerError as error:
            return jsonify({"error": str(error), "status": llama_manager.status()}), 400

    @app.post("/api/llama/stop")
    def llama_stop():
        return jsonify(llama_manager.stop())

    @app.post("/api/llama/restart")
    def llama_restart():
        payload = request.get_json(silent=True) or {}
        try:
            return jsonify(llama_manager.restart(payload))
        except LlamaManagerError as error:
            return jsonify({"error": str(error), "status": llama_manager.status()}), 400

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

    @app.post("/api/voice/transcribe")
    def voice_transcribe():
        uploaded_audio = request.files.get("audio")
        if uploaded_audio is None:
            return jsonify({"error": "audio file is required"}), 400

        suffix = normalize_audio_suffix(uploaded_audio.filename or "")
        try:
            transcript = voice_transcriber.transcribe_upload(uploaded_audio.stream, suffix=suffix)
        except VoiceTranscriptionError as error:
            return jsonify({"error": str(error)}), 502

        return jsonify({"transcript": transcript})

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
