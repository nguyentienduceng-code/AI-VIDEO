@echo off
echo Khoi dong PM2 Daemon...
call npm install -g pm2
call pm2 start ecosystem.config.js
call pm2 save
echo.
echo Da khoi dong thanh cong! Cac tien trinh Backend va Frontend dang chay ngam.
echo Ban co the tat cua so nay an toan.
echo De kiem tra trang thai, mo CMD va chay: pm2 list
echo.
pause
