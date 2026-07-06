from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from .prompt import DEFAULT_SYSTEM_PROMPT
except ImportError:
    from prompt import DEFAULT_SYSTEM_PROMPT


DEFAULT_EMBEDDING_MODEL_PATH = Path("/storage/gguf/nomic-embed-text-v2-moe.Q8_0.gguf")
DEFAULT_LLAMA_MODELS_DIR = Path("/storage/gguf")
DEFAULT_LLAMA_SERVER_PATH = Path("/home/zak/engines/llama.cpp/build/bin/llama-server")
DEFAULT_CHAT_MODEL_PATH = DEFAULT_LLAMA_MODELS_DIR / "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"
DEFAULT_WHISPER_CPP_DIR = Path("/home/zak/engines/whisper.cpp")
DEFAULT_WHISPER_EXECUTABLE_PATH = DEFAULT_WHISPER_CPP_DIR / "build/bin/whisper-cli"
DEFAULT_WHISPER_MODEL_PATH = DEFAULT_WHISPER_CPP_DIR / "models/ggml-large-v3.bin"


@dataclass(frozen=True)
class AppConfig:
    port: int
    frontend_origin: str
    database_path: Path | None
    model_endpoint_url: str
    model_name: str
    model_timeout_seconds: float
    model_temperature: float | None
    model_repeat_penalty: float | None
    use_placeholder_chat: bool
    embedding_provider: str
    embedding_model_path: Path
    embedding_endpoint_url: str
    embedding_model: str
    embedding_timeout_seconds: float
    embedding_context_size: int
    rolling_message_count: int
    retrieved_memory_count: int
    retrieval_similarity_threshold: float | None
    default_context_before: int
    default_context_after: int
    max_tool_expansion_passes: int
    system_prompt: str
    llama_server_path: Path
    llama_models_dir: Path
    llama_default_model_path: Path
    llama_host: str
    llama_port: int
    llama_context_size: int
    llama_batch_size: int
    llama_gpu_layers: int
    llama_threads: int
    whisper_executable_path: Path
    whisper_model_path: Path
    whisper_ffmpeg_path: Path
    whisper_timeout_seconds: float
    whisper_language: str


def load_config() -> AppConfig:
    model_endpoint_url = _read_str("MODEL_ENDPOINT_URL", "http://localhost:8080/v1")
    embedding_model_path = Path(_read_str("EMBEDDING_MODEL_PATH", str(DEFAULT_EMBEDDING_MODEL_PATH)))
    llama_default_model_path = Path(_read_str("LLAMA_DEFAULT_MODEL_PATH", str(DEFAULT_CHAT_MODEL_PATH)))

    database_path_raw = os.getenv("DATABASE_PATH")

    return AppConfig(
        port=_read_int("PORT", 5000, minimum=1),
        frontend_origin=_read_str("FRONTEND_ORIGIN", "*"),
        database_path=Path(database_path_raw) if database_path_raw else None,
        model_endpoint_url=model_endpoint_url,
        model_name=_read_str("MODEL_NAME", "local-placeholder-model"),
        model_timeout_seconds=_read_float("MODEL_TIMEOUT_SECONDS", 480.0),
        model_temperature=_read_optional_float("MODEL_TEMPERATURE", minimum=0.0),
        model_repeat_penalty=_read_optional_float("MODEL_REPEAT_PENALTY", minimum=0.0),
        use_placeholder_chat=_read_bool("USE_PLACEHOLDER_CHAT", False),
        embedding_provider=_read_str("EMBEDDING_PROVIDER", "auto").strip().lower(),
        embedding_model_path=embedding_model_path,
        embedding_endpoint_url=_read_str("EMBEDDING_ENDPOINT_URL", model_endpoint_url),
        embedding_model=_read_str("EMBEDDING_MODEL", embedding_model_path.name),
        embedding_timeout_seconds=_read_float("EMBEDDING_TIMEOUT_SECONDS", 60.0),
        embedding_context_size=_read_int("EMBEDDING_CONTEXT_SIZE", 512, minimum=128),
        rolling_message_count=_read_int("ROLLING_MESSAGE_COUNT", 12, minimum=1),
        retrieved_memory_count=_read_int("RETRIEVED_MEMORY_COUNT", 6, minimum=0),
        retrieval_similarity_threshold=_read_optional_float("RETRIEVAL_SIMILARITY_THRESHOLD"),
        default_context_before=_read_int("DEFAULT_CONTEXT_BEFORE", 3, minimum=0),
        default_context_after=_read_int("DEFAULT_CONTEXT_AFTER", 3, minimum=0),
        max_tool_expansion_passes=_read_int("MAX_TOOL_EXPANSION_PASSES", 1, minimum=0),
        system_prompt=_read_str("SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
        llama_server_path=Path(_read_str("LLAMA_SERVER_PATH", str(DEFAULT_LLAMA_SERVER_PATH))),
        llama_models_dir=Path(_read_str("LLAMA_MODELS_DIR", str(DEFAULT_LLAMA_MODELS_DIR))),
        llama_default_model_path=llama_default_model_path,
        llama_host=_read_str("LLAMA_HOST", "127.0.0.1"),
        llama_port=_read_int("LLAMA_PORT", 8080, minimum=1),
        llama_context_size=_read_int("LLAMA_CONTEXT_SIZE", 13000, minimum=1),
        llama_batch_size=_read_int("LLAMA_BATCH_SIZE", 2048, minimum=1),
        llama_gpu_layers=_read_int("LLAMA_GPU_LAYERS", 13, minimum=0),
        llama_threads=_read_int("LLAMA_THREADS", 40, minimum=1),
        whisper_executable_path=Path(_read_str("WHISPER_EXECUTABLE_PATH", str(DEFAULT_WHISPER_EXECUTABLE_PATH))),
        whisper_model_path=Path(_read_str("WHISPER_MODEL_PATH", str(DEFAULT_WHISPER_MODEL_PATH))),
        whisper_ffmpeg_path=Path(_read_str("WHISPER_FFMPEG_PATH", "/usr/bin/ffmpeg")),
        whisper_timeout_seconds=_read_float("WHISPER_TIMEOUT_SECONDS", 120.0),
        whisper_language=_read_str("WHISPER_LANGUAGE", "en"),
    )


def _read_str(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        return default

    return value


def _read_int(name: str, default: int, minimum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default

    if minimum is not None:
        return max(minimum, value)

    return value


def _read_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _read_optional_float(name: str, minimum: float | None = None) -> float | None:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return None

    try:
        value = float(raw_value)
    except ValueError:
        return None

    if minimum is not None:
        return max(minimum, value)

    return value


def _read_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    return raw_value.strip().lower() in {"1", "true", "yes", "on"}
