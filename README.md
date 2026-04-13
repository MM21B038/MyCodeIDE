# MyCodeIDE Context Engine

A professional starter project for the most critical subsystem in an AI coding assistant: the context engine.

## What it does

- indexes a local codebase
- extracts symbols and imports
- builds a lightweight dependency graph
- performs hybrid retrieval using lexical, structural, dependency, and optional embedding signals
- returns a compressed context pack for downstream LLM prompts
- can call a configured chat model using retrieved repository context

## Architecture

```text
API / CLI
   ->
Context Engine
   ->
Indexer -> Symbol Extractor -> Dependency Graph -> Retriever -> Ranker -> Context Builder
```

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
uvicorn context_engine.api.main:app --reload
```                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                

Desktop app:

```bash
context-engine-desktop
```

Or:

```bash
python -m context_engine.desktop
```

For local sentence-transformer embeddings:

```bash
pip install -e .[embeddings]
```

## Configuration

Copy `config.example.toml` to `config.toml` and set the providers you want.

Supported LLM providers:

- `openai_compatible`
- `openrouter`
- `gemini`
- `none`

Supported embedding providers:

- `openai_compatible`
- `ollama`
- `sentence_transformers`
- `none`

### Example: OpenAI-compatible chat + OpenAI-compatible embeddings

```toml
[llm]
provider = "openai_compatible"
model = "gpt-4o-mini"
base_url = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"

[embeddings]
provider = "openai_compatible"
model = "text-embedding-3-small"
base_url = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"
```

### Example: OpenRouter chat + Ollama embeddings

```toml
[llm]
provider = "openrouter"
model = "openai/gpt-4o-mini"
base_url = "https://openrouter.ai/api/v1"
api_key_env = "OPENROUTER_API_KEY"

[embeddings]
provider = "ollama"
model = "nomic-embed-text"
base_url = "http://localhost:11434"
```

### Example: Gemini chat + Sentence Transformers embeddings

```toml
[llm]
provider = "gemini"
model = "gemini-1.5-flash"
api_key_env = "GEMINI_API_KEY"

[embeddings]
provider = "sentence_transformers"
model = "all-MiniLM-L6-v2"
```

## Example

Index a project:

```bash
curl -X POST http://127.0.0.1:8000/index ^
  -H "Content-Type: application/json" ^
  -d "{\"root_path\":\"D:\\\\app\\\\backend\\\\MyCodeIDE\"}"
```

Query the engine:

```bash
curl -X POST http://127.0.0.1:8000/query ^
  -H "Content-Type: application/json" ^
  -d "{\"query\":\"Fix authentication bug in login API\"}"
```

Chat with the configured model:

```bash
curl -X POST http://127.0.0.1:8000/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"message\":\"Fix the authentication bug in the login API\"}"
```

## Notes

- OpenAI-compatible APIs are used for both standard OpenAI-style services and OpenRouter chat routing.
- Gemini uses its native REST API for content generation.
- Embeddings are computed directly through the configured provider and used in the retriever's semantic score.
- Python receives deeper structural analysis via the standard `ast` module. Other languages still participate through lexical indexing.
- The desktop app uses a native folder picker and indexes directly from your local filesystem instead of uploading files through the browser.
