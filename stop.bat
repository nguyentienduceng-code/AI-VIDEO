@echo off
title AI Video Studio — Stop All
echo.
echo  Dang tat tat ca cac tien trinh...
echo.
taskkill /FI "WindowTitle eq AI-Backend*" /F > nul 2>&1
taskkill /FI "WindowTitle eq AI-Frontend*" /F > nul 2>&1
echo  [OK] Da tat het. Tam biet!
timeout /t 2 > nul
