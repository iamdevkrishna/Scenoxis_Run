# Scenoxis Run

A blazing-fast, AI-powered system overlay and launcher.

Press **Alt+Space** anywhere in Windows to instantly bring up the Scenoxis Run search bar.

## Features

- **App Launcher**: Start typing the name of any installed application to launch it instantly (e.g. "code" or "spotify").
- **Calculator**: Type a math expression for instant evaluation. Supports advanced math functions via `asteval` (e.g. `24 * (100 - 45.3) / pi`).
- **Currency & Unit Converter**: Type "convert 100 USD to EUR" or "100 km to miles" for instant real-time conversions.
- **Image Converter**: Type "convert png to jpg" to instantly convert images between formats (png, jpg, jpeg, webp, bmp).
- **Image Resizer**: Type "resize 1920x1080" or "resize image 500x500" to instantly resize images.
- **File Search**: Type "find myfile" to quickly locate documents, images, and folders across your system.
- **Notes**: Type "note: buy groceries" or "add note pick up dry cleaning" to quickly save a note with a timestamp. Type "view notes" to see them, and press Enter on a note to delete it.
- **Reminders**: Type "remind me in 5 minutes to stretch" to set system notifications.
- **System Controls**: Type "shutdown", "restart", "sleep", "lock", "mute", "volume up", or "brightness 50" to control your PC.
- **YouTube Downloader**: Type "download youtube audio" to fetch the best audio from the current video you're watching (or paste a URL). Supports video & audio downloads.
- **Smart Web Search**: Ask questions like "Who won the superbowl in 2024?" to get a summarized, AI-generated answer using live web data.
- **Contextual AI Chat**: Start a natural conversation. The AI understands what's on your screen (if you have a browser open) and can answer contextual questions.

## Settings

Scenoxis Run now runs in the **System Tray**. Right-click the Scenoxis Run icon in your taskbar to open **Settings**.

From the Settings menu, you can:
- Add your **Groq API Key** for AI chat.
- Add your **Tavily API Key** for live web search.
- Change the Theme (**System, Dark, Light**).

## Building from Source

To build a standalone executable:
```bash
pip install -r requirements.txt
pip install pyinstaller
python build.py
```

The compiled application will be available in the `dist/ScenoxisRun` directory. Run `ScenoxisRun.exe`.