# 🤖 ARIA — AI Companion Desktop App
### Build your own `.exe` in 2 minutes, no Node.js needed!

---

## ⚡ Quickest Way: Build ARIA.exe on Windows

**Requirements:** Python 3.10+ from [python.org](https://python.org) *(free, 5min install)*

1. Extract this folder anywhere
2. Double-click **`build_windows.bat`**
3. Wait ~60 seconds → `dist/ARIA.exe` appears
4. **Double-click `ARIA.exe` — done! No install needed.**

> On first run, Windows may show a security warning. Click "More info" → "Run anyway" (it's safe — you built it yourself).

---

## 🍎 macOS

```bash
chmod +x build_mac.sh
./build_mac.sh
# → dist/ARIA launches directly
```

---

## 🐧 Linux

```bash
pip3 install customtkinter pyinstaller
pyinstaller --onefile --windowed --name ARIA --collect-all customtkinter aria.py
./dist/ARIA
```

---

## 💬 What ARIA Can Do

| Say this | ARIA does this |
|---|---|
| "Open my Downloads folder" | Opens Downloads in Explorer |
| "Open YouTube" | Opens in your browser |
| "Launch Notepad" | Starts Notepad |
| "Search for Python tutorials" | Google search opens |
| "Open the calculator" | Launches Calculator |
| "Tell me a joke" | Responds with personality 😄 |
| "What files are in my Desktop?" | Runs `dir` and shows output |
| Click the mic button and speak | ARIA listens, transcribes your speech, and replies out loud |
| Say "Hey Aria" (wake-word mode on) | ARIA wakes up and starts listening automatically |

---

## 🖥️ Local Model Setup

ARIA is now wired directly to local Ollama and does not require any cloud API key.

Model setup uses your local `Modelfile` or `Modelfile.txt`.

One-time local setup:
1. Install Ollama: https://ollama.com/download
2. Keep `Modelfile` or `Modelfile.txt` in the same folder as `aria.py` (or next to `ARIA.exe`).
3. Start Ollama service (if not already running):

```bash
ollama serve
```

4. Launch ARIA. It will auto-create model `aria-qwen-coder` from your Modelfile if it is not already present.

Optional manual create (same result):

```bash
ollama create aria-qwen-coder -f Modelfile.txt
```

After that, ARIA will call your local model name `aria-qwen-coder` at `http://127.0.0.1:11434` automatically.

### Strict JSON Runtime Contract

ARIA now parses model output as strict JSON and executes actions from parsed fields.
Model responses should follow this schema:

```json
{
	"reply": "string",
	"action": {
		"type": "none|open_url|open_file|open_folder|open_app|run_cmd|search",
		"value": "string"
	}
}
```

If no action is needed, return `"type": "none"` and `"value": ""`.

---

## 🔒 Privacy
- Your model, configuration, and conversations stay **100% on your machine**
- No telemetry, no analytics, no tracking
- Voice input and spoken replies use the built-in Windows speech engine on Windows, so they stay local too

---

## ❓ FAQ

**Q: Windows blocked the exe?**  
A: Right-click → Properties → Unblock, or click "More info" → "Run anyway" in the SmartScreen dialog.

**Q: Python install failed?**  
A: Make sure you checked **"Add Python to PATH"** during Python installation.

**Q: Can I run aria.py directly without building?**  
A: Yes! Just `pip install customtkinter` then `python aria.py`

**Q: Does voice work on every platform?**  
A: Voice input and spoken replies are currently enabled on Windows. The rest of the app still runs on macOS and Linux.

**Q: How do I use wake-word mode?**  
A: Turn on wake-word mode in Settings (or the 👂 button), then say "Hey Aria" to trigger voice listening.

---

*ARIA now runs against your local Ollama model, with no API key required.*
