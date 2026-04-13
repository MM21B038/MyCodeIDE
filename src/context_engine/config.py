from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


LlmProvider = Literal["openai_compatible", "openrouter", "gemini", "none"]
EmbeddingProvider = Literal["openai_compatible", "ollama", "sentence_transformers", "none"]


class LlmConfig(BaseModel):
    provider: LlmProvider = "none"
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None
    timeout_seconds: float = Field(default=60.0, gt=0)
    temperature: float = Field(default=0.1, ge=0, le=2)

    def resolved_api_key(self) -> str | None:
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            return os.getenv(self.api_key_env)
        return None


class EmbeddingConfig(BaseModel):
    provider: EmbeddingProvider = "none"
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None
    timeout_seconds: float = Field(default=60.0, gt=0)

    def resolved_api_key(self) -> str | None:
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            return os.getenv(self.api_key_env)
        return None


class EngineConfig(BaseModel):
    max_files: int = Field(default=5000, ge=1)
    max_file_size_bytes: int = Field(default=256_000, ge=1024)
    default_window: int = Field(default=20, ge=1)
    top_k_chunks: int = Field(default=8, ge=1)
    top_k_files: int = Field(default=5, ge=1)
    include_extensions: tuple[str, ...] = (
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".java",
        ".go",
        ".rs",
        ".json",
        ".md",
        ".yaml",
        ".yml",
    )
    ignore_dirs: tuple[str, ...] = (
        ".git",
        ".ipynb_checkpoints",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        "dist",
        "build",
    )
    workspace_root: Path | None = None


class AppConfig(BaseModel):
    engine: EngineConfig = Field(default_factory=EngineConfig)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    embeddings: EmbeddingConfig = Field(default_factory=EmbeddingConfig)


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def load_app_config(path: Path | None = None) -> AppConfig:
    config_path = path or Path("config.toml")
    load_dotenv(config_path.with_name(".env"))
    if not config_path.exists():
        return AppConfig()

    with config_path.open("rb") as handle:
        data = tomllib.load(handle)

    return AppConfig.model_validate(data)
