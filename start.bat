@echo off
title AI Video Studio — Launcher
color 0B
cls
echo.
echo  ============================================
echo   AI VIDEO STUDIO — Personal Automation Tool
echo  ============================================
echo.

:: ─────────────────────────────────────────────────────────────────────
:: [1/3] PRE-FLIGHT — soi ma nguon TRUOC khi khoi dong.
::
:: Ly do co buoc nay: nhung loi nguy hiem nhat cua du an nay khong lam
:: chet server luc khoi dong — chung nam im den giua chung job render roi
:: moi no, dot sach cong API da goi. Vi du that ngay 2026-07-11:
::     UnboundLocalError: cannot access local variable 'shutil'
:: (import cuc bo che module import — xem backend/scripts/check_imports.py).
:: Ba lop kiem tra duoi day bat duoc lop loi do trong ~2 giay.
:: ─────────────────────────────────────────────────────────────────────
echo  [1/3] Kiem tra suc khoe ma nguon backend...
echo.
set "PREFLIGHT_FAIL="
pushd "%~dp0backend"
call .\venv\Scripts\activate.bat

:: Lop 1 — cu phap Python
python -m compileall -q main.py config.py services
if errorlevel 1 (
    set "PREFLIGHT_FAIL=1"
    echo    [LOI] Sai cu phap Python.
)

:: Lop 2 — ten duoc goi ma chua import / dinh nghia trung / loi cu phap nang
python -m ruff check main.py config.py services --select F821,F811,E9 --quiet
if errorlevel 1 (
    set "PREFLIGHT_FAIL=1"
    echo    [LOI] Ruff: ten chua import hoac dinh nghia trung lap.
)

:: Lop 3 — UnboundLocalError do import cuc bo che module import
::         (py_compile va ruff DEU khong bat duoc loai nay)
python scripts\check_imports.py
if errorlevel 1 set "PREFLIGHT_FAIL=1"

popd

if defined PREFLIGHT_FAIL (
    color 0E
    echo.
    echo  ****************************************************************
    echo   CANH BAO: ma nguon dang co van de o tren.
    echo   Job render CO THE crash giua chung va dot cong API vo ich.
    echo   Nen sua truoc. Nhan phim bat ky de VAN tiep tuc khoi dong...
    echo  ****************************************************************
    pause > nul
    color 0B
)
echo.

echo  [2/3] Khoi dong Backend (FastAPI :8000)...
echo.

:: Khởi Backend trong cửa sổ mới
start "AI-Backend" cmd /k "cd /d C:\dev\AI-VIDEO-MAKER\backend && .\venv\Scripts\activate && uvicorn main:app --reload --port 8000"

:: Chờ 2 giây để Backend khởi động trước
timeout /t 2 /nobreak > nul

echo  [3/3] Khoi dong Frontend (Vite :3001)...
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
