from __future__ import annotations

import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
DEFAULT_KNOWLEDGE_SOURCES_PATH = Path.cwd() / "knowledge_sources.json"


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
    knowledge_sources_path: Path
    knowledge_sources: tuple[dict[str, str], ...]


def load_config() -> AppConfig:
    model_endpoint_url = _read_str("MODEL_ENDPOINT_URL", "http://localhost:8080/v1")
    embedding_model_path = Path(_read_str("EMBEDDING_MODEL_PATH", str(DEFAULT_EMBEDDING_MODEL_PATH)))
    llama_default_model_path = Path(_read_str("LLAMA_DEFAULT_MODEL_PATH", str(DEFAULT_CHAT_MODEL_PATH)))

    database_path_raw = os.getenv("DATABASE_PATH")
    knowledge_sources_path = Path(_read_str("KNOWLEDGE_SOURCES_PATH", str(DEFAULT_KNOWLEDGE_SOURCES_PATH)))

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
        knowledge_sources_path=knowledge_sources_path,
        knowledge_sources=merge_knowledge_sources(
            _read_knowledge_sources("KNOWLEDGE_SOURCES_JSON"),
            load_knowledge_sources_file(knowledge_sources_path),
        ),
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


def _read_knowledge_sources(name: str) -> tuple[dict[str, str], ...]:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return ()

    return parse_knowledge_sources_json(raw_value)


def parse_knowledge_sources_json(raw_value: str) -> tuple[dict[str, str], ...]:
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return ()

    if not isinstance(parsed, list):
        return ()

    sources = []
    for entry in parsed:
        normalized = normalize_knowledge_source(entry)
        if normalized is not None:
            sources.append(normalized)

    return tuple(sources)


def normalize_knowledge_source(entry: Any) -> dict[str, str] | None:
    if not isinstance(entry, dict):
        return None

    raw_path = str(entry.get("path") or "").strip()
    if not raw_path:
        return None

    source_id = str(entry.get("id") or Path(raw_path).stem or "source").strip()
    source_id = "".join(character if character.isalnum() or character in {"_", "-"} else "_" for character in source_id)
    if not source_id:
        return None

    return {
        "id": source_id,
        "path": raw_path,
        "name": str(entry.get("name") or Path(raw_path).name).strip() or Path(raw_path).name,
        "description": str(entry.get("description") or "External SQLite knowledge source").strip(),
        "permission": str(entry.get("permission") or "sqlite.read").strip() or "sqlite.read",
    }


def load_knowledge_sources_file(path: Path) -> tuple[dict[str, str], ...]:
    try:
        raw_value = path.expanduser().read_text(encoding="utf-8")
    except FileNotFoundError:
        return ()
    except OSError:
        return ()

    return parse_knowledge_sources_json(raw_value)


def save_knowledge_sources_file(path: Path, sources: tuple[dict[str, str], ...] | list[dict[str, str]]) -> None:
    normalized_sources = [source for source in (normalize_knowledge_source(source) for source in sources) if source is not None]
    resolved_path = path.expanduser()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_path.write_text(json.dumps(normalized_sources, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def merge_knowledge_sources(*source_groups: tuple[dict[str, str], ...] | list[dict[str, str]]) -> tuple[dict[str, str], ...]:
    merged: dict[str, dict[str, str]] = {}
    for sources in source_groups:
        for source in sources:
            normalized = normalize_knowledge_source(source)
            if normalized is not None:
                merged[normalized["id"]] = normalized

    return tuple(merged.values())
