from __future__ import annotations

import os
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext

from openai import OpenAI

from agent import _choose_api_mode, run_turn_chat, run_turn_responses
from memory import MemoryStore


class AgentGui:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("My Agent UI")
        self.compact_mode = os.getenv("AGENT_GUI_COMPACT", "1") != "0"
        self._fit_window_to_screen()
        self.root.minsize(760, 520)

        self.colors = {
            "bg": "#0f1117",
            "panel": "#171a22",
            "panel_alt": "#1d2130",
            "text": "#e8ebf3",
            "muted": "#9ea7bd",
            "accent": "#4fa2ff",
            "accent_active": "#2f87ea",
            "ok": "#62d295",
            "warn": "#ffb86b",
            "user": "#7ecbff",
            "agent": "#88f1bc",
            "system": "#c7b5ff",
        }

        self.font_ui = ("Segoe UI", 9 if self.compact_mode else 10)
        self.font_ui_bold = ("Segoe UI Semibold", 9 if self.compact_mode else 10)
        self.font_chat = ("Consolas", 10 if self.compact_mode else 11)

        self.workspace_var = tk.StringVar(value=str(Path.cwd()))
        self.base_url_var = tk.StringVar(value=os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:1234/v1"))
        self.model_var = tk.StringVar(value="google/gemma-3-4b")
        self.api_mode_var = tk.StringVar(value="auto")

        self.client: OpenAI | None = None
        self.workspace = Path(self.workspace_var.get()).resolve()
        self.memory = MemoryStore(self.workspace / ".agent" / "memory.json")
        self.busy = False
        self.typing_visible = False

        self._build_ui()

    def _fit_window_to_screen(self) -> None:
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()

        target_w = min(1200, max(760, screen_w - 80))
        target_h = min(820, max(520, screen_h - 100))
        pos_x = max((screen_w - target_w) // 2, 0)
        pos_y = max((screen_h - target_h) // 2, 0)
        self.root.geometry(f"{target_w}x{target_h}+{pos_x}+{pos_y}")

    def _style_entry(self, entry: tk.Entry) -> None:
        entry.configure(
            bg=self.colors["panel_alt"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            relief="flat",
            highlightthickness=1,
            highlightbackground="#2a3143",
            highlightcolor=self.colors["accent"],
            font=self.font_ui,
        )

    def _style_button(self, button: tk.Button, primary: bool = False) -> None:
        bg = self.colors["accent"] if primary else self.colors["panel_alt"]
        fg = "#ffffff" if primary else self.colors["text"]
        active_bg = self.colors["accent_active"] if primary else "#2b3245"
        button.configure(
            bg=bg,
            fg=fg,
            activebackground=active_bg,
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            padx=8 if self.compact_mode else 10,
            pady=4 if self.compact_mode else 6,
            font=self.font_ui_bold,
            cursor="hand2",
        )

    def _build_ui(self) -> None:
        self.root.configure(bg=self.colors["bg"])

        outer_pad = 10 if self.compact_mode else 14
        panel_gap = 8 if self.compact_mode else 10

        header = tk.Frame(self.root, bg=self.colors["bg"])
        header.pack(fill="x", padx=outer_pad, pady=(8 if self.compact_mode else 14, 4 if self.compact_mode else 8))

        tk.Label(
            header,
            text="Local AI Assistant",
            bg=self.colors["bg"],
            fg=self.colors["text"],
            font=("Segoe UI Semibold", 13 if self.compact_mode else 16),
        ).pack(anchor="w")

        if not self.compact_mode:
            tk.Label(
                header,
                text="LM Studio + tool calling",
                bg=self.colors["bg"],
                fg=self.colors["muted"],
                font=self.font_ui,
            ).pack(anchor="w", pady=(2, 0))

        top = tk.Frame(self.root, bg=self.colors["panel"])
        top.pack(fill="x", padx=outer_pad, pady=(0, panel_gap))

        top.grid_columnconfigure(0, weight=0)
        top.grid_columnconfigure(1, weight=3)
        top.grid_columnconfigure(2, weight=0)
        top.grid_columnconfigure(3, weight=2)
        top.grid_columnconfigure(4, weight=0)

        tk.Label(top, text="Workspace", bg=self.colors["panel"], fg=self.colors["muted"], font=self.font_ui).grid(
            row=0, column=0, sticky="w", padx=(10, 6), pady=(7 if self.compact_mode else 10, 4 if self.compact_mode else 5)
        )
        workspace_entry = tk.Entry(top, textvariable=self.workspace_var)
        workspace_entry.grid(
            row=0, column=1, padx=6, pady=(7 if self.compact_mode else 10, 4 if self.compact_mode else 5), sticky="we"
        )
        self._style_entry(workspace_entry)

        tk.Label(top, text="Model", bg=self.colors["panel"], fg=self.colors["muted"], font=self.font_ui).grid(
            row=0, column=2, sticky="w", padx=(10, 6), pady=(7 if self.compact_mode else 10, 4 if self.compact_mode else 5)
        )
        model_entry = tk.Entry(top, textvariable=self.model_var)
        model_entry.grid(
            row=0, column=3, padx=(6, 10), pady=(7 if self.compact_mode else 10, 4 if self.compact_mode else 5), sticky="we"
        )
        self._style_entry(model_entry)

        tk.Label(top, text="Base URL", bg=self.colors["panel"], fg=self.colors["muted"], font=self.font_ui).grid(
            row=1, column=0, sticky="w", padx=(10, 6), pady=(4, 7 if self.compact_mode else 10)
        )
        base_url_entry = tk.Entry(top, textvariable=self.base_url_var)
        base_url_entry.grid(row=1, column=1, padx=6, pady=(4, 7 if self.compact_mode else 10), sticky="we")
        self._style_entry(base_url_entry)

        tk.Label(top, text="API mode", bg=self.colors["panel"], fg=self.colors["muted"], font=self.font_ui).grid(
            row=1, column=2, sticky="w", padx=(10, 6), pady=(4, 7 if self.compact_mode else 10)
        )
        mode_menu = tk.OptionMenu(top, self.api_mode_var, "auto", "chat", "responses")
        mode_menu.grid(row=1, column=3, padx=(6, 10), pady=(4, 7 if self.compact_mode else 10), sticky="ew")
        mode_menu.configure(
            bg=self.colors["panel_alt"],
            fg=self.colors["text"],
            activebackground="#2b3245",
            activeforeground=self.colors["text"],
            highlightthickness=0,
            relief="flat",
            font=self.font_ui,
        )
        mode_menu["menu"].configure(bg=self.colors["panel_alt"], fg=self.colors["text"], font=self.font_ui)

        button_col = tk.Frame(top, bg=self.colors["panel"])
        button_col.grid(
            row=0, column=4, rowspan=2, sticky="ne", padx=(4, 10), pady=(7 if self.compact_mode else 10, 7 if self.compact_mode else 10)
        )

        self.connect_btn = tk.Button(button_col, text="Connect", command=self.connect)
        self.connect_btn.pack(fill="x", pady=(0, 8))
        self._style_button(self.connect_btn, primary=True)

        self.server_btn = tk.Button(button_col, text="Start LM Server", command=self.start_lm_server)
        self.server_btn.pack(fill="x")
        self._style_button(self.server_btn, primary=False)

        chat_frame = tk.Frame(self.root, bg=self.colors["panel"])
        chat_frame.pack(fill="both", expand=True, padx=outer_pad, pady=(0, panel_gap))

        tk.Label(chat_frame, text="Chat", bg=self.colors["panel"], fg=self.colors["muted"], font=self.font_ui).pack(
            anchor="w", padx=10, pady=(7 if self.compact_mode else 10, 4)
        )

        self.chat = scrolledtext.ScrolledText(
            chat_frame,
            height=16 if self.compact_mode else 20,
            wrap="word",
            state="disabled",
            bg="#131722",
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground="#2a3143",
            highlightcolor=self.colors["accent"],
            padx=12,
            pady=12,
            font=self.font_chat,
        )
        self.chat.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.chat.tag_configure("role_user", foreground=self.colors["user"], font=("Consolas", 11, "bold"))
        self.chat.tag_configure("role_agent", foreground=self.colors["agent"], font=("Consolas", 11, "bold"))
        self.chat.tag_configure("role_system", foreground=self.colors["system"], font=("Consolas", 11, "bold"))
        self.chat.tag_configure("msg", foreground=self.colors["text"], font=self.font_chat)
        self.chat.tag_configure("typing", foreground=self.colors["muted"], font=("Consolas", 11, "italic"))

        bottom = tk.Frame(self.root, bg=self.colors["panel"])
        bottom.pack(fill="x", padx=outer_pad, pady=(0, outer_pad))

        tk.Label(bottom, text="Message", bg=self.colors["panel"], fg=self.colors["muted"], font=self.font_ui).pack(
            anchor="w", padx=10, pady=(7 if self.compact_mode else 10, 4)
        )

        self.input_box = tk.Text(
            bottom,
            height=4 if self.compact_mode else 5,
            wrap="word",
            bg=self.colors["panel_alt"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground="#2a3143",
            highlightcolor=self.colors["accent"],
            padx=10,
            pady=10,
            font=self.font_ui,
        )
        self.input_box.pack(fill="x", expand=True, padx=10, pady=(0, 8))
        self.input_box.bind("<Return>", self._send_enter)
        self.input_box.bind("<Shift-Return>", self._newline_hotkey)
        self.input_box.bind("<Control-Return>", self._send_hotkey)

        actions = tk.Frame(bottom, bg=self.colors["panel"])
        actions.pack(fill="x", padx=10, pady=(0, 10))

        self.send_btn = tk.Button(actions, text="Send", width=12, command=self.send)
        self.send_btn.pack(side="left")
        self._style_button(self.send_btn, primary=True)

        self.status_var = tk.StringVar(value="Disconnected")
        self.status_label = tk.Label(
            actions,
            textvariable=self.status_var,
            bg=self.colors["panel"],
            fg=self.colors["warn"],
            font=self.font_ui,
        )
        self.status_label.pack(side="left", padx=12)

        self._append("system", "Klik op Connect, daarna kun je chatten. Ctrl+Enter = versturen.")

    def _append(self, role: str, text: str) -> None:
        role_map = {
            "you": ("YOU", "role_user"),
            "agent": ("AGENT", "role_agent"),
            "system": ("SYSTEM", "role_system"),
        }
        label, tag = role_map.get(role, (role.upper(), "role_system"))

        self.chat.configure(state="normal")
        self.chat.insert("end", f"{label}> ", tag)
        self.chat.insert("end", f"{text}\n\n", "msg")
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _show_typing_indicator(self) -> None:
        if self.typing_visible:
            return
        self.chat.configure(state="normal")
        self.chat.mark_set("typing_start", "end-1c")
        self.chat.insert("end", "AGENT> ", "role_agent")
        self.chat.insert("end", "typing...\n\n", "typing")
        self.chat.mark_set("typing_end", "end-1c")
        self.chat.see("end")
        self.chat.configure(state="disabled")
        self.typing_visible = True

    def _clear_typing_indicator(self) -> None:
        if not self.typing_visible:
            return
        self.chat.configure(state="normal")
        try:
            self.chat.delete("typing_start", "typing_end")
        except tk.TclError:
            pass
        self.chat.configure(state="disabled")
        self.typing_visible = False

    def _send_hotkey(self, _event: tk.Event) -> str:
        self.send()
        return "break"

    def _send_enter(self, _event: tk.Event) -> str:
        self.send()
        return "break"

    def _newline_hotkey(self, _event: tk.Event) -> str | None:
        return None

    def connect(self) -> None:
        workspace = Path(self.workspace_var.get().strip() or ".").resolve()
        workspace.mkdir(parents=True, exist_ok=True)

        base_url = self.base_url_var.get().strip() or None
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key and base_url and ("localhost" in base_url.lower() or "127.0.0.1" in base_url.lower()):
            api_key = "lm-studio"

        if not api_key:
            messagebox.showerror("API key ontbreekt", "OPENAI_API_KEY is niet gezet en base-url is niet lokaal.")
            return

        self.workspace = workspace
        self.memory = MemoryStore(self.workspace / ".agent" / "memory.json")
        self.client = OpenAI(api_key=api_key, base_url=base_url)

        mode = _choose_api_mode(self.api_mode_var.get(), base_url)
        self.status_var.set(f"Connected ({mode})")
        self.status_label.configure(fg=self.colors["ok"])
        self._append("system", f"Connected. Workspace={self.workspace}")

    def start_lm_server(self) -> None:
        self.server_btn.configure(state="disabled")
        self.status_var.set("Starting LM Server...")
        self.status_label.configure(fg=self.colors["warn"])
        thread = threading.Thread(target=self._start_lm_server_worker, daemon=True)
        thread.start()

    def _start_lm_server_worker(self) -> None:
        app_path = Path(os.getenv("LOCALAPPDATA", "")) / "Programs" / "LM Studio" / "LM Studio.exe"
        lms_path = Path(os.getenv("LOCALAPPDATA", "")) / "Programs" / "LM Studio" / "resources" / "app" / ".webpack" / "lms.exe"
        if app_path.exists():
            try:
                # Start app; if already running this is harmless.
                subprocess.Popen([str(app_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(2)
            except Exception:
                pass

        if not lms_path.exists():
            self.root.after(0, self._on_lm_server_result, False, f"lms.exe niet gevonden: {lms_path}")
            return

        try:
            completed = subprocess.run(
                [str(lms_path), "server", "start"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            output = (completed.stdout or completed.stderr or "").strip()
            lower_output = output.lower()
            if completed.returncode == 0 or "already running" in lower_output:
                msg = output if output else "LM Studio server gestart."
                self.root.after(0, self._on_lm_server_result, True, msg)
                return
            self.root.after(0, self._on_lm_server_result, False, output or f"Exit code {completed.returncode}")
        except Exception as exc:
            self.root.after(0, self._on_lm_server_result, False, str(exc))

    def _on_lm_server_result(self, ok: bool, message: str) -> None:
        self.server_btn.configure(state="normal")
        if ok:
            self.status_var.set("LM Server running")
            self.status_label.configure(fg=self.colors["ok"])
            self._append("system", f"LM Server: {message}")
            return
        self.status_var.set("LM Server start failed")
        self.status_label.configure(fg=self.colors["warn"])
        self._append("system", f"LM Server error: {message}")

    def send(self) -> None:
        if self.busy:
            return
        if self.client is None:
            messagebox.showwarning("Niet verbonden", "Klik eerst op Connect.")
            return

        user_text = self.input_box.get("1.0", "end").strip()
        if not user_text:
            return

        self.input_box.delete("1.0", "end")
        self._append("you", user_text)
        self.memory.append("user", user_text)
        self.busy = True
        self.send_btn.configure(state="disabled", bg="#34496f")
        self.status_var.set("Thinking...")
        self.status_label.configure(fg=self.colors["warn"])
        self._show_typing_indicator()

        thread = threading.Thread(target=self._run_agent, args=(user_text,), daemon=True)
        thread.start()

    def _run_agent(self, user_text: str) -> None:
        assert self.client is not None
        model = self.model_var.get().strip() or "google/gemma-3-4b"
        base_url = self.base_url_var.get().strip() or None
        mode = _choose_api_mode(self.api_mode_var.get(), base_url)

        try:
            if mode == "chat":
                answer = run_turn_chat(self.client, model, user_text, self.workspace, self.memory)
            else:
                answer = run_turn_responses(self.client, model, user_text, self.workspace, self.memory)
        except Exception as exc:
            answer = f"Error: {exc}"

        self.root.after(0, self._on_agent_done, answer, mode)

    def _on_agent_done(self, answer: str, mode: str) -> None:
        self._clear_typing_indicator()
        self._append("agent", answer)
        self.memory.append("assistant", answer)
        self.busy = False
        self.send_btn.configure(state="normal", bg=self.colors["accent"])
        self.status_var.set(f"Connected ({mode})")
        self.status_label.configure(fg=self.colors["ok"])


def main() -> None:
    root = tk.Tk()
    app = AgentGui(root)
    app.connect()
    root.mainloop()


if __name__ == "__main__":
    main()
