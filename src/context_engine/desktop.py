from __future__ import annotations

import queue
import threading
from pathlib import Path
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

from .engine import ContextEngine
from .models import RankedChunk


def format_chunk_title(index: int, item: RankedChunk) -> str:
    display_path = item.chunk.file_path.as_posix()
    return (
        f"{index}. {display_path} "
        f"[{item.chunk.start_line}-{item.chunk.end_line}] "
        f"score={item.score:.4f}"
    )


class DesktopApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("MyCodeIDE Context Engine")
        self.root.geometry("1440x920")
        self.root.minsize(1100, 760)

        self.engine = ContextEngine(config_path=Path("config.toml"))
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.ranked_chunks: list[RankedChunk] = []
        self.current_root: Path | None = None

        self.root_path_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Select a project folder to begin.")
        self.files_var = tk.StringVar(value="0")
        self.chunks_var = tk.StringVar(value="0")
        self.matches_var = tk.StringVar(value="0")
        self.top_k_var = tk.StringVar(value="8")
        self.mode_var = tk.StringVar(value="query")
        self.use_embeddings_var = tk.BooleanVar(value=False)

        self._build_ui()
        self.root.after(120, self._process_events)

    def _build_ui(self) -> None:
        self.root.configure(bg="#e9e2d4")

        shell = ttk.Frame(self.root, padding=14)
        shell.pack(fill="both", expand=True)

        default_font = tkfont.nametofont("TkDefaultFont")
        default_font.configure(family="Segoe UI", size=10)
        text_font = tkfont.nametofont("TkTextFont")
        text_font.configure(family="Segoe UI", size=10)
        fixed_font = tkfont.nametofont("TkFixedFont")
        fixed_font.configure(family="Consolas", size=10)

        header_font = tkfont.Font(family="Segoe UI", size=20, weight="bold")
        section_font = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        metric_font = tkfont.Font(family="Segoe UI", size=16, weight="bold")
        button_font = tkfont.Font(family="Segoe UI", size=10, weight="bold")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#e9e2d4")
        style.configure("Surface.TFrame", background="#fbf7ef")
        style.configure("Sidebar.TFrame", background="#f6f0e5")
        style.configure("Header.TLabel", background="#fbf7ef", foreground="#17202a", font=header_font)
        style.configure("Sub.TLabel", background="#fbf7ef", foreground="#5c6670", font=default_font)
        style.configure("Section.TLabel", background="#f6f0e5", foreground="#5c6670", font=section_font)
        style.configure("MetricValue.TLabel", background="#fbf7ef", foreground="#17202a", font=metric_font)
        style.configure("MetricLabel.TLabel", background="#fbf7ef", foreground="#6d7680", font=default_font)
        style.configure("Primary.TButton", font=button_font)

        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(shell, style="Sidebar.TFrame", padding=18)
        sidebar.grid(row=0, column=0, sticky="nsw")

        content = ttk.Frame(shell, style="Surface.TFrame", padding=18)
        content.grid(row=0, column=1, sticky="nsew", padx=(14, 0))
        content.columnconfigure(0, weight=1)
        content.rowconfigure(3, weight=1)

        ttk.Label(sidebar, text="Context Engine", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            sidebar,
            text="Desktop indexing and retrieval for local codebases.",
            style="Sub.TLabel",
            wraplength=280,
        ).pack(anchor="w", pady=(4, 18))

        ttk.Label(sidebar, text="PROJECT FOLDER", style="Section.TLabel").pack(anchor="w")
        path_row = ttk.Frame(sidebar, style="Sidebar.TFrame")
        path_row.pack(fill="x", pady=(6, 0))
        self.path_entry = ttk.Entry(path_row, textvariable=self.root_path_var, width=30)
        self.path_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(path_row, text="Browse", command=self._browse_folder).pack(side="left", padx=(8, 0))

        ttk.Button(sidebar, text="Index Folder", style="Primary.TButton", command=self._start_index).pack(
            fill="x", pady=(14, 0)
        )

        metrics = ttk.Frame(sidebar, style="Sidebar.TFrame")
        metrics.pack(fill="x", pady=(18, 0))
        for idx, (value_var, label) in enumerate(
            (
                (self.files_var, "Files"),
                (self.chunks_var, "Chunks"),
                (self.matches_var, "Matches"),
            )
        ):
            card = ttk.Frame(metrics, style="Surface.TFrame", padding=12)
            card.grid(row=0, column=idx, sticky="nsew", padx=(0, 8 if idx < 2 else 0))
            metrics.columnconfigure(idx, weight=1)
            ttk.Label(card, textvariable=value_var, style="MetricValue.TLabel").pack(anchor="w")
            ttk.Label(card, text=label, style="MetricLabel.TLabel").pack(anchor="w")

        ttk.Label(sidebar, text="PROMPT", style="Section.TLabel").pack(anchor="w", pady=(18, 0))
        self.query_text = tk.Text(
            sidebar,
            height=10,
            wrap="word",
            relief="flat",
            bg="#fffdf8",
            fg="#17202a",
            insertbackground="#17202a",
            padx=10,
            pady=10,
        )
        query_frame = ttk.Frame(sidebar, style="Sidebar.TFrame")
        query_frame.pack(fill="x", pady=(6, 0))
        query_frame.columnconfigure(0, weight=1)
        self.query_text.grid(in_=query_frame, row=0, column=0, sticky="nsew")
        query_scroll = ttk.Scrollbar(query_frame, orient="vertical", command=self.query_text.yview)
        query_scroll.grid(row=0, column=1, sticky="ns")
        self.query_text.configure(yscrollcommand=query_scroll.set)
        self._bind_mousewheel(self.query_text)

        options = ttk.Frame(sidebar, style="Sidebar.TFrame")
        options.pack(fill="x", pady=(12, 0))
        ttk.Label(options, text="Top K", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(options, textvariable=self.top_k_var, width=8).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Label(options, text="Mode", style="Section.TLabel").grid(row=0, column=1, sticky="w", padx=(12, 0))
        mode_box = ttk.Combobox(
            options,
            textvariable=self.mode_var,
            values=("query", "chat"),
            state="readonly",
            width=10,
        )
        mode_box.grid(row=1, column=1, sticky="w", padx=(12, 0), pady=(6, 0))

        embedding_toggle = ttk.Checkbutton(
            sidebar,
            text="Allow embedding model",
            variable=self.use_embeddings_var,
        )
        embedding_toggle.pack(anchor="w", pady=(12, 0))
        ttk.Label(
            sidebar,
            text="Off by default. Enable this only when you want semantic embedding ranking.",
            style="Sub.TLabel",
            wraplength=290,
        ).pack(anchor="w", pady=(4, 0))

        action_row = ttk.Frame(sidebar, style="Sidebar.TFrame")
        action_row.pack(fill="x", pady=(14, 0))
        ttk.Button(action_row, text="Run", command=self._start_run).pack(side="left", fill="x", expand=True)
        ttk.Button(action_row, text="Reload Config", command=self._reload_config).pack(side="left", padx=(8, 0))

        status = ttk.Label(sidebar, textvariable=self.status_var, style="Sub.TLabel", wraplength=290, justify="left")
        status.pack(anchor="w", pady=(18, 0))

        ttk.Label(content, text="Repository Context With Visible Evidence", style="Header.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            content,
            text="Open a folder directly from disk, index it locally, and inspect ranked chunks, context pack, and model output.",
            style="Sub.TLabel",
            wraplength=900,
        ).grid(row=1, column=0, sticky="w", pady=(4, 16))

        info_bar = ttk.Frame(content, style="Surface.TFrame")
        info_bar.grid(row=2, column=0, sticky="ew")
        info_bar.columnconfigure(0, weight=1)
        ttk.Label(info_bar, text="Indexed Root", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.root_label = ttk.Label(info_bar, text="No folder indexed.", style="Sub.TLabel", wraplength=900)
        self.root_label.grid(row=1, column=0, sticky="w", pady=(2, 0))

        panes = ttk.Panedwindow(content, orient="horizontal")
        panes.grid(row=3, column=0, sticky="nsew", pady=(16, 0))

        left = ttk.Frame(panes, style="Surface.TFrame", padding=12)
        right = ttk.Frame(panes, style="Surface.TFrame", padding=12)
        panes.add(left, weight=3)
        panes.add(right, weight=2)

        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        left.rowconfigure(3, weight=1)
        ttk.Label(left, text="Ranked Chunks", style="Section.TLabel").grid(row=0, column=0, sticky="w")

        chunk_split = ttk.Panedwindow(left, orient="vertical")
        chunk_split.grid(row=1, column=0, sticky="nsew", pady=(6, 0))

        list_frame = ttk.Frame(chunk_split, style="Surface.TFrame")
        detail_frame = ttk.Frame(chunk_split, style="Surface.TFrame")
        chunk_split.add(list_frame, weight=2)
        chunk_split.add(detail_frame, weight=3)

        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self.chunk_list = tk.Listbox(
            list_frame,
            activestyle="none",
            relief="flat",
            bg="#fffdf8",
            fg="#17202a",
            selectbackground="#d5844f",
            selectforeground="#ffffff",
            exportselection=False,
        )
        self.chunk_list.grid(row=0, column=0, sticky="nsew")
        self.chunk_list.bind("<<ListboxSelect>>", self._on_chunk_select)
        chunk_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.chunk_list.yview)
        chunk_scroll.grid(row=0, column=1, sticky="ns")
        self.chunk_list.configure(yscrollcommand=chunk_scroll.set)
        self._bind_mousewheel(self.chunk_list)

        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(1, weight=1)
        ttk.Label(detail_frame, text="Chunk Detail", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.chunk_detail = tk.Text(
            detail_frame,
            wrap="none",
            relief="flat",
            bg="#101826",
            fg="#f7f7f2",
            insertbackground="#f7f7f2",
            padx=12,
            pady=12,
        )
        self.chunk_detail.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        chunk_detail_scroll = ttk.Scrollbar(detail_frame, orient="vertical", command=self.chunk_detail.yview)
        chunk_detail_scroll.grid(row=1, column=1, sticky="ns", pady=(6, 0))
        self.chunk_detail.configure(yscrollcommand=chunk_detail_scroll.set)
        self.chunk_detail.configure(state="disabled")
        self._bind_mousewheel(self.chunk_detail)

        ttk.Label(left, text="Context Pack", style="Section.TLabel").grid(row=2, column=0, sticky="w", pady=(14, 0))
        self.context_text = tk.Text(
            left,
            wrap="word",
            relief="flat",
            bg="#fffdf8",
            fg="#17202a",
            insertbackground="#17202a",
            padx=12,
            pady=12,
        )
        self.context_text.grid(row=3, column=0, sticky="nsew", pady=(6, 0))
        context_scroll = ttk.Scrollbar(left, orient="vertical", command=self.context_text.yview)
        context_scroll.grid(row=3, column=1, sticky="ns", pady=(6, 0))
        self.context_text.configure(yscrollcommand=context_scroll.set)
        self.context_text.configure(state="disabled")
        self._bind_mousewheel(self.context_text)

        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        ttk.Label(right, text="Model Output / Notes", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.answer_text = tk.Text(
            right,
            wrap="word",
            relief="flat",
            bg="#fffdf8",
            fg="#17202a",
            insertbackground="#17202a",
            padx=12,
            pady=12,
        )
        self.answer_text.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        answer_scroll = ttk.Scrollbar(right, orient="vertical", command=self.answer_text.yview)
        answer_scroll.grid(row=1, column=1, sticky="ns", pady=(6, 0))
        self.answer_text.configure(yscrollcommand=answer_scroll.set)
        self.answer_text.configure(state="disabled")
        self._bind_mousewheel(self.answer_text)

    def _browse_folder(self) -> None:
        selected = filedialog.askdirectory(title="Select project folder")
        if selected:
            self.root_path_var.set(selected)

    def _set_busy(self, message: str) -> None:
        self.status_var.set(message)
        self.root.config(cursor="watch")

    def _clear_busy(self) -> None:
        self.root.config(cursor="")

    def _start_index(self) -> None:
        raw_path = self.root_path_var.get().strip()
        if not raw_path:
            messagebox.showerror("Missing folder", "Select a project folder first.")
            return

        root_path = Path(raw_path)
        if not root_path.exists():
            messagebox.showerror("Invalid folder", f"Folder does not exist:\n{root_path}")
            return

        self._set_busy(f"Indexing {root_path}...")
        threading.Thread(
            target=self._run_index,
            args=(root_path, self.use_embeddings_var.get()),
            daemon=True,
        ).start()

    def _run_index(self, root_path: Path, use_embeddings: bool) -> None:
        try:
            self.engine.index_codebase(root_path, use_embeddings=use_embeddings)
            self.events.put(("indexed", root_path))
        except Exception as exc:
            self.events.put(("error", f"Index failed: {exc}"))

    def _start_run(self) -> None:
        prompt = self.query_text.get("1.0", "end").strip()
        if not prompt:
            messagebox.showerror("Missing query", "Enter a query or task first.")
            return
        if not self.engine.retriever:
            messagebox.showerror("Not indexed", "Index a folder before running a query.")
            return

        try:
            top_k = int(self.top_k_var.get().strip() or "8")
            if top_k <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid top K", "Top K must be a positive integer.")
            return

        mode = self.mode_var.get()
        self._set_busy("Running retrieval..." if mode == "query" else "Calling model with retrieved context...")
        threading.Thread(target=self._run_prompt, args=(mode, prompt, top_k), daemon=True).start()

    def _run_prompt(self, mode: str, prompt: str, top_k: int) -> None:
        try:
            if mode == "chat":
                response = self.engine.chat(prompt, top_k=top_k)
            else:
                response = self.engine.query(prompt, top_k=top_k)
            self.events.put((mode, response))
        except Exception as exc:
            self.events.put(("error", f"{mode.title()} failed: {exc}"))

    def _reload_config(self) -> None:
        self._set_busy("Reloading config...")
        threading.Thread(target=self._run_reload, daemon=True).start()

    def _run_reload(self) -> None:
        try:
            self.engine.reload_config(Path("config.toml"))
            self.events.put(("reloaded", None))
        except Exception as exc:
            self.events.put(("error", f"Config reload failed: {exc}"))

    def _process_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                self._handle_event(event, payload)
        except queue.Empty:
            pass
        self.root.after(120, self._process_events)

    def _handle_event(self, event: str, payload: object) -> None:
        self._clear_busy()

        if event == "indexed":
            root_path = payload
            assert isinstance(root_path, Path)
            self.current_root = root_path
            self.root_label.config(text=str(root_path))
            self.files_var.set(str(len(self.engine.files)))
            self.chunks_var.set(str(len(self.engine.chunks)))
            self.matches_var.set("0")
            self.ranked_chunks = []
            self.chunk_list.delete(0, "end")
            self._set_text(self.chunk_detail, "Select a query result to inspect its snippet and reasons.")
            self._set_text(self.context_text, "Run a query to build a context pack.")
            self._set_text(self.answer_text, f"Indexed {len(self.engine.files)} files from:\n{root_path}")
            self.use_embeddings_var.set(self.engine.embeddings_enabled)
            self.status_var.set(
                f"Index complete. {len(self.engine.files)} files and {len(self.engine.chunks)} chunks are ready."
                f" Embeddings {'enabled' if self.engine.embeddings_enabled else 'disabled'}."
            )
            return

        if event == "query":
            response = payload
            self.files_var.set(str(response.total_files))
            self.chunks_var.set(str(response.total_chunks))
            self.matches_var.set(str(len(response.ranked_chunks)))
            self.ranked_chunks = response.ranked_chunks
            self._populate_chunks()
            self._set_text(self.context_text, response.context_pack)
            self._set_text(self.answer_text, f"Retrieved {len(response.ranked_chunks)} ranked chunks for:\n{response.query}")
            self.status_var.set(f"Query complete. {len(response.ranked_chunks)} ranked chunks returned.")
            return

        if event == "chat":
            response = payload
            query_response = self.engine.query(response.message)
            self.files_var.set(str(query_response.total_files))
            self.chunks_var.set(str(query_response.total_chunks))
            self.matches_var.set(str(len(query_response.ranked_chunks)))
            self.ranked_chunks = query_response.ranked_chunks
            self._populate_chunks()
            self._set_text(self.context_text, response.context_pack)
            model_name = response.model_name or "configured model"
            self._set_text(self.answer_text, f"{model_name}\n\n{response.answer}")
            self.status_var.set(f"Model response complete via {response.model_provider}.")
            return

        if event == "reloaded":
            self.use_embeddings_var.set(self.engine.embeddings_enabled)
            self.status_var.set("Config reloaded.")
            return

        if event == "error":
            assert isinstance(payload, str)
            self.status_var.set(payload)
            messagebox.showerror("Context Engine", payload)

    def _populate_chunks(self) -> None:
        self.chunk_list.delete(0, "end")
        for index, item in enumerate(self.ranked_chunks, start=1):
            self.chunk_list.insert("end", format_chunk_title(index, item))

        if self.ranked_chunks:
            self.chunk_list.selection_set(0)
            self.chunk_list.activate(0)
            self._show_chunk(0)
        else:
            self._set_text(self.chunk_detail, "No ranked chunks matched the current query.")

    def _on_chunk_select(self, _event: object) -> None:
        selection = self.chunk_list.curselection()
        if selection:
            self._show_chunk(selection[0])

    def _show_chunk(self, index: int) -> None:
        if index >= len(self.ranked_chunks):
            return
        item = self.ranked_chunks[index]
        detail = "\n".join(
            [
                f"File: {item.chunk.file_path}",
                f"Lines: {item.chunk.start_line}-{item.chunk.end_line}",
                f"Score: {item.score:.4f}",
                f"Reasons: {', '.join(item.reasons) if item.reasons else 'retrieval match'}",
                "",
                item.chunk.content,
            ]
        )
        self._set_text(self.chunk_detail, detail)

    def _set_text(self, widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _bind_mousewheel(self, widget: tk.Misc) -> None:
        widget.bind("<MouseWheel>", lambda event, target=widget: self._on_mousewheel(event, target), add="+")
        widget.bind("<Button-4>", lambda event, target=widget: self._on_mousewheel(event, target), add="+")
        widget.bind("<Button-5>", lambda event, target=widget: self._on_mousewheel(event, target), add="+")

    def _on_mousewheel(self, event: tk.Event, widget: tk.Misc) -> str:
        delta = getattr(event, "delta", 0)
        if delta:
            steps = -int(delta / 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
        else:
            num = getattr(event, "num", 0)
            steps = -1 if num == 4 else 1
        widget.yview_scroll(steps, "units")
        return "break"

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    DesktopApp().run()


if __name__ == "__main__":
    main()
