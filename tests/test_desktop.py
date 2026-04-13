from pathlib import Path

from context_engine.models import CodeChunk, RankedChunk
from context_engine.desktop import format_chunk_title


def test_format_chunk_title() -> None:
    ranked = RankedChunk(
        chunk=CodeChunk(
            file_path=Path("src/app.py"),
            start_line=10,
            end_line=24,
            content="print('hello')",
            symbols=["run"],
        ),
        score=0.8123,
        reasons=["keyword overlap"],
    )

    title = format_chunk_title(2, ranked)

    assert "2." in title
    assert "src/app.py" in title
    assert "[10-24]" in title
    assert "0.8123" in title


def test_desktop_source_exposes_embedding_toggle() -> None:
    source = Path("src/context_engine/desktop.py").read_text(encoding="utf-8")

    assert "Allow embedding model" in source


def test_desktop_source_binds_scroll_support() -> None:
    source = Path("src/context_engine/desktop.py").read_text(encoding="utf-8")

    assert "_bind_mousewheel" in source
    assert "<MouseWheel>" in source
    assert "yscrollcommand" in source
