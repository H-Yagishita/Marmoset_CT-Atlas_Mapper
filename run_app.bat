@echo off
setlocal
cd /d "%~dp0"
if exist "MarmosetAtlasMapper.exe" (
  start "" "MarmosetAtlasMapper.exe"
  exit /b 0
)
if not exist ".venv\Scripts\python.exe" (
  echo Python environment not found.
  echo Run: py -3.12 -m venv .venv
  echo Then: .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)
".venv\Scripts\python.exe" app.py
