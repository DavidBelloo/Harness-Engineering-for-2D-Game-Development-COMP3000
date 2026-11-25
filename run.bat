@echo off
rem Make a game:  run.bat "a ghost dodging falling pumpkins"
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
