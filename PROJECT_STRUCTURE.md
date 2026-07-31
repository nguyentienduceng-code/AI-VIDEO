# Bảng Giải Trình Cấu Trúc Dự Án AI-VIDEO-MAKER (Toàn Diện v2.3+)

*Tài liệu dành cho chuyên gia AI & IT phục vụ việc đánh giá tổng thể, bảo trì và lên kế hoạch nâng cấp.*

---

## 1. Tổng quan Hệ thống (System Overview)

**AI-VIDEO-MAKER** là hệ thống phần mềm dạng Client-Server (Single Page Application) chuyên dụng để tự động hoá toàn bộ quy trình sản xuất video dạng ngắn (TikTok, YouTube Shorts, Reels) bằng các mô hình Trí tuệ Nhân tạo tiên tiến nhất.

**Các tính năng cốt lõi (Features):**

- **AI Storyteller (Gemini 2.5 Flash/Pro)**: Tự động viết kịch bản chi tiết dựa trên chủ đề (Topic). Hỗ trợ các Option linh hoạt (Storyteller, Quiz/Listicle, Ảnh -> Video) với độ sáng tạo cao.
- **Script → Video (Strict Mode)**: Trình bóc tách kịch bản chuyên nghiệp. AI giữ nguyên văn 100% lời thoại người dùng, tự động nhận diện và dịch các "chỉ dẫn đạo diễn" sang Prompt hình ảnh/hiệu ứng. Tích hợp Regex loại bỏ Emoji tự động trước khi nạp vào TTS để tránh đọc sai.
- **AI Image Generation (Imagen 3)**: Sinh hình ảnh minh họa chất lượng cao cho từng phân cảnh.
- **AI Video Generation (Veo 3.1)**: Biến hình ảnh tĩnh thành video điện ảnh có chuyển động mượt mà.
- **Advanced AI Voice (OmniVoice v3.2 & Edge-TTS)**: Đọc thuyết minh bằng giọng điệu tự nhiên. Sử dụng engine OmniVoice chạy trên GPU cho chất lượng cao (Zero-shot cloning, cố định timbre), kết hợp cơ chế fallback 4 lớp (Edge-TTS -> gTTS -> Offline SAPI5) để đảm bảo không đứt gãy luồng xử lý. Cung cấp **Voice & BGM Preview API** cho phép nghe thử trực tiếp trên giao diện.
- **Karaoke Subtitles & Animated Captions**: Phụ đề tự động nhảy khớp âm thanh (Word-level boundary) bằng định dạng ASS, hiển thị đầy đủ Emoji sống động.
- **Smart Audio Mixing & Beat Sync**: Hệ thống âm thanh được Master độc lập bằng FFmpeg Engine (Sidechain ducking, Loudnorm).
- **Premium UI/UX**: Giao diện người dùng hiện đại, nổi bật với các Micro-animations, hiệu ứng Glow và các thẻ chọn Mode (Option) trực quan.
- **Hardware Acceleration**: GPU NVENC được kích hoạt để nén và burn-in phụ đề (ASS) trong 1 bước duy nhất.

---

## 2. Kiến trúc Thư mục và Mã nguồn (Directory Structure)

```text
AI-VIDEO-MAKER/
├── USER_GUIDE.md                 # Hướng dẫn sử dụng cho người dùng (Cách dùng App & AI Skill)
├── PROJECT_STRUCTURE.md          # Sơ đồ kiến trúc tổng thể (file này)
├── ROADMAP.md                    # Lịch trình phát triển và nâng cấp hệ thống
├── ARCHITECTURE.md               # Kiến trúc luồng dữ liệu chuyên sâu
├── .agents/skills/               # Nơi chứa các AI Skill (vd: content-cinematic)
├── frontend/                     # UI Application (React + Vite)
│   ├── src/App.jsx               # Toàn bộ logic giao diện, cài đặt hiệu ứng và kết nối API.
│   ├── src/index.css             # Định dạng UI bằng Tailwind CSS.
│   └── vite.config.js            # Cấu hình build.
├── backend/                      # API Server (FastAPI - Python)
│   ├── main.py                   # Điểm neo (Entry point) khởi chạy Server & Routing APIs (xử lý polling/background task).
│   ├── services/
│   │   ├── gemini_service.py     # Prompt tương tác LLM với Structured Outputs.
│   │   ├── veo_service.py        # Logic tạo video clip bằng Google Veo 3.1.
│   │   ├── image_router.py       # Phân luồng sinh ảnh (Veo → Pexels → Imagen → Pollinations).
│   │   ├── image_upload_service.py # Nhận ảnh user tải lên (photo_narration / ghi đè cảnh).
│   │   ├── tts_service.py        # Tích hợp OmniVoice V3.2 (Zero-shot, Chunking) & Edge-TTS với cơ chế fallback 4 lớp và regex ngắt nghỉ.
│   │   ├── video_service.py      # Core ghép media cơ bản (RAW Video) bằng MoviePy.
│   │   ├── ffmpeg_assembler.py   # Đường nhanh: dựng cả timeline bằng MỘT lệnh FFmpeg (xfade + NVENC).
│   │   ├── audio_mix_service.py  # FFmpeg Mastering Engine: Xử lý BGM Auto-ducking, EQ, Loudnorm & ASS Burn-in.
│   │   ├── render_worker.py      # Chạy MoviePy/FFmpeg trong process con (multiprocessing).
│   │   ├── hook_engine.py        # 4 hiệu ứng mở màn (Slot Machine, Blackout, Typewriter, Vignette).
│   │   ├── beat_sync.py          # Phân tích Audio peak tạo điểm nhấn hình ảnh.
│   │   ├── motion_effects.py     # Source of Truth cho Timeline, Zoom, Ken Burns, Transitions.
│   │   ├── cache_service.py      # Cache V2: kịch bản Gemini + media nhị phân theo hash prompt.
│   │   ├── preset_service.py     # Hệ thống quản lý và tự động merge Presets người dùng.
│   │   ├── project_service.py    # Hệ thống Smart Resume Checkpoints (lưu trạng thái job).
│   │   ├── quota_service.py      # Đếm số lần gọi API còn lại trong ngày.
│   │   ├── key_manager.py        # Quản lý xoay vòng API Keys.
│   │   └── log_setup.py          # Ép stdout/stderr UTF-8 + ghi log ra file + gắn [job_id]. Xem §5.
│   ├── scripts/
│   │   └── check_imports.py      # Cổng chất lượng: bắt UnboundLocalError do import cục bộ. Xem §5.
│   ├── logs/                     # Log ứng dụng, xoay vòng 10MB × 5 (đã .gitignore). Xem §5.
│   ├── config.py                 # Nguồn sự thật duy nhất cho đường dẫn file. Tách 2 gốc:
│   │                             #   BUNDLED (bgm/sfx/fonts — ở lại cùng mã nguồn)
│   │                             #   DATA    (ảnh/video/cache — đổi ổ được qua CUSTOM_ASSETS_DIR)
│   ├── assets/                   # Kho lưu trữ tài nguyên tạm và thành phẩm.
│   │   ├── bgm/, sfx/, slot_covers/, fonts/            # tài nguyên gốc, chỉ đọc
│   │   ├── audio/, images/, output/, cache/, projects/ # dữ liệu sinh ra, di dời được
│   │   ├── uploads/, overrides/, voices_preview/, presets.json
│   └── .env                      # Lưu biến môi trường (API keys, CUSTOM_ASSETS_DIR).
├── start.bat, stop.bat           # Khởi chạy trực tiếp (uvicorn trong cửa sổ cmd) và dọn tiến trình.
├── start-pm2.bat                 # Khởi chạy qua PM2: autorestart + log bền. NÊN DÙNG. Xem §5.
├── setup-pm2-autostart.bat       # Đăng ký/gỡ Scheduled Task tự chạy cùng Windows.
├── ecosystem.config.js           # Cấu hình PM2 (đường dẫn tuyệt đối, chặn vòng lặp crash).
└── scripts/                      # Tiện ích rời, KHÔNG thuộc luồng chạy của app
    └── export_context.py         # Trích xuất mã nguồn ra file AI_CONTEXT.md.
```

> Phân biệt hai thư mục cùng tên: `scripts/` ở gốc là tiện ích thủ công cho người phát triển;
> `backend/scripts/` là công cụ được app và git hook gọi tự động.

---

## 3. Bản đồ API & Data Flow (API Map)

Hệ thống hoạt động theo **Luồng xử lý Bất đồng bộ (Async Pipeline)** để ngăn ngừa HTTP Timeout:

### Nhóm API Quản lý Tài nguyên:

1. `GET /api/bgm-list`: Lấy danh sách nhạc nền có sẵn.
2. `GET /api/voices`: Lấy danh sách giọng đọc tiếng Việt.
3. `POST /api/upload-images`: Tải ảnh cục bộ lên server (Dành cho mode Photo Narration / Slideshow).
4. `POST /api/voice-clone`: Upload mẫu âm thanh 5-10s tạo giọng clone tự động bằng Whisper.
5. `GET/POST/DELETE /api/presets`: Quản lý cấu hình lưu sẵn.
6. `GET /api/quota`: Kiểm tra quota & giới hạn API.
7. `GET/POST /api/storage-config`: Xem/đổi thư mục lưu dữ liệu sinh ra sang ổ đĩa khác. POST chỉ ghi `CUSTOM_ASSETS_DIR` vào `.env` — **phải khởi động lại backend** mới có hiệu lực (xem `backend/config.py`).

### Nhóm API Hậu kỳ (Post-Render Fine-Tuning):

1. `POST /api/cache-probe`: Trả về `{audio_cached, image_cached}` cho từng cảnh, để UI hiện đèn 🟢 *đã có sẵn* / 🔴 *sẽ tạo mới*. Khoá cache tính y hệt lúc render — sửa công thức ở `image_router` hoặc `tts_service` thì phải sửa cả đây, nếu không đèn báo sẽ nói dối.
2. `POST /api/scene-asset`: Tải ảnh/video của user lên để **ghi đè** hình AI của một cảnh. Trả về `asset_id`, gắn vào `scene.override_asset` rồi render bình thường. Không gắn với `job_id` vì mỗi lần render lại là một job mới.
3. `GET/DELETE /api/scene-asset/{asset_id}`: Xem lại / gỡ file ghi đè.
4. `POST /api/preview-scene-voice`: Nghe thử giọng đọc của MỘT cảnh (kể cả nhịp nghỉ `<break>`). Đi qua đúng `synthesize_speech` với đúng bộ tham số của pipeline nên **nạp luôn vào TTS cache** — nghe thử xong, cảnh đó chuyển 🟢 và lúc render không phải sinh lại.
5. `GET /api/cache-stats` + `DELETE /api/cache`: Xem/dọn bộ nhớ đệm. Mặc định chỉ xoá media; `?include_script_cache=true` mới xoá kịch bản Gemini (sinh lại tốn quota API). `quota.json` luôn được bảo vệ dù nằm chung thư mục.

### Nhóm API Core Pipeline:

4. **Bước 1: Sinh Kịch bản (`POST /api/generate-script`)**
   - **Đầu vào:** Chủ đề, Mô tả nhân vật, Mode.
   - **Hoạt động:** Chạy đồng bộ (Sync). Gọi Gemini phân tích và trả về ngay mảng JSON chứa các cảnh (Scenes) chi tiết (Hình ảnh, Lời bình, SFX, Chuyển cảnh riêng).
5. **Bước 2: Kết xuất Video (`POST /api/render-video`)**
   - **Đầu vào:** Danh sách Scenes, Cấu hình hiệu ứng.
   - **Hoạt động:**
     - 1. Tính toán Timeline tại `motion_effects.py`.
     - 2. Ghép RAW Video (không có nhạc nền/phụ đề) bằng `video_service.py`.
     - 3. Mix âm thanh chuẩn FFmpeg & Burn phụ đề, tối ưu GPU tại `audio_mix_service.py`.
   - Trả về `job_id` lập tức để Frontend bắt đầu cơ chế Polling.
6. **Polling Theo dõi (`GET /api/job-status/{job_id}`)**
   - Frontend gửi GET request định kỳ lấy trạng thái tiến trình (Progress %, Message, Status).
7. **Tải File (`GET /api/download/{filename}`)**
   - Tải file MP4 thành phẩm.

---

## 4. Quản lý Nợ Kỹ thuật & Khuyến nghị Cập nhật (Technical Debt)

*Các lỗi lớn ở bản MVP như Event Loop crash, HTTP Timeout, Tràn bộ nhớ temp file đã được fix dứt điểm ở v2.0.*

### ✅ Đã xử lý (v2.3+ — 2026-07-24):

1. **~~Quản lý State Frontend~~:** `App.jsx` đã được tách thành 9 components + `AppContext.jsx` quản lý state tập trung.
2. **~~Offload Render~~:** `render_worker.py` chạy MoviePy/FFmpeg trong `multiprocessing.Process` riêng biệt, giao tiếp qua file JSON.
3. **~~Cache AI~~:** `cache_service.py` V2 cache binary media (ảnh/video) theo hash prompt. Auto-cleanup khi > 5GB.
4. **~~Smart Resume Checkpoint~~:** Lưu tiến trình render vào JSON (`project_service.py`) để tránh chạy lại TTS/Hình ảnh từ đầu khi lỗi.
5. **~~Pexels Video Stock Fix~~:** Fix lỗi HTTP 403 bằng cách thêm `User-Agent` chuẩn, hỗ trợ `prefer_stock_video` ép dùng video thật.

### ✅ Đã xử lý (2026-07-28 — Vận hành & Chẩn đoán):

1. **~~Mất dấu vết khi crash~~:** Log giờ ghi ra `backend/logs/`, kèm traceback đầy đủ và nhãn `[job_id]`. Xem §5.
2. **~~Lỗi lọt qua mọi lớp kiểm tra~~:** `check_imports.py` bắt `UnboundLocalError` do import cục bộ — loại lỗi mà `py_compile` và `ruff` đều mù. Chạy tự động ở `start.bat` và git pre-commit.
3. **~~Không có autorestart~~:** `start-pm2.bat` + `ecosystem.config.js` cho phép chạy qua PM2.

### 🟢 Định hướng mở rộng:

1. Chuyển sang Redis Queue + Celery khi mở rộng lên Render Farm multi-server.
2. Tích hợp API Auto-publish TikTok/YouTube Shorts.
3. Batch render hàng loạt video từ danh sách chủ đề CSV.

---

## 5. Vận hành & Chẩn đoán (Operations & Diagnostics)

*Bổ sung 2026-07-28. Toàn bộ mục này sinh ra từ một sự cố thật: ngày 11/07 backend chết ngầm giữa job render với `UnboundLocalError`, nhưng vì không có log bền nên 17 ngày sau mới truy ra — và suýt kết luận sai vì đọc nhầm log cũ.*

### 5.1. Ba cách khởi chạy

| Cách | Lệnh | Khi nào dùng |
|---|---|---|
| PM2 (khuyến nghị) | `start-pm2.bat` | Dùng hằng ngày. Tự dựng lại khi crash, log bền, đóng cửa sổ vẫn chạy. |
| Trực tiếp | `start.bat` | Khi cần xem log cuộn trực tiếp trong cmd lúc debug. |
| Tự chạy khi boot | `setup-pm2-autostart.bat` | Cài một lần. Đăng ký Scheduled Task gọi `pm2 resurrect` lúc đăng nhập. |

> `pm2 startup` **không chạy trên Windows** — đó là lý do phải có `setup-pm2-autostart.bat` thay vì dùng lệnh PM2 tiêu chuẩn.
>
> `ecosystem.config.js` cố ý đặt `watch: false`. MoviePy/FFmpeg ghi file tạm ngay trong cây dự án; bật watch sẽ khiến PM2 restart server **giữa lúc đang render**.

### 5.2. Hệ thống Log

Cấu hình tại `services/log_setup.py`, gọi ở cả tiến trình FastAPI lẫn process con.

| File | Nội dung |
|---|---|
| `backend/logs/backend.log` | Log ứng dụng của tiến trình chính. |
| `backend/logs/render_worker.log` | Log của process con (MoviePy, FFmpeg mastering). |
| `backend/logs/pm2-backend-*.log` | stdout/stderr thô do PM2 bắt được. |

Ba đặc tính quan trọng:

1. **Xoay vòng 10MB × 5** — không phình đĩa vô hạn.
2. **Nhãn `[job_id]` trên mọi dòng**, kể cả log của `services/` và thư viện ngoài (`httpx`, `google_genai`). Cài bằng `ContextVar` + `logging.Filter` ở tầng handler, nên không cần sửa một dòng nào trong `services/`. Nhờ đó hai job chạy chồng nhau vẫn tách bạch được.
3. **`exc_info=True` ở mọi `logger.error`** — có traceback đầy đủ chỉ đúng file/dòng, thay vì chỉ một câu `str(e)` cụt.

> **Vì sao mỗi tiến trình một file riêng:** `RotatingFileHandler` không an toàn đa tiến trình trên Windows — xoay vòng là đổi tên file, mà Windows cấm đổi tên file đang bị tiến trình khác mở. Nếu sau này chạy nhiều worker song song thật sự, phải đổi sang `QueueHandler` + một tiến trình ghi log duy nhất.

### 5.3. Cổng chất lượng (Quality Gates)

Ba lớp, chạy tự động ở `start.bat`, `start-pm2.bat` và git pre-commit hook:

| Lớp | Bắt được gì |
|---|---|
| `python -m compileall` | Lỗi cú pháp. |
| `ruff --select F821,F811,E9` | Gọi tên chưa import, định nghĩa trùng lặp. |
| `python scripts/check_imports.py` | `UnboundLocalError` do import cục bộ che module import. |

Lớp thứ ba tồn tại vì hai lớp trên **đều bỏ lọt** loại lỗi đó: cú pháp hoàn toàn hợp lệ và tên vẫn có được import, chỉ sai thứ tự thực thi — nên nó chỉ nổ lúc runtime, ở đúng nhánh hiếm chạy. Đã kiểm chứng bằng cách tái dựng lại bug ngày 11/07.

Chạy tay bất cứ lúc nào:

```bash
cd backend
venv/Scripts/python.exe scripts/check_imports.py
```

Bỏ qua hook khi thật sự cần: `git commit --no-verify`.

### 5.4. Bẫy đã gặp — đừng lặp lại

- **Log PM2 cũ có thể đánh lừa.** Sự cố 11/07 nằm trong `~/.pm2/logs/`, nhưng file đó đóng băng vì backend thực tế chạy qua `start.bat` chứ không qua PM2. Các file cũ đã được đổi tên thành `*.2026-07-11.log`. **Luôn kiểm tra `mtime` và đối chiếu tên hàm trong traceback với code hiện tại** trước khi kết luận.
- **File `.bat` phải là CRLF.** `cmd.exe` xử lý khối `if (...)` nhiều dòng bị vỡ nếu file dùng LF.

---

## 6. Phụ lục: Mã nguồn Cốt lõi (Code Appendix)

### Phụ lục 1: Schema Request Mới (backend/main.py)

Tích hợp các cài đặt điện ảnh nâng cao.

```python
class RenderVideoRequest(BaseModel):
    scenes: List[dict]
    mode: str = "storyteller"
    voice: Optional[str] = None
    bgm_track: Optional[str] = None
    use_veo: bool = False
    use_frame_chaining: bool = False
    use_beat_sync: bool = False
    use_veo_ambient_audio: bool = False
    use_gpu_encode: bool = False
    hook_zoom_boost: bool = False
    use_ken_burns: bool = False
    use_animated_captions: bool = True
    subtitle_style: str = "karaoke_bold"
    prefer_stock_video: bool = False
    use_sfx: bool = True
    sfx_volume: float = 0.5
    color_grading: str = "warm_cinematic"
    hook_effect: str = "word_by_word"
    use_breathing: bool = False
```

### Phụ lục 2: Đồng bộ nhịp tim nhạc - Beat Sync (backend/services/beat_sync.py)

Logic cơ bản để phát hiện nhịp điệu (Onset detection) từ track BGM, làm căn cứ để chuyển cảnh hoặc zoom.

```python
# Phân tích Onset (điểm nhấn bass mạnh)
y, sr = librosa.load(bgm_path)
onset_env = librosa.onset.onset_strength(y=y, sr=sr)
peaks = librosa.util.peak_pick(onset_env, pre_max=3, post_max=3, pre_avg=3, post_avg=5, delta=0.5, wait=10)
peak_times = librosa.frames_to_time(peaks, sr=sr)
```

---

*Tài liệu được kết xuất tự động - Đã cập nhật v2.3+ Điện Ảnh.*
