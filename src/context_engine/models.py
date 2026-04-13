from pathlib import Path

from pydantic import BaseModel, Field


class Symbol(BaseModel):
    name: str
    kind: str
    line_start: int
    line_end: int


class FileRecord(BaseModel):
    path: Path
    language: str
    content: str
    symbols: list[Symbol] = Field(default_factory=list)
    imports: list[str] = Field(default_factory=list)


class CodeChunk(BaseModel):
    file_path: Path
    start_line: int
    end_line: int
    content: str
    symbols: list[str] = Field(default_factory=list)


class RankedChunk(BaseModel):
    chunk: CodeChunk
    score: float
    reasons: list[str] = Field(default_factory=list)


class QueryRequest(BaseModel):
    query: str
    top_k: int | None = Field(default=None, ge=1)


class ChatRequest(BaseModel):
    message: str
    top_k: int | None = Field(default=None, ge=1)


class IndexRequest(BaseModel):
    root_path: Path


class QueryResponse(BaseModel):
    query: str
    indexed_root: Path | None
    total_files: int
    total_chunks: int
    context_pack: str
    ranked_chunks: list[RankedChunk]


class ChatResponse(BaseModel):
    message: str
    indexed_root: Path | None
    model_provider: str
    model_name: str | None
    context_pack: str
    answer: str
