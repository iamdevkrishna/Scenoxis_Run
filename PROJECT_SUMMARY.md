# Scenoxis Run - Project Summary

## Overview
**Scenoxis Run** is a powerful, Spotlight-like AI desktop overlay for Windows. It runs silently in the background (accessible via the System Tray) and can be instantly summoned using a global hotkey (`Alt+Space`). The application serves as a unified interface for chatting with a personalized AI assistant (Scenoxis), launching local applications, and executing native desktop tools.

## Architecture & Tech Stack
- **Language**: Python
- **UI Framework**: PySide6 (Qt) with custom CSS/QSS for a modern, animated, glassmorphism design.
- **AI/LLM Engine**: Groq API (specifically Llama-3 models) orchestrated via LangChain and LangGraph.
- **Memory/Vector Store**: ChromaDB for persisting the user's personal context and conversation history locally.
- **Packaging**: PyInstaller (via `build.py`) for bundling into a standalone `.exe`.

## Core Features & Agentic Tools
1. **Intelligent Chat (Agentic Workflow)**
   - Powered by LangGraph, the AI acts as an autonomous agent capable of deciding when to answer directly or when to invoke external tools.
   - Fallback mechanisms exist to handle LLM tool-calling hallucinations (e.g., parsing raw `<function>` XML tags natively when Groq throws 400 Bad Request errors).

2. **Web Search Integration**
   - Uses Tavily API to fetch real-time, up-to-date information when the user asks about current events, public figures, or facts not in its memory.

3. **Local App Indexing & Launching**
   - Indexes local Windows `.lnk` and `.exe` files and allows the user to quickly launch applications directly from the overlay.

4. **Contextual Memory**
   - Stores and retrieves personal details (e.g., dietary preferences, user's name, location) using ChromaDB, allowing the AI to maintain long-term personalized context.

5. **Native Desktop UI Actions**
   - **YouTube Downloader**: Uses `yt-dlp` and `uiautomation` to extract video/audio from YouTube URLs directly from the active browser tab.
   - **Image Utilities**: Built-in native UI dialogs for converting image formats and resizing images.

6. **System Tray & Background Execution**
   - Lives in the Windows system tray with a custom context menu (Settings, Quit, etc.).
   - Includes graceful fallback icons if custom assets are missing in the build.

## Guide for Future LLMs
If you are an LLM taking over development or maintenance of this project, keep in mind:
- **UI**: Modifying the UI involves updating PySide6 widgets and `styles.qss`. Always ensure animations and window opacity are handled cleanly so the overlay doesn't block the user's screen.
- **LLM Prompts & Graph**: The main agent loop lives in `agent/graph.py`. Be careful when altering how `ToolMessage` and `AIMessage` are appended to the LangGraph state, as Groq API requires strict message sequencing.
- **Building**: We use `build.py` to run PyInstaller. If you add new dependencies (especially native C libraries or modules with dynamic loading like `uiautomation` or `chromadb`), you must add them as `hidden-imports` or bundle their DLLs in `build.py`.
