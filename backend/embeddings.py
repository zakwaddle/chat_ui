from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

@dataclass(frozen=True)
class EmbeddingResult:
    provider: str
    model: str
    vector: list[float]


class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str

    def embed(self, text: str) -> EmbeddingResult:
        ...


class StubEmbeddingProvider:
    provider_name = "stub"
    model_name = "deterministic-hash-v1"

    def embed(self, text: str) -> EmbeddingResult:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vector = [round((byte / 127.5) - 1.0, 6) for byte in digest[:32]]
        return EmbeddingResult(self.provider_name, self.model_name, vector)


class OpenAICompatibleEmbeddingProvider:
    provider_name = "openai-compatible"

    def __init__(self, base_url: str, model: str, timeout_seconds: float) -> None:
        self.base_url = base_url
        self.model_name = model
        self.timeout_seconds = timeout_seconds

    def embed(self, text: str) -> EmbeddingResult:
        url = f"{self.base_url.rstrip('/')}/embeddings"
        payload = {"model": self.model_name, "input": text}
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"embedding server returned HTTP {error.code}: {detail}") from error
        except URLError as error:
            raise RuntimeError(f"could not reach embedding server: {error.reason}") from error
        except TimeoutError as error:
            raise RuntimeError("embedding server request timed out") from error

        return EmbeddingResult(
            self.provider_name,
            self.model_name,
            _extract_openai_embedding(data),
        )


class LlamaCppEmbeddingProvider:
    provider_name = "llama-cpp-python"

    def __init__(self, model_path: Path, context_size: int) -> None:
        self.model_path = model_path
        self.model_name = str(model_path)
        self.context_size = context_size
        self._llama = None

    def embed(self, text: str) -> EmbeddingResult:
        if self._llama is None:
            from llama_cpp import Llama

            self._llama = Llama(
                model_path=str(self.model_path),
                embedding=True,
                n_ctx=self.context_size,
                verbose=False,
            )

        data = self._llama.create_embedding(text)
        return EmbeddingResult(
            self.provider_name,
            self.model_name,
            _extract_openai_embedding(data),
        )


def _extract_openai_embedding(data: object) -> list[float]:
    try:
        vector = data["data"][0]["embedding"]  # type: ignore[index]
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError("embedding response did not include a vector") from error

    if not isinstance(vector, list) or not vector:
        raise RuntimeError("embedding response vector was empty")

    return [float(value) for value in vector]


def serialize_vector(vector: list[float]) -> str:
    return json.dumps(vector, separators=(",", ":"))


def build_embedding_provider(config=None) -> EmbeddingProvider:
    if config is None:
        try:
            from .config import load_config
        except ImportError:
            from config import load_config

        config = load_config()

    provider = config.embedding_provider
    model_path = Path(config.embedding_model_path)

    if provider == "stub":
        return StubEmbeddingProvider()

    if provider in {"openai", "openai-compatible"}:
        return OpenAICompatibleEmbeddingProvider(
            base_url=config.embedding_endpoint_url,
            model=config.embedding_model,
            timeout_seconds=config.embedding_timeout_seconds,
        )

    if provider in {"auto", "llama-cpp", "llama_cpp"} and model_path.exists():
        return LlamaCppEmbeddingProvider(
            model_path=model_path,
            context_size=config.embedding_context_size,
        )

    return StubEmbeddingProvider()
