// ecosystem.config.js — cấu hình PM2 cho AI Video Studio.
//
// Vì sao nên chạy bằng PM2 thay vì start.bat:
//   - autorestart: job render chết vì OOM/FFmpeg thì server tự dựng lại, không phải
//     ngồi canh cửa sổ cmd.
//   - log bền: PM2 ghi ra file và đã bật pm2-logrotate (10MB × 14 bản, nén).
//     start.bat thì đóng cửa sổ là mất sạch.
//
// Dùng:  pm2 start ecosystem.config.js    (hoặc chạy start-pm2.bat)
//        pm2 logs AI-Backend              xem log trực tiếp
//        pm2 restart AI-Backend           nạp lại sau khi sửa code
//        pm2 stop all                     dừng
//
// LƯU Ý: KHÔNG bật `watch` cho backend. MoviePy/FFmpeg ghi file tạm ngay trong cây
// thư mục dự án; watch sẽ thấy file mới rồi restart server GIỮA LÚC ĐANG RENDER.

const path = require("path");

// Neo theo vị trí file này, không theo thư mục đang đứng khi gõ lệnh — nếu không,
// `pm2 start C:\...\ecosystem.config.js` từ chỗ khác sẽ resolve sai cwd và chết ngay.
const ROOT = __dirname;

module.exports = {
  apps: [
    {
      name: "AI-Backend",
      script: path.join(ROOT, "backend", "venv", "Scripts", "uvicorn.exe"),
      args: "main:app --host 127.0.0.1 --port 8000",
      cwd: path.join(ROOT, "backend"),
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_memory_restart: "2G",

      // Chặn vòng lặp crash: nếu sống dưới 10s mà chết thì tính là hỏng thật;
      // thử lại 5 lần rồi dừng hẳn để còn đọc log, thay vì restart vô tận.
      min_uptime: "10s",
      max_restarts: 5,
      restart_delay: 3000,

      time: true, // đóng dấu thời gian vào log PM2
      out_file: path.join(ROOT, "backend", "logs", "pm2-backend-out.log"),
      error_file: path.join(ROOT, "backend", "logs", "pm2-backend-error.log"),

      env: {
        NODE_ENV: "development",
        PYTHONIOENCODING: "utf-8", // log tiếng Việt không vỡ khi stdout bị PM2 bắt ống
      },
    },
    {
      name: "AI-Frontend",
      script: "npm.cmd",
      args: "run dev -- --port 3001",
      cwd: path.join(ROOT, "frontend"),
      // BẮT BUỘC trên Windows: PM2 chọn interpreter theo phần mở rộng của script, mà
      // ".cmd" không có trong bảng đó → nó rơi về `node` và cố parse npm.cmd như file
      // JavaScript, chết ngay lúc start. "none" = chạy thẳng như tiến trình hệ điều
      // hành (giống AI-Backend gọi uvicorn.exe ở trên).
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_memory_restart: "1G",

      min_uptime: "10s",
      max_restarts: 5,
      restart_delay: 3000,

      time: true,
      out_file: path.join(ROOT, "backend", "logs", "pm2-frontend-out.log"),
      error_file: path.join(ROOT, "backend", "logs", "pm2-frontend-error.log"),

      env: {
        NODE_ENV: "development",
      },
    },
  ],
};
