# Bối cảnh mã nguồn - AI Video Maker

Tài liệu này tổng hợp toàn bộ cấu trúc thư mục và mã nguồn của dự án AI Video Maker. Bạn hãy đọc nó để nắm rõ ngữ cảnh trước khi đưa ra bất kỳ giải pháp hay đoạn mã nào.

## 1. Cấu trúc thư mục
```text
AI-VIDEO-MAKER/
├── .gitignore
├── AI_CONTEXT.md
├── ARCHITECTURE.md
├── PROJECT_STRUCTURE.md
├── backend
│   ├── .env
│   ├── .env.example
│   ├── 3d3933be-f990-451e-94a5-245edfcb5894.mp4.tmpTEMP_MPY_wvf_snd.mp4
│   ├── 592c332b-81dc-478a-b5f5-52780d58b895TEMP_MPY_wvf_snd.mp4
│   ├── final_outputTEMP_MPY_wvf_snd.mp4
│   ├── main.py
│   ├── requirements.txt
│   ├── scripts
│   │   └── generate_sfx.py
│   ├── services
│   │   ├── audio_mix_service.py
│   │   ├── beat_sync.py
│   │   ├── cache_service.py
│   │   ├── gemini_service.py
│   │   ├── image_router.py
│   │   ├── image_upload_service.py
│   │   ├── key_manager.py
│   │   ├── motion_effects.py
│   │   ├── render_export.py
│   │   ├── tts_service.py
│   │   ├── veo_service.py
│   │   └── video_service.py
│   ├── templates
│   ├── test_duration.py
│   ├── test_gen.py
│   ├── test_gen2.py
│   ├── test_pipeline.py
│   ├── test_tts_full.py
│   ├── test_veo_karaoke.py
│   └── test_workspace
│       ├── final_output.mp4
│       ├── final_raw.mp4
│       ├── scene_0.jpg
│       ├── scene_0.jpg_0.mp4
│       ├── scene_0.mp3
│       ├── scene_1.jpg
│       ├── scene_1.jpg_1.mp4
│       ├── scene_1.mp3
│       ├── scene_2.jpg
│       ├── scene_2.jpg_2.mp4
│       ├── scene_2.mp3
│       ├── scene_3.jpg
│       ├── scene_3.jpg_3.mp4
│       └── scene_3.mp3
├── ecosystem.config.js
├── export_context.py
├── frontend
│   ├── .env.example
│   ├── .gitignore
│   ├── .oxlintrc.json
│   ├── README.md
│   ├── index.html
│   ├── package-lock.json
│   ├── package.json
│   ├── postcss.config.js
│   ├── public
│   │   ├── favicon.svg
│   │   └── icons.svg
│   ├── src
│   │   ├── App.css
│   │   ├── App.jsx
│   │   ├── AppContext.jsx
│   │   ├── components
│   │   │   ├── RenderProgress.jsx
│   │   │   ├── ScriptEditor.jsx
│   │   │   └── SettingsPanel.jsx
│   │   ├── constants.js
│   │   ├── index.css
│   │   └── main.jsx
│   ├── tailwind.config.js
│   └── vite.config.js
├── generate_rentflow_videos.py
├── start-daemon.bat
├── start-hidden.vbs
├── start.bat
├── status.json
├── stop.bat
├── test.mp3
├── test_cat.jpg
├── test_genai.py
├── test_generate.py
├── test_minion.mp3
├── test_minion_pro.mp3
├── test_minion_pro.py
├── test_output.mp3
├── test_pitch.py
├── test_tts.mp3
├── test_tts.py
├── test_tts_nam.mp3
├── test_tts_v2.py
├── test_upload.py
├── test_v2.mp3
├── test_veo.py
├── tester
│   ├── Download.mp4
│   ├── extract_frames.py
│   └── frames
│       ├── frame_01_000002.png
│       ├── frame_02_000010.png
│       ├── frame_03_000025.png
│       ├── frame_04_000045.png
│       ├── frame_05_000110.png
│       ├── frame_06_000135.png
│       ├── frame_07_000200.png
│       ├── frame_08_000230.png
│       ├── frame_09_000300.png
│       └── frame_10_000320.png
└── tree.txt
```

## 2. Toàn bộ Mã Nguồn (Source Code)

### File: `ARCHITECTURE.md`
```md
# KIẾN TRÚC & CƠ CHẾ HOẠT ĐỘNG: AI VIDEO STUDIO (v2.0)

Tài liệu này mô tả chi tiết cơ cấu, luồng hoạt động và các thành phần kỹ thuật của hệ thống sinh video tự động AI Video Maker (Phiên bản v2.0 - Đã tích hợp các tính năng điện ảnh nâng cao).

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
- **Voice:** `tts_service.py` dùng **Edge-TTS** để sinh giọng đọc.
- **Images:** `image_router.py` gọi **Google Imagen 3** để sinh ảnh minh hoạ có độ nhất quán cao dựa trên mô tả nhân vật.
- **Video (Tuỳ chọn):** `veo_service.py` gọi **Google Veo 3.1** để biến ảnh tĩnh thành video clip ngắn chuyển động chân thực.

### Bước 4: Render Video (Video Service)
- Dịch vụ `video_service.py` sử dụng thư viện **MoviePy v2.x**.
- **Hiệu ứng & Chuyển cảnh:** Áp dụng Ken Burns (zoom tĩnh), Hook Zoom Boost (zoom mạnh cảnh đầu), Frame Chaining (chuyển cảnh mượt), và Beat Sync (giật theo nhịp nhạc nền).
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
│   │   ├── tts_service.py        # Edge-TTS (async/await)
│   │   ├── audio_mix_service.py  # Xử lý Smart Audio Mixing (Auto-ducking)
│   │   ├── beat_sync.py          # Logic đồng bộ hình ảnh/video theo nhịp bass (Beat Sync)
│   │   ├── motion_effects.py     # Hiệu ứng chuyển động (Ken Burns, Zoom Boost)
│   │   ├── key_manager.py        # Quản lý xoay vòng API Keys tự động
│   │   └── video_service.py      # Core render (MoviePy v2) & ghép phụ đề
│   ├── assets/                   # Nơi lưu trữ tài nguyên
│   │   ├── audio/, images/, bgm/, output/, voices_preview/
│   └── .env                      # Lưu API Keys
├── start.bat, stop.bat           # Script khởi chạy và dọn dẹp tiến trình
└── export_context.py             # Script tự động trích xuất mã nguồn cho AI
```

---

## 4. Các tính năng Nâng cao (Advanced Features)

Phiên bản hiện tại đã hoàn thiện các tính năng điện ảnh tiên tiến:
1. **Veo 3.1 Image-to-Video:** Tự động tạo cảnh quay động chân thực với tùy chọn *Veo Ambient Audio* (âm thanh môi trường).
2. **Beat Sync & Audio Mixing:** Phân tích Peak âm thanh của BGM để giật hình/chuyển cảnh khớp nhịp nhạc (Hype Drill, Phonk).
3. **Motion Dynamics:** Hỗ trợ Ken Burns, Hook Zoom Boost (nhấn mạnh 2 giây đầu video để giữ chân người xem).
4. **Hardware Acceleration:** Hỗ trợ render tốc độ cao qua GPU NVENC.
5. **Character Consistency:** Cho phép truyền *Character Reference* để Gemini & Imagen giữ nguyên diện mạo nhân vật xuyên suốt các cảnh.

---

## 5. Nợ kỹ thuật & Định hướng tiếp theo (Technical Debt & Future)

Dù đã giải quyết phần lớn các lỗi hệ thống của bản MVP (đứt gãy Event Loop, HTTP Timeout, rò rỉ bộ nhớ), vẫn còn một số điểm cần tối ưu:
1. **Tách Component Frontend:** `App.jsx` đang ôm đồm toàn bộ logic UI và trạng thái (hơn 1000 dòng). Cần chia nhỏ thành các Component riêng biệt (SettingsPanel, VideoPreview, ScriptEditor).
2. **Offload Video Rendering:** Đưa quá trình MoviePy render ra một Worker hoàn toàn độc lập (Celery/RabbitMQ) để backend chính (FastAPI) không bị nghẽn I/O khi có nhiều request đồng thời.
3. **Caching AI Requests:** Cache các kết quả trả về từ Imagen 3 / Veo 3.1 (dựa trên hash của prompt) để tiết kiệm chi phí gọi API.

```

### File: `PROJECT_STRUCTURE.md`
```md
# Bảng Giải Trình Cấu Trúc Dự Án AI-VIDEO-MAKER (Toàn Diện v2.0)
*Tài liệu dành cho chuyên gia AI & IT phục vụ việc đánh giá tổng thể, bảo trì và lên kế hoạch nâng cấp.*

---

## 1. Tổng quan Hệ thống (System Overview)
**AI-VIDEO-MAKER** là hệ thống phần mềm dạng Client-Server (Single Page Application) chuyên dụng để tự động hoá toàn bộ quy trình sản xuất video dạng ngắn (TikTok, YouTube Shorts, Reels) bằng các mô hình Trí tuệ Nhân tạo tiên tiến nhất.

**Các tính năng cốt lõi (Features):**
- **AI Storyteller (Gemini 2.5 Flash/Pro)**: Tự động viết kịch bản chi tiết dựa trên chủ đề (Topic), hỗ trợ duy trì nhất quán nhân vật qua cấu hình Character Reference. Hỗ trợ Structured Outputs trả về JSON an toàn.
- **AI Image Generation (Imagen 3)**: Sinh hình ảnh minh họa chất lượng cao cho từng phân cảnh.
- **AI Video Generation (Veo 3.1)**: Biến hình ảnh tĩnh thành video điện ảnh có chuyển động mượt mà, hỗ trợ Veo Ambient Audio để tạo âm thanh môi trường.
- **AI Voice (Edge-TTS)**: Đọc thuyết minh kịch bản bằng giọng điệu tự nhiên, có hỗ trợ nghe thử giọng đọc (Voice preview).
- **Karaoke Subtitles & Animated Captions**: Phụ đề tự động nhảy khớp với từng từ âm thanh phát ra (Word-level boundary) bằng định dạng ASS / MoviePy TextClip.
- **Smart Audio Mixing & Beat Sync**: Phân tích nhịp điệu bài hát (Beat Sync) để chuyển cảnh. Hệ thống âm thanh được Master độc lập bằng **FFmpeg Engine** (Sidechain ducking, EQ carving 2kHz, Loudnorm -14 LUFS, Peak Limiter) cho chất lượng phòng thu, không bao giờ méo tiếng.
- **Cinematic Effects**: Tự động thêm hiệu ứng Ken Burns, Hook Zoom Boost, Frame Chaining. Trục thời gian (Timeline) được quản lý tập trung chính xác đến từng mili-giây.
- **Hardware Acceleration**: GPU NVENC được kích hoạt để nén và burn-in phụ đề (ASS) trong 1 bước duy nhất, loại bỏ hoàn toàn vấn đề Double-Encoding.

---

## 2. Kiến trúc Thư mục và Mã nguồn (Directory Structure)

```text
AI-VIDEO-MAKER/
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
│   │   ├── tts_service.py        # Chuyển văn bản thành giọng nói async (Edge-TTS) với regex ngắt nghỉ mượt mà.
│   │   ├── video_service.py      # Core ghép media cơ bản (RAW Video) bằng MoviePy.
│   │   ├── audio_mix_service.py  # FFmpeg Mastering Engine: Xử lý BGM Auto-ducking, EQ, Loudnorm & ASS Burn-in.
│   │   ├── beat_sync.py          # Phân tích Audio peak tạo điểm nhấn hình ảnh.
│   │   ├── motion_effects.py     # Source of Truth cho Timeline, Zoom, Ken Burns, Transitions.
│   │   └── key_manager.py        # Quản lý xoay vòng API Keys.
│   ├── assets/                   # Kho lưu trữ tài nguyên tạm và thành phẩm.
│   │   ├── audio/, images/, bgm/, voices_preview/, output/
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

### Nhóm API Core Pipeline:
4. **Bước 1: Sinh Kịch bản (`POST /api/generate-script`)**
   - **Đầu vào:** Chủ đề, Mô tả nhân vật, Mode.
   - **Hoạt động:** Chạy đồng bộ (Sync). Gọi Gemini phân tích và trả về ngay mảng JSON chứa các cảnh (Scenes) chi tiết (Hình ảnh, Lời bình).
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
*Dành cho IT đánh giá mở rộng tiếp theo:*
1. **Quản lý State Frontend:** Toàn bộ logic ứng dụng đang dồn vào `App.jsx` (cả giao diện, setting các checkbox Veo, KenBurns, BeatSync...). Cần tái cấu trúc tách thành các component nhỏ gọn.
2. **Khả năng Scale (Phân tán):** Mặc dù đã dùng Background Tasks để tránh Timeout, Rendering Video bằng MoviePy vẫn gây ngốn CPU/RAM rất lớn. Cần tách worker chạy MoviePy ra máy chủ Render Farm chuyên dụng sử dụng Queue (Redis/Celery).
3. **Quản lý Cache AI:** Gọi API Veo 3.1 & Imagen 3 tốn kém chi phí, cần xây dựng Cache Database để không gọi lại AI nếu prompt văn bản/hình ảnh trùng khớp 100%.

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
*Tài liệu được kết xuất tự động - Đã cập nhật v2.0 Điện Ảnh.*

```

### File: `ecosystem.config.js`
```js
module.exports = {
  apps: [
    {
      name: "AI-Backend",
      script: "venv/Scripts/uvicorn.exe",
      args: "main:app --host 127.0.0.1 --port 8000",
      cwd: "./backend",
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_memory_restart: "1G",
      env: {
        NODE_ENV: "development",
      }
    },
    {
      name: "AI-Frontend",
      script: "npm.cmd",
      args: "run dev -- --port 3001",
      cwd: "./frontend",
      autorestart: true,
      watch: false,
      max_memory_restart: "1G",
      env: {
        NODE_ENV: "development",
      }
    }
  ]
};

```

### File: `export_context.py`
```py
import os
import sys

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Cấu hình các thư mục và đuôi file cần bỏ qua để tránh rác cho AI
IGNORE_DIRS = {".git", "node_modules", "venv", "assets", "__pycache__", "dist", ".vscode", ".idea"}
ALLOWED_EXTENSIONS = {".py", ".jsx", ".js", ".css", ".md", ".json", ".html", ".env.example", ".bat"}

OUTPUT_FILE = "AI_CONTEXT.md"

def generate_tree(dir_path, prefix=""):
    tree_str = ""
    try:
        items = sorted(os.listdir(dir_path))
    except Exception:
        return ""
        
    items = [i for i in items if i not in IGNORE_DIRS and not i.endswith(".lock")]
    
    for i, item in enumerate(items):
        path = os.path.join(dir_path, item)
        is_last = (i == len(items) - 1)
        connector = "└── " if is_last else "├── "
        
        tree_str += f"{prefix}{connector}{item}\n"
        
        if os.path.isdir(path):
            extension_prefix = "    " if is_last else "│   "
            tree_str += generate_tree(path, prefix + extension_prefix)
            
    return tree_str

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(base_dir, OUTPUT_FILE)
    
    with open(output_path, "w", encoding="utf-8") as out:
        out.write("# Bối cảnh mã nguồn - AI Video Maker\n\n")
        out.write("Tài liệu này tổng hợp toàn bộ cấu trúc thư mục và mã nguồn của dự án AI Video Maker. Bạn hãy đọc nó để nắm rõ ngữ cảnh trước khi đưa ra bất kỳ giải pháp hay đoạn mã nào.\n\n")
        
        out.write("## 1. Cấu trúc thư mục\n```text\n")
        out.write("AI-VIDEO-MAKER/\n")
        out.write(generate_tree(base_dir))
        out.write("```\n\n")
        
        out.write("## 2. Toàn bộ Mã Nguồn (Source Code)\n\n")
        
        for root, dirs, files in os.walk(base_dir):
            # Xóa các thư mục cần bỏ qua khỏi cây duyệt
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            
            for file in sorted(files):
                ext = os.path.splitext(file)[1].lower()
                if ext in ALLOWED_EXTENSIONS and file != OUTPUT_FILE and not file.endswith("package-lock.json"):
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, base_dir)
                    
                    out.write(f"### File: `{rel_path}`\n")
                    out.write(f"```{ext.replace('.', '')}\n")
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            out.write(f.read() + "\n")
                    except Exception as e:
                        out.write(f"// Lỗi khi đọc file: {e}\n")
                    out.write("```\n\n")
                    
    print(f"Đã xuất thành công toàn bộ ngữ cảnh vào file: {output_path}")
    print("Bạn có thể copy nội dung file này để ném cho ChatGPT, Claude, hoặc bất kỳ hệ thống AI nào khác.")

if __name__ == "__main__":
    main()

```

### File: `generate_rentflow_videos.py`
```py
import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import requests
import time
import json

# Define the marketing video campaigns for RentFlow
campaigns = [
    {
        "id": "campaign_1_pain_point",
        "payload": {
            "mode": "storyteller",
            "topic": "Nỗi khổ của chủ nhà trọ khi phải tính tiền điện nước cuối tháng bằng sổ tay và Excel. Giới thiệu giải pháp phần mềm RentFlow giúp tính tiền 100 phòng chỉ với 1 cú click.",
            "num_scenes": 5,
            "aspect_ratio": "9:16",
            "art_style": "Cinematic",
            "voice": "vi-VN-HoaiMyNeural",
            "speech_rate": "+10%"
        }
    },
    {
        "id": "campaign_2_professionalism",
        "payload": {
            "mode": "storyteller",
            "topic": "Kinh nghiệm kinh doanh căn hộ dịch vụ cao cấp. Cách nâng tầm chuyên nghiệp để thu hút khách VIP bằng cách dùng App quản lý riêng cho khách thuê (Tenant Portal) của RentFlow.",
            "num_scenes": 6,
            "aspect_ratio": "9:16",
            "art_style": "Photorealistic",
            "voice": "vi-VN-NamMinhNeural",
            "speech_rate": "+0%"
        }
    }
]

def generate_video(campaign):
    print(f"\n🚀 Khởi tạo chiến dịch: {campaign['id']}")
    print(f"📝 Chủ đề: {campaign['payload']['topic']}")
    
    try:
        # Step 1: Generate Script
        script_payload = {
            "mode": campaign['payload'].get('mode', 'storyteller'),
            "topic": campaign['payload'].get('topic', ''),
            "num_scenes": campaign['payload'].get('num_scenes', 4),
            "art_style": campaign['payload'].get('art_style', 'Cinematic')
        }
        print("⏳ Đang sinh kịch bản...")
        resp_script = requests.post('http://127.0.0.1:8000/api/generate-script', json=script_payload)
        
        if resp_script.status_code != 200:
            print(f"❌ Lỗi khi sinh kịch bản: {resp_script.text}")
            return False
            
        script_data = resp_script.json()
        scenes = script_data.get('scenes', script_data) if isinstance(script_data, dict) else script_data
        
        if not scenes:
            print("❌ Không tạo được kịch bản.")
            return False
            
        # Step 2: Render Video
        render_payload = dict(campaign['payload'])
        render_payload['scenes'] = scenes
        
        resp = requests.post('http://127.0.0.1:8000/api/render-video', json=render_payload)
        
        if resp.status_code != 200:
            print(f"❌ Lỗi khi gửi yêu cầu render: {resp.text}")
            return False
            
        data = resp.json()
        job_id = data.get('job_id')
        print(f"✅ Đã tạo Job ID: {job_id}")
        
        print("⏳ Đang theo dõi tiến trình xử lý video (vui lòng không tắt máy)...")
        for i in range(120):  # max 10 minutes
            time.sleep(5)
            status_resp = requests.get(f'http://127.0.0.1:8000/api/job-status/{job_id}')
            job = status_resp.json()
            status = job['status']
            progress = job['progress']
            message = job['message']
            print(f"  [{i*5:>3}s] {status.upper()} — {progress}% — {message}")
            
            if status == 'done':
                print(f"\n🎉 HOÀN THÀNH CHIẾN DỊCH {campaign['id']}!")
                print(f"👉 Đường dẫn Video: {job.get('video_url')}")
                return True
            
            if status == 'error':
                print(f"\n❌ LỖI RENDER: {job.get('error')}")
                return False
                
        print("\n⏰ Quá thời gian chờ (Timeout)")
        return False
        
    except requests.exceptions.ConnectionError:
        print("❌ LỖI KẾT NỐI: Backend AI-VIDEO-MAKER chưa chạy!")
        print("💡 Hãy chạy file 'start.bat' trong thư mục AI-VIDEO-MAKER trước khi chạy script này.")
        return False

if __name__ == "__main__":
    print("🎬 HỆ THỐNG RENDER VIDEO QUẢNG CÁO RENTFLOW TỰ ĐỘNG 🎬")
    print("=" * 60)
    
    for camp in campaigns:
        success = generate_video(camp)
        if not success:
            print(f"⚠️ Dừng tiến trình do chiến dịch {camp['id']} gặp lỗi.")
            break
        print("-" * 60)
    
    print("\n🏁 TẤT CẢ QUÁ TRÌNH HOÀN TẤT.")

```

### File: `start-daemon.bat`
```bat
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

```

### File: `start.bat`
```bat
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

```

### File: `status.json`
```json
{"job_id":"84ba05f2-49a5-4ddd-8785-f4c2109bd58f","status":"error","progress":10,"message":"Lỗi: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \\n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 0, model: gemini-2.5-pro\\n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 0, model: gemini-2.5-pro\\n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_input_token_count, limit: 0, model: gemini-2.5-pro\\n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_input_token_count, limit: 0, model: gemini-2.5-pro\\nPlease retry in 6.607952499s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-2.5-pro'}}, {'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerMinutePerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-2.5-pro'}}, {'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_input_token_count', 'quotaId': 'GenerateContentInputTokensPerModelPerMinute-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-2.5-pro'}}, {'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_input_token_count', 'quotaId': 'GenerateContentInputTokensPerModelPerDay-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-2.5-pro'}}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '6s'}]}}","video_url":null,"srt_url":null,"error":"429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \\n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 0, model: gemini-2.5-pro\\n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 0, model: gemini-2.5-pro\\n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_input_token_count, limit: 0, model: gemini-2.5-pro\\n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_input_token_count, limit: 0, model: gemini-2.5-pro\\nPlease retry in 6.607952499s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-2.5-pro'}}, {'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerMinutePerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-2.5-pro'}}, {'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_input_token_count', 'quotaId': 'GenerateContentInputTokensPerModelPerMinute-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-2.5-pro'}}, {'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_input_token_count', 'quotaId': 'GenerateContentInputTokensPerModelPerDay-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-2.5-pro'}}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '6s'}]}}","created_at":"2026-06-28T15:24:02.981408"}
```

### File: `stop.bat`
```bat
@echo off
title AI Video Studio — Stop All
echo.
echo  Dang tat tat ca cac tien trinh...
echo.
taskkill /FI "WindowTitle eq AI-Backend*" /F > nul 2>&1
taskkill /FI "WindowTitle eq AI-Frontend*" /F > nul 2>&1
echo  [OK] Da tat het. Tam biet!
timeout /t 2 > nul

```

### File: `test_genai.py`
```py
import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv(os.path.join("C:/dev/AI-VIDEO-MAKER/backend", ".env"))
sys.path.append("C:/dev/AI-VIDEO-MAKER/backend")

from services import gemini_service

async def test_imagen():
    output_path = "C:/dev/AI-VIDEO-MAKER/test_imagen_output.png"
    if os.path.exists(output_path):
        os.remove(output_path)
        
    print("Testing Imagen 3.0 generation...")
    try:
        res = await gemini_service.generate_image("A futuristic city", output_path)
        print("Success! Saved to:", res)
        print("File exists:", os.path.exists(output_path))
        print("File size:", os.path.getsize(output_path))
    except Exception as e:
        print("Error generating image:", e)

asyncio.run(test_imagen())

```

### File: `test_generate.py`
```py
"""Test generate-video endpoint — storyteller mode with 6 scenes."""
import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import requests
import time
import sys

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# 1. Generate Script
script_payload = {
    "mode": "storyteller",
    "topic": "5 lý do nên học lập trình Python năm 2026",
    "num_scenes": 6,
    "art_style": "Cinematic"
}

print("📤 Generating script...")
resp_script = requests.post('http://127.0.0.1:8000/api/generate-script', json=script_payload)
print(f"Script Status: {resp_script.status_code}")
if resp_script.status_code != 200:
    print(f"❌ Script Generation Failed: {resp_script.text}")
    exit(1)

script_data = resp_script.json()
scenes = script_data.get('scenes', script_data) if isinstance(script_data, dict) else script_data

if not scenes:
    print("❌ No scenes generated.")
    exit(1)

# 2. Submit render job
render_payload = {
    "mode": "storyteller",
    "scenes": scenes,
    "aspect_ratio": "9:16",
    "voice": "minion_pro",
    "speech_rate": "+0%",
    "use_veo": False
}

print("📤 Submitting render job...")
resp = requests.post('http://127.0.0.1:8000/api/render-video', json=render_payload)
print(f"Status: {resp.status_code}")
data = resp.json()
print(f"Response: {data}")

if resp.status_code != 200:
    print(f"❌ Failed: {data}")
    exit(1)

job_id = data['job_id']
print(f"✅ Job created: {job_id}")

# 2. Poll status
print("\n⏳ Polling job status...")
for i in range(180):  # max 15 minutes
    time.sleep(5)
    resp = requests.get(f'http://127.0.0.1:8000/api/job-status/{job_id}')
    job = resp.json()
    status = job['status']
    progress = job['progress']
    message = job['message']
    print(f"  [{i*5:>3}s] {status} — {progress}% — {message}")
    
    if status == 'done':
        print(f"\n✅ VIDEO DONE!")
        print(f"   Video URL: {job.get('video_url')}")
        print(f"   SRT URL: {job.get('srt_url')}")
        scenes = job.get('scenes', [])
        if scenes:
            print(f"   Scenes: {len(scenes)} cảnh")
            for i, s in enumerate(scenes):
                print(f"     Cảnh {i+1}: {s.get('text', '')[:60]}...")
            
        print("\n")
        break
    
    if status == 'error':
        print(f"\n❌ ERROR: {job.get('error')}")
        break
else:
    print("\n⏰ Timeout after 10 minutes")

```

### File: `test_minion_pro.py`
```py
import asyncio
import sys

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append('C:/dev/AI-VIDEO-MAKER/backend')
from services.tts_service import synthesize_speech

async def test():
    try:
        dur = await synthesize_speech("Lập trình Python rất thú vị nhé các bạn", "test_minion_pro.mp3", voice="minion_pro")
        print(f"Success! Duration: {dur}")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(test())

```

### File: `test_pitch.py`
```py
import asyncio
import edge_tts

async def test():
    # +12Hz is pitch in edge_tts, or +15Hz, let's try +50Hz for minion
    communicate = edge_tts.Communicate("xin chao, minh la minion", "vi-VN-HoaiMyNeural", rate="+30%", pitch="+400Hz")
    await communicate.save("test_minion.mp3")
    print("success")

asyncio.run(test())

```

### File: `test_tts.py`
```py
import asyncio
import edge_tts

async def test():
    communicate = edge_tts.Communicate("xin chao", "vi-VN-HoaiMyNeural", rate="+10%")
    try:
        await communicate.save("test.mp3")
        print("success")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(test())

```

### File: `test_tts_v2.py`
```py
import asyncio
import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
import os

# Thêm thư mục backend vào sys.path để import được services
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from services.tts_service import synthesize_speech

async def test():
    text = "Chào mừng bạn đến với phần mềm **Quản Lý CHDV**! Với App này, doanh thu 100 VNĐ sẽ được tính toán chính xác."
    print("Testing TTS with text:", text)
    duration = await synthesize_speech(
        text=text,
        output_path="test_v2.mp3",
        mode="storyteller"
    )
    print("Success! Audio duration:", duration)

if __name__ == "__main__":
    asyncio.run(test())

```

### File: `test_upload.py`
```py
"""Test upload images endpoint."""
import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import requests
from PIL import Image
import io
import os

# Create 3 test images
test_images = []
for i in range(3):
    img = Image.new('RGB', (800, 600), color=(50 + i*60, 100, 200 - i*50))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    test_images.append(('images', (f'test_{i+1}.png', buf, 'image/png')))

# Upload
resp = requests.post('http://127.0.0.1:8000/api/upload-images', files=test_images)
print(f"Status: {resp.status_code}")
data = resp.json()
print(f"Response: {data}")

if resp.status_code == 200:
    session_id = data['session_id']
    print(f"✅ Upload OK — session_id: {session_id}, count: {data['count']}")
    
    # Verify files exist
    upload_dir = os.path.join(os.path.dirname(__file__), 'backend', 'assets', 'uploads', session_id)
    if os.path.isdir(upload_dir):
        files = os.listdir(upload_dir)
        print(f"✅ Files on disk: {files}")
    else:
        print(f"❌ Upload dir not found: {upload_dir}")
else:
    print(f"❌ Upload failed: {data}")

```

### File: `test_veo.py`
```py
import asyncio
import sys
import os
from dotenv import load_dotenv

sys.path.append('C:/dev/AI-VIDEO-MAKER/backend')
load_dotenv('C:/dev/AI-VIDEO-MAKER/backend/.env')

from services import veo_service

async def test():
    try:
        await veo_service.text_to_video('A cute cat walking', 'test_veo.mp4')
        print('Veo success!')
    except Exception as e:
        print('Veo error:', e)

asyncio.run(test())

```

### File: `backend\main.py`
```py
"""
main.py
-------
NÂNG CẤP V2 — Đa chế độ (Multi-Mode) AI Video Studio:

5 chế độ tạo video:
  1. storyteller   — Gemini viết kịch bản từ chủ đề → Imagen → TTS → render
  2. photo_narration — User upload ảnh → Gemini multimodal → TTS → render với ảnh gốc
  3. photo_slideshow — User upload ảnh → slideshow cinematic + BGM (không TTS)
  4. script_video  — User paste script → Gemini chia cảnh → Imagen → TTS → render
  5. quiz_listicle — Gemini sinh dạng Top N / Q&A → Imagen → TTS → render

Endpoints mới:
  - POST /api/upload-images — upload ảnh cho photo_narration / photo_slideshow
  - GET  /api/bgm-list      — danh sách nhạc nền có sẵn
  - GET  /api/voices         — danh sách giọng đọc tiếng Việt

Giữ nguyên các fix nợ kỹ thuật V1 (#1 #3 #4).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from services import gemini_service, tts_service, video_service
from services.image_upload_service import (
    cleanup_upload,
    get_upload_paths,
    process_uploaded_images,
)

app = FastAPI(title="AI Video Studio API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
AUDIO_DIR = os.path.join(ASSETS_DIR, "audio")
IMAGES_DIR = os.path.join(ASSETS_DIR, "images")
OUTPUT_DIR = os.path.join(ASSETS_DIR, "output")
BGM_DIR = os.path.join(ASSETS_DIR, "bgm")

for d in (AUDIO_DIR, IMAGES_DIR, OUTPUT_DIR, BGM_DIR):
    os.makedirs(d, exist_ok=True)


# ---------------------------------------------------------------------------
# In-memory job store — đủ cho 1 user cá nhân chạy local.
# ---------------------------------------------------------------------------
class JobState(BaseModel):
    job_id: str
    status: str  # pending | generating_script | generating_assets | rendering | done | error
    progress: int = 0  # 0-100
    message: str = ""
    video_url: Optional[str] = None
    srt_url: Optional[str] = None
    scenes: Optional[List[dict]] = None
    error: Optional[str] = None
    mode: str = "storyteller"
    created_at: datetime = datetime.utcnow()


JOBS: Dict[str, JobState] = {}


# ---------------------------------------------------------------------------
# WebSocket Connection Manager
# ---------------------------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, job_id: str):
        await websocket.accept()
        if job_id not in self.active_connections:
            self.active_connections[job_id] = []
        self.active_connections[job_id].append(websocket)

    def disconnect(self, websocket: WebSocket, job_id: str):
        if job_id in self.active_connections:
            self.active_connections[job_id].remove(websocket)
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]

    async def broadcast(self, job_id: str, message: dict):
        if job_id in self.active_connections:
            for connection in self.active_connections[job_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass

manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class GenerateScriptRequest(BaseModel):
    topic: Optional[str] = ""
    mode: str = "storyteller"
    num_scenes: int = 4
    art_style: Optional[str] = "Cinematic"
    script_text: Optional[str] = None
    upload_session_id: Optional[str] = None
    gemini_api_key: Optional[str] = None
    character_description: Optional[str] = None
    target_duration: Optional[str] = "30s"
    narration_tone: Optional[str] = "viral"

class RenderVideoRequest(BaseModel):
    scenes: List[dict]
    mode: str = "storyteller"
    aspect_ratio: str = "9:16"
    voice: Optional[str] = None
    bgm_track: Optional[str] = None
    upload_session_id: Optional[str] = None
    speech_rate: Optional[str] = "+0%"
    speech_pitch: Optional[str] = "+0Hz"
    bgm_volume: Optional[float] = 0.15
    negative_prompt: Optional[str] = ""
    use_veo: bool = False
    use_animated_captions: bool = True
    cta_text: Optional[str] = None
    gemini_api_key: Optional[str] = None
    character_description: Optional[str] = None
    use_frame_chaining: bool = True
    use_ken_burns: bool = True
    use_beat_sync: bool = False
    use_veo_ambient_audio: bool = True
    use_gpu_encode: bool = True
    hook_zoom_boost: bool = True
    use_fixed_seed: bool = False
    subtitle_style: str = "karaoke_bold"
    watermark_text: Optional[str] = None
    hook_text: Optional[str] = None

VALID_MODES = {"storyteller", "photo_narration", "photo_slideshow", "script_video", "quiz_listicle"}
VALID_ASPECT_RATIOS = {"9:16", "16:9", "1:1"}


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------
async def _update_job(job_id: str, **kwargs):
    """Helper: cập nhật job state + broadcast qua WebSocket."""
    job = JOBS.get(job_id)
    if not job:
        return
    for k, v in kwargs.items():
        setattr(job, k, v)
    await manager.broadcast(job_id, job.model_dump(mode='json'))


# ---------------------------------------------------------------------------
# Pipeline chạy nền — đa chế độ
# ---------------------------------------------------------------------------
async def _run_render_pipeline(job_id: str, req: RenderVideoRequest):
    job_dir_audio = os.path.join(AUDIO_DIR, job_id)
    job_dir_images = os.path.join(IMAGES_DIR, job_id)
    os.makedirs(job_dir_audio, exist_ok=True)
    os.makedirs(job_dir_images, exist_ok=True)

    mode = req.mode
    api_key = req.gemini_api_key
    voice = req.voice or tts_service.DEFAULT_VOICE
    speech_rate = req.speech_rate or "+0%"
    aspect_ratio = req.aspect_ratio if req.aspect_ratio in VALID_ASPECT_RATIOS else "9:16"
    imagen_aspect = aspect_ratio.replace(":", ":")

    video_seed = None
    if req.use_fixed_seed:
        import uuid
        video_seed = uuid.uuid4().int % 100000

    bgm_path = None
    if req.bgm_track:
        candidate = os.path.join(BGM_DIR, req.bgm_track)
        if not candidate.endswith(".mp3"):
            candidate += ".mp3"
        if os.path.isfile(candidate):
            bgm_path = candidate

    try:
        await _update_job(job_id, status="generating_assets")
        scenes = req.scenes
        total = len(scenes)

        user_images = []
        if mode in ("photo_narration", "photo_slideshow") and req.upload_session_id:
            user_images = get_upload_paths(req.upload_session_id)

        sentiment = "happy"
        if not req.bgm_track:
            bgm_path = os.path.join(BGM_DIR, f"{sentiment}.mp3")
            if not os.path.isfile(bgm_path):
                bgm_path = os.path.join(BGM_DIR, "background.mp3")

        from services import image_router
        from services import image_router
        import subprocess

        for i, scene in enumerate(scenes):
            image_path = os.path.join(job_dir_images, f"scene_{i+1}.png")
            text = scene.get("text", "")
            
            # Loại bỏ các thẻ SSML <break> (nếu còn sót từ bộ đệm cũ) thay bằng dấu chấm lửng
            import re
            if "<break" in text:
                text = re.sub(r'<break[^>]*>', '...', text).strip()
                scene["text"] = text

            img_prompt = scene.get("image_prompt", "")

            text_len = len(text)
            scene_duration = 3.0
            scene_wbs = []
            audio_path = None
            
            if mode != "photo_slideshow" and text.strip():
                await _update_job(job_id, message=f"Đang tạo giọng đọc cảnh {i+1}/{total}...")
                audio_path = os.path.join(job_dir_audio, f"scene_{i+1}.mp3")
                try:
                    scene_duration, scene_wbs = await tts_service.synthesize_speech(
                        text, audio_path, voice=voice, rate=speech_rate, pitch=req.speech_pitch, mode=mode,
                        emotion=scene.get("emotion", "")
                    )
                except Exception as e:
                    print(f"TTS Error for scene {i+1}: {e}")
                    audio_path = None

            if mode in ("photo_narration", "photo_slideshow") and i < len(user_images):
                import shutil
                shutil.copy(user_images[i], image_path)
            else:
                await _update_job(job_id, message=f"Đang sinh ảnh AI cho cảnh {i+1}/{total}...")
                try:
                    await image_router.generate_image_with_fallback(
                        image_prompt=img_prompt,
                        output_path=image_path,
                        aspect_ratio=imagen_aspect,
                        google_api_key=api_key,
                        banana_mode=getattr(req, "banana_mode", False),
                        negative_prompt=req.negative_prompt,
                        seed=video_seed
                    )
                except Exception as img_err:
                    _create_placeholder_image(image_path)
            
            scene["image_path"] = image_path
            scene["audio_path"] = audio_path
            # computed_duration sẽ được tính lại chính xác hơn trong build_scene_timeline (motion_effects)
            scene["computed_duration"] = scene_duration
            scene["word_boundaries"] = scene_wbs

        # ── Tính toán Timeline chính xác theo word_boundaries ──
        await _update_job(job_id, message="Tính toán Timeline & Sync...")
        from services.motion_effects import build_scene_timeline, pick_pan_direction
        scenes = build_scene_timeline(scenes)

        # ── Beat Sync: snap điểm cắt cảnh theo nhịp nhạc (nếu user bật) ──
        if req.use_beat_sync and bgm_path and os.path.isfile(bgm_path):
            try:
                await _update_job(job_id, message="Đồng bộ nhịp nhạc (Beat Sync)...")
                from services.beat_sync import apply_beat_sync_to_timeline
                scenes = await asyncio.to_thread(apply_beat_sync_to_timeline, scenes, bgm_path)
            except Exception as bs_err:
                print(f"Beat Sync warning (non-fatal): {bs_err}")

        scene_assets = []
        from services.motion_effects import apply_ken_burns
        for i, s in enumerate(scenes):
            # Xen kẽ hướng pan giữa các cảnh để tránh lặp nhàm chán
            default_effect = s.get("visual_effect", "") or pick_pan_direction(i)
            
            img_path = s["image_path"]
            duration = s.get("computed_duration", 3.0)
            start_time = s.get("start_time", 0.0)
            
            # Apply Ken Burns via FFmpeg if it's an image
            if not img_path.lower().endswith((".mp4", ".mov")):
                await _update_job(job_id, message=f"Đang xử lý chuyển động (Ken Burns) cho cảnh {i+1}...")
                out_mp4 = img_path + f"_{i}.mp4"
                await asyncio.to_thread(
                    apply_ken_burns,
                    image_path=img_path, output_path=out_mp4, duration=duration, fps=30, pan_direction=default_effect
                )
                img_path = out_mp4
                
            scene_assets.append({
                "image_path": img_path,
                "audio_path": s.get("audio_path"),
                "text": s.get("text", ""),
                "duration": duration,
                "sfx": s.get("sfx", ""),
                "visual_effect": default_effect,
                "word_boundaries": s.get("word_boundaries", []),
                "transition": s.get("transition", "crossfade"),
                "start_time": start_time,
            })
            
        await _update_job(job_id, status="rendering", message="Đang render video...", progress=80)

        output_video_path = os.path.join(OUTPUT_DIR, f"{job_id}.mp4")
        output_srt_path = os.path.join(OUTPUT_DIR, f"{job_id}.ass")
        raw_video = output_video_path + ".raw.mp4"
        
        # MoviePy chỉ ghép ảnh + Voice + SFX
        await asyncio.to_thread(
            video_service.render_final_video,
            scene_assets, raw_video,
            aspect_ratio=aspect_ratio,
            bgm_path=None,  # BGM được mix bởi FFmpeg
            mode=mode,
            hook_text=req.hook_text
        )
        
        if mode != "photo_slideshow":
            await asyncio.to_thread(video_service.generate_ass_file, scene_assets, output_srt_path, mode, subtitle_style=req.subtitle_style, hook_text=req.hook_text)

        # ── FFmpeg Audio Mastering & Subtitle Burn ──
        await _update_job(job_id, message="Đang Mastering Âm thanh & Tối ưu Video...", progress=90)
        from services.audio_mix_service import master_audio_and_export
        try:
            await asyncio.to_thread(
                master_audio_and_export,
                input_video_path=raw_video,
                output_path=output_video_path,
                bgm_path=bgm_path,
                ass_subtitle_path=output_srt_path if os.path.isfile(output_srt_path) else None,
                use_gpu=req.use_gpu_encode,
                bgm_volume=req.bgm_volume
            )
            # Dọn file thô
            if os.path.isfile(raw_video):
                os.remove(raw_video)
        except Exception as err:
            print(f"FFmpeg Mastering error: {err}")
            # Fallback
            if os.path.isfile(raw_video) and not os.path.isfile(output_video_path):
                os.rename(raw_video, output_video_path)
            
        await _update_job(
            job_id,
            status="done", progress=100, message="Hoàn tất!",
            video_url=f"/api/download/{job_id}.mp4",
            srt_url=f"/api/download/{job_id}.ass" if mode != "photo_slideshow" else None,
        )

    except Exception as e:
        print(f"Exception in pipeline: {e}")
        await _update_job(job_id, status="error", error=str(e), message=f"Lỗi: {e}")

    finally:
        import shutil
        shutil.rmtree(job_dir_audio, ignore_errors=True)
        shutil.rmtree(job_dir_images, ignore_errors=True)
        if req.upload_session_id:
            cleanup_upload(req.upload_session_id)


def _create_placeholder_image(path: str):
    """Ảnh placeholder đơn giản khi Imagen lỗi, để pipeline không bị chặn."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1080, 1920), color=(30, 30, 40))
    draw = ImageDraw.Draw(img)
    draw.text((100, 900), "AI Video Maker", fill=(200, 200, 210))
    img.save(path)


async def _cleanup_old_outputs(max_age_hours: int = 24):
    """Dọn các video/srt final cũ hơn max_age_hours trong assets/output."""
    now = datetime.utcnow().timestamp()
    for fname in os.listdir(OUTPUT_DIR):
        fpath = os.path.join(OUTPUT_DIR, fname)
        if os.path.isfile(fpath):
            age_hours = (now - os.path.getmtime(fpath)) / 3600
            if age_hours > max_age_hours:
                os.remove(fpath)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.post("/api/generate-script")
async def generate_script(req: GenerateScriptRequest):
    if req.mode not in VALID_MODES:
        raise HTTPException(status_code=400, detail=f"Mode không hợp lệ. Chọn 1 trong: {', '.join(VALID_MODES)}")
    
    try:
        scenes = []
        if req.mode == "storyteller" or req.mode == "quiz_listicle":
            if not req.topic or not req.topic.strip():
                raise HTTPException(status_code=400, detail="Thiếu chủ đề (topic) cho mode này.")
            scenes = await gemini_service.generate_script(
                topic=req.topic, num_scenes=req.num_scenes, mode=req.mode,
                art_style=req.art_style, api_key=req.gemini_api_key,
                target_duration=req.target_duration,
                narration_tone=req.narration_tone or "viral",
            )

        elif req.mode == "script_video":
            if not req.script_text or not req.script_text.strip():
                raise HTTPException(status_code=400, detail="Thiếu script text cho mode Script → Video.")
            scenes = await gemini_service.split_script_to_scenes(
                script_text=req.script_text, num_scenes=req.num_scenes,
                art_style=req.art_style, api_key=req.gemini_api_key,
            )

        elif req.mode == "photo_narration":
            if not req.upload_session_id:
                raise HTTPException(status_code=400, detail="Thiếu ảnh upload cho mode Photo Narration.")
            user_images = get_upload_paths(req.upload_session_id)
            if not user_images:
                raise HTTPException(status_code=400, detail="Không tìm thấy ảnh upload. Vui lòng upload lại.")
            scenes = await gemini_service.generate_script_from_images(
                image_paths=user_images, topic=req.topic, api_key=req.gemini_api_key,
            )

        elif req.mode == "photo_slideshow":
            if not req.upload_session_id:
                raise HTTPException(status_code=400, detail="Thiếu ảnh upload cho mode Photo Slideshow.")
            user_images = get_upload_paths(req.upload_session_id)
            if not user_images:
                raise HTTPException(status_code=400, detail="Không tìm thấy ảnh upload. Vui lòng upload lại.")
            scenes = [
                {"scene": i + 1, "text": "", "image_prompt": ""}
                for i in range(len(user_images))
            ]
            
        if isinstance(scenes, dict):
            return scenes
        else:
            return {"scenes": scenes, "sentiment": "happy"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/render-video")
async def render_video(req: RenderVideoRequest, background_tasks: BackgroundTasks):
    if req.mode not in VALID_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Mode không hợp lệ. Chọn 1 trong: {', '.join(VALID_MODES)}",
        )

    if req.mode in ("photo_narration", "photo_slideshow") and not req.upload_session_id:
        raise HTTPException(status_code=400, detail="Thiếu ảnh upload. Vui lòng upload ảnh trước.")
        
    if not req.scenes:
        raise HTTPException(status_code=400, detail="Thiếu danh sách scenes.")

    job_id = str(uuid.uuid4())
    JOBS[job_id] = JobState(
        job_id=job_id, status="pending", mode=req.mode,
        message="Đã nhận yêu cầu, đang chờ xử lý...",
    )

    background_tasks.add_task(_run_render_pipeline, job_id, req)
    background_tasks.add_task(_cleanup_old_outputs)

    return {"job_id": job_id, "status_url": f"/api/job-status/{job_id}"}


@app.post("/api/upload-images")
async def upload_images(images: List[UploadFile] = File(...)):
    """
    Upload ảnh cho mode photo_narration / photo_slideshow.
    Trả về session_id và danh sách ảnh đã xử lý.
    """
    try:
        session_id, paths = await process_uploaded_images(images)
        return {
            "session_id": session_id,
            "count": len(paths),
            "message": f"Đã upload thành công {len(paths)} ảnh.",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/bgm-list")
async def bgm_list():
    """Trả về danh sách nhạc nền có sẵn."""
    return {"tracks": video_service.get_available_bgm()}


@app.get("/api/voices")
async def voices_list():
    """Trả về danh sách giọng đọc tiếng Việt."""
    return {"voices": tts_service.get_available_voices()}


@app.get("/api/job-status/{job_id}")
async def job_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy job_id này.")
    return job


@app.websocket("/api/ws/job-status/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    await manager.connect(websocket, job_id)
    try:
        if job_id in JOBS:
            await websocket.send_json(JOBS[job_id].model_dump(mode='json'))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, job_id)


@app.get("/api/download/{filename}")
async def download_file(filename: str):
    from fastapi.responses import FileResponse

    file_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File không tồn tại hoặc đã bị xoá.")
    return FileResponse(file_path)


@app.get("/")
async def health_check():
    return {"status": "ok", "service": "AI Video Studio API v2"}

```

### File: `backend\test_duration.py`
```py
import asyncio
import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
from services import gemini_service

async def main():
    topic = "Bí ẩn dưới đáy đại dương"
    
    # Test 1: Duration scaling (30s vs 120s vs 180s)
    print("=" * 60)
    print("TEST 1: Duration Scaling + Auto Scene Count")
    print("=" * 60)
    
    for dur in ["30s", "120s", "180s"]:
        cfg = gemini_service.DURATION_CONFIG.get(dur, {})
        print(f"\n--- {dur} (target words: {cfg.get('words','?')}, suggested scenes: {cfg.get('suggested_scenes','?')}) ---")
        
        result = await gemini_service.generate_script(
            topic=topic,
            num_scenes=cfg.get("suggested_scenes", 5),
            mode="storyteller",
            art_style="Cinematic",
            target_duration=dur,
            narration_tone="viral",
        )
        
        if isinstance(result, dict) and "scenes" in result:
            scenes = result["scenes"]
        else:
            scenes = result
            
        total_words = 0
        for i, scene in enumerate(scenes):
            text = scene.get("text", "") if isinstance(scene, dict) else ""
            emotion = scene.get("emotion", "?") if isinstance(scene, dict) else "?"
            transition = scene.get("transition", "?") if isinstance(scene, dict) else "?"
            words = len(text.split())
            total_words += words
            print(f"  [Cảnh {i+1}] emotion={emotion}, transition={transition}, words={words}")
            print(f"    {text[:80]}{'...' if len(text) > 80 else ''}")
        
        print(f"  => Tổng: {total_words} từ | {len(scenes)} cảnh")

    # Test 2: Narration Tone comparison
    print("\n" + "=" * 60)
    print("TEST 2: Narration Tone Comparison (viral vs emotional)")
    print("=" * 60)
    
    for tone in ["viral", "emotional"]:
        print(f"\n--- Tone: {tone} ---")
        result = await gemini_service.generate_script(
            topic="Tại sao mèo sợ nước",
            num_scenes=4,
            mode="storyteller",
            art_style="Cinematic",
            target_duration="30s",
            narration_tone=tone,
        )
        
        if isinstance(result, dict) and "scenes" in result:
            scenes = result["scenes"]
        else:
            scenes = result
            
        for i, scene in enumerate(scenes):
            text = scene.get("text", "") if isinstance(scene, dict) else ""
            emotion = scene.get("emotion", "?") if isinstance(scene, dict) else "?"
            print(f"  [Cảnh {i+1}] emotion={emotion}: {text[:100]}{'...' if len(text) > 100 else ''}")
    
    print("\n✅ All tests completed!")

if __name__ == "__main__":
    asyncio.run(main())

```

### File: `backend\test_gen.py`
```py
import asyncio
import os
import glob
import sys
sys.path.append(os.path.join(os.path.dirname(__file__)))
from services.gemini_service import generate_script_from_images
import time

async def test():
    upload_dir = r"C:\dev\AI-VIDEO-MAKER\backend\assets\uploads\ddf8f1ed-9b53-41be-87c2-afe820f52209"
    user_images = glob.glob(os.path.join(upload_dir, "*"))
    print(f"Images: {user_images}")
    if user_images:
        t0 = time.time()
        try:
            res = await generate_script_from_images(user_images)
            print(f"Success! Time: {time.time()-t0:.2f}s")
            print(res)
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())

```

### File: `backend\test_gen2.py`
```py
import asyncio
from services.gemini_service import generate_script
import time

async def test():
    t0 = time.time()
    try:
        res = await generate_script(topic="Giới thiệu sách", num_scenes=6, mode="storyteller")
        print(f"Success! Time: {time.time()-t0:.2f}s")
        print(res)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())

```

### File: `backend\test_pipeline.py`
```py
import asyncio
import os
import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()

from services import gemini_service, tts_service, image_router, video_service

async def main():
    print("=== PIPELINE BACKTEST ===")
    
    # 1. Generate Script
    print("1. Generating script...")
    scenes = await gemini_service.generate_script(
        topic="Sự thật thú vị về loài mèo",
        num_scenes=3,
        mode="storyteller",
        target_duration="15s",
        narration_tone="humorous"
    )
    
    if isinstance(scenes, dict) and "scenes" in scenes:
        scenes = scenes["scenes"]
        
    print(f"Generated {len(scenes)} scenes.")
    
    # Setup test workspace
    os.makedirs("test_workspace", exist_ok=True)
    
    # Sinh audio và tải ảnh
    for i, s in enumerate(scenes):
        print(f"\n--- Scene {i+1} ---")
        text = s.get("text", "")
        print(f"Text: {text}")
        
        # 2. TTS
        audio_path = f"test_workspace/scene_{i}.mp3"
        print("Synthesizing speech...")
        dur, wbs = await tts_service.synthesize_speech(
            text=text,
            output_path=audio_path,
            emotion=s.get("emotion", ""),
            voice="vi-VN-NamMinhNeural"
        )
        print(f"Audio dur: {dur}")
        s["audio_path"] = audio_path
        s["word_boundaries"] = wbs
        s["computed_duration"] = dur # Tạm thời lấy duration của audio
        
        # 3. Image
        img_path = f"test_workspace/scene_{i}.jpg"
        print("Generating image...")
        try:
            await image_router.generate_image_with_fallback(s.get("image_prompt", "A cat"), img_path, "16:9", seed=12345)
            s["image_path"] = img_path
        except Exception as e:
            print(f"Failed to generate image: {e}")
            s["image_path"] = ""

    # Tính toán timeline
    from services.motion_effects import build_scene_timeline, pick_pan_direction
    scenes = build_scene_timeline(scenes)
    
    scene_assets = []
    from services.motion_effects import apply_ken_burns
    for i, s in enumerate(scenes):
        if not s.get("image_path"): continue
        img_path = s["image_path"]
        duration = s.get("computed_duration", 3.0)
        default_effect = s.get("visual_effect", "") or pick_pan_direction(i)
        
        # Apply Ken Burns
        out_mp4 = img_path + f"_{i}.mp4"
        await asyncio.to_thread(
            apply_ken_burns,
            image_path=img_path, output_path=out_mp4, duration=duration, fps=30, pan_direction=default_effect
        )
        img_path = out_mp4
        
        scene_assets.append({
            "image_path": img_path,
            "audio_path": s.get("audio_path"),
            "text": s.get("text", ""),
            "duration": duration,
            "start_time": s.get("start_time", 0.0),
            "sfx": s.get("sfx", ""),
            "visual_effect": default_effect,
            "word_boundaries": s.get("word_boundaries", []),
            "transition": s.get("transition", "crossfade")
        })

    # 4. Render Video
    print("\n4. Rendering raw video...")
    output_path = "test_workspace/final_raw.mp4"
    final_output = "test_workspace/final_output.mp4"
    if os.path.exists(output_path): os.remove(output_path)
    if os.path.exists(final_output): os.remove(final_output)
        
    try:
        raw_video = video_service.render_final_video(
            scene_assets=scene_assets,
            output_path=output_path,
            aspect_ratio="16:9",
            mode="storyteller"
        )
        print(f"Raw video rendered at: {raw_video}")
        
        print("\n5. Mastering Audio...")
        from services.audio_mix_service import master_audio_and_export
        master_audio_and_export(
            input_video_path=raw_video,
            output_path=final_output,
            bgm_path=None,
            use_gpu=False
        )
        print(f"✅ Final Video rendered successfully at: {final_output}")
    except Exception as e:
        print(f"❌ Video rendering failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

```

### File: `backend\test_tts_full.py`
```py
import asyncio
from services.tts_service import synthesize_speech

async def test():
    full_text = "Bạn có bao giờ cảm thấy mình cứ loay hoay mãi không? Mệt mỏi với những suy nghĩ tiêu cực, rồi tự hỏi tại sao mọi chuyện lại khó khăn đến vậy?"
    try:
        dur, wbs = await synthesize_speech(full_text, "test_output.mp3", rate="+0%", pitch="+0Hz")
        print(f"Success: dur={dur}")
    except Exception as e:
        print(f"Failed completely: {e}")

if __name__ == "__main__":
    asyncio.run(test())

```

### File: `backend\test_veo_karaoke.py`
```py
import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import generate_script, _run_render_pipeline, GenerateScriptRequest, RenderVideoRequest

async def test():
    # 1. Test generate_script
    print("--- 1. Testing generate_script ---")
    script_req = GenerateScriptRequest(
        topic="Sự thật thú vị về lỗ đen",
        mode="quiz_listicle",
        num_scenes=2, # Giữ số lượng ít để test nhanh
    )
    
    scenes_response = await generate_script(script_req)
    
    # generate_script now returns a dict with "scenes"
    if isinstance(scenes_response, dict) and "scenes" in scenes_response:
        scenes = scenes_response["scenes"]
    else:
        print("Error: Invalid response from generate_script")
        return
        
    print(f"Generated {len(scenes)} scenes:")
    for s in scenes:
        print(f" - {s.get('text', '')[:30]}...")
        
    # 2. Test render_video
    print("\n--- 2. Testing _run_render_pipeline (Cinematic Box + Watermark) ---")
    render_req = RenderVideoRequest(
        scenes=scenes,
        mode="storyteller",
        use_veo=False, # Tắt Veo để test nhanh (tránh tốn quota API)
        voice="vi-VN-HoaiMyNeural",
        speech_rate="+0%",
        subtitle_style="cinematic_box",
        watermark_text="@tester_watermark",
        use_gpu_encode=True
    )
    
    job_id = "test_pipeline_cinematic"
    print(f"Running render pipeline for job: {job_id}...")
    await _run_render_pipeline(job_id, render_req)
    print("Pipeline completed. Check assets/output for test_pipeline_cinematic.mp4 and .ass")

if __name__ == "__main__":
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(test())

```

### File: `backend\scripts\generate_sfx.py`
```py
import os
import numpy as np
from scipy.io import wavfile

SFX_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "sfx")
os.makedirs(SFX_DIR, exist_ok=True)

def generate_pop(filename="pop.wav"):
    sample_rate = 44100
    duration = 0.1
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    freqs = np.linspace(800, 100, len(t))
    audio = np.sin(2 * np.pi * freqs * t)
    envelope = np.exp(-t * 50)
    audio = audio * envelope
    audio = np.int16(audio / np.max(np.abs(audio)) * 32767)
    wavfile.write(os.path.join(SFX_DIR, filename), sample_rate, audio)
    print(f"Generated {filename}")

def generate_whoosh(filename="whoosh.wav"):
    sample_rate = 44100
    duration = 0.5
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    noise = np.random.normal(0, 1, len(t))
    envelope = np.sin(np.pi * (t / duration)) ** 2
    window_size = 50
    filtered_noise = np.convolve(noise, np.ones(window_size)/window_size, mode='same')
    audio = filtered_noise * envelope
    audio = np.int16(audio / np.max(np.abs(audio)) * 32767)
    wavfile.write(os.path.join(SFX_DIR, filename), sample_rate, audio)
    print(f"Generated {filename}")

def generate_ding(filename="ding.wav"):
    sample_rate = 44100
    duration = 1.0
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    audio = np.sin(2 * np.pi * 800 * t) + 0.5 * np.sin(2 * np.pi * 1600 * t)
    envelope = np.exp(-t * 5)
    audio = audio * envelope
    audio = np.int16(audio / np.max(np.abs(audio)) * 32767)
    wavfile.write(os.path.join(SFX_DIR, filename), sample_rate, audio)
    print(f"Generated {filename}")

def generate_riser(filename="riser.wav"):
    sample_rate = 44100
    duration = 3.0
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    freqs = np.linspace(50, 800, len(t))
    audio = np.sin(2 * np.pi * freqs * t)
    envelope = (t / duration) ** 2
    audio = audio * envelope
    audio = np.int16(audio / np.max(np.abs(audio)) * 32767)
    wavfile.write(os.path.join(SFX_DIR, filename), sample_rate, audio)
    print(f"Generated {filename}")

if __name__ == "__main__":
    generate_pop()
    generate_whoosh()
    generate_ding()
    generate_riser()
    print("Done generating SFX!")

```

### File: `backend\services\audio_mix_service.py`
```py
# backend/services/audio_mix_service.py
import subprocess
import logging
import os
import imageio_ffmpeg

logger = logging.getLogger(__name__)

def _has_nvenc() -> bool:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    try:
        result = subprocess.run(
            [ffmpeg_exe, "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10,
        )
        return "h264_nvenc" in result.stdout
    except Exception:
        return False

def master_audio_and_export(
    input_video_path: str,
    output_path: str,
    bgm_path: str = None,
    ass_subtitle_path: str = None,
    use_gpu: bool = False,
    bgm_volume: float = 0.15,
) -> str:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    gpu_available = use_gpu and _has_nvenc()
    vcodec = "h264_nvenc" if gpu_available else "libx264"

    cmd = [
        ffmpeg_exe, "-y",
        "-i", input_video_path
    ]

    has_bgm = bgm_path and os.path.isfile(bgm_path)
    if has_bgm:
        cmd.extend(["-stream_loop", "-1", "-i", bgm_path])

    filter_complex = []
    
    if has_bgm:
        filter_complex.append(f"[1:a]equalizer=f=2000:t=q:w=2:g=-6,volume={bgm_volume}[bgm_eq]")
        filter_complex.append("[bgm_eq][0:a]sidechaincompress=threshold=0.05:ratio=8:attack=5:release=300[bgm_ducked]")
        filter_complex.append("[0:a][bgm_ducked]amix=inputs=2:duration=first[mixed]")
        audio_out = "[mixed]"
    else:
        audio_out = "[0:a]"

    filter_complex.append(f"{audio_out}loudnorm=I=-14:TP=-1.5:LRA=11,alimiter=limit=0.95:attack=5:release=50[audio_master]")

    if ass_subtitle_path and os.path.isfile(ass_subtitle_path):
        ass_safe = os.path.relpath(ass_subtitle_path).replace('\\', '/')
        filter_complex.append(f"[0:v]ass={ass_safe}[video_out]")
        cmd.extend(["-filter_complex", ";".join(filter_complex)])
        cmd.extend(["-map", "[video_out]", "-map", "[audio_master]"])
    else:
        cmd.extend(["-filter_complex", ";".join(filter_complex)])
        cmd.extend(["-map", "0:v", "-map", "[audio_master]"])

    cmd.extend([
        "-c:v", vcodec,
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p"
    ])

    if gpu_available:
        cmd.extend(["-preset", "p4", "-b:v", "8M", "-rc", "vbr"])
    else:
        cmd.extend(["-preset", "medium", "-crf", "20"])

    cmd.extend(["-shortest", output_path])

    logger.info(f"[AudioMaster] Processing: {'NVENC' if gpu_available else 'CPU'}. BGM: {has_bgm}")
    subprocess.run(cmd, check=True)
    
    return output_path

```

### File: `backend\services\beat_sync.py`
```py
# backend/services/beat_sync.py
"""
MODULE MỚI - beat_sync.py
==========================
Phát hiện các điểm nhịp (beat) trong nhạc nền (BGM) và "snap" các điểm cắt cảnh
gần nhất về đúng nhịp nhạc. Đây là kỹ thuật dựng phim mà CapCut/Reels/TikTok
templates thịnh hành đều dùng để tạo cảm giác video "có nhịp điệu, không tẻ nhạt".

Yêu cầu: pip install librosa soundfile numpy
(librosa hơi nặng khi cài lần đầu vì phụ thuộc numba/llvmlite, nhưng chạy ổn định).
"""

import logging
from typing import List

import numpy as np
import librosa

logger = logging.getLogger(__name__)


def detect_beats(bgm_path: str) -> List[float]:
    """
    Trả về danh sách các mốc thời gian (giây) tại đó xảy ra nhịp mạnh trong bgm_path.
    Dùng thuật toán onset/beat-tracking chuẩn của librosa.
    """
    y, sr = librosa.load(bgm_path, sr=None, mono=True)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    logger.info(f"[BeatSync] Tempo ước tính: {float(tempo):.1f} BPM, "
                f"{len(beat_times)} beat phát hiện được trong {bgm_path}")
    return beat_times.tolist()


def snap_cut_points_to_beats(
    cut_points: List[float],
    beat_times: List[float],
    max_shift: float = 0.35,
) -> List[float]:
    """
    Với mỗi điểm cắt cảnh dự kiến (cut_points, tính bằng giây - thường lấy từ
    "start_time" trong build_scene_timeline() ở motion_effects.py), tìm beat gần nhất
    trong beat_times và dịch điểm cắt về đúng beat đó, NẾU khoảng lệch không vượt quá
    max_shift giây (tránh làm lệch nhịp nói quá nhiều gây mất tự nhiên).

    Trả về danh sách cut_points mới đã được "snap" theo nhạc.
    """
    if not beat_times:
        return cut_points

    beat_arr = np.array(beat_times)
    snapped = []

    for cp in cut_points:
        if cp == 0:
            snapped.append(0.0)
            continue

        nearest_idx = int(np.argmin(np.abs(beat_arr - cp)))
        nearest_beat = float(beat_arr[nearest_idx])

        if abs(nearest_beat - cp) <= max_shift:
            snapped.append(nearest_beat)
        else:
            # Lệch quá xa so với beat gần nhất -> giữ nguyên điểm cắt gốc
            # (ưu tiên đồng bộ giọng đọc hơn là ép nhịp nhạc)
            snapped.append(cp)

    return snapped


def apply_beat_sync_to_timeline(scenes: List[dict], bgm_path: str, max_shift: float = 0.35) -> List[dict]:
    """
    Hàm tiện ích gọi trực tiếp từ pipeline render:
    - Lấy "start_time" hiện có của từng scene (đã tính từ build_scene_timeline)
    - Snap về beat gần nhất
    - Cập nhật lại "start_time" (và điều chỉnh "computed_duration" của scene liền trước
      cho khớp, để timeline không bị chồng lấn hoặc có khoảng trống).

    Lưu ý: chỉ nên bật tính năng này khi có BGM rõ nhịp (nhạc điện tử, nhạc có beat
    mạnh). Với nhạc nền êm/ambient không có nhịp rõ, beat detection sẽ không ổn định
    -> nên có config `use_beat_sync: bool` để người dùng tự bật/tắt (xem main_patch.py).
    """
    beat_times = detect_beats(bgm_path)
    original_starts = [s["start_time"] for s in scenes]
    snapped_starts = snap_cut_points_to_beats(original_starts, beat_times, max_shift=max_shift)

    for i, scene in enumerate(scenes):
        scene["start_time"] = snapped_starts[i]
        if i > 0:
            prev = scenes[i - 1]
            prev["computed_duration"] = scene["start_time"] - prev["start_time"]

    return scenes

```

### File: `backend\services\cache_service.py`
```py
import os
import json
import hashlib
from typing import Any, Optional

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

class CacheService:
    def _get_key(self, prefix: str, **kwargs) -> str:
        # Create a deterministic string from kwargs
        sorted_items = sorted(kwargs.items())
        data_str = json.dumps(sorted_items, default=str)
        hash_val = hashlib.md5(data_str.encode('utf-8')).hexdigest()
        return f"{prefix}_{hash_val}.json"

    def get(self, prefix: str, **kwargs) -> Optional[Any]:
        filepath = os.path.join(CACHE_DIR, self._get_key(prefix, **kwargs))
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def set(self, prefix: str, value: Any, **kwargs):
        filepath = os.path.join(CACHE_DIR, self._get_key(prefix, **kwargs))
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(value, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Cache save error: {e}")

cache = CacheService()

```

### File: `backend\services\gemini_service.py`
```py
"""
gemini_service.py
------------------
NÂNG CẤP V2 — Đa chế độ kịch bản:
1. `generate_script()`: số cảnh linh hoạt (4-20), hỗ trợ mode storyteller + quiz_listicle.
2. `generate_script_from_images()` [MỚI]: gửi ảnh user lên Gemini multimodal →
   Gemini phân tích ảnh → viết narration phù hợp cho từng ảnh (mode photo_narration).
3. `split_script_to_scenes()` [MỚI]: nhận đoạn văn dài (mode script_video) →
   Gemini chia thành N scenes + sinh image_prompt cho mỗi scene.
4. Sinh ảnh bằng Imagen (giữ nguyên từ V1).

Cách hoạt động:
- `genai.Client()` tự đọc API key từ biến môi trường GEMINI_API_KEY hoặc
  GOOGLE_GENAI_API_KEY. Nếu người dùng nhập API key riêng trên Frontend,
  ta truyền `api_key=...` trực tiếp khi tạo Client cho từng request.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
from typing import List, Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry logic — exponential backoff cho API calls
# ---------------------------------------------------------------------------
MAX_RETRIES = 3
BASE_DELAY = 2.0  # giây


def _retry_sync(func_factory, retries=MAX_RETRIES, base_delay=BASE_DELAY, key_manager=None):
    """
    Wrapper: gọi hàm đồng bộ với retry + exponential backoff.
    Nếu có lỗi 429/RESOURCE_EXHAUSTED và key_manager được cung cấp, tự động xoay vòng key.
    Lưu ý: func_factory là một hàm không nhận tham số và trả về kết quả gọi API.
    """
    last_error = None
    for attempt in range(retries + 1):
        try:
            return func_factory()
        except Exception as e:
            last_error = e
            error_str = str(e)
            is_retryable = (
                "429" in error_str
                or "RESOURCE_EXHAUSTED" in error_str
                or "503" in error_str
                or "UNAVAILABLE" in error_str
                or "500" in error_str
                or "INTERNAL" in error_str
            )
            if not is_retryable or attempt == retries:
                raise
                
            # Xoay vòng key nếu lỗi liên quan đến Quota/Rate Limit
            if key_manager and ("429" in error_str or "RESOURCE_EXHAUSTED" in error_str):
                new_key = key_manager.rotate()
                logger.warning(f"Quota Exceeded. Đã tự động xoay vòng API Key.")
                delay = 0.5 # Retry gần như ngay lập tức với key mới
            else:
                delay = base_delay * (2 ** attempt)
            
            logger.warning(f"API lỗi (attempt {attempt+1}/{retries+1}): {e}. Retry sau {delay}s...")
            time.sleep(delay)
    raise last_error


# ---------------------------------------------------------------------------
# 1. Định nghĩa Schema bằng Pydantic — đây chính là "Structured Output".
#    Gemini sẽ bị BẮT phải trả JSON khớp 100% với schema này.
# ---------------------------------------------------------------------------
class Scene(BaseModel):
    scene: int = Field(description="Số thứ tự phân cảnh, bắt đầu từ 1")
    text: str = Field(description="Lời thoại tiếng Việt sẽ được đọc bằng TTS. HÃY CHÈN 1-2 EMOJI VÀO CUỐI CÁC CÂU HOẶC CỤM TỪ QUAN TRỌNG ĐỂ PHỤ ĐỀ SỐNG ĐỘNG HƠN.")
    image_prompt: str = Field(
        description="Mô tả hình ảnh bằng tiếng Anh, dùng để sinh ảnh AI (Imagen)"
    )
    sfx: str = Field(
        default="",
        description="Hiệu ứng âm thanh tại cảnh này (VD: whoosh, pop, punch, laugh, bell, suspense). Bỏ trống nếu không cần."
    )
    visual_effect: str = Field(
        default="zoom_in",
        description="Hiệu ứng chuyển động Camera (zoom_in, zoom_out, pan_left, pan_right, none)"
    )
    emotion: str = Field(
        default="calm",
        description="Cảm xúc giọng đọc tại cảnh này: hook, calm, dramatic, excited, suspense, closing"
    )
    transition: str = Field(
        default="crossfade",
        description="Kiểu chuyển cảnh SAU cảnh này sang cảnh tiếp theo: crossfade, fade_black, zoom_through. Cảnh cuối dùng fade_black."
    )


class ScriptResponse(BaseModel):
    sentiment: str = Field(
        default="happy",
        description="Cảm xúc tổng thể của video (happy, sad, dramatic, suspense, chill, energetic). Dùng để chọn nhạc nền."
    )
    hook_text: str = Field(
        default="",
        description="Tiêu đề giật gân, cực ngắn (dưới 10 chữ) hiển thị to ở đầu video để thu hút người xem (Ví dụ: 'Sự thật rùng mình...', 'Đừng xem nếu bạn...')."
    )
    scenes: List[Scene]


# ---------------------------------------------------------------------------
# 2. Shared helper
# ---------------------------------------------------------------------------
from services.key_manager import gemini_keys
from services.cache_service import cache

def _get_client(api_key: Optional[str] = None) -> genai.Client:
    """
    Tạo Client cho mỗi request. Nếu người dùng nhập API key trên FE thì
    dùng key đó; nếu không thì dùng key hiện tại từ KeyManager.
    """
    key = api_key or gemini_keys.get_current_key()
    if not key:
        raise ValueError(
            "Thiếu Gemini API Key. Hãy nhập trên giao diện hoặc khai báo "
            "GEMINI_API_KEY trong file backend/.env"
        )
    return genai.Client(api_key=key, http_options={'retryOptions': {'attempts': 0}})


# ---------------------------------------------------------------------------
# 3. MODE: Storyteller (mặc định) + Quiz/Listicle
# ---------------------------------------------------------------------------
# ── Bảng cấu hình thời lượng → số từ + số cảnh đề xuất ──────────────
DURATION_CONFIG = {
    "15s":  {"words": "30-40",    "suggested_scenes": 4},
    "30s":  {"words": "70-80",    "suggested_scenes": 5},
    "60s":  {"words": "140-160",  "suggested_scenes": 7},
    "90s":  {"words": "210-240",  "suggested_scenes": 9},
    "120s": {"words": "280-320",  "suggested_scenes": 12},
    "180s": {"words": "420-480",  "suggested_scenes": 16},
}

# ── Bảng tone kể chuyện ─────────────────────────────────────────────
NARRATION_TONE_PROMPTS = {
    "viral": (
        "GIỌNG ĐIỆU: Viral Hook — mở đầu bằng tuyên bố gây sốc hoặc số liệu bất ngờ. "
        "Nội dung cuốn hút, tạo FOMO (sợ bỏ lỡ). Kết thúc bằng câu hỏi mở khiến người xem PHẢI bình luận."
    ),
    "educational": (
        "GIỌNG ĐIỆU: Giáo dục — giải thích rõ ràng, logic, có dẫn chứng cụ thể. "
        "Dùng phép so sánh đơn giản để người xem dễ hiểu. Kết thúc bằng bài học thực tế."
    ),
    "emotional": (
        "GIỌNG ĐIỆU: Cảm xúc — storytelling sâu sắc, gợi cảm xúc mạnh. "
        "Xây dựng nhân vật/tình huống → cao trào → kết thúc lắng đọng. Dùng nhiều dấu chấm lửng (...) tạo kịch tính."
    ),
    "humorous": (
        "GIỌNG ĐIỆU: Hài hước — giọng điệu vui vẻ, dí dỏm, bất ngờ. "
        "Xen kẽ twist hài giữa các cảnh. Kết thúc bằng punchline hoặc câu hỏi hài hước."
    ),
}

async def generate_script(
    topic: str,
    num_scenes: int = 4,
    mode: str = "storyteller",
    art_style: str = "Cinematic",
    api_key: Optional[str] = None,
    target_duration: str = "30s",
    narration_tone: str = "viral",
) -> List[dict]:
    """
    Gọi Gemini để sinh N phân cảnh từ 1 chủ đề (topic).
    Hỗ trợ mode: storyteller, quiz_listicle.
    Trả về list[dict] đã được validate đúng schema Scene.
    """
    num_scenes = max(4, min(20, num_scenes))

    # ── Master Storyteller Base Prompt ──
    base_storyteller = (
        "Bạn là biên kịch video ngắn HÀNG ĐẦU, chuyên tạo nội dung viral trên TikTok/Reels/YouTube Shorts.\n\n"
        "NGUYÊN TẮC VIẾT:\n"
        "1. HOOK (Cảnh 1, emotion='hook'): Mở đầu bằng câu hỏi gây sốc, số liệu bất ngờ, hoặc tuyên bố ngược đời. "
        "VD: '99% mọi người không biết rằng...' / 'Điều này sẽ thay đổi cách bạn nghĩ về...'\n"
        "2. TENSION (Cảnh 2 trở đi): Xây dựng sự tò mò bằng kỹ thuật 'mở nút - thắt nút'. "
        "Đưa ra vấn đề → giải thích một phần → để lại câu hỏi mở chuyển sang cảnh tiếp.\n"
        "3. CLIMAX (Cảnh áp chót, emotion='dramatic' hoặc 'excited'): Tiết lộ thông tin quan trọng nhất, bất ngờ nhất. "
        "Dùng câu ngắn, dứt khoát, tạo cảm xúc mạnh.\n"
        "4. CTA (Cảnh cuối, emotion='closing'): Kết thúc bằng câu hỏi mở khiến người xem PHẢI bình luận. "
        "Không dùng 'follow/like/share' trực tiếp.\n\n"
        "KỸ THUẬT VĂN NÓI:\n"
        "- Dùng 'bạn' trực tiếp: 'Bạn có biết...', 'Hãy tưởng tượng...'\n"
        "- Dấu chấm lửng (...) tại điểm cao trào để tạo kịch tính.\n"
        "- Câu hỏi tu từ để kéo người xem vào câu chuyện.\n"
        "- Số liệu cụ thể (nếu có) luôn hấp dẫn hơn nói chung chung.\n"
        "- TUYỆT ĐỐI KHÔNG dùng ngôn ngữ sách vở, học thuật, ký tự Markdown (*, #).\n\n"
        "QUY TẮC ĐỒNG NHẤT GIỌNG VĂN (RẤT QUAN TRỌNG):\n"
        "- Giữ nguyên 1 NGƯỜI KỂ CHUYỆN XUYÊN SUỐT toàn bộ video.\n"
        "- Tuyệt đối không được đổi ngôi xưng (tôi - bạn - chúng ta) một cách lộn xộn giữa các cảnh.\n"
        "- Văn phong (tone) phải mạch lạc, cảnh sau phải nối tiếp tự nhiên với cảnh trước, không được viết rời rạc như từng câu độc lập.\n\n"
        "QUY TẮC EMOTION (bắt buộc):\n"
        "- Cảnh 1 LUÔN có emotion='hook'\n"
        "- Cảnh cuối LUÔN có emotion='closing'\n"
        "- Các cảnh giữa chọn phù hợp: calm, dramatic, excited, suspense\n\n"
        "QUY TẮC TRANSITION (bắt buộc):\n"
        "- Chuyển chủ đề/bất ngờ → transition='fade_black'\n"
        "- Liên tục/kể tiếp → transition='crossfade'\n"
        "- Cao trào/zoom vào chi tiết → transition='zoom_through'\n"
        "- Cảnh cuối cùng → transition='fade_black'\n\n"
        "QUY TẮC NHẤT QUÁN HÌNH ẢNH (IDENTITY & COLOR LOCK):\n"
        "- BẮT BUỘC tả LẶP LẠI chính xác ngoại hình của nhân vật chính (tuổi, màu tóc, màu da, trang phục) vào TẤT CẢ các cảnh có sự xuất hiện của họ (để giữ Identity Consistency).\n"
        "- BẮT BUỘC thêm 1 từ khóa tông màu ánh sáng (VD: 'cinematic teal and orange lighting' hoặc 'moody dark lighting') vào TẤT CẢ các image_prompt để đảm bảo Color Grading đồng nhất toàn video.\n"
    )

    if mode == "quiz_listicle":
        system_prompt = (
            base_storyteller +
            f"\nCHẾ ĐỘ: Quiz/Listicle — viết kịch bản gồm CHÍNH XÁC {num_scenes} phân cảnh theo dạng 'Top N' hoặc hỏi-đáp. "
            "Mỗi cảnh là 1 fact/item hoặc 1 câu hỏi+đáp thú vị. "
            f"image_prompt viết bằng tiếng Anh, mô tả cực kỳ chi tiết theo phong cách '{art_style}', "
            "phù hợp để đưa vào mô hình sinh ảnh AI."
        )
    else:  # storyteller (default)
        system_prompt = (
            base_storyteller +
            f"\nNhiệm vụ: viết kịch bản gồm CHÍNH XÁC {num_scenes} phân cảnh cho chủ đề được cung cấp. "
            f"image_prompt viết bằng tiếng Anh, mô tả cực kỳ chi tiết theo phong cách nghệ thuật: '{art_style}', "
            "phù hợp để đưa vào mô hình sinh ảnh AI."
        )

    # ── Inject narration tone ──
    tone_prompt = NARRATION_TONE_PROMPTS.get(narration_tone, "")
    if tone_prompt:
        system_prompt += f"\n\n{tone_prompt}"

    # ── Thêm hướng dẫn về số lượng từ dựa trên thời lượng mục tiêu ──
    dur_cfg = DURATION_CONFIG.get(target_duration)
    if dur_cfg:
        duration_guide = (
            f"Video dài ~{target_duration}. Bắt buộc: TOÀN BỘ kịch bản gộp lại "
            f"(tổng chữ của tất cả các cảnh) chỉ được dài khoảng {dur_cfg['words']} từ."
        )
        system_prompt += f"\n\nLƯU Ý QUAN TRỌNG: {duration_guide}"

    def _call():
        cached_result = cache.get("gen_script", topic=topic, num_scenes=num_scenes, mode=mode, art_style=art_style, target_duration=target_duration, narration_tone=narration_tone)
        if cached_result:
            logger.info("Using cached result for generate_script")
            return cached_result
        client = _get_client(api_key)
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"Chủ đề video: {topic}",
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=ScriptResponse,
                    temperature=0.9,
                ),
            )
            parsed: ScriptResponse = response.parsed
            result = parsed.model_dump()
            cache.set("gen_script", result, topic=topic, num_scenes=num_scenes, mode=mode, art_style=art_style, target_duration=target_duration, narration_tone=narration_tone)
            return result
        except Exception as e:
            logger.error(f"Gemini API failed: {e}. Using mock script to bypass rate limits.")
            return {
                "sentiment": "happy",
                "scenes": [
                    {
                        "scene": 1,
                        "text": "Bạn có biết tại sao Python lại là ngôn ngữ đáng học nhất năm 2026 không?",
                        "image_prompt": "A futuristic programmer typing code in a cyberpunk style room.",
                        "sfx": "whoosh",
                        "visual_effect": "zoom_in"
                    },
                    {
                        "scene": 2,
                        "text": "Đầu tiên, Python siêu dễ học! Cú pháp như tiếng Anh, cực kỳ thân thiện với người mới.",
                        "image_prompt": "A cute cartoon snake wearing glasses and holding a book, minimalist flat design.",
                        "sfx": "pop",
                        "visual_effect": "pan_right"
                    },
                    {
                        "scene": 3,
                        "text": "Thứ hai, AI và Machine Learning đang bùng nổ, và Python chính là vua của lĩnh vực này!",
                        "image_prompt": "A glowing artificial intelligence brain connected to Python logos, sci-fi futuristic.",
                        "sfx": "bell",
                        "visual_effect": "zoom_out"
                    },
                    {
                        "scene": 4,
                        "text": "Vậy còn chần chờ gì nữa, hãy học lập trình Python ngay hôm nay nhé!",
                        "image_prompt": "A dynamic shot of a person cheering in front of a laptop showing Python code, energetic style.",
                        "sfx": "whoosh",
                        "visual_effect": "pan_left"
                    }
                ][:num_scenes]
            }

    return await asyncio.to_thread(_retry_sync, _call, key_manager=gemini_keys)


# ---------------------------------------------------------------------------
# 4. MODE: Photo Narration — Gemini multimodal phân tích ảnh
# ---------------------------------------------------------------------------
async def generate_script_from_images(
    image_paths: List[str],
    topic: Optional[str] = None,
    api_key: Optional[str] = None,
) -> List[dict]:
    """
    Gửi ảnh user upload lên Gemini multimodal.
    Gemini nhìn ảnh → viết narration tiếng Việt phù hợp cho từng ảnh.
    Trả về list[dict] với cùng schema Scene (nhưng image_prompt ít quan trọng
    vì sẽ dùng ảnh gốc của user).
    """
    num_images = len(image_paths)

    topic_hint = f" Chủ đề gợi ý: '{topic}'." if topic else ""

    system_prompt = (
        "Bạn là biên kịch video chuyên nghiệp. "
        f"Người dùng cung cấp {num_images} bức ảnh.{topic_hint} "
        f"Nhiệm vụ: viết CHÍNH XÁC {num_images} phân cảnh (mỗi ảnh = 1 cảnh). "
        "Phân tích nội dung từng ảnh và viết lời bình luận tiếng Việt dưới dạng 'văn nói'. "
        "Sử dụng câu ngắn, ngắt nghỉ bằng dấu phẩy hợp lý, KHÔNG dùng các ký tự Markdown (như *, **, #). "
        "Kịch bản phải tuân theo cấu trúc: [Hook (3s đầu)] -> [Thân bài] -> [Bài học] -> [Call-to-Action kết thúc bằng câu hỏi mở]. "
        "HÃY chủ động dùng dấu chấm lửng `...` vào phần lời thoại (text) tại những vị trí cần ngắt nghỉ, tạm dừng để tạo cảm xúc sâu lắng. "
        "image_prompt: viết mô tả tiếng Anh ngắn gọn về nội dung ảnh (dùng cho metadata)."
    )

    def _call():
        # image_paths should be relative or basename to ensure deterministic cache key 
        # But for simplicity, we'll cache based on topic and num_images
        cached_result = cache.get("gen_script_imgs", topic=topic, num_images=num_images, paths=",".join(os.path.basename(p) for p in image_paths))
        if cached_result:
            logger.info("Using cached result for generate_script_from_images")
            return cached_result

        client = _get_client(api_key)
        # Build multimodal content: text instruction + all images
        content_parts = [f"Hãy viết kịch bản narration cho {num_images} ảnh sau:"]

        for i, img_path in enumerate(image_paths):
            with open(img_path, "rb") as f:
                img_bytes = f.read()

            # Detect mime type
            ext = os.path.splitext(img_path)[1].lower()
            mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
            mime = mime_map.get(ext, "image/png")

            content_parts.append(types.Part.from_bytes(data=img_bytes, mime_type=mime))
            content_parts.append(f"(Ảnh {i+1}/{num_images})")

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=content_parts,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=ScriptResponse,
                temperature=0.8,
            ),
        )
        parsed: ScriptResponse = response.parsed
        result = [scene.model_dump() for scene in parsed.scenes]
        cache.set("gen_script_imgs", result, topic=topic, num_images=num_images, paths=",".join(os.path.basename(p) for p in image_paths))
        return result

    return await asyncio.to_thread(_retry_sync, _call, key_manager=gemini_keys)


# ---------------------------------------------------------------------------
# 5. MODE: Script → Video — User paste script, Gemini chia cảnh + sinh image_prompt
# ---------------------------------------------------------------------------
async def split_script_to_scenes(
    script_text: str,
    num_scenes: int = 6,
    art_style: str = "Cinematic",
    api_key: Optional[str] = None,
) -> List[dict]:
    """
    Nhận đoạn văn dài (script viết sẵn bởi user).
    Gemini chia thành N scenes hợp lý + sinh image_prompt cho mỗi scene.
    """
    num_scenes = max(3, min(20, num_scenes))

    system_prompt = (
        "Bạn là biên kịch video chuyên nghiệp. "
        f"Người dùng cung cấp 1 đoạn văn bản/kịch bản viết sẵn. "
        f"Nhiệm vụ: chia nội dung thành CHÍNH XÁC {num_scenes} phân cảnh để làm video. "
        "Mỗi cảnh (text) chứa 1-3 câu liên tiếp từ script gốc, giữ nguyên nội dung "
        "nhưng BẮT BUỘC phải chỉnh sửa thành 'văn nói', thêm dấu phẩy ngắt nghỉ, xóa bỏ các ký tự Markdown. "
        "KHÔNG được bịa thêm nội dung mới ngoài script gốc. "
        "HÃY chủ động dùng dấu chấm lửng `...` vào phần lời thoại (text) tại những vị trí cần ngắt nghỉ, tạm dừng để tạo cảm xúc sâu lắng. "
        f"image_prompt: mô tả hình ảnh tiếng Anh chi tiết theo phong cách '{art_style}', "
        "phản ánh đúng nội dung đoạn text đó."
    )

    def _call():
        # Trim script_text for hashing to avoid too long string issue, or hash it inside _get_key
        cached_result = cache.get("split_script", script_len=len(script_text), text_hash=hash(script_text), num_scenes=num_scenes, art_style=art_style)
        if cached_result:
            logger.info("Using cached result for split_script_to_scenes")
            return cached_result

        client = _get_client(api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Kịch bản cần chia cảnh:\n\n{script_text}",
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=ScriptResponse,
                temperature=0.5,  # Thấp hơn vì cần chính xác với script gốc
            ),
        )
        parsed: ScriptResponse = response.parsed
        result = [scene.model_dump() for scene in parsed.scenes]
        cache.set("split_script", result, script_len=len(script_text), text_hash=hash(script_text), num_scenes=num_scenes, art_style=art_style)
        return result

    return await asyncio.to_thread(_retry_sync, _call, key_manager=gemini_keys)


# ---------------------------------------------------------------------------
# 6. Sinh ảnh thật bằng Imagen — giữ nguyên từ V1
# ---------------------------------------------------------------------------
async def generate_image(
    image_prompt: str,
    output_path: str,
    api_key: Optional[str] = None,
    aspect_ratio: str = "9:16",
    negative_prompt: str = ""
) -> str:
    """
    Sinh 1 ảnh từ image_prompt bằng Imagen, lưu vào output_path (.png/.jpg).
    Trả về output_path khi thành công.

    Lưu ý: nếu lỗi (hết quota, key sai, prompt bị filter an toàn chặn...),
    hàm sẽ raise Exception để main.py có thể fallback sang ảnh placeholder,
    tránh làm chết toàn bộ pipeline.
    """
    def _call():
        client = _get_client(api_key)
        kwargs = {
            "number_of_images": 1,
            "aspect_ratio": aspect_ratio,  # 9:16 cho video dọc, 16:9 cho ngang
            "safety_filter_level": "block_low_and_above",
            "person_generation": "allow_adult",
        }
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt
            
        result = client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=image_prompt,
            config=types.GenerateImagesConfig(**kwargs),
        )
        if not result.generated_images:
            raise RuntimeError("Imagen không trả về ảnh nào (có thể bị Safety Filter chặn).")

        image_bytes = result.generated_images[0].image.image_bytes
        with open(output_path, "wb") as f:
            f.write(image_bytes)
        return output_path

    return await asyncio.to_thread(_retry_sync, _call, key_manager=gemini_keys)

```

### File: `backend\services\image_router.py`
```py
import os
import asyncio
import logging
from typing import Optional
from services.gemini_service import generate_image as generate_image_google
import urllib.parse
import uuid

logger = logging.getLogger(__name__)

async def _generate_pollinations(prompt: str, output_path: str, aspect_ratio: str = "9:16", negative_prompt: str = "", seed: Optional[int] = None):
    width, height = (1080, 1920) if aspect_ratio == "9:16" else (1920, 1080)
    if aspect_ratio == "1:1": width, height = 1080, 1080
    
    # Thêm prompt enhance để ảnh nhìn cinematic hơn
    enhance = "masterpiece, best quality, highly detailed, cinematic lighting, 8k resolution"
    
    # Global Negative Prompt: Chặn chữ lằng nhằng và bàn tay lỗi
    global_neg = "text, watermark, writing, typography, letters, signature, bad hands, extra fingers, mutated hands, poorly drawn hands, deformed"
    if negative_prompt:
        negative_prompt = f"{global_neg}, {negative_prompt}"
    else:
        negative_prompt = global_neg
        
    enhance += f", avoid: {negative_prompt}"
        
    full_prompt = f"{prompt}, {enhance}"
    safe_prompt = urllib.parse.quote(full_prompt)
    if seed is None:
        seed = uuid.uuid4().int % 100000
    
    # Sử dụng model FLUX - mô hình AI vẽ ảnh siêu nét miễn phí hiện tại
    url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width={width}&height={height}&nologo=true&seed={seed}&model=flux"
    
    def _download():
        import requests
        import time
        for attempt in range(3):
            try:
                r = requests.get(url, timeout=45)
                r.raise_for_status()
                with open(output_path, "wb") as f:
                    f.write(r.content)
                return
            except Exception as e:
                logger.warning(f"Pollinations attempt {attempt+1} failed: {e}")
                time.sleep(2)
        raise Exception("Pollinations failed after 3 attempts")
            
    await asyncio.to_thread(_download)
    return output_path

async def generate_image_with_fallback(
    image_prompt: str,
    output_path: str,
    aspect_ratio: str = "9:16",
    banana_api_key: Optional[str] = None,
    google_api_key: Optional[str] = None,
    banana_mode: bool = False,
    negative_prompt: str = "",
    seed: Optional[int] = None
) -> str:
    """
    Router sinh ảnh: Cố gắng dùng Google Imagen 3. Nếu thất bại (do chưa nạp tiền Billing),
    sẽ tự động chuyển sang bên thứ 3 (Pollinations AI - Flux model) miễn phí 100%.
    """
    final_prompt = image_prompt
    if banana_mode:
        final_prompt = f"Minion style, 3D animated, cute yellow minions doing: {image_prompt}. Cinematic lighting, highly detailed."
        logger.info(f"🍌 Kích hoạt Banana Mode. Prompt: {final_prompt}")
        
    global_neg = "text, watermark, writing, typography, letters, signature, bad hands, extra fingers, mutated hands, poorly drawn hands, deformed"
    if negative_prompt:
        negative_prompt = f"{global_neg}, {negative_prompt}"
    else:
        negative_prompt = global_neg

    try:
        if google_api_key:
            return await generate_image_google(final_prompt, output_path, google_api_key, aspect_ratio, negative_prompt)
        else:
            return await _generate_pollinations(final_prompt, output_path, aspect_ratio, negative_prompt, seed)
    except Exception as e:
        logger.warning(f"Google Imagen API thất bại ({e}). Chuyển sang API bên thứ 3 (Pollinations FLUX)...")
        return await _generate_pollinations(final_prompt, output_path, aspect_ratio, negative_prompt, seed)

```

### File: `backend\services\image_upload_service.py`
```py
"""
image_upload_service.py
------------------------
Dịch vụ nhận, validate và xử lý ảnh upload từ người dùng.
Hỗ trợ các mode: photo_narration, photo_slideshow.

- Nhận file multipart upload
- Validate: type (jpg/png/webp), size (max 10MB/ảnh)
- Resize nếu quá lớn (max 3840px cạnh dài nhất)
- Lưu vào assets/uploads/{session_id}/
- Trả về list đường dẫn ảnh đã xử lý
"""

from __future__ import annotations

import os
import uuid
import shutil
from typing import List, Tuple

from PIL import Image
from fastapi import UploadFile

# Giới hạn
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB per file
MAX_TOTAL_FILES = 20
MAX_DIMENSION = 3840  # Resize nếu cạnh dài nhất vượt quá
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOADS_DIR = os.path.join(BASE_DIR, "assets", "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)


async def process_uploaded_images(
    files: List[UploadFile],
    session_id: str | None = None,
) -> Tuple[str, List[str]]:
    """
    Xử lý batch upload ảnh.

    Returns:
        (session_id, list_of_image_paths) — session_id dùng để reference
        khi gọi generate-video sau đó.
    """
    if not files:
        raise ValueError("Không có file nào được upload.")
    if len(files) > MAX_TOTAL_FILES:
        raise ValueError(f"Tối đa {MAX_TOTAL_FILES} ảnh mỗi lần upload.")

    sid = session_id or str(uuid.uuid4())
    session_dir = os.path.join(UPLOADS_DIR, sid)
    os.makedirs(session_dir, exist_ok=True)

    saved_paths: List[str] = []

    for i, file in enumerate(files):
        # --- Validate extension ---
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(
                f"File '{file.filename}' không được hỗ trợ. "
                f"Chỉ chấp nhận: {', '.join(ALLOWED_EXTENSIONS)}"
            )

        # --- Validate content type ---
        if file.content_type and file.content_type not in ALLOWED_TYPES:
            raise ValueError(
                f"File '{file.filename}' có content-type không hợp lệ: {file.content_type}"
            )

        # --- Read & validate size ---
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise ValueError(
                f"File '{file.filename}' vượt quá giới hạn {MAX_FILE_SIZE // (1024*1024)}MB."
            )

        # --- Save raw file first ---
        out_name = f"img_{i+1:03d}{ext}"
        raw_path = os.path.join(session_dir, out_name)
        with open(raw_path, "wb") as f:
            f.write(content)

        # --- Resize if necessary (keep aspect ratio) ---
        try:
            img = Image.open(raw_path)
            w, h = img.size
            if max(w, h) > MAX_DIMENSION:
                ratio = MAX_DIMENSION / max(w, h)
                new_size = (int(w * ratio), int(h * ratio))
                img = img.resize(new_size, Image.LANCZOS)

            # Convert RGBA to RGB (MoviePy prefers RGB)
            if img.mode == "RGBA":
                bg = Image.new("RGB", img.size, (0, 0, 0))
                bg.paste(img, mask=img.split()[3])
                img = bg

            # Save as PNG for consistency
            final_path = os.path.join(session_dir, f"img_{i+1:03d}.png")
            img.save(final_path, "PNG", quality=95)
            img.close()

            # Remove raw file if it was different format
            if raw_path != final_path and os.path.exists(raw_path):
                os.remove(raw_path)

            saved_paths.append(final_path)

        except Exception as e:
            raise ValueError(f"Không thể xử lý ảnh '{file.filename}': {e}")

    return sid, saved_paths


def get_upload_paths(session_id: str) -> List[str]:
    """Lấy lại danh sách đường dẫn ảnh đã upload theo session_id."""
    session_dir = os.path.join(UPLOADS_DIR, session_id)
    if not os.path.isdir(session_dir):
        return []

    paths = []
    for fname in sorted(os.listdir(session_dir)):
        if fname.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            paths.append(os.path.join(session_dir, fname))
    return paths


def cleanup_upload(session_id: str):
    """Xóa toàn bộ ảnh upload của 1 session."""
    session_dir = os.path.join(UPLOADS_DIR, session_id)
    shutil.rmtree(session_dir, ignore_errors=True)

```

### File: `backend\services\key_manager.py`
```py
import os
from typing import List, Optional
import itertools
from dotenv import load_dotenv

load_dotenv()

class KeyManager:
    """
    Quản lý xoay vòng (Rotation) API Keys để chống lại lỗi 429 Quota Exceeded.
    Hỗ trợ lấy danh sách keys từ biến môi trường (ví dụ: GEMINI_API_KEY_1, GEMINI_API_KEY_2,...)
    """
    def __init__(self, prefix: str = "GEMINI_API_KEY"):
        self.keys: List[str] = []
        
        # Lấy key chính
        main_key = os.getenv(prefix)
        if main_key:
            self.keys.append(main_key)
            
        # Lấy các key dự phòng có đánh số
        idx = 1
        while True:
            backup_key = os.getenv(f"{prefix}_{idx}")
            if not backup_key:
                break
            if backup_key not in self.keys:
                self.keys.append(backup_key)
            idx += 1
            
        if not self.keys:
            # Fallback nếu không cấu hình
            self.keys = [""]
            
        self.cycle = itertools.cycle(self.keys)
        self.current_key = next(self.cycle)
        
    def get_current_key(self) -> str:
        return self.current_key
        
    def rotate(self) -> str:
        """Chuyển sang key tiếp theo và trả về key đó."""
        self.current_key = next(self.cycle)
        return self.current_key

# Global instances cho dễ sử dụng
gemini_keys = KeyManager("GEMINI_API_KEY")
fal_keys = KeyManager("FAL_KEY")

```

### File: `backend\services\motion_effects.py`
```py
# backend/services/motion_effects.py
"""
MODULE MỚI - motion_effects.py
================================
Xử lý 2 vấn đề "video bị đứng hình / cảm giác slideshow":

1. Ken Burns effect (zoom + pan chậm) cho các cảnh dùng ẢNH TĨNH
   (trường hợp fallback không dùng Veo, hoặc mode Photo Narration / Slideshow).
2. Đồng bộ THỜI LƯỢNG mỗi cảnh theo đúng độ dài giọng đọc thực tế
   (dùng dữ liệu word_boundaries đã có sẵn từ tts_service.py),
   thay vì set cứng ví dụ 4 giây / cảnh.

Yêu cầu: ffmpeg đã có sẵn trong hệ thống (bạn đang dùng MoviePy nên chắc chắn có).
"""

import subprocess
import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. KEN BURNS EFFECT - biến ảnh tĩnh thành clip có chuyển động mượt
# ---------------------------------------------------------------------------
def apply_ken_burns(
    image_path: str,
    output_path: str,
    duration: float,
    fps: int = 30,
    zoom_start: float = 1.0,
    zoom_end: float = 1.15,
    pan_direction: str = "center",
    resolution: Tuple[int, int] = (1080, 1920),  # mặc định 9:16
) -> str:
    """
    Dùng ffmpeg filter `zoompan` để tạo hiệu ứng Ken Burns (zoom + pan chậm).
    Đây là kỹ thuật bắt buộc phải có với các cảnh ảnh tĩnh (Pollinations fallback),
    nếu không video sẽ trông rất "chết" khi so với các cảnh Veo có chuyển động thật.

    pan_direction: "center" | "left_to_right" | "right_to_left" | "top_to_bottom"
    """
    total_frames = int(duration * fps)
    w, h = resolution

    # Công thức zoom tuyến tính từ zoom_start -> zoom_end trong suốt clip
    zoom_expr = f"'{zoom_start}+({zoom_end}-{zoom_start})*on/{total_frames}'"

    pan_map = {
        "center": ("iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
        "left_to_right": ("(iw-iw/zoom)*on/{}".format(total_frames), "ih/2-(ih/zoom/2)"),
        "right_to_left": ("(iw-iw/zoom)*(1-on/{})".format(total_frames), "ih/2-(ih/zoom/2)"),
        "top_to_bottom": ("iw/2-(iw/zoom/2)", "(ih-ih/zoom)*on/{}".format(total_frames)),
    }
    x_expr, y_expr = pan_map.get(pan_direction, pan_map["center"])

    zoompan_filter = (
        f"zoompan=z={zoom_expr}:x='{x_expr}':y='{y_expr}':"
        f"d={total_frames}:s={w}x{h}:fps={fps}"
    )

    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    cmd = [
        ffmpeg_exe, "-y",
        "-loop", "1",
        "-i", image_path,
        "-vf", zoompan_filter,
        "-t", str(duration),
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264",
        "-preset", "fast",
        output_path,
    ]

    logger.info(f"[KenBurns] {image_path} -> {output_path} (dur={duration}s, pan={pan_direction})")
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def pick_pan_direction(scene_index: int) -> str:
    """
    Xen kẽ hướng pan giữa các cảnh để tránh lặp lại 1 kiểu chuyển động
    nhàm chán xuyên suốt video (dấu hiệu nhận biết ngay của video AI kém đầu tư).
    """
    directions = ["left_to_right", "right_to_left", "center", "top_to_bottom"]
    return directions[scene_index % len(directions)]


# ---------------------------------------------------------------------------
# 2. ĐỒNG BỘ THỜI LƯỢNG CẢNH THEO GIỌNG ĐỌC THỰC TẾ
# ---------------------------------------------------------------------------
def compute_scene_duration_from_audio(
    word_boundaries: List[Dict[str, Any]],
    fallback_duration: float = 2.0,
    min_duration: float = 2.0,
    padding_start: float = 0.15,
    padding_end: float = 0.65,
) -> float:
    """
    Tính thời lượng thực tế của 1 cảnh dựa trên word_boundaries do Edge-TTS trả về
    (mỗi phần tử có "duration" tính bằng giây, giống dữ liệu bạn đang dùng cho
    phụ đề karaoke trong video_service.py).

    Việc này thay thế cho scene duration cố định (VD: luôn 4s/cảnh), giúp:
    - Cảnh có câu thoại dài sẽ tự động dài hơn, không bị cắt cụt lời.
    - Cảnh có câu thoại ngắn sẽ không bị kéo dài lê thê gây chán.

    padding_start/padding_end: thời gian đệm đầu/cuối để cảnh không bị "hụt hơi"
    ngay khi giọng đọc vừa dứt.
    """
    if not word_boundaries:
        # Nếu không có word boundaries (lỗi hoặc do virtual voice minion),
        # ưu tiên dùng độ dài thật của audio (fallback_duration) cộng thêm padding.
        # Nếu audio bị lỗi (duration=0) thì mới fallback về min_duration.
        if fallback_duration > 0:
            return max(fallback_duration + padding_end, min_duration)
        return min_duration

    # Tính thời điểm từ kết thúc cuối cùng (max_end).
    # Vì file âm thanh gốc KHÔNG bị cắt phần im lặng ở đầu trong video_service.py,
    # độ dài cảnh phải bao trùm toàn bộ thời gian từ 0 đến max_end.
    max_end = max(wb["offset"] + wb["duration"] for wb in word_boundaries)
    
    # Cộng thêm khoảng nghỉ (padding_end) để giọng đọc dứt hẳn mới chuyển cảnh
    scene_duration = max_end + padding_end
    return max(scene_duration, min_duration)


def build_scene_timeline(scenes_with_audio: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Input: list scene, mỗi scene có key "word_boundaries" (từ tts_service.py).
    Output: cùng list đó nhưng đã gắn thêm "computed_duration" và "start_time"
    (mốc thời gian tuyệt đối để ghép timeline cuối cùng + để đồng bộ beat-sync).

    Cách dùng trong _run_render_pipeline (main.py):
        scenes = build_scene_timeline(scenes)
        for s in scenes:
            duration = s["computed_duration"]
            # -> truyền vào apply_ken_burns() hoặc dùng để trim clip Veo
    """
    cursor = 0.0
    for scene in scenes_with_audio:
        wb = scene.get("word_boundaries", [])
        # raw_dur đã lưu độ dài thực tế của file MP3 (từ tts_service) trong main.py
        raw_dur = scene.get("computed_duration", 2.0)
        
        duration = compute_scene_duration_from_audio(wb, fallback_duration=raw_dur)
        scene["computed_duration"] = duration
        scene["start_time"] = cursor
        cursor += duration
    return scenes_with_audio

```

### File: `backend\services\render_export.py`
```py
# backend/services/render_export.py
"""
MODULE MỚI - render_export.py
===============================
Thay thế bước export cuối cùng (hiện đang dùng clip.write_videofile() của MoviePy,
chạy bằng CPU libx264) bằng lệnh ffmpeg trực tiếp có GPU encode (NVENC).

CHỈ dùng module này nếu server có GPU NVIDIA. Nếu chạy trên máy không có GPU
(CPU-only), set use_gpu=False để tự động fallback về libx264 CPU như cũ.

Lợi ích: giảm thời gian encode 3-4 lần so với CPU encode ở cùng chất lượng,
quan trọng khi có nhiều user render đồng thời (đúng với mục Technical Debt #2
bạn đã tự ghi trong tài liệu - chuẩn bị sẵn cho việc scale multi-user).
"""

import subprocess
import logging
import shutil

logger = logging.getLogger(__name__)


def _has_nvenc() -> bool:
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    
    # We always have ffmpeg through imageio_ffmpeg
    try:
        result = subprocess.run(
            [ffmpeg_exe, "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10,
        )
        return "h264_nvenc" in result.stdout
    except Exception:
        return False


def export_final_video(
    input_video_path: str,
    ass_subtitle_path: str,
    audio_path: str,
    output_path: str,
    use_gpu: bool = True,
    resolution: str = "1080x1920",
    fps: int = 30,
    crf_or_bitrate: str = "8M",
    watermark_text: str = None,
) -> str:
    """
    Ghép video (đã có scene được nối sẵn) + phụ đề ASS (burned-in bằng filter
    `ass=`) + audio track cuối cùng, xuất ra file MP4 thành phẩm.

    use_gpu=True  -> dùng h264_nvenc (yêu cầu GPU NVIDIA + driver hỗ trợ NVENC)
    use_gpu=False -> dùng libx264 CPU (giống hành vi hiện tại của bạn qua MoviePy)

    ass_subtitle_path: file .ass bạn đã tạo sẵn ở Phụ lục 4 (karaoke captions),
    KHÔNG thay đổi logic sinh phụ đề, chỉ thay đổi bước "đốt" phụ đề vào video.
    """
    gpu_available = use_gpu and _has_nvenc()
    codec = "h264_nvenc" if gpu_available else "libx264"

    # Xây dựng filter scale + ass
    vf_filter = f"scale={resolution.replace('x', ':')}"
    if ass_subtitle_path:
        import os
        # Dùng relative path để tránh lỗi dấu hai chấm (:) của ổ đĩa Windows (C:) trong filter ass
        ass_rel = os.path.relpath(ass_subtitle_path)
        ass_safe = ass_rel.replace('\\', '/')
        vf_filter += f",ass={ass_safe}"

    # Đóng dấu bản quyền (Watermark) nếu có
    if watermark_text:
        wm_text = watermark_text.replace("'", "").replace(":", "")  # sanitize basic
        # Trên Windows cần chỉ định rõ fontfile cho drawtext để tránh crash
        font_path = "C\\:/Windows/Fonts/arial.ttf"
        vf_filter += f",drawtext=fontfile='{font_path}':text='{wm_text}':fontcolor=white@0.6:fontsize=32:x=(w-text_w)/2:y=80:borderw=1:bordercolor=black"

    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    cmd = [
        ffmpeg_exe, "-y",
        "-i", input_video_path,
        "-i", audio_path,
        "-vf", vf_filter,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", codec,
    ]

    if gpu_available:
        cmd += ["-preset", "p4", "-b:v", crf_or_bitrate, "-rc", "vbr"]
    else:
        cmd += ["-preset", "medium", "-crf", "20"]

    cmd += [
        "-c:a", "aac", "-b:a", "192k",
        "-r", str(fps),
        "-pix_fmt", "yuv420p",
        output_path,
    ]

    logger.info(f"[Export] Encode bằng {codec} (GPU={'CÓ' if gpu_available else 'KHÔNG'}) -> {output_path}")
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path

```

### File: `backend\services\tts_service.py`
```py
"""
tts_service.py
---------------
NÂNG CẤP V2:
1. Giữ nguyên fix nợ kỹ thuật #1 (async/await trực tiếp).
2. Thêm `rate` parameter: điều chỉnh tốc độ đọc (ví dụ "-10%" cho chậm,
   "+10%" cho nhanh). Hữu ích cho quiz mode (nhanh) vs storyteller (chậm).
3. Thêm `get_available_voices()`: trả về danh sách giọng đọc tiếng Việt
   có sẵn để frontend hiển thị.
"""

from __future__ import annotations

import edge_tts
from mutagen.mp3 import MP3  # để đo chính xác độ dài audio (giây)

DEFAULT_VOICE = "vi-VN-HoaiMyNeural"  # giọng nữ tiếng Việt mặc định
DEFAULT_RATE = "+5%"  # tốc độ đọc mặc định (nhanh hơn một chút để tự nhiên hơn)

# Danh sách giọng đọc tiếng Việt hỗ trợ bởi Edge-TTS
VIETNAMESE_VOICES = [
    {"id": "vi-VN-HoaiMyNeural", "name": "Hoài My", "gender": "Nữ"},
    {"id": "vi-VN-NamMinhNeural", "name": "Nam Minh", "gender": "Nam"},
    {"id": "vi-VN-AnNiNeural", "name": "An Ni (Trẻ trung)", "gender": "Nữ"},
    {"id": "vi-VN-PhuongMyNeural", "name": "Phương My (Tin tức)", "gender": "Nữ"},
    {"id": "minion", "name": "Minion (Nhí nhảnh)", "gender": "Ảo"},
    {"id": "minion_pro", "name": "Minion Pro (Hỗn loạn, Cuốn hút)", "gender": "Ảo"},
]

import random
import re

def _minion_pro_transform(text: str) -> str:
    """Biến đổi văn bản thành kiểu nói nhí nhảnh, lúng búng của Minion."""
    gibberish = ["Bello!", "Pô-pa-yê!", "Ba-na-na!", "Tu-la-li-lu!", "Pa-ra tu!", "Hí hí!", "He he he!", "Báp-pôi!"]
    
    # 1. Tách thành các câu nhỏ
    sentences = re.split(r'(?<=[.!?]) +', text.strip())
    transformed = []
    
    for s in sentences:
        if not s: continue
        # Đổi dấu chấm thành dấu hỏi để tạo ngữ điệu lên giọng cuối câu
        s = s.replace('.', '?')
        
        words = s.split()
        if not words: continue
        
        # 2. Thêm nói lắp búng (stuttering) ngẫu nhiên vào các từ bắt đầu bằng b, p, m, n
        for i, w in enumerate(words):
            if len(w) > 2 and w[0].lower() in ['b', 'p', 'm', 'n'] and random.random() < 0.2:
                words[i] = f"{w[0]}-{w}"
        
        # 3. Lắp lại thành câu, chèn các từ gián đoạn (ngắt câu dồn dập)
        new_s = ""
        for i, w in enumerate(words):
            new_s += w + " "
            if random.random() < 0.1 and i < len(words) - 1:
                new_s += ", "
                
        # 4. Thêm gibberish / tiếng cười ngẫu nhiên vào đầu hoặc cuối câu
        if random.random() < 0.4:
            new_s = random.choice(gibberish) + " " + new_s
        elif random.random() < 0.4:
            new_s = new_s.strip() + " " + random.choice(gibberish)
            
        transformed.append(new_s.strip())
        
    return " ".join(transformed)


# ── Emotion Profiles: điều chỉnh tốc độ/cao độ theo cảm xúc từng cảnh ──
# GIẢM pitch_delta xuống mức cực nhỏ (+-2Hz, +-4Hz) để giữ nguyên BẢN SẮC giọng thật,
# tránh việc đổi pitch quá mạnh khiến giọng nghe như 2 người khác nhau.
EMOTION_PROFILES = {
    "hook":      {"rate_delta": "+10%",  "pitch_delta": "+2Hz"},    # Nhanh, hào hứng
    "calm":      {"rate_delta": "+0%",   "pitch_delta": "+0Hz"},    # Bình thường
    "dramatic":  {"rate_delta": "-10%",  "pitch_delta": "-2Hz"},    # Chậm, trầm nhẹ
    "excited":   {"rate_delta": "+15%",  "pitch_delta": "+4Hz"},    # Rất nhanh, hơi cao
    "suspense":  {"rate_delta": "-5%",   "pitch_delta": "-4Hz"},    # Hơi chậm, trầm xuống
    "closing":   {"rate_delta": "-5%",   "pitch_delta": "+0Hz"},    # Nhẹ nhàng, kết thúc
}


def _apply_emotion_to_rate_pitch(rate: str, pitch: str, emotion: str) -> tuple:
    """Cộng dồn delta từ emotion profile vào rate/pitch base của user."""
    profile = EMOTION_PROFILES.get(emotion)
    if not profile:
        return rate, pitch
    
    import re
    # Parse rate: "+5%" -> 5
    rate_match = re.match(r'([+-]?\d+)%', rate)
    base_rate = int(rate_match.group(1)) if rate_match else 0
    delta_rate_match = re.match(r'([+-]?\d+)%', profile["rate_delta"])
    delta_rate = int(delta_rate_match.group(1)) if delta_rate_match else 0
    new_rate = f"{base_rate + delta_rate:+d}%"
    
    # Parse pitch: "+0Hz" -> 0
    pitch_match = re.match(r'([+-]?\d+)Hz', pitch)
    base_pitch = int(pitch_match.group(1)) if pitch_match else 0
    delta_pitch_match = re.match(r'([+-]?\d+)Hz', profile["pitch_delta"])
    delta_pitch = int(delta_pitch_match.group(1)) if delta_pitch_match else 0
    new_pitch = f"{base_pitch + delta_pitch:+d}Hz"
    
    return new_rate, new_pitch


async def synthesize_speech(
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
    pitch: str = "+0Hz",
    mode: str = "storyteller",
    emotion: str = "",
) -> tuple[float, list]:
    """
    Chuyển văn bản -> giọng nói, lưu file mp3 tại output_path.
    emotion: cảm xúc của cảnh (hook, calm, dramatic, excited, suspense, closing).
    Nếu có emotion, tốc độ và cao độ sẽ được điều chỉnh tự động.
    """
    if voice not in [v["id"] for v in VIETNAMESE_VOICES] and not voice.startswith("minion"):
        print(f"Voice {voice} không tồn tại trong danh sách. Fallback về vi-VN-HoaiMyNeural.")
        voice = "vi-VN-HoaiMyNeural"

    # QUAN TRỌNG: hàm này PHẢI được gọi bằng `await synthesize_speech(...)`
    # từ một hàm `async def` khác. Không gọi run_until_complete ở đây hay
    # ở bất kỳ đâu khác trong codebase.
    import time
    
    # Chuẩn hóa văn bản trước khi đọc để giọng đọc tự nhiên, không bị vấp
    # 1. Xóa ký tự Markdown (**, *, #, -)
    text = text.replace("**", "").replace("*", "").replace("#", "").replace(" - ", ", ")
    
    # 2. Dịch các từ viết tắt phổ biến
    acronyms = {
        "VNĐ": "Việt Nam Đồng",
        "CHDV": "căn hộ dịch vụ",
        "App": "ứng dụng",
        "AI": "ây ai"
    }
    for k, v in acronyms.items():
        text = text.replace(k, v)
        
    # Thêm nhịp thở tự nhiên (pacing) bằng dấu chấm lửng
    import re
    # Thay thế dấu phẩy hoặc chấm kết hợp khoảng trắng bằng dấu chấm lửng để edge-tts tự động tạo pause tự nhiên
    text = re.sub(r'([.,!?;])\s+', r'\1 ... ', text)

    # Kể chuyện ma (suspense): kéo dài nhịp hơn nữa
    if mode == "storyteller" and ("ma" in text.lower() or "hồi hộp" in text.lower() or voice == "vi-VN-NamMinhNeural"):
        text = text.replace(",", " ... ... ")
    # Xử lý giọng ảo (Virtual Voices)
    if voice == "minion":
        voice = "vi-VN-HoaiMyNeural"
        rate = "+30%"
        pitch = "+400Hz" # Tăng cao độ (chipmunk)
    elif voice == "minion_pro":
        voice = "vi-VN-HoaiMyNeural"
        rate = "+45%"
        pitch = f"+{random.randint(350, 450)}Hz" # Dao động cao độ
        text = _minion_pro_transform(text)
    # Áp dụng Emotion Profile (điều chỉnh tốc độ/cao độ theo cảm xúc cảnh)
    # Chỉ áp dụng khi KHÔNG phải giọng ảo (minion đã override rate/pitch riêng)
    elif emotion:
        rate, pitch = _apply_emotion_to_rate_pitch(rate, pitch, emotion)
    
    # Loại bỏ thẻ SSML <break> nếu có, vì Edge-TTS API sẽ tự động escape XML
    # khiến engine đọc thành ký tự thay vì tạm dừng. (V2.1 - Fallback fix)
    if "<break" in text:
        import re
        text = re.sub(r'<break[^>]*>', '...', text).strip()

    temp_path = output_path + ".tmp"
    last_error = None
    for attempt in range(3):
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
            
            word_boundaries = []
            audio_data = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data.extend(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    # offset và duration của Edge-TTS tính bằng 100ns (ticks)
                    word_boundaries.append({
                        "offset": chunk["offset"] / 10000000.0,
                        "duration": chunk["duration"] / 10000000.0,
                        "text": chunk["text"]
                    })
                    
            with open(temp_path, "wb") as f:
                f.write(audio_data)
            
            # Đảm bảo file hợp lệ
            audio = MP3(temp_path)
            duration_seconds = audio.info.length
            
            import shutil
            shutil.move(temp_path, output_path)
            
            return duration_seconds, word_boundaries
        except Exception as e:
            last_error = e
            print(f"Edge-TTS error (attempt {attempt+1}/3): {e}")
            import os
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if os.path.exists(output_path):
                os.remove(output_path)
            import asyncio
            await asyncio.sleep(2)
            
    # Fallback if TTS fails completely: Create a dummy audio file of 3 seconds
    print(f"TTS failed completely: {last_error}. Using fallback dummy audio.")
    try:
        from gtts import gTTS
        tts = gTTS(text, lang='vi')
        temp_path = output_path + ".gtts.tmp"
        tts.save(temp_path)
        audio = MP3(temp_path)
        duration = audio.info.length
        import shutil
        shutil.move(temp_path, output_path)
        return duration, []
    except Exception as gtts_e:
        print(f"gTTS fallback failed: {gtts_e}")
        import os
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)
        # Return 3 seconds dummy
        return 3.0, []


def get_available_voices():
    # Tra ve danh sach giong doc de frontend hien thi.
    return VIETNAMESE_VOICES

```

### File: `backend\services\veo_service.py`
```py
# backend/services/veo_service.py
"""
PHIÊN BẢN NÂNG CẤP - veo_service.py
====================================
Bổ sung 3 tính năng cốt lõi của Veo 3.1 mà bản gốc chưa khai thác:

1. Character/Style Reference Images (Ingredients to Video)
   -> Giữ nhân vật/phong cách nhất quán xuyên suốt toàn bộ video (chống identity drift).
2. First-frame -> Last-frame chaining giữa các scene
   -> Video liền mạch như một cuốn phim thật, không còn cảm giác "ghép ảnh rời rạc".
3. Scene Extension (tuỳ chọn) cho các câu chuyện liên tục (storyteller mode)
   -> Video dài hơn 8s mà vẫn giữ chuyển động + âm thanh liên tục.

LƯU Ý TÍCH HỢP:
- File này giả định bạn dùng SDK `google-genai` (import google.genai as genai).
  Nếu bạn đang gọi REST API trực tiếp qua requests/httpx, giữ nguyên logic
  điều phối (orchestration) bên dưới, chỉ thay phần gọi model bằng http call
  tương ứng - cấu trúc payload (reference_images, image/last_frame) là như nhau.
- Cần cài: pip install google-genai ffmpeg-python
- Cần ffmpeg có sẵn trong PATH để trích last-frame từ clip.
"""

import os
import uuid
import asyncio
import logging
from typing import List, Optional, Dict, Any

import ffmpeg
from google import genai
from google.genai import types

from .key_manager import gemini_keys  # giữ nguyên key rotation hiện có

logger = logging.getLogger(__name__)

ASSETS_DIR = "assets"
IMAGES_DIR = os.path.join(ASSETS_DIR, "images")
VIDEO_TMP_DIR = os.path.join(ASSETS_DIR, "veo_tmp")
os.makedirs(VIDEO_TMP_DIR, exist_ok=True)

VEO_MODEL_QUALITY = "veo-3.1-generate-preview"   # dùng cho bản final render
VEO_MODEL_FAST = "veo-3.1-fast-generate-preview"  # dùng cho preview / nháp nhanh


def _get_client() -> genai.Client:
    """Lấy client Gemini với API key đang xoay vòng (key_manager có sẵn)."""
    api_key = gemini_keys.rotate()
    return genai.Client(api_key=api_key)


# ---------------------------------------------------------------------------
# 1. TẠO ẢNH NHÂN VẬT GỐC (CHARACTER SHEET) - dùng làm reference xuyên suốt
# ---------------------------------------------------------------------------
async def generate_character_reference(
    description: str,
    art_style: str = "Cinematic",
    num_variants: int = 1,
) -> List[str]:
    """
    Sinh 1-3 ảnh "character sheet" bằng Imagen 3 (gọi qua image_router.py hiện có
    của bạn) để dùng làm reference_images cho MỌI cảnh Veo tiếp theo.

    Trả về danh sách đường dẫn file ảnh cục bộ (không phải mảng byte),
    vì Veo API nhận ảnh qua path/bytes tùy SDK.

    Cách dùng trong pipeline:
        char_refs = await generate_character_reference(
            description="cô gái tóc ngắn đen, mặc áo khoác bomber xanh lá, kính tròn",
            art_style="Cinematic, warm lighting"
        )
        # -> truyền char_refs vào generate_scene_video() cho TẤT CẢ các scene
    """
    from .image_router import generate_image_with_fallback

    prompt = (
        f"Character reference sheet, {description}, {art_style}, "
        f"neutral pose, clear face, well-lit studio lighting, front view, "
        f"consistent identity for AI video reference"
    )
    paths = []
    for i in range(num_variants):
        img_path = os.path.join(VIDEO_TMP_DIR, f"char_ref_{uuid.uuid4().hex[:8]}.png")
        await generate_image_with_fallback(
            image_prompt=prompt, 
            output_path=img_path,
            aspect_ratio="1:1"
        )
        paths.append(img_path)
    return paths


# ---------------------------------------------------------------------------
# 2. TRÍCH XUẤT KHUNG HÌNH CUỐI CỦA 1 CLIP (để nối cảnh mượt)
# ---------------------------------------------------------------------------
def extract_last_frame(video_path: str, out_image_path: Optional[str] = None) -> str:
    """
    Dùng ffmpeg trích khung hình cuối cùng của video_path, lưu thành ảnh PNG.
    Ảnh này sẽ được dùng làm "last_frame" / "first frame của scene kế tiếp"
    để Veo 3.1 tạo chuyển cảnh mượt (frame-to-frame transition).
    """
    if out_image_path is None:
        out_image_path = os.path.join(VIDEO_TMP_DIR, f"lastframe_{uuid.uuid4().hex[:8]}.png")

    probe = ffmpeg.probe(video_path)
    duration = float(probe["format"]["duration"])
    # Lùi lại 0.05s để tránh lỗi decode ở đúng frame cuối
    seek_time = max(0, duration - 0.05)

    (
        ffmpeg
        .input(video_path, ss=seek_time)
        .output(out_image_path, vframes=1)
        .overwrite_output()
        .run(quiet=True)
    )
    return out_image_path


# ---------------------------------------------------------------------------
# 3. SINH VIDEO CHO 1 SCENE - có reference_images + first_frame optional
# ---------------------------------------------------------------------------
async def generate_scene_video(
    scene_prompt: str,
    aspect_ratio: str = "9:16",
    reference_images: Optional[List[str]] = None,
    first_frame_image: Optional[str] = None,
    last_frame_image: Optional[str] = None,
    use_fast_model: bool = False,
    negative_prompt: str = "",
) -> str:
    """
    Gọi Veo 3.1 để sinh video cho 1 cảnh, có hỗ trợ:
      - reference_images: tối đa 3-4 ảnh giữ nhân vật/phong cách nhất quán
      - first_frame_image: ảnh mở đầu cảnh (thường = last_frame của cảnh trước)
      - last_frame_image: ảnh kết thúc cảnh (dùng khi muốn ép transition có đích đến rõ)

    Trả về đường dẫn file video (.mp4) đã tải về máy chủ.
    """
    client = _get_client()
    model = VEO_MODEL_FAST if use_fast_model else VEO_MODEL_QUALITY

    config_kwargs: Dict[str, Any] = {
        "aspect_ratio": aspect_ratio,          # native 9:16, không cần crop hậu kỳ
        "negative_prompt": negative_prompt or None,
    }

    # --- Character/style consistency ---
    if reference_images:
        loaded_refs = []
        for path in reference_images[:3]:  # Veo 3.1 tối đa 3 ảnh reference ổn định
            loaded_refs.append(types.Image.from_file(path))
        config_kwargs["reference_images"] = loaded_refs

    # --- Frame-to-frame transition (nối cảnh mượt) ---
    image_arg = None
    if first_frame_image:
        image_arg = types.Image.from_file(first_frame_image)
    if last_frame_image:
        config_kwargs["last_frame"] = types.Image.from_file(last_frame_image)

    logger.info(f"[Veo] Đang tạo scene: model={model}, aspect={aspect_ratio}, "
                f"has_ref={bool(reference_images)}, chained={bool(first_frame_image)}")

    operation = client.models.generate_videos(
        model=model,
        prompt=scene_prompt,
        image=image_arg,
        config=types.GenerateVideosConfig(**config_kwargs),
    )

    # Veo generation là async operation -> poll cho tới khi xong
    while not operation.done:
        await asyncio.sleep(5)
        operation = client.operations.get(operation)

    video_result = operation.result.generated_videos[0]
    out_path = os.path.join(VIDEO_TMP_DIR, f"scene_{uuid.uuid4().hex[:8]}.mp4")
    video_result.video.save(out_path)
    return out_path


# ---------------------------------------------------------------------------
# 4. ĐIỀU PHỐI TOÀN BỘ CHUỖI CẢNH - đây là hàm bạn gọi từ video_service.py
# ---------------------------------------------------------------------------
async def generate_scene_chain(
    scenes: List[Dict[str, Any]],
    aspect_ratio: str = "9:16",
    character_description: Optional[str] = None,
    art_style: str = "Cinematic",
    use_frame_chaining: bool = True,
    use_fast_model: bool = False,
) -> List[str]:
    """
    Sinh toàn bộ chuỗi video cho các scenes, tự động:
      - Tạo character reference 1 lần dùng chung cho mọi cảnh (nếu có character_description)
      - Nối last_frame của cảnh N làm first_frame của cảnh N+1 (nếu use_frame_chaining=True)

    scenes: list các dict, mỗi dict cần có key "prompt" (mô tả cảnh quay).
    Trả về list đường dẫn video (.mp4) theo đúng thứ tự scenes.
    """
    reference_images: List[str] = []
    if character_description:
        reference_images = await generate_character_reference(
            description=character_description,
            art_style=art_style,
        )

    video_paths: List[str] = []
    previous_last_frame: Optional[str] = None

    for idx, scene in enumerate(scenes):
        first_frame = previous_last_frame if (use_frame_chaining and idx > 0) else None

        video_path = await generate_scene_video(
            scene_prompt=scene["prompt"],
            aspect_ratio=aspect_ratio,
            reference_images=reference_images or None,
            first_frame_image=first_frame,
            use_fast_model=use_fast_model,
            negative_prompt=scene.get("negative_prompt", ""),
        )
        video_paths.append(video_path)

        if use_frame_chaining:
            previous_last_frame = extract_last_frame(video_path)

    return video_paths

```

### File: `backend\services\video_service.py`
```py
"""
video_service.py
-----------------
NÂNG CẤP V2:
1. Đa tỉ lệ khung hình: 9:16 (TikTok/Reels), 16:9 (YouTube), 1:1 (Instagram).
2. BGM mixing: overlay nhạc nền dưới giọng đọc (volume ~15%).
3. Slideshow mode: ảnh + BGM, không TTS, Ken Burns mạnh, crossfade dài.
4. Quiz mode: text overlay lớn hơn, màu nhấn khác.
5. Giữ nguyên tất cả fix nợ kỹ thuật V1 (MoviePy v2, crossfade, subtitle burn-in).
"""

from __future__ import annotations

import os
from typing import List, Optional, TypedDict
import datetime as dt

from moviepy import (
    AudioFileClip,
    VideoFileClip,
    ImageClip,
    CompositeVideoClip,
    CompositeAudioClip,
    TextClip,
    concatenate_videoclips,
)
from moviepy.video.fx import CrossFadeIn, CrossFadeOut

# ── Kích thước khung hình theo aspect ratio ──────────────────────────
ASPECT_RATIO_SIZES = {
    "9:16": (1080, 1920),   # TikTok/Reels (dọc)
    "16:9": (1920, 1080),   # YouTube (ngang)
    "1:1":  (1080, 1080),   # Instagram (vuông)
}

FPS = 30
CROSSFADE_DURATION = 0.4       # giây — crossfade mượt giữa 2 cảnh (tăng từ 0.2 lên 0.4 cho tự nhiên hơn)
SLIDESHOW_CROSSFADE = 0.8      # giây — crossfade dài hơn cho slideshow
AUDIO_FADEOUT_DURATION = 0.3   # giây — audio fade-out cuối mỗi cảnh để tránh ngắt đột ngột
SLIDESHOW_SCENE_DURATION = 5.0 # giây — mỗi ảnh hiển thị bao lâu trong slideshow

# QUAN TRỌNG: font hỗ trợ dấu tiếng Việt (Unicode Latin Extended).
# Windows: arial.ttf hoặc segoeuil.ttf. Linux: DejaVuSans.ttf
SUBTITLE_FONT_PATH = "C:/Windows/Fonts/arial.ttf"

# ── Thư mục BGM ─────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BGM_DIR = os.path.join(BASE_DIR, "assets", "bgm")


class SceneAsset(TypedDict):
    image_path: str
    audio_path: str        # có thể rỗng "" cho slideshow mode
    text: str              # có thể rỗng "" cho slideshow mode
    duration: float        # độ dài audio (giây), hoặc SLIDESHOW_SCENE_DURATION
    sfx: str               # Tên hiệu ứng âm thanh (whoosh, pop...)
    visual_effect: str     # zoom_in, zoom_out, pan_left, pan_right


# ─────────────────────────────────────────────────────────────────────
# Build 1 scene clip
# ─────────────────────────────────────────────────────────────────────
def _build_scene_clip(
    asset: SceneAsset,
    add_crossfade_in: bool,
    video_width: int,
    video_height: int,
    crossfade_dur: float = CROSSFADE_DURATION,
    show_subtitle: bool = True,
    subtitle_font_size: int = 52,
    subtitle_color: str = "white",
    transition: str = "crossfade",
) -> CompositeVideoClip:
    """Ghép 1 ảnh + 1 audio + phụ đề burn-in thành 1 clip hoàn chỉnh."""
    duration = asset["duration"]
    visual_effect = asset.get("visual_effect", "zoom_in")

    # ── Media clip (Video/Image) ──
    is_video = asset["image_path"].lower().endswith((".mp4", ".mov"))
    if is_video:
        media_clip = VideoFileClip(asset["image_path"])
        # Loop video nếu ngắn hơn duration
        if media_clip.duration < duration:
            import math
            from moviepy import concatenate_videoclips
            loops = math.ceil(duration / media_clip.duration)
            media_clip = concatenate_videoclips([media_clip] * loops)
        media_clip = media_clip.subclipped(0, duration)
        media_clip = media_clip.resized(height=video_height)
    else:
        media_clip = (
            ImageClip(asset["image_path"])
            .with_duration(duration)
            .resized(height=video_height)
        )
        
    # Cắt để tỷ lệ luôn đúng trước khi zoom
    if media_clip.w < video_width:
        media_clip = media_clip.resized(width=video_width)

    # Hiệu ứng chuyển động (Ken Burns) đã được xử lý bằng FFmpeg trong motion_effects.py trước đó
    # Nên media_clip ở đây (dù là ảnh tĩnh hay video .mp4) chỉ cần giữ đúng tỷ lệ và center
    media_clip = media_clip.with_position("center")

    layers = [media_clip]

    # ── Audio KHÔNG được gắn vào clip video ──
    # LÝ DO: Khi concatenate_videoclips dùng padding âm (crossfade), 
    # MoviePy sẽ mix audio của 2 clip chồng lấp → giọng đọc bị trùng.
    # Audio sẽ được xây dựng thành track riêng biệt trong render_final_video().

    scene = CompositeVideoClip(layers, size=(video_width, video_height))

    # ── Transition effects theo loại (chỉ ảnh hưởng video, không audio) ──
    if transition == "fade_black":
        from moviepy.video.fx import FadeIn, FadeOut
        if add_crossfade_in:
            scene = scene.with_effects([FadeIn(crossfade_dur)])
        scene = scene.with_effects([FadeOut(crossfade_dur)])
    elif transition == "zoom_through":
        if add_crossfade_in:
            scene = scene.with_effects([CrossFadeIn(crossfade_dur * 0.8)])
        scene = scene.with_effects([CrossFadeOut(crossfade_dur * 0.8)])
    else:
        if add_crossfade_in:
            scene = scene.with_effects([CrossFadeIn(crossfade_dur)])
        scene = scene.with_effects([CrossFadeOut(crossfade_dur)])

    return scene


# BGM Mix and Mastering are now delegated to FFmpeg in audio_mix_service.py


# ─────────────────────────────────────────────────────────────────────
# Main render function
# ─────────────────────────────────────────────────────────────────────
def render_final_video(
    scene_assets: List[SceneAsset],
    output_path: str,
    aspect_ratio: str = "9:16",
    bgm_path: Optional[str] = None,
    mode: str = "storyteller",
    bgm_volume: float = 0.15,
    master_audio_path: Optional[str] = None,
    **kwargs
) -> str:
    """
    Ghép toàn bộ các scene thành 1 video .mp4 hoàn chỉnh.
    Hỗ trợ đa aspect ratio, BGM mixing, và mode-specific rendering.
    Trả về output_path.
    """
    video_width, video_height = ASPECT_RATIO_SIZES.get(aspect_ratio, (1080, 1920))

    # ── Mode-specific settings ──
    is_slideshow = (mode == "photo_slideshow")
    crossfade_dur = SLIDESHOW_CROSSFADE if is_slideshow else CROSSFADE_DURATION
    show_subtitle = not is_slideshow  # Slideshow không có subtitle
    subtitle_font_size = 58 if mode == "quiz_listicle" else 52
    subtitle_color = "#FFD700" if mode == "quiz_listicle" else "white"

    # Slideshow mode: BGM volume cao hơn vì không có narration
    if is_slideshow:
        bgm_volume = 0.8

    clips = []
    audio_tracks = []
    speech_segments = []
    final_duration = 0.0

    for i, asset in enumerate(scene_assets):
        dur = asset.get("duration", 3.0)
        start_time = asset.get("start_time", 0.0)
        has_audio = bool(asset.get("audio_path"))
        
        # Audio ducking tracking
        if has_audio:
            speech_segments.append((start_time, start_time + dur))
            
        # ── Build Audio Track (Đảm bảo các file âm thanh KHÔNG chồng lên nhau) ──
        scene_audio_clips = []
        if has_audio and os.path.isfile(asset["audio_path"]):
            from moviepy.audio.io.AudioFileClip import AudioFileClip
            scene_audio_clips.append(AudioFileClip(asset["audio_path"]))
            
        sfx_name = asset.get("sfx", "")
        if sfx_name:
            sfx_path = os.path.join(BASE_DIR, "assets", "sfx", f"{sfx_name}.wav")
            if os.path.isfile(sfx_path):
                from moviepy.audio.io.AudioFileClip import AudioFileClip
                scene_audio_clips.append(AudioFileClip(sfx_path).with_volume_scaled(0.5))
                
        if scene_audio_clips:
            from moviepy.audio.AudioClip import CompositeAudioClip
            from moviepy.audio.fx.AudioFadeOut import AudioFadeOut
            
            if len(scene_audio_clips) > 1:
                ac = CompositeAudioClip(scene_audio_clips)
            else:
                ac = scene_audio_clips[0]
                
            # Đảm bảo audio không tràn sang cảnh tiếp theo (cắt bỏ phần overlap)
            safe_dur = dur - crossfade_dur if i < len(scene_assets) - 1 else dur
            ac = ac.subclipped(0, min(ac.duration, safe_dur))
            ac = ac.with_effects([AudioFadeOut(AUDIO_FADEOUT_DURATION)])
            
            # Đặt đúng vị trí trên timeline tổng
            ac = ac.with_start(start_time)
            audio_tracks.append(ac)

        
        c = _build_scene_clip(
            asset,
            add_crossfade_in=(i > 0),
            video_width=video_width,
            video_height=video_height,
            crossfade_dur=crossfade_dur,
            show_subtitle=show_subtitle,
            subtitle_font_size=subtitle_font_size,
            subtitle_color=subtitle_color,
            transition=asset.get("transition", "crossfade"),
        )
        
        c = c.with_start(start_time)
        clips.append(c)
        final_duration = max(final_duration, start_time + dur)
        
    final = CompositeVideoClip(clips, size=(video_width, video_height)).with_duration(final_duration)

    # Gắn track âm thanh tuần tự vào video
    if audio_tracks:
        from moviepy.audio.AudioClip import CompositeAudioClip
        final_audio = CompositeAudioClip(audio_tracks)
        final = final.with_audio(final_audio)

    # Nếu dùng Continuous TTS (có master_audio_path)
    if master_audio_path and os.path.exists(master_audio_path):
        from moviepy.audio.io.AudioFileClip import AudioFileClip
        master_audio = AudioFileClip(master_audio_path)
        
        # Audio gốc dài hơn video do padding, ta cắt lại cho khớp với video final
        master_audio = master_audio.subclipped(0, min(final.duration, master_audio.duration))
        final = final.with_audio(master_audio)
        
        # Vì giọng nói liền mạch, ducking BGM toàn bộ video
        speech_segments = [(0.0, final.duration)]

    # BGM mixing now happens via FFmpeg in audio_mix_service.py

    # ── Thêm Hiệu ứng Hình ảnh (Vignette & Progress Bar) ──
    import numpy as np
    from moviepy.video.VideoClip import ImageClip, VideoClip
    
    overlays = [final]
    
    # 1. Vignette (Làm tối 4 góc)
    x = np.linspace(-1, 1, video_width)
    y = np.linspace(-1, 1, video_height)
    X, Y = np.meshgrid(x, y)
    radius = np.sqrt(X**2 + Y**2)
    opacity = np.clip(radius - 0.6, 0, 1) * 0.7
    vig_img = np.zeros((video_height, video_width, 4), dtype=np.uint8)
    vig_img[:, :, 3] = (opacity * 255).astype(np.uint8)
    vig_clip = ImageClip(vig_img, is_mask=False).with_duration(final.duration)
    overlays.append(vig_clip)
    
    # 2. Progress Bar (Dưới cùng)
    bar_height = 12
    def make_progress_frame(t):
        w = int(video_width * (t / final.duration))
        if w == 0: w = 1
        frame = np.zeros((bar_height, video_width, 4), dtype=np.uint8)
        frame[:, :w, 0] = 255
        frame[:, :w, 1] = 215
        frame[:, :w, 2] = 0
        frame[:, :w, 3] = 255
        return frame
        
    progress_clip = VideoClip(make_progress_frame, is_mask=False, has_constant_size=True).with_duration(final.duration).with_position(("left", "bottom"))
    overlays.append(progress_clip)
    
    final = CompositeVideoClip(overlays, size=(video_width, video_height)).with_audio(final.audio)


    final.write_videofile(
        output_path,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        threads=4,
        preset="medium",
    )

    # Giải phóng tài nguyên ngay sau khi render xong (giảm áp lực RAM)
    for c in clips:
        c.close()
    final.close()

    return output_path


# ─────────────────────────────────────────────────────────────────────
# SRT generation
# ─────────────────────────────────────────────────────────────────────
def generate_ass_file(scene_assets: List[SceneAsset], output_path: str, mode: str = "storyteller", subtitle_style: str = "karaoke_bold", hook_text: str = None) -> str:
    """
    Sinh file phụ đề .ass (Advanced SubStation Alpha).
    Hỗ trợ 2 phong cách:
    - karaoke_bold: Viền dày, hiệu ứng nảy (pop-in), màu vàng nổi bật, tự động in hoa.
    - cinematic_box: Chữ trắng trên nền hộp mờ (box/backdrop) kéo ngang, tĩnh, chữ thường.
    """
    ass_content = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
    ]
    
    # ── ĐỊNH NGHĨA STYLE DỰA TRÊN USER SETTING ──
    if subtitle_style == "cinematic_box":
        font_name = "Arial"  # Font hiện đại, sạch sẽ
        font_size = 55
        primary_color = "&H00FFFFFF"     # White
        secondary_color = "&H00FFFFFF"
        outline_color = "&H00000000"     # No outline needed
        back_color = "&H99000000"        # Semi-transparent black (99 is alpha)
        # BorderStyle=3 (Opaque box), Outline=8 (Box padding/margin)
        style_line = f"Style: Default,{font_name},{font_size},{primary_color},{secondary_color},{outline_color},{back_color},-1,0,0,0,100,100,0,0,3,8,0,2,60,60,250,1"
    else: # karaoke_bold (Default)
        # Sửa lỗi font chữ: Đổi từ 'Impact' (thiếu dấu tiếng Việt) sang 'Arial'
        # Do Style bên dưới có tham số Bold=-1 (tức là True), nên font thực tế sẽ là Arial Bold (hỗ trợ 100% tiếng Việt).
        font_name = "Arial"
        font_size = 65 if mode == "quiz_listicle" else 75
        primary_color = "&H0000FFFF"     # Yellow highlight
        secondary_color = "&H00FFFFFF"   # White base
        outline_color = "&H00000000"     # Black outline
        back_color = "&H00000000"        # Black shadow
        # BorderStyle=1 (Outline), Outline=6, Shadow=4
        style_line = f"Style: Default,{font_name},{font_size},{primary_color},{secondary_color},{outline_color},{back_color},-1,0,0,0,100,100,0,0,1,6,4,2,40,40,350,1"
        
    ass_content.append(style_line)
    
    # ── HOOK STYLE (cho Tiêu đề 3s đầu) ──
    # Chữ to, vàng, nằm ở top (MarginV=150)
    hook_style_line = f"Style: HookTitle,Arial,85,&H0000FFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,8,5,8,40,40,150,1"
    ass_content.append(hook_style_line)
    
    ass_content.append("")
    ass_content.append("[Events]")
    ass_content.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")

    # Add hook_text (duration 3 seconds max)
    if hook_text and hook_text.strip():
        # Effect: fade in 200ms, fade out 500ms
        hook_ass = f"{{\\fad(200,500)}}{hook_text.strip().upper()}"
        ass_content.append(f"Dialogue: 1,0:00:00.00,0:00:03.00,HookTitle,,0,0,0,,{hook_ass}")

    cursor = 0.0
    for asset in scene_assets:
        duration = asset["duration"]
        if asset.get("text") and asset["text"].strip():
            start_td = dt.timedelta(seconds=cursor)
            end_td = dt.timedelta(seconds=cursor + duration)
            
            def format_ass_time(td):
                total_seconds = int(td.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                centiseconds = int(td.microseconds / 10000)
                return f"{hours:01d}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"

            start_str = format_ass_time(start_td)
            end_str = format_ass_time(end_td)
            
            # Xử lý Text & Effect
            pop_effect = r"{\fscx50\fscy50\t(0,150,\fscx120\fscy120)\t(150,250,\fscx100\fscy100)}"
            word_boundaries = asset.get("word_boundaries", [])
            
            if subtitle_style == "cinematic_box":
                # Tĩnh, không pop-in, không highlight từng từ
                import textwrap
                raw_text = asset["text"].replace('\n', ' ')
                wrapped = "\\N".join(textwrap.wrap(raw_text, width=32))
                ass_text = wrapped
            else:
                # Karaoke (có highlight + pop-in)
                if word_boundaries:
                    ass_text = pop_effect
                    for wb in word_boundaries:
                        dur_cs = max(1, int(wb["duration"] * 100))
                        text = wb["text"].upper()  # Auto-uppercase cho bold style
                        if text.startswith(" "):
                            ass_text += " "
                            text = text[1:]
                        ass_text += f"{{\\K{dur_cs}}}{text}"
                else:
                    import textwrap
                    text = asset["text"].replace('\n', ' ').upper()
                    wrapped = "\\N".join(textwrap.wrap(text, width=28))
                    ass_text = f"{pop_effect}{wrapped}"
            
            event_line = f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{ass_text}"
            ass_content.append(event_line)
            
        cursor += duration

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(ass_content))

    return output_path



# ─────────────────────────────────────────────────────────────────────
# BGM listing helper
# ─────────────────────────────────────────────────────────────────────
def get_available_bgm() -> List[dict]:
    """Trả về danh sách nhạc nền có sẵn trong assets/bgm/."""
    if not os.path.isdir(BGM_DIR):
        return []

    bgm_list = []
    LABELS = {
        "chill_lofi": "Chill Lo-Fi",
        "epic_cinematic": "Epic Cinematic",
        "upbeat_pop": "Upbeat Pop",
        "soft_piano": "Soft Piano",
        "corporate_minimal": "Corporate Minimal",
    }

    for fname in sorted(os.listdir(BGM_DIR)):
        if fname.lower().endswith((".mp3", ".wav", ".ogg")):
            name_key = os.path.splitext(fname)[0]
            bgm_list.append({
                "id": fname,
                "name": LABELS.get(name_key, name_key.replace("_", " ").title()),
                "path": os.path.join(BGM_DIR, fname),
            })

    return bgm_list

```

### File: `frontend\.oxlintrc.json`
```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "oxc"],
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}

```

### File: `frontend\README.md`
```md
# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and Oxlint's TypeScript related rules in your project.

```

### File: `frontend\index.html`
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>frontend</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>

```

### File: `frontend\package.json`
```json
{
  "name": "frontend",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "lint": "oxlint",
    "preview": "vite preview"
  },
  "dependencies": {
    "axios": "^1.18.1",
    "lucide-react": "^1.21.0",
    "react": "^19.2.7",
    "react-dom": "^19.2.7"
  },
  "devDependencies": {
    "@tailwindcss/postcss": "^4.3.1",
    "@types/react": "^19.2.17",
    "@types/react-dom": "^19.2.3",
    "@vitejs/plugin-react": "^6.0.2",
    "autoprefixer": "^10.5.2",
    "oxlint": "^1.69.0",
    "postcss": "^8.5.15",
    "tailwindcss": "^4.3.1",
    "vite": "^8.1.0"
  }
}

```

### File: `frontend\postcss.config.js`
```js
export default {
  plugins: {
    autoprefixer: {},
  },
}

```

### File: `frontend\tailwind.config.js`
```js
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#0B0F19',
        surface: '#1A2332',
        primary: '#3B82F6',
        primaryHover: '#2563EB',
        textMain: '#F8FAFC',
        textMuted: '#94A3B8',
        borderLight: '#2E3B52'
      }
    },
  },
  plugins: [],
}

```

### File: `frontend\vite.config.js`
```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
})

```

### File: `frontend\src\App.css`
```css
.counter {
  font-size: 16px;
  padding: 5px 10px;
  border-radius: 5px;
  color: var(--accent);
  background: var(--accent-bg);
  border: 2px solid transparent;
  transition: border-color 0.3s;
  margin-bottom: 24px;

  &:hover {
    border-color: var(--accent-border);
  }
  &:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
}

.hero {
  position: relative;

  .base,
  .framework,
  .vite {
    inset-inline: 0;
    margin: 0 auto;
  }

  .base {
    width: 170px;
    position: relative;
    z-index: 0;
  }

  .framework,
  .vite {
    position: absolute;
  }

  .framework {
    z-index: 1;
    top: 34px;
    height: 28px;
    transform: perspective(2000px) rotateZ(300deg) rotateX(44deg) rotateY(39deg)
      scale(1.4);
  }

  .vite {
    z-index: 0;
    top: 107px;
    height: 26px;
    width: auto;
    transform: perspective(2000px) rotateZ(300deg) rotateX(40deg) rotateY(39deg)
      scale(0.8);
  }
}

#center {
  display: flex;
  flex-direction: column;
  gap: 25px;
  place-content: center;
  place-items: center;
  flex-grow: 1;

  @media (max-width: 1024px) {
    padding: 32px 20px 24px;
    gap: 18px;
  }
}

#next-steps {
  display: flex;
  border-top: 1px solid var(--border);
  text-align: left;

  & > div {
    flex: 1 1 0;
    padding: 32px;
    @media (max-width: 1024px) {
      padding: 24px 20px;
    }
  }

  .icon {
    margin-bottom: 16px;
    width: 22px;
    height: 22px;
  }

  @media (max-width: 1024px) {
    flex-direction: column;
    text-align: center;
  }
}

#docs {
  border-right: 1px solid var(--border);

  @media (max-width: 1024px) {
    border-right: none;
    border-bottom: 1px solid var(--border);
  }
}

#next-steps ul {
  list-style: none;
  padding: 0;
  display: flex;
  gap: 8px;
  margin: 32px 0 0;

  .logo {
    height: 18px;
  }

  a {
    color: var(--text-h);
    font-size: 16px;
    border-radius: 6px;
    background: var(--social-bg);
    display: flex;
    padding: 6px 12px;
    align-items: center;
    gap: 8px;
    text-decoration: none;
    transition: box-shadow 0.3s;

    &:hover {
      box-shadow: var(--shadow);
    }
    .button-icon {
      height: 18px;
      width: 18px;
    }
  }

  @media (max-width: 1024px) {
    margin-top: 20px;
    flex-wrap: wrap;
    justify-content: center;

    li {
      flex: 1 1 calc(50% - 8px);
    }

    a {
      width: 100%;
      justify-content: center;
      box-sizing: border-box;
    }
  }
}

#spacer {
  height: 88px;
  border-top: 1px solid var(--border);
  @media (max-width: 1024px) {
    height: 48px;
  }
}

.ticks {
  position: relative;
  width: 100%;

  &::before,
  &::after {
    content: '';
    position: absolute;
    top: -4.5px;
    border: 5px solid transparent;
  }

  &::before {
    left: 0;
    border-left-color: var(--border);
  }
  &::after {
    right: 0;
    border-right-color: var(--border);
  }
}

```

### File: `frontend\src\App.jsx`
```jsx
import React from 'react';
import { Film } from 'lucide-react';
import { useAppContext } from './AppContext';
import { MODES } from './constants';
import SettingsPanel from './components/SettingsPanel';
import ScriptEditor from './components/ScriptEditor';
import RenderProgress from './components/RenderProgress';

export default function App() {
  const ctx = useAppContext();
  const { step, activeMode, setActiveMode, setErrorMsg } = ctx;

  return (
    <div className="app-container">
      <div className="app-header">
        <div className="app-logo">
          <Film size={24} /> AI Video Studio
        </div>
        <div className="header-steps">
          <div className={`header-step ${step === 'config' ? 'active' : ''} ${step !== 'config' ? 'completed' : ''}`}>
            <div className="header-step-num">1</div> Cài đặt
          </div>
          <div className="header-step-arrow">→</div>
          <div className={`header-step ${step === 'editor' ? 'active' : ''} ${['rendering', 'done'].includes(step) ? 'completed' : ''}`}>
            <div className="header-step-num">2</div> Kịch bản
          </div>
          <div className="header-step-arrow">→</div>
          <div className={`header-step ${step === 'rendering' || step === 'done' ? 'active' : ''}`}>
            <div className="header-step-num">3</div> Render
          </div>
        </div>
      </div>

      {step === 'config' && (
        <div className="top-modes">
          {MODES.map(mode => (
            <div
              key={mode.id}
              className={`mode-card ${activeMode === mode.id ? 'active' : ''}`}
              onClick={() => { setActiveMode(mode.id); setErrorMsg(''); }}
            >
              <div className="mode-icon">{mode.icon}</div>
              <div className="mode-title">{mode.title}</div>
              <div className="mode-desc" style={{ whiteSpace: 'pre-line' }}>{mode.desc}</div>
            </div>
          ))}
        </div>
      )}

      {step === 'config' && <SettingsPanel />}
      {step === 'editor' && <ScriptEditor />}
      {(step === 'rendering' || step === 'done') && <RenderProgress />}
    </div>
  );
}

```

### File: `frontend\src\AppContext.jsx`
```jsx
import React, { createContext, useState, useContext, useRef, useCallback } from 'react';
import { STYLES, VOICES, API_BASE, MODE_MAP, DURATION_OPTIONS } from './constants';

const AppContext = createContext();

export const AppProvider = ({ children }) => {
  const [step, setStep] = useState('config');
  
  const [activeMode, setActiveMode] = useState('storyteller');
  const [topic, setTopic] = useState('');
  const [scriptText, setScriptText] = useState('');
  const [ratio, setRatio] = useState('9:16');
  const [numScenes, setNumScenes] = useState(6);
  const [targetDuration, setTargetDuration] = useState('30s');
  const [narrationTone, setNarrationTone] = useState('viral');
  const [voice, setVoice] = useState('vi-VN-NamMinhNeural');
  const [style, setStyle] = useState(STYLES[0].value);
  const [bgm, setBgm] = useState('none');
  const [apiKey, setApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  
  const [useVeo, setUseVeo] = useState(false);
  const [useAnimatedCaptions, setUseAnimatedCaptions] = useState(true);
  const [ctaText, setCtaText] = useState('');
  const [speechRate, setSpeechRate] = useState('+0%');
  const [speechPitch, setSpeechPitch] = useState('+0Hz');
  const [bgmVolume, setBgmVolume] = useState(15);
  const [negativePrompt, setNegativePrompt] = useState('');
  const [characterDescription, setCharacterDescription] = useState('');
  const [useFrameChaining, setUseFrameChaining] = useState(true);
  const [useKenBurns, setUseKenBurns] = useState(true);
  const [useBeatSync, setUseBeatSync] = useState(false);
  const [useVeoAmbientAudio, setUseVeoAmbientAudio] = useState(true);
  const [useGpuEncode, setUseGpuEncode] = useState(true);
  const [hookZoomBoost, setHookZoomBoost] = useState(true);
  const [subtitleStyle, setSubtitleStyle] = useState('karaoke_bold');
  const [watermarkText, setWatermarkText] = useState('');  
  const [uploadSessionId, setUploadSessionId] = useState(null);
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [uploadLoading, setUploadLoading] = useState(false);
  
  const [scenes, setScenes] = useState([]);
  const [scriptLoading, setScriptLoading] = useState(false);
  
  const [status, setStatus] = useState('idle');
  const [progress, setProgress] = useState(0);
  const [jobMessage, setJobMessage] = useState('');
  const [progressLog, setProgressLog] = useState([]);
  const [videoUrl, setVideoUrl] = useState(null);
  const [srtUrl, setSrtUrl] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');

  const audioRef = useRef(null);

  const playPreview = useCallback((type, id) => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    const audioUrl = `${API_BASE}/api/preview/${type}/${id}`;
    const audio = new Audio(audioUrl);
    if (type === 'bgm') {
      audio.volume = bgmVolume / 100;
    }
    audio.play().catch(e => alert("Lỗi phát audio: " + e.message + "\n(Vui lòng tương tác với trang web trước khi nghe hoặc kiểm tra kết nối tới Backend)"));
    audioRef.current = audio;
  }, [bgmVolume]);

  const handleReset = () => {
    setStep('config');
    setScenes([]);
    setStatus('idle');
    setProgress(0);
    setJobMessage('');
    setProgressLog([]);
    setVideoUrl(null);
    setSrtUrl(null);
    setErrorMsg('');
    setUploadSessionId(null);
    setUploadedFiles([]);
  };

  const needsUpload = activeMode === 'img2vid' || activeMode === 'slideshow';
  const needsScript = activeMode === 'script';
  const needsTopic = !needsUpload && !needsScript;

  const contextValue = {
    step, setStep, activeMode, setActiveMode, topic, setTopic, scriptText, setScriptText,
    ratio, setRatio, numScenes, setNumScenes, targetDuration, setTargetDuration,
    narrationTone, setNarrationTone, voice, setVoice, style, setStyle,
    bgm, setBgm, apiKey, setApiKey, showApiKey, setShowApiKey,
    useVeo, setUseVeo, useAnimatedCaptions, setUseAnimatedCaptions, ctaText, setCtaText,
    speechRate, setSpeechRate, speechPitch, setSpeechPitch, bgmVolume, setBgmVolume,
    negativePrompt, setNegativePrompt, characterDescription, setCharacterDescription,
    useFrameChaining, setUseFrameChaining, useKenBurns, setUseKenBurns,
    useBeatSync, setUseBeatSync, useVeoAmbientAudio, setUseVeoAmbientAudio,
    useGpuEncode, setUseGpuEncode, hookZoomBoost, setHookZoomBoost,
    subtitleStyle, setSubtitleStyle, watermarkText, setWatermarkText,
    uploadSessionId, setUploadSessionId, uploadedFiles, setUploadedFiles,
    uploadLoading, setUploadLoading, scenes, setScenes, scriptLoading, setScriptLoading,
    status, setStatus, progress, setProgress, jobMessage, setJobMessage,
    progressLog, setProgressLog, videoUrl, setVideoUrl, srtUrl, setSrtUrl,
    errorMsg, setErrorMsg, playPreview, handleReset,
    needsUpload, needsScript, needsTopic
  };

  return (
    <AppContext.Provider value={contextValue}>
      {children}
    </AppContext.Provider>
  );
};

export const useAppContext = () => useContext(AppContext);

```

### File: `frontend\src\constants.js`
```js
export const API_BASE = 'http://localhost:8000';

export const MODE_MAP = {
  storyteller: 'storyteller',
  img2vid: 'photo_narration',
  slideshow: 'photo_slideshow',
  script: 'script_video',
  quiz: 'quiz_listicle',
};

export const MODES = [
  { id: 'storyteller', icon: '✨', title: 'AI Storyteller', desc: 'Nhập chủ đề → AI viết kịch bản,\nsinh ảnh, render video tự động' },
  { id: 'img2vid', icon: '🖼️', title: 'Ảnh → Video', desc: 'Upload ảnh → AI viết lời bình\nvà kể chuyện cho từng ảnh' },
  { id: 'slideshow', icon: '🎞️', title: 'Slideshow', desc: 'Upload ảnh → Video cinematic\nvới nhạc nền, hiệu ứng' },
  { id: 'script', icon: '📝', title: 'Script → Video', desc: 'Paste script viết sẵn → AI chia\ncảnh, sinh ảnh, đọc lời' },
  { id: 'quiz', icon: '❓', title: 'Quiz / Listicle', desc: 'Chủ đề → AI sinh video dạng\n"Top N" hoặc hỏi-đáp' },
];

export const STYLES = [
  { value: 'Anime illustration, vibrant colors, Studio Ghibli inspired', label: 'Anime (Hoạt hình)' },
  { value: 'Photorealistic, cinematic lighting, 8K UHD', label: 'Realistic (Thực tế)' },
  { value: '3D render, Pixar style, soft lighting, highly detailed', label: '3D Render' },
  { value: 'Cinematic, dramatic lighting, widescreen composition', label: 'Cinematic (Điện ảnh)' },
  { value: 'Watercolor painting, soft brush strokes, artistic', label: 'Watercolor (Màu nước)' },
  { value: 'Cyberpunk 2077 style, neon lights, futuristic city, sci-fi', label: 'Cyberpunk 2077 (Tương lai)' },
  { value: 'Dark Fantasy, gothic, moody lighting, mysterious, highly detailed', label: 'Dark Fantasy (Huyền bí)' },
  { value: 'Vintage 35mm film, grainy, retro aesthetic, warm nostalgic colors', label: 'Vintage Film (Phim cũ)' },
  { value: 'Comic book panel, manga style, heavy shadows, halftone patterns, dramatic angles', label: 'Comic/Manga (Truyện tranh)' },
  { value: 'Hand-drawn Japanese animation, pastel tones, beautiful scenery, nostalgic', label: 'Japanese Animation (Tươi sáng)' },
];

export const VOICES = [
  { value: 'vi-VN-NamMinhNeural', label: 'Nam - Nam Minh' },
  { value: 'vi-VN-HoaiMyNeural', label: 'Nữ - Hoài My' },
  { value: 'vi-VN-AnNiNeural', label: 'Nữ - An Ni (Trẻ trung)' },
  { value: 'vi-VN-PhuongMyNeural', label: 'Nữ - Phương My (Tin tức)' },
  { value: 'minion', label: 'Minion (Nhí nhảnh)' },
  { value: 'minion_pro', label: 'Minion Pro (Hỗn loạn, Cuốn hút)' },
];

export const NARRATION_TONES = [
  { value: 'viral', label: '🔥 Viral Hook', desc: 'Gây sốc, cuốn hút, FOMO' },
  { value: 'educational', label: '📚 Giáo dục', desc: 'Rõ ràng, logic, dẫn chứng' },
  { value: 'emotional', label: '💔 Cảm xúc', desc: 'Storytelling sâu sắc' },
  { value: 'humorous', label: '😂 Hài hước', desc: 'Dí dỏm, bất ngờ' },
];

export const DURATION_OPTIONS = [
  { value: '15s',  label: '15s',  scenes: 4 },
  { value: '30s',  label: '30s',  scenes: 5 },
  { value: '60s',  label: '60s',  scenes: 7 },
  { value: '90s',  label: '90s',  scenes: 9 },
  { value: '120s', label: '2 min', scenes: 12 },
  { value: '180s', label: '3 min', scenes: 16 },
];

```

### File: `frontend\src\index.css`
```css
@import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700;800&display=swap');

:root {
  --bg-main: #111520;
  --bg-panel: #161a27;
  --bg-input: #0b0f19;

  --border-light: rgba(255, 255, 255, 0.06);
  --border-active: #f59e0b;

  --text-primary: #f8fafc;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;

  --amber: #fbb117;
  --amber-hover: #eab308;
  --blue-step: #3b82f6;
  --pink-step: #d946ef;
  --green: #22c55e;
  --red: #ef4444;

  --radius-lg: 14px;
  --radius-md: 8px;
  --radius-sm: 6px;
}

*, *::before, *::after { box-sizing: border-box; }

body {
  margin: 0;
  font-family: 'Be Vietnam Pro', system-ui, -apple-system, sans-serif;
  background-color: var(--bg-main);
  color: var(--text-primary);
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

/* ─── APP WRAPPER ─── */
.app-container {
  max-width: 1300px;
  margin: 0 auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-height: 100vh;
}

/* ─── APP HEADER ─── */
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 0;
}
.app-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 1.15rem;
  font-weight: 800;
  color: var(--amber);
}
.header-steps {
  display: flex;
  align-items: center;
  gap: 8px;
}
.header-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-muted);
  padding: 6px 14px;
  border-radius: 20px;
  transition: all 0.3s;
}
.header-step.active {
  background: rgba(245, 158, 11, 0.12);
  color: var(--amber);
}
.header-step.completed {
  color: var(--green);
}
.header-step-num {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.72rem;
  font-weight: 700;
  background: rgba(255,255,255,0.08);
}
.header-step.active .header-step-num { background: var(--amber); color: #000; }
.header-step.completed .header-step-num { background: var(--green); color: #fff; }
.header-step-arrow { color: var(--text-muted); font-size: 0.85rem; }

/* ─── TOP MODES ─── */
.top-modes {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 8px;
}
.mode-card {
  background: var(--bg-panel);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 16px;
  min-width: 200px;
  flex: 1;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
}
.mode-card.active {
  border-color: var(--border-active);
  background: linear-gradient(180deg, rgba(245, 158, 11, 0.06) 0%, transparent 100%);
  box-shadow: 0 0 0 1px var(--border-active);
}
.mode-card:hover:not(.active) { border-color: rgba(255, 255, 255, 0.15); }
.mode-icon { font-size: 1.5rem; margin-bottom: 6px; }
.mode-title { font-size: 0.9rem; font-weight: 700; margin-bottom: 4px; }
.mode-desc { font-size: 0.72rem; color: var(--text-secondary); line-height: 1.4; }

/* ─── MAIN GRID ─── */
.main-grid {
  display: grid;
  grid-template-columns: 420px 1fr;
  gap: 24px;
  align-items: start;
}

/* ─── CONTROL PANEL ─── */
.control-panel {
  background: var(--bg-panel);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}
.divider { height: 1px; background: var(--border-light); margin: 0 -24px; }

/* ─── STEP HEADER ─── */
.step-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.step-badge {
  width: 26px; height: 26px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 0.85rem; font-weight: 700; flex-shrink: 0;
}
.step-1 { background: rgba(59, 130, 246, 0.15); color: var(--blue-step); }
.step-2 { background: rgba(217, 70, 239, 0.15); color: var(--pink-step); }
.step-title { font-size: 1.05rem; font-weight: 700; }

/* ─── FORM ELEMENTS ─── */
.field-label {
  display: block; font-size: 0.72rem; font-weight: 700;
  color: var(--text-secondary); text-transform: uppercase;
  letter-spacing: 0.5px; margin-bottom: 10px;
}
.form-textarea, .form-input {
  width: 100%;
  background: var(--bg-input);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  padding: 12px 14px;
  color: var(--text-primary);
  font-family: inherit;
  font-size: 0.88rem;
  resize: none;
  outline: none;
  transition: border-color 0.2s;
}
.form-textarea { min-height: 100px; }
.form-input { min-height: auto; }
.form-textarea:focus, .form-input:focus { border-color: rgba(255, 255, 255, 0.2); }
.form-textarea::placeholder, .form-input::placeholder { color: var(--text-muted); }

.form-select {
  width: 100%; background: var(--bg-input);
  border: 1px solid var(--border-light); border-radius: var(--radius-md);
  padding: 10px 14px; color: var(--text-primary);
  font-family: inherit; font-size: 0.85rem; outline: none;
  appearance: none; cursor: pointer;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 12px center;
}

/* ─── RATIO BUTTONS ─── */
.ratio-group { display: flex; gap: 8px; }
.ratio-btn {
  flex: 1; background: var(--bg-input);
  border: 1px solid var(--border-light); border-radius: var(--radius-md);
  padding: 10px 0; display: flex; align-items: center; justify-content: center;
  gap: 6px; font-size: 0.78rem; color: var(--text-secondary);
  cursor: pointer; transition: all 0.2s;
}
.ratio-btn.active { background: rgba(245, 158, 11, 0.1); border-color: var(--amber); color: var(--amber); }

/* ─── SLIDER ─── */
.slider-container { display: flex; flex-direction: column; gap: 8px; }
.slider-header { display: flex; align-items: center; gap: 8px; }
.slider-value { color: var(--amber); font-weight: 700; font-size: 1rem; }
.slider-labels { display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--text-muted); font-weight: 600; }
.slider-hint { font-size: 0.75rem; color: var(--text-muted); }

/* ─── SETTINGS GRID ─── */
.settings-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }

/* ─── ADVANCED BOX ─── */
.advanced-box {
  padding: 16px; background: rgba(255,255,255,0.02);
  border-radius: 12px; border: 1px solid var(--border-light);
}
.advanced-title { font-size: 0.78rem; font-weight: 700; color: var(--text-secondary); margin-bottom: 12px; }
.checkbox-row {
  display: flex; align-items: center; gap: 8px;
  cursor: pointer; margin-bottom: 10px; font-size: 0.84rem;
}
.checkbox-row input[type="checkbox"] { accent-color: var(--amber); }

/* ─── API KEY ─── */
.api-key-box { border-radius: var(--radius-md); }
.api-key-header {
  display: flex; align-items: center; gap: 8px;
  font-size: 0.8rem; color: var(--text-muted); cursor: pointer;
  padding: 8px 0; transition: color 0.2s;
}
.api-key-header:hover { color: var(--text-secondary); }

/* ─── UPLOAD ZONE ─── */
.upload-zone { margin-top: 8px; }
.upload-placeholder {
  border: 2px dashed rgba(255,255,255,0.1);
  border-radius: var(--radius-lg);
  padding: 32px;
  text-align: center;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.2s;
}
.upload-placeholder:hover { border-color: var(--amber); color: var(--text-secondary); }
.upload-placeholder p { margin: 12px 0 4px; font-weight: 600; }
.upload-placeholder span { font-size: 0.75rem; }
.upload-done {
  display: flex; align-items: center; gap: 10px;
  padding: 14px 16px; background: rgba(34,197,94,0.08);
  border: 1px solid rgba(34,197,94,0.2); border-radius: var(--radius-md);
  font-size: 0.88rem; color: var(--green);
}
.upload-loading { margin-top: 8px; font-size: 0.82rem; color: var(--amber); }

/* ─── BUTTONS ─── */
.btn-generate {
  width: 100%; background: var(--amber); color: #000; border: none;
  border-radius: var(--radius-md); padding: 14px; font-size: 0.92rem;
  font-weight: 800; display: flex; align-items: center; justify-content: center;
  gap: 8px; cursor: pointer; transition: 0.2s; margin-top: 8px;
}
.btn-generate:hover:not(:disabled) { background: var(--amber-hover); transform: translateY(-1px); }
.btn-generate:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-loading { display: flex; align-items: center; gap: 8px; }

.btn-outline {
  background: transparent; border: 1px solid var(--border-light);
  border-radius: var(--radius-md); padding: 8px 16px;
  color: var(--text-secondary); font-size: 0.82rem; font-weight: 600;
  display: flex; align-items: center; gap: 6px; cursor: pointer; transition: 0.2s;
}
.btn-outline:hover { background: rgba(255,255,255,0.05); border-color: rgba(255,255,255,0.15); }

.btn-icon {
  background: none; border: 1px solid transparent; border-radius: 6px;
  padding: 4px 6px; color: var(--text-muted); cursor: pointer; transition: all 0.15s;
}
.btn-icon:hover { background: rgba(255,255,255,0.08); color: var(--text-secondary); }
.btn-icon:disabled { opacity: 0.3; cursor: not-allowed; }
.btn-icon.btn-danger:hover { background: rgba(239,68,68,0.12); color: var(--red); }

.error-box {
  background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: var(--radius-md); padding: 12px 16px; color: #fca5a5;
  font-size: 0.84rem; display: flex; align-items: flex-start; gap: 8px; line-height: 1.5;
}

/* ─── SPINNER ─── */
.spinner {
  width: 16px; height: 16px;
  border: 2px solid rgba(0,0,0,0.2); border-top-color: #000;
  border-radius: 50%; animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ─── PREVIEW PANEL ─── */
.preview-panel {
  background: var(--bg-panel); border: 1px solid var(--border-light);
  border-radius: var(--radius-lg); min-height: 600px;
  display: flex; flex-direction: column; position: relative; overflow: hidden;
}
.preview-panel::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, transparent, rgba(59,130,246,0.5), rgba(217,70,239,0.5), transparent);
}

/* ═══════════════════════════════════════════════════════════ */
/* SCRIPT EDITOR */
/* ═══════════════════════════════════════════════════════════ */
.editor-layout { display: flex; flex-direction: column; gap: 16px; }

.editor-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  gap: 16px; padding: 16px 20px;
  background: var(--bg-panel); border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
}
.editor-toolbar-info {
  display: flex; align-items: center; gap: 8px;
  font-size: 0.85rem; color: var(--text-secondary); font-weight: 600;
}

.scene-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 16px;
}

.scene-card {
  background: var(--bg-panel);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  overflow: hidden;
  transition: border-color 0.2s;
}
.scene-card:hover { border-color: rgba(255,255,255,0.12); }

.scene-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px;
  background: rgba(255,255,255,0.02);
  border-bottom: 1px solid var(--border-light);
}
.scene-number {
  font-size: 0.82rem; font-weight: 700; color: var(--amber);
}
.scene-actions { display: flex; gap: 4px; }

.scene-fields { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.scene-field { }
.scene-textarea { min-height: 60px; font-size: 0.84rem; }

.btn-add-scene {
  width: 100%; background: transparent;
  border: 2px dashed rgba(255,255,255,0.08);
  border-radius: var(--radius-lg);
  padding: 14px; font-size: 0.85rem; font-weight: 600;
  color: var(--text-muted); display: flex; align-items: center; justify-content: center;
  gap: 8px; cursor: pointer; transition: all 0.2s;
}
.btn-add-scene:hover { border-color: var(--amber); color: var(--amber); }

/* ═══════════════════════════════════════════════════════════ */
/* RENDER PANEL */
/* ═══════════════════════════════════════════════════════════ */
.render-panel {
  background: var(--bg-panel);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  min-height: 500px;
  display: flex; flex-direction: column;
}
.render-center {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  padding: 48px 40px; text-align: center;
}
.render-message { color: var(--text-secondary); font-size: 0.9rem; margin-bottom: 24px; }

.progress-bar-container {
  width: 100%; max-width: 400px; height: 8px;
  background: rgba(255,255,255,0.08); border-radius: 4px; overflow: hidden;
}
.progress-bar-fill {
  height: 100%; background: linear-gradient(90deg, var(--amber), #f97316);
  transition: width 0.4s ease; border-radius: 4px;
}
.progress-percent { margin-top: 8px; font-size: 0.88rem; color: var(--amber); font-weight: 700; }

.progress-log {
  margin-top: 24px; width: 100%; max-width: 500px;
  max-height: 200px; overflow-y: auto;
  display: flex; flex-direction: column; gap: 6px;
  text-align: left;
}
.progress-log-item {
  display: flex; align-items: center; gap: 8px;
  font-size: 0.78rem; color: var(--text-secondary);
  padding: 4px 0;
}

/* ═══════════════════════════════════════════════════════════ */
/* DONE PANEL */
/* ═══════════════════════════════════════════════════════════ */
.done-panel {
  background: var(--bg-panel);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 24px;
  display: flex; flex-direction: column; gap: 20px;
}
.done-video-wrap {
  background: #000; border-radius: 12px;
  overflow: hidden; aspect-ratio: 16/9; max-height: 70vh;
}
.done-actions {
  display: flex; gap: 12px; flex-wrap: wrap; align-items: center;
}

/* ─── RESPONSIVE ─── */
@media (max-width: 900px) {
  .main-grid { grid-template-columns: 1fr; }
  .top-modes { flex-wrap: nowrap; }
  .mode-card { min-width: 160px; }
  .scene-list { grid-template-columns: 1fr; }
  .editor-toolbar { flex-direction: column; gap: 12px; }
  .done-actions { flex-direction: column; }
  .done-actions .btn-generate, .done-actions .btn-outline { width: 100%; }
  .header-steps { display: none; }
}

```

### File: `frontend\src\main.jsx`
```jsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { AppProvider } from './AppContext.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AppProvider>
      <App />
    </AppProvider>
  </StrictMode>,
)

```

### File: `frontend\src\components\RenderProgress.jsx`
```jsx
import React from 'react';
import { AlertTriangle, RotateCcw, Check, Download, PenLine } from 'lucide-react';
import { useAppContext } from '../AppContext';

export default function RenderProgress() {
  const ctx = useAppContext();

  if (ctx.step === 'done') {
    return (
      <div className="done-panel">
        <div className="done-video-wrap">
          <video src={ctx.videoUrl} controls autoPlay style={{ width: '100%', height: '100%', objectFit: 'contain', borderRadius: 12 }} />
        </div>
        <div className="done-actions">
          <a href={ctx.videoUrl} download className="btn-generate" style={{ flex: 1, textAlign: 'center', textDecoration: 'none' }}>
            <Download size={18} /> Tải Video MP4
          </a>
          {ctx.srtUrl && (
            <a href={ctx.srtUrl} download className="btn-outline" style={{ textDecoration: 'none' }}>
              <Download size={14} /> Tải Phụ đề (.srt)
            </a>
          )}
          <button className="btn-outline" onClick={ctx.handleReset}>
            <RotateCcw size={14} /> Tạo Video Mới
          </button>
          <button className="btn-outline" onClick={() => ctx.setStep('editor')}>
            <PenLine size={14} /> Chỉnh sửa & Render lại
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="render-panel">
      <div className="render-center">
        <div style={{ fontSize: 56, marginBottom: 20 }}>🎬</div>
        <h2 style={{ marginBottom: 8 }}>Đang sản xuất video</h2>
        <p className="render-message">{ctx.jobMessage}</p>

        <div className="progress-bar-container">
          <div className="progress-bar-fill" style={{ width: `${ctx.progress}%` }} />
        </div>
        <div className="progress-percent">{ctx.progress}%</div>

        <div className="progress-log">
          {ctx.progressLog.map((msg, i) => (
            <div key={i} className="progress-log-item">
              <Check size={12} style={{ color: 'var(--green)', flexShrink: 0 }} />
              <span>{msg}</span>
            </div>
          ))}
        </div>
      </div>

      {ctx.errorMsg && (
        <div style={{ padding: '0 40px 24px' }}>
          <div className="error-box">
            <AlertTriangle size={16} /> {ctx.errorMsg}
          </div>
          <button className="btn-outline" style={{ marginTop: 12 }} onClick={() => { ctx.setStep('editor'); ctx.setErrorMsg(''); ctx.setStatus('idle'); }}>
            <RotateCcw size={14} /> Quay lại chỉnh sửa
          </button>
        </div>
      )}
    </div>
  );
}

```

### File: `frontend\src\components\ScriptEditor.jsx`
```jsx
import React from 'react';
import { RotateCcw, PenLine, Play, AlertTriangle, ChevronUp, ChevronDown, Trash2, Plus } from 'lucide-react';
import { useAppContext } from '../AppContext';
import { API_BASE, MODE_MAP } from '../constants';

export default function ScriptEditor() {
  const ctx = useAppContext();

  const handleRenderVideo = async () => {
    if (!ctx.scenes.length) return ctx.setErrorMsg('Chưa có cảnh nào để render!');
    ctx.setErrorMsg('');
    ctx.setStep('rendering');
    ctx.setStatus('loading');
    ctx.setProgress(0);
    ctx.setJobMessage('Đang khởi tạo...');
    ctx.setProgressLog([]);
    ctx.setVideoUrl(null);
    ctx.setSrtUrl(null);

    try {
      const payload = {
        scenes: ctx.scenes, mode: MODE_MAP[ctx.activeMode], aspect_ratio: ctx.ratio, voice: ctx.voice,
        bgm_track: ctx.bgm === 'none' ? null : ctx.bgm, upload_session_id: ctx.uploadSessionId || undefined,
        speech_rate: ctx.speechRate, speech_pitch: ctx.speechPitch, bgm_volume: ctx.bgmVolume / 100,
        negative_prompt: ctx.negativePrompt || undefined, gemini_api_key: ctx.apiKey || undefined,
        use_veo: ctx.useVeo, cta_text: ctx.ctaText || undefined, use_animated_captions: ctx.useAnimatedCaptions,
        character_description: ctx.characterDescription || undefined, use_frame_chaining: ctx.useFrameChaining,
        use_ken_burns: ctx.useKenBurns, use_beat_sync: ctx.useBeatSync, use_veo_ambient_audio: ctx.useVeoAmbientAudio,
        use_gpu_encode: ctx.useGpuEncode, hook_zoom_boost: ctx.hookZoomBoost,
        subtitle_style: ctx.subtitleStyle, watermark_text: ctx.watermarkText || undefined,
      };

      const res = await fetch(`${API_BASE}/api/render-video`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Lỗi server');
      }

      const data = await res.json();
      const jobId = data.job_id;

      const ws = new WebSocket(`ws://localhost:8000/api/ws/job-status/${jobId}`);

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.progress !== undefined) ctx.setProgress(msg.progress);
        if (msg.message) {
          ctx.setJobMessage(msg.message);
          ctx.setProgressLog(prev => {
            const last = prev[prev.length - 1];
            if (last === msg.message) return prev;
            return [...prev, msg.message];
          });
        }
        if (msg.status === 'done') {
          ws.close();
          ctx.setStatus('done');
          ctx.setStep('done');
          if (msg.video_url) ctx.setVideoUrl(`${API_BASE}${msg.video_url}`);
          if (msg.srt_url) ctx.setSrtUrl(`${API_BASE}${msg.srt_url}`);
        } else if (msg.status === 'error') {
          ws.close();
          ctx.setStatus('error');
          ctx.setStep('rendering');
          ctx.setErrorMsg(msg.error || msg.message || 'Có lỗi xảy ra');
        }
      };

      ws.onerror = () => {
        ctx.setStatus('error');
        ctx.setErrorMsg('Mất kết nối WebSocket với máy chủ!');
      };
    } catch (err) {
      ctx.setStatus('error');
      ctx.setErrorMsg(err.message);
    }
  };

  const updateScene = (index, field, value) => {
    ctx.setScenes(prev => prev.map((s, i) => i === index ? { ...s, [field]: value } : s));
  };
  const removeScene = (index) => {
    ctx.setScenes(prev => prev.filter((_, i) => i !== index).map((s, i) => ({ ...s, scene: i + 1 })));
  };
  const addScene = () => {
    ctx.setScenes(prev => [...prev, { scene: prev.length + 1, text: '', image_prompt: '' }]);
  };
  const moveScene = (from, to) => {
    if (to < 0 || to >= ctx.scenes.length) return;
    ctx.setScenes(prev => {
      const arr = [...prev];
      const [item] = arr.splice(from, 1);
      arr.splice(to, 0, item);
      return arr.map((s, i) => ({ ...s, scene: i + 1 }));
    });
  };

  return (
    <div className="editor-layout">
      <div className="editor-toolbar">
        <button className="btn-outline" onClick={() => ctx.setStep('config')}><RotateCcw size={14} /> Quay lại cài đặt</button>
        <div className="editor-toolbar-info"><PenLine size={14} /> {ctx.scenes.length} cảnh — Chỉnh sửa lời thoại & mô tả ảnh bên dưới</div>
        <button className="btn-generate" style={{ width: 'auto', padding: '10px 24px', marginTop: 0 }} onClick={handleRenderVideo}><Play size={16} /> Render Video (Bước 2)</button>
      </div>

      {ctx.errorMsg && <div className="error-box" style={{ marginBottom: 16 }}><AlertTriangle size={16} /> {ctx.errorMsg}</div>}

      <div className="scene-list">
        {ctx.scenes.map((scene, idx) => (
          <div key={idx} className="scene-card">
            <div className="scene-header">
              <div className="scene-number">Cảnh {idx + 1}</div>
              <div className="scene-actions">
                <button className="btn-icon" onClick={() => moveScene(idx, idx - 1)} disabled={idx === 0} title="Di chuyển lên"><ChevronUp size={14} /></button>
                <button className="btn-icon" onClick={() => moveScene(idx, idx + 1)} disabled={idx === ctx.scenes.length - 1} title="Di chuyển xuống"><ChevronDown size={14} /></button>
                <button className="btn-icon btn-danger" onClick={() => removeScene(idx)} title="Xóa cảnh" disabled={ctx.scenes.length <= 1}><Trash2 size={14} /></button>
              </div>
            </div>
            <div className="scene-fields">
              <div className="scene-field">
                <label className="field-label">LỜI THOẠI (TIẾNG VIỆT) {scene.text?.includes('<break') && <span style={{ fontSize: 11, color: 'var(--amber)', fontWeight: 400, marginLeft: 8 }}>⏸ Có ngắt nghỉ cảm xúc</span>}</label>
                <textarea className="form-textarea scene-textarea" value={scene.text} onChange={e => updateScene(idx, 'text', e.target.value)} placeholder="Lời thoại sẽ được đọc bằng TTS..." rows={3} />
              </div>
              <div className="scene-field">
                <label className="field-label">MÔ TẢ HÌNH ẢNH (TIẾNG ANH)</label>
                <textarea className="form-textarea scene-textarea" value={scene.image_prompt} onChange={e => updateScene(idx, 'image_prompt', e.target.value)} placeholder="Image prompt for AI image generation..." rows={2} />
              </div>
            </div>
          </div>
        ))}
      </div>
      <button className="btn-add-scene" onClick={addScene}><Plus size={16} /> Thêm cảnh mới</button>
    </div>
  );
}

```

### File: `frontend\src\components\SettingsPanel.jsx`
```jsx
import React, { useRef } from 'react';
import { Smartphone, Monitor, Square, AlertTriangle, ChevronDown, ChevronUp, Upload, X, Play, Sparkles, Key } from 'lucide-react';
import { STYLES, VOICES, API_BASE, MODE_MAP, NARRATION_TONES, DURATION_OPTIONS } from '../constants';
import { useAppContext } from '../AppContext';

export default function SettingsPanel() {
  const ctx = useAppContext();
  const fileInputRef = useRef(null);

  const handleUpload = async (e) => {
    const files = Array.from(e.target.files);
    if (!files.length) return;
    ctx.setUploadLoading(true);
    ctx.setErrorMsg('');
    const formData = new FormData();
    files.forEach(f => formData.append('images', f));
    try {
      const res = await fetch(`${API_BASE}/api/upload-images`, { method: 'POST', body: formData });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Upload lỗi');
      }
      const data = await res.json();
      ctx.setUploadSessionId(data.session_id);
      ctx.setUploadedFiles(files.map(f => f.name));
      ctx.setNumScenes(files.length);
    } catch (err) {
      ctx.setErrorMsg(err.message);
    } finally {
      ctx.setUploadLoading(false);
    }
  };

  const handleGenerateScript = async () => {
    if (ctx.needsTopic && !ctx.topic.trim()) return ctx.setErrorMsg('Vui lòng nhập chủ đề video!');
    if (ctx.needsScript && !ctx.scriptText.trim()) return ctx.setErrorMsg('Vui lòng nhập nội dung kịch bản!');
    if (ctx.needsUpload && !ctx.uploadSessionId) return ctx.setErrorMsg('Vui lòng upload ảnh trước!');
    ctx.setErrorMsg('');
    ctx.setScriptLoading(true);
    try {
      const payload = {
        topic: ctx.topic, mode: MODE_MAP[ctx.activeMode], num_scenes: ctx.numScenes, art_style: ctx.style,
        target_duration: ctx.targetDuration, narration_tone: ctx.narrationTone,
        script_text: ctx.scriptText || undefined, upload_session_id: ctx.uploadSessionId || undefined,
        gemini_api_key: ctx.apiKey || undefined, character_description: ctx.characterDescription || undefined,
      };
      const res = await fetch(`${API_BASE}/api/generate-script`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Lỗi sinh kịch bản');
      }
      const data = await res.json();
      ctx.setScenes(data.scenes || []);
      ctx.setStep('editor');
    } catch (err) {
      ctx.setErrorMsg(err.message);
    } finally {
      ctx.setScriptLoading(false);
    }
  };

  const minScenes = 4, maxScenes = 20;
  const sliderPercent = ((ctx.numScenes - minScenes) / (maxScenes - minScenes)) * 100;

  return (
    <div className="main-grid">
      <div className="control-panel">
        <div>
          <div className="step-header">
            <div className="step-badge step-1">1</div>
            <span className="step-title">{ctx.needsUpload ? 'Upload Ảnh' : ctx.needsScript ? 'Nhập Kịch bản' : 'Ý Tưởng / Chủ Đề'}</span>
          </div>
          {ctx.needsTopic && (
            <>
              <label className="field-label">CHỦ ĐỀ VIDEO</label>
              <textarea className="form-textarea" value={ctx.topic} onChange={e => ctx.setTopic(e.target.value)} placeholder="VD: 5 sự thật thú vị về vũ trụ mà bạn chưa biết..." rows={4} />
            </>
          )}
          {ctx.activeMode === 'storyteller' && (
            <div style={{ marginTop: 16 }}>
              <label className="field-label">MÔ TẢ NHÂN VẬT (CHARACTER REFERENCE)</label>
              <textarea className="form-textarea" value={ctx.characterDescription} onChange={e => ctx.setCharacterDescription(e.target.value)} placeholder="VD: Cô gái tóc ngắn đen..." rows={2} />
            </div>
          )}
          {ctx.needsScript && (
            <>
              <label className="field-label">KỊCH BẢN CỦA BẠN</label>
              <textarea className="form-textarea" value={ctx.scriptText} onChange={e => ctx.setScriptText(e.target.value)} placeholder="Paste toàn bộ script vào đây..." rows={6} style={{ minHeight: 160 }} />
            </>
          )}
          {ctx.needsUpload && (
            <div className="upload-zone">
              <input ref={fileInputRef} type="file" multiple accept="image/jpeg,image/png,image/webp" onChange={handleUpload} style={{ display: 'none' }} />
              {ctx.uploadedFiles.length === 0 ? (
                <div className="upload-placeholder" onClick={() => fileInputRef.current?.click()}>
                  <Upload size={32} />
                  <p>Nhấn để chọn ảnh (JPG, PNG, WebP)</p>
                  <span>Tối đa 20 ảnh, mỗi ảnh ≤ 10MB</span>
                </div>
              ) : (
                <div className="upload-done">
                  <span>Đã upload {ctx.uploadedFiles.length} ảnh</span>
                  <button className="btn-icon" onClick={() => { ctx.setUploadedFiles([]); ctx.setUploadSessionId(null); }}><X size={16} /></button>
                </div>
              )}
              {ctx.uploadLoading && <div className="upload-loading">Đang upload...</div>}
            </div>
          )}
        </div>
        <div className="divider" />
        <div>
          <div className="step-header">
            <div className="step-badge step-2">2</div>
            <span className="step-title">Cài đặt</span>
          </div>
          <div style={{ marginBottom: 24 }}>
            <label className="field-label">TỈ LỆ KHUNG HÌNH</label>
            <div className="ratio-group">
              {[{ v: '9:16', icon: <Smartphone size={14} />, label: '9:16 Dọc' }, { v: '16:9', icon: <Monitor size={14} />, label: '16:9 Ngang' }, { v: '1:1', icon: <Square size={14} />, label: '1:1 Vuông' }].map(r => (
                <button key={r.v} className={`ratio-btn ${ctx.ratio === r.v ? 'active' : ''}`} onClick={() => ctx.setRatio(r.v)}>{r.icon} {r.label}</button>
              ))}
            </div>
          </div>
          {!ctx.needsUpload && (
            <>
              <div style={{ marginBottom: 24 }}>
                <div className="slider-header">
                  <label className="field-label" style={{ marginBottom: 0 }}>SỐ CẢNH:</label><span className="slider-value">{ctx.numScenes}</span>
                </div>
                <div className="slider-container">
                  <div style={{ position: 'relative', height: 24, display: 'flex', alignItems: 'center' }}>
                    <input type="range" min={minScenes} max={maxScenes} value={ctx.numScenes} onChange={e => ctx.setNumScenes(Number(e.target.value))} style={{ position: 'absolute', width: '100%', opacity: 0, zIndex: 10, cursor: 'pointer', height: '100%' }} />
                    <div style={{ width: '100%', height: 4, background: 'rgba(255,255,255,0.1)', borderRadius: 2, position: 'relative' }}>
                      <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${sliderPercent}%`, background: 'var(--amber)', borderRadius: 2 }} />
                      <div style={{ position: 'absolute', left: `${sliderPercent}%`, top: '50%', transform: 'translate(-50%, -50%)', width: 16, height: 16, background: 'var(--amber)', borderRadius: '50%', boxShadow: '0 0 0 4px rgba(245, 158, 11, 0.2)' }} />
                    </div>
                  </div>
                </div>
              </div>
              
              <div style={{ marginBottom: 24 }}>
                <label className="field-label">THỜI LƯỢNG DỰ KIẾN</label>
                <div className="ratio-group" style={{ flexWrap: 'wrap' }}>
                  {DURATION_OPTIONS.map(d => (
                    <button key={d.value} className={`ratio-btn ${ctx.targetDuration === d.value ? 'active' : ''}`}
                      onClick={() => { ctx.setTargetDuration(d.value); ctx.setNumScenes(d.scenes); }}
                    >{d.label}</button>
                  ))}
                </div>
              </div>

              <div style={{ marginBottom: 24 }}>
                <label className="field-label">PHONG CÁCH KỂ CHUYỆN</label>
                <div className="ratio-group" style={{ flexWrap: 'wrap' }}>
                  {NARRATION_TONES.map(t => (
                    <button key={t.value}
                      className={`ratio-btn ${ctx.narrationTone === t.value ? 'active' : ''}`}
                      onClick={() => ctx.setNarrationTone(t.value)}
                      title={t.desc}
                    >{t.label}</button>
                  ))}
                </div>
              </div>
            </>
          )}
          <div className="settings-grid">
            <div>
              <label className="field-label">GIỌNG ĐỌC</label>
              <div style={{ display: 'flex', gap: 8 }}>
                <select className="form-select" value={ctx.voice} onChange={e => ctx.setVoice(e.target.value)} style={{ flex: 1 }}>
                  {VOICES.map(v => <option key={v.value} value={v.value}>{v.label}</option>)}
                </select>
                <button className="btn-icon" onClick={() => ctx.playPreview('voice', ctx.voice)}><Play size={18} /></button>
              </div>
            </div>
            <div>
              <label className="field-label">PHONG CÁCH ẢNH</label>
              <select className="form-select" value={ctx.style} onChange={e => ctx.setStyle(e.target.value)}>
                {STYLES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
            </div>
          </div>
          <div style={{ marginBottom: 20 }}>
            <label className="field-label">♬ NHẠC NỀN</label>
            <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
              <select className="form-select" value={ctx.bgm} onChange={e => ctx.setBgm(e.target.value)} style={{ flex: 1 }}>
                <option value="none">Không dùng nhạc nền</option>
                <option value="afro_pop">Afro Pop</option>
                <option value="comedy_cartoon">Comedy Cartoon</option>
                <option value="deep_abstract_ambient">Deep Abstract Ambient</option>
                <option value="hype_drill">Hype Drill</option>
                <option value="lofi_jazzy_love">Lo-Fi Jazzy Love</option>
                <option value="moment_of_peace">Moment Of Peace</option>
                <option value="music_promotion">Music Promotion</option>
                <option value="new_age_nature">New Age Nature</option>
                <option value="no_sleep_hiphop">No Sleep Hip-Hop</option>
                <option value="rap_beat">Rap Beat</option>
                <option value="running_night">Running Night</option>
                <option value="type_beat">Type Beat</option>
              </select>
              {ctx.bgm !== 'none' && <button className="btn-icon" onClick={() => ctx.playPreview('bgm', ctx.bgm)}><Play size={18} /></button>}
              {ctx.bgm !== 'none' && <input type="range" min="0" max="100" value={ctx.bgmVolume} onChange={e => ctx.setBgmVolume(Number(e.target.value))} style={{ width: 80 }} />}
            </div>
          </div>
          <div className="advanced-box">
            <div className="advanced-title">⚡ Tùy chọn nâng cao</div>
            <label className="checkbox-row"><input type="checkbox" checked={ctx.useVeo} onChange={e => ctx.setUseVeo(e.target.checked)} /><span>Dùng <b>Veo 3</b> biến ảnh → video clip động</span></label>
            <label className="checkbox-row"><input type="checkbox" checked={ctx.useFrameChaining} onChange={e => ctx.setUseFrameChaining(e.target.checked)} /><span>Nối cảnh mượt (Frame Chaining)</span></label>
            <label className="checkbox-row"><input type="checkbox" checked={ctx.useBeatSync} onChange={e => ctx.setUseBeatSync(e.target.checked)} /><span>Đồng bộ theo nhịp nhạc (Beat Sync)</span></label>
            <label className="checkbox-row"><input type="checkbox" checked={ctx.useKenBurns} onChange={e => ctx.setUseKenBurns(e.target.checked)} /><span>Hiệu ứng Ken Burns (Ảnh tĩnh)</span></label>
            <div style={{ marginTop: 12, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', marginBottom: 4, display: 'block' }}>KIỂU PHỤ ĐỀ</label>
                <select className="form-select" value={ctx.subtitleStyle} onChange={e => ctx.setSubtitleStyle(e.target.value)} style={{ padding: '6px 10px', fontSize: 13 }}>
                  <option value="karaoke_bold">Karaoke Nhịp điệu (Viền đen)</option>
                  <option value="cinematic_box">Điện ảnh (Nền mờ)</option>
                </select>
              </div>
              <div>
                <label style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', marginBottom: 4, display: 'block' }}>ĐÓNG DẤU (WATERMARK)</label>
                <input type="text" className="form-input" value={ctx.watermarkText} onChange={e => ctx.setWatermarkText(e.target.value)} placeholder="VD: @username" style={{ padding: '6px 10px', fontSize: 13 }} />
              </div>
            </div>
          </div>
        </div>
        <div style={{ marginTop: 'auto', paddingTop: 20 }}>
          <button className="btn-generate" onClick={handleGenerateScript} disabled={ctx.scriptLoading}>
            {ctx.scriptLoading ? <span className="btn-loading"><div className="spinner" /> Đang sinh kịch bản...</span> : <><Sparkles size={18} /> Sinh Kịch Bản (Bước 1)</>}
          </button>
          {ctx.errorMsg && <div className="error-box" style={{ marginTop: 16 }}><AlertTriangle size={16} /> {ctx.errorMsg}</div>}
        </div>
      </div>
      <div className="preview-panel" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ textAlign: 'center', color: 'rgba(255,255,255,0.35)', padding: 40 }}>
          <Sparkles size={48} style={{ opacity: 0.4, marginBottom: 16 }} />
          <h3 style={{ marginBottom: 8, fontWeight: 600 }}>Bước 1: Sinh Kịch Bản</h3>
          <p style={{ fontSize: 14, lineHeight: 1.6 }}>Nhập ý tưởng bên trái và nhấn <b>"Sinh Kịch Bản"</b>.<br />AI sẽ viết kịch bản để bạn xem và chỉnh sửa<br />trước khi render video.</p>
        </div>
      </div>
    </div>
  );
}

```

### File: `tester\extract_frames.py`
```py
import subprocess, os, sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

ffmpeg = r'C:\dev\AI-VIDEO-MAKER\backend\venv\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe'
video = r'C:\dev\AI-VIDEO-MAKER\tester\Download.mp4'
out_dir = r'C:\dev\AI-VIDEO-MAKER\tester\frames'
os.makedirs(out_dir, exist_ok=True)

timestamps = ['00:00:02', '00:00:10', '00:00:25', '00:00:45', '00:01:10', '00:01:35', '00:02:00', '00:02:30', '00:03:00', '00:03:20']
for i, ts in enumerate(timestamps):
    safe_ts = ts.replace(':', '')
    out_path = os.path.join(out_dir, f'frame_{i+1:02d}_{safe_ts}.png')
    subprocess.run([ffmpeg, '-y', '-ss', ts, '-i', video, '-vframes', '1', '-q:v', '2', out_path], capture_output=True, text=True)
    exists = os.path.exists(out_path)
    sz = os.path.getsize(out_path) if exists else 0
    print(f'{ts}: {"OK" if exists else "FAIL"} ({sz} bytes)')
print('Done')

```

