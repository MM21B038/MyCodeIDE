from __future__ import annotations

import ast
from pathlib import Path
from typing import Callable, Iterable

from .config import EngineConfig
from .languages import detect_language
from .models import CodeChunk, FileRecord, Symbol


class CodebaseIndexer:
    def __init__(self, config: EngineConfig) -> None:
        self.config = config

    def index(
        self,
        root: Path,
        progress_callback: Callable[[int, int, Path], None] | None = None,
    ) -> tuple[list[FileRecord], list[CodeChunk]]:
        files: list[FileRecord] = []
        chunks: list[CodeChunk] = []
        candidates = list(self._iter_files(root))
        total = len(candidates)

        for index, path in enumerate(candidates, start=1):
            content = path.read_text(encoding="utf-8", errors="ignore")
            record = self._build_file_record(path, content)
            files.append(record)
            chunks.extend(self._chunk_file(record))
            if progress_callback:
                progress_callback(index, total, path)

        return files, chunks

    def index_uploaded(
        self,
        virtual_root: Path,
        uploaded_files: Iterable[tuple[Path, str]],
        progress_callback: Callable[[int, int, Path], None] | None = None,
    ) -> tuple[list[FileRecord], list[CodeChunk]]:
        files: list[FileRecord] = []
        chunks: list[CodeChunk] = []
        accepted_files: list[tuple[Path, str]] = []

        for relative_path, content in uploaded_files:
            if len(accepted_files) >= self.config.max_files:
                break

            normalized = Path(str(relative_path).replace("\\", "/"))
            if normalized.suffix.lower() not in self.config.include_extensions:
                continue
            if any(part in self.config.ignore_dirs for part in normalized.parts):
                continue
            if len(content.encode("utf-8", errors="ignore")) > self.config.max_file_size_bytes:
                continue

            accepted_files.append((normalized, content))

        total = len(accepted_files)
        for index, (normalized, content) in enumerate(accepted_files, start=1):
            record = self._build_file_record(virtual_root / normalized, content)
            files.append(record)
            chunks.extend(self._chunk_file(record))
            if progress_callback:
                progress_callback(index, total, virtual_root / normalized)

        return files, chunks

    def _iter_files(self, root: Path):
        count = 0
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in self.config.include_extensions:
                continue
            if any(part in self.config.ignore_dirs for part in path.parts):
                continue
            try:
                if path.stat().st_size > self.config.max_file_size_bytes:
                    continue
            except OSError:
                continue
            yield path
            count += 1
            if count >= self.config.max_files:
                break

    def _build_file_record(self, path: Path, content: str) -> FileRecord:
        language = detect_language(path)
        symbols: list[Symbol] = []
        imports: list[str] = []

        if language == "python":
            symbols, imports = self._parse_python(content)

        return FileRecord(
            path=path,
            language=language,
            content=content,
            symbols=symbols,
            imports=imports,
        )

    def _parse_python(self, content: str) -> tuple[list[Symbol], list[str]]:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return [], []

        symbols: list[Symbol] = []
        imports: list[str] = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                end_lineno = getattr(node, "end_lineno", node.lineno)
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                symbols.append(
                    Symbol(
                        name=node.name,
                        kind=kind,
                        line_start=node.lineno,
                        line_end=end_lineno,
                    )
                )
            elif isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)

        return symbols, imports

    def _chunk_file(self, record: FileRecord) -> list[CodeChunk]:
        lines = record.content.splitlines()
        if not lines:
            return []

        if record.symbols:
            return [
                CodeChunk(
                    file_path=record.path,
                    start_line=symbol.line_start,
                    end_line=symbol.line_end,
                    content="\n".join(lines[symbol.line_start - 1 : symbol.line_end]),
                    symbols=[symbol.name],
                )
                for symbol in record.symbols
            ]

        window = max(self.config.default_window, 1)
        chunks: list[CodeChunk] = []
        for start in range(0, len(lines), window):
            end = min(start + window, len(lines))
            chunks.append(
                CodeChunk(
                    file_path=record.path,
                    start_line=start + 1,
                    end_line=end,
                    content="\n".join(lines[start:end]),
                    symbols=[],
                )
            )
        return chunks
