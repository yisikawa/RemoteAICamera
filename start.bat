@echo off
chcp 65001 > nul
title RemoteAICamera

echo [1/2] Backend (camera + API server) ...
start "Backend" cmd /k "cd /d %~dp0 && .venv\Scripts\python.exe main.py"

timeout /t 3 /nobreak > nul

echo [2/2] Frontend (Vite dev server) ...
start "Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo Backend  : http://localhost:8000
echo Frontend : http://localhost:5173
echo.
echo Close each window to stop.
