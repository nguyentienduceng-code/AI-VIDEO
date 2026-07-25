áa

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
│   │   ├── image_router.py       # Phân luồng sinh ảnh.
│   │   ├── tts_service.py        # Tích hợp OmniVoice V3.2 (Zero-shot, Chunking) & Edge-TTS với cơ chế fallback 4 lớp và regex ngắt nghỉ.
│   │   ├── video_service.py      # Core ghép media cơ bản (RAW Video) bằng MoviePy.
│   │   ├── audio_mix_service.py  # FFmpeg Mastering Engine: Xử lý BGM Auto-ducking, EQ, Loudnorm & ASS Burn-in.
│   │   ├── beat_sync.py          # Phân tích Audio peak tạo điểm nhấn hình ảnh.
│   │   ├── motion_effects.py     # Source of Truth cho Timeline, Zoom, Ken Burns, Transitions.
│   │   ├── preset_service.py     # Hệ thống quản lý và tự động merge Presets người dùng.
│   │   ├── project_service.py    # Hệ thống Smart Resume Checkpoints (lưu trạng thái job).
│   │   └── key_manager.py        # Quản lý xoay vòng API Keys.
│   ├── assets/                   # Kho lưu trữ tài nguyên tạm và thành phẩm.
│   │   ├── audio/, images/, bgm/, voices_preview/, output/, cache/, presets.json
│   └── .env                      # Lưu biến môi trường.
├── start.bat, stop.bat           # Script khởi chạy và dọn dẹp tiến trình.
└── export_context.py             # Script tự động trích xuất mã nguồn ra file AI_CONTEXT.md.
```

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

### 🟢 Định hướng mở rộng:

1. Chuyển sang Redis Queue + Celery khi mở rộng lên Render Farm multi-server.
2. Tích hợp API Auto-publish TikTok/YouTube Shorts.
3. Batch render hàng loạt video từ danh sách chủ đề CSV.

---

## 5. Phụ lục: Mã nguồn Cốt lõi (Code Appendix)

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
