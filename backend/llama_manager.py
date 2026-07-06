from __future__ import annotations

import subprocess
import time
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


@dataclass(frozen=True)
class LlamaManagerConfig:
    server_path: Path
    models_dir: Path
    default_model_path: Path
    embedding_model_path: Path
    host: str
    port: int
    context_size: int
    batch_size: int
    gpu_layers: int
    threads: int
    model_name: str
    temperature: float | None
    repeat_penalty: float | None
    endpoint_url: str


@dataclass(frozen=True)
class LlamaLaunchConfig:
    model_path: Path
    embedding_model_path: Path
    host: str
    port: int
    context_size: int
    batch_size: int
    gpu_layers: int
    threads: int
    temperature: float | None
    repeat_penalty: float | None
    model_name: str


class LlamaManagerError(RuntimeError):
    pass


class LlamaServerManager:
    def __init__(self, config: LlamaManagerConfig) -> None:
        self.config = config
        self.process: subprocess.Popen | None = None
        self.launch_config: LlamaLaunchConfig | None = None
        self.started_at: float | None = None

    def list_models(self) -> dict[str, Any]:
        models = []
        if self.config.models_dir.exists():
            for path in sorted(self.config.models_dir.rglob("*.gguf")):
                models.append(
                    {
                        "name": path.name,
                        "path": str(path),
                        "size_bytes": path.stat().st_size,
                        "is_embedding": "embed" in path.name.lower() or "nomic" in path.name.lower(),
                    }
                )

        return {
            "models": models,
            "defaults": self.default_launch_config_payload(),
        }

    def default_launch_config_payload(self) -> dict[str, Any]:
        return launch_config_payload(
            LlamaLaunchConfig(
                model_path=self.config.default_model_path,
                embedding_model_path=self.config.embedding_model_path,
                host=self.config.host,
                port=self.config.port,
                context_size=self.config.context_size,
                batch_size=self.config.batch_size,
                gpu_layers=self.config.gpu_layers,
                threads=self.config.threads,
                temperature=self.config.temperature,
                repeat_penalty=self.config.repeat_penalty,
                model_name=self.config.model_name,
            )
        )

    def status(self) -> dict[str, Any]:
        process_state = "stopped"
        return_code = None
        pid = None
        if self.process is not None:
            return_code = self.process.poll()
            if return_code is None:
                process_state = "running"
                pid = self.process.pid
            else:
                process_state = "exited"

        endpoint_url = endpoint_url_for(self.launch_config, self.config)
        endpoint_reachable = is_endpoint_reachable(endpoint_url)
        return {
            "process_state": process_state,
            "pid": pid,
            "return_code": return_code,
            "managed": self.process is not None and return_code is None,
            "endpoint_url": endpoint_url,
            "endpoint_reachable": endpoint_reachable,
            "started_at": self.started_at,
            "launch": launch_config_payload(self.launch_config) if self.launch_config else None,
            "defaults": self.default_launch_config_payload(),
        }

    def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.process is not None and self.process.poll() is None:
            raise LlamaManagerError("llama server is already running")

        launch_config = self.read_launch_config(payload)
        if not self.config.server_path.exists():
            raise LlamaManagerError(f"llama-server not found: {self.config.server_path}")
        if not launch_config.model_path.exists():
            raise LlamaManagerError(f"model not found: {launch_config.model_path}")

        command = build_llama_server_command(self.config.server_path, launch_config)
        self.process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self.launch_config = launch_config
        self.started_at = time.time()
        return self.status()

    def stop(self) -> dict[str, Any]:
        if self.process is None or self.process.poll() is not None:
            self.process = None
            self.started_at = None
            return self.status()

        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)

        self.process = None
        self.started_at = None
        return self.status()

    def restart(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.stop()
        return self.start(payload)

    def read_launch_config(self, payload: dict[str, Any]) -> LlamaLaunchConfig:
        defaults = self.default_launch_config_payload()
        model_path = Path(read_str(payload, "model_path", defaults["model_path"]))
        embedding_model_path = Path(read_str(payload, "embedding_model_path", defaults["embedding_model_path"]))
        return LlamaLaunchConfig(
            model_path=model_path,
            embedding_model_path=embedding_model_path,
            host=read_str(payload, "host", defaults["host"]),
            port=read_int(payload, "port", defaults["port"], minimum=1),
            context_size=read_int(payload, "context_size", defaults["context_size"], minimum=1),
            batch_size=read_int(payload, "batch_size", defaults["batch_size"], minimum=1),
            gpu_layers=read_int(payload, "gpu_layers", defaults["gpu_layers"], minimum=0),
            threads=read_int(payload, "threads", defaults["threads"], minimum=1),
            temperature=read_optional_float(payload, "temperature", defaults["temperature"], minimum=0.0),
            repeat_penalty=read_optional_float(payload, "repeat_penalty", defaults["repeat_penalty"], minimum=0.0),
            model_name=read_str(payload, "model_name", defaults["model_name"]),
        )


def build_llama_server_command(server_path: Path, launch_config: LlamaLaunchConfig) -> list[str]:
    command = [
        str(server_path),
        "--model",
        str(launch_config.model_path),
        "--host",
        launch_config.host,
        "--port",
        str(launch_config.port),
        "--ctx-size",
        str(launch_config.context_size),
        "--batch-size",
        str(launch_config.batch_size),
        "--gpu-layers",
        str(launch_config.gpu_layers),
        "--threads",
        str(launch_config.threads),
        "--alias",
        launch_config.model_name,
    ]
    if launch_config.temperature is not None:
        command.extend(["--temp", str(launch_config.temperature)])
    if launch_config.repeat_penalty is not None:
        command.extend(["--repeat-penalty", str(launch_config.repeat_penalty)])

    return command


def launch_config_payload(launch_config: LlamaLaunchConfig | None) -> dict[str, Any] | None:
    if launch_config is None:
        return None

    payload = asdict(launch_config)
    payload["model_path"] = str(launch_config.model_path)
    payload["embedding_model_path"] = str(launch_config.embedding_model_path)
    return payload


def endpoint_url_for(launch_config: LlamaLaunchConfig | None, config: LlamaManagerConfig) -> str:
    if launch_config is not None:
        return f"http://{launch_config.host}:{launch_config.port}/v1"

    return config.endpoint_url


def is_endpoint_reachable(endpoint_url: str) -> bool:
    health_url = endpoint_url.rstrip("/").removesuffix("/v1") + "/health"
    try:
        with urlopen(health_url, timeout=0.5) as response:
            return 200 <= response.status < 500
    except (OSError, URLError, TimeoutError):
        return False


def read_str(payload: dict[str, Any], key: str, default: str) -> str:
    value = payload.get(key)
    if value is None or str(value).strip() == "":
        return str(default)

    return str(value).strip()


def read_int(payload: dict[str, Any], key: str, default: int, minimum: int | None = None) -> int:
    try:
        value = int(payload.get(key, default))
    except (TypeError, ValueError):
        value = int(default)

    if minimum is not None:
        return max(minimum, value)

    return value


def read_optional_float(
    payload: dict[str, Any],
    key: str,
    default: float | None,
    minimum: float | None = None,
) -> float | None:
    raw_value = payload.get(key, default)
    if raw_value is None or raw_value == "":
        return None

    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return default

    if minimum is not None:
        return max(minimum, value)

    return value
