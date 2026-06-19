# 🤖 ARIA — Multi-Agent Orchestration System

**ARIA** (Adaptive Reasoning & Intelligence Assistant) has evolved into a powerful multi-agent orchestration system. Built on top of **[CrewAI](https://crewai.com/)** and **Langchain**, ARIA delegates tasks intelligently to specialized AI agents to solve complex requests autonomously.

---

## 🏗️ Architecture

The system uses a modular, multi-agent framework:

- **`aria.py`**: The main orchestrator script. It initializes the LLM engine (`gpt-4o-mini`), establishes the Crew, defines the execution workflow (Tasks), and kicks off the process.
- **`agents.py`**: Contains the specialized agents, making it easy to debug, scale, and add new capabilities.

### Current Agent Roster
1. **Aria (Master Router):** The Chief Orchestrator. Analyzes incoming user requests and delegates optimally to specialized agents.
2. **Global News Agent:** The Chief Global Historian & Breaking News Analyst. Retrieves, contextualizes, and summarizes geopolitical events.
3. **Senior Dev Agent:** The Principal Software Engineer. An aggressively confident expert at writing optimized code, designing software architecture, and algorithms.

---

## ⚡ Quick Start

### 1. Requirements

Make sure you have Python installed, then install the required dependencies:

```bash
pip install crewai langchain-openai
```

### 2. Environment Setup

ARIA uses OpenAI's models (`gpt-4o-mini`) under the hood. You must set your API key as an environment variable before running the orchestrator.

**On Windows (PowerShell):**
```powershell
$env:OPENAI_API_KEY="your-openai-api-key"
```

**On macOS/Linux:**
```bash
export OPENAI_API_KEY="your-openai-api-key"
```

### 3. Run ARIA

To kick off the multi-agent workflow, simply run the orchestrator:

```bash
python aria.py
```

Watch as Aria receives the task, delegates it to the News Agent and Dev Agent, and returns a structured final output!

---

## 🔮 Future Roadmap
- Expansion of the agent roster (e.g., Data Analyst, DevOps, etc.)
- Integration of custom tools for web scraping and local file execution.
- Dynamic task generation based on live user inputs.

*(Note: The previous Tkinter GUI and local Ollama integrations have been deprecated in favor of this advanced CrewAI orchestration model. Local build scripts like `build_windows.bat` are effectively retired for this pure orchestration setup).*
