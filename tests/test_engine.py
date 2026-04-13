from pathlib import Path

from context_engine.config import load_app_config
from context_engine.engine import ContextEngine


def test_index_and_query(tmp_path: Path) -> None:
    source = tmp_path / "auth.py"
    source.write_text(
        "\n".join(
            [
                "import jwt",
                "",
                "def login_user(email, password):",
                "    return generate_jwt(email)",
                "",
                "def generate_jwt(subject):",
                "    return subject",
            ]
        ),
        encoding="utf-8",
    )

    engine = ContextEngine()
    engine.index_codebase(tmp_path)
    response = engine.query("fix login auth jwt bug")

    assert response.total_files == 1
    assert response.total_chunks >= 1
    assert "login_user" in response.context_pack
    assert engine.embeddings_enabled is False


def test_index_can_enable_embeddings_flag_without_changing_default(tmp_path: Path) -> None:
    source = tmp_path / "auth.py"
    source.write_text("def login_user(email, password):\n    return email\n", encoding="utf-8")

    engine = ContextEngine()
    engine.index_codebase(tmp_path, use_embeddings=True)

    assert engine.embeddings_enabled is True


def test_query_uses_hybrid_bm25_and_fuzzy_matching(tmp_path: Path) -> None:
    source = tmp_path / "authentication.py"
    source.write_text(
        "\n".join(
            [
                "def login_user(email, password):",
                "    return email",
            ]
        ),
        encoding="utf-8",
    )

    engine = ContextEngine()
    engine.index_codebase(tmp_path)
    response = engine.query("logn usr authntication", top_k=3)

    assert response.ranked_chunks
    reasons = response.ranked_chunks[0].reasons
    assert "fuzzy match" in reasons
    assert "symbol/path match" in reasons


def test_load_app_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                "[llm]",
                'provider = "openrouter"',
                'model = "openai/gpt-4o-mini"',
                'base_url = "https://openrouter.ai/api/v1"',
                "",
                "[embeddings]",
                'provider = "ollama"',
                'model = "nomic-embed-text"',
                'base_url = "http://localhost:11434"',
            ]
        ),
        encoding="utf-8",
    )

    app_config = load_app_config(config_path)

    assert app_config.llm.provider == "openrouter"
    assert app_config.embeddings.provider == "ollama"


def test_load_app_config_reads_dotenv_for_api_key(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.toml"
    dotenv_path = tmp_path / ".env"
    config_path.write_text(
        "\n".join(
            [
                "[llm]",
                'provider = "openrouter"',
                'model = "openai/gpt-4o-mini"',
                'base_url = "https://openrouter.ai/api/v1"',
                'api_key_env = "OPENROUTER_API_KEY"',
            ]
        ),
        encoding="utf-8",
    )
    dotenv_path.write_text('OPENROUTER_API_KEY = "test-key"\n', encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    app_config = load_app_config(config_path)

    assert app_config.llm.resolved_api_key() == "test-key"
