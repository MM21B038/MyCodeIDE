from __future__ import annotations

import math
from typing import Protocol

import httpx

from .config import EmbeddingConfig, LlmConfig


class EmbeddingProvider(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...


class LlmProvider(Protocol):
    def chat(self, messages: list[dict[str, str]], temperature: float) -> str:
        ...


class NullEmbeddingProvider:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[] for _ in texts]


class NullLlmProvider:
    def chat(self, messages: list[dict[str, str]], temperature: float) -> str:
        raise RuntimeError("No LLM provider is configured.")


def raise_for_status_with_detail(response: httpx.Response, provider_name: str) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = response.text.strip()
        if response.status_code == 401:
            raise RuntimeError(
                f"{provider_name} returned 401 Unauthorized. Check the configured API key and .env loading."
            ) from exc
        if detail:
            raise RuntimeError(f"{provider_name} request failed: {response.status_code} {detail}") from exc
        raise


class OpenAICompatibleEmbeddingProvider:
    def __init__(self, config: EmbeddingConfig) -> None:
        if not config.base_url or not config.model:
            raise ValueError("OpenAI-compatible embeddings require base_url and model.")
        self.base_url = config.base_url.rstrip("/")
        self.model = config.model
        self.api_key = config.resolved_api_key()
        self.timeout = config.timeout_seconds

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/embeddings",
                headers=headers,
                json={"model": self.model, "input": texts},
            )
            raise_for_status_with_detail(response, "Embedding provider")
            data = response.json()
        return [item["embedding"] for item in data["data"]]


class OllamaEmbeddingProvider:
    def __init__(self, config: EmbeddingConfig) -> None:
        self.base_url = (config.base_url or "http://localhost:11434").rstrip("/")
        self.model = config.model or "nomic-embed-text"
        self.timeout = config.timeout_seconds

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        with httpx.Client(timeout=self.timeout) as client:
            for text in texts:
                response = client.post(
                    f"{self.base_url}/api/embed",
                    json={"model": self.model, "input": text},
                )
                if response.status_code == 404:
                    response = client.post(
                        f"{self.base_url}/api/embeddings",
                        json={"model": self.model, "prompt": text},
                    )
                raise_for_status_with_detail(response, "Ollama embeddings")
                data = response.json()
                if "embeddings" in data:
                    vectors.append(data["embeddings"][0])
                else:
                    vectors.append(data["embedding"])
        return vectors


class SentenceTransformerEmbeddingProvider:
    def __init__(self, config: EmbeddingConfig) -> None:
        if not config.model:
            raise ValueError("Sentence Transformers embeddings require a model name.")
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is not installed. Install with `pip install -e .[embeddings]`."
            ) from exc

        self.model = SentenceTransformer(config.model)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(texts, normalize_embeddings=True)
        return [vector.tolist() for vector in vectors]


class OpenAICompatibleLlmProvider:
    def __init__(self, config: LlmConfig, extra_headers: dict[str, str] | None = None) -> None:
        if not config.base_url or not config.model:
            raise ValueError("OpenAI-compatible chat requires base_url and model.")
        self.base_url = config.base_url.rstrip("/")
        self.model = config.model
        self.api_key = config.resolved_api_key()
        self.timeout = config.timeout_seconds
        self.extra_headers = extra_headers or {}

    def chat(self, messages: list[dict[str, str]], temperature: float) -> str:
        headers = {"Content-Type": "application/json", **self.extra_headers}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                },
            )
            raise_for_status_with_detail(response, "LLM provider")
            data = response.json()
        return data["choices"][0]["message"]["content"]


class GeminiLlmProvider:
    def __init__(self, config: LlmConfig) -> None:
        if not config.model:
            raise ValueError("Gemini chat requires a model.")
        self.model = config.model
        self.api_key = config.resolved_api_key()
        if not self.api_key:
            raise ValueError("Gemini chat requires an API key.")
        self.timeout = config.timeout_seconds
        self.base_url = (config.base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")

    def chat(self, messages: list[dict[str, str]], temperature: float) -> str:
        contents = []
        for message in messages:
            role = "user" if message["role"] == "user" else "model" if message["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": message["content"]}]})

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/models/{self.model}:generateContent",
                params={"key": self.api_key},
                json={
                    "contents": contents,
                    "generationConfig": {"temperature": temperature},
                },
            )
            raise_for_status_with_detail(response, "Gemini")
            data = response.json()

        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError("Gemini returned no candidates.")
        parts = candidates[0].get("content", {}).get("parts", [])
        return "\n".join(part.get("text", "") for part in parts).strip()


def create_embedding_provider(config: EmbeddingConfig) -> EmbeddingProvider:
    if config.provider == "none":
        return NullEmbeddingProvider()
    if config.provider == "openai_compatible":
        return OpenAICompatibleEmbeddingProvider(config)
    if config.provider == "ollama":
        return OllamaEmbeddingProvider(config)
    if config.provider == "sentence_transformers":
        return SentenceTransformerEmbeddingProvider(config)
    raise ValueError(f"Unsupported embedding provider: {config.provider}")


def create_llm_provider(config: LlmConfig) -> LlmProvider:
    if config.provider == "none":
        return NullLlmProvider()
    if config.provider == "openai_compatible":
        return OpenAICompatibleLlmProvider(config)
    if config.provider == "openrouter":
        return OpenAICompatibleLlmProvider(
            config,
            extra_headers={
                "HTTP-Referer": "https://mycodeide.local",
                "X-Title": "MyCodeIDE Context Engine",
            },
        )
    if config.provider == "gemini":
        return GeminiLlmProvider(config)
    raise ValueError(f"Unsupported LLM provider: {config.provider}")


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)
