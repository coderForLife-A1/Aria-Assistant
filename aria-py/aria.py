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
import time
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
    cpu_threads = max(1, (os.cpu_count() or 4))
    body = json.dumps({
        "model": OLLAMA_MODEL_NAME,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + history,
        "stream": False,
        "keep_alive": "30m",
        "options": {
            "temperature": 0.7,
            "num_predict": 1000,
            "num_thread": cpu_threads,
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


def call_gemma_local_stream(history, on_chunk):
    """Call local Gemma through Ollama chat API with streamed chunks."""
    cpu_threads = max(1, (os.cpu_count() or 4))
    body = json.dumps({
        "model": OLLAMA_MODEL_NAME,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + history,
        "stream": True,
        "keep_alive": "30m",
        "options": {
            "temperature": 0.7,
            "num_predict": 1000,
            "num_thread": cpu_threads,
        },
    }).encode()

    req = urllib.request.Request(
        OLLAMA_API_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    full_text = ""
    with urllib.request.urlopen(req, timeout=180) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            if getattr(on_chunk, "should_stop", None) and on_chunk.should_stop():
                break
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            if "error" in data:
                raise RuntimeError(data["error"])

            piece = data.get("message", {}).get("content", "")
            if piece:
                full_text += piece
                on_chunk(full_text)

    if not full_text:
        raise RuntimeError("Empty response from Ollama.")
    return full_text

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


def sanitize_text_for_speech(text):
    if not text:
        return ""

    # Convert markdown links to visible text and drop URL noise.
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)

    # Remove fenced code markers and inline code ticks.
    text = text.replace("```", " ")
    text = text.replace("`", "")

    # Remove heading/bullet/list prefixes so they are not read aloud.
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"(?m)^\s*[-*+]\s+", "", text)
    text = re.sub(r"(?m)^\s*\d+\.\s+", "", text)

    # Remove common markdown emphasis/control symbols.
    text = text.replace("**", "")
    text = text.replace("__", "")
    text = text.replace("*", "")
    text = text.replace("_", " ")

    # Remove common emoji and pictograph ranges so TTS does not read icon names.
    text = re.sub(r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U0001F1E6-\U0001F1FF]", "", text)
    text = text.replace("\uFE0F", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def strip_leading_action_for_display(text):
    """Hide action tags while streaming so the user only sees natural language."""
    if not text:
        return ""
    if text.startswith("[ACTION:"):
        close_index = text.find("]")
        if close_index == -1:
            return ""
        return text[close_index + 1:].lstrip()
    return text

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
        self.voice_reply_enabled = self.config_data.get("voice_reply_enabled", True)
        self.voice_input_enabled = self.config_data.get("voice_input_enabled", True)
        self.voice_supported = platform.system() == "Windows"
        self.wake_word_enabled = self.config_data.get("wake_word_enabled", self.voice_supported)
        self.voice_status = "ready"
        self.voice_lock = threading.Lock()
        self.wake_word_active = False
        self.wake_word_thread = None
        self.model_warmed = False
        self.stream_raw_text = ""
        self.stream_active = False
        self.stream_cancel_requested = False

        self.title("ARIA")
        self.geometry("420x680")
        self.minsize(360, 500)
        self.configure(fg_color=COLORS["bg"])
        self.resizable(True, True)

        # Remove default title bar on Windows for cleaner look
        if platform.system() == "Windows":
            self.overrideredirect(False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", self._on_escape)

        self._build_ui()
        self._show_chat()
        self._add_welcome()
        self._apply_wake_word_state()
        threading.Thread(target=self._prepare_local_model, daemon=True).start()

    def _on_close(self):
        self.wake_word_active = False
        self.destroy()

    def _on_escape(self, event=None):
        if self.stream_active:
            self._stop_streaming_response()
            return "break"
        return None

    def _prepare_local_model(self):
        try:
            ensure_ollama_model()
            self.modelfile_path = find_modelfile_path()
            self.ollama_ready = True
            self.after(0, lambda: self.status_label.configure(text=" ● local gemma ready", text_color=COLORS["success"]))
            threading.Thread(target=self._warm_model_once, daemon=True).start()
        except Exception as e:
            self.model_bootstrap_error = str(e)
            self.after(0, lambda: self.status_label.configure(text=" ● local model unavailable", text_color=COLORS["error"]))

    def _warm_model_once(self):
        if self.model_warmed or not self.ollama_ready:
            return
        try:
            # Small one-time warmup to reduce first real response latency.
            body = json.dumps({
                "model": OLLAMA_MODEL_NAME,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": "Respond with exactly: ready"},
                ],
                "stream": False,
                "keep_alive": "30m",
                "options": {
                    "temperature": 0.0,
                    "num_predict": 8,
                    "num_thread": max(1, (os.cpu_count() or 4)),
                },
            }).encode()

            req = urllib.request.Request(
                OLLAMA_API_URL,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=60):
                pass
            self.model_warmed = True
        except Exception:
            # Ignore warmup failures; normal chat still works.
            return

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
        self.voice_toggle_btn = ctk.CTkButton(right, text="🔊", width=30, height=30, corner_radius=8,
                              fg_color=COLORS["card"], hover_color=COLORS["border"],
                              text_color=COLORS["muted"], font=("Arial", 13),
                              command=self._toggle_voice_reply)
        self.voice_toggle_btn.pack(side="left", padx=2)
        self.wake_word_btn = ctk.CTkButton(right, text="👂", width=30, height=30, corner_radius=8,
                            fg_color=COLORS["card"], hover_color=COLORS["border"],
                            text_color=COLORS["muted"], font=("Arial", 12),
                            command=self._toggle_wake_word)
        self.wake_word_btn.pack(side="left", padx=2)
        self.stop_btn = ctk.CTkButton(right, text="⏹", width=30, height=30, corner_radius=8,
                          fg_color=COLORS["card"], hover_color=COLORS["border"],
                          text_color=COLORS["muted"], font=("Arial", 12),
                          command=self._stop_streaming_response)
        self.stop_btn.pack(side="left", padx=2)
        ctk.CTkButton(right, text="✕", width=30, height=30, corner_radius=8,
                  fg_color=COLORS["card"], hover_color="#3a1010",
                  text_color=COLORS["muted"], font=("Arial", 13),
                  command=self._on_close).pack(side="left", padx=2)

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

        self.mic_btn = ctk.CTkButton(input_inner, text="🎙", width=38, height=38,
                          fg_color=COLORS["card"], hover_color=COLORS["border"],
                          text_color=COLORS["muted"], font=("Arial", 14), corner_radius=10,
                          command=self._start_voice_capture)
        self.mic_btn.pack(side="right", padx=(0, 6), pady=4)

        self.send_btn = ctk.CTkButton(input_inner, text="➤", width=38, height=38,
                                       fg_color=COLORS["accent"], hover_color="#6a5de8",
                                       font=("Arial", 16), corner_radius=10,
                                       command=self._do_send)
        self.send_btn.pack(side="right", padx=6, pady=4)
        self._refresh_voice_controls()

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
        self.model_warmed = False
        self.model_bootstrap_error = None
        self.status_label.configure(text=" ● building local gemma...", text_color=COLORS["accent"])
        threading.Thread(target=self._prepare_local_model, daemon=True).start()

    def _set_status(self, text, color):
        self.status_label.configure(text=text, text_color=color)

    def _refresh_voice_controls(self):
        if hasattr(self, "voice_toggle_btn"):
            if self.voice_reply_enabled:
                self.voice_toggle_btn.configure(text="🔊", fg_color=COLORS["accent"], text_color="#ffffff")
            else:
                self.voice_toggle_btn.configure(text="🔈", fg_color=COLORS["card"], text_color=COLORS["muted"])

        if hasattr(self, "wake_word_btn"):
            if self.voice_supported and self.wake_word_enabled:
                self.wake_word_btn.configure(text="👂", fg_color=COLORS["accent2"], text_color="#ffffff")
            else:
                self.wake_word_btn.configure(text="👂", fg_color=COLORS["card"], text_color=COLORS["muted"])

        if hasattr(self, "mic_btn"):
            if self.voice_supported and self.voice_input_enabled and self.voice_status != "listening":
                self.mic_btn.configure(state="normal", text="🎙", fg_color=COLORS["card"], text_color=COLORS["muted"])
            else:
                self.mic_btn.configure(state="disabled", text="🎙", fg_color=COLORS["card"], text_color=COLORS["muted"])

        if hasattr(self, "stop_btn"):
            if self.stream_active:
                self.stop_btn.configure(state="normal", fg_color=COLORS["error"], text_color="#ffffff")
            else:
                self.stop_btn.configure(state="disabled", fg_color=COLORS["card"], text_color=COLORS["muted"])

    def _persist_voice_config(self):
        self.config_data["voice_reply_enabled"] = self.voice_reply_enabled
        self.config_data["voice_input_enabled"] = self.voice_input_enabled
        self.config_data["wake_word_enabled"] = self.wake_word_enabled
        save_config(self.config_data)

    def _toggle_voice_reply(self):
        self.voice_reply_enabled = not self.voice_reply_enabled
        self._persist_voice_config()
        self._refresh_voice_controls()
        if self.voice_reply_enabled:
            self._set_status(" ● voice replies on", COLORS["success"])
        else:
            self._set_status(" ● voice replies off", COLORS["muted"])

    def _toggle_voice_input(self):
        self.voice_input_enabled = not self.voice_input_enabled
        if not self.voice_input_enabled:
            self.wake_word_enabled = False
            self._stop_wake_word_listener()
        self._persist_voice_config()
        self._apply_wake_word_state()
        self._refresh_voice_controls()

    def _toggle_wake_word(self):
        if not self.voice_supported:
            self._add_error("Wake-word mode is currently available on Windows only.")
            return
        if not self.voice_input_enabled:
            self._add_error("Enable voice input first to use wake-word mode.")
            return

        self.wake_word_enabled = not self.wake_word_enabled
        self._persist_voice_config()
        self._apply_wake_word_state()
        self._refresh_voice_controls()

        if self.wake_word_enabled:
            self._set_status(" ● wake-word listening", COLORS["accent2"])
        else:
            self._set_status(" ● wake-word off", COLORS["muted"])

    def _apply_wake_word_state(self):
        if self.voice_supported and self.voice_input_enabled and self.wake_word_enabled:
            self._start_wake_word_listener()
        else:
            self._stop_wake_word_listener()

    def _start_wake_word_listener(self):
        if self.wake_word_active:
            return
        self.wake_word_active = True
        self.wake_word_thread = threading.Thread(target=self._wake_word_loop, daemon=True)
        self.wake_word_thread.start()

    def _stop_wake_word_listener(self):
        self.wake_word_active = False

    def _listen_for_wake_word(self):
        self._init_voice_engine()
        script = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$engine = New-Object System.Speech.Recognition.SpeechRecognitionEngine
$engine.SetInputToDefaultAudioDevice()
$choices = New-Object System.Speech.Recognition.Choices
$choices.Add('hey aria')
$builder = New-Object System.Speech.Recognition.GrammarBuilder
$builder.Append($choices)
$grammar = New-Object System.Speech.Recognition.Grammar($builder)
$engine.LoadGrammar($grammar)
$result = $engine.Recognize([TimeSpan]::FromSeconds(4))
if ($null -ne $result) {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    Write-Output $result.Text
}
"""
        result = self._run_powershell(script, timeout=8)
        if result.returncode != 0:
            details = result.stderr.strip() or result.stdout.strip() or "Wake-word listener failed."
            raise RuntimeError(details)
        return result.stdout.strip().lower()

    def _wake_word_loop(self):
        while self.wake_word_active:
            if not (self.voice_supported and self.voice_input_enabled and self.wake_word_enabled):
                time.sleep(0.5)
                continue

            if self.thinking or self.voice_status == "listening":
                time.sleep(0.4)
                continue

            try:
                heard = self._listen_for_wake_word()
            except Exception as e:
                self.after(0, lambda err=str(e): self._add_error(f"Wake-word error: {err}"))
                time.sleep(1.0)
                continue

            normalized = " ".join(heard.lower().strip().split())
            if normalized == "hey aria":
                self.after(0, lambda: self._set_status(" ● wake word detected", COLORS["accent2"]))
                self.after(0, self._start_voice_capture)
                time.sleep(1.0)

    def _init_voice_engine(self):
        if not self.voice_supported:
            raise RuntimeError("Voice input and spoken replies are currently supported on Windows only.")

    def _run_powershell(self, script, env=None, timeout=30):
        powershell_cmd = "powershell"
        result = subprocess.run(
            [powershell_cmd, "-NoProfile", "-STA", "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return result

    def _listen_for_speech(self):
        self._init_voice_engine()
        script = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$engine = New-Object System.Speech.Recognition.SpeechRecognitionEngine
$engine.SetInputToDefaultAudioDevice()
$grammar = New-Object System.Speech.Recognition.DictationGrammar
$engine.LoadGrammar($grammar)
$result = $engine.Recognize([TimeSpan]::FromSeconds(12))
if ($null -ne $result) {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    Write-Output $result.Text
}
"""
        result = self._run_powershell(script, timeout=20)
        if result.returncode != 0:
            details = result.stderr.strip() or result.stdout.strip() or "Voice capture failed."
            raise RuntimeError(details)
        return result.stdout.strip()

    def _speak_text(self, text):
        self._init_voice_engine()
        text = sanitize_text_for_speech((text or "").strip())
        if not text:
            return

        text = text[:500]
        env = os.environ.copy()
        env["ARIA_TTS_TEXT"] = text
        script = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$text = $env:ARIA_TTS_TEXT
if ([string]::IsNullOrWhiteSpace($text)) { return }
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.Rate = 0
$synth.Volume = 100
$synth.Speak($text)
"""
        result = self._run_powershell(script, env=env, timeout=30)
        if result.returncode != 0:
            details = result.stderr.strip() or result.stdout.strip() or "Text to speech failed."
            raise RuntimeError(details)

    def _start_voice_capture(self):
        if self.thinking:
            return

        if not self.voice_supported or not self.voice_input_enabled:
            self._add_error("Voice input is not available on this platform.")
            return

        with self.voice_lock:
            if self.voice_status == "listening":
                return
            self.voice_status = "listening"

        self._set_status(" ● listening...", COLORS["accent2"])
        self.mic_btn.configure(state="disabled")
        threading.Thread(target=self._voice_capture_worker, daemon=True).start()

    def _stop_streaming_response(self):
        if not self.stream_active:
            return
        self.stream_cancel_requested = True
        self._set_status(" ● stopping...", COLORS["muted"])

    def _stream_should_stop(self):
        return self.stream_cancel_requested

    def _voice_capture_worker(self):
        try:
            spoken_text = self._listen_for_speech()
            if not spoken_text:
                raise RuntimeError("I did not catch anything. Try again.")
            self.voice_status = "ready"
            self.after(0, self._refresh_voice_controls)
            self.after(0, lambda: self._set_status(" ● thinking...", COLORS["accent"]))
            self.after(0, lambda t=spoken_text: self._send(t))
        except Exception as e:
            self.after(0, lambda: self._voice_capture_failed(str(e)))

    def _voice_capture_failed(self, message):
        self.voice_status = "ready"
        self._refresh_voice_controls()
        if self.wake_word_enabled and self.voice_input_enabled and self.voice_supported:
            self._set_status(" ● wake-word listening", COLORS["accent2"])
        else:
            self._set_status(" ● online", COLORS["success"])
        self._add_error(message)

    # ── Settings dialog ────────────────────────────────────────────────────

    def _open_settings(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Settings")
        dlg.geometry("380x370")
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
        ctk.CTkLabel(dlg, text=f"Voice: {'Windows speech enabled' if self.voice_supported else 'Unavailable on this platform'}",
                     font=("Arial", 11), text_color=COLORS["muted"]).pack(anchor="w", padx=24, pady=(0,10))

        def refresh_voice_labels():
            voice_button.configure(text="Disable voice replies" if self.voice_reply_enabled else "Enable voice replies")
            mic_button.configure(text="Disable voice input" if self.voice_input_enabled else "Enable voice input")
            wake_button.configure(text="Disable wake-word ('Hey Aria')" if self.wake_word_enabled else "Enable wake-word ('Hey Aria')")

        def toggle_voice_reply_and_refresh():
            self._toggle_voice_reply()
            refresh_voice_labels()

        def toggle_voice_input_and_refresh():
            self._toggle_voice_input()
            self._apply_wake_word_state()
            refresh_voice_labels()

        def toggle_wake_word_and_refresh():
            self._toggle_wake_word()
            refresh_voice_labels()

        voice_button = ctk.CTkButton(dlg, text="", width=290, height=38,
                                     fg_color=COLORS["card"], command=toggle_voice_reply_and_refresh)
        voice_button.pack(padx=24, pady=2)
        mic_button = ctk.CTkButton(dlg, text="", width=290, height=38,
                                   fg_color=COLORS["card"], command=toggle_voice_input_and_refresh)
        mic_button.pack(padx=24, pady=2)
        wake_button = ctk.CTkButton(dlg, text="", width=290, height=38,
                        fg_color=COLORS["card"], command=toggle_wake_word_and_refresh)
        wake_button.pack(padx=24, pady=2)
        refresh_voice_labels()

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

    def _update_stream_text(self, full_text):
        self.stream_raw_text = full_text
        shown_text = strip_leading_action_for_display(full_text)
        if shown_text:
            self._set_status(" ● responding...", COLORS["accent"])
        if hasattr(self, "typing_label") and self.typing_label.winfo_exists():
            self.typing_label.configure(
                text=shown_text or "● ● ●",
                font=("Arial", 13),
                text_color=COLORS["text"],
                wraplength=300,
                justify="left"
            )
            self._scroll_bottom()

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
        self.stream_active = True
        self.stream_cancel_requested = False
        self.send_btn.configure(state="disabled")
        self.status_label.configure(text=" ● thinking...", text_color=COLORS["accent"])
        self._refresh_voice_controls()

        typing_el = self._add_typing()
        threading.Thread(target=self._worker, args=(typing_el,), daemon=True).start()

    def _worker(self, typing_el):
        try:
            if not self.ollama_ready:
                ensure_ollama_model()
                self.ollama_ready = True
            self.stream_raw_text = ""
            def on_chunk(full_text):
                self.after(0, lambda t=full_text: self._update_stream_text(t))

            on_chunk.should_stop = self._stream_should_stop
            reply = call_gemma_local_stream(
                self.history,
                on_chunk
            )
            if self.stream_cancel_requested:
                reply = None
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
        self.stream_active = False
        self.stream_cancel_requested = False
        self.send_btn.configure(state="normal")
        self._refresh_voice_controls()

        if error:
            self._set_status(" ● local model unavailable", COLORS["error"])
            self._add_error(error)
            return

        if reply is None:
            self._set_status(" ● online", COLORS["success"])
            return

        self._set_status(" ● local gemma ready", COLORS["success"])

        # Parse action
        action_result = None
        action_match = re.match(r'^\[ACTION:(\w+):(.+?)\]\s*', reply)
        if action_match:
            action_tag = action_match.group(0).strip()
            action_result = execute_action(action_tag)
            reply = reply[len(action_match.group(0)):].strip()
            if not reply and action_result:
                reply = "Done."

        self.history.append({"role": "assistant", "content": reply})
        self._add_aria_msg(reply, action_result)

        if self.wake_word_enabled and self.voice_input_enabled and self.voice_supported:
            self._set_status(" ● wake-word listening", COLORS["accent2"])

        if self.voice_reply_enabled and reply:
            threading.Thread(target=self._speak_reply_worker, args=(reply,), daemon=True).start()

    def _speak_reply_worker(self, text):
        try:
            self._speak_text(text)
        except Exception as e:
            self.after(0, lambda: self._add_error(f"Voice reply failed: {e}"))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = ARIAApp()
    app.mainloop()
