@echo off
title AI Video Studio — Cai dat tu khoi dong cung Windows
color 0B
cls
echo.
echo  ============================================
echo   TU KHOI DONG AI VIDEO STUDIO CUNG WINDOWS
echo  ============================================
echo.
echo  VI SAO CAN SCRIPT NAY:
echo    Lenh `pm2 startup` cua PM2 chi chay tren Linux/macOS, tren Windows
echo    no bao loi. Cach dung duoc la dang ky mot Scheduled Task goi
echo    `pm2 resurrect` moi khi ban dang nhap — lenh do dung lai dung danh
echo    sach app da luu boi `pm2 save`.
echo.
echo  Task se tao:  AI-Video-Studio-PM2   (chay luc dang nhap)
echo  Go bo sau nay: chay lai file nay roi chon 2
echo.
echo  ------------------------------------------------
echo    1 = CAI DAT tu khoi dong
echo    2 = GO BO tu khoi dong
echo    3 = Thoat (khong lam gi)
echo  ------------------------------------------------
echo.

set "CHOICE="
set /p CHOICE=  Chon (1/2/3):

if "%CHOICE%"=="2" goto uninstall
if "%CHOICE%"=="3" goto done
if not "%CHOICE%"=="1" goto done

:install
echo.
echo  [1/3] Tim pm2...
set "PM2CMD=%APPDATA%\npm\pm2.cmd"
if not exist "%PM2CMD%" (
    color 0C
    echo    [LOI] Khong thay pm2 tai: %PM2CMD%
    echo    Cai bang:  npm install -g pm2
    echo.
    pause > nul
    exit /b 1
)
echo    [OK] %PM2CMD%

echo.
echo  [2/3] Luu danh sach app hien tai ^(pm2 save^)...
call pm2 save
if errorlevel 1 (
    color 0E
    echo    [!] pm2 save that bai — co the chua co app nao chay.
    echo        Hay chay start-pm2.bat truoc, roi chay lai file nay.
    echo.
    pause > nul
    exit /b 1
)

echo.
echo  [3/3] Dang ky Scheduled Task...
schtasks /Create /TN "AI-Video-Studio-PM2" /TR "\"%PM2CMD%\" resurrect" /SC ONLOGON /RL HIGHEST /F
if errorlevel 1 (
    color 0C
    echo.
    echo    [LOI] Khong tao duoc task. Thu chay file nay bang quyen Administrator
    echo          ^(chuot phai -^> Run as administrator^).
    echo.
    pause > nul
    exit /b 1
)

color 0A
echo.
echo  ================================================================
echo   [OK] DA CAI DAT. Lan dang nhap sau, PM2 se tu dung lai cac app.
echo  ================================================================
echo.
echo   Kiem tra ngay:   schtasks /Query /TN "AI-Video-Studio-PM2"
echo   Chay thu:        schtasks /Run   /TN "AI-Video-Studio-PM2"
echo.
echo   LUU Y: moi khi them/bot app trong PM2, nho chay lai `pm2 save`
echo          thi lan khoi dong sau moi dung danh sach moi.
echo.
goto done

:uninstall
echo.
echo  Dang go bo Scheduled Task...
schtasks /Delete /TN "AI-Video-Studio-PM2" /F
if errorlevel 1 (
    color 0E
    echo    [!] Khong tim thay task ^(co the chua tung cai^).
) else (
    color 0A
    echo    [OK] Da go bo. Windows se khong tu khoi dong AI Video Studio nua.
)
echo.
goto done

:done
echo  Nhan phim bat ky de dong...
pause > nul
