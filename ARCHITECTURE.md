# KIẾN TRÚC & CƠ CHẾ HOẠT ĐỘNG: AI VIDEO STUDIO (v2.3+)

Tài liệu này mô tả chi tiết cơ cấu, luồng hoạt động và các thành phần kỹ thuật của hệ thống sinh video tự động AI Video Maker (Phiên bản v2.3+ - Đã tích hợp các tính năng điện ảnh nâng cao, router 4 tầng và cache thông minh).

---

## 1. Tổng quan Hệ thống (System Overview)

Hệ thống được thiết kế theo kiến trúc Client-Server:
- **Frontend (React + Vite):** Giao diện người dùng đơn trang (SPA) cho phép nhập ý tưởng kịch bản, cấu hình nhân vật (Character Reference), tuỳ chỉnh giọng đọc/âm nhạc, bật/tắt các hiệu ứng (Veo 3, Beat Sync, Ken Burns, GPU Encode) và theo dõi tiến trình qua WebSocket.
- **Backend (FastAPI - Python):** Xử lý logic lõi, điều phối các luồng gọi API bên ngoài (Gemini 2.5, Imagen 3, Veo 3.1, Edge-TTS) và tiến hành render video tự động thông qua MoviePy.
- **Communication:** Giao tiếp qua REST API tại endpoint `/api/generate-video` (hoặc `/api/render-video`) kết hợp với WebSockets để push trạng thái real-time.

---

## 2. Luồng xử lý cốt lõi (Main Workflow)

Quy trình từ ý tưởng thành video hoàn chỉnh diễn ra hoàn toàn tự động qua 4 bước:

### Bước 1: Tiếp nhận yêu cầu (Frontend → Backend)
- Người dùng nhập *Chủ đề (Topic)*, *Mô tả Nhân vật (Character Reference)* và các tuỳ chọn hiệu ứng (Ken Burns, Veo, GPU Encode, Beat Sync).
- Payload được gửi qua HTTP POST tới `/api/generate-script` hoặc `/api/render-video`.

### Bước 2: Sinh Kịch bản & Phân cảnh (Gemini Service)
- Dịch vụ `gemini_service.py` gọi **Gemini 2.5 Flash/Pro** với cơ chế **Structured Outputs** (Pydantic Schema) để đảm bảo trả về JSON chuẩn xác 100%.
- Hệ thống phân tích chủ đề và trả về các phân cảnh chi tiết (lời thoại, mô tả hình ảnh).

### Bước 3: Tạo Âm thanh & Hình ảnh tĩnh/động (TTS & AI Generation)
- **Voice:** `tts_service.py` sử dụng **OmniVoice V3.3** (chạy GPU, Zero-shot voice cloning) làm engine chính để sinh giọng đọc cao cấp. Đi kèm cơ chế Fallback tự động 4 lớp (Edge-TTS -> gTTS -> Offline TTS) và TTS Cache. Hỗ trợ Voice Cloning qua API chuyên biệt.
- **Images/Video Router 4 Tầng:** `image_router.py` quản lý luồng fallback: **Veo 3.1** (ưu tiên nếu bật) $\rightarrow$ **Pexels Stock Video** (video thật) $\rightarrow$ **Google Imagen 3** (ảnh AI chất lượng cao) $\rightarrow$ **Pollinations AI** (ảnh AI siêu tốc). Hỗ trợ chế độ `prefer_stock_video` ép dùng video stock cho 100% cảnh.

### Bước 4: Render Video (Video Service)
- Dịch vụ `video_service.py` sử dụng thư viện **MoviePy v2.x**.
- **Hiệu ứng & Chuyển cảnh:** Áp dụng Transition Engine 10 kiểu (slide, whip_pan, page_flip...), Ken Burns (zoom tĩnh), Hook Zoom Boost (zoom mạnh cảnh đầu), Frame Chaining, và Beat Sync. Hỗ trợ thay đổi từng cảnh.
- **Subtitles & BGM:** Tự động Auto-ducking nhạc nền khi có giọng đọc, render phụ đề động (Karaoke effect).
- Xuất file `.mp4` (hỗ trợ tăng tốc GPU NVENC) ở định dạng khung hình dọc (Tiktok/Reels) về thư mục `assets/output`.

---

## 3. Cấu trúc mã nguồn (Directory Structure)

```text
AI-VIDEO-MAKER/
├── frontend/                     # UI Application (React + Vite)
│   ├── src/App.jsx               # Logic tương tác, tuỳ chỉnh nâng cao
│   ├── src/index.css             # Định dạng, hiệu ứng UI
│   └── vite.config.js
├── backend/                      # API Server (FastAPI)
│   ├── main.py                   # Điểm đầu vào, khai báo Endpoint & Background Tasks
│   ├── services/
│   │   ├── gemini_service.py     # Gọi LLM với Structured Outputs
│   │   ├── image_router.py       # Tích hợp Imagen 3 sinh ảnh
│   │   ├── veo_service.py        # Tích hợp Veo 3.1 sinh video
│   │   ├── tts_service.py        # Tích hợp lõi OmniVoice V3.2 chạy GPU và cơ chế Fallback Edge-TTS (async/await)
│   │   ├── audio_mix_service.py  # Xử lý Smart Audio Mixing (Auto-ducking)
│   │   ├── beat_sync.py          # Logic đồng bộ hình ảnh/video theo nhịp bass (Beat Sync)
│   │   ├── motion_effects.py     # Hiệu ứng chuyển động (Ken Burns, Zoom Boost)
│   │   ├── preset_service.py     # Quản lý cấu hình lưu sẵn của người dùng
│   │   ├── project_service.py    # Quản lý Checkpoint Smart Resume
│   │   ├── key_manager.py        # Quản lý xoay vòng API Keys tự động
│   │   ├── render_worker.py      # Chạy MoviePy/FFmpeg trong process con
│   │   ├── hook_engine.py        # 4 hiệu ứng mở màn (Slot/Blackout/Typewriter/Vignette)
│   │   ├── log_setup.py          # UTF-8 streams + log ra file + nhãn [job_id] (mục 6)
│   │   └── video_service.py      # Core render (MoviePy v2) & ghép phụ đề
│   ├── scripts/check_imports.py  # Cổng chất lượng chống UnboundLocalError (mục 6)
│   ├── logs/                     # backend.log, render_worker.log (xoay vòng 10MB×5)
│   ├── config.py                 # NGUỒN SỰ THẬT DUY NHẤT cho mọi đường dẫn file
│   ├── assets/                   # Nơi lưu trữ tài nguyên
│   │   ├── bgm/, sfx/, slot_covers/, fonts/   # ĐI KÈM MÃ NGUỒN — không di dời
│   │   ├── audio/, images/, output/, cache/, projects/, uploads/, overrides/
│   │   │                         # ↑ dữ liệu sinh ra — chuyển sang ổ khác được
│   │   │                           qua CUSTOM_ASSETS_DIR trong .env
│   └── .env                      # Lưu API Keys + CUSTOM_ASSETS_DIR
├── start.bat, stop.bat           # Khởi chạy trực tiếp (uvicorn) và dọn tiến trình
├── start-pm2.bat                 # Khởi chạy qua PM2 (autorestart + log bền) — NÊN DÙNG
├── setup-pm2-autostart.bat       # Đăng ký Scheduled Task tự chạy cùng Windows
├── ecosystem.config.js           # Cấu hình PM2
└── scripts/export_context.py     # Trích xuất mã nguồn ra AI_CONTEXT.md (tiện ích rời)
```

---

## 4. Các tính năng Nâng cao (Advanced Features)

Phiên bản hiện tại đã hoàn thiện các tính năng điện ảnh tiên tiến:
1. **Veo 3.1 Image-to-Video:** Tự động tạo cảnh quay động chân thực với tùy chọn *Veo Ambient Audio* (âm thanh môi trường). Tự động cảnh báo UI khi hết quota billing.
2. **OmniVoice V3.3 & Prosody Engine:** Sinh giọng đọc cao cấp bằng GPU với Zero-shot Cloning, Prosody Engine (micro-prosody per sentence), Forced Alignment Word Boundaries (stable-ts) cho phụ đề Karaoke chính xác, và kho giọng custom.
3. **Beat Sync & Audio Mixing:** Phân tích Peak âm thanh của BGM để giật hình/chuyển cảnh khớp nhịp nhạc (Hype Drill, Phonk).
4. **Motion Dynamics & Transitions:** Hỗ trợ Ken Burns, Hook Zoom Boost (nhấn mạnh 2 giây đầu video), và Transition Engine 10 kiểu.
5. **Stock Video Router & Prefer Stock Mode:** Xử lý luồng tải video stock thông minh, tự động lọc từ khóa, kèm toggle ép dùng footage thực tế tạo sự chân thực.
6. **Smart Resume Checkpoints:** Khôi phục render dang dở không cần tốn API chạy lại các bước TTS/Hình ảnh đã xong.
7. **Character Consistency:** Cho phép truyền *Character Reference* để Gemini & Imagen giữ nguyên diện mạo nhân vật xuyên suốt các cảnh.

---

## 5. Nợ kỹ thuật & Định hướng tiếp theo (Technical Debt & Future)

Dù đã giải quyết phần lớn các lỗi hệ thống của bản MVP (đứt gãy Event Loop, HTTP Timeout, rò rỉ bộ nhớ), vẫn còn một số điểm cần tối ưu:

### ✅ Đã xử lý (v2.3+ — 2026-07-24):
1. **~~Tách Component Frontend~~:** `App.jsx` đã được tái cấu trúc thành 9 components riêng biệt + `AppContext.jsx` quản lý state tập trung.
2. **~~Offload Video Rendering~~:** Tạo `render_worker.py` sử dụng `multiprocessing.Process` để tách MoviePy/FFmpeg ra process con.
3. **~~Caching AI Requests~~:** Nâng cấp `cache_service.py` V2 hỗ trợ cache binary media (ảnh/video) theo hash prompt.
4. **~~Smart Resume & Preset System~~:** Đã bổ sung cơ chế lưu file project tự động để nối tiếp render nếu lỗi, cùng hệ thống preset.

### ✅ Đã xử lý (2026-07-28 — Vận hành & Chẩn đoán):
1. **~~Mất dấu vết khi crash~~:** Log ghi ra file, có traceback đầy đủ và nhãn `[job_id]`. Xem mục 6.
2. **~~Lỗi lọt mọi lớp kiểm tra~~:** `scripts/check_imports.py` bắt `UnboundLocalError` do import cục bộ.
3. **~~Không có autorestart~~:** Chạy qua PM2 bằng `start-pm2.bat`.

### 🟢 Định hướng tiếp theo:
1. **Distributed Rendering:** Khi mở rộng lên nhiều user đồng thời, cần chuyển từ `multiprocessing` sang Redis Queue + Celery Worker trên máy chủ Render Farm riêng.
2. **Distributed Cache:** Cache hiện tại lưu trên disk local. Cần chuyển sang Redis/Memcached khi deploy multi-server.
3. **Auto-publish:** Tích hợp API đăng video tự động lên TikTok/YouTube Shorts.
4. **Log tập trung:** Khi chạy nhiều render worker song song, `RotatingFileHandler` mỗi tiến trình một file sẽ không đủ — cần `QueueHandler` + một tiến trình ghi log duy nhất.

---

## 6. Vận hành & Chẩn đoán (Operations & Diagnostics)

*Bổ sung 2026-07-28, sinh ra từ một sự cố thật: 11/07 backend chết ngầm giữa job render với `UnboundLocalError`, nhưng vì log không được ghi ra file nên mãi 17 ngày sau mới truy được nguyên nhân.*

### 6.1. Khởi chạy

| Cách | Lệnh | Đặc điểm |
|---|---|---|
| PM2 (khuyến nghị) | `start-pm2.bat` | Autorestart khi crash, log bền, chạy nền |
| Trực tiếp | `start.bat` | Xem log cuộn trực tiếp trong cmd |
| Tự chạy khi boot | `setup-pm2-autostart.bat` | Scheduled Task gọi `pm2 resurrect` lúc đăng nhập |

`pm2 startup` **không hỗ trợ Windows** — đó là lý do cần script riêng. `ecosystem.config.js` cố ý để `watch: false`: MoviePy/FFmpeg ghi file tạm trong cây dự án, bật watch sẽ restart server **giữa lúc đang render**.

### 6.2. Hệ thống Log (`services/log_setup.py`)

- `backend/logs/backend.log` — tiến trình FastAPI chính.
- `backend/logs/render_worker.log` — process con (MoviePy, FFmpeg mastering).
- Xoay vòng **10MB × 5**, encoding UTF-8 (mặc định cp1252 sẽ làm vỡ mọi dòng log tiếng Việt).

**Nhãn `[job_id]` trên mọi dòng** — cài bằng `ContextVar` + `logging.Filter` ở tầng handler, nên phủ cả log của `services/` lẫn thư viện ngoài (`httpx`, `google_genai`) mà không phải sửa dòng nào trong các module đó. Đây là lý do không dùng `LoggerAdapter`: adapter chỉ gắn nhãn cho lời gọi qua chính nó, tức chỉ `main.py`.

`ContextVar` không vượt qua ranh giới tiến trình, nên `render_worker._worker_main()` phải gọi lại `set_job_id()` cho riêng nó.

**Mọi `logger.error` đều có `exc_info=True`** → traceback chỉ đúng file/dòng. Các `logger.warning` cố ý KHÔNG có, vì đó là những nhánh fallback đã biết trước nguyên nhân (Veo hết quota, Pexels 403) — thêm traceback chỉ làm loãng log.

### 6.3. Cổng chất lượng

Ba lớp chạy tự động ở `start.bat`, `start-pm2.bat` và git pre-commit hook:

| Lớp | Bắt được |
|---|---|
| `compileall` | Lỗi cú pháp |
| `ruff --select F821,F811,E9` | Tên chưa import, định nghĩa trùng |
| `scripts/check_imports.py` | `UnboundLocalError` do import cục bộ che module import |

Lớp thứ ba tồn tại vì hai lớp trên **đều bỏ lọt** loại lỗi này — cú pháp hợp lệ, tên vẫn có import, chỉ sai thứ tự thực thi nên chỉ nổ lúc runtime ở nhánh hiếm chạy.

### 6.4. Bẫy đã gặp

- **Log PM2 cũ có thể đánh lừa.** Sự cố 11/07 nằm trong `~/.pm2/logs/` nhưng file đó đóng băng vì backend thực tế chạy qua `start.bat`. Các file cũ đã đổi tên thành `*.2026-07-11.log`. Luôn kiểm tra `mtime` và đối chiếu tên hàm trong traceback với code hiện tại trước khi kết luận.
- **File `.bat` phải dùng CRLF** — `cmd.exe` xử lý sai khối `if (...)` nhiều dòng nếu file là LF.
