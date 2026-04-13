from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from context_engine.engine import ContextEngine
from context_engine.models import ChatRequest, ChatResponse, IndexRequest, QueryRequest, QueryResponse

app = FastAPI(title="MyCodeIDE Context Engine", version="0.2.0")
engine = ContextEngine(config_path=Path("config.toml"))
UI_PATH = Path(__file__).with_name("ui.html")


@dataclass
class IndexJob:
    job_id: str
    status: str = "queued"
    stage: str = "queued"
    message: str = "Waiting to start."
    processed_files: int = 0
    total_files: int = 0
    files: int = 0
    chunks: int = 0
    root_path: str | None = None
    embeddings_enabled: bool = False
    error: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            progress = 0
            if self.status == "completed":
                progress = 100
            elif self.total_files > 0:
                progress = min(99, round((self.processed_files / self.total_files) * 100))
            return {
                "job_id": self.job_id,
                "status": self.status,
                "stage": self.stage,
                "message": self.message,
                "processed_files": self.processed_files,
                "total_files": self.total_files,
                "progress_percent": progress,
                "files": self.files,
                "chunks": self.chunks,
                "root_path": self.root_path,
                "embeddings_enabled": self.embeddings_enabled,
                "error": self.error,
            }


index_jobs: dict[str, IndexJob] = {}


def _create_job(use_embeddings: bool) -> IndexJob:
    job_id = uuid4().hex
    job = IndexJob(job_id=job_id, embeddings_enabled=use_embeddings)
    index_jobs[job_id] = job
    return job


def _start_index_job(
    job: IndexJob,
    target: Any,
    *,
    root_path: Path,
    use_embeddings: bool,
) -> None:
    def run() -> None:
        with job.lock:
            job.status = "running"
            job.stage = "indexing"
            job.message = "Indexing codebase..."

        def on_progress(processed: int, total: int, current_path: Path) -> None:
            with job.lock:
                job.total_files = total
                job.processed_files = processed
                job.message = f"Indexed {processed}/{total} files: {current_path.name}" if total else "Indexing codebase..."

        try:
            target(root_path, use_embeddings=use_embeddings, progress_callback=on_progress)
        except Exception as exc:
            with job.lock:
                job.status = "failed"
                job.stage = "failed"
                job.message = "Indexing failed."
                job.error = str(exc)
            return

        with job.lock:
            job.status = "completed"
            job.stage = "completed"
            job.message = "Indexing complete."
            job.root_path = str(engine.indexed_root) if engine.indexed_root else str(root_path)
            job.files = len(engine.files)
            job.chunks = len(engine.chunks)
            job.processed_files = job.total_files or len(engine.files)

    threading.Thread(target=run, daemon=True).start()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return UI_PATH.read_text(encoding="utf-8")


@app.get("/state")
def state() -> dict[str, str | int | bool | list[str] | None]:
    return {
        "indexed_root": str(engine.indexed_root) if engine.indexed_root else None,
        "files": len(engine.files),
        "chunks": len(engine.chunks),
        "embeddings_enabled": engine.embeddings_enabled,
        "max_files": engine.config.max_files,
        "max_file_size_bytes": engine.config.max_file_size_bytes,
        "include_extensions": list(engine.config.include_extensions),
        "ignore_dirs": list(engine.config.ignore_dirs),
    }


@app.post("/config/reload")
def reload_config() -> dict[str, str]:
    try:
        engine.reload_config(Path("config.toml"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "reloaded"}


@app.post("/index")
def index_codebase(request: IndexRequest, use_embeddings: bool = False) -> dict[str, str | int | bool]:
    if not request.root_path.exists():
        raise HTTPException(status_code=400, detail="Root path does not exist.")

    job = _create_job(use_embeddings=use_embeddings)
    _start_index_job(job, engine.index_codebase, root_path=request.root_path, use_embeddings=use_embeddings)
    return job.snapshot()


@app.post("/index/upload")
async def index_uploaded_codebase(
    root_name: str = Form(...),
    use_embeddings: bool = Form(False),
    files: list[UploadFile] = File(...),
) -> dict[str, str | int | bool | None]:
    uploaded_files: list[tuple[Path, str]] = []

    for file in files:
        relative_name = file.filename or ""
        if not relative_name:
            continue
        try:
            content = (await file.read()).decode("utf-8", errors="ignore")
        finally:
            await file.close()
        uploaded_files.append((Path(relative_name), content))

    if not uploaded_files:
        raise HTTPException(status_code=400, detail="No supported files were uploaded.")

    job = _create_job(use_embeddings=use_embeddings)

    def run_uploaded_index(
        root_path: Path,
        *,
        use_embeddings: bool,
        progress_callback,
    ) -> None:
        engine.index_uploaded_codebase(
            root_path,
            uploaded_files,
            use_embeddings=use_embeddings,
            progress_callback=progress_callback,
        )

    _start_index_job(job, run_uploaded_index, root_path=Path(root_name), use_embeddings=use_embeddings)
    return job.snapshot()


@app.get("/index/jobs/{job_id}")
def get_index_job(job_id: str) -> dict[str, Any]:
    job = index_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Index job not found.")
    return job.snapshot()


@app.post("/query", response_model=QueryResponse)
def query_context(request: QueryRequest) -> QueryResponse:
    try:
        return engine.query(request.query, top_k=request.top_k)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/chat", response_model=ChatResponse)
def chat_with_context(request: ChatRequest) -> ChatResponse:
    try:
        return engine.chat(request.message, top_k=request.top_k)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
