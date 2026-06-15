@echo off
chcp 65001 > nul
title RemoteAICamera Stop

echo [停止] Backend (port 8000) を終了します...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000 " ^| findstr LISTENING 2^>nul') do taskkill /PID %%p /F >nul 2>&1

echo [停止] Frontend (port 5173) を終了します...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5173 " ^| findstr LISTENING 2^>nul') do taskkill /PID %%p /F >nul 2>&1

echo 停止完了
