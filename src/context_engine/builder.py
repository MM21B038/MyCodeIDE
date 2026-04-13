from __future__ import annotations

from .models import RankedChunk


class ContextBuilder:
    def build(self, query: str, chunks: list[RankedChunk]) -> str:
        lines = [
            f"User Request:\n{query}",
            "",
            "Relevant Context:",
        ]

        for index, item in enumerate(chunks, start=1):
            lines.extend(
                [
                    f"{index}. File: {item.chunk.file_path}",
                    f"   Lines: {item.chunk.start_line}-{item.chunk.end_line}",
                    f"   Score: {item.score}",
                    f"   Reasons: {', '.join(item.reasons) or 'retrieval match'}",
                    "   Snippet:",
                    self._indent(item.chunk.content.strip() or "<empty>"),
                    "",
                ]
            )

        return "\n".join(lines).rstrip()

    def _indent(self, text: str) -> str:
        return "\n".join(f"   {line}" for line in text.splitlines())
