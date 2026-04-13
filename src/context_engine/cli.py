from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import ContextEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Context engine CLI")
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index", help="Index a codebase")
    index_parser.add_argument("root", type=Path)

    query_parser = subparsers.add_parser("query", help="Query indexed codebase")
    query_parser.add_argument("root", type=Path)
    query_parser.add_argument("query", type=str)
    query_parser.add_argument("--top-k", type=int, default=None)

    chat_parser = subparsers.add_parser("chat", help="Query indexed codebase and call configured LLM")
    chat_parser.add_argument("root", type=Path)
    chat_parser.add_argument("message", type=str)
    chat_parser.add_argument("--top-k", type=int, default=None)

    args = parser.parse_args()
    engine = ContextEngine(config_path=args.config)

    if args.command == "index":
        engine.index_codebase(args.root)
        print(f"Indexed {len(engine.files)} files and {len(engine.chunks)} chunks from {args.root}")
        return

    if args.command == "query":
        engine.index_codebase(args.root)
        response = engine.query(args.query, top_k=args.top_k)
        print(json.dumps(response.model_dump(mode="json"), indent=2, default=str))
        return

    if args.command == "chat":
        engine.index_codebase(args.root)
        response = engine.chat(args.message, top_k=args.top_k)
        print(json.dumps(response.model_dump(mode="json"), indent=2, default=str))


if __name__ == "__main__":
    main()
