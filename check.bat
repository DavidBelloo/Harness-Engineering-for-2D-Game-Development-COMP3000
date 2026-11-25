@echo off
rem Pre-flight check: is everything installed and running?
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.local\bin;%LOCALAPPDATA%\Programs\Ollama;%PATH%"
uv run python setup_check.py
echo.
pause
