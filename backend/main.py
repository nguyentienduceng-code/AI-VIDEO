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
class GenerateVideoRequest(BaseModel):
    topic: Optional[str] = ""
    mode: str = "storyteller"  # storyteller | photo_narration | photo_slideshow | script_video | quiz_listicle
    num_scenes: int = 4  # 4-20
    aspect_ratio: str = "9:16"  # 9:16 | 16:9 | 1:1
    gemini_api_key: Optional[str] = None
    voice: Optional[str] = None
    art_style: Optional[str] = "Cinematic"
    bgm_track: Optional[str] = None  # filename from bgm/ dir, or None
    script_text: Optional[str] = None  # for script_video mode
    upload_session_id: Optional[str] = None  # for photo_narration / photo_slideshow
    speech_rate: Optional[str] = "+0%"  # TTS speed: "-10%", "+0%", "+15%"


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
    await manager.broadcast(job_id, job.model_dump())


# ---------------------------------------------------------------------------
# Pipeline chạy nền — đa chế độ
# ---------------------------------------------------------------------------
async def _run_pipeline(job_id: str, req: GenerateVideoRequest):
    job_dir_audio = os.path.join(AUDIO_DIR, job_id)
    job_dir_images = os.path.join(IMAGES_DIR, job_id)
    os.makedirs(job_dir_audio, exist_ok=True)
    os.makedirs(job_dir_images, exist_ok=True)

    mode = req.mode
    api_key = req.gemini_api_key
    voice = req.voice or tts_service.DEFAULT_VOICE
    art_style = req.art_style or "Cinematic"
    speech_rate = req.speech_rate or "+0%"
    num_scenes = max(4, min(20, req.num_scenes))
    aspect_ratio = req.aspect_ratio if req.aspect_ratio in VALID_ASPECT_RATIOS else "9:16"

    # Map aspect ratio cho Imagen
    imagen_aspect = aspect_ratio.replace(":", ":")  # already fine for Imagen

    # BGM path (nếu user chọn)
    bgm_path = None
    if req.bgm_track:
        candidate = os.path.join(BGM_DIR, req.bgm_track)
        if os.path.isfile(candidate):
            bgm_path = candidate

    try:
        # ══════════════════════════════════════════════════════════════
        # BƯỚC 1: SINH KỊCH BẢN — tuỳ theo mode
        # ══════════════════════════════════════════════════════════════
        await _update_job(job_id, status="generating_script", message="Đang sinh kịch bản...", progress=10)

        scenes: List[dict] = []

        if mode == "storyteller" or mode == "quiz_listicle":
            if not req.topic or not req.topic.strip():
                raise ValueError("Thiếu chủ đề (topic) cho mode này.")
            scenes = await gemini_service.generate_script(
                topic=req.topic, num_scenes=num_scenes, mode=mode,
                art_style=art_style, api_key=api_key,
            )

        elif mode == "script_video":
            if not req.script_text or not req.script_text.strip():
                raise ValueError("Thiếu script text cho mode Script → Video.")
            scenes = await gemini_service.split_script_to_scenes(
                script_text=req.script_text, num_scenes=num_scenes,
                art_style=art_style, api_key=api_key,
            )

        elif mode == "photo_narration":
            if not req.upload_session_id:
                raise ValueError("Thiếu ảnh upload cho mode Photo Narration.")
            user_images = get_upload_paths(req.upload_session_id)
            if not user_images:
                raise ValueError("Không tìm thấy ảnh upload. Vui lòng upload lại.")
            scenes = await gemini_service.generate_script_from_images(
                image_paths=user_images, topic=req.topic, api_key=api_key,
            )

        elif mode == "photo_slideshow":
            if not req.upload_session_id:
                raise ValueError("Thiếu ảnh upload cho mode Photo Slideshow.")
            user_images = get_upload_paths(req.upload_session_id)
            if not user_images:
                raise ValueError("Không tìm thấy ảnh upload. Vui lòng upload lại.")
            # Slideshow: không cần Gemini, mỗi ảnh là 1 scene không có text
            scenes = [
                {"scene": i + 1, "text": "", "image_prompt": ""}
                for i in range(len(user_images))
            ]

        await _update_job(job_id, scenes=scenes, progress=25)

        # ══════════════════════════════════════════════════════════════
        # BƯỚC 2: TẠO ASSETS — Audio (TTS) + Hình ảnh
        # ══════════════════════════════════════════════════════════════
        await _update_job(job_id, status="generating_assets")

        scene_assets = []
        total = len(scenes)

        # Lấy ảnh user upload (nếu mode photo)
        user_images = []
        if mode in ("photo_narration", "photo_slideshow") and req.upload_session_id:
            user_images = get_upload_paths(req.upload_session_id)

        for i, scene in enumerate(scenes):
            audio_path = os.path.join(job_dir_audio, f"scene_{i+1}.mp3")
            image_path = os.path.join(job_dir_images, f"scene_{i+1}.png")

            # ── Audio: TTS nếu có text ──
            duration = video_service.SLIDESHOW_SCENE_DURATION  # default cho slideshow
            if scene.get("text") and scene["text"].strip() and mode != "photo_slideshow":
                await _update_job(job_id, message=f"Đang tạo giọng đọc cảnh {i+1}/{total}...")
                duration = await tts_service.synthesize_speech(
                    scene["text"], audio_path, voice=voice, rate=speech_rate,
                )
            else:
                audio_path = ""  # slideshow: không có audio per-scene

            # ── Image: dùng ảnh user hoặc sinh bằng Imagen ──
            if mode in ("photo_narration", "photo_slideshow") and i < len(user_images):
                # Dùng ảnh gốc của user
                image_path = user_images[i]
            else:
                # Sinh ảnh AI bằng Imagen
                await _update_job(job_id, message=f"Đang sinh ảnh AI cho cảnh {i+1}/{total}...")
                try:
                    await gemini_service.generate_image(
                        scene["image_prompt"], image_path,
                        api_key=api_key, aspect_ratio=imagen_aspect,
                    )
                except Exception as img_err:
                    await _update_job(
                        job_id,
                        message=f"Cảnh {i+1}: sinh ảnh AI lỗi ({img_err}), dùng ảnh placeholder.",
                    )
                    _create_placeholder_image(image_path)

            scene_assets.append({
                "image_path": image_path,
                "audio_path": audio_path,
                "text": scene.get("text", ""),
                "duration": duration,
            })
            await _update_job(job_id, progress=25 + int(50 * (i + 1) / total))

        # ══════════════════════════════════════════════════════════════
        # BƯỚC 3: RENDER VIDEO (MoviePy v2)
        # ══════════════════════════════════════════════════════════════
        await _update_job(
            job_id, status="rendering", message="Đang render video cuối cùng...", progress=80,
        )

        output_video_path = os.path.join(OUTPUT_DIR, f"{job_id}.mp4")
        output_srt_path = os.path.join(OUTPUT_DIR, f"{job_id}.srt")

        # MoviePy CPU-bound -> chạy trong thread riêng
        await asyncio.to_thread(
            video_service.render_final_video,
            scene_assets, output_video_path,
            aspect_ratio=aspect_ratio,
            bgm_path=bgm_path,
            mode=mode,
        )

        # SRT chỉ có ý nghĩa khi có text (không cho slideshow)
        if mode != "photo_slideshow":
            await asyncio.to_thread(video_service.generate_srt_file, scene_assets, output_srt_path)

        await _update_job(
            job_id,
            status="done", progress=100, message="Hoàn tất!",
            video_url=f"/api/download/{job_id}.mp4",
            srt_url=f"/api/download/{job_id}.srt" if mode != "photo_slideshow" else None,
        )

    except Exception as e:
        await _update_job(job_id, status="error", error=str(e), message=f"Lỗi: {e}")

    finally:
        # Dọn rác audio/ảnh tạm (giữ lại video/srt final + ảnh upload)
        shutil.rmtree(job_dir_audio, ignore_errors=True)
        shutil.rmtree(job_dir_images, ignore_errors=True)
        # Cleanup ảnh upload sau khi render xong
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
@app.post("/api/generate-video")
async def generate_video(req: GenerateVideoRequest, background_tasks: BackgroundTasks):
    # Validate mode
    if req.mode not in VALID_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Mode không hợp lệ. Chọn 1 trong: {', '.join(VALID_MODES)}",
        )

    # Validate input theo mode
    if req.mode in ("storyteller", "quiz_listicle") and (not req.topic or not req.topic.strip()):
        raise HTTPException(status_code=400, detail="Thiếu chủ đề (topic) cho mode này.")

    if req.mode == "script_video" and (not req.script_text or not req.script_text.strip()):
        raise HTTPException(status_code=400, detail="Thiếu script text cho mode Script → Video.")

    if req.mode in ("photo_narration", "photo_slideshow") and not req.upload_session_id:
        raise HTTPException(status_code=400, detail="Thiếu ảnh upload. Vui lòng upload ảnh trước.")

    job_id = str(uuid.uuid4())
    JOBS[job_id] = JobState(
        job_id=job_id, status="pending", mode=req.mode,
        message="Đã nhận yêu cầu, đang chờ xử lý...",
    )

    background_tasks.add_task(_run_pipeline, job_id, req)
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
            await websocket.send_json(JOBS[job_id].model_dump())
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
