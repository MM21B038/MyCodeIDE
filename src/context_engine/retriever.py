from __future__ import annotations

import difflib
import math
import re
from collections import Counter

from .graph import DependencyGraph
from .models import CodeChunk, FileRecord, RankedChunk
from .providers import EmbeddingProvider, NullEmbeddingProvider, cosine_similarity


TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
CAMEL_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z]|\d|_|$)|[A-Z]?[a-z]+|\d+")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for token in TOKEN_RE.findall(text):
        lowered = token.lower()
        tokens.append(lowered)
        for part in token.split("_"):
            if not part:
                continue
            for camel_part in CAMEL_RE.findall(part):
                normalized = camel_part.lower()
                if normalized and normalized != lowered:
                    tokens.append(normalized)
    return tokens


class HybridRetriever:
    def __init__(
        self,
        files: list[FileRecord],
        chunks: list[CodeChunk],
        graph: DependencyGraph,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.files = files
        self.chunks = chunks
        self.graph = graph
        self.embedding_provider = embedding_provider or NullEmbeddingProvider()
        self.chunk_terms = [tokenize(chunk.content) for chunk in self.chunks]
        self.document_frequency = self._compute_document_frequency()
        self.average_chunk_length = self._compute_average_chunk_length()
        self.chunk_embeddings = self._build_chunk_embeddings()

    def _compute_document_frequency(self) -> Counter[str]:
        counter: Counter[str] = Counter()
        for chunk in self.chunks:
            counter.update(set(tokenize(chunk.content)))
        return counter

    def _compute_average_chunk_length(self) -> float:
        if not self.chunk_terms:
            return 0.0
        return sum(len(terms) for terms in self.chunk_terms) / len(self.chunk_terms)

    def _build_chunk_embeddings(self) -> list[list[float]]:
        if not self.chunks:
            return []
        return self.embedding_provider.embed_texts([chunk.content for chunk in self.chunks])

    def search(self, query: str, top_k: int) -> list[RankedChunk]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        query_embedding = self.embedding_provider.embed_texts([query])[0] if self.chunk_embeddings else []
        ranked: list[RankedChunk] = []
        file_lookup = {record.path: record for record in self.files}

        for index, chunk in enumerate(self.chunks):
            bm25 = self._bm25_score(query_tokens, index)
            fuzzy = self._fuzzy_score(query_tokens, chunk, file_lookup)
            semantic = self._semantic_score(query_embedding, index)
            structural = self._structural_score(query_tokens, chunk, file_lookup)
            dependency = self._dependency_score(query_tokens, chunk, file_lookup)
            score = 0.35 * bm25 + 0.20 * fuzzy + 0.25 * semantic + 0.15 * structural + 0.05 * dependency
            if score <= 0:
                continue

            reasons: list[str] = []
            if bm25:
                reasons.append("bm25 keyword match")
            if fuzzy:
                reasons.append("fuzzy match")
            if semantic:
                reasons.append("semantic similarity")
            if structural:
                reasons.append("symbol/path match")
            if dependency:
                reasons.append("dependency hint")

            ranked.append(RankedChunk(chunk=chunk, score=round(score, 4), reasons=reasons))

        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked[:top_k]

    def _bm25_score(self, query_tokens: list[str], chunk_index: int) -> float:
        if chunk_index >= len(self.chunk_terms):
            return 0.0
        terms = self.chunk_terms[chunk_index]
        if not terms:
            return 0.0

        counts = Counter(terms)
        total_docs = max(len(self.chunks), 1)
        avg_len = max(self.average_chunk_length, 1.0)
        doc_len = len(terms)
        k1 = 1.5
        b = 0.75
        score = 0.0
        for token in query_tokens:
            df = self.document_frequency.get(token, 0)
            tf = counts[token]
            if tf == 0:
                continue
            idf = math.log(1 + ((total_docs - df + 0.5) / (df + 0.5)))
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * (doc_len / avg_len))
            score += idf * (numerator / denominator)
        return score

    def _fuzzy_score(
        self,
        query_tokens: list[str],
        chunk: CodeChunk,
        file_lookup: dict,
    ) -> float:
        candidates = set(tokenize(chunk.content))
        candidates.update(tokenize(str(chunk.file_path)))
        candidates.update(token.lower() for symbol in chunk.symbols for token in tokenize(symbol))
        record = file_lookup.get(chunk.file_path)
        if record:
            candidates.update(tokenize(" ".join(record.imports)))
        if not candidates:
            return 0.0

        score = 0.0
        for token in query_tokens:
            best = 0.0
            for candidate in candidates:
                if token == candidate:
                    best = 1.0
                    break
                ratio = difflib.SequenceMatcher(None, token, candidate).ratio()
                if ratio > best:
                    best = ratio
            if best >= 0.82:
                score += best
        return score / max(len(query_tokens), 1)

    def _semantic_score(self, query_embedding: list[float], chunk_index: int) -> float:
        if not query_embedding or chunk_index >= len(self.chunk_embeddings):
            return 0.0
        return max(cosine_similarity(query_embedding, self.chunk_embeddings[chunk_index]), 0.0)

    def _structural_score(
        self,
        query_tokens: list[str],
        chunk: CodeChunk,
        file_lookup: dict,
    ) -> float:
        score = 0.0
        path_tokens = tokenize(str(chunk.file_path))
        symbol_tokens = [token.lower() for symbol in chunk.symbols for token in tokenize(symbol)]
        for token in query_tokens:
            if token in path_tokens:
                score += 1.0
            if token in symbol_tokens:
                score += 1.5
        return score

    def _dependency_score(
        self,
        query_tokens: list[str],
        chunk: CodeChunk,
        file_lookup: dict,
    ) -> float:
        record = file_lookup.get(chunk.file_path)
        if not record:
            return 0.0
        neighbors = self.graph.neighbors(record.path)
        score = 0.0
        for token in query_tokens:
            if any(token in neighbor.lower() for neighbor in neighbors):
                score += 0.75
        return score
