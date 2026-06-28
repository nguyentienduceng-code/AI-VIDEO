# Bối cảnh mã nguồn - AI Video Maker

Tài liệu này tổng hợp toàn bộ cấu trúc thư mục và mã nguồn của dự án AI Video Maker. Bạn hãy đọc nó để nắm rõ ngữ cảnh trước khi đưa ra bất kỳ giải pháp hay đoạn mã nào.

## 1. Cấu trúc thư mục
```text
AI-VIDEO-MAKER/
├── .gitignore
├── AI_CONTEXT.md
├── ARCHITECTURE.md
├── backend
│   ├── .env
│   ├── .env.example
│   ├── main.py
│   ├── requirements.txt
│   └── services
│       ├── gemini_service.py
│       ├── tts_service.py
│       └── video_service.py
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
│   │   ├── index.css
│   │   └── main.jsx
│   ├── tailwind.config.js
│   └── vite.config.js
├── start.bat
├── status.json
└── stop.bat
```

## 2. Toàn bộ Mã Nguồn (Source Code)

### File: `ARCHITECTURE.md`
```md
# KIẾN TRÚC & CƠ CHẾ HOẠT ĐỘNG: AI VIDEO STUDIO

Tài liệu này mô tả chi tiết cơ cấu, luồng hoạt động và các thành phần kỹ thuật của hệ thống sinh video tự động AI Video Maker, phục vụ cho việc kiểm soát, bảo trì và phát triển tính năng về sau.

---

## 1. Tổng quan Hệ thống (System Overview)

Hệ thống được thiết kế theo kiến trúc Client-Server:
- **Frontend (React + Vite):** Giao diện người dùng đơn trang (SPA) cho phép nhập ý tưởng kịch bản, cấu hình API Key và xem trực tiếp trạng thái tiến trình xử lý cũng như kết quả video.
- **Backend (FastAPI - Python):** Xử lý logic lõi, điều phối các luồng gọi API bên ngoài (LLM, TTS) và tiến hành render video tự động thông qua công cụ MoviePy.
- **Communication:** Giao tiếp qua REST API tại endpoint `/api/generate-video` với định dạng dữ liệu trao đổi là JSON.

---

## 2. Luồng xử lý cốt lõi (Main Workflow)

Quy trình từ ý tưởng thành video hoàn chỉnh diễn ra hoàn toàn tự động qua 4 bước:

### Bước 1: Tiếp nhận yêu cầu (Frontend → Backend)
- Người dùng nhập *Chủ đề (Topic)* và tuỳ chọn *Gemini API Key* vào giao diện.
- Payload được gửi qua HTTP POST tới `http://localhost:8000/api/generate-video`.

### Bước 2: Sinh Kịch bản & Phân cảnh (Gemini Service)
- Dịch vụ `gemini_service.py` gọi **Gemini 1.5 Pro**.
- Hệ thống phân tích chủ đề và trả về 1 mảng JSON chứa 4 phân cảnh.
- Mỗi phân cảnh gồm: số thứ tự cảnh (`scene`), lời thoại (`text`) và mô tả hình ảnh tiếng Anh (`image_prompt`).

### Bước 3: Tạo Âm thanh & Hình ảnh (TTS Service)
- Dịch vụ `tts_service.py` dùng thư viện **Edge-TTS** (Microsoft) để tổng hợp giọng nói Tiếng Việt (mặc định nữ: `vi-VN-HoaiMyNeural`). 
- Đồng thời, tải hoặc sinh hình ảnh tương ứng (hiện tại dùng placeholder ngẫu nhiên, cấu trúc đã mở sẵn để cắm API sinh ảnh chuyên dụng như Imagen 3).

### Bước 4: Render Video (Video Service)
- Dịch vụ `video_service.py` sử dụng thư viện **MoviePy**.
- Cắt/ghép (concatenate) các chuỗi Audio và Hình ảnh đã sinh; tự động căn chỉnh thời lượng hiển thị hình ảnh khớp chính xác với độ dài đoạn audio tương ứng.
- Xuất file `.mp4` (codec libx264/aac) ở định dạng khung hình dọc (Tiktok/Reels) về thư mục `assets/output`.

---

## 3. Cấu trúc mã nguồn (Directory Structure)

```text
AI-VIDEO-MAKER/
├── frontend/                     # UI Application (React + Vite)
│   ├── src/App.jsx               # Logic tương tác, gọi API và hiển thị
│   ├── src/index.css             # Định dạng, hiệu ứng UI
│   └── vite.config.js
├── backend/                      # API Server (FastAPI)
│   ├── main.py                   # Điểm đầu vào, khai báo Endpoint và CORS
│   ├── services/
│   │   ├── gemini_service.py     # Prompt kỹ thuật sư cho LLM
│   │   ├── tts_service.py        # Logic chuyển văn bản thành giọng nói async
│   │   └── video_service.py      # Logic ghép media bằng MoviePy
│   ├── assets/                   # Nơi lưu trữ tài nguyên máy tạo ra
│   │   ├── audio/                # Chứa file .mp3 từng phân cảnh
│   │   ├── images/               # Chứa file .jpg/.png từng phân cảnh
│   │   └── output/               # Chứa file final_video.mp4 
│   └── .env                      # Lưu GEMINI_API_KEY, TTS_VOICE
├── start.bat                     # Script khởi chạy đồng thời FE/BE
└── stop.bat                      # Script tắt sạch các tiến trình ngầm
```

---

## 4. Định hướng phát triển và mở rộng (Future Roadmap)

Tài liệu cung cấp sẵn các "điểm neo" (hook points) để nhà phát triển mở rộng trong tương lai:

1. **Image Generation API:** Thay thế logic placeholder tại `main.py` bằng thư viện gọi API Google Imagen 3, Midjourney hoặc DALL-E thông qua trường `image_prompt`.
2. **Hiệu ứng chữ (Subtitles):** Thêm module sinh file `.srt` từ text hoặc chèn TextClip trong `video_service.py` để tạo phụ đề động (karaoke effect) giúp video hấp dẫn hơn.
3. **Chuyển cảnh (Transitions):** Bổ sung các hiệu ứng chuyển cảnh mượt mà (Fade in/Fade out, Slide) giữa các phân đoạn hình ảnh trong quá trình render.
4. **Tối ưu Pipeline & Scale:** Sử dụng cơ chế hàng đợi (Celery/Redis) hoặc WebSockets để frontend có thể nhận real-time status thay vì HTTP Request chặn (blocking) nếu thời gian render video quá lớn/dài.

---

## 5. Nợ kỹ thuật & Rủi ro hệ thống (Technical Debt & Limitations)

Hiện tại hệ thống đang ở giai đoạn MVP (Minimum Viable Product). Dưới đây là các rủi ro hệ thống và khoản nợ kỹ thuật cần ưu tiên xử lý để đảm bảo ứng dụng đạt chuẩn Production:

1. **Lỗi Event Loop (FastAPI vs Edge-TTS):** `tts_service.py` đang dùng `asyncio.get_event_loop().run_until_complete()` bên trong môi trường FastAPI vốn đã chạy sẵn một event loop, có thể gây lỗi `RuntimeError: This event loop is already running`. *Khắc phục: Dùng endpoint `async def` và gọi `await` trực tiếp.*
2. **Thư viện Gemini bị Deprecated:** Thư viện `google.generativeai` đang bị Google ngừng hỗ trợ (End-of-life). *Khắc phục: Cần migrate sang package mới `google.genai` và dùng **Structured Outputs** (Pydantic Schema) để đảm bảo LLM trả về chuẩn JSON 100%, tránh parse lỗi.*
3. **Nguy cơ Timeout (Kiến trúc HTTP):** Render video bằng `MoviePy` rất nặng. Việc bắt HTTP Request chờ (blocking) có thể gây lỗi 504 Gateway Timeout. *Khắc phục: Áp dụng Hàng đợi (Queue) hoặc WebSocket như đề cập ở phần Định hướng.*
4. **Tràn bộ nhớ do Quản lý File:** Các tài nguyên sinh ra (ảnh, âm thanh, video) lưu trong thư mục `assets/` không được xóa đi sau mỗi chu kỳ chạy, dẫn tới rác bộ nhớ ổ cứng. *Khắc phục: Cần thiết lập cơ chế Cleanup (xóa file temp) tự động sau khi video render xong.*
5. **Đứt gãy Audio-Video (MoviePy):** Việc nối thẳng các clip mà không có crossfade hoặc xử lý audio tĩnh khiến luồng chuyển động hình ảnh trở nên thô và giật cục. *Khắc phục: Áp dụng hiệu ứng âm thanh/hình ảnh khi chuyển đổi (Transition/Crossfade).*

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

### File: `backend\main.py`
```py
"""
main.py
-------
NÂNG CẤP TỔNG HỢP (giải quyết đồng thời nợ kỹ thuật #1, #3, #4):

1. FIX TIMEOUT (#3): Thay vì xử lý toàn bộ pipeline ngay trong request
   HTTP (gây 504 Gateway Timeout với video dài), endpoint
   `/api/generate-video` giờ:
     - Tạo 1 `job_id`, lưu trạng thái "pending" vào bộ nhớ (dict).
     - Lên lịch toàn bộ pipeline chạy trong `BackgroundTasks`.
     - Trả về `job_id` NGAY LẬP TỨC (không chờ).
   Frontend sau đó gọi `GET /api/job-status/{job_id}` định kỳ (polling)
   để lấy % tiến trình và link video khi xong.

2. FIX EVENT LOOP (#1): toàn bộ chuỗi xử lý là `async def`, dùng
   `await` trực tiếp xuống tts_service/gemini_service. Không có
   run_until_complete ở đâu trong file này.

3. FIX RÁC BỘ NHỚ (#4): sau khi render xong và trả video cho người dùng,
   một task dọn dẹp sẽ tự xoá toàn bộ ảnh/audio tạm của job đó (giữ lại
   video final trong 1 khoảng thời gian rồi cũng xoá).

Lưu ý quan trọng khi triển khai thực tế nhiều người dùng đồng thời:
   Dict `JOBS` ở đây chỉ lưu trong RAM của 1 process — đủ dùng cho
   cá nhân (1 user, chạy local) như bạn đã chọn. Nếu sau này deploy
   multi-instance/production thật, hãy thay bằng Redis hoặc DB.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from services import gemini_service, tts_service, video_service

app = FastAPI(title="AI Video Maker API")

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

for d in (AUDIO_DIR, IMAGES_DIR, OUTPUT_DIR):
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
    created_at: datetime = datetime.utcnow()


JOBS: Dict[str, JobState] = {}


class GenerateVideoRequest(BaseModel):
    topic: str
    gemini_api_key: Optional[str] = None
    voice: Optional[str] = None  # ví dụ "vi-VN-HoaiMyNeural" / "vi-VN-NamMinhNeural"
    art_style: Optional[str] = "Cinematic"


# ---------------------------------------------------------------------------
# Pipeline chạy nền — đây là nơi tổng hợp toàn bộ logic cũ nằm rải rác
# ---------------------------------------------------------------------------
async def _run_pipeline(job_id: str, topic: str, api_key: Optional[str], voice: Optional[str], art_style: Optional[str] = "Cinematic"):
    job_dir_audio = os.path.join(AUDIO_DIR, job_id)
    job_dir_images = os.path.join(IMAGES_DIR, job_id)
    os.makedirs(job_dir_audio, exist_ok=True)
    os.makedirs(job_dir_images, exist_ok=True)

    try:
        # --- Bước 1: Sinh kịch bản (Structured Output, không thể lỗi parse) ---
        JOBS[job_id].status = "generating_script"
        JOBS[job_id].message = "Đang sinh kịch bản với Gemini..."
        JOBS[job_id].progress = 10
        scenes = await gemini_service.generate_script(topic, art_style=art_style, api_key=api_key)
        JOBS[job_id].scenes = scenes

        # --- Bước 2: Sinh audio (TTS) + ảnh (Imagen, fallback placeholder) ---
        JOBS[job_id].status = "generating_assets"
        scene_assets = []
        total = len(scenes)
        for i, scene in enumerate(scenes):
            audio_path = os.path.join(job_dir_audio, f"scene_{i+1}.mp3")
            image_path = os.path.join(job_dir_images, f"scene_{i+1}.png")

            JOBS[job_id].message = f"Đang tạo giọng đọc cảnh {i+1}/{total}..."
            duration = await tts_service.synthesize_speech(
                scene["text"], audio_path, voice=voice or tts_service.DEFAULT_VOICE
            )

            JOBS[job_id].message = f"Đang sinh ảnh AI cho cảnh {i+1}/{total}..."
            try:
                await gemini_service.generate_image(
                    scene["image_prompt"], image_path, api_key=api_key
                )
            except Exception as img_err:
                # Fallback: không để lỗi sinh ảnh (hết quota, bị safety filter...)
                # làm chết toàn bộ video. Dùng ảnh placeholder thay thế.
                JOBS[job_id].message = (
                    f"Cảnh {i+1}: sinh ảnh AI lỗi ({img_err}), dùng ảnh placeholder."
                )
                _create_placeholder_image(image_path)

            scene_assets.append(
                {
                    "image_path": image_path,
                    "audio_path": audio_path,
                    "text": scene["text"],
                    "duration": duration,
                }
            )
            JOBS[job_id].progress = 10 + int(60 * (i + 1) / total)

        # --- Bước 3: Render video (MoviePy v2, có crossfade + subtitle burn-in) ---
        JOBS[job_id].status = "rendering"
        JOBS[job_id].message = "Đang render video cuối cùng..."
        JOBS[job_id].progress = 75

        output_video_path = os.path.join(OUTPUT_DIR, f"{job_id}.mp4")
        output_srt_path = os.path.join(OUTPUT_DIR, f"{job_id}.srt")

        # MoviePy là thư viện đồng bộ/CPU-bound -> chạy trong thread riêng
        # để không block event loop trong lúc render (vài chục giây tới vài phút)
        await asyncio.to_thread(video_service.render_final_video, scene_assets, output_video_path)
        await asyncio.to_thread(video_service.generate_srt_file, scene_assets, output_srt_path)

        JOBS[job_id].status = "done"
        JOBS[job_id].progress = 100
        JOBS[job_id].message = "Hoàn tất!"
        JOBS[job_id].video_url = f"/api/download/{job_id}.mp4"
        JOBS[job_id].srt_url = f"/api/download/{job_id}.srt"

    except Exception as e:
        JOBS[job_id].status = "error"
        JOBS[job_id].error = str(e)
        JOBS[job_id].message = f"Lỗi: {e}"

    finally:
        # --- FIX NỢ #4: luôn dọn rác audio/ảnh tạm sau mỗi lần chạy,
        # bất kể thành công hay lỗi. Chỉ giữ lại video/srt final. ---
        shutil.rmtree(job_dir_audio, ignore_errors=True)
        shutil.rmtree(job_dir_images, ignore_errors=True)


def _create_placeholder_image(path: str):
    """Ảnh placeholder đơn giản khi Imagen lỗi, để pipeline không bị chặn."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1080, 1920), color=(30, 30, 40))
    draw = ImageDraw.Draw(img)
    draw.text((100, 900), "AI Video Maker", fill=(200, 200, 210))
    img.save(path)


async def _cleanup_old_outputs(max_age_hours: int = 24):
    """
    Dọn các video/srt final cũ hơn max_age_hours trong assets/output.
    Gọi định kỳ (vd. mỗi khi có request mới) để tránh tích rác lâu dài,
    bổ sung thêm cho phần cleanup tức thời ở trên.
    """
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
@app.post("/api/generate-video")
async def generate_video(req: GenerateVideoRequest, background_tasks: BackgroundTasks):
    if not req.topic or not req.topic.strip():
        raise HTTPException(status_code=400, detail="Thiếu chủ đề (topic).")

    job_id = str(uuid.uuid4())
    JOBS[job_id] = JobState(job_id=job_id, status="pending", message="Đã nhận yêu cầu, đang chờ xử lý...")

    background_tasks.add_task(_run_pipeline, job_id, req.topic, req.gemini_api_key, req.voice, req.art_style)
    background_tasks.add_task(_cleanup_old_outputs)

    # Trả về NGAY, không chờ render -> không còn lo 504 Gateway Timeout
    return {"job_id": job_id, "status_url": f"/api/job-status/{job_id}"}


@app.get("/api/job-status/{job_id}")
async def job_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy job_id này.")
    return job


@app.get("/api/download/{filename}")
async def download_file(filename: str):
    from fastapi.responses import FileResponse

    file_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File không tồn tại hoặc đã bị xoá.")
    return FileResponse(file_path)


@app.get("/")
async def health_check():
    return {"status": "ok", "service": "AI Video Maker API"}

```

### File: `backend\services\gemini_service.py`
```py
"""
gemini_service.py
------------------
NÂNG CẤP:
1. Migrate từ `google.generativeai` (deprecated) sang SDK mới `google.genai`.
2. Dùng Structured Output (response_schema bằng Pydantic) để Gemini LUÔN trả
   JSON đúng cấu trúc — không cần parse / regex / try-except JSON nữa.
3. Thêm hàm sinh ảnh thật bằng Imagen, dùng cho từng scene.

Cách hoạt động:
- `genai.Client()` tự đọc API key từ biến môi trường GEMINI_API_KEY hoặc
  GOOGLE_GENAI_API_KEY. Nếu người dùng nhập API key riêng trên Frontend,
  ta truyền `api_key=...` trực tiếp khi tạo Client cho từng request.
"""

from __future__ import annotations

import asyncio
import base64
import os
from typing import List, Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 1. Định nghĩa Schema bằng Pydantic — đây chính là "Structured Output".
#    Gemini sẽ bị BẮT phải trả JSON khớp 100% với schema này.
# ---------------------------------------------------------------------------
class Scene(BaseModel):
    scene: int = Field(description="Số thứ tự phân cảnh, bắt đầu từ 1")
    text: str = Field(description="Lời thoại tiếng Việt sẽ được đọc bằng TTS")
    image_prompt: str = Field(
        description="Mô tả hình ảnh bằng tiếng Anh, dùng để sinh ảnh AI (Imagen)"
    )


class ScriptResponse(BaseModel):
    scenes: List[Scene]


# ---------------------------------------------------------------------------
# 2. Sinh kịch bản (text) — thay thế hoàn toàn logic cũ
# ---------------------------------------------------------------------------
def _get_client(api_key: Optional[str] = None) -> genai.Client:
    """
    Tạo Client cho mỗi request. Nếu người dùng nhập API key trên FE thì
    dùng key đó; nếu không thì fallback về biến môi trường trong .env.
    """
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError(
            "Thiếu Gemini API Key. Hãy nhập trên giao diện hoặc khai báo "
            "GEMINI_API_KEY trong file backend/.env"
        )
    return genai.Client(api_key=key)


async def generate_script(topic: str, art_style: str = "Cinematic", api_key: Optional[str] = None) -> List[dict]:
    """
    Gọi Gemini để sinh 4 phân cảnh từ 1 chủ đề (topic).
    Trả về list[dict] đã được validate đúng schema Scene — không thể sai cấu trúc.
    """
    client = _get_client(api_key)

    system_prompt = (
        "Bạn là một biên kịch video ngắn (TikTok/Reels) chuyên nghiệp. "
        "Nhiệm vụ: viết kịch bản gồm CHÍNH XÁC 4 phân cảnh cho chủ đề được cung cấp. "
        "Lời thoại (text) viết bằng tiếng Việt, tự nhiên, súc tích, hấp dẫn người xem trong vài giây đầu. "
        f"image_prompt viết bằng tiếng Anh, mô tả cực kỳ chi tiết theo phong cách nghệ thuật: '{art_style}', "
        "phù hợp để đưa vào mô hình sinh ảnh AI."
    )

    # google.genai SDK chạy đồng bộ (sync) -> chạy trong thread riêng để
    # không block event loop của FastAPI (xem fix #1 trong tts_service.py)
    def _call():
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
        # Khi dùng response_schema, SDK cung cấp sẵn .parsed (đã validate)
        parsed: ScriptResponse = response.parsed
        return [scene.model_dump() for scene in parsed.scenes]

    return await asyncio.to_thread(_call)


# ---------------------------------------------------------------------------
# 3. Sinh ảnh thật bằng Imagen — thay cho placeholder ngẫu nhiên
# ---------------------------------------------------------------------------
async def generate_image(
    image_prompt: str,
    output_path: str,
    api_key: Optional[str] = None,
    aspect_ratio: str = "9:16",
) -> str:
    """
    Sinh 1 ảnh từ image_prompt bằng Imagen, lưu vào output_path (.png/.jpg).
    Trả về output_path khi thành công.

    Lưu ý: nếu lỗi (hết quota, key sai, prompt bị filter an toàn chặn...),
    hàm sẽ raise Exception để main.py có thể fallback sang ảnh placeholder,
    tránh làm chết toàn bộ pipeline.
    """
    client = _get_client(api_key)

    def _call():
        result = client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=image_prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio=aspect_ratio,  # 9:16 cho video dọc Tiktok/Reels
                safety_filter_level="block_low_and_above",
                person_generation="allow_adult",
            ),
        )
        if not result.generated_images:
            raise RuntimeError("Imagen không trả về ảnh nào (có thể bị Safety Filter chặn).")

        image_bytes = result.generated_images[0].image.image_bytes
        with open(output_path, "wb") as f:
            f.write(image_bytes)
        return output_path

    return await asyncio.to_thread(_call)

```

### File: `backend\services\tts_service.py`
```py
"""
tts_service.py
---------------
FIX NỢ KỸ THUẬT #1 (Event Loop):
- Code cũ dùng `asyncio.get_event_loop().run_until_complete(...)` bên trong
  một ứng dụng FastAPI đã có event loop chạy sẵn -> RuntimeError.
- Code mới: hàm này tự thân đã là `async def`, và gọi trực tiếp
  `await communicate.save(...)` của edge-tts. Endpoint phía main.py cũng
  phải là `async def` và `await` hàm này, KHÔNG được bọc thêm
  run_until_complete ở bất kỳ đâu nữa.
"""

from __future__ import annotations

import edge_tts
from mutagen.mp3 import MP3  # để đo chính xác độ dài audio (giây)

DEFAULT_VOICE = "vi-VN-HoaiMyNeural"  # giọng nữ tiếng Việt mặc định


async def synthesize_speech(text: str, output_path: str, voice: str = DEFAULT_VOICE) -> float:
    """
    Chuyển văn bản -> giọng nói, lưu file mp3 tại output_path.
    Trả về độ dài audio (giây) để video_service.py căn thời gian hiển thị ảnh.

    QUAN TRỌNG: hàm này PHẢI được gọi bằng `await synthesize_speech(...)`
    từ một hàm `async def` khác. Không gọi run_until_complete ở đây hay
    ở bất kỳ đâu khác trong codebase.
    """
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

    audio = MP3(output_path)
    duration_seconds = audio.info.length
    return duration_seconds

```

### File: `backend\services\video_service.py`
```py
"""
video_service.py
-----------------
NÂNG CẤP:
1. Cập nhật cú pháp sang MoviePy v2.x (breaking changes so với v1):
   - import từ `moviepy` thay vì `moviepy.editor`
   - `.set_start()` -> `.with_start()`, dùng `.with_effects([...])`
2. FIX NỢ KỸ THUẬT #5 (Đứt gãy Audio-Video): thêm CrossFadeIn/CrossFadeOut
   giữa các phân cảnh để chuyển cảnh mượt, không còn giật cục.
3. Thêm sinh phụ đề .srt (Roadmap mục 2), đốt thẳng (burn-in) phụ đề bằng
   TextClip lên video — không cần người xem tự tải file .srt riêng.
"""

from __future__ import annotations

import os
from typing import List, TypedDict

import srt
import datetime as dt

from moviepy import (
    AudioFileClip,
    ImageClip,
    CompositeVideoClip,
    TextClip,
    concatenate_videoclips,
)
from moviepy.video.fx import CrossFadeIn, CrossFadeOut

# Kích thước khung hình dọc chuẩn Tiktok/Reels
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30
CROSSFADE_DURATION = 0.6  # giây — thời gian chuyển cảnh mượt giữa 2 ảnh

# QUAN TRỌNG: chỉ định rõ font hỗ trợ đầy đủ dấu tiếng Việt (Latin Extended).
# Nếu để Pillow tự chọn font mặc định, có nguy cơ rơi vào bitmap font
# không có dấu tiếng Việt -> phụ đề hiển thị sai/ thiếu dấu.
# DejaVu Sans được cài sẵn trên hầu hết bản Linux/Ubuntu và hỗ trợ đủ
# Unicode tiếng Việt; trên Windows hãy đổi sang đường dẫn arial.ttf hoặc
# một font Unicode đầy đủ khác (ví dụ "C:/Windows/Fonts/arial.ttf").
SUBTITLE_FONT_PATH = "C:/Windows/Fonts/arial.ttf"


class SceneAsset(TypedDict):
    image_path: str
    audio_path: str
    text: str
    duration: float  # độ dài audio (giây), lấy từ tts_service.synthesize_speech


def _build_scene_clip(asset: SceneAsset, add_crossfade_in: bool) -> CompositeVideoClip:
    """Ghép 1 ảnh + 1 audio + phụ đề burn-in thành 1 clip hoàn chỉnh."""
    duration = asset["duration"]

    image_clip = (
        ImageClip(asset["image_path"])
        .with_duration(duration)
        .resized(height=VIDEO_HEIGHT)
    )
    # Cắt để tỷ lệ luôn là 9:16 trước khi zoom
    if image_clip.w < VIDEO_WIDTH:
        image_clip = image_clip.resized(width=VIDEO_WIDTH)
    
    # Hiệu ứng Ken Burns (Zoom in nhẹ 10% trong suốt thời gian)
    def get_zoom_factor(t):
        return 1.0 + 0.1 * (t / duration)
        
    image_clip = image_clip.resized(get_zoom_factor).with_position("center")

    audio_clip = AudioFileClip(asset["audio_path"])

    subtitle_clip = (
        TextClip(
            text=asset["text"],
            font=SUBTITLE_FONT_PATH,
            font_size=52,
            color="white",
            stroke_color="black",
            stroke_width=2,
            method="caption",
            size=(int(VIDEO_WIDTH * 0.92), None),
            text_align="center",
        )
        .with_duration(duration)
        .with_position(("center", VIDEO_HEIGHT * 0.78))
    )

    scene = CompositeVideoClip(
        [image_clip, subtitle_clip], size=(VIDEO_WIDTH, VIDEO_HEIGHT)
    ).with_audio(audio_clip)

    if add_crossfade_in:
        scene = scene.with_effects([CrossFadeIn(CROSSFADE_DURATION)])
    scene = scene.with_effects([CrossFadeOut(CROSSFADE_DURATION)])

    return scene


def render_final_video(scene_assets: List[SceneAsset], output_path: str) -> str:
    """
    Ghép toàn bộ các scene thành 1 video .mp4 hoàn chỉnh, có crossfade
    chuyển cảnh mượt giữa mỗi phân đoạn. Trả về output_path.
    """
    clips = [
        _build_scene_clip(asset, add_crossfade_in=(i > 0))
        for i, asset in enumerate(scene_assets)
    ]

    # padding âm = các clip overlap nhau đúng bằng thời gian crossfade,
    # tạo hiệu ứng tan-vào-nhau thay vì cắt cứng giữa 2 cảnh
    final = concatenate_videoclips(clips, method="compose", padding=-CROSSFADE_DURATION)

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


def generate_srt_file(scene_assets: List[SceneAsset], output_path: str) -> str:
    """
    Sinh file phụ đề .srt độc lập từ danh sách scene (Roadmap mục 2).
    Hữu ích nếu người dùng muốn tải phụ đề riêng để chỉnh sửa / đăng kèm
    video gốc lên các nền tảng cho phép upload .srt riêng.
    """
    subtitles = []
    cursor = 0.0
    for i, asset in enumerate(scene_assets, start=1):
        start = dt.timedelta(seconds=cursor)
        end = dt.timedelta(seconds=cursor + asset["duration"])
        subtitles.append(
            srt.Subtitle(index=i, start=start, end=end, content=asset["text"])
        )
        cursor += asset["duration"]

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(srt.compose(subtitles))

    return output_path

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
    "@tailwindcss/postcss": {},
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
import React, { useState } from 'react';
import axios from 'axios';
import {
  Film, Play, Loader2, CheckCircle, Sparkles, Mic, Video, Wand2, Key
} from 'lucide-react';

export default function App() {
  const [topic, setTopic] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [voice, setVoice] = useState('vi-VN-HoaiMyNeural');
  const [artStyle, setArtStyle] = useState('Cinematic');
  const [status, setStatus] = useState('idle'); // idle | pending | generating_script | generating_assets | rendering | done | error
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState('');
  const [videoUrl, setVideoUrl] = useState(null);
  const [srtUrl, setSrtUrl] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [script, setScript] = useState([]);

  const pollingRef = React.useRef(null);
  const API_BASE = "http://127.0.0.1:8000";

  const handleGenerate = async () => {
    if (!topic.trim()) return;
    setErrorMsg('');
    setVideoUrl(null);
    setScript([]);
    setStatus('pending');
    setProgress(0);

    try {
      const res = await axios.post(`${API_BASE}/api/generate-video`, {
        topic,
        gemini_api_key: apiKey || null,
        voice,
        art_style: artStyle,
      });
      startPolling(res.data.job_id);
    } catch (err) {
      setStatus('error');
      setErrorMsg(err.response?.data?.detail || err.message || 'Lỗi từ server.');
    }
  };

  const startPolling = (jobId) => {
    if (pollingRef.current) clearInterval(pollingRef.current);

    pollingRef.current = setInterval(async () => {
      try {
        const res = await axios.get(`${API_BASE}/api/job-status/${jobId}`);
        const job = res.data;
        setStatus(job.status);
        setProgress(job.progress);
        setMessage(job.message);

        if (job.status === 'done') {
          clearInterval(pollingRef.current);
          setVideoUrl(`${API_BASE}${job.video_url}`);
          setSrtUrl(`${API_BASE}${job.srt_url}`);
          if (job.scenes) {
            setScript(job.scenes);
          }
        }

        if (job.status === 'error') {
          clearInterval(pollingRef.current);
          setErrorMsg(job.error);
        }
      } catch (err) {
        clearInterval(pollingRef.current);
        setStatus('error');
        setErrorMsg(err.message);
      }
    }, 1000);
  };

  return (
    <div className="app-wrapper">

      {/* ── HEADER ── */}
      <header className="app-header">
        <div className="header-icon-wrap">
          <Film size={26} />
        </div>
        <div>
          <h1 className="header-title">AI Video Studio</h1>
          <p className="header-sub">Xưởng sản xuất Video Tự động — Cá nhân · Miễn phí</p>
        </div>

        {/* Status chips */}
        <div className="status-bar" style={{ marginLeft: 'auto' }}>
          <span className="status-chip chip-green">
            <span className="chip-dot" />
            Backend Online
          </span>
          <span className="status-chip chip-blue">
            <span className="chip-dot" />
            Gemini API
          </span>
        </div>
      </header>

      {/* ── WORKFLOW BANNER ── */}
      <div className="card workflow-card">
        <p className="workflow-title">Quy trình tự động hóa</p>
        <div className="workflow-steps">
          {[
            { icon: <Wand2 size={13} />, label: 'Gemini\nViết kịch bản', color: '#f59e0b' },
            { icon: <Mic size={13} />, label: 'Edge TTS\nGiọng đọc AI', color: '#3b82f6' },
            { icon: <Sparkles size={13} />, label: 'Imagen\nSinh hình ảnh', color: '#8b5cf6' },
            { icon: <Video size={13} />, label: 'MoviePy\nRender MP4', color: '#10b981' },
          ].map((s, i) => (
            <div className="wf-step" key={i}>
              <div className="wf-icon" style={{ color: s.color, borderColor: s.color + '40', background: s.color + '10' }}>
                {s.icon}
              </div>
              <span className="wf-label" style={{ whiteSpace: 'pre-line' }}>{s.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── MAIN GRID ── */}
      <div className="main-grid">

        {/* LEFT — Control Panel */}
        <div className="card" style={{ alignSelf: 'start' }}>
          <div className="card-top-bar" />

          <div className="section-label">
            <div className="step-badge">1</div>
            <span className="section-title">Nội dung Kịch bản</span>
          </div>

          <div className="form-group">
            <label className="form-label">Ý tưởng / Chủ đề</label>
            <textarea
              className="form-textarea"
              value={topic}
              onChange={e => setTopic(e.target.value)}
              placeholder="Ví dụ: Làm 1 video ngắn 30s giới thiệu Căn hộ dịch vụ tại Tân Bình, nhấn mạnh tiện ích full nội thất, giờ giấc tự do, giá tốt..."
            />
          </div>

          <div className="divider" />
          
          <div className="section-label">
            <div className="step-badge" style={{ color: '#ec4899', borderColor: '#ec489940', background: '#ec489910' }}>
              2
            </div>
            <span className="section-title">Tuỳ chỉnh Nâng cao</span>
          </div>

          <div style={{ display: 'flex', gap: '16px', marginBottom: '16px' }}>
            <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
              <label className="form-label">Giọng đọc (Voice)</label>
              <select className="form-input" value={voice} onChange={e => setVoice(e.target.value)} style={{ appearance: 'auto', backgroundColor: 'rgba(0,0,0,0.2)' }}>
                <option value="vi-VN-HoaiMyNeural">Nữ - Hoài My</option>
                <option value="vi-VN-NamMinhNeural">Nam - Nam Minh</option>
              </select>
            </div>
            <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
              <label className="form-label">Phong cách (Art Style)</label>
              <select className="form-input" value={artStyle} onChange={e => setArtStyle(e.target.value)} style={{ appearance: 'auto', backgroundColor: 'rgba(0,0,0,0.2)' }}>
                <option value="Cinematic">Cinematic (Điện ảnh)</option>
                <option value="Anime">Anime (Hoạt hình)</option>
                <option value="Realistic">Realistic (Chân thực)</option>
                <option value="3D Render">3D Render (Khối 3D)</option>
              </select>
            </div>
          </div>

          <div className="divider" />

          <div className="section-label" style={{ marginBottom: 12 }}>
            <div className="step-badge" style={{ color: '#a78bfa', borderColor: '#a78bfa40', background: '#a78bfa10' }}>
              <Key size={12} />
            </div>
            <span className="section-title">API Key</span>
          </div>

          <div className="form-group">
            <label className="form-label">Gemini API Key (Tùy chọn)</label>
            <input
              type="password"
              className="form-input"
              value={apiKey}
              onChange={e => setApiKey(e.target.value)}
              placeholder="Lấy miễn phí tại aistudio.google.com"
            />
          </div>

          <div style={{ marginTop: 24 }}>
            <button
              className="btn-generate"
              onClick={handleGenerate}
              disabled={['pending', 'generating_script', 'generating_assets', 'rendering'].includes(status) || !topic.trim()}
            >
              {['pending', 'generating_script', 'generating_assets', 'rendering'].includes(status) ? (
                <><Loader2 size={20} className="spin" /> Đang xử lý... {progress}%</>
              ) : (
                <><Play size={20} fill="currentColor" /> Sản Xuất Video Ngay</>
              )}
            </button>
          </div>

          {status === 'error' && (
            <div className="error-box">⚠ {errorMsg}</div>
          )}
        </div>

        {/* RIGHT — Preview Panel */}
        <div className="preview-panel">

          {/* Preview Card */}
          <div className="card preview-card">
            <div className="card-top-bar" style={{ background: 'linear-gradient(90deg, #3b82f6, #8b5cf6)' }} />

            {/* IDLE */}
            {status === 'idle' && (
              <div className="idle-state">
                <div className="idle-icon">
                  <Film size={32} opacity={0.3} />
                </div>
                <h3 className="idle-title">Chưa có Video</h3>
                <p className="idle-desc">Nhập ý tưởng bên trái và bấm <strong>Sản Xuất</strong> để hệ thống bắt đầu làm việc.</p>
              </div>
            )}

            {/* LOADING */}
            {['pending', 'generating_script', 'generating_assets', 'rendering'].includes(status) && (
              <div className="loading-state">
                <div className="spinner-ring" />
                <h3 className="loading-title">{message || 'Đang xử lý...'}</h3>
                <div style={{ marginTop: 20, width: '100%', background: 'rgba(255,255,255,0.1)', height: 8, borderRadius: 4, overflow: 'hidden' }}>
                   <div style={{ width: `${progress}%`, background: 'linear-gradient(90deg, #3b82f6, #a855f7)', height: '100%', borderRadius: 4, transition: 'width 0.5s ease' }} />
                </div>
                <p style={{ marginTop: 12, fontSize: 13, color: '#aaa', fontWeight: 500 }}>Tiến trình: {progress}%</p>
              </div>
            )}

            {/* SUCCESS */}
            {status === 'done' && (
              <div className="success-state">
                <div className="success-badge">
                  <CheckCircle size={14} />
                  Kết xuất thành công
                </div>
                <div className="video-player-wrap" style={{ display: 'flex', flexDirection: 'column', gap: '10px', width: '100%', alignItems: 'center' }}>
                  {videoUrl && <video src={videoUrl} controls style={{ width: '100%', borderRadius: '8px', maxHeight: '400px' }} />}
                  <div style={{ display: 'flex', gap: '10px' }}>
                    <a href={videoUrl} download style={{ padding: '6px 12px', background: 'rgba(255,255,255,0.1)', borderRadius: '6px', color: '#fff', textDecoration: 'none', fontSize: '0.85rem' }}>⬇️ Tải Video</a>
                    <a href={srtUrl} download style={{ padding: '6px 12px', background: 'rgba(255,255,255,0.1)', borderRadius: '6px', color: '#fff', textDecoration: 'none', fontSize: '0.85rem' }}>⬇️ Tải Phụ đề (.srt)</a>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Script preview card (show if success) */}
          {status === 'done' && script.length > 0 && (
            <div className="card" style={{ padding: '20px 24px' }}>
              <div className="section-label" style={{ marginBottom: 14 }}>
                <div className="step-badge" style={{ color: '#10b981', borderColor: '#10b98140', background: '#10b98110' }}>
                  <Sparkles size={12} />
                </div>
                <span className="section-title" style={{ fontSize: '0.9rem' }}>Kịch bản được tạo</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {script.map((scene, i) => (
                  <div key={i} style={{
                    background: 'rgba(0,0,0,0.25)',
                    border: '1px solid rgba(255,255,255,0.06)',
                    borderRadius: 8,
                    padding: '10px 14px',
                  }}>
                    <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#f59e0b', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.6px' }}>
                      Cảnh {scene.scene}
                    </div>
                    <div style={{ fontSize: '0.9rem', color: '#cbd5e1', lineHeight: 1.5 }}>{scene.text}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}

```

### File: `frontend\src\index.css`
```css
@import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700;800;900&display=swap');

:root {
  --bg-main: #0a0e1a;
  --bg-card: rgba(16, 22, 38, 0.85);
  --bg-input: rgba(0, 0, 0, 0.4);
  --border: rgba(255, 255, 255, 0.08);
  --border-focus: rgba(245, 158, 11, 0.5);
  --amber: #f59e0b;
  --amber-dark: #d97706;
  --amber-bright: #fbbf24;
  --blue: #3b82f6;
  --text-1: #f8fafc;
  --text-2: #cbd5e1;
  --text-3: #64748b;
  --green: #10b981;
  --red: #ef4444;
  --radius: 16px;
  --radius-sm: 10px;
  --shadow-card: 0 4px 24px -6px rgba(0, 0, 0, 0.5);
  --shadow-amber: 0 4px 20px rgba(245, 158, 11, 0.3);
  --shadow-amber-hover: 0 8px 28px rgba(245, 158, 11, 0.5);
  --transition: 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

*, *::before, *::after { box-sizing: border-box; }

body {
  margin: 0;
  font-family: 'Be Vietnam Pro', system-ui, -apple-system, sans-serif;
  font-size: 15px;
  line-height: 1.6;
  letter-spacing: 0.15px;
  color: var(--text-1);
  background: var(--bg-main);
  background-image:
    radial-gradient(circle at 10% 60%, rgba(245, 158, 11, 0.04) 0%, transparent 40%),
    radial-gradient(circle at 90% 20%, rgba(59, 130, 246, 0.04) 0%, transparent 40%);
  min-height: 100vh;
}

/* ─── LAYOUT ──────────────────────────── */
.app-wrapper {
  max-width: 1200px;
  margin: 0 auto;
  padding: 40px 32px;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  gap: 36px;
}

/* ─── HEADER ──────────────────────────── */
.app-header {
  display: flex;
  align-items: center;
  gap: 20px;
  padding-bottom: 32px;
  border-bottom: 1px solid var(--border);
}

.header-icon-wrap {
  width: 56px;
  height: 56px;
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.2);
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 0 18px rgba(245, 158, 11, 0.12);
  flex-shrink: 0;
  color: var(--amber);
}

.header-title {
  font-size: 2.2rem;
  font-weight: 900;
  letter-spacing: -0.5px;
  background: linear-gradient(135deg, var(--amber) 0%, var(--amber-bright) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin: 0;
  line-height: 1.1;
}

.header-sub {
  font-size: 0.95rem;
  color: var(--text-3);
  font-weight: 500;
  margin: 4px 0 0;
}

/* ─── STATUS BAR ──────────────────────── */
.status-bar {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.status-chip {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 6px 14px;
  border-radius: 99px;
  font-size: 0.8rem;
  font-weight: 600;
  border: 1px solid;
}
.chip-green {
  background: rgba(16, 185, 129, 0.08);
  border-color: rgba(16, 185, 129, 0.25);
  color: #34d399;
}
.chip-blue {
  background: rgba(59, 130, 246, 0.08);
  border-color: rgba(59, 130, 246, 0.25);
  color: #60a5fa;
}
.chip-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse 2s infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* ─── MAIN GRID ───────────────────────── */
.main-grid {
  display: grid;
  grid-template-columns: 420px 1fr;
  gap: 24px;
  align-items: start;
  flex: 1;
}

/* ─── CARD ────────────────────────────── */
.card {
  background: var(--bg-card);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 28px;
  box-shadow: var(--shadow-card);
  position: relative;
  overflow: hidden;
  transition: border-color var(--transition), box-shadow var(--transition);
}

.card:hover {
  border-color: rgba(245, 158, 11, 0.2);
}

.card-top-bar {
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--amber), var(--amber-bright));
  border-radius: var(--radius) var(--radius) 0 0;
}

/* ─── SECTION LABEL ───────────────────── */
.section-label {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 18px;
}

.step-badge {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.25);
  color: var(--blue);
  font-weight: 700;
  font-size: 0.8rem;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.section-title {
  font-size: 1rem;
  font-weight: 700;
  color: var(--text-1);
  letter-spacing: 0.1px;
}

/* ─── FORM ELEMENTS ───────────────────── */
.form-group {
  margin-bottom: 18px;
}

.form-label {
  display: block;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: 0.6px;
  margin-bottom: 8px;
}

.form-textarea {
  width: 100%;
  height: 140px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 14px 16px;
  color: var(--text-1);
  font-family: inherit;
  font-size: 0.95rem;
  line-height: 1.6;
  resize: none;
  outline: none;
  transition: border-color var(--transition), box-shadow var(--transition);
}

.form-textarea:focus {
  border-color: var(--border-focus);
  box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.1);
}

.form-textarea::placeholder {
  color: var(--text-3);
  font-size: 0.88rem;
}

.form-input {
  width: 100%;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 12px 16px;
  color: var(--text-1);
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 0.85rem;
  outline: none;
  transition: border-color var(--transition);
}

.form-input:focus {
  border-color: var(--border-focus);
}

.form-input::placeholder {
  color: var(--text-3);
  font-family: 'Be Vietnam Pro', sans-serif;
}

/* ─── DIVIDER ─────────────────────────── */
.divider {
  height: 1px;
  background: var(--border);
  margin: 20px 0;
}

/* ─── GENERATE BUTTON ─────────────────── */
.btn-generate {
  width: 100%;
  padding: 15px 24px;
  background: linear-gradient(135deg, var(--amber) 0%, var(--amber-bright) 100%);
  border: none;
  border-radius: var(--radius-sm);
  color: #000;
  font-family: inherit;
  font-size: 1rem;
  font-weight: 800;
  letter-spacing: 0.3px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  box-shadow: var(--shadow-amber);
  transition: all var(--transition);
}

.btn-generate:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: var(--shadow-amber-hover);
}

.btn-generate:active:not(:disabled) {
  transform: translateY(0);
}

.btn-generate:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* ─── ERROR BOX ───────────────────────── */
.error-box {
  margin-top: 14px;
  padding: 12px 16px;
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.25);
  border-radius: var(--radius-sm);
  color: #fca5a5;
  font-size: 0.88rem;
  line-height: 1.5;
}

/* ─── PREVIEW PANEL ───────────────────── */
.preview-panel {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-height: 580px;
}

.preview-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

/* IDLE state */
.idle-state {
  text-align: center;
  color: var(--text-3);
}

.idle-icon {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.03);
  border: 1px dashed rgba(255, 255, 255, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 20px;
}

.idle-title {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--text-2);
  margin: 0 0 8px;
}

.idle-desc {
  font-size: 0.88rem;
  color: var(--text-3);
  max-width: 260px;
  margin: 0 auto;
  line-height: 1.6;
}

/* LOADING state */
.loading-state {
  width: 100%;
  max-width: 360px;
  text-align: center;
}

.spinner-ring {
  width: 72px;
  height: 72px;
  border: 4px solid rgba(255, 255, 255, 0.06);
  border-top-color: var(--amber);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 24px;
  box-shadow: 0 0 20px rgba(245, 158, 11, 0.4);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-title {
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--text-1);
  margin: 0 0 20px;
}

.step-list {
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  text-align: left;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 0.88rem;
  color: var(--text-3);
}

.step-item.done { color: var(--green); }
.step-item.active { color: var(--text-1); font-weight: 600; }
.step-item.pending { opacity: 0.4; }

/* SUCCESS state */
.success-state {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

.success-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 20px;
  background: rgba(16, 185, 129, 0.08);
  border: 1px solid rgba(16, 185, 129, 0.25);
  border-radius: 99px;
  color: var(--green);
  font-size: 0.85rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.8px;
}

.video-player-wrap {
  width: 100%;
  max-width: 300px;
  aspect-ratio: 9/16;
  background: #000;
  border-radius: 20px;
  border: 3px solid rgba(255, 255, 255, 0.08);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.6);
}

.video-play-btn {
  width: 64px;
  height: 64px;
  background: rgba(255,255,255,0.1);
  border: 2px solid rgba(255,255,255,0.2);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(8px);
  cursor: pointer;
  transition: transform var(--transition), background var(--transition);
}

.video-play-btn:hover {
  transform: scale(1.1);
  background: rgba(255,255,255,0.18);
}

/* ─── WORKFLOW INFO ────────────────────── */
.workflow-card {
  padding: 18px 22px;
}

.workflow-title {
  font-size: 0.8rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: var(--text-3);
  margin: 0 0 14px;
}

.workflow-steps {
  display: flex;
  gap: 0;
  position: relative;
}

.workflow-steps::before {
  content: '';
  position: absolute;
  top: 14px;
  left: 14px;
  right: 14px;
  height: 1px;
  background: var(--border);
  z-index: 0;
}

.wf-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  flex: 1;
  position: relative;
  z-index: 1;
}

.wf-icon {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.7rem;
  font-weight: 700;
  border: 1px solid var(--border);
  background: var(--bg-main);
}

.wf-label {
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text-3);
  text-align: center;
  line-height: 1.3;
}

/* ─── SPIN ANIMATION ──────────────────── */
.spin { animation: spin 1s linear infinite; }

/* ─── RESPONSIVE ──────────────────────── */
@media (max-width: 900px) {
  .app-wrapper { padding: 24px 16px; gap: 24px; }
  .main-grid { grid-template-columns: 1fr; }
  .header-title { font-size: 1.7rem; }
}

```

### File: `frontend\src\main.jsx`
```jsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

```

