"""
pipeline_orchestrator.py
------------------------
Refactored render pipeline extracted from main.py::_run_render_pipeline.

Encapsulates the full render pipeline as distinct phases:
  TTS  →  IMAGES  →  TIMELINE  →  RENDER

Each phase is a separate method with typed dicts as inputs/outputs.
Phase enum enables simple progress reporting via _update_job.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import shutil
import time
import uuid
from enum import Enum, auto
from typing import Any, Dict, List, Optional, TypedDict

from config import (
    AUDIO_DIR,
    BGM_DIR,
    DATA_DIR,
    IMAGES_DIR,
    OUTPUT_DIR,
    OVERRIDES_DIR,
    RENDER_STATUS_DIR,
    WATERMARKS_DIR,
)
from services import tts_service
from services.beat_sync import apply_beat_sync_to_timeline
from services.image_upload_service import cleanup_upload, get_upload_paths
from services.motion_effects import (
    apply_ken_burns,
    build_scene_timeline,
    build_timeline_from_narration,
    normalize_stock_clip,
    resolve_motion,
)
from services.render_worker import (
    cancel_render,
    cleanup_status,
    is_render_active,
    read_status as read_render_status,
    spawn_render,
)
from services.render_worker import MAX_CONCURRENT_RENDERS
# RENDER_POLL_INTERVAL and RENDER_STALL_TIMEOUT are defined in main.py
from main import RENDER_POLL_INTERVAL, RENDER_STALL_TIMEOUT
from services.video_service import (
    VOICE_SIDECHAIN_SUFFIX,
    ASPECT_RATIO_SIZES,
    CROSSFADE_DURATION,
    SLIDESHOW_CROSSFADE,
    render_final_video,
    resolve_hook_timing,
    resolve_outro_text,
    resolve_outro_timing,
)
from services import image_router

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Typed dicts for phase I/O
# ---------------------------------------------------------------------------

class TTSResult(TypedDict):
    scene_audio_paths: List[Optional[str]]
    master_audio_path: Optional[str]
    tts_warnings: List[str]


class ImageResult(TypedDict):
    scene_image_paths: List[str]
    veo_state: Dict[str, Any]
    stock_used_ids: set


class TimelineResult(TypedDict):
    timeline: List[Dict[str, Any]]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Phase(Enum):
    PENDING = "pending"
    TTS = "tts"
    IMAGES = "images"
    TIMELINE = "timeline"
    RENDER = "render"
    DONE = "done"
    ERROR = "error"


class PipelineOrchestrator:
    """
    Encapsulates the entire video render pipeline as distinct phases.

    Usage:
        orchestrator = PipelineOrchestrator(job_id, req)
        await orchestrator.execute()
    """

    def __init__(self, job_id: str, req: Any):
        self.job_id = job_id
        self.req = req

        self.mode = req.mode
        self.api_key = req.gemini_api_key
        self.voice = req.voice or tts_service.DEFAULT_VOICE
        self.speech_rate = req.speech_rate or "+0%"
        self.aspect_ratio = req.aspect_ratio if req.aspect_ratio in {"9:16", "16:9", "1:1"} else "9:16"
        self.imagen_aspect = self.aspect_ratio

        # Shared state across phases
        self.render_failed = False
        self.scenes = req.scenes
        self.total = len(req.scenes)
        self.job_dir_audio = os.path.join(AUDIO_DIR, job_id)
        self.job_dir_images = os.path.join(IMAGES_DIR, job_id)

        # Per-job state
        self.veo_state: Dict[str, Any] = {"disabled": False}
        self.stock_used_ids: set = set()
        self.tts_warned: set = set()
        self.master_audio_path: Optional[str] = None
        self.narration_scene_wbs: Optional[List[Any]] = None
        self.narration_total_dur: float = 0.0
        self.user_images: List[str] = []
        self.intro_bgm_path: Optional[str] = None
        self.bgm_path: Optional[str] = None
        self.video_seed: Optional[int] = None
        self.frame_size: tuple[int, int] = ASPECT_RATIO_SIZES.get(self.aspect_ratio, (1080, 1920))
        self.hook_timing: Optional[Dict[str, Any]] = None

    # -------------------------------------------------------------------------
    # Public entry point
    # -------------------------------------------------------------------------

    async def execute(self) -> None:
        """
        Main async orchestration method. OPTIMIZED: TTS và Image chạy SONG SONG.

        Luồng cũ (tuần tự - SLOW):
          Phase 1: TTS tất cả scenes → Phase 2: Images tất cả scenes

        Luồng mới (song song - FAST):
          Vòng lặp: Với mỗi scene i, chạy TTS[i] + Image[i] SONG SONG
          Tổng thời gian = max(tong_TTS, tong_Image) thay vì tong_TTS + tong_Image

        All assets (audio/images) are preserved on failure for resumable renders;
        only deleted on full success.
        """
        # Attach job_id to every log line from here onward
        from services.log_setup import set_job_id
        set_job_id(self.job_id)

        os.makedirs(self.job_dir_audio, exist_ok=True)
        os.makedirs(self.job_dir_images, exist_ok=True)

        try:
            # ── Pre-flight: BGM, intro BGM, video seed ──────────────────────
            await self._preflight()

            # ── OPTIMIZED: TTS + Images SONG SONG ─────────────────────────
            # Thay vì: Phase 1 TTS (xong hết) → Phase 2 Images (xong hết)
            # Ta chạy: Với mỗi scene, TTS + Image SONG SONG
            tts_result, image_result = await self.run_parallel_tts_and_images()

            self.master_audio_path = tts_result["master_audio_path"]
            self.narration_scene_wbs = tts_result.get("narration_scene_wbs")
            self.narration_total_dur = tts_result.get("narration_total_dur", 0.0)
            for warn in tts_result.get("tts_warnings", []):
                await self._update_job(message=warn)

            # ── Phase 3: Timeline ──────────────────────────────────────────
            timeline_result = await self.compute_timeline(tts_result, image_result)
            scene_assets = timeline_result["timeline"]

            # ── Phase 4: Render ─────────────────────────────────────────────
            kwargs = self._build_render_kwargs()
            output_path = await self.run_render_phase(scene_assets, kwargs)

            if output_path and os.path.isfile(output_path):
                await self._update_job(
                    status="done", progress=100, message="Hoàn tất!",
                    video_url=f"/api/download/{self.job_id}.mp4",
                    srt_url=f"/api/download/{self.job_id}.ass"
                    if self.mode != "photo_slideshow" else None,
                )
            else:
                await self._update_job(
                    status="error",
                    error="Không tạo được file video đầu ra",
                    message=(
                        "Lỗi render cuối cùng. "
                        "Xem backend/logs/main.log để biết chi tiết."
                    ),
                )
                self.render_failed = True

        except Exception as e:
            logger.error("Exception in pipeline: %s", e, exc_info=True)
            await self._update_job(status="error", error=str(e), message=f"Lỗi: {e}")
            if self.req.upload_session_id:
                cleanup_upload(self.req.upload_session_id)
            return

        finally:
            await self._cleanup()

    # -------------------------------------------------------------------------
    # Phase 1: TTS
    # -------------------------------------------------------------------------

    async def run_tts_phase(self, scenes: List[Dict[str, Any]]) -> TTSResult:
        """
        Handles single-pass narration + per-scene TTS synthesis.

        Returns:
            TTSResult with scene_audio_paths, master_audio_path, narration_scene_wbs,
            narration_total_dur, and tts_warnings.
        """
        self.phase = Phase.TTS
        await self._update_job(status="generating_assets")

        # ── Single-pass narration (reads entire script in one TTS call) ────────
        master_audio_path: Optional[str] = None
        narration_scene_wbs: Optional[List[Any]] = None
        narration_total_dur: float = 0.0
        tts_warnings: List[str] = []

        if self.req.use_single_pass_narration and self.mode != "photo_slideshow":
            await self._update_job(
                message="Đang đọc liền mạch toàn bộ kịch bản (1 lần gọi)..."
            )
            master_audio_path = os.path.join(self.job_dir_audio, "narration_master.mp3")
            try:
                scene_texts = [
                    tts_service.strip_break_tags(
                        tts_service._strip_emoji(s.get("text", "") or "")
                    ).strip()
                    for s in scenes
                ]
                narration_total_dur, narration_scene_wbs, _ = (
                    await tts_service.synthesize_script_single_pass(
                        scene_texts, master_audio_path,
                        voice=self.voice, rate=self.speech_rate,
                        pitch=getattr(self.req, "speech_pitch", None),
                        warning_callback=self._tts_warning_once,
                    )
                )
                await self._update_job(
                    message=f"Đọc liền mạch xong ({narration_total_dur:.1f}s) "
                    "— timeline sẽ bám theo giọng.",
                )
            except Exception as narr_err:
                logger.warning(
                    "[Narration] Đọc liền mạch thất bại (%s). Quay về đọc từng cảnh.",
                    narr_err,
                )
                await self._update_job(
                    message=f"⚠️ Không dùng được chế độ đọc liền mạch ({narr_err}). "
                    "Đã chuyển về đọc từng cảnh.",
                )
                master_audio_path = None
                narration_scene_wbs = None

        scene_audio_paths: List[Optional[str]] = [None] * len(scenes)

        for i, scene in enumerate(scenes):
            # Skip TTS for photo_slideshow or empty scenes
            if self.mode == "photo_slideshow":
                continue

            text_raw = scene.get("text", "") or ""
            tts_text = tts_service._strip_emoji(text_raw).strip()
            tts_text = re.sub(r'  +', ' ', tts_text)
            text = tts_service.strip_break_tags(tts_text)
            scene["text"] = text

            if narration_scene_wbs is not None:
                # Single-pass mode: audio already generated before the loop
                _, wbs, _ = narration_scene_wbs[i]
                scene_audio_paths[i] = None  # shared master_audio_path used
                scene["word_boundaries"] = wbs
                scene["computed_duration"] = 0.0
                continue

            if not text.strip():
                pause_s = scene.get("pause_after_ms", 0) / 1000.0
                scene["computed_duration"] = 3.0 + pause_s
                scene["word_boundaries"] = []
                scene_audio_paths[i] = None
                continue

            a_path = os.path.join(self.job_dir_audio, f"scene_{i+1}.mp3")
            wav_alt = a_path.replace(".mp3", ".wav")

            # Check audio cache
            if os.path.exists(a_path) and os.path.getsize(a_path) > 0:
                from mutagen.mp3 import MP3
                try:
                    dur = MP3(a_path).info.length
                    scene_audio_paths[i] = a_path
                    scene["audio_path"] = a_path
                    scene["computed_duration"] = dur
                    scene["word_boundaries"] = scene.get("word_boundaries", [])
                    continue
                except Exception:
                    pass

            if os.path.exists(wav_alt) and os.path.getsize(wav_alt) > 0:
                import soundfile as sf
                try:
                    info = sf.info(wav_alt)
                    scene_audio_paths[i] = wav_alt
                    scene["audio_path"] = wav_alt
                    scene["computed_duration"] = info.duration
                    scene["word_boundaries"] = scene.get("word_boundaries", [])
                    continue
                except Exception:
                    pass

            await self._update_job(
                message=f"Đang tạo giọng đọc cảnh {i+1}/{self.total}..."
            )
            scene_rate = self._compose_speech_rate(
                self.speech_rate, scene.get("speech_rate_modifier", "0%")
            )
            try:
                dur, wbs = await tts_service.synthesize_speech(
                    tts_text, a_path,
                    voice=self.voice, rate=scene_rate,
                    pitch=getattr(self.req, "speech_pitch", None),
                    mode=self.mode,
                    emotion=scene.get("emotion", ""),
                    warning_callback=self._tts_warning_once,
                    use_breathing=getattr(self.req, "use_breathing", False),
                )

                from services import duration_model
                duration_model.record_observation(
                    tts_text, dur, voice=self.voice, rate=scene_rate
                )

                if self.voice.startswith("omnivoice_") and dur > 0:
                    uoc = tts_service.uoc_tinh_thoi_gian_giong_ai(dur * self.total)
                    if uoc:
                        tts_warnings.append(uoc)

                if os.path.exists(a_path) and os.path.getsize(a_path) > 0:
                    scene_audio_paths[i] = a_path
                    scene["audio_path"] = a_path
                    scene["computed_duration"] = dur
                    scene["word_boundaries"] = wbs
                elif os.path.exists(wav_alt) and os.path.getsize(wav_alt) > 0:
                    scene_audio_paths[i] = wav_alt
                    scene["audio_path"] = wav_alt
                    scene["computed_duration"] = dur
                    scene["word_boundaries"] = wbs
            except Exception as e:
                logger.error("TTS Error for scene %s: %s", i + 1, e, exc_info=True)
                pause_s = scene.get("pause_after_ms", 0) / 1000.0
                scene["computed_duration"] = 3.0 + pause_s
                scene["word_boundaries"] = []
                scene_audio_paths[i] = None

        return TTSResult(
            scene_audio_paths=scene_audio_paths,
            master_audio_path=master_audio_path,
            narration_scene_wbs=narration_scene_wbs,
            narration_total_dur=narration_total_dur,
            tts_warnings=tts_warnings,
        )

    # =========================================================================
    # OPTIMIZED: TTS + Images SONG SONG
    # =========================================================================
    # VẤN ĐỀ CŨ: Phase 1 (TTS xong hết) → Phase 2 (Images xong hết)
    #   → 10 scenes × 5s TTS + 10 scenes × 5s Image = 100s
    #
    # GIẢI PHÁP MỚI: Với mỗi scene, chạy TTS + Image SONG SONG
    #   → 10 scenes × max(5s TTS, 5s Image) = 50s (tiết kiệm ~50%)
    # =========================================================================

    async def run_parallel_tts_and_images(self) -> tuple[TTSResult, ImageResult]:
        """
        OPTIMIZED: Chạy TTS và Image SONG SONG cho mỗi scene.

        Với mỗi scene i:
          1. Sinh TTS cho scene[i] SONG SONG với sinh Image cho scene[i]
          2. Lưu kết quả vào scene[i]

        Sau khi tất cả scenes xong:
          - Gọi run_image_phase để xử lý Ken Burns / stock normalization
          - Gọi run_tts_phase một phần để lấy master_audio_path (nếu dùng single-pass)

        Returns:
            (TTSResult, ImageResult)
        """
        scenes = self.scenes
        total = len(scenes)

        # Khởi tạo kết quả TTS
        scene_audio_paths: List[Optional[str]] = [None] * total
        tts_warnings: List[str] = []

        # Khởi tạo kết quả Image
        scene_image_paths: List[str] = [""] * total

        # Single-pass narration: sinh TOÀN BỘ kịch bản 1 lần TRƯỚC
        master_audio_path: Optional[str] = None
        narration_scene_wbs: Optional[List[Any]] = None
        narration_total_dur: float = 0.0

        if self.req.use_single_pass_narration and self.mode != "photo_slideshow":
            await self._update_job(
                message="Đang đọc liền mạch toàn bộ kịch bản (1 lần gọi)..."
            )
            master_audio_path = os.path.join(self.job_dir_audio, "narration_master.mp3")
            try:
                scene_texts = [
                    tts_service.strip_break_tags(
                        tts_service._strip_emoji(s.get("text", "") or "")
                    ).strip()
                    for s in scenes
                ]
                narration_total_dur, narration_scene_wbs, _ = (
                    await tts_service.synthesize_script_single_pass(
                        scene_texts, master_audio_path,
                        voice=self.voice, rate=self.speech_rate,
                        pitch=getattr(self.req, "speech_pitch", None),
                        warning_callback=self._tts_warning_once,
                    )
                )
                await self._update_job(
                    message=f"Đọc liền mạch xong ({narration_total_dur:.1f}s). "
                    "Đang sinh hình ảnh song song..."
                )
            except Exception as narr_err:
                logger.warning(
                    "[Narration] Đọc liền mạch thất bại (%s). Quay về đọc từng cảnh.",
                    narr_err,
                )
                await self._update_job(
                    message=f"⚠️ Không dùng được chế độ đọc liền mạch. Đọc từng cảnh."
                )
                master_audio_path = None
                narration_scene_wbs = None

        # Semaphore RIÊNG cho TTS và Image — trước đây dùng chung (_sem) khiến
        # TTS và Image phải XẾP HÀNG qua cùng một semaphore 4 worker, tối đa hóa
        # tổng thời gian = tong_TTS + tong_Image (tuần tự). Tách riêng → 4 TTS + 4
        # Image chạy song song thực sự, tong thời gian = max(tong_TTS, tong_Image).
        cpu_count = os.cpu_count() or 4
        tts_sem = asyncio.Semaphore(min(4, cpu_count))
        image_sem = asyncio.Semaphore(min(4, cpu_count))
        # Counter để theo dõi progress tổng (TTS + Image)
        # Dùng list 1 phần tử để nonlocal trong nested async fn hoạt động với int
        _tts_done = [0]
        _image_done = [0]

        async def _do_single_scene_tts(i: int, scene: dict) -> tuple[int, Optional[str], Optional[float], List, Optional[str]]:
            """Sinh TTS cho một scene - chạy trong semaphore RIÊNG (tách khỏi image)."""
            try:
                return await _do_single_scene_tts_inner(i, scene)
            except Exception as e:
                logger.error("Unexpected TTS error in scene %s: %s", i + 1, e, exc_info=True)
                return i, None, 3.0, [], None
            finally:
                _tts_done[0] += 1
                total_done = _tts_done[0] + _image_done[0]
                p = min(50, int(total_done / max(2 * total, 1) * 50))
                if p > 0:
                    await self._update_job(progress=p)

        async def _do_single_scene_tts_inner(i: int, scene: dict) -> tuple[int, Optional[str], Optional[float], List, Optional[str]]:
            async with tts_sem:
                text_raw = scene.get("text", "") or ""
                tts_text = tts_service._strip_emoji(text_raw).strip()
                tts_text = re.sub(r'  +', ' ', tts_text)
                text = tts_service.strip_break_tags(tts_text)
                scene["text"] = text

                # Nếu dùng single-pass narration, audio đã có sẵn
                if narration_scene_wbs is not None:
                    _, wbs, _ = narration_scene_wbs[i]
                    scene["word_boundaries"] = wbs
                    scene["computed_duration"] = 0.0
                    return i, None, 0.0, wbs, None

                if not text.strip():
                    pause_s = scene.get("pause_after_ms", 0) / 1000.0
                    scene["computed_duration"] = 3.0 + pause_s
                    scene["word_boundaries"] = []
                    return i, None, scene["computed_duration"], [], None

                a_path = os.path.join(self.job_dir_audio, f"scene_{i+1}.mp3")
                wav_alt = a_path.replace(".mp3", ".wav")

                # Check cache trước
                if os.path.exists(a_path) and os.path.getsize(a_path) > 0:
                    from mutagen.mp3 import MP3
                    try:
                        dur = MP3(a_path).info.length
                        scene["audio_path"] = a_path
                        scene["computed_duration"] = dur
                        scene["word_boundaries"] = scene.get("word_boundaries", [])
                        return i, a_path, dur, scene["word_boundaries"], None
                    except Exception:
                        pass

                if os.path.exists(wav_alt) and os.path.getsize(wav_alt) > 0:
                    import soundfile as sf
                    try:
                        info = sf.info(wav_alt)
                        scene["audio_path"] = wav_alt
                        scene["computed_duration"] = info.duration
                        scene["word_boundaries"] = scene.get("word_boundaries", [])
                        return i, wav_alt, info.duration, scene["word_boundaries"], None
                    except Exception:
                        pass

                await self._update_job(
                    message=f"Đang tạo giọng đọc cảnh {i+1}/{total}..."
                )
                scene_rate = self._compose_speech_rate(
                    self.speech_rate, scene.get("speech_rate_modifier", "0%")
                )
                try:
                    dur, wbs = await tts_service.synthesize_speech(
                        tts_text, a_path,
                        voice=self.voice, rate=scene_rate,
                        pitch=getattr(self.req, "speech_pitch", None),
                        mode=self.mode,
                        emotion=scene.get("emotion", ""),
                        warning_callback=self._tts_warning_once,
                        use_breathing=getattr(self.req, "use_breathing", False),
                    )

                    from services import duration_model
                    duration_model.record_observation(
                        tts_text, dur, voice=self.voice, rate=scene_rate
                    )

                    if self.voice.startswith("omnivoice_") and dur > 0:
                        uoc = tts_service.uoc_tinh_thoi_gian_giong_ai(dur * total)
                        if uoc:
                            tts_warnings.append(uoc)

                    if os.path.exists(a_path) and os.path.getsize(a_path) > 0:
                        scene["audio_path"] = a_path
                        scene["computed_duration"] = dur
                        scene["word_boundaries"] = wbs
                        return i, a_path, dur, wbs, None
                    elif os.path.exists(wav_alt) and os.path.getsize(wav_alt) > 0:
                        scene["audio_path"] = wav_alt
                        scene["computed_duration"] = dur
                        scene["word_boundaries"] = wbs
                        return i, wav_alt, dur, wbs, None
                except Exception as e:
                    logger.error("TTS Error for scene %s: %s", i + 1, e, exc_info=True)

                pause_s = scene.get("pause_after_ms", 0) / 1000.0
                scene["computed_duration"] = 3.0 + pause_s
                scene["word_boundaries"] = []
                result = (i, None, scene["computed_duration"], [], None)
                return result

        async def _do_single_scene_image(i: int, scene: dict) -> tuple[int, str]:
            """Sinh Image cho một scene - chạy trong semaphore RIÊNG (tách khỏi TTS)."""
            try:
                return await _do_single_scene_image_inner(i, scene)
            except Exception as e:
                logger.error("Unexpected Image error in scene %s: %s", i + 1, e, exc_info=True)
                image_path = os.path.join(self.job_dir_images, f"scene_{i+1}.png")
                self._create_placeholder_image(image_path)
                return i, image_path
            finally:
                _image_done[0] += 1
                total_done = _tts_done[0] + _image_done[0]
                p = min(50, int(total_done / max(2 * total, 1) * 50))
                if p > 0:
                    await self._update_job(progress=p)

        async def _do_single_scene_image_inner(i: int, scene: dict) -> tuple[int, str]:
            async with image_sem:
                image_path = os.path.join(self.job_dir_images, f"scene_{i+1}.png")
                img_prompt = scene.get("image_prompt", "")
                text = scene.get("text", "") or ""
                scene_rate = self._compose_speech_rate(
                    self.speech_rate, scene.get("speech_rate_modifier", "0%")
                )
                vis_meta: dict = {}

                def _mark(nguon: str):
                    vis_meta.setdefault("source", nguon)

                async def _gen_ai_image():
                    return await image_router.generate_image_with_fallback(
                        image_prompt=img_prompt,
                        output_path=image_path,
                        aspect_ratio=self.imagen_aspect,
                        google_api_key=self.api_key,
                        negative_prompt=getattr(self.req, "negative_prompt", None),
                        seed=self.video_seed,
                        art_style=getattr(self.req, "art_style", None),
                        source_meta=vis_meta,
                    )

                # Manual override (user-uploaded asset)
                override_src = self._resolve_override_asset(scene.get("override_asset"))
                if override_src:
                    override_ext = os.path.splitext(override_src)[1].lower()
                    dest = os.path.splitext(image_path)[0] + override_ext
                    await asyncio.to_thread(shutil.copy2, override_src, dest)
                    await self._update_job(
                        message=f"Cảnh {i+1}: dùng hình bạn tự tải lên."
                    )
                    _mark("user_override")
                    scene["visual_source_used"] = "user_override"
                    return i, dest

                mp4_alt = image_path.replace(".png", ".mp4")
                if os.path.exists(mp4_alt) and os.path.getsize(mp4_alt) > 0:
                    _mark("cache:file_mp4")
                    scene["visual_source_used"] = "cache:file_mp4"
                    return i, mp4_alt
                if os.path.exists(image_path) and os.path.getsize(image_path) > 1000:
                    _mark("cache:file_img")
                    scene["visual_source_used"] = "cache:file_img"
                    return i, image_path

                # Photo modes
                if self.mode in ("photo_narration", "photo_slideshow") and i < len(self.user_images):
                    await asyncio.to_thread(shutil.copy, self.user_images[i], image_path)
                    _mark("user_photo")
                    scene["visual_source_used"] = "user_photo"
                    return i, image_path

                # Cover image
                if (getattr(self.req, "cover_image_session_id", None)
                        and (getattr(self.req, "cover_image_position", None) in ("start", "both")
                             and i == 0
                             or getattr(self.req, "cover_image_position", None) in ("end", "both")
                             and i == len(scenes) - 1)):
                    cover_images = get_upload_paths(getattr(self.req, "cover_image_session_id", ""))
                    if cover_images:
                        await asyncio.to_thread(shutil.copy, cover_images[0], image_path)
                        _mark("user_cover")
                        scene["visual_source_used"] = "user_cover"
                        return i, image_path

                # Veo video generation
                if getattr(self.req, "use_veo", False) and not self.veo_state["disabled"]:
                    await self._update_job(
                        message=f"Đang sinh Video AI (Veo) cho cảnh {i+1}/{total}..."
                    )
                    try:
                        from services.veo_service import generate_scene_video
                        video_path = await generate_scene_video(
                            scene_prompt=img_prompt,
                            aspect_ratio=self.aspect_ratio,
                            use_fast_model=True,
                            negative_prompt=getattr(self.req, "negative_prompt", "") or "",
                        )
                        _mark("veo")
                        vis_meta["is_veo_scene"] = True
                        scene["visual_source_used"] = "veo"
                        return i, video_path
                    except Exception as veo_err:
                        err_str = str(veo_err)
                        if any(sig in err_str for sig in (
                            "429", "RESOURCE_EXHAUSTED", "403", "PERMISSION_DENIED", "billed"
                        )):
                            self.veo_state["disabled"] = True
                            await self._update_job(
                                message=(
                                    "⚠️ Veo 3 không khả dụng: API key hiện tại chưa bật billing. "
                                    "Tự động dùng Pexels Video / Ảnh AI + Ken Burns."
                                ),
                            )
                        logger.warning(
                            "Veo Error for scene %s: %s. Fallback...",
                            i + 1, veo_err,
                        )
                        pexels_key = os.getenv("PEXELS_API_KEY")
                        if pexels_key:
                            try:
                                return await self._fetch_stock_video_cached(
                                    img_prompt, image_path, self.imagen_aspect, pexels_key,
                                    needed_duration=self._estimate_scene_duration(text, self.voice, scene_rate),
                                    used_ids=self.stock_used_ids,
                                    api_key=self.api_key,
                                    source_meta=vis_meta,
                                )
                            except Exception as pex_v_err:
                                logger.warning("Pexels Video fallback failed: %s", pex_v_err)
                        _result = await _gen_ai_image()
                        return i, _result

                # Stock video or AI image
                pexels_key = os.getenv("PEXELS_API_KEY")
                want_stock = self._pick_visual_source(self.req, scene, i) == "stock_video"
                if want_stock and pexels_key:
                    await self._update_job(
                        message=f"Đang tìm video Pexels cho cảnh {i+1}/{total}..."
                    )
                    try:
                        result = await self._fetch_stock_video_cached(
                            img_prompt, image_path, self.imagen_aspect, pexels_key,
                            needed_duration=self._estimate_scene_duration(text, self.voice, scene_rate),
                            used_ids=self.stock_used_ids,
                            api_key=self.api_key,
                            source_meta=vis_meta,
                        )
                        scene["visual_source_used"] = vis_meta.get("source", "unknown")
                        return i, result
                    except Exception as pexels_err:
                        logger.warning(
                            "Pexels video cho cảnh %s thất bại (%s). Rơi về ảnh AI.",
                            i + 1, pexels_err,
                        )

                await self._update_job(
                    message=f"Đang sinh ảnh AI cho cảnh {i+1}/{total}..."
                )
                try:
                    result = await _gen_ai_image()
                    scene["visual_source_used"] = vis_meta.get("source", "unknown")
                except Exception:
                    self._create_placeholder_image(image_path)
                    _mark("placeholder")
                    scene["visual_source_used"] = "placeholder"
                    result = image_path
                return i, result

        # ── CHẠY TTS + IMAGES SONG SONG CHO MỖI SCENE ──────────────────────────
        self.phase = Phase.TTS
        await self._update_job(status="generating_assets")

        # Tạo tasks cho TTS và Images
        tts_tasks = []
        image_tasks = []

        for i, scene in enumerate(scenes):
            tts_tasks.append(_do_single_scene_tts(i, scene))
            image_tasks.append(_do_single_scene_image(i, scene))

        # Chạy TẤT CẢ tasks SONG SONG (TTS + Image trong cùng 1 gather)
        logger.info(
            "[Pipeline] Bắt đầu sinh TTS + Images SONG SONG (1 gather) cho %d scenes...",
            total
        )
        all_results = await asyncio.gather(*tts_tasks, *image_tasks)
        tts_results  = all_results[:total]
        image_results = all_results[total:]

        # ── Xử lý kết quả TTS ──────────────────────────────────────────────────
        for result in tts_results:
            i, audio_path, dur, wbs, _ = result
            scene_audio_paths[i] = audio_path
            if audio_path:
                scenes[i]["audio_path"] = audio_path
            if dur and dur > 0:
                scenes[i]["computed_duration"] = dur
            if wbs:
                scenes[i]["word_boundaries"] = wbs

        # ── Xử lý kết quả Images ──────────────────────────────────────────────
        for i_res, img_path in image_results:
            scene_image_paths[i_res] = img_path
            scenes[i_res]["image_path"] = img_path

        # ── Lưu checkpoint ────────────────────────────────────────────────────
        from services import project_service
        await asyncio.to_thread(
            project_service.save_project_state, self.job_id,
            {
                "job_id": self.job_id,
                "title": getattr(self.req, "topic", None) or f"Dự án {self.job_id[:8]}",
                "mode": self.mode,
                "scenes": scenes,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": "generating_assets",
                "req": self.req.model_dump(mode='json'),
            },
        )

        # Visual source summary
        summary = self._summarize_visual_sources(scenes)
        if summary:
            logger.info("[VisualSources] %s", summary)
            await self._update_job(message=f"Nguồn hình: {summary}")

        # Xây dựng kết quả TTS
        tts_result = TTSResult(
            scene_audio_paths=scene_audio_paths,
            master_audio_path=master_audio_path,
            narration_scene_wbs=narration_scene_wbs,
            narration_total_dur=narration_total_dur,
            tts_warnings=tts_warnings,
        )

        # Xây dựng kết quả Image
        image_result = ImageResult(
            scene_image_paths=scene_image_paths,
            veo_state=self.veo_state,
            stock_used_ids=self.stock_used_ids,
        )

        logger.info(
            "[Pipeline] Hoàn tất TTS + Images song song: %d scenes trong 1 vòng parallel",
            total
        )

        return tts_result, image_result

    # -------------------------------------------------------------------------
    # Phase 2: Images / Visuals
    # -------------------------------------------------------------------------

    async def run_image_phase(self, scenes: List[Dict[str, Any]], tts_result: TTSResult) -> ImageResult:
        """
        Generates per-scene visuals in parallel with TTS results.
        Runs asyncio.gather over _do_tts + _do_visuals for each scene.

        Returns:
            ImageResult with scene_image_paths, veo_state, stock_used_ids.
        """
        self.phase = Phase.IMAGES

        scene_image_paths: List[str] = ["" for _ in scenes]

        for i, scene in enumerate(scenes):
            image_path = os.path.join(self.job_dir_images, f"scene_{i+1}.png")
            img_prompt = scene.get("image_prompt", "")
            text = scene.get("text", "") or ""
            scene_rate = self._compose_speech_rate(
                self.speech_rate, scene.get("speech_rate_modifier", "0%")
            )
            vis_meta: dict = {}

            # ── Per-scene TTS (runs after single-pass, reads cached results) ──
            async def _do_tts():
                # Already handled in run_tts_phase; here we just return cached values
                return (
                    scene.get("computed_duration", 3.0),
                    scene.get("word_boundaries", []),
                    scene.get("audio_path"),
                )

            # ── Per-scene visuals ───────────────────────────────────────────
            async def _do_visuals():
                final_img_path = image_path

                def _mark(nguon: str):
                    vis_meta.setdefault("source", nguon)

                async def _gen_ai_image():
                    return await image_router.generate_image_with_fallback(
                        image_prompt=img_prompt,
                        output_path=final_img_path,
                        aspect_ratio=self.imagen_aspect,
                        google_api_key=self.api_key,
                        negative_prompt=getattr(self.req, "negative_prompt", None),
                        seed=self.video_seed,
                        art_style=getattr(self.req, "art_style", None),
                        source_meta=vis_meta,
                    )

                # Manual override (user-uploaded asset for this scene)
                override_src = self._resolve_override_asset(scene.get("override_asset"))
                if override_src:
                    override_ext = os.path.splitext(override_src)[1].lower()
                    dest = os.path.splitext(final_img_path)[0] + override_ext
                    await asyncio.to_thread(shutil.copy2, override_src, dest)
                    await self._update_job(
                        message=f"Cảnh {i+1}: dùng hình bạn tự tải lên."
                    )
                    _mark("user_override")
                    return dest

                mp4_alt = final_img_path.replace(".png", ".mp4")
                if os.path.exists(mp4_alt) and os.path.getsize(mp4_alt) > 0:
                    _mark("cache:file_mp4")
                    return mp4_alt
                if os.path.exists(final_img_path) and os.path.getsize(final_img_path) > 1000:
                    _mark("cache:file_img")
                    return final_img_path

                if self.mode in ("photo_narration", "photo_slideshow") and i < len(self.user_images):
                    await asyncio.to_thread(shutil.copy, self.user_images[i], final_img_path)
                    _mark("user_photo")
                    return final_img_path
                elif (getattr(self.req, "cover_image_session_id", None)
                      and (getattr(self.req, "cover_image_position", None) in ("start", "both")
                           and i == 0
                           or getattr(self.req, "cover_image_position", None) in ("end", "both")
                           and i == len(scenes) - 1)):
                    cover_images = get_upload_paths(getattr(self.req, "cover_image_session_id", ""))
                    if cover_images:
                        await asyncio.to_thread(shutil.copy, cover_images[0], final_img_path)
                        _mark("user_cover")
                        return final_img_path
                    else:
                        await _gen_ai_image()
                        return final_img_path

                elif getattr(self.req, "use_veo", False) and not self.veo_state["disabled"]:
                    await self._update_job(
                        message=f"Đang sinh Video AI (Veo) cho cảnh {i+1}/{self.total}..."
                    )
                    try:
                        from services.veo_service import generate_scene_video
                        video_path = await generate_scene_video(
                            scene_prompt=img_prompt,
                            aspect_ratio=self.aspect_ratio,
                            use_fast_model=True,
                            negative_prompt=getattr(self.req, "negative_prompt", "") or "",
                        )
                        _mark("veo")
                        vis_meta["is_veo_scene"] = True
                        return video_path
                    except Exception as veo_err:
                        err_str = str(veo_err)
                        if any(sig in err_str for sig in (
                            "429", "RESOURCE_EXHAUSTED", "403", "PERMISSION_DENIED", "billed"
                        )):
                            self.veo_state["disabled"] = True
                            await self._update_job(
                                message=(
                                    "⚠️ Veo 3 không khả dụng: API key hiện tại chưa bật billing "
                                    "(Google yêu cầu gói trả phí cho Veo). Tự động dùng "
                                    "Pexels Video / Ảnh AI + Ken Burns cho toàn bộ video."
                                ),
                            )
                        logger.warning(
                            "Veo Error for scene %s: %s. Tự động fallback sang Pexels Video / Image Router...",
                            i + 1, veo_err,
                        )
                        pexels_key = os.getenv("PEXELS_API_KEY")
                        if pexels_key:
                            try:
                                return await self._fetch_stock_video_cached(
                                    img_prompt, final_img_path, self.imagen_aspect, pexels_key,
                                    needed_duration=self._estimate_scene_duration(text, self.voice, scene_rate),
                                    used_ids=self.stock_used_ids,
                                    api_key=self.api_key,
                                    source_meta=vis_meta,
                                )
                            except Exception as pex_v_err:
                                logger.warning("Pexels Video fallback failed: %s", pex_v_err)
                        return await _gen_ai_image()
                else:
                    pexels_key = os.getenv("PEXELS_API_KEY")
                    want_stock = self._pick_visual_source(self.req, scene, i) == "stock_video"
                    if want_stock and pexels_key:
                        await self._update_job(
                            message=f"Đang tìm video Pexels cho cảnh {i+1}/{self.total}..."
                        )
                        try:
                            return await self._fetch_stock_video_cached(
                                img_prompt, final_img_path, self.imagen_aspect, pexels_key,
                                needed_duration=self._estimate_scene_duration(text, self.voice, scene_rate),
                                used_ids=self.stock_used_ids,
                                api_key=self.api_key,
                                source_meta=vis_meta,
                            )
                        except Exception as pexels_err:
                            logger.warning(
                                "Pexels video cho cảnh %s thất bại (%s). Rơi về ảnh AI.",
                                i + 1, pexels_err,
                            )

                    await self._update_job(
                        message=f"Đang sinh ảnh AI cho cảnh {i+1}/{self.total}..."
                    )
                    try:
                        await _gen_ai_image()
                    except Exception:
                        self._create_placeholder_image(final_img_path)
                        _mark("placeholder")
                    return final_img_path

            # Run TTS + visuals in parallel for this scene
            (scene_duration, scene_wbs, audio_path), image_path = await asyncio.gather(
                _do_tts(), _do_visuals()
            )

            scene["image_path"] = image_path
            if not scene.get("audio_path"):
                scene["audio_path"] = audio_path
            scene["visual_source_used"] = vis_meta.get("source", "unknown")
            scene["is_veo_scene"] = vis_meta.get("is_veo_scene", False)
            if vis_meta.get("query"):
                scene["stock_query_used"] = vis_meta["query"]
            if not scene.get("computed_duration"):
                scene["computed_duration"] = scene_duration
            if not scene.get("word_boundaries"):
                scene["word_boundaries"] = scene_wbs
            scene_image_paths[i] = image_path

            # Save checkpoint after each scene
            from services import project_service
            await asyncio.to_thread(
                project_service.save_project_state, self.job_id,
                {
                    "job_id": self.job_id,
                    "title": getattr(self.req, "topic", None) or f"Dự án {self.job_id[:8]}",
                    "mode": self.mode,
                    "scenes": scenes,
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "status": "generating_assets",
                    "req": self.req.model_dump(mode='json'),
                },
            )

        # Visual source summary
        summary = self._summarize_visual_sources(scenes)
        if summary:
            logger.info("[VisualSources] %s", summary)
            await self._update_job(message=f"Nguồn hình: {summary}")

        return ImageResult(
            scene_image_paths=scene_image_paths,
            veo_state=self.veo_state,
            stock_used_ids=self.stock_used_ids,
        )

    # -------------------------------------------------------------------------
    # Phase 3: Timeline
    # -------------------------------------------------------------------------

    async def compute_timeline(self, tts_result: TTSResult, image_result: ImageResult) -> TimelineResult:
        """
        Builds the final timeline: beat sync, hook timing, Ken Burns / stock normalization,
        per-scene visual processing, and BGM volume segments.

        Returns:
            TimelineResult with timeline (list of scene_assets dicts).
        """
        self.phase = Phase.TIMELINE

        scenes = self.scenes
        narration_scene_wbs = tts_result.get("narration_scene_wbs")
        narration_total_dur = tts_result.get("narration_total_dur", 0.0)
        cf_dur = SLIDESHOW_CROSSFADE if self.mode == "photo_slideshow" else CROSSFADE_DURATION

        # ── Accurate timeline from word_boundaries ─────────────────────────
        import asyncio as _asyncio
        _asyncio.get_event_loop()  # ensure event loop exists (sync call)

        if narration_scene_wbs is not None:
            scenes = build_timeline_from_narration(
                scenes, narration_scene_wbs, narration_total_dur, overlap_dur=cf_dur
            )
        else:
            scenes = build_scene_timeline(scenes, overlap_dur=cf_dur)

        # ── Beat Sync ──────────────────────────────────────────────────────
        if self.req.use_beat_sync and self.bgm_path and os.path.isfile(self.bgm_path):
            try:
                await _asyncio.get_event_loop().run_in_executor(
                    None, apply_beat_sync_to_timeline, scenes, self.bgm_path
                )
                # Run in executor to avoid blocking (apply_beat_sync_to_timeline is sync)
            except Exception as bs_err:
                logger.warning("Beat Sync warning (non-fatal): %s", bs_err)

        # ── Hook: skip empty hook effects ──────────────────────────────────
        HOOK_TEXT_REQUIRED = {"blackout_question", "typewriter_quote"}
        if self.req.hook_effect in HOOK_TEXT_REQUIRED:
            if not (self.req.hook_text or "").strip() and (self.req.hook_quote or "").strip():
                self.req.hook_text = self.req.hook_quote
        if self.req.hook_effect in HOOK_TEXT_REQUIRED and not (self.req.hook_text or "").strip():
            logger.info("[Hook] '%s' rỗng chữ — bỏ qua hook (hook_effect=none).", self.req.hook_effect)
            self.req.hook_effect = "none"

        # ── Hook lead: push all scene start_times back ─────────────────────
        self.hook_timing = resolve_hook_timing(self.req.hook_effect, self.req.hook_text)
        if self.hook_timing:
            lead = self.hook_timing["narration_lead"]
            for s in scenes:
                s["start_time"] = s.get("start_time", 0.0) + lead
            # Fire and forget the message update
            asyncio.create_task(self._update_job(
                message=f"Dời giọng đọc {lead:.2f}s để tránh đè hiệu ứng mở đầu...",
            ))

        # ── Per-scene visual processing: Ken Burns / stock normalization ──────
        _visual_sem = asyncio.Semaphore(min(4, os.cpu_count() or 4))
        _visual_done = 0

        async def _process_scene_visual(i: int, s: dict) -> dict:
            nonlocal _visual_done
            async with _visual_sem:
                scene_effect = s.get("visual_effect", "")
                img_path = s["image_path"]
                duration = s.get("computed_duration", 3.0)
                start_time = s.get("start_time", 0.0)

                is_video_asset = img_path.lower().endswith((".mp4", ".mov"))
                if not is_video_asset:
                    out_mp4 = img_path + f"_{i}.mp4"
                    if getattr(self.req, "use_ken_burns", True):
                        hook_boost = bool(
                            i == 0
                            and getattr(self.req, "hook_zoom_boost", False)
                            and self.req.hook_effect != "carousel_quote"
                        )
                        pan_dir, kb_zoom_start, kb_zoom_end = resolve_motion(
                            scene_effect, i, hook_boost=hook_boost
                        )
                    else:
                        pan_dir, kb_zoom_start, kb_zoom_end = "center", 1.0, 1.0
                    try:
                        await asyncio.to_thread(
                            apply_ken_burns,
                            image_path=img_path, output_path=out_mp4,
                            duration=duration, fps=30,
                            pan_direction=pan_dir,
                            zoom_start=kb_zoom_start, zoom_end=kb_zoom_end,
                            resolution=self.frame_size,
                        )
                        img_path = out_mp4
                    except Exception as kb_err:
                        logger.error(
                            "Cảnh %s: đúc ảnh thành video thất bại (%s). Giữ ảnh tĩnh.",
                            i + 1, kb_err, exc_info=True,
                        )
                elif is_video_asset:
                    norm_mp4 = f"{os.path.splitext(img_path)[0]}_norm{i}.mp4"
                    try:
                        await asyncio.to_thread(
                            normalize_stock_clip,
                            video_path=img_path, output_path=norm_mp4,
                            duration=duration, resolution=self.frame_size, fps=30,
                        )
                        img_path = norm_mp4
                    except Exception as norm_err:
                        logger.warning(
                            "[StockNorm] Cảnh %s chuẩn hoá thất bại (%s). Dùng clip gốc.",
                            i + 1, norm_err,
                        )

                # Hook SFX: add 'riser' to first scene if enabled
                scene_sfx = s.get("sfx", "")
                if (i == 0 and getattr(self.req, "hook_zoom_boost", False)
                        and getattr(self.req, "use_sfx", False)
                        and not scene_sfx):
                    scene_sfx = "riser"

                _visual_done += 1
                await self._update_job(
                    message=f"Đang dựng hình/video cảnh: {_visual_done}/{len(scenes)}...",
                )

                return {
                    "image_path": img_path,
                    "audio_path": s.get("audio_path"),
                    "text": s.get("text", ""),
                    "duration": duration,
                    "sfx": scene_sfx,
                    "word_boundaries": s.get("word_boundaries", []),
                    "transition": s.get("transition", "crossfade"),
                    "start_time": start_time,
                    "highlight_text": s.get("highlight_text", ""),
                    "source_quote": s.get("source_quote", ""),
                    "subtitle_text": s.get("subtitle_text", ""),
                    "bgm_volume": s.get("bgm_volume"),
                    "is_stock_video": is_video_asset,
                }

        # ── Run all scene visual processing concurrently ────────────────────
        scene_assets: List[Dict[str, Any]] = list(await asyncio.gather(
            *[_process_scene_visual(i, s) for i, s in enumerate(scenes)]
        ))

        # ── BGM volume per scene ───────────────────────────────────────────
        bgm_volume_segments = [
            (a["start_time"], a["start_time"] + a["duration"], float(a["bgm_volume"]))
            for a in scene_assets
            if a.get("bgm_volume") is not None
        ]
        if bgm_volume_segments:
            asyncio.create_task(self._update_job(
                message=f"Áp dụng nhạc nền riêng cho {len(bgm_volume_segments)} cảnh...",
            ))

        self.scene_assets = scene_assets
        self.bgm_volume_segments = bgm_volume_segments

        return TimelineResult(timeline=scene_assets)

    # -------------------------------------------------------------------------
    # Phase 4: Render
    # -------------------------------------------------------------------------

    async def run_render_phase(
        self, scene_assets: List[Dict[str, Any]], kwargs: Dict[str, Any]
    ) -> Optional[str]:
        """
        Spawns render (or runs inline if MAX_CONCURRENT_RENDERS is hit),
        polls worker status, and handles stall/cancellation.

        Returns:
            Output video path if successful, None otherwise.
        """
        self.phase = Phase.RENDER
        await self._update_job(
            status="rendering", message="Đang render video...", progress=80
        )

        output_video_path = os.path.join(OUTPUT_DIR, f"{self.job_id}.mp4")
        output_srt_path = os.path.join(OUTPUT_DIR, f"{self.job_id}.ass")
        raw_video = output_video_path + ".raw.mp4"

        # ── Total duration for progress bar ────────────────────────────────
        outro_timing = resolve_outro_timing(
            self.req.outro_effect,
            resolve_outro_text(
                getattr(self.req, "outro_text", "") or "",
                getattr(self.req, "cta_text", "") or "",
                getattr(self.req, "hook_text", "") or "",
            ),
        )
        outro_duration = outro_timing["duration"] if outro_timing else 0.0
        video_total_duration = (
            max((a["start_time"] + a["duration"]) for a in scene_assets)
            if scene_assets else 0.0
        ) + outro_duration

        # ── Intro BGM duration ────────────────────────────────────────────
        actual_intro_bgm_duration = 0.0
        if self.intro_bgm_path and scene_assets:
            actual_intro_bgm_duration = getattr(self.req, "intro_bgm_duration", 0.0)
            if actual_intro_bgm_duration <= 0.0:
                first = scene_assets[0]
                actual_intro_bgm_duration = first["start_time"] + first["duration"]

        # ── Master kwargs for audio mixing ──────────────────────────────────
        master_kwargs = dict(
            bgm_path=self.bgm_path,
            intro_bgm_path=self.intro_bgm_path,
            intro_bgm_duration=actual_intro_bgm_duration,
            total_duration=video_total_duration,
            use_gpu=getattr(self.req, "use_gpu_encode", False),
            bgm_volume=getattr(self.req, "bgm_volume", 0.15),
            watermark_text=getattr(self.req, "watermark_text", None),
            watermark_logo=self._watermark_logo_path(
                getattr(self.req, "watermark_logo", None)
            ),
            color_grading=getattr(self.req, "color_grading", None),
            subtitle_style=getattr(self.req, "subtitle_style", None),
            hook_effect=self.req.hook_effect,
            bgm_volume_segments=self.bgm_volume_segments,
            use_audio_ducking=getattr(self.req, "use_audio_ducking", True),
            narration_tone=getattr(self.req, "narration_tone", None) or "viral",
            use_pattern_interrupt=getattr(self.req, "use_pattern_interrupt", False),
            hook_duration=(self.hook_timing or {}).get("duration", 0.0),
        )

        # ── Spawn render worker ─────────────────────────────────────────────
        spawned = spawn_render(
            job_id=self.job_id,
            scene_assets=scene_assets,
            raw_video_path=raw_video,
            output_video_path=output_video_path,
            output_srt_path=output_srt_path,
            render_kwargs=kwargs,
            master_kwargs=master_kwargs,
        )

        if not spawned:
            # ── Fallback: run render inline (MAX_CONCURRENT_RENDERS hit) ────
            await self._update_job(
                message="Hàng đợi render đầy. Đang render trực tiếp..."
            )
            fallback_notes: list[str] = []
            await asyncio.to_thread(
                render_final_video,
                scene_assets, raw_video,
                on_fallback=fallback_notes.append,
                **kwargs,
            )
            for note in fallback_notes:
                await self._update_job(message=note)

            if self.mode != "photo_slideshow":
                from services.video_service import generate_ass_file
                await asyncio.to_thread(
                    generate_ass_file,
                    scene_assets, output_srt_path,
                    self.mode,
                    subtitle_style=getattr(self.req, "subtitle_style", None),
                    hook_text=getattr(self.req, "hook_text", ""),
                    hook_effect=self.req.hook_effect,
                    video_width=self.frame_size[0],
                    video_height=self.frame_size[1],
                )

            await self._update_job(
                message="Đang Mastering Âm thanh & Tối ưu Video...", progress=90
            )
            from services.audio_mix_service import master_audio_and_export as _master_audio

            inline_sidechain = raw_video + VOICE_SIDECHAIN_SUFFIX
            if not os.path.isfile(inline_sidechain):
                inline_sidechain = None

            try:
                await asyncio.to_thread(
                    _master_audio,
                    input_video_path=raw_video,
                    output_path=output_video_path,
                    sidechain_audio_path=inline_sidechain,
                    ass_subtitle_path=output_srt_path
                    if os.path.isfile(output_srt_path) else None,
                    **{
                        k: v for k, v in master_kwargs.items()
                        if k not in ("subtitle_style", "hook_effect")
                    },
                )
                if os.path.isfile(raw_video):
                    os.remove(raw_video)
                if inline_sidechain and os.path.isfile(inline_sidechain):
                    os.remove(inline_sidechain)
            except Exception as err:
                logger.error("FFmpeg Mastering error: %s", err, exc_info=True)
                if os.path.isfile(raw_video):
                    for _ in range(3):
                        try:
                            os.replace(raw_video, output_video_path)
                            break
                        except PermissionError:
                            await asyncio.sleep(1)

            return output_video_path if os.path.isfile(output_video_path) else None

        # ── Worker polling loop ─────────────────────────────────────────────
        while True:
            await asyncio.sleep(RENDER_POLL_INTERVAL)
            ws = read_render_status(self.job_id)

            if ws is not None:
                await self._update_job(
                    status=ws.get("status", "rendering"),
                    progress=ws.get("progress", 80),
                    message=ws.get("message", "Đang render..."),
                    video_url=ws.get("video_url"),
                    srt_url=ws.get("srt_url"),
                    error=ws.get("error"),
                )
                if ws.get("status") in ("done", "error"):
                    self.render_failed = ws.get("status") == "error"
                    cleanup_status(self.job_id)
                    break

            # Safety: worker process died without writing final status
            if not is_render_active(self.job_id):
                logger.error(
                    "[Render] Worker của job %s đã chết mà không ghi trạng thái cuối.",
                    self.job_id,
                )
                cleanup_status(self.job_id)
                await self._update_job(
                    status="error", progress=0,
                    error="Render worker dừng đột ngột",
                    message=(
                        "❌ Tiến trình render dừng đột ngột (thường là hết RAM khi dựng "
                        "video dài). Ảnh và giọng đọc đã sinh vẫn được giữ lại — mở dự án "
                        "và render lại sẽ không tốn thêm quota API. "
                        "Chi tiết lỗi: backend/logs/render_worker.log"
                    ),
                )
                self.render_failed = True
                break

            # Stall detection: process alive but silent too long
            last_beat = (ws or {}).get("updated_at", 0)
            if last_beat and time.time() - last_beat > RENDER_STALL_TIMEOUT:
                logger.error(
                    "[Render] Job %s không nhúc nhích %.0f giây — coi như treo, "
                    "đang huỷ để giải phóng slot render.",
                    self.job_id, time.time() - last_beat,
                )
                try:
                    cancel_render(self.job_id)
                except Exception as cancel_err:
                    logger.error(
                        "[Render] Không huỷ được worker treo của job %s: %s",
                        self.job_id, cancel_err,
                    )
                await self._update_job(
                    status="error",
                    error="Render treo quá lâu",
                    message=(
                        f"⚠️ Không có tín hiệu nào từ tiến trình render trong "
                        f"{RENDER_STALL_TIMEOUT // 60} phút — đã tự huỷ để giải phóng "
                        f"slot render. Ảnh và giọng đọc đã sinh vẫn được giữ lại, "
                        f"render lại sẽ không tốn thêm quota API. "
                        f"Chi tiết: backend/logs/render_worker.log."
                    ),
                )
                self.render_failed = True
                break

        return output_video_path

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    async def _preflight(self) -> None:
        """Resolve BGM paths, video seed, intro BGM, user images."""
        # Video seed
        if getattr(self.req, "use_fixed_seed", False) or getattr(self.req, "use_frame_chaining", False):
            self.video_seed = uuid.uuid4().int % 100000

        # BGM path
        bgm_track = getattr(self.req, "bgm_track", None)
        if bgm_track:
            if bgm_track == "auto":
                available = [
                    f for f in os.listdir(BGM_DIR)
                    if f.endswith((".mp3", ".wav", ".ogg"))
                ]
                if available:
                    self.bgm_path = os.path.join(BGM_DIR, random.choice(available))
            else:
                candidate = os.path.join(BGM_DIR, os.path.basename(bgm_track))
                if not candidate.endswith(".mp3"):
                    candidate += ".mp3"
                if os.path.isfile(candidate):
                    self.bgm_path = candidate

        # Intro BGM
        intro_bgm_track = getattr(self.req, "intro_bgm_track", None)
        if intro_bgm_track:
            candidate = os.path.join(BGM_DIR, os.path.basename(intro_bgm_track))
            if not candidate.endswith(".mp3"):
                candidate += ".mp3"
            if os.path.isfile(candidate):
                self.intro_bgm_path = candidate

        # User images for photo modes
        if self.mode in ("photo_narration", "photo_slideshow") and getattr(self.req, "upload_session_id", None):
            self.user_images = get_upload_paths(self.req.upload_session_id)

    def _build_render_kwargs(self) -> Dict[str, Any]:
        """Build kwargs for render_final_video (shared between worker and inline paths)."""
        from main import RENDER_PASSTHROUGH_FIELDS, build_render_kwargs
        kwargs = build_render_kwargs(self.req, self.aspect_ratio, self.mode, self.master_audio_path)
        return kwargs

    async def _update_job(self, **kwargs) -> None:
        """Write job status JSON and broadcast via WebSocket."""
        # Avoid circular import by reading from main module at call time
        from main import JOBS, manager

        job = JOBS.get(self.job_id)
        if not job:
            return
        # Use phase enum value as status when not overridden
        if "status" not in kwargs and hasattr(self, "phase"):
            kwargs["status"] = self.phase.value
        for k, v in kwargs.items():
            setattr(job, k, v)
        # Fire and forget the broadcast
        asyncio.create_task(manager.broadcast(self.job_id, job.model_dump(mode='json')))

    async def _tts_warning_once(self, msg: str) -> None:
        """Emit a TTS warning to the UI exactly once per job."""
        if msg in self.tts_warned:
            return
        self.tts_warned.add(msg)
        await self._update_job(message=msg)

    async def _cleanup(self) -> None:
        """
        Delete per-scene audio/image dirs on success.
        On failure, preserve them so a re-render can reuse cached assets.
        """
        if not self.render_failed:
            shutil.rmtree(self.job_dir_audio, ignore_errors=True)
            shutil.rmtree(self.job_dir_images, ignore_errors=True)
        else:
            logger.info(
                "[Render] Job %s lỗi — giữ lại ảnh/giọng đọc trong %s và %s "
                "để render lại.",
                self.job_id, self.job_dir_audio, self.job_dir_images,
            )
        if getattr(self.req, "upload_session_id", None):
            cleanup_upload(self.req.upload_session_id)

    # -------------------------------------------------------------------------
    # Utility methods (copied verbatim from main.py helpers)
    # -------------------------------------------------------------------------

    @staticmethod
    def _resolve_override_asset(asset_id: Optional[str]) -> Optional[str]:
        """Convert asset override id to absolute path."""
        from main import OVERRIDE_ALLOWED_EXTS
        if not asset_id:
            return None
        safe = os.path.basename(str(asset_id).strip())
        if not safe or os.path.splitext(safe)[1].lower() not in OVERRIDE_ALLOWED_EXTS:
            return None
        path = os.path.join(OVERRIDES_DIR, safe)
        return path if os.path.isfile(path) and os.path.getsize(path) > 0 else None

    @staticmethod
    def _pick_visual_source(req: Any, scene: dict, scene_index: int) -> str:
        """Decide visual source for one scene: stock_video or ai_image."""
        from main import _pick_visual_source
        return _pick_visual_source(req, scene, scene_index)

    @staticmethod
    def _estimate_scene_duration(text: str, voice: Optional[str] = None, rate: Optional[str] = None) -> float:
        """Estimate scene duration for stock clip selection."""
        from main import _estimate_scene_duration
        return _estimate_scene_duration(text, voice, rate)

    @staticmethod
    def _summarize_visual_sources(scenes: List[Dict[str, Any]]) -> str:
        """Count scenes by visual source → human-readable summary."""
        from main import _summarize_visual_sources
        return _summarize_visual_sources(scenes)

    @staticmethod
    def _create_placeholder_image(path: str) -> None:
        """Create a simple placeholder image when Imagen fails."""
        from main import _create_placeholder_image
        return _create_placeholder_image(path)

    @staticmethod
    def _compose_speech_rate(user_rate: str, scene_modifier: str) -> str:
        """Combine user speech rate with per-scene modifier."""
        from main import _compose_speech_rate
        return _compose_speech_rate(user_rate, scene_modifier)

    @staticmethod
    def _watermark_logo_path(name: Optional[str]) -> Optional[str]:
        """Convert logo name to absolute PNG path in watermarks dir."""
        from main import _watermark_logo_path
        return _watermark_logo_path(name)

    async def _fetch_stock_video_cached(
        self,
        image_prompt: str,
        output_path: str,
        aspect_ratio: str,
        pexels_key: str,
        needed_duration: float,
        used_ids: set,
        api_key: Optional[str],
        source_meta: Optional[dict] = None,
    ) -> str:
        """Fetch a stock video with caching."""
        from main import _fetch_stock_video_cached
        return await _fetch_stock_video_cached(
            image_prompt=image_prompt,
            output_path=output_path,
            aspect_ratio=aspect_ratio,
            pexels_key=pexels_key,
            needed_duration=needed_duration,
            used_ids=used_ids,
            api_key=api_key,
            source_meta=source_meta,
        )
