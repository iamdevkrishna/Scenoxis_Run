# Scenoxis Run

A Windows-only AI-powered launcher — the speed of PowerToys Run, the intelligence of an LLM-native desktop assistant.

## What it does

Scenoxis Run is an LLM at your fingertips, available instantly across your entire operating system. It's not just a launcher — it's an intelligent desktop assistant with an arsenal of crazy tools.

- 🚀 **Universal App Launcher**: Open *any* application on your PC in under 1 millisecond using lightning-fast native fuzzy-matching. 
- 🧠 **Persistent Long-Term Memory**: Scenoxis remembers things about you locally using ChromaDB and HuggingFace. Tell it your preferences or facts, and it will effortlessly recall them in future conversations.
- 👁️ **Full-Screen Vision Analysis**: Type `analyze the screen` and watch the beautiful edge-scanner sweep across your monitor. It seamlessly takes a screenshot of whatever you were doing and gives you a deep, multimodal analysis using Groq Vision. 
- 🌐 **Web Search Agent**: Ask it anything about current events, and the LLM will autonomously invoke the Tavily API to browse the web and synthesize an answer for you in seconds.
- 📺 **Native YouTube Downloader**: Paste any YouTube link directly into the bar, and it will instantly present you with a native UI to choose your audio/video format and download location.
- 🧮 **Instant Local Calculator**: Type any mathematical expression (`100 / 4 * 2`) and get the answer in zero milliseconds — no LLM required.

**Global hotkey:** `Alt+Space` — toggles the overlay from anywhere.

---

## Tech stack

- **UI:** PySide6 (native, frameless, WA_TranslucentBackground)
- **Blur:** Windows DWM `SetWindowCompositionAttribute` Acrylic via ctypes
- **Hotkey:** Win32 `RegisterHotKey` via ctypes (no admin required for most setups)
- **Orchestration:** LangChain + LangGraph StateGraph
- **LLM:** Groq API (`llama-3.3-70b-versatile` for chat, `qwen/qwen3.6-27b` for vision)
- **Embeddings:** HuggingFace `sentence-transformers/all-MiniLM-L6-v2` (local, free)
- **Memory:** ChromaDB with Fernet app-layer encryption at rest
- **Fuzzy match:** rapidfuzz
- **Calculator:** asteval (never `eval`)
- **Web search:** Tavily API
- **YouTube:** yt-dlp

---

## Setup

### 1. Requirements

- Windows 10 / 11
- Python 3.11+
- `pip install -r requirements.txt`

### 2. API keys

Create a `.env` file (you can copy `.env.example`). Your `.env` is already in `.gitignore` so your keys will never be committed:

```env
GROQ_API_KEY="gsk_..."
TAVILY_API_KEY="tvly-..."
```

### 3. Run

```powershell
python main.py
```

The overlay appears on first launch. Press **Alt+Z** to toggle it at any time.

### 4. Smoke test (no network required)

```powershell
python smoke_test.py
```

---

## Project structure

```
Scenoxis Run/
├── main.py                  # Entry point
├── smoke_test.py            # Offline sanity checks
├── requirements.txt
├── .env                     # API keys (never committed)
│
├── core/
│   ├── app_index.py         # Start Menu + Desktop scanner (rapidfuzz)
│   ├── calculator.py        # asteval wrapper + regex detector
│   ├── dwm_blur.py          # Acrylic blur via ctypes DWM API
│   └── hotkey.py            # Win32 RegisterHotKey pump thread
│
├── agent/
│   ├── classifier.py        # Local intent router (zero I/O per keystroke)
│   ├── graph.py             # LangGraph StateGraph (all 5 intent branches)
│   ├── memory.py            # ChromaDB + HuggingFace + Fernet encryption
│   ├── state.py             # AgentState TypedDict
│   └── tools/
│       ├── launch_app.py    # @tool + direct fast-path launcher
│       ├── calculator_tool.py
│       ├── web_search.py    # Tavily @tool
│       ├── page_analyzer.py # PrintWindow capture + Groq vision
│       └── yt_downloader.py # yt-dlp format list + download
│
├── ui/
│   ├── overlay_window.py    # Main frameless window, QThread workers
│   ├── results_panel.py     # Stacked results: list / chat / thinking / scan
│   ├── scanner_overlay.py   # Full-screen animated cyan edge scanner
│   ├── search_bar.py        # QLineEdit with arrow/enter/esc routing
│   ├── result_item.py       # ResultItem dataclass + ResultKind enum
│   └── styles.qss           # Qt glassmorphism stylesheet
│
├── prompts/
│   ├── chat_system.yaml     # Groq chat system prompt (hot-reloadable)
│   ├── vision_analysis.yaml # Groq vision system prompt
│   └── memory_write_decision.yaml
│
└── data/                    # ChromaDB + encryption key (gitignored)
```

---

## Intent routing

```
ALT+Z → search bar keystroke
         │
         ├─ regex: arithmetic?  ──► calc result (instant, no LLM)
         ├─ fuzzy: app index?   ──► app list (instant, no LLM)
         │
         │  [Enter / 420ms debounce]
         │
         ├─ YouTube URL?        ──► yt-dlp format list → download
         ├─ "analyse…" phrase?  ──► PrintWindow → Groq vision
         └─ everything else     ──► ChromaDB RAG → Groq chat → maybe Tavily
```

---

## Memory

Personal facts are stored in ChromaDB as Fernet-encrypted documents. The encryption key lives in `data/.memory_key` (auto-generated on first run, never committed).

To teach Scenoxis about yourself:
```
My name is Alex, I'm a senior Python developer working on ML infrastructure.
```
It will detect a personal fact (heuristic + optional Groq confirmation) and store it. Next time you ask "who am I?", it retrieves and uses it.

---

## Prompts (hot-reload)

Edit any file in `prompts/` while the app is running — changes take effect on the next query, no restart needed.

---

## Adding a new tool

1. Create `agent/tools/my_tool.py` with a `@tool` decorated function
2. Import it in `agent/graph.py` and add it to `_CHAT_TOOLS` (if the LLM should call it) or add a new intent branch
3. Add a classifier pattern to `agent/classifier.py` if it has a deterministic trigger
 