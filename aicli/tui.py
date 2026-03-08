"""
tui.py — F7: Full TUI for aicli using Textual.

A real terminal UI with:
  - Left sidebar: session list with live message counts
  - Main panel: scrollable conversation with role colors
  - Bottom input bar: prompt entry, multi-line support (Ctrl+Enter)
  - Status bar: active provider, model, token usage
  - Keyboard shortcuts: Ctrl+N new session, Ctrl+D delete, Ctrl+E export,
                        Ctrl+W toggle web search, Ctrl+X toggle context,
                        Ctrl+Q quit

Usage:
    aicli tui [--session NAME] [--model MODEL]
    aicli tui  (opens last session or creates new)
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import (
    Button, Footer, Header, Input, Label,
    ListItem, ListView, Markdown, Static, TextArea,
)
from textual.message import Message


# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = """
Screen {
    background: $surface;
}

#sidebar {
    width: 26;
    min-width: 26;
    border-right: solid $primary-darken-2;
    background: $surface-darken-1;
}

#sidebar-header {
    height: 3;
    content-align: center middle;
    background: $primary-darken-3;
    color: $text;
    text-style: bold;
    border-bottom: solid $primary-darken-2;
}

#session-list {
    height: 1fr;
}

#session-list > ListItem {
    padding: 0 1;
    height: 3;
    border-bottom: solid $surface-darken-2;
}

#session-list > ListItem.--highlight {
    background: $primary-darken-2;
}

#session-list > ListItem > Label {
    width: 1fr;
    overflow: hidden ellipsis;
}

#main {
    width: 1fr;
}

#chat-scroll {
    height: 1fr;
    padding: 0 1;
}

.msg-user {
    color: $accent;
    text-style: bold;
    margin-top: 1;
}

.msg-user-content {
    color: $text;
    margin-bottom: 1;
    padding-left: 2;
}

.msg-assistant {
    color: $success;
    text-style: bold;
    margin-top: 1;
}

.msg-assistant-content {
    color: $text-muted;
    margin-bottom: 1;
    padding-left: 2;
}

.msg-summary {
    color: $warning;
    text-style: italic;
    padding: 0 2;
    margin: 1 0;
}

#status-bar {
    height: 1;
    background: $primary-darken-3;
    color: $text-muted;
    padding: 0 1;
    content-align: left middle;
}

#input-area {
    height: auto;
    max-height: 8;
    border-top: solid $primary-darken-2;
    background: $surface-darken-1;
    padding: 0 1;
}

#flags-bar {
    height: 1;
    background: $surface-darken-2;
    color: $text-muted;
    padding: 0 1;
}

#prompt-input {
    height: auto;
    min-height: 1;
    border: none;
    background: $surface-darken-1;
    color: $text;
}

#thinking {
    color: $warning;
    text-style: italic;
    height: 1;
    padding: 0 1;
    display: none;
}

#thinking.visible {
    display: block;
}
"""


# ── Widgets ───────────────────────────────────────────────────────────────────

class StatusBar(Static):
    """Bottom status bar showing provider + flags."""

    provider: reactive[str] = reactive("—")
    web_on:   reactive[bool] = reactive(False)
    ctx_on:   reactive[bool] = reactive(False)
    tokens:   reactive[int]  = reactive(0)

    def render(self) -> str:
        flags = []
        if self.web_on:
            flags.append("\U0001f310 web")
        if self.ctx_on:
            flags.append("\U0001f9e0 ctx")
        flag_str = "  " + "  ".join(flags) if flags else ""
        tok_str  = f"  ~{self.tokens} tokens" if self.tokens else ""
        return f" provider: {self.provider}{flag_str}{tok_str}"


class ThinkingIndicator(Static):
    """Animated 'thinking...' indicator shown during LLM call."""
    pass


class MessageBlock(Static):
    """A single rendered message block (user or assistant)."""

    def __init__(self, role: str, content: str, timestamp: str = "") -> None:
        super().__init__()
        self.msg_role    = role
        self.msg_content = content
        self.msg_ts      = timestamp[:16] if timestamp else ""

    def compose(self) -> ComposeResult:
        ts = f"  \033[90m{self.msg_ts}\033[0m" if self.msg_ts else ""
        if self.msg_role == "user":
            yield Label(f"You{ts}", classes="msg-user")
            yield Label(self.msg_content, classes="msg-user-content")
        elif self.msg_role == "assistant":
            yield Label(f"Assistant{ts}", classes="msg-assistant")
            yield Label(self.msg_content, classes="msg-assistant-content")
        elif self.msg_role == "system" and self.msg_content.startswith("[AUTO-SUMMARY]"):
            summary_text = self.msg_content[14:].strip()
            yield Label(f"[ Summary: {summary_text[:120]}... ]", classes="msg-summary")


# ── Main TUI App ──────────────────────────────────────────────────────────────

class AicliTUI(App):
    """aicli Terminal UI — full session manager + chat interface."""

    CSS = CSS

    BINDINGS = [
        Binding("ctrl+q",     "quit",           "Quit"),
        Binding("ctrl+n",     "new_session",    "New session"),
        Binding("ctrl+d",     "delete_session", "Delete session"),
        Binding("ctrl+e",     "export_session", "Export"),
        Binding("ctrl+w",     "toggle_web",     "Toggle web"),
        Binding("ctrl+x",     "toggle_context", "Toggle ctx"),
        Binding("ctrl+s",     "summarize",      "Summarize"),
        Binding("enter",      "send",           "Send", show=False),
        Binding("ctrl+enter", "newline",        "Newline", show=False),
    ]

    # Reactive state
    active_session_id:   reactive[str | None] = reactive(None)
    active_session_name: reactive[str]        = reactive("—")
    web_enabled:  reactive[bool] = reactive(False)
    ctx_enabled:  reactive[bool] = reactive(False)
    is_thinking:  reactive[bool] = reactive(False)

    def __init__(
        self,
        initial_session: str | None = None,
        model: str | None = None,
    ) -> None:
        super().__init__()
        self._initial_session = initial_session
        self._model = model
        self._pipeline = None
        self._config   = None
        self._conn     = None
        self._sessions: list[dict] = []

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self._load_backend()
        self._refresh_session_list()
        if self._initial_session:
            self._open_session_by_name(self._initial_session)
        elif self._sessions:
            self._open_session(self._sessions[0])
        self._update_status()

    def _load_backend(self) -> None:
        from aicli.config import load_config
        from aicli.db.chat_db import get_connection
        from aicli.providers.pipeline import ProviderPipeline
        self._config = load_config()
        self._conn   = get_connection()
        try:
            self._pipeline = ProviderPipeline(
                provider_chain=self._config["provider_chain"],
                cooldown_seconds=self._config["cooldown_seconds"],
                max_retries_per_provider=self._config["max_retries_per_provider"],
                show_provider=False,
            )
        except Exception:
            self._pipeline = None

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            # Sidebar
            with Vertical(id="sidebar"):
                yield Static("aicli sessions", id="sidebar-header")
                yield ListView(id="session-list")
            # Main area
            with Vertical(id="main"):
                yield ScrollableContainer(id="chat-scroll")
                yield Static("", id="thinking", classes="")
                yield Static(self._flags_text(), id="flags-bar")
                with Vertical(id="input-area"):
                    yield Input(placeholder='Type a message… (Enter=send, Ctrl+W=web, Ctrl+X=ctx)', id="prompt-input")
        yield StatusBar(id="status-bar")
        yield Footer()

    def _flags_text(self) -> str:
        parts = []
        if self.web_enabled:
            parts.append("\033[32m[web ON]\033[0m")
        if self.ctx_enabled:
            parts.append("\033[32m[ctx ON]\033[0m")
        if not parts:
            parts.append("\033[90m[web off] [ctx off]\033[0m")
        return "  " + "  ".join(parts)

    # ── Session management ────────────────────────────────────────────────────

    def _refresh_session_list(self) -> None:
        from aicli.db.chat_db import list_sessions
        self._sessions = list_sessions(self._conn)
        lv = self.query_one("#session-list", ListView)
        lv.clear()
        for s in self._sessions:
            name  = s["name"] or s["id"][:8]
            count = s.get("message_count", 0)
            item  = ListItem(Label(f"{name[:18]}\n\033[90m{count} msgs\033[0m"))
            item.data = s  # type: ignore[attr-defined]
            lv.append(item)

    def _open_session(self, session: dict) -> None:
        self.active_session_id   = session["id"]
        self.active_session_name = session.get("name") or session["id"][:8]
        self._render_chat()
        self.sub_title = self.active_session_name

    def _open_session_by_name(self, name: str) -> None:
        for s in self._sessions:
            if s["name"] == name or s["id"] == name:
                self._open_session(s)
                return
        # Create it
        self._create_session(name)

    def _create_session(self, name: str | None = None) -> None:
        import uuid
        from aicli.db.chat_db import ensure_session
        new_id   = str(uuid.uuid4())
        new_name = name or f"session-{new_id[:8]}"
        ensure_session(self._conn, new_id, new_name)
        self._refresh_session_list()
        for s in self._sessions:
            if s["id"] == new_id:
                self._open_session(s)
                break

    def _render_chat(self) -> None:
        """Clear and re-render the chat scroll area for the active session."""
        if not self.active_session_id:
            return
        from aicli.db.chat_db import load_messages
        messages = load_messages(self._conn, self.active_session_id)

        scroll = self.query_one("#chat-scroll", ScrollableContainer)
        scroll.remove_children()

        for msg in messages:
            block = MessageBlock(msg["role"], str(msg["content"]), msg.get("timestamp", ""))
            scroll.mount(block)

        # Scroll to bottom
        self.call_after_refresh(scroll.scroll_end, animate=False)

    def _update_status(self) -> None:
        try:
            bar = self.query_one("#status-bar", StatusBar)
            provider = self._pipeline.last_provider if self._pipeline else "—"
            bar.provider = provider or "—"
            bar.web_on   = self.web_enabled
            bar.ctx_on   = self.ctx_enabled
        except NoMatches:
            pass

    # ── Input handling ────────────────────────────────────────────────────────

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        session = getattr(item, "data", None)
        if session:
            self._open_session(session)

    async def action_send(self) -> None:
        inp = self.query_one("#prompt-input", Input)
        prompt = inp.value.strip()
        if not prompt or self.is_thinking or not self.active_session_id:
            return
        inp.value = ""
        await self._send_message(prompt)

    def action_newline(self) -> None:
        inp = self.query_one("#prompt-input", Input)
        inp.value += "\n"

    # ── LLM call ──────────────────────────────────────────────────────────────

    async def _send_message(self, prompt: str) -> None:
        if not self._pipeline:
            self._append_message("system", "[Error: no provider available]")
            return

        # Save user message
        from aicli.db.chat_db import save_message, load_messages
        save_message(self._conn, self.active_session_id, "user", prompt)

        scroll = self.query_one("#chat-scroll", ScrollableContainer)
        scroll.mount(MessageBlock("user", prompt))
        self.call_after_refresh(scroll.scroll_end, animate=False)

        # Show thinking indicator
        self.is_thinking = True
        try:
            thinking = self.query_one("#thinking", Static)
            thinking.update("  \U0001f4ad thinking...")
            thinking.add_class("visible")
        except NoMatches:
            pass

        # Build messages for provider
        from aicli.role import get_role
        role    = get_role("default")
        history = load_messages(self._conn, self.active_session_id)
        msgs: list[dict] = []
        if role.system_prompt:
            msgs.append({"role": "system", "content": role.system_prompt})

        # Inject web results
        if self.web_enabled:
            try:
                from aicli.web import web_search
                web_block = await web_search(prompt)
                if web_block:
                    msgs.append({"role": "system", "content": web_block})
            except Exception:
                pass

        # Inject RAG context
        if self.ctx_enabled:
            try:
                from aicli.config import CHROMA_DIR
                from aicli.context.retriever import ContextRetriever
                retriever = ContextRetriever(CHROMA_DIR)
                ctx_block = retriever.retrieve(prompt)
                if ctx_block:
                    msgs.append({"role": "system", "content": ctx_block})
            except Exception:
                pass

        for m in history:
            if isinstance(m["content"], str):
                msgs.append({"role": m["role"], "content": m["content"]})

        # Stream response
        chunks: list[str] = []
        try:
            async for chunk in self._pipeline.stream(msgs, model=self._model):
                chunks.append(chunk)
        except Exception as e:
            chunks = [f"[Error: {e}]"]

        response = "".join(chunks).strip()
        save_message(self._conn, self.active_session_id, "assistant", response)

        # Hide thinking, show response
        try:
            thinking = self.query_one("#thinking", Static)
            thinking.remove_class("visible")
        except NoMatches:
            pass
        self.is_thinking = False

        scroll.mount(MessageBlock("assistant", response))
        self.call_after_refresh(scroll.scroll_end, animate=False)

        self._refresh_session_list()
        self._update_status()

    def _append_message(self, role: str, content: str) -> None:
        scroll = self.query_one("#chat-scroll", ScrollableContainer)
        scroll.mount(MessageBlock(role, content))
        self.call_after_refresh(scroll.scroll_end, animate=False)

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_new_session(self) -> None:
        self._create_session()

    def action_delete_session(self) -> None:
        if not self.active_session_id:
            return
        from aicli.db.chat_db import delete_session
        delete_session(self._conn, self.active_session_id)
        self.active_session_id   = None
        self.active_session_name = "—"
        self._refresh_session_list()
        if self._sessions:
            self._open_session(self._sessions[0])
        else:
            scroll = self.query_one("#chat-scroll", ScrollableContainer)
            scroll.remove_children()

    def action_export_session(self) -> None:
        if not self.active_session_id:
            return
        from aicli.db.chat_db import load_messages, load_latest_summary
        from aicli.handlers.export import _to_markdown
        messages = load_messages(self._conn, self.active_session_id)
        summary  = load_latest_summary(self._conn, self.active_session_id)
        name     = self.active_session_name
        content  = _to_markdown(name, self.active_session_id, messages, summary, include_summary=True)
        out_path = Path.home() / f"aicli-{name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
        out_path.write_text(content)
        self._append_message("system", f"[Exported to {out_path}]")

    def action_toggle_web(self) -> None:
        self.web_enabled = not self.web_enabled
        try:
            self.query_one("#flags-bar", Static).update(self._flags_text())
        except NoMatches:
            pass
        self._update_status()

    def action_toggle_context(self) -> None:
        self.ctx_enabled = not self.ctx_enabled
        try:
            self.query_one("#flags-bar", Static).update(self._flags_text())
        except NoMatches:
            pass
        self._update_status()

    def action_summarize(self) -> None:
        if not self.active_session_id:
            return
        self.call_later(self._run_summarize)

    async def _run_summarize(self) -> None:
        if not self._pipeline or not self.active_session_id:
            return
        from aicli.db.chat_db import load_messages, save_summary
        from aicli.context.manager import ContextManager
        messages = load_messages(self._conn, self.active_session_id)
        if len(messages) < 4:
            self._append_message("system", "[Need at least 4 messages to summarize]")
            return
        self._append_message("system", "[ Summarizing... ]")
        config = self._config or {}
        ctx = ContextManager(
            session_id=self.active_session_id,
            pipeline=self._pipeline,
            config=config,
            db_path=None,
        )
        try:
            summary = await ctx.summarize_now(messages)
            if summary:
                save_summary(self._conn, self.active_session_id, summary, 0, len(messages))
                self._append_message("system", f"[AUTO-SUMMARY] {summary}")
        except Exception as e:
            self._append_message("system", f"[Summarize failed: {e}]")


# ── Entry point ───────────────────────────────────────────────────────────────

def run_tui(session: str | None = None, model: str | None = None) -> None:
    """Launch the TUI. Called from app.py `aicli tui` command."""
    app = AicliTUI(initial_session=session, model=model)
    app.run()
