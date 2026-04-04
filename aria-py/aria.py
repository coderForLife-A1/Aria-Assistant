"""
ARIA - Adaptive Reasoning & Intelligence Assistant
A locally-run AI companion desktop app.
"""

import customtkinter as ctk
import threading
import json
import os
import sys
import subprocess
import webbrowser
import urllib.request
import urllib.error
import urllib.parse
import re
import platform
from pathlib import Path
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
APP_NAME = "ARIA"
OLLAMA_API_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL_NAME = "aria-gemma"
CONFIG_FILE = Path.home() / ".aria_config.json"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

COLORS = {
    "bg":         "#0a0a0f",
    "surface":    "#111118",
    "card":       "#16161f",
    "border":     "#222230",
    "accent":     "#7c6dfa",
    "accent2":    "#f06292",
    "text":       "#e8e6f0",
    "muted":      "#6e6a80",
    "user_msg":   "#1e1b30",
    "aria_msg":   "#13131a",
    "success":    "#4ade80",
    "error":      "#f87171",
    "user_text":  "#d4cfff",
}

SYSTEM_PROMPT = f"""You are ARIA (Adaptive Reasoning & Intelligence Assistant), a warm, witty, and genuinely helpful AI companion running locally on the user's computer.

System: Platform={platform.system()}, User={os.getlogin() if hasattr(os, 'getlogin') else 'User'}, Home={Path.home()}

You can perform REAL system actions. When the user wants to open something, respond with an action tag FIRST, then your message.

Action format (put at the very START of your response):
[ACTION:open_url:https://...]
[ACTION:open_file:/path/to/file]
[ACTION:open_folder:/path/to/folder]  
[ACTION:open_app:appname]
[ACTION:run_cmd:shell command]
[ACTION:search:search query]

Platform-specific app commands:
- Windows: notepad, calc, mspaint, explorer, chrome, code
- Mac: open -a "App Name"
- Linux: gedit, gnome-calculator, nautilus, code

Rules:
- Be warm, conversational, and friendly — like a smart best friend
- Use light humor when appropriate
- Always confirm what action you're doing naturally in your reply
- For the home/downloads folder: use the actual path from system info above
- NEVER be robotic. You have real personality!
- Keep responses concise but never cold"""

# ── Config I/O ────────────────────────────────────────────────────────────────

def load_config():
    try:
        if CONFIG_FILE.exists():
            return json.loads(CONFIG_FILE.read_text())
    except Exception:
        pass
    return {}

def save_config(data):
    CONFIG_FILE.write_text(json.dumps(data, indent=2))

# ── Local Gemma (Ollama) ─────────────────────────────────────────────────────

def find_modelfile_path():
    candidates = [
        Path(__file__).resolve().parent / "Modelfile",
        Path(__file__).resolve().parent / "Modelfile.txt",
        Path.cwd() / "Modelfile",
        Path.cwd() / "Modelfile.txt",
    ]

    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "Modelfile")
        candidates.append(Path(sys.executable).resolve().parent / "Modelfile.txt")

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None

def ensure_ollama_model():
    """Ensure Ollama is installed and the local Gemma model is created from Modelfile."""
    modelfile_path = find_modelfile_path()
    if not modelfile_path:
        raise RuntimeError("Missing Modelfile.txt in app folder.")

    try:
        check = subprocess.run(
            ["ollama", "show", OLLAMA_MODEL_NAME],
            capture_output=True, text=True, timeout=20
        )
        if check.returncode == 0:
            return
    except FileNotFoundError:
        raise RuntimeError("Ollama not found. Install Ollama and run it locally.")

    create = subprocess.run(
        ["ollama", "create", OLLAMA_MODEL_NAME, "-f", modelfile_path.name],
        cwd=str(modelfile_path.parent),
        capture_output=True, text=True, timeout=1800
    )
    if create.returncode != 0:
        details = create.stderr.strip() or create.stdout.strip() or "unknown error"
        raise RuntimeError(f"Failed to create model '{OLLAMA_MODEL_NAME}': {details}")


def call_gemma_local(history):
    """Call local Gemma through Ollama chat API."""
    body = json.dumps({
        "model": OLLAMA_MODEL_NAME,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + history,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 1000,
        },
    }).encode()

    req = urllib.request.Request(
        OLLAMA_API_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read())

    if "message" in data and "content" in data["message"]:
        return data["message"]["content"]
    if "error" in data:
        raise RuntimeError(data["error"])
    raise RuntimeError(f"Unexpected Ollama response: {data}")

# ── System Actions ────────────────────────────────────────────────────────────

def execute_action(action_str):
    """Parse and execute [ACTION:type:value] strings."""
    match = re.match(r'\[ACTION:(\w+):(.+?)\]', action_str.strip())
    if not match:
        return None
    kind, value = match.group(1), match.group(2)
    sys_platform = platform.system()

    try:
        if kind == "open_url":
            webbrowser.open(value)
            return f"Opened {value}"

        elif kind == "open_file":
            path = os.path.expanduser(value)
            if sys_platform == "Windows":
                os.startfile(path)
            elif sys_platform == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
            return f"Opened file: {path}"

        elif kind == "open_folder":
            path = os.path.expanduser(value)
            if sys_platform == "Windows":
                subprocess.Popen(["explorer", path])
            elif sys_platform == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
            return f"Opened folder: {path}"

        elif kind == "open_app":
            if sys_platform == "Windows":
                subprocess.Popen(value, shell=True)
            elif sys_platform == "Darwin":
                subprocess.Popen(["open", "-a", value])
            else:
                subprocess.Popen(value, shell=True)
            return f"Launched {value}"

        elif kind == "run_cmd":
            result = subprocess.run(
                value, shell=True, capture_output=True, text=True, timeout=10
            )
            out = result.stdout.strip() or result.stderr.strip() or "Done"
            return out[:300]

        elif kind == "search":
            webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(value)}")
            return f"Searched: {value}"

    except Exception as e:
        return f"Action failed: {e}"

    return None

# ── Main App ──────────────────────────────────────────────────────────────────

class ARIAApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.config_data = load_config()
        self.modelfile_path = find_modelfile_path()
        self.ollama_ready = False
        self.model_bootstrap_error = None
        self.history = []
        self.thinking = False

        self.title("ARIA")
        self.geometry("420x680")
        self.minsize(360, 500)
        self.configure(fg_color=COLORS["bg"])
        self.resizable(True, True)

        # Remove default title bar on Windows for cleaner look
        if platform.system() == "Windows":
            self.overrideredirect(False)

        self._build_ui()
        self._show_chat()
        self._add_welcome()
        threading.Thread(target=self._prepare_local_model, daemon=True).start()

    def _prepare_local_model(self):
        try:
            ensure_ollama_model()
            self.modelfile_path = find_modelfile_path()
            self.ollama_ready = True
            self.after(0, lambda: self.status_label.configure(text=" ● local gemma ready", text_color=COLORS["success"]))
        except Exception as e:
            self.model_bootstrap_error = str(e)
            self.after(0, lambda: self.status_label.configure(text=" ● local model unavailable", text_color=COLORS["error"]))

    # ── UI Builder ─────────────────────────────────────────────────────────

    def _build_ui(self):
        # Title bar
        self.titlebar = ctk.CTkFrame(self, fg_color=COLORS["surface"], height=52, corner_radius=0)
        self.titlebar.pack(fill="x", side="top")
        self.titlebar.pack_propagate(False)

        tb_inner = ctk.CTkFrame(self.titlebar, fg_color="transparent")
        tb_inner.pack(fill="both", expand=True, padx=14, pady=8)

        # Left side
        left = ctk.CTkFrame(tb_inner, fg_color="transparent")
        left.pack(side="left", fill="y")

        ctk.CTkLabel(left, text="◉", font=("Arial", 18), text_color=COLORS["accent"]).pack(side="left", padx=(0,8))
        ctk.CTkLabel(left, text="ARIA", font=("Arial Black", 14), text_color=COLORS["accent"]).pack(side="left")
        self.status_label = ctk.CTkLabel(left, text=" ● online", font=("Arial", 10), text_color=COLORS["success"])
        self.status_label.pack(side="left", padx=6)

        # Right side controls
        right = ctk.CTkFrame(tb_inner, fg_color="transparent")
        right.pack(side="right", fill="y")

        ctk.CTkButton(right, text="⚙", width=30, height=30, corner_radius=8,
                      fg_color=COLORS["card"], hover_color=COLORS["border"],
                      text_color=COLORS["muted"], font=("Arial", 14),
                      command=self._open_settings).pack(side="left", padx=2)
        ctk.CTkButton(right, text="✕", width=30, height=30, corner_radius=8,
                      fg_color=COLORS["card"], hover_color="#3a1010",
                      text_color=COLORS["muted"], font=("Arial", 13),
                      command=self.quit).pack(side="left", padx=2)

        # Separator
        sep = ctk.CTkFrame(self, fg_color=COLORS["border"], height=1, corner_radius=0)
        sep.pack(fill="x")

        # Content area (swappable)
        self.content = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.content.pack(fill="both", expand=True)

        # Setup frame
        self.setup_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        self._build_setup()

        # Chat frame
        self.chat_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        self._build_chat()

    def _build_setup(self):
        f = self.setup_frame
        ctk.CTkFrame(f, fg_color="transparent", height=30).pack()

        ctk.CTkLabel(f, text="◉", font=("Arial", 52), text_color=COLORS["accent"]).pack()
        ctk.CTkLabel(f, text="Hello, I'm ARIA", font=("Arial Black", 22), text_color=COLORS["text"]).pack(pady=(8,4))
        ctk.CTkLabel(f, text="Your local AI companion.\nChat, open apps & files, search the web,\nand more — all from your desktop.",
                     font=("Arial", 12), text_color=COLORS["muted"],
                     justify="center", wraplength=300).pack(pady=(0,24))

        ctk.CTkLabel(f, text=f"Model: {OLLAMA_MODEL_NAME}", font=("Courier", 11),
                 text_color=COLORS["text"]).pack(anchor="w", padx=40, pady=(0,6))
        ctk.CTkLabel(f, text=f"Modelfile: {(self.modelfile_path.name if self.modelfile_path else 'not found')}", font=("Courier", 11),
                 text_color=COLORS["muted"]).pack(anchor="w", padx=40)

        ctk.CTkButton(f, text="Prepare Local Gemma →", width=320, height=44,
                      fg_color=COLORS["accent"], hover_color="#6a5de8",
                      font=("Arial Black", 13), corner_radius=12,
                  command=lambda: threading.Thread(target=self._prepare_local_model, daemon=True).start()).pack(padx=40, pady=(16,0))

        ctk.CTkLabel(f, text="This app runs Gemma through your local Ollama service.\nNo cloud API key is required.",
                     font=("Arial", 10), text_color=COLORS["muted"], justify="center").pack(pady=14)

        ctk.CTkButton(f, text="Open Ollama Guide", width=200, height=30,
                      fg_color="transparent", hover_color=COLORS["card"],
                      border_width=1, border_color=COLORS["border"],
                      text_color=COLORS["accent"], font=("Arial", 11),
                  command=lambda: webbrowser.open("https://ollama.com/download")).pack()

    def _build_chat(self):
        f = self.chat_frame

        # Scrollable message area
        self.msg_scroll = ctk.CTkScrollableFrame(f, fg_color=COLORS["bg"], corner_radius=0)
        self.msg_scroll.pack(fill="both", expand=True, padx=0, pady=0)

        # Quick action chips
        chips_frame = ctk.CTkFrame(f, fg_color=COLORS["surface"], corner_radius=0, height=40)
        chips_frame.pack(fill="x")
        chips_frame.pack_propagate(False)

        chips_inner = ctk.CTkFrame(chips_frame, fg_color="transparent")
        chips_inner.pack(side="left", padx=10, pady=6)

        quick_cmds = [
            ("📁 Home", f"Open my home folder at {Path.home()}"),
            ("🌐 Browser", "Open a new browser tab"),
            ("🔍 Search", "Search Google for "),
            ("🧮 Calc", "Open the calculator app"),
        ]
        for label, cmd in quick_cmds:
            ctk.CTkButton(chips_inner, text=label, width=70, height=26,
                          fg_color=COLORS["card"], hover_color=COLORS["border"],
                          text_color=COLORS["muted"], font=("Arial", 10), corner_radius=20,
                          border_width=1, border_color=COLORS["border"],
                          command=lambda c=cmd: self._send(c)).pack(side="left", padx=3)

        # Separator
        ctk.CTkFrame(f, fg_color=COLORS["border"], height=1, corner_radius=0).pack(fill="x")

        # Input row
        input_frame = ctk.CTkFrame(f, fg_color=COLORS["surface"], corner_radius=0)
        input_frame.pack(fill="x", padx=0, pady=0)

        input_inner = ctk.CTkFrame(input_frame, fg_color=COLORS["card"],
                                   corner_radius=14, border_width=1,
                                   border_color=COLORS["border"])
        input_inner.pack(fill="x", padx=12, pady=10)

        self.input_box = ctk.CTkTextbox(input_inner, height=40, fg_color="transparent",
                                         text_color=COLORS["text"], font=("Arial", 13),
                                         wrap="word", border_width=0)
        self.input_box.pack(side="left", fill="both", expand=True, padx=10, pady=6)
        self.input_box.bind("<Return>", self._on_enter)
        self.input_box.bind("<Shift-Return>", lambda e: None)

        self.send_btn = ctk.CTkButton(input_inner, text="➤", width=38, height=38,
                                       fg_color=COLORS["accent"], hover_color="#6a5de8",
                                       font=("Arial", 16), corner_radius=10,
                                       command=self._do_send)
        self.send_btn.pack(side="right", padx=6, pady=4)

    # ── Screen switching ───────────────────────────────────────────────────

    def _show_setup(self):
        self.chat_frame.pack_forget()
        self.setup_frame.pack(fill="both", expand=True)

    def _show_chat(self):
        self.setup_frame.pack_forget()
        self.chat_frame.pack(fill="both", expand=True)
        self.after(100, lambda: self.input_box.focus_set())

    # ── Local model actions ────────────────────────────────────────────────

    def _rebuild_local_model(self):
        self.ollama_ready = False
        self.model_bootstrap_error = None
        self.status_label.configure(text=" ● building local gemma...", text_color=COLORS["accent"])
        threading.Thread(target=self._prepare_local_model, daemon=True).start()

    # ── Settings dialog ────────────────────────────────────────────────────

    def _open_settings(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Settings")
        dlg.geometry("380x320")
        dlg.configure(fg_color=COLORS["surface"])
        dlg.resizable(False, False)
        dlg.grab_set()

        ctk.CTkLabel(dlg, text="⚙  Settings", font=("Arial Black", 15),
                     text_color=COLORS["text"]).pack(pady=(20,12))

        ctk.CTkLabel(dlg, text=f"Model: {OLLAMA_MODEL_NAME}", font=("Courier", 11),
                     text_color=COLORS["text"]).pack(anchor="w", padx=24, pady=(4,6))
        ctk.CTkLabel(dlg, text=f"Modelfile: {(self.modelfile_path.name if self.modelfile_path else 'not found')}", font=("Courier", 11),
                     text_color=COLORS["muted"]).pack(anchor="w", padx=24)
        ctk.CTkLabel(dlg, text="No API key needed. ARIA uses local Ollama + Gemma.",
                     font=("Arial", 11), text_color=COLORS["muted"]).pack(anchor="w", padx=24, pady=(8,14))

        def do_clear():
            self.history.clear()
            for w in self.msg_scroll.winfo_children():
                w.destroy()
            self._add_welcome()
            dlg.destroy()

        def do_rebuild():
            self._rebuild_local_model()
            dlg.destroy()

        ctk.CTkButton(dlg, text="Rebuild Local Gemma Model", width=290, height=38,
                      fg_color=COLORS["accent"], command=do_rebuild).pack(padx=24, pady=2)
        ctk.CTkButton(dlg, text="Clear Chat History", width=290, height=38,
                      fg_color="transparent", border_width=1,
                      border_color=COLORS["error"], text_color=COLORS["error"],
                      hover_color="#2a1010", command=do_clear).pack(padx=24, pady=2)
        ctk.CTkButton(dlg, text="Cancel", width=290, height=38,
                      fg_color=COLORS["card"], hover_color=COLORS["border"],
                      text_color=COLORS["muted"], command=dlg.destroy).pack(padx=24, pady=2)

    # ── Message rendering ──────────────────────────────────────────────────

    def _add_welcome(self):
        container = ctk.CTkFrame(self.msg_scroll, fg_color="transparent")
        container.pack(fill="x", pady=16, padx=16)

        ctk.CTkLabel(container, text="Hey there! 👋",
                     font=("Arial Black", 17), text_color=COLORS["accent"]).pack()
        ctk.CTkLabel(container,
                     text="I'm ARIA — your AI companion. I can chat,\nopen apps & files, search the web, and more.",
                     font=("Arial", 12), text_color=COLORS["muted"],
                     justify="center", wraplength=320).pack(pady=(4,12))

        chips = ctk.CTkFrame(container, fg_color="transparent")
        chips.pack()
        suggestions = [
            ("📁 Downloads", "Open my Downloads folder"),
            ("▶ YouTube", "Open YouTube in my browser"),
            ("✨ What can you do?", "What can you do for me?"),
            ("💡 Fun fact", "Tell me a cool fun fact"),
        ]
        for i, (label, msg) in enumerate(suggestions):
            ctk.CTkButton(chips, text=label, width=140, height=30,
                          fg_color=COLORS["card"], hover_color=COLORS["border"],
                          text_color=COLORS["muted"], font=("Arial", 11), corner_radius=20,
                          border_width=1, border_color=COLORS["border"],
                          command=lambda m=msg: self._send(m)).grid(
                              row=i//2, column=i%2, padx=4, pady=3)

    def _add_user_msg(self, text):
        outer = ctk.CTkFrame(self.msg_scroll, fg_color="transparent")
        outer.pack(fill="x", padx=12, pady=(4,0))
        ctk.CTkLabel(outer, text="YOU", font=("Arial", 9, "bold"),
                     text_color=COLORS["muted"]).pack(anchor="e")
        bubble = ctk.CTkFrame(outer, fg_color=COLORS["user_msg"],
                               corner_radius=14, border_width=1,
                               border_color="#3d3070")
        bubble.pack(anchor="e", pady=2)
        ctk.CTkLabel(bubble, text=text, font=("Arial", 13),
                     text_color=COLORS["user_text"],
                     wraplength=280, justify="right").pack(padx=12, pady=8)
        self._scroll_bottom()

    def _add_aria_msg(self, text, action_result=None):
        outer = ctk.CTkFrame(self.msg_scroll, fg_color="transparent")
        outer.pack(fill="x", padx=12, pady=(4,2))
        ctk.CTkLabel(outer, text="ARIA", font=("Arial", 9, "bold"),
                     text_color=COLORS["accent"]).pack(anchor="w")

        if action_result:
            tag = ctk.CTkFrame(outer, fg_color="#1a1830", corner_radius=20,
                                border_width=1, border_color="#3d3070")
            tag.pack(anchor="w", pady=(0,4))
            ctk.CTkLabel(tag, text=f"⚡ {action_result[:60]}",
                         font=("Arial", 10), text_color=COLORS["accent"]).pack(padx=10, pady=3)

        bubble = ctk.CTkFrame(outer, fg_color=COLORS["aria_msg"],
                               corner_radius=14, border_width=1,
                               border_color=COLORS["border"])
        bubble.pack(anchor="w", pady=2)
        ctk.CTkLabel(bubble, text=text, font=("Arial", 13),
                     text_color=COLORS["text"],
                     wraplength=300, justify="left").pack(padx=12, pady=8)
        self._scroll_bottom()

    def _add_typing(self):
        outer = ctk.CTkFrame(self.msg_scroll, fg_color="transparent")
        outer.pack(fill="x", padx=12, pady=(4,2))
        ctk.CTkLabel(outer, text="ARIA", font=("Arial", 9, "bold"),
                     text_color=COLORS["accent"]).pack(anchor="w")
        bubble = ctk.CTkFrame(outer, fg_color=COLORS["aria_msg"],
                               corner_radius=14, border_width=1,
                               border_color=COLORS["border"])
        bubble.pack(anchor="w", pady=2)
        self.typing_label = ctk.CTkLabel(bubble, text="● ● ●", font=("Arial", 14),
                                          text_color=COLORS["muted"])
        self.typing_label.pack(padx=14, pady=10)
        self._scroll_bottom()
        return outer

    def _add_error(self, msg):
        outer = ctk.CTkFrame(self.msg_scroll, fg_color="#1a0f0f",
                              corner_radius=10, border_width=1,
                              border_color="#3a1010")
        outer.pack(fill="x", padx=24, pady=4)
        ctk.CTkLabel(outer, text=f"⚠  {msg}", font=("Arial", 12),
                     text_color=COLORS["error"], wraplength=320).pack(padx=12, pady=8)
        self._scroll_bottom()

    def _scroll_bottom(self):
        self.after(50, lambda: self.msg_scroll._parent_canvas.yview_moveto(1.0))

    # ── Send logic ─────────────────────────────────────────────────────────

    def _on_enter(self, event):
        if not event.state & 0x1:  # shift not held
            self._do_send()
            return "break"

    def _do_send(self):
        text = self.input_box.get("1.0", "end").strip()
        if not text or self.thinking:
            return
        self.input_box.delete("1.0", "end")
        self._send(text)

    def _send(self, text):
        if self.thinking:
            return
        self._add_user_msg(text)
        self.history.append({"role": "user", "content": text})
        self.thinking = True
        self.send_btn.configure(state="disabled")
        self.status_label.configure(text=" ● thinking...", text_color=COLORS["accent"])

        typing_el = self._add_typing()
        threading.Thread(target=self._worker, args=(typing_el,), daemon=True).start()

    def _worker(self, typing_el):
        try:
            if not self.ollama_ready:
                ensure_ollama_model()
                self.ollama_ready = True
            reply = call_gemma_local(self.history)
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            try:
                msg = json.loads(body)["error"]["message"]
            except Exception:
                msg = str(e)
            self.after(0, lambda: self._finish(typing_el, None, error=msg))
            return
        except Exception as e:
            self.after(0, lambda: self._finish(typing_el, None, error=str(e)))
            return

        self.after(0, lambda: self._finish(typing_el, reply))

    def _finish(self, typing_el, reply, error=None):
        typing_el.destroy()
        self.thinking = False
        self.send_btn.configure(state="normal")

        if error:
            self.status_label.configure(text=" ● local model unavailable", text_color=COLORS["error"])
            self._add_error(error)
            return

        self.status_label.configure(text=" ● local gemma ready", text_color=COLORS["success"])

        # Parse action
        action_result = None
        action_match = re.match(r'^\[ACTION:(\w+):(.+?)\]\s*', reply)
        if action_match:
            action_tag = action_match.group(0).strip()
            action_result = execute_action(action_tag)
            reply = reply[len(action_match.group(0)):].strip()

        self.history.append({"role": "assistant", "content": reply})
        self._add_aria_msg(reply, action_result)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = ARIAApp()
    app.mainloop()
