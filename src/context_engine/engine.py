from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable

from .builder import ContextBuilder
from .config import AppConfig, EngineConfig, load_app_config
from .graph import DependencyGraph
from .indexer import CodebaseIndexer
from .models import ChatResponse, QueryResponse
from .providers import create_embedding_provider, create_llm_provider
from .retriever import HybridRetriever


class ContextEngine:
    def __init__(
        self,
        config: EngineConfig | None = None,
        app_config: AppConfig | None = None,
        config_path: Path | None = None,
    ) -> None:
        self.app_config = app_config or load_app_config(config_path)
        self.config = config or self.app_config.engine
        self.indexed_root: Path | None = None
        self.files = []
        self.chunks = []
        self.graph = DependencyGraph()
        self.builder = ContextBuilder()
        self.llm_provider = create_llm_provider(self.app_config.llm)
        self.retriever: HybridRetriever | None = None
        self.embeddings_enabled = False

    def reload_config(self, config_path: Path | None = None) -> None:
        self.app_config = load_app_config(config_path)
        self.config = self.app_config.engine
        self.llm_provider = create_llm_provider(self.app_config.llm)
        if self.indexed_root:
            self.index_codebase(self.indexed_root, use_embeddings=self.embeddings_enabled)

    def index_codebase(
        self,
        root: Path,
        use_embeddings: bool = False,
        progress_callback: Callable[[int, int, Path], None] | None = None,
    ) -> None:
        root = root.resolve()
        indexer = CodebaseIndexer(self.config)
        files, chunks = indexer.index(root, progress_callback=progress_callback)
        self._set_index(root, files, chunks, use_embeddings=use_embeddings)

    def index_uploaded_codebase(
        self,
        virtual_root: Path,
        uploaded_files: Iterable[tuple[Path, str]],
        use_embeddings: bool = False,
        progress_callback: Callable[[int, int, Path], None] | None = None,
    ) -> None:
        indexer = CodebaseIndexer(self.config)
        files, chunks = indexer.index_uploaded(
            virtual_root,
            uploaded_files,
            progress_callback=progress_callback,
        )
        self._set_index(virtual_root, files, chunks, use_embeddings=use_embeddings)

    def _set_index(self, root: Path, files, chunks, use_embeddings: bool = False) -> None:
        self.files = files
        self.chunks = chunks
        self.graph.build(self.files)
        embedding_provider = create_embedding_provider(self.app_config.embeddings) if use_embeddings else None
        self.retriever = HybridRetriever(
            self.files,
            self.chunks,
            self.graph,
            embedding_provider=embedding_provider,
        )
        self.indexed_root = root
        self.embeddings_enabled = use_embeddings

    def query(self, query: str, top_k: int | None = None) -> QueryResponse:
        if not self.retriever:
            raise RuntimeError("Codebase is not indexed.")

        limit = top_k or self.config.top_k_chunks
        ranked = self.retriever.search(query, top_k=limit)
        context_pack = self.builder.build(query, ranked)
        return QueryResponse(
            query=query,
            indexed_root=self.indexed_root,
            total_files=len(self.files),
            total_chunks=len(self.chunks),
            context_pack=context_pack,
            ranked_chunks=ranked,
        )

    def chat(self, message: str, top_k: int | None = None) -> ChatResponse:
        response = self.query(message, top_k=top_k)
        system_prompt = (
            "You are an expert coding assistant. Use the provided repository context and be explicit when the "
            "context is insufficient."
        )
        answer = self.llm_provider.chat(
            [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"{response.context_pack}\n\nUser Message:\n{message}",
                },
            ],
            temperature=self.app_config.llm.temperature,
        )
        return ChatResponse(
            message=message,
            indexed_root=self.indexed_root,
            model_provider=self.app_config.llm.provider,
            model_name=self.app_config.llm.model,
            context_pack=response.context_pack,
            answer=answer,
        )
