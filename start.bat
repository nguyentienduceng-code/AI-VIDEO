@echo off
title AI Video Studio — Launcher
color 0B
cls
echo.
echo  ============================================
echo   AI VIDEO STUDIO — Personal Automation Tool
echo  ============================================
echo.
echo  [1/2] Khoi dong Backend (FastAPI :8000)...
echo.

:: Khởi Backend trong cửa sổ mới
start "AI-Backend" cmd /k "cd /d C:\dev\AI-VIDEO-MAKER\backend && .\venv\Scripts\activate && uvicorn main:app --reload --port 8000"

:: Chờ 2 giây để Backend khởi động trước
timeout /t 2 /nobreak > nul

echo  [2/2] Khoi dong Frontend (Vite :3001)...
echo.

:: Khởi Frontend trong cửa sổ mới
start "AI-Frontend" cmd /k "cd /d C:\dev\AI-VIDEO-MAKER\frontend && npm run dev -- --port 3001"

:: Chờ 2 giây để Frontend khởi động
timeout /t 2 /nobreak > nul

echo  [OK] He thong da khoi dong!
echo.
echo  Backend API : http://localhost:8000
echo  Frontend UI : http://localhost:3001
echo  API Docs    : http://localhost:8000/docs
echo.

:: Tự động mở trình duyệt
start "" "http://localhost:3001"

echo  Nhan phim bat ky de dong cua so nay...
pause > nul
