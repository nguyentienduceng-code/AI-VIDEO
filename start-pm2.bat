@echo off
title AI Video Studio — PM2 Launcher
color 0B
cls
echo.
echo  ============================================
echo   AI VIDEO STUDIO — khoi dong bang PM2
echo  ============================================
echo.
echo  Khac gi start.bat?
echo    - Tu dung day lai khi backend chet (autorestart)
echo    - Log ghi ra file, xoay vong tu dong, dong cua so khong mat
echo    - Chay nen: dong cua so nay he thong VAN chay
echo.

:: ─────────────────────────────────────────────────────────────────────
:: [1/4] Pre-flight — giong start.bat: bat loi truoc khi no dot cong API
:: ─────────────────────────────────────────────────────────────────────
echo  [1/4] Kiem tra suc khoe ma nguon backend...
echo.
set "PREFLIGHT_FAIL="
pushd "%~dp0backend"
call .\venv\Scripts\activate.bat

python -m compileall -q main.py config.py services
if errorlevel 1 (
    set "PREFLIGHT_FAIL=1"
    echo    [LOI] Sai cu phap Python.
)

python -m ruff check main.py config.py services --select F821,F811,E9 --quiet
if errorlevel 1 (
    set "PREFLIGHT_FAIL=1"
    echo    [LOI] Ruff: ten chua import hoac dinh nghia trung lap.
)

python scripts\check_imports.py
if errorlevel 1 set "PREFLIGHT_FAIL=1"

popd

if defined PREFLIGHT_FAIL (
    color 0E
    echo.
    echo  ****************************************************************
    echo   CANH BAO: ma nguon dang co van de o tren.
    echo   Nhan phim bat ky de VAN tiep tuc khoi dong...
    echo  ****************************************************************
    pause > nul
    color 0B
)
echo.

:: ─────────────────────────────────────────────────────────────────────
:: [2/4] Cong 8000 co ai chiem chua?
::  Neu start.bat dang chay san, uvicorn cua PM2 se chet ngay vi trung
::  cong — va vi min_uptime/max_restarts, PM2 se thu 5 lan roi bo cuoc.
::  Bao truoc con hon de nguoi dung tu doan.
:: ─────────────────────────────────────────────────────────────────────
echo  [2/4] Kiem tra cong 8000...
netstat -ano -p tcp | findstr ":8000 " | findstr "LISTENING" > nul
if not errorlevel 1 (
    color 0E
    echo    [!] Cong 8000 DANG BI CHIEM — nhieu kha nang start.bat con chay.
    echo        Hay dong cua so "AI-Backend" cu ^(hoac chay stop.bat^) truoc.
    echo.
    echo    Nhan phim bat ky de van thu khoi dong, hoac dong cua so nay de huy...
    pause > nul
    color 0B
) else (
    echo    [OK] Cong 8000 dang trong.
)
echo.

:: ─────────────────────────────────────────────────────────────────────
:: [3/4] Khoi dong qua PM2
:: ─────────────────────────────────────────────────────────────────────
echo  [3/4] Khoi dong AI-Backend + AI-Frontend qua PM2...
echo.
call pm2 start "%~dp0ecosystem.config.js"
if errorlevel 1 (
    color 0C
    echo.
    echo  [LOI] PM2 khong khoi dong duoc. Kiem tra: pm2 logs
    pause > nul
    exit /b 1
)

:: Ghi lai danh sach app dang chay -> `pm2 resurrect` sau nay dung lai duoc
call pm2 save > nul
echo.
echo    [OK] Da luu danh sach tien trinh ^(pm2 save^).
echo.

:: ─────────────────────────────────────────────────────────────────────
:: [4/4] Tong ket
:: ─────────────────────────────────────────────────────────────────────
echo  [4/4] Trang thai:
echo.
call pm2 list
echo.
echo  ============================================
echo   Backend API : http://localhost:8000
echo   Frontend UI : http://localhost:3001
echo   API Docs    : http://localhost:8000/docs
echo  ============================================
echo.
echo   Lenh hay dung:
echo     pm2 logs AI-Backend      xem log truc tiep
echo     pm2 restart AI-Backend   nap lai sau khi sua code
echo     pm2 stop all             dung tat ca
echo     pm2 monit                bang theo doi CPU/RAM
echo.
echo   Log file:
echo     backend\logs\backend.log        (log ung dung, co [job_id])
echo     backend\logs\render_worker.log  (log tien trinh render)
echo     backend\logs\pm2-backend-*.log  (stdout/stderr do PM2 bat)
echo.

timeout /t 3 /nobreak > nul
start "" "http://localhost:3001"

echo  Nhan phim bat ky de dong cua so nay ^(he thong VAN chay nen^)...
pause > nul
