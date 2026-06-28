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
