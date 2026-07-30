@echo off
REM Scenoxis Run launcher — activates the venv and starts the app
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python main.py
