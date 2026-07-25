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
import re
import shutil
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from services import gemini_service, tts_service, video_service
from services.image_upload_service import (
    cleanup_upload,
    get_upload_paths,
    process_uploaded_images,
)

app = FastAPI(title="AI Video Studio API")

# CORS cấu hình qua env ALLOWED_ORIGINS (danh sách phân tách bằng dấu phẩy).
# Mặc định "*" để dev local hoạt động như cũ; khi deploy public nên set origin cụ thể.
_origins_env = os.getenv("ALLOWED_ORIGINS", "*").strip()
ALLOWED_ORIGINS = ["*"] if _origins_env == "*" else [o.strip() for o in _origins_env.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=ALLOWED_ORIGINS != ["*"],
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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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
    sync_characters: bool = False
    content_niche: Optional[str] = None  # book|finance|history|psychology|truecrime|travel — palette hiệu ứng chính xác

class RenderVideoRequest(BaseModel):
    scenes: List[dict]
    mode: str = "storyteller"
    aspect_ratio: str = "9:16"
    art_style: Optional[str] = "Cinematic"
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
    cover_image_session_id: Optional[str] = None
    cover_image_position: str = "start"  # "start", "end", "both"
    use_sfx: bool = True
    sfx_volume: float = 0.08
    color_grading: str = "warm_cinematic"
    topic: Optional[str] = None
    use_breathing: bool = False
    hook_effect: str = "word_by_word"
    hook_quote: Optional[str] = None
    hook_reel_sfx: str = "tick_wood"  # tiếng trục quay Máy Xèng — xem video_service.HOOK_REEL_SOUNDS
    prefer_stock_video: bool = False  # Ép dùng video stock Pexels cho MỌI cảnh (video thật thay ảnh AI)
    # Nguồn hình cho từng cảnh — thay cho heuristic dò chuỗi "photorealistic" trong prompt:
    #   auto        = theo lựa chọn user (prefer_stock_video / art_style thực sự là footage thật)
    #   ai_image    = KHÔNG bao giờ dùng stock, luôn sinh ảnh AI
    #   stock_video = luôn thử video stock trước, fallback ảnh AI nếu không có
    #   mixed       = xen kẽ theo cảm xúc cảnh (xem _pick_visual_source)
    visual_source: str = "auto"
    # Đọc liền mạch: gọi Edge-TTS 1 lần cho TOÀN kịch bản thay vì từng cảnh.
    # Đánh đổi: bỏ qua emotion + speech_rate_modifier riêng của từng cảnh.
    use_single_pass_narration: bool = False

class PresetRequest(BaseModel):
    name: str
    aspect_ratio: str = "9:16"
    voice: str = "vi-VN-NamMinhNeural"
    art_style: str = "Anime illustration, vibrant colors, Studio Ghibli inspired"
    bgm_track: Optional[str] = "auto"
    target_duration: str = "30s"
    narration_tone: str = "viral"
    speech_rate: str = "+0%"
    speech_pitch: str = "+0Hz"
    bgm_volume: float = 15
    subtitle_style: str = "karaoke_bold"
    color_grading: str = "warm_cinematic"
    prefer_stock_video: bool = False
    visual_source: str = "auto"
    use_single_pass_narration: bool = False
    hook_effect: str = "word_by_word"
    hook_reel_sfx: str = "tick_wood"
    use_sfx: bool = True
    sfx_volume: float = 8
    use_ken_burns: bool = True
    hook_zoom_boost: bool = True
    use_breathing: bool = False
    use_frame_chaining: bool = True
    use_beat_sync: bool = False

VALID_MODES = {"storyteller", "photo_narration", "photo_slideshow", "script_video", "quiz_listicle", "manual"}
VALID_ASPECT_RATIOS = {"9:16", "16:9", "1:1"}


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------
VALID_VISUAL_SOURCES = {"auto", "ai_image", "stock_video", "mixed"}

# Cảm xúc hợp với b-roll quay thật (cảnh trầm, trừu tượng, mang tính không khí).
# Các cảm xúc còn lại (hook, excited) cần dàn dựng cụ thể → ưu tiên ảnh AI.
_STOCK_FRIENDLY_EMOTIONS = {"calm", "closing", "dramatic", "suspense"}


def _pick_visual_source(req, scene: dict, scene_index: int) -> str:
    """
    Quyết định nguồn hình cho 1 cảnh: "stock_video" hay "ai_image".

    LÝ DO TỒN TẠI: trước đây pipeline dò chuỗi "photorealistic"/"realistic" trong
    `image_prompt` để bật Pexels. Nhưng base prompt của gemini_service BẮT BUỘC Gemini
    chèn "8k, photorealistic, Unreal Engine 5" vào MỌI image_prompt → điều kiện luôn
    đúng → gần như mọi video đều bị đẩy sang video tải về, kể cả khi user không chọn.
    Giờ chỉ dựa trên lựa chọn tường minh của user (visual_source / prefer_stock_video)
    và art_style — thứ do user chọn chứ không do Gemini sinh ra.
    """
    source = getattr(req, "visual_source", "auto")
    if source not in VALID_VISUAL_SOURCES:
        source = "auto"

    if source == "ai_image":
        return "ai_image"
    if source == "stock_video":
        return "stock_video"

    if source == "mixed":
        # Cảnh mở màn luôn dùng ảnh AI: hook cần kiểm soát bố cục 100%, không phó thác
        # cho kết quả tìm kiếm stock.
        if scene_index == 0:
            return "ai_image"
        emotion = (scene.get("emotion") or "").strip().lower()
        return "stock_video" if emotion in _STOCK_FRIENDLY_EMOTIONS else "ai_image"

    # auto: chỉ khi user chủ động bật, hoặc art_style do user chọn đúng là dòng
    # footage/tư liệu thật. KHÔNG dò image_prompt nữa (xem docstring).
    if req.prefer_stock_video:
        return "stock_video"
    art_style = (req.art_style or "").lower()
    if any(kw in art_style for kw in ("realistic", "photography", "documentary", "footage", "photoreal")):
        return "stock_video"
    return "ai_image"


def _estimate_scene_duration(text: str) -> float:
    """
    Ước lượng thời lượng cảnh từ số từ, dùng LÚC CHỌN clip stock.

    Cần thiết vì `_do_tts` và `_do_visuals` chạy song song (asyncio.gather) nên thời
    lượng thật từ word_boundaries CHƯA có khi ta phải quyết định tải clip nào. Con số
    này chỉ dùng để chấm điểm "clip có đủ dài không", còn việc cắt/ping-pong về đúng
    thời lượng thật thì làm sau, ở bước normalize_stock_clip.
    Giọng Việt Edge-TTS đọc ~2.6 từ/giây.
    """
    words = len((text or "").split())
    return max(3.0, words * 0.38 + 0.7)


def _compose_speech_rate(user_rate: str, scene_modifier: str) -> str:
    """
    CỘNG DỒN tốc độ đọc của user với `speech_rate_modifier` Gemini gán cho từng cảnh.

    LÝ DO: trước đây là phép GHI ĐÈ — hễ Gemini gán khác "0%" là tốc độ user chỉnh trên
    UI bị vứt bỏ hoàn toàn. Vì base prompt yêu cầu Gemini gán '+15%' cho hook, '-5%' cho
    giải thích..., gần như mọi cảnh đều ghi đè → thanh chỉnh tốc độ của user vô tác dụng.
    Cộng dồn giữ được cả ý đồ đạo diễn của Gemini lẫn quyền chỉnh tay của user.
    """
    def _parse(v: str) -> int:
        m = re.match(r'\s*([+-]?\d+)\s*%', v or "")
        return int(m.group(1)) if m else 0

    total = _parse(user_rate) + _parse(scene_modifier)
    # Chặn biên: quá ±50% thì giọng Edge-TTS méo và nghe không còn tự nhiên.
    total = max(-50, min(50, total))
    return f"{total:+d}%"


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
    imagen_aspect = aspect_ratio

    video_seed = None
    if req.use_fixed_seed or req.use_frame_chaining:
        import uuid
        video_seed = uuid.uuid4().int % 100000

    bgm_path = None
    if req.bgm_track:
        if req.bgm_track == "auto":
            import random
            available = [f for f in os.listdir(BGM_DIR) if f.endswith((".mp3", ".wav", ".ogg"))]
            if available:
                bgm_path = os.path.join(BGM_DIR, random.choice(available))
        else:
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

        from services import image_router
        import subprocess

        # Trạng thái Veo cho toàn job: nếu lỗi quota/permission (không thể tự hết trong
        # phiên render) → tắt Veo cho các cảnh còn lại, tránh lãng phí thời gian retry,
        # đồng thời báo rõ lý do lên UI thay vì fallback im lặng.
        veo_state = {"disabled": False}

        # Id các clip Pexels đã dùng trong job này — chặn 2 cảnh nhận về cùng 1 đoạn phim.
        stock_used_ids: set = set()

        # ── Single-Pass Narration: đọc TOÀN kịch bản trong 1 lần gọi ──
        # Phải chạy TRƯỚC vòng lặp vì mốc thời gian của mọi cảnh đều suy ra từ dải giọng này.
        master_audio_path = None
        narration_scene_wbs = None
        narration_total_dur = 0.0
        if req.use_single_pass_narration and mode != "photo_slideshow":
            await _update_job(job_id, message="Đang đọc liền mạch toàn bộ kịch bản (1 lần gọi)...")
            master_audio_path = os.path.join(job_dir_audio, "narration_master.mp3")
            try:
                scene_texts = [
                    tts_service._strip_emoji(s.get("text", "") or "").strip() for s in scenes
                ]
                narration_total_dur, narration_scene_wbs, _ = await tts_service.synthesize_script_single_pass(
                    scene_texts, master_audio_path,
                    voice=voice, rate=speech_rate, pitch=req.speech_pitch,
                )
                await _update_job(
                    job_id,
                    message=f"Đọc liền mạch xong ({narration_total_dur:.1f}s) — timeline sẽ bám theo giọng.",
                )
            except Exception as narr_err:
                # Giọng không hỗ trợ (OmniVoice/Minion) hoặc ánh xạ từ→cảnh hỏng →
                # quay về đọc từng cảnh, KHÔNG làm chết job.
                print(f"[Narration] Đọc liền mạch thất bại ({narr_err}). Quay về đọc từng cảnh.")
                await _update_job(
                    job_id,
                    message=f"⚠️ Không dùng được chế độ đọc liền mạch ({narr_err}). Đã chuyển về đọc từng cảnh.",
                )
                master_audio_path = None
                narration_scene_wbs = None

        for i, scene in enumerate(scenes):
            image_path = os.path.join(job_dir_images, f"scene_{i+1}.png")
            text = scene.get("text", "")
            
            # Loại bỏ các thẻ SSML <break> (nếu còn sót từ bộ đệm cũ) thay bằng dấu chấm lửng
            if "<break" in text:
                text = re.sub(r'<break[^>]*>', '...', text).strip()
            
            # Lọc emoji/icons tại nguồn — đảm bảo TẤT CẢ downstream (TTS, Subtitle, Checkpoint)
            # đều nhận text sạch, không cần lọc lại nhiều lần
            text = tts_service._strip_emoji(text).strip()
            text = re.sub(r'  +', ' ', text)  # Dọn khoảng trắng đôi
            scene["text"] = text

            img_prompt = scene.get("image_prompt", "")

            async def _do_tts():
                # Chế độ đọc liền mạch: giọng đã sinh xong trước vòng lặp. Không có file audio
                # riêng cho cảnh (audio_path=None) — cả bài dùng chung master_audio_path.
                if narration_scene_wbs is not None:
                    return 0.0, narration_scene_wbs[i], None
                if mode != "photo_slideshow" and text.strip():
                    a_path = os.path.join(job_dir_audio, f"scene_{i+1}.mp3")
                    wav_alt = a_path.replace(".mp3", ".wav")
                    # Check cache audio cũ
                    if os.path.exists(a_path) and os.path.getsize(a_path) > 0:
                        from mutagen.mp3 import MP3
                        try:
                            dur = MP3(a_path).info.length
                            return dur, scene.get("word_boundaries", []), a_path
                        except Exception: pass
                    if os.path.exists(wav_alt) and os.path.getsize(wav_alt) > 0:
                        import soundfile as sf
                        try:
                            info = sf.info(wav_alt)
                            return info.duration, scene.get("word_boundaries", []), wav_alt
                        except Exception: pass

                    await _update_job(job_id, message=f"Đang tạo giọng đọc cảnh {i+1}/{total}...")
                    
                    # Tạo callback để broadcast cảnh báo OmniVoice fallback qua WebSocket
                    async def _voice_warning(msg: str):
                        await _update_job(job_id, message=msg)
                    
                    dynamic_rate = scene.get("speech_rate_modifier", "0%")
                    final_rate = _compose_speech_rate(speech_rate, dynamic_rate)
                    
                    try:
                        dur, wbs = await tts_service.synthesize_speech(
                            text, a_path, voice=voice, rate=final_rate, pitch=req.speech_pitch, mode=mode,
                            emotion=scene.get("emotion", ""),
                            warning_callback=_voice_warning,
                            use_breathing=req.use_breathing
                        )
                        if os.path.exists(a_path) and os.path.getsize(a_path) > 0:
                            return dur, wbs, a_path
                        if os.path.exists(wav_alt) and os.path.getsize(wav_alt) > 0:
                            return dur, wbs, wav_alt
                    except Exception as e:
                        print(f"TTS Error for scene {i+1}: {e}")
                return 3.0, [], None

            async def _do_visuals():
                final_img_path = image_path
                mp4_alt = final_img_path.replace(".png", ".mp4")
                # Check cache visual cũ
                if os.path.exists(mp4_alt) and os.path.getsize(mp4_alt) > 0:
                    return mp4_alt
                if os.path.exists(final_img_path) and os.path.getsize(final_img_path) > 1000:
                    return final_img_path

                if mode in ("photo_narration", "photo_slideshow") and i < len(user_images):
                    import shutil
                    shutil.copy(user_images[i], final_img_path)
                    return final_img_path
                elif req.cover_image_session_id and (
                    (req.cover_image_position in ("start", "both") and i == 0) or
                    (req.cover_image_position in ("end", "both") and i == len(req.scenes) - 1)
                ):
                    cover_images = get_upload_paths(req.cover_image_session_id)
                    if cover_images:
                        import shutil
                        shutil.copy(cover_images[0], final_img_path)
                        return final_img_path
                    else:
                        await image_router.generate_image_with_fallback(
                            image_prompt=img_prompt, output_path=final_img_path,
                            aspect_ratio=imagen_aspect, google_api_key=api_key,
                            banana_mode=getattr(req, "banana_mode", False),
                            negative_prompt=req.negative_prompt, seed=video_seed,
                            art_style=req.art_style
                        )
                        return final_img_path
                elif req.use_veo and not veo_state["disabled"]:
                    await _update_job(job_id, message=f"Đang sinh Video AI (Veo) cho cảnh {i+1}/{total}...")
                    try:
                        from services.veo_service import generate_scene_video
                        video_path = await generate_scene_video(
                            scene_prompt=img_prompt, aspect_ratio=aspect_ratio,
                            use_fast_model=True, negative_prompt=req.negative_prompt or ""
                        )
                        return video_path
                    except Exception as veo_err:
                        err_str = str(veo_err)
                        # Lỗi quota/billing/permission → không thể tự hết trong phiên này:
                        # tắt Veo cho các cảnh còn lại + báo rõ lý do lên UI.
                        if any(sig in err_str for sig in ("429", "RESOURCE_EXHAUSTED", "403", "PERMISSION_DENIED", "billed")):
                            veo_state["disabled"] = True
                            await _update_job(
                                job_id,
                                message=(
                                    "⚠️ Veo 3 không khả dụng: API key hiện tại chưa bật billing "
                                    "(Google yêu cầu gói trả phí cho Veo). Tự động dùng "
                                    "Pexels Video / Ảnh AI + Ken Burns cho toàn bộ video."
                                ),
                            )
                        print(f"Veo Error for scene {i+1}: {veo_err}. Tự động fallback sang Pexels Video / Image Router...")
                        pexels_key = os.getenv("PEXELS_API_KEY")
                        if pexels_key:
                            try:
                                from services.gemini_service import extract_search_keyword
                                query = await extract_search_keyword(img_prompt, api_key)
                                return await image_router.fetch_pexels_video(
                                    query, final_img_path, imagen_aspect, pexels_key,
                                    needed_duration=_estimate_scene_duration(text),
                                    used_ids=stock_used_ids,
                                )
                            except Exception as pex_v_err:
                                print(f"Pexels Video fallback failed: {pex_v_err}")
                        return await image_router.generate_image_with_fallback(
                            image_prompt=img_prompt, output_path=final_img_path,
                            aspect_ratio=imagen_aspect, google_api_key=api_key,
                            banana_mode=getattr(req, "banana_mode", False),
                            negative_prompt=req.negative_prompt, seed=video_seed,
                            art_style=req.art_style
                        )
                else:
                    pexels_key = os.getenv("PEXELS_API_KEY")
                    want_stock = _pick_visual_source(req, scene, i) == "stock_video"
                    if want_stock and pexels_key:
                        await _update_job(job_id, message=f"Đang tìm video Pexels cho cảnh {i+1}/{total}...")
                        try:
                            from services.gemini_service import extract_search_keyword
                            query = await extract_search_keyword(img_prompt, api_key)
                            pexels_vid = await image_router.fetch_pexels_video(
                                query, final_img_path, imagen_aspect, pexels_key,
                                needed_duration=_estimate_scene_duration(text),
                                used_ids=stock_used_ids,
                            )
                            return pexels_vid
                        except Exception as pexels_err:
                            print(f"Pexels video cho cảnh {i+1} thất bại ({pexels_err}). Rơi về ảnh AI.")

                    await _update_job(job_id, message=f"Đang sinh ảnh AI cho cảnh {i+1}/{total}...")
                    try:
                        await image_router.generate_image_with_fallback(
                            image_prompt=img_prompt, output_path=final_img_path,
                            aspect_ratio=imagen_aspect, google_api_key=api_key,
                            banana_mode=getattr(req, "banana_mode", False),
                            negative_prompt=req.negative_prompt, seed=video_seed,
                            art_style=req.art_style
                        )
                    except Exception as img_err:
                        _create_placeholder_image(final_img_path)
                    return final_img_path

            # Chạy song song TTS và Sinh ảnh (Giảm 50% thời gian!)
            (scene_duration, scene_wbs, audio_path), image_path = await asyncio.gather(_do_tts(), _do_visuals())
            
            scene["image_path"] = image_path
            scene["audio_path"] = audio_path
            # computed_duration sẽ được tính lại chính xác hơn trong build_scene_timeline (motion_effects)
            scene["computed_duration"] = scene_duration
            scene["word_boundaries"] = scene_wbs

            # Checkpoint tự động lưu project state sau từng scene
            from services import project_service
            import time
            project_service.save_project_state(job_id, {
                "job_id": job_id,
                "title": getattr(req, "topic", None) or f"Dự án {job_id[:8]}",
                "mode": mode,
                "scenes": scenes,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": "generating_assets",
                "req": req.model_dump(mode='json')
            })

        # ── Tính toán Timeline chính xác theo word_boundaries ──
        await _update_job(job_id, message="Tính toán Timeline & Sync...")
        from services.motion_effects import build_scene_timeline, build_timeline_from_narration
        from services.video_service import CROSSFADE_DURATION, SLIDESHOW_CROSSFADE
        cf_dur = SLIDESHOW_CROSSFADE if mode == "photo_slideshow" else CROSSFADE_DURATION
        if narration_scene_wbs is not None:
            # Hình bám theo giọng: mốc cắt cảnh lấy từ thời điểm giọng bước sang câu kế tiếp.
            scenes = build_timeline_from_narration(
                scenes, narration_scene_wbs, narration_total_dur, overlap_dur=cf_dur
            )
        else:
            scenes = build_scene_timeline(scenes, overlap_dur=cf_dur)

        # ── Beat Sync: snap điểm cắt cảnh theo nhịp nhạc (nếu user bật) ──
        if req.use_beat_sync and bgm_path and os.path.isfile(bgm_path):
            try:
                await _update_job(job_id, message="Đồng bộ nhịp nhạc (Beat Sync)...")
                from services.beat_sync import apply_beat_sync_to_timeline
                scenes = await asyncio.to_thread(apply_beat_sync_to_timeline, scenes, bgm_path)
            except Exception as bs_err:
                print(f"Beat Sync warning (non-fatal): {bs_err}")

        # ── Hook Máy Xèng: đẩy TOÀN BỘ mốc thời gian lùi lại để giọng đọc không bị
        # tiếng trục quay đè lên. Chỉ dời tiếng + phụ đề; lớp phủ hook vẫn ở 0-3.5s.
        # Đặt SAU beat sync vì beat sync tự tính lại start_time từ duration.
        if req.hook_effect == "carousel_quote":
            from services.video_service import HOOK_NARRATION_LEAD
            for s in scenes:
                s["start_time"] = s.get("start_time", 0.0) + HOOK_NARRATION_LEAD
            await _update_job(
                job_id,
                message=f"Dời giọng đọc {HOOK_NARRATION_LEAD}s để tránh đè tiếng Máy Xèng...",
            )

        scene_assets = []
        from services.motion_effects import apply_ken_burns, resolve_motion, normalize_stock_clip
        from services.video_service import ASPECT_RATIO_SIZES
        frame_size = ASPECT_RATIO_SIZES.get(aspect_ratio, (1080, 1920))
        for i, s in enumerate(scenes):
            scene_effect = s.get("visual_effect", "")

            img_path = s["image_path"]
            duration = s.get("computed_duration", 3.0)
            start_time = s.get("start_time", 0.0)

            # Apply Ken Burns via FFmpeg if it's an image (và user chưa tắt cờ use_ken_burns)
            is_video_asset = img_path.lower().endswith((".mp4", ".mov"))
            if not is_video_asset and req.use_ken_burns:
                await _update_job(job_id, message=f"Đang xử lý chuyển động (Ken Burns) cho cảnh {i+1}...")
                out_mp4 = img_path + f"_{i}.mp4"
                # Hook Zoom Boost: cảnh đầu zoom mạnh hơn (1.0→1.35) tạo "cú đấm" thị giác
                # giữ chân người xem trong 2-3 giây đầu. Đây là cờ bật/tắt thật sự.
                hook_boost = bool(i == 0 and req.hook_zoom_boost)
                pan_dir, kb_zoom_start, kb_zoom_end = resolve_motion(scene_effect, i, hook_boost=hook_boost)
                await asyncio.to_thread(
                    apply_ken_burns,
                    image_path=img_path, output_path=out_mp4, duration=duration, fps=30,
                    pan_direction=pan_dir, zoom_start=kb_zoom_start, zoom_end=kb_zoom_end
                )
                img_path = out_mp4
            elif is_video_asset:
                # Clip stock/Veo: cắt đúng thời lượng cảnh (ưu tiên đoạn giữa), ping-pong nếu
                # ngắn, ép về đúng khung + đồng chất màu. Lỗi thì giữ nguyên file gốc —
                # video_service vẫn tự xử lý được, chỉ là không đẹp bằng.
                await _update_job(job_id, message=f"Đang chuẩn hoá clip nền cảnh {i+1}...")
                norm_mp4 = f"{os.path.splitext(img_path)[0]}_norm{i}.mp4"
                try:
                    await asyncio.to_thread(
                        normalize_stock_clip,
                        video_path=img_path, output_path=norm_mp4, duration=duration,
                        resolution=frame_size, fps=30,
                    )
                    img_path = norm_mp4
                except Exception as norm_err:
                    print(f"[StockNorm] Cảnh {i+1} chuẩn hoá thất bại ({norm_err}). Dùng clip gốc.")

            # Hook SFX: tự thêm 'riser' mở màn cho cảnh đầu nếu bật Hook Zoom Boost + SFX
            # và cảnh chưa có sẵn hiệu ứng âm thanh nào.
            scene_sfx = s.get("sfx", "")
            if i == 0 and req.hook_zoom_boost and req.use_sfx and not scene_sfx:
                scene_sfx = "riser"

            scene_assets.append({
                "image_path": img_path,
                "audio_path": s.get("audio_path"),
                "text": s.get("text", ""),
                "duration": duration,
                "sfx": scene_sfx,
                "visual_effect": scene_effect,
                "word_boundaries": s.get("word_boundaries", []),
                "transition": s.get("transition", "crossfade"),
                "start_time": start_time,
                "highlight_text": s.get("highlight_text", ""),
            })
            
        await _update_job(job_id, status="rendering", message="Đang render video...", progress=80)

        output_video_path = os.path.join(OUTPUT_DIR, f"{job_id}.mp4")
        output_srt_path = os.path.join(OUTPUT_DIR, f"{job_id}.ass")
        raw_video = output_video_path + ".raw.mp4"
        
        # ══════════════════════════════════════════════════════════
        # Phase 2: Render — OFFLOAD sang process con riêng biệt
        # MoviePy + FFmpeg là CPU-bound nặng, chạy trong process con
        # để không block FastAPI event loop
        # ══════════════════════════════════════════════════════════
        from services.render_worker import spawn_render, read_status as read_render_status

        render_kwargs = dict(
            aspect_ratio=aspect_ratio,
            bgm_path=None,  # BGM được mix bởi FFmpeg
            mode=mode,
            hook_text=req.hook_text,
            use_sfx=req.use_sfx,
            sfx_volume=req.sfx_volume if req.sfx_volume is not None else 0.5,
            hook_effect=req.hook_effect,   # để render_final_video dựng hook carousel_quote
            hook_quote=req.hook_quote,
            hook_reel_sfx=req.hook_reel_sfx,
            master_audio_path=master_audio_path,  # chế độ đọc liền mạch (None nếu tắt)
        )
        master_kwargs = dict(
            bgm_path=bgm_path,
            use_gpu=req.use_gpu_encode,
            bgm_volume=req.bgm_volume,
            watermark_text=req.watermark_text,
            color_grading=req.color_grading,
            subtitle_style=req.subtitle_style,
            hook_effect=req.hook_effect,
        )

        spawned = spawn_render(
            job_id=job_id,
            scene_assets=scene_assets,
            raw_video_path=raw_video,
            output_video_path=output_video_path,
            output_srt_path=output_srt_path,
            render_kwargs=render_kwargs,
            master_kwargs=master_kwargs,
        )

        if not spawned:
            # Nếu đạt giới hạn worker → fallback chạy inline (giữ backward-compatible)
            await _update_job(job_id, message="Hàng đợi render đầy. Đang render trực tiếp...")
            await asyncio.to_thread(
                video_service.render_final_video,
                scene_assets, raw_video,
                aspect_ratio=aspect_ratio, bgm_path=None, mode=mode,
                hook_text=req.hook_text, use_sfx=req.use_sfx,
                sfx_volume=req.sfx_volume if req.sfx_volume is not None else 0.5,
                hook_effect=req.hook_effect, hook_quote=req.hook_quote,
                hook_reel_sfx=req.hook_reel_sfx,
                master_audio_path=master_audio_path,
            )
            if mode != "photo_slideshow":
                await asyncio.to_thread(
                    video_service.generate_ass_file, scene_assets, output_srt_path,
                    mode, subtitle_style=req.subtitle_style,
                    hook_text=req.hook_text, hook_effect=req.hook_effect,
                )
            await _update_job(job_id, message="Đang Mastering Âm thanh & Tối ưu Video...", progress=90)
            from services.audio_mix_service import master_audio_and_export
            try:
                await asyncio.to_thread(
                    master_audio_and_export,
                    input_video_path=raw_video, output_path=output_video_path,
                    bgm_path=bgm_path,
                    ass_subtitle_path=output_srt_path if os.path.isfile(output_srt_path) else None,
                    use_gpu=req.use_gpu_encode, bgm_volume=req.bgm_volume,
                    watermark_text=req.watermark_text, color_grading=req.color_grading,
                )
                if os.path.isfile(raw_video):
                    os.remove(raw_video)
            except Exception as err:
                print(f"FFmpeg Mastering error: {err}")
                if os.path.isfile(raw_video) and not os.path.isfile(output_video_path):
                    os.rename(raw_video, output_video_path)
            await _update_job(
                job_id, status="done", progress=100, message="Hoàn tất!",
                video_url=f"/api/download/{job_id}.mp4",
                srt_url=f"/api/download/{job_id}.ass" if mode != "photo_slideshow" else None,
            )
        else:
            # Worker đang chạy → poll file status và broadcast qua WebSocket
            while True:
                await asyncio.sleep(2)
                ws = read_render_status(job_id)
                if ws is None:
                    continue
                await _update_job(
                    job_id,
                    status=ws.get("status", "rendering"),
                    progress=ws.get("progress", 80),
                    message=ws.get("message", "Đang render..."),
                    video_url=ws.get("video_url"),
                    srt_url=ws.get("srt_url"),
                    error=ws.get("error"),
                )
                if ws.get("status") in ("done", "error"):
                    from services.render_worker import cleanup_status
                    cleanup_status(job_id)
                    break

    except Exception as e:
        print(f"Exception in pipeline: {e}")
        await _update_job(job_id, status="error", error=str(e), message=f"Lỗi: {e}")
        # Giữ lại ảnh/audio đã sinh khi lỗi để có thể sinh lại từng cảnh / resume,
        # thay vì xoá sạch khiến lần sau phải chạy lại toàn bộ.
        if req.upload_session_id:
            cleanup_upload(req.upload_session_id)
        return

    # Chỉ dọn asset tạm khi pipeline thành công.
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
    now = datetime.now(timezone.utc).timestamp()
    for fname in os.listdir(OUTPUT_DIR):
        fpath = os.path.join(OUTPUT_DIR, fname)
        if os.path.isfile(fpath):
            age_hours = (now - os.path.getmtime(fpath)) / 3600
            if age_hours > max_age_hours:
                os.remove(fpath)


def _prune_old_jobs(max_jobs: int = 200):
    """Giới hạn kích thước JOBS in-memory: xoá bớt job cũ nhất đã kết thúc để tránh rò rỉ RAM."""
    if len(JOBS) <= max_jobs:
        return
    finished = [
        (jid, j) for jid, j in JOBS.items()
        if j.status in ("done", "error")
    ]
    finished.sort(key=lambda kv: kv[1].created_at)
    for jid, _ in finished[: len(JOBS) - max_jobs]:
        JOBS.pop(jid, None)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
from services import quota_service

@app.get("/api/quota")
async def get_quota():
    return quota_service.get_quota()

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
                character_description=req.character_description,
                sync_characters=req.sync_characters,
                content_niche=req.content_niche,
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
    except HTTPException:
        # Giữ nguyên status code gốc (400 thiếu topic/script...) thay vì bọc thành 500.
        raise
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

    _prune_old_jobs()
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
    """Trả về danh sách giọng đọc tiếng Việt (gồm cả giọng clone cá nhân)."""
    return {"voices": tts_service.get_available_voices()}


@app.get("/api/tts-health")
async def tts_health():
    """Trạng thái hạ tầng TTS: OmniVoice/GPU/whisper-align sẵn sàng hay chưa."""
    return tts_service.get_tts_health()


@app.on_event("startup")
async def _startup_warmup():
    """Warmup OmniVoice + whisper-align trong background (tắt bằng OMNIVOICE_WARMUP=0)."""
    if os.getenv("OMNIVOICE_WARMUP", "1") != "0":
        asyncio.create_task(tts_service.warmup_omnivoice())


# ---------------------------------------------------------------------------
# Voice Cloning (Phase 3) — upload mẫu giọng 5-10s → giọng OmniVoice cá nhân
# ---------------------------------------------------------------------------
ALLOWED_VOICE_SAMPLE_EXTS = {".wav", ".mp3", ".m4a", ".ogg", ".flac"}
MAX_VOICE_SAMPLE_SIZE = 15 * 1024 * 1024  # 15MB


@app.post("/api/voice-clone")
async def create_voice_clone(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    transcript: Optional[str] = Form(None),
):
    """
    Nhận file mẫu giọng (5-10s) → chuẩn hóa 24kHz mono WAV làm reference cho
    OmniVoice Voice Cloning. Nếu không có transcript, tự nhận dạng bằng whisper.
    Trả về voice_id để chọn trong danh sách giọng đọc.
    """
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_VOICE_SAMPLE_EXTS:
        raise HTTPException(status_code=400, detail=f"Định dạng không hỗ trợ. Chấp nhận: {', '.join(sorted(ALLOWED_VOICE_SAMPLE_EXTS))}")
    content = await file.read()
    if len(content) > MAX_VOICE_SAMPLE_SIZE:
        raise HTTPException(status_code=400, detail="File mẫu giọng vượt quá 15MB.")
    if len(content) < 10_000:
        raise HTTPException(status_code=400, detail="File mẫu quá ngắn. Cần đoạn nói rõ ràng 5-10 giây.")

    voice_id = f"omnivoice_custom_{uuid.uuid4().hex[:8]}"
    preview_dir = tts_service.VOICES_PREVIEW_DIR
    os.makedirs(preview_dir, exist_ok=True)

    raw_path = os.path.join(preview_dir, f"{voice_id}_src{ext}")
    ref_wav_path = os.path.join(preview_dir, f"{voice_id}_ref.wav")
    preview_mp3_path = os.path.join(preview_dir, f"{voice_id}.mp3")
    with open(raw_path, "wb") as f:
        f.write(content)

    def _convert():
        """Chuẩn hóa mẫu về 24kHz mono WAV (tối đa 15s) + xuất mp3 preview."""
        import subprocess
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run(
            [ffmpeg_exe, "-y", "-i", raw_path, "-t", "15", "-ar", "24000", "-ac", "1", ref_wav_path],
            check=True, capture_output=True, timeout=120,
        )
        subprocess.run(
            [ffmpeg_exe, "-y", "-i", ref_wav_path, "-b:a", "128k", preview_mp3_path],
            check=True, capture_output=True, timeout=120,
        )

    try:
        await asyncio.to_thread(_convert)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Không thể xử lý file âm thanh: {e}")
    finally:
        if os.path.exists(raw_path):
            try:
                os.remove(raw_path)
            except OSError:
                pass

    # Transcript: user cung cấp hoặc tự nhận dạng bằng whisper (cần cho ref_text của cloning)
    ref_text = (transcript or "").strip()
    if not ref_text:
        def _transcribe():
            model = tts_service._get_whisper_model()
            result = model.transcribe(ref_wav_path, language="vi")
            return " ".join(seg.text.strip() for seg in result.segments).strip()
        try:
            ref_text = await asyncio.to_thread(_transcribe)
        except Exception as e:
            print(f"[VoiceClone] Whisper transcribe lỗi: {e}")
    if not ref_text:
        ref_text = "Chào bạn, đây là giọng đọc tham khảo để đồng bộ video."

    display_name = (name or "").strip() or f"Giọng của tôi {voice_id[-4:]}"
    entry = tts_service.register_custom_voice(voice_id, display_name, ref_text)
    return {
        "voice_id": voice_id,
        "name": display_name,
        "ref_text": ref_text,
        "message": "Đã tạo giọng clone thành công. Chọn giọng này trong danh sách Giọng đọc.",
        "voice": entry,
    }


@app.delete("/api/voice-clone/{voice_id}")
async def delete_voice_clone(voice_id: str):
    """Xóa giọng clone cá nhân (registry + file mẫu)."""
    safe_id = os.path.basename(voice_id)
    if not safe_id.startswith("omnivoice_custom_"):
        raise HTTPException(status_code=400, detail="Chỉ xóa được giọng clone cá nhân.")
    if not tts_service.remove_custom_voice(safe_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy giọng clone này.")
    return {"message": "Đã xóa giọng clone."}


from services import preset_service

@app.get("/api/presets")
async def get_presets():
    """Trả về danh sách tất cả các preset đã lưu."""
    return {"presets": preset_service.load_presets()}

@app.post("/api/presets")
async def create_preset(req: PresetRequest):
    """Lưu 1 preset mới."""
    if not req.name or not req.name.strip():
        raise HTTPException(status_code=400, detail="Thiếu tên preset.")
    new_preset = preset_service.add_preset(req.model_dump())
    return {"message": "Đã lưu preset thành công.", "preset": new_preset}

@app.delete("/api/presets/{preset_id}")
async def delete_preset(preset_id: str):
    """Xóa 1 preset."""
    success = preset_service.delete_preset(preset_id)
    if not success:
        raise HTTPException(status_code=400, detail="Không thể xóa preset này (preset mặc định hoặc không tồn tại).")
    return {"message": "Đã xóa preset thành công."}


@app.get("/api/preview/{type}/{id}")
async def preview_media(type: str, id: str):
    """Phát thử nhạc nền (BGM) hoặc giọng đọc mẫu."""
    from fastapi.responses import FileResponse
    # Chống path traversal: chỉ lấy phần basename, loại bỏ mọi thành phần thư mục.
    safe_id = os.path.basename(id)
    if type == "bgm":
        bgm_path = os.path.join(BGM_DIR, f"{safe_id}.mp3")
        if os.path.isfile(bgm_path):
            return FileResponse(bgm_path)
    elif type == "voice":
        voice_path = os.path.join(ASSETS_DIR, "voices_preview", f"{safe_id}.mp3")
        if os.path.isfile(voice_path):
            return FileResponse(voice_path)
    elif type == "sfx":
        sfx_path = os.path.join(ASSETS_DIR, "sfx", f"{safe_id}.wav")
        if os.path.isfile(sfx_path):
            return FileResponse(sfx_path)
    elif type == "hook_sfx":
        from services.video_service import HOOK_REEL_SOUNDS, DEFAULT_HOOK_REEL
        filename = HOOK_REEL_SOUNDS.get(safe_id, HOOK_REEL_SOUNDS.get(DEFAULT_HOOK_REEL, "reel_spin.wav"))
        hook_sfx_path = os.path.join(ASSETS_DIR, "sfx", filename)
        if os.path.isfile(hook_sfx_path):
            return FileResponse(hook_sfx_path)

    raise HTTPException(status_code=404, detail="Không tìm thấy file nghe thử.")


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

    # Chống path traversal: chỉ cho phép basename nằm trong OUTPUT_DIR.
    safe_name = os.path.basename(filename)
    file_path = os.path.join(OUTPUT_DIR, safe_name)
    if os.path.commonpath((os.path.abspath(file_path), OUTPUT_DIR)) != OUTPUT_DIR:
        raise HTTPException(status_code=400, detail="Tên file không hợp lệ.")
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File không tồn tại hoặc đã bị xoá.")
    return FileResponse(file_path)


@app.get("/")
async def health_check():
    return {"status": "ok", "service": "AI Video Studio API v2"}


# ---------------------------------------------------------------------------
# Project Management & Single Scene Editing Endpoints
# ---------------------------------------------------------------------------
from services import project_service

class RegenerateSceneImageRequest(BaseModel):
    new_prompt: Optional[str] = None
    aspect_ratio: Optional[str] = "9:16"
    art_style: Optional[str] = None

@app.get("/api/projects")
async def list_user_projects():
    """Liệt kê các dự án đã lưu."""
    return {"projects": project_service.list_projects()}

@app.get("/api/projects/{job_id}")
async def get_project_detail(job_id: str):
    """Tải thông tin dự án chi tiết."""
    state = project_service.load_project_state(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án này.")
    return state

@app.post("/api/projects/{job_id}/scenes/{scene_idx}/regenerate-image")
async def regenerate_scene_image(job_id: str, scene_idx: int, req: RegenerateSceneImageRequest):
    """Sinh lại ảnh AI riêng cho phân cảnh scene_idx."""
    state = project_service.load_project_state(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="Dự án không tồn tại.")
    scenes = state.get("scenes", [])
    if scene_idx < 0 or scene_idx >= len(scenes):
        raise HTTPException(status_code=400, detail="Chỉ số phân cảnh không hợp lệ.")
    
    scene = scenes[scene_idx]
    prompt = req.new_prompt or scene.get("image_prompt", "")
    job_dir_images = os.path.join(IMAGES_DIR, job_id)
    os.makedirs(job_dir_images, exist_ok=True)
    img_path = os.path.join(job_dir_images, f"scene_{scene_idx+1}.png")
    
    # Xóa file cũ nếu có để buộc vẽ lại
    if os.path.exists(img_path):
        os.remove(img_path)
    mp4_alt = img_path.replace(".png", ".mp4")
    if os.path.exists(mp4_alt):
        os.remove(mp4_alt)

    from services import image_router
    new_path = await image_router.generate_image_with_fallback(
        image_prompt=prompt,
        output_path=img_path,
        aspect_ratio=req.aspect_ratio or "9:16",
        art_style=req.art_style
    )
    
    project_service.update_scene_asset(job_id, scene_idx, image_path=new_path, image_prompt=prompt)
    return {"message": f"Đã sinh lại ảnh cho cảnh {scene_idx+1} thành công.", "image_path": new_path}

@app.post("/api/projects/{job_id}/scenes/{scene_idx}/upload-image")
async def upload_scene_image(job_id: str, scene_idx: int, file: UploadFile = File(...)):
    """Upload bức ảnh tùy chỉnh cho riêng phân cảnh scene_idx."""
    state = project_service.load_project_state(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="Dự án không tồn tại.")
    scenes = state.get("scenes", [])
    if scene_idx < 0 or scene_idx >= len(scenes):
        raise HTTPException(status_code=400, detail="Chỉ số phân cảnh không hợp lệ.")

    job_dir_images = os.path.join(IMAGES_DIR, job_id)
    os.makedirs(job_dir_images, exist_ok=True)
    img_path = os.path.join(job_dir_images, f"scene_{scene_idx+1}.png")
    
    content = await file.read()
    with open(img_path, "wb") as f:
        f.write(content)
        
    project_service.update_scene_asset(job_id, scene_idx, image_path=img_path)
    return {"message": f"Đã cập nhật ảnh tùy chỉnh cho cảnh {scene_idx+1}.", "image_path": img_path}

