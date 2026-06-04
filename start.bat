@echo off
chcp 65001 > nul
title RemoteAICamera

echo Stopping existing processes...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000 " ^| findstr LISTENING 2^>nul') do taskkill /PID %%p /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5173 " ^| findstr LISTENING 2^>nul') do taskkill /PID %%p /F >nul 2>&1
timeout /t 1 /nobreak > nul

echo [1/2] Backend (camera + API server) ...
start "Backend" cmd /k "cd /d %~dp0 && .venv\Scripts\python.exe main.py"

timeout /t 3 /nobreak > nul

echo [2/2] Frontend (Vite dev server) ...
start "Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo Backend  : http://localhost:8000
echo Frontend : http://localhost:5173
echo WebSocket: ws://localhost:8000/ws
echo.
echo Close each window to stop.
