@echo off
chcp 65001 >nul
title LFChatbot Backend Server

cd /d "%~dp0..\backend"

echo ============================================
echo   LFChatbot Backend Server
echo   Log file: backend\logs\server.log
echo   Tail:     bat\tail_log.bat
echo ============================================
echo.

python -X utf8 app/main.py
