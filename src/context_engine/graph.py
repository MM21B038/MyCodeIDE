from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .models import FileRecord


class DependencyGraph:
    def __init__(self) -> None:
        self.forward: dict[Path, set[str]] = defaultdict(set)

    def build(self, files: list[FileRecord]) -> "DependencyGraph":
        self.forward.clear()
        for record in files:
            self.forward[record.path].update(record.imports)
        return self

    def neighbors(self, path: Path) -> set[str]:
        return self.forward.get(path, set())
