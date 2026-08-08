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
import logging
import os
import imageio_ffmpeg

# Inject ffmpeg path globally
os.environ["PATH"] += os.pathsep + os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())

import json
import re
import shutil
import subprocess
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote

# PHẢI chạy trước dòng log tiếng Việt đầu tiên: khi stdout bị chuyển hướng (chạy như
# service, ghi ra file), Windows mở nó bằng cp1252/strict và mọi dấu tiếng Việt sẽ
# ném UnicodeEncodeError thoát ra ngoài, giết cả job. Xem services/log_setup.py.
from services.log_setup import set_job_id, setup_logging

setup_logging()

logger = logging.getLogger(__name__)

# PHẢI import TRƯỚC mọi module trong services/: config gọi load_dotenv() với đường dẫn
# tuyệt đối tới backend/.env, còn key_manager (bị services.gemini_service kéo theo) gọi
# load_dotenv() trần — dò theo CWD. load_dotenv không ghi đè biến đã có, nên module nào
# nạp trước thì cấu hình của module đó thắng. Nạp config trước = luôn đúng file .env.
import config  # noqa: E402

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from services import gemini_service, tts_service, video_service
from services.image_upload_service import (
    cleanup_upload,
    get_upload_paths,
    process_uploaded_images,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Việc phải làm lúc bật/tắt server.

    Thay cho @app.on_event("startup") — decorator đó đã bị FastAPI đánh dấu deprecated
    và sẽ bị gỡ. Thân hàm chỉ chạy lúc khởi động nên vẫn gọi được những thứ định nghĩa
    ở phía dưới file này.
    """
    restored = _restore_jobs_from_disk()
    if restored:
        logger.info("[Startup] Khôi phục %d job từ đĩa sau khi khởi động lại.", restored)

    # Warmup OmniVoice + whisper-align chạy nền (tắt bằng OMNIVOICE_WARMUP=0).
    if os.getenv("OMNIVOICE_WARMUP", "1") != "0":
        asyncio.create_task(tts_service.warmup_omnivoice())

    yield


app = FastAPI(title="AI Video Studio API", lifespan=lifespan)

# CORS cấu hình qua env ALLOWED_ORIGINS (danh sách phân tách bằng dấu phẩy).
#
# MẶC ĐỊNH KHÔNG CÒN LÀ "*". Backend này lắng nghe trên localhost và có những endpoint
# thay đổi hệ thống thật: đổi thư mục lưu trữ (ghi vào .env), xoá bộ nhớ đệm, huỷ job.
# Với "*", BẤT KỲ trang web nào người dùng đang mở trong trình duyệt cũng gọi được
# chúng bằng một dòng fetch tới http://localhost:8000 — trình duyệt sẽ gửi request đi
# và cho JavaScript đọc kết quả. Danh sách trắng cổng dev của chính dự án đóng cửa đó
# lại mà không ảnh hưởng gì tới cách dùng hằng ngày.
#
# Mở UI từ máy khác trong mạng LAN? Thêm origin đó vào .env:
#   ALLOWED_ORIGINS=http://localhost:3001,http://192.168.1.50:3001
DEFAULT_LOCAL_ORIGINS = [
    "http://localhost:3001", "http://127.0.0.1:3001",   # start.bat / ecosystem.config.js
    "http://localhost:5173", "http://127.0.0.1:5173",   # cổng mặc định của Vite
]
_origins_env = os.getenv("ALLOWED_ORIGINS", "").strip()
if _origins_env == "*":
    ALLOWED_ORIGINS = ["*"]
    logger.warning(
        "[CORS] ALLOWED_ORIGINS=* — mọi website đang mở trong trình duyệt đều gọi được "
        "API này. Chỉ nên dùng khi đang gỡ lỗi."
    )
elif _origins_env:
    ALLOWED_ORIGINS = [o.strip() for o in _origins_env.split(",") if o.strip()]
else:
    ALLOWED_ORIGINS = DEFAULT_LOCAL_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=ALLOWED_ORIGINS != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    # Không khai báo thì trình duyệt GIẤU header này khỏi JS (CORS mặc định chỉ lộ vài
    # header an toàn) — cảnh báo "giọng clone hỏng, đang đọc bằng giọng thay thế" của
    # /api/preview-scene-voice sẽ tới nơi nhưng không ai đọc được.
    expose_headers=["X-TTS-Warning"],
)

# Đường dẫn lấy TẤT CẢ từ config — xem config.py để biết vì sao tài nguyên đi kèm mã
# nguồn (bgm/sfx) và dữ liệu sinh ra (images/output/cache) nằm ở hai gốc khác nhau.
from config import (
    AUDIO_DIR,
    BGM_DIR,
    CUSTOM_SFX_DIR,
    IMAGES_DIR,
    OUTPUT_DIR,
    OVERRIDES_DIR,
    RENDER_STATUS_DIR,
    SFX_DIR,
    TEMP_DIR,
    VOICES_PREVIEW_DIR,
    WATERMARKS_DIR,
)


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
    # Dùng cho job "nghe thử cả bài" (/api/preview-full-script). Để chung JobState thay
    # vì dựng một bảng trạng thái thứ hai: WebSocket, /api/job-status và cơ chế dọn job
    # cũ đều đã chạy sẵn trên đây rồi.
    audio_url: Optional[str] = None
    scene_ranges: Optional[List[Optional[List[float]]]] = None
    cache_scope: Optional[str] = None
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
        if job_id not in self.active_connections:
            return
        # LỖI CŨ: lỗi gửi bị nuốt nhưng socket KHÔNG bị bỏ khỏi active_connections.
        # disconnect() chỉ chạy khi websocket.receive_text() nhận được WebSocketDisconnect
        # "sạch" — client rớt mạng đột ngột (tắt máy, mất wifi) không qua đường đó, để
        # lại một WebSocket đã chết nằm mãi trong danh sách. Mọi broadcast() sau đó cho
        # job này thử gửi lại, thất bại lại, mãi mãi — không hại gì ngoài lãng phí, nhưng
        # dọn ngay khi phát hiện thì rẻ hơn để tích tụ qua một job chạy hàng chục phút.
        dead = []
        for connection in self.active_connections[job_id]:
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)
        for connection in dead:
            self.disconnect(connection, job_id)

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
    variation_seed: int = 0
    # Cân lại nhịp sau khi Gemini chia cảnh (chỉ áp dụng cho mode script_video).
    # Đặt False nếu muốn giữ ĐÚNG cách chia của Gemini để đối chiếu.
    auto_balance_scenes: bool = True
    voice: Optional[str] = None      # để ước lượng thời lượng đúng giọng sẽ dùng
    speech_rate: str = "+0%"
    # Nguồn hình dự kiến khi render — quyết định KIỂU image_prompt Gemini phải viết.
    # Thiếu hai field này (trạng thái trước đây), tầng sinh kịch bản luôn viết prompt
    # cinematic kiểu "Extreme close-up shot of..., 8k, Unreal Engine"; nếu user render bằng
    # footage stock thì extract_search_keyword() phải gỡ lại đúng những chữ đó để tìm Pexels,
    # và chữ nào lọt lưới sẽ thành từ khoá rác → trả về video sai chủ đề.
    prefer_stock_video: bool = False
    visual_source: str = "auto"      # auto | ai_image | stock_video | mixed
    # Viết lại kịch bản ĐÚNG 1 lượt nếu lớp review chấm dưới 60/100, và chỉ nhận bản mới khi
    # nó điểm cao hơn. Tốn thêm 1-2 lượt quota mỗi lần kích hoạt, nên có công tắc tắt.
    # KHÔNG áp cho mode script_video: lời thoại ở đó là của người dùng, giữ nguyên văn 100%.
    auto_retry_low_quality: bool = True

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
    cta_text: Optional[str] = None
    gemini_api_key: Optional[str] = None
    character_description: Optional[str] = None
    use_frame_chaining: bool = True
    use_ken_burns: bool = True
    use_beat_sync: bool = False
    use_veo_ambient_audio: bool = True
    use_gpu_encode: bool = True
    hook_zoom_boost: bool = True
    use_pattern_interrupt: bool = True
    use_fixed_seed: bool = False
    subtitle_style: str = "karaoke_bold"
    watermark_text: Optional[str] = None
    watermark_logo: Optional[str] = None
    hook_text: Optional[str] = None
    cover_image_session_id: Optional[str] = None
    cover_image_position: str = "start"  # "start", "end", "both"
    use_sfx: bool = True
    sfx_volume: float = 0.064
    use_audio_ducking: bool = True
    color_grading: str = "warm_cinematic"
    topic: Optional[str] = None
    narration_tone: Optional[str] = "viral"
    use_breathing: bool = False
    hook_effect: str = "word_by_word"
    hook_quote: Optional[str] = None
    hook_reel_sfx: str = "tick_wood"  # tiếng trục quay Máy Xèng — xem video_service.HOOK_REEL_SOUNDS
    # ĐƠN VỊ: HỆ SỐ nhân (1.0 = 100%), KHÔNG phải phần trăm — frontend đã chia 100 trước
    # khi gửi (ScriptEditor.jsx). Khác đơn vị với PresetRequest.hook_sfx_volume (thang %),
    # nên đừng bao giờ gán thẳng giá trị từ preset sang đây: chênh nhau đúng 100 lần.
    # ge/le: chốt chặn ở tầng API để client quên chia 100 thì bị 422 ngay, thay vì lọt
    # xuống video_service rồi dựa vào các min() rải rác trong hook engine đỡ hộ.
    hook_sfx_volume: float = Field(0.8, ge=0.0, le=2.0)
    # "none" từng là mặc định — khiến toàn bộ 7 hiệu ứng outro (kể cả cta_card, thiết
    # kế riêng cho outro) không bao giờ xuất hiện trừ khi user tự vào đổi. cta_card
    # ngắn (2.4s), tự ẩn dòng CTA nếu outro_text rỗng (build_cta_card_hook), an toàn
    # làm mặc định cho mọi video.
    outro_effect: str = "cta_card"
    outro_text: Optional[str] = None
    outro_reel_sfx: str = "none"
    outro_sfx_volume: float = Field(0.8, ge=0.0, le=2.0)
    # Nhạc mở màn, chuyển sang bgm_track chính bằng crossfade. None/"" = không dùng.
    #
    # LỖI CŨ: hai field này bị QUÊN ở model trong khi _run_render_pipeline đọc
    # `req.intro_bgm_track` vô điều kiện. Pydantic mặc định BỎ IM LẶNG field lạ, nên
    # frontend gửi đúng tên vẫn bị vứt, rồi mọi job render chết bằng AttributeError —
    # ở vị trí NGOÀI khối try nên lỗi thoát ra khỏi BackgroundTask và job đứng ở
    # "pending" vĩnh viễn, giao diện không hiện lỗi nào. Xem tests/test_render_contract.py
    # (test_moi_field_req_doc_deu_ton_tai_trong_model) — nay đã có lưới chặn.
    intro_bgm_track: Optional[str] = None
    # 0 = tự lấy bằng thời điểm KẾT THÚC cảnh 1 trên timeline (đã gồm phần dời do hook).
    intro_bgm_duration: float = Field(0.0, ge=0.0, le=120.0)
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
    # Dựng timeline bằng 1 lệnh FFmpeg (xfade + NVENC) thay vì MoviePy — nhanh ~50 lần.
    # Tự rơi về MoviePy nếu có cảnh không đủ điều kiện. Tắt khi cần đối chiếu bản cũ.
    use_fast_assembly: bool = True

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
    # CÓ ở preset, KHÁC với watermark_text ngay bên cạnh nó trong RenderVideoRequest.
    # Hai thứ này nghe giống nhau nhưng khác loại: `watermark_text` là NỘI DUNG (chữ
    # riêng của từng video → không lưu, xem chú thích quy tắc bên dưới), còn
    # `watermark_logo` chỉ là TÊN FILE logo trong assets/watermarks — một lựa chọn kiểu
    # dáng đóng dấu, dùng lại y nguyên cho mọi video của cùng một kênh. Thiếu nó ở đây
    # thì user bật "Chèn Logo", lưu preset, nạp lại → toggle âm thầm về False và video
    # ra không có logo, đúng triệu chứng "chèn logo không hoạt động".
    watermark_logo: Optional[str] = None
    prefer_stock_video: bool = False
    visual_source: str = "auto"
    use_single_pass_narration: bool = False
    hook_effect: str = "word_by_word"
    hook_reel_sfx: str = "tick_wood"
    # ĐƠN VỊ: PHẦN TRĂM (100 = 100%) — preset lưu đúng con số hiện trên thanh trượt UI,
    # giống bgm_volume/sfx_volume ngay trong model này. Đổi sang hệ số ở ranh giới gửi
    # render (ScriptEditor.jsx chia 100), KHÔNG đổi ở đây.
    hook_sfx_volume: float = Field(80, ge=0, le=200)
    use_sfx: bool = True
    sfx_volume: float = 6.4
    use_audio_ducking: bool = True
    # Tên PHẢI trùng RenderVideoRequest.intro_bgm_track. Nhạc chính đã dùng `bgm_track` ở
    # cả hai model; để riêng chỗ này là `intro_bgm` thì mỗi lần đọc code lại phải nhớ
    # "preset gọi tên khác" — đúng loại lệch âm thầm sinh ra bug gán nhầm field.
    intro_bgm_track: Optional[str] = None
    intro_bgm_duration: float = Field(0, ge=0, le=120)
    outro_effect: str = "cta_card"
    # KHÔNG có outro_text ở đây, có chủ ý. Preset lưu KIỂU DÁNG, không lưu NỘI DUNG:
    # hook_text, hook_quote, topic, watermark_text, cta_text, negative_prompt,
    # character_description đều vắng mặt vì cùng lý do — đó là chữ nghĩa riêng của từng
    # video, nạp preset cũ mà chữ cũ hiện ra là sai kỳ vọng người dùng.
    # outro_text từng lọt vào đây một mình, thành ngoại lệ duy nhất phá quy tắc, và cũng
    # chưa bao giờ được frontend gửi hay khôi phục — một field chết.
    outro_reel_sfx: str = "none"
    # ĐƠN VỊ: PHẦN TRĂM (100 = 100%) — giống hook_sfx_volume ngay trên, KHÁC với
    # RenderVideoRequest.outro_sfx_volume (hệ số). ScriptEditor.jsx chia 100 ở ranh giới
    # gửi render; ở đây lưu đúng con số hiện trên thanh trượt.
    outro_sfx_volume: float = Field(100, ge=0, le=200)
    use_ken_burns: bool = True
    hook_zoom_boost: bool = True
    use_pattern_interrupt: bool = True
    use_breathing: bool = False
    use_frame_chaining: bool = True
    use_beat_sync: bool = False

VALID_MODES = {"storyteller", "photo_narration", "photo_slideshow", "script_video", "quiz_listicle", "manual"}
VALID_ASPECT_RATIOS = {"9:16", "16:9", "1:1"}


# ── Cầu nối RenderVideoRequest → render_final_video ──────────────────────────
# Field của request được chuyển THẲNG sang render_final_video, CÙNG TÊN, không biến đổi.
#
# LỖI CŨ (nguồn gốc của cả bug hook_sfx_volume): render_kwargs được gõ tay từng dòng
# `x=req.x`. Thêm tuỳ chọn mới vào model + UI mà quên thêm đúng một dòng ở đây thì
# render_final_video lặng lẽ dùng giá trị mặc định — không lỗi, không cảnh báo, và
# triệu chứng ("kéo thanh trượt không thấy gì đổi") trông y hệt lỗi thuật toán, cực khó
# lần ra. Khai báo tập hợp một lần rồi dựng dict từ nó thì thêm tuỳ chọn = thêm 1 dòng
# tên vào đây, và tests/test_render_contract.py đối chiếu tập này với
# video_service.RENDER_KWARG_KEYS nên quên là test đỏ ngay.
RENDER_PASSTHROUGH_FIELDS = (
    "hook_text",
    "use_sfx",
    "use_breathing",    # ghép breath.wav 1 lần vào đầu audio (video_service)
    "use_veo_ambient_audio",  # ambient sound cho scene Veo (video_service)
    "hook_effect",      # để render_final_video dựng hook carousel_quote
    "hook_quote",
    "hook_reel_sfx",
    "hook_sfx_volume",  # HỆ SỐ (1.0 = 100%), frontend đã chia 100 trước khi gửi
    "outro_effect",
    "outro_text",
    # CTA do Gemini sinh — nguồn chữ DỰ PHÒNG cho outro khi user không gõ tay, xem
    # video_service.resolve_outro_text(). Trước đây là field chết: model có, frontend
    # gửi, không nơi nào đọc.
    "cta_text",
    "outro_reel_sfx",
    "outro_sfx_volume",
    "use_fast_assembly",
    "use_gpu_encode",
)


def build_render_kwargs(req, aspect_ratio: str, mode: str, master_audio_path: str | None) -> dict:
    """Dựng tham số cho render_final_video — DÙNG CHUNG cho cả đường worker lẫn đường
    inline, để hai nhánh không thể trôi lệch nhau theo thời gian."""
    kwargs = {field: getattr(req, field) for field in RENDER_PASSTHROUGH_FIELDS}
    # Phần còn lại KHÔNG phải ánh xạ 1-1 nên vẫn viết tay:
    kwargs.update(
        aspect_ratio=aspect_ratio,
        bgm_path=None,  # BGM được mix bởi FFmpeg ở bước master
        mode=mode,
        sfx_volume=req.sfx_volume if req.sfx_volume is not None else 0.5,
        master_audio_path=master_audio_path,  # chế độ đọc liền mạch (None nếu tắt)
    )
    return kwargs


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------
VALID_VISUAL_SOURCES = {"auto", "ai_image", "stock_video", "mixed"}

# Cảm xúc hợp với b-roll quay thật (cảnh trầm, trừu tượng, mang tính không khí).
# Các cảm xúc còn lại (hook, excited) cần dàn dựng cụ thể → ưu tiên ảnh AI.
_STOCK_FRIENDLY_EMOTIONS = {"calm", "closing", "dramatic", "suspense"}


# Tên hiển thị cho người dùng của từng nguồn hình. Khoá phải khớp các chuỗi mà
# `image_router.generate_image_with_fallback` và `_fetch_stock_video_cached` ghi vào
# `source_meta["source"]`.
VISUAL_SOURCE_LABELS = {
    "Pexels": "video Pexels",
    "Pixabay": "video Pixabay",
    "gemini_image": "ảnh Gemini",
    "pexels_photo": "ảnh Pexels",
    "pollinations_flux": "ảnh Pollinations",
    "gradient_offline": "gradient dự phòng",
    "placeholder": "ảnh trống",
    "veo": "video Veo",
    "user_override": "hình bạn tự chọn",
    "user_photo": "ảnh bạn tải lên",
    "user_cover": "ảnh bìa của bạn",
    "unknown": "không rõ",
}


def _summarize_visual_sources(scenes: list) -> str:
    """Đếm số cảnh theo từng nguồn hình → một câu đọc được cho log và UI.

    VÌ SAO CẦN: khi mọi nhánh sinh hình đều `return` một đường dẫn giống nhau, hiện tượng
    "hết quota ảnh Gemini nên cả video âm thầm thành ảnh stock tĩnh" là hoàn toàn vô hình —
    video vẫn render xong, chỉ là không còn là thứ người dùng chọn. Câu tổng kết này là
    điều kiện tiên quyết để tối ưu: không có nó thì mọi phán đoán về tỉ lệ nguồn chỉ là
    cảm giác.
    """
    from collections import Counter

    dem = Counter()
    for s in scenes:
        raw = str(s.get("visual_source_used") or "unknown")
        # "cache:Pexels" / "cache:file_mp4" → gộp về nhóm "dùng lại từ cache".
        dem["cache"] += 1 if raw.startswith("cache:") else 0
        if not raw.startswith("cache:"):
            dem[raw] += 1
    phan = [
        f"{n} {VISUAL_SOURCE_LABELS.get(k, k)}"
        for k, n in dem.most_common()
        if n > 0 and k != "cache"
    ]
    if dem.get("cache"):
        phan.append(f"{dem['cache']} dùng lại từ cache")
    return ", ".join(phan)


def _wants_stock_footage(req) -> bool:
    """Video này DỰ KIẾN dựng bằng footage stock hay ảnh AI?

    Dùng ở tầng SINH KỊCH BẢN (trước khi có cảnh nào) để chọn kiểu `image_prompt` Gemini
    phải viết — xem IMAGE_PROMPT_RULES_STOCK/_AI. Cố ý dùng CÙNG bộ luật với
    `_pick_visual_source`, nhưng gộp ở cấp video vì lúc này chưa có emotion từng cảnh để
    phân xử chế độ "mixed"; "mixed" đằng nào cũng trộn cả hai nguồn nên viết prompt kiểu
    cinematic là lựa chọn an toàn hơn (ảnh AI dùng được prompt tả cảnh thật, nhưng Pexels
    thì không dùng nổi prompt đầy jargon).

    ĐÃ BỎ HẲN `art_style` KHỎI PHÉP CHỌN NÀY — xem chú thích ở `_pick_visual_source`.
    """
    source = getattr(req, "visual_source", "auto")
    if source == "stock_video":
        return True
    if source in ("ai_image", "mixed"):
        return False
    return bool(getattr(req, "prefer_stock_video", False))


def _pick_visual_source(req, scene: dict, scene_index: int) -> str:
    """
    Quyết định nguồn hình cho 1 cảnh: "stock_video" hay "ai_image".

    CHỈ dựa trên lựa chọn TƯỜNG MINH của user: `visual_source` (cấp cảnh rồi cấp video)
    và công tắc `prefer_stock_video`.

    HAI THẾ HỆ BẪY ĐÃ GỠ Ở ĐÂY — cả hai đều gây đúng một triệu chứng "gần như mọi video
    đều là footage tải về, ảnh AI hầu như không được dùng":

    1. (cũ) Dò chuỗi "photorealistic"/"realistic" trong `image_prompt`. Nhưng base prompt
       BẮT BUỘC Gemini chèn "8k, photorealistic, Unreal Engine 5" vào MỌI image_prompt →
       điều kiện luôn đúng → mọi cảnh bị đẩy sang stock.
    2. (vừa gỡ) Dò chính chuỗi đó trong `art_style` của user. Nghe hợp lý hơn, nhưng
       `STYLES[1]` trên giao diện là **"Realistic (Thực tế)"** = `"Photorealistic,
       cinematic lighting, 8K UHD"` — một lựa chọn hoàn toàn tự nhiên cho chủ đề đời thực.
       Chọn nó là TOÀN BỘ video âm thầm chuyển sang Pexels, trong khi người dùng tưởng
       mình vừa chọn PHONG CÁCH VẼ cho AI. `art_style` trả lời câu hỏi "vẽ theo kiểu gì",
       KHÔNG phải "lấy hình từ đâu"; app đã có sẵn hai điều khiển riêng cho câu hỏi sau.

    Bài học chung: đừng suy ra nguồn hình từ một chuỗi được sinh/chọn cho mục đích khác.
    """
    # 1. Ưu tiên cấu hình riêng của từng cảnh (do người dùng chỉnh sửa trên giao diện)
    scene_source = scene.get("visual_source", "auto")
    if scene_source in ("ai_image", "stock_video"):
        return scene_source

    # 2. Nếu cảnh để "auto", dùng cấu hình chung của toàn bộ video
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

    # auto: CHỈ khi user chủ động bật công tắc "ưu tiên video thật".
    return "stock_video" if req.prefer_stock_video else "ai_image"


# Biên an toàn khi chọn clip stock: thà lấy clip dài dư rồi cắt, còn hơn lấy clip
# thiếu vài giây và phải ping-pong (chạy tiến rồi lùi) thấy rõ trên màn hình.
_STOCK_CLIP_SAFETY = 1.15


def _estimate_scene_duration(text: str, voice: str | None = None, rate: str | None = None) -> float:
    """
    Ước lượng thời lượng cảnh từ số từ, dùng LÚC CHỌN clip stock.

    Cần thiết vì `_do_tts` và `_do_visuals` chạy song song (asyncio.gather) nên thời
    lượng thật từ word_boundaries CHƯA có khi ta phải quyết định tải clip nào. Con số
    này chỉ dùng để chấm điểm "clip có đủ dài không", còn việc cắt/ping-pong về đúng
    thời lượng thật thì làm sau, ở bước normalize_stock_clip.

    LỖI CŨ: hàm này có công thức riêng `words * 0.38 + 0.7` (2.6 từ/giây) trong khi
    gemini_service ước lượng bằng 3.0 từ/giây và cảnh báo trên UI ngầm định 3.0 — ba
    thước đo lệch nhau tới 15% cho cùng một kịch bản. Giờ tất cả gọi chung
    duration_model, và con số đó tự hiệu chỉnh theo giọng người dùng thật sự đang dùng.
    """
    from services import duration_model

    return max(3.0, duration_model.estimate_duration(text, voice, rate) * _STOCK_CLIP_SAFETY)


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


# Định dạng cho phép ghi đè thủ công. Danh sách TRẮNG, không phải danh sách đen: file
# lạ lọt vào đây sẽ được đưa thẳng cho FFmpeg xử lý.
OVERRIDE_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
OVERRIDE_VIDEO_EXTS = {".mp4", ".mov", ".webm"}
OVERRIDE_ALLOWED_EXTS = OVERRIDE_IMAGE_EXTS | OVERRIDE_VIDEO_EXTS
MAX_OVERRIDE_BYTES = 200 * 1024 * 1024   # 200MB — đủ cho một clip quay bằng điện thoại
# Ảnh thay cho MỘT cảnh thì không cần rộng rãi như video: 30MB đã dư cho ảnh máy ảnh
# full-frame chưa nén. Xem /api/projects/{job_id}/scenes/{i}/upload-image.
MAX_SCENE_IMAGE_BYTES = 30 * 1024 * 1024


def _stock_cache_params(image_prompt: str, aspect_ratio: str) -> dict:
    """
    Khoá cache cho video stock Pexels.

    Khoá theo `image_prompt` — thứ NGƯỜI DÙNG gõ — chứ không theo từ khoá tìm kiếm mà
    Gemini rút ra từ nó. Hai lý do:
      1. Cache hit thì bỏ qua LUÔN cả lần gọi Gemini `extract_search_keyword`, không chỉ
         bỏ qua lần tải video.
      2. Đúng với kỳ vọng của người dùng: "cảnh này tôi không sửa gì thì đừng tạo lại".
         Nếu khoá theo từ khoá Gemini, hai cảnh khác hẳn nhau nhưng cùng rút ra chữ
         "ocean" sẽ dùng chung một clip — đúng cái lỗi lộ liễu mà used_ids đang chống.

    KHÔNG đưa thời lượng cảnh vào khoá: sửa lời thoại làm cảnh dài/ngắn đi không có
    nghĩa là phải tải clip khác, vì normalize_stock_clip đã tự cắt/ping-pong clip về
    đúng thời lượng cần.
    """
    return dict(prompt=image_prompt or "", aspect_ratio=aspect_ratio, source="pexels_video")


async def _fetch_stock_video_cached(
    image_prompt: str, output_path: str, aspect_ratio: str, pexels_key: str,
    needed_duration: float, used_ids: set, api_key: Optional[str],
    source_meta: Optional[dict] = None,
) -> str:
    """
    Tải video stock CÓ CACHE.

    LÝ DO TỒN TẠI: `fetch_pexels_video` trước đây không đụng gì tới cache — khác hẳn
    `generate_image_with_fallback`. Hệ quả là ai bật "ưu tiên video thật" thì Smart
    Caching mất tác dụng hoàn toàn ở phần hình: mỗi lần render lại là một lần gọi Gemini
    rút từ khoá + tải lại toàn bộ clip, dù không sửa một chữ nào. Đo trên dự án thật:
    12/12 cảnh phải tạo mới, cache chỉ có giọng đọc.
    """
    from services import image_router
    from services.cache_service import cache as media_cache

    params = _stock_cache_params(image_prompt, aspect_ratio)
    mp4_path = os.path.splitext(output_path)[0] + ".mp4"

    if media_cache.get_media("stock", mp4_path, **params):
        meta = media_cache.get("stock_meta", **params) or {}
        # Nạp lại id clip để cảnh sau không vô tình chọn trúng đúng clip này.
        if meta.get("id") is not None:
            used_ids.add(meta["id"])
        logger.info("[Stock] Dùng lại clip đã tải trước đó (không gọi Pexels).")
        if source_meta is not None:
            source_meta["source"] = f"cache:{meta.get('provider') or 'stock'}"
            source_meta["query"] = meta.get("query") or ""
        return mp4_path

    from services.gemini_service import build_stock_queries

    # BẬC THANG: cụ thể → rộng dần, và mỗi bậc thử LẦN LƯỢT các nhà cung cấp.
    # Trước đây chỉ có ĐÚNG MỘT truy vấn trên ĐÚNG MỘT nhà cung cấp: hụt là rơi thẳng về
    # ảnh AI tĩnh, nên một video dễ thành nửa footage thật nửa ảnh tĩnh — lộ ngay khi xem.
    pixabay_key = os.getenv("PIXABAY_API_KEY")
    nha_cung_cap = [("Pexels", image_router.fetch_pexels_video, pexels_key)]
    if pixabay_key:
        nha_cung_cap.append(("Pixabay", image_router.fetch_pixabay_video, pixabay_key))

    out_meta: dict = {}
    result = None
    loi_cuoi: Optional[Exception] = None
    for query in build_stock_queries(image_prompt):
        for ten, fetch, key in nha_cung_cap:
            try:
                result = await fetch(
                    query, output_path, aspect_ratio, key,
                    needed_duration=needed_duration, used_ids=used_ids, out_meta=out_meta,
                )
                break
            except Exception as e:
                loi_cuoi = e
                logger.info(f"[Stock] {ten} không có clip cho '{query}': {e}")
        if result:
            break

    if not result:
        raise loi_cuoi or RuntimeError("Không nhà cung cấp stock nào trả về clip.")

    if source_meta is not None:
        source_meta["source"] = out_meta.get("provider") or "stock"
        source_meta["query"] = out_meta.get("query") or ""

    try:
        media_cache.set_media("stock", result, **params)
        media_cache.set("stock_meta", {
            "id": out_meta.get("id"),
            "query": out_meta.get("query"),
            "provider": out_meta.get("provider"),
        }, **params)
    except Exception as e:
        logger.warning(f"[Stock] Lưu cache thất bại (không ảnh hưởng render): {e}")
    return result


def _resolve_override_asset(asset_id: Optional[str]) -> Optional[str]:
    """
    Đổi id file ghi đè (do /api/scene-asset trả về) thành đường dẫn tuyệt đối.

    os.path.basename() chặn path traversal: kịch bản đến từ body JSON của client nên
    "../../.env" hoàn toàn có thể xuất hiện ở đây.
    """
    if not asset_id:
        return None
    safe = os.path.basename(str(asset_id).strip())
    if not safe or os.path.splitext(safe)[1].lower() not in OVERRIDE_ALLOWED_EXTS:
        return None
    path = os.path.join(OVERRIDES_DIR, safe)
    return path if os.path.isfile(path) and os.path.getsize(path) > 0 else None


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
# Nhịp hỏi thăm render worker qua file status.
RENDER_POLL_INTERVAL = 2

# Worker còn sống nhưng bao lâu không ghi thêm dòng nào thì coi là treo.
# 15 phút: bước nặng nhất (FFmpeg mastering + burn phụ đề của video dài) có thể chạy
# liền vài phút mà không phát tiến độ, nên ngưỡng phải rộng hơn hẳn khoảng đó —
# báo treo nhầm giữa lúc máy vẫn đang làm việc còn tệ hơn là báo muộn.
RENDER_STALL_TIMEOUT = 900


def _watermark_logo_path(name: Optional[str]) -> Optional[str]:
    """Tên logo do UI gửi ("logo_ntd") → đường dẫn file PNG trong assets/watermarks.

    LỖI ĐÃ VÁ: biểu thức `os.path.join(BASE_DIR, "assets", "watermarks", ...)` được gõ
    TAY ở hai chỗ (đường worker + nhánh inline), mà BASE_DIR CHƯA BAO GIỜ được import
    vào main.py. Nó nằm sau `if req.watermark_logo` của một biểu thức điều kiện, nên
    Python không đánh giá nó khi user KHÔNG bật logo: module import bình thường, mọi
    test đi qua, không một cảnh báo nào. Lỗi chỉ nổ đúng lúc user tick "Chèn Logo NTD",
    và nổ ở dòng 1125 — SAU khi đã sinh xong toàn bộ ảnh + TTS (phần đắt nhất của job).
    Người dùng thấy đúng một dòng "Lỗi: name 'BASE_DIR' is not defined", nên triệu chứng
    được hiểu thành "chèn logo không hoạt động".

    Gom về MỘT hàm: một chỗ duy nhất để đúng, và một chỗ duy nhất để cảnh báo khi thiếu
    file — audio_mix_service bỏ qua logo không tồn tại mà không in gì cả (`if
    watermark_logo and os.path.isfile(...)`), nên không cảnh báo ở đây thì "bật logo mà
    video ra không có logo" lại thành một lỗi im lặng khác.
    """
    if not name:
        return None
    # `name` đến từ request của client. basename() chặn `../..` leo ra khỏi thư mục
    # watermarks — đây là chuỗi đi thẳng vào os.path.join.
    safe = os.path.basename(str(name)).strip()
    if not safe or safe != name:
        logger.warning("[Watermark] Tên logo không hợp lệ: %r — bỏ qua logo.", name)
        return None
    path = os.path.join(WATERMARKS_DIR, f"{safe}.png")
    if not os.path.isfile(path):
        logger.warning(
            "[Watermark] Không tìm thấy logo %r tại %s — video sẽ KHÔNG có logo.", safe, path
        )
        return None
    return path


async def _run_render_pipeline(job_id: str, req: RenderVideoRequest):
    # Gắn job_id vào MỌI dòng log sinh ra từ đây trở đi — kể cả log của services/
    # (tts_service, video_service, image_router...). Không có nhãn này thì hai job
    # chạy chồng nhau sẽ trộn log và không dựng lại được diễn biến của job nào.
    set_job_id(job_id)

    job_dir_audio = os.path.join(AUDIO_DIR, job_id)
    job_dir_images = os.path.join(IMAGES_DIR, job_id)
    os.makedirs(job_dir_audio, exist_ok=True)
    os.makedirs(job_dir_images, exist_ok=True)

    # Render kết thúc trong lỗi hay không — quyết định có được xoá ảnh/giọng đọc đã sinh
    # ở cuối hàm không. Xem vòng poll worker và khối dọn dẹp cuối hàm.
    render_failed = False

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
            candidate = os.path.join(BGM_DIR, os.path.basename(req.bgm_track))
            if not candidate.endswith(".mp3"):
                candidate += ".mp3"
            if os.path.isfile(candidate):
                bgm_path = candidate

    try:
        # Đặt TRONG try: mọi thứ đọc từ `req` đều có thể ném (field thiếu, kiểu sai) và
        # phải rơi vào lưới báo lỗi cuối hàm, chứ không được thoát ra khỏi BackgroundTask
        # — thoát ra là job treo ở "pending" mà giao diện không biết gì.
        intro_bgm_path = None
        if req.intro_bgm_track:
            candidate = os.path.join(BGM_DIR, os.path.basename(req.intro_bgm_track))
            if not candidate.endswith(".mp3"):
                candidate += ".mp3"
            if os.path.isfile(candidate):
                intro_bgm_path = candidate


        await _update_job(job_id, status="generating_assets")
        scenes = req.scenes
        total = len(scenes)

        user_images = []
        if mode in ("photo_narration", "photo_slideshow") and req.upload_session_id:
            user_images = get_upload_paths(req.upload_session_id)

        from services import image_router

        # Trạng thái Veo cho toàn job: nếu lỗi quota/permission (không thể tự hết trong
        # phiên render) → tắt Veo cho các cảnh còn lại, tránh lãng phí thời gian retry,
        # đồng thời báo rõ lý do lên UI thay vì fallback im lặng.
        veo_state = {"disabled": False}

        # Id các clip Pexels đã dùng trong job này — chặn 2 cảnh nhận về cùng 1 đoạn phim.
        stock_used_ids: set = set()

        # Cảnh báo TTS đã báo cho user trong job này. Giọng clone hỏng là lỗi của CẢ JOB
        # (thiếu GPU, mất file mẫu), không phải của riêng một cảnh — không chặn thì một
        # video 20 cảnh dội đúng một câu cảnh báo 20 lần lên UI và đè mất mọi thông báo
        # tiến độ khác.
        tts_warned: set = set()

        async def _tts_warning_once(msg: str):
            if msg in tts_warned:
                return
            tts_warned.add(msg)
            await _update_job(job_id, message=msg)

        # ── Single-Pass Narration: đọc TOÀN kịch bản trong 1 lần gọi ──
        # Phải chạy TRƯỚC vòng lặp vì mốc thời gian của mọi cảnh đều suy ra từ dải giọng này.
        master_audio_path = None
        narration_scene_wbs = None
        narration_total_dur = 0.0
        if req.use_single_pass_narration and mode != "photo_slideshow":
            await _update_job(job_id, message="Đang đọc liền mạch toàn bộ kịch bản (1 lần gọi)...")
            master_audio_path = os.path.join(job_dir_audio, "narration_master.mp3")
            try:
                # Đọc liền mạch = MỘT lần gọi cho cả bài, không có chỗ để khâu khoảng
                # lặng riêng từng cảnh → thẻ <break> bị gỡ bỏ ở chế độ này (đã ghi rõ
                # trên UI). Muốn vi chỉnh nhịp nghỉ thì tắt "Đọc liền mạch".
                scene_texts = [
                    tts_service.strip_break_tags(
                        tts_service._strip_emoji(s.get("text", "") or "")
                    ).strip()
                    for s in scenes
                ]
                # Cảnh báo từ tầng TTS (đổi cách sinh, giọng clone hỏng...) → đẩy lên UI,
                # mỗi nội dung đúng một lần cho cả job.
                narration_total_dur, narration_scene_wbs, _ = await tts_service.synthesize_script_single_pass(
                    scene_texts, master_audio_path,
                    voice=voice, rate=speech_rate, pitch=req.speech_pitch,
                    warning_callback=_tts_warning_once,
                )
                await _update_job(
                    job_id,
                    message=f"Đọc liền mạch xong ({narration_total_dur:.1f}s) — timeline sẽ bám theo giọng.",
                )
            except Exception as narr_err:
                # Giọng không hỗ trợ (OmniVoice/Minion) hoặc ánh xạ từ→cảnh hỏng →
                # quay về đọc từng cảnh, KHÔNG làm chết job.
                logger.warning(f"[Narration] Đọc liền mạch thất bại ({narr_err}). Quay về đọc từng cảnh.")
                await _update_job(
                    job_id,
                    message=f"⚠️ Không dùng được chế độ đọc liền mạch ({narr_err}). Đã chuyển về đọc từng cảnh.",
                )
                master_audio_path = None
                narration_scene_wbs = None

        for i, scene in enumerate(scenes):
            image_path = os.path.join(job_dir_images, f"scene_{i+1}.png")
            # Lọc emoji/icons tại nguồn — đảm bảo TẤT CẢ downstream (TTS, Subtitle, Checkpoint)
            # đều nhận text sạch, không cần lọc lại nhiều lần
            tts_text = tts_service._strip_emoji(scene.get("text", "") or "").strip()
            tts_text = re.sub(r'  +', ' ', tts_text)  # Dọn khoảng trắng đôi

            # HAI BẢN VĂN BẢN, có chủ ý:
            #   tts_text — GIỮ thẻ <break time="1s"/> để tts_service khâu khoảng lặng thật.
            #   text     — đã gỡ thẻ, dùng cho phụ đề/checkpoint (khán giả không thấy thẻ).
            # Trước đây thẻ bị thay bằng "..." ngay tại đây, nên nó chỉ tạo được nhịp
            # nghỉ vài chục ms của dấu chấm lửng — công cụ vi chỉnh coi như vô tác dụng.
            text = tts_service.strip_break_tags(tts_text)
            scene["text"] = text

            img_prompt = scene.get("image_prompt", "")

            # Tốc độ đọc CUỐI CÙNG của cảnh này, tính MỘT LẦN ở đây thay vì trong _do_tts:
            # _do_visuals chạy song song cũng cần đúng con số đó để ước lượng thời lượng
            # (chọn clip stock đủ dài) — hai closure phải nhìn thấy cùng một giá trị.
            scene_rate = _compose_speech_rate(speech_rate, scene.get("speech_rate_modifier", "0%"))

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

                    final_rate = scene_rate

                    try:
                        dur, wbs = await tts_service.synthesize_speech(
                            tts_text, a_path, voice=voice, rate=final_rate, pitch=req.speech_pitch, mode=mode,
                            emotion=scene.get("emotion", ""),
                            warning_callback=_tts_warning_once,
                            use_breathing=req.use_breathing
                        )
                        # Số đo THẬT — kéo dần ước lượng của toàn hệ thống về đúng tốc độ
                        # đọc của chính giọng này. Trước đây dur chỉ dùng dựng timeline
                        # rồi bỏ, nên hệ thống mãi ước lượng bằng hằng số gõ tay.
                        from services import duration_model
                        duration_model.record_observation(tts_text, dur, voice=voice, rate=final_rate)

                        # Giọng AI chạy trên GPU có thể chậm hơn thời gian thực nhiều lần
                        # (đo được RTF ≈ 8 trên GTX 1660 SUPER). Sau cảnh ĐẦU TIÊN đã có số
                        # đo thật của chính máy này → nói luôn cho user tổng thời gian phải
                        # chờ, thay vì để họ đoán qua thanh tiến trình. Ước tổng lời thoại
                        # bằng cảnh đầu nhân số cảnh: thô nhưng dựa trên số đo, không phải
                        # hằng số gõ tay.
                        if voice.startswith("omnivoice_") and dur > 0:
                            uoc_tinh = tts_service.uoc_tinh_thoi_gian_giong_ai(dur * total)
                            if uoc_tinh:
                                await _tts_warning_once(uoc_tinh)

                        if os.path.exists(a_path) and os.path.getsize(a_path) > 0:
                            return dur, wbs, a_path
                        if os.path.exists(wav_alt) and os.path.getsize(wav_alt) > 0:
                            return dur, wbs, wav_alt
                    except Exception as e:
                        logger.error(f"TTS Error for scene {i+1}: {e}", exc_info=True)
                
                # Cảnh không có chữ (VD: quote_card) hoặc lỗi sinh giọng đọc
                base_duration = 3.0
                pause_s = scene.get("pause_after_ms", 0) / 1000.0
                return base_duration + pause_s, [], None

            # Nguồn hình THẬT của cảnh này. Trước đây không có gì ghi lại: mọi nhánh đều
            # trả về một đường dẫn giống nhau, nên không ai biết cảnh nào là video stock,
            # cảnh nào là ảnh Gemini, cảnh nào chỉ là gradient dự phòng. Không có số liệu
            # này thì mọi phán đoán kiểu "đa số video lấy từ Pexels" chỉ là cảm giác.
            vis_meta: dict = {}

            async def _do_visuals():
                final_img_path = image_path

                def _mark(nguon: str):
                    vis_meta.setdefault("source", nguon)

                # 3 nhánh bên dưới (cover-image rỗng, Veo lỗi/tắt, mặc định) đều rơi về
                # sinh ảnh AI với ĐÚNG một bộ tham số giống hệt nhau — gom một chỗ để sửa
                # 1 tham số không phải nhớ sửa cả 3 nơi.
                async def _gen_ai_image():
                    return await image_router.generate_image_with_fallback(
                        image_prompt=img_prompt, output_path=final_img_path,
                        aspect_ratio=imagen_aspect, google_api_key=api_key,
                        negative_prompt=req.negative_prompt, seed=video_seed,
                        art_style=req.art_style, source_meta=vis_meta,
                    )

                # ── Ghi đè thủ công: ảnh/video user tự tải lên cho ĐÚNG cảnh này ──
                # Đặt TRƯỚC mọi thứ khác: khi user đã tự chọn hình, không có lý do gì
                # để hỏi AI nữa — kể cả khi cache đang có sẵn ảnh của prompt cũ.
                override_src = _resolve_override_asset(scene.get("override_asset"))
                if override_src:
                    override_ext = os.path.splitext(override_src)[1].lower()
                    dest = os.path.splitext(final_img_path)[0] + override_ext
                    await asyncio.to_thread(shutil.copy2, override_src, dest)
                    await _update_job(job_id, message=f"Cảnh {i+1}: dùng hình bạn tự tải lên.")
                    _mark("user_override")
                    return dest

                mp4_alt = final_img_path.replace(".png", ".mp4")
                # Check cache visual cũ
                if os.path.exists(mp4_alt) and os.path.getsize(mp4_alt) > 0:
                    _mark("cache:file_mp4")
                    return mp4_alt
                if os.path.exists(final_img_path) and os.path.getsize(final_img_path) > 1000:
                    _mark("cache:file_img")
                    return final_img_path

                if mode in ("photo_narration", "photo_slideshow") and i < len(user_images):
                    await asyncio.to_thread(shutil.copy, user_images[i], final_img_path)
                    _mark("user_photo")
                    return final_img_path
                elif req.cover_image_session_id and (
                    (req.cover_image_position in ("start", "both") and i == 0) or
                    (req.cover_image_position in ("end", "both") and i == len(req.scenes) - 1)
                ):
                    cover_images = get_upload_paths(req.cover_image_session_id)
                    if cover_images:
                        await asyncio.to_thread(shutil.copy, cover_images[0], final_img_path)
                        _mark("user_cover")
                        return final_img_path
                    else:
                        await _gen_ai_image()
                        return final_img_path
                elif req.use_veo and not veo_state["disabled"]:
                    await _update_job(job_id, message=f"Đang sinh Video AI (Veo) cho cảnh {i+1}/{total}...")
                    try:
                        from services.veo_service import generate_scene_video
                        video_path = await generate_scene_video(
                            scene_prompt=img_prompt, aspect_ratio=aspect_ratio,
                            use_fast_model=True, negative_prompt=req.negative_prompt or ""
                        )
                        _mark("veo")
                        # Đánh dấu scene dùng Veo → audio_service biết scene nào cần ambient
                        vis_meta["is_veo_scene"] = True
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
                        logger.warning(f"Veo Error for scene {i+1}: {veo_err}. Tự động fallback sang Pexels Video / Image Router...")
                        pexels_key = os.getenv("PEXELS_API_KEY")
                        if pexels_key:
                            try:
                                return await _fetch_stock_video_cached(
                                    img_prompt, final_img_path, imagen_aspect, pexels_key,
                                    needed_duration=_estimate_scene_duration(text, voice, scene_rate),
                                    used_ids=stock_used_ids, api_key=api_key,
                                    source_meta=vis_meta,
                                )
                            except Exception as pex_v_err:
                                logger.warning(f"Pexels Video fallback failed: {pex_v_err}")
                        return await _gen_ai_image()
                else:
                    pexels_key = os.getenv("PEXELS_API_KEY")
                    want_stock = _pick_visual_source(req, scene, i) == "stock_video"
                    if want_stock and pexels_key:
                        await _update_job(job_id, message=f"Đang tìm video Pexels cho cảnh {i+1}/{total}...")
                        try:
                            return await _fetch_stock_video_cached(
                                img_prompt, final_img_path, imagen_aspect, pexels_key,
                                needed_duration=_estimate_scene_duration(text, voice, scene_rate),
                                used_ids=stock_used_ids, api_key=api_key,
                                source_meta=vis_meta,
                            )
                        except Exception as pexels_err:
                            logger.warning(f"Pexels video cho cảnh {i+1} thất bại ({pexels_err}). Rơi về ảnh AI.")

                    await _update_job(job_id, message=f"Đang sinh ảnh AI cho cảnh {i+1}/{total}...")
                    try:
                        await _gen_ai_image()
                    except Exception:
                        _create_placeholder_image(final_img_path)
                        _mark("placeholder")
                    return final_img_path

            # Chạy song song TTS và Sinh ảnh (Giảm 50% thời gian!)
            (scene_duration, scene_wbs, audio_path), image_path = await asyncio.gather(_do_tts(), _do_visuals())
            
            scene["image_path"] = image_path
            scene["audio_path"] = audio_path
            # Nguồn hình thật + truy vấn stock đã dùng: lưu vào scene để nó đi cả vào
            # project state, log tổng kết và (sau này) badge trên UI.
            scene["visual_source_used"] = vis_meta.get("source", "unknown")
            scene["is_veo_scene"] = vis_meta.get("is_veo_scene", False)
            if vis_meta.get("query"):
                scene["stock_query_used"] = vis_meta["query"]
            # computed_duration sẽ được tính lại chính xác hơn trong build_scene_timeline (motion_effects)
            scene["computed_duration"] = scene_duration
            scene["word_boundaries"] = scene_wbs

            # Checkpoint tự động lưu project state sau từng scene. to_thread: đây là ghi
            # đĩa đồng bộ (json.dump + os.replace) chạy N lần/video (N = số cảnh) ngay
            # trong event loop chính — chặn broadcast tiến độ WebSocket của job khác.
            from services import project_service
            await asyncio.to_thread(project_service.save_project_state, job_id, {
                "job_id": job_id,
                "title": getattr(req, "topic", None) or f"Dự án {job_id[:8]}",
                "mode": mode,
                "scenes": scenes,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": "generating_assets",
                "req": req.model_dump(mode='json')
            })

        # ── Tổng kết nguồn hình: nói cho người dùng biết video này thật ra làm từ đâu ──
        # Trước đây thông tin này bị chôn trong log WARNING rời rạc, nên hiện tượng "hết
        # quota ảnh Gemini nên cả video thành ảnh stock tĩnh" hoàn toàn vô hình.
        _tom_tat_nguon = _summarize_visual_sources(scenes)
        if _tom_tat_nguon:
            logger.info(f"[VisualSources] {_tom_tat_nguon}")
            await _update_job(job_id, message=f"Nguồn hình: {_tom_tat_nguon}")

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
                logger.warning(f"Beat Sync warning (non-fatal): {bs_err}")

        # ── UX: bỏ hẳn Hook nếu hiệu ứng cần chữ mà user để trống ô nhập ──────────
        # blackout_question/typewriter_quote KHÔNG có nội dung nào khác ngoài chữ —
        # để trống thì trước đây vẫn ra 1.5-2.5s màn hình đen tuyền/tối om (không chữ,
        # không hình) đúng vào khoảnh khắc quan trọng nhất để giữ chân người xem, còn
        # dời giọng đọc lùi vô ích theo. Coi như user không chọn hook gì: Cảnh 1 hiện
        # ngay từ 0s, không tốn giây nào cho một khung hình rỗng.
        #
        # LỖI CŨ (phát hiện thêm khi rà lại): kiểm tra nhầm `hook_quote` — field UI
        # thật sự cho 2 hiệu ứng này là "TIÊU ĐỀ HOOK CHỮ" (hook_text); hook_quote là
        # "TRÍCH DẪN HOOK BÌA SÁCH", chỉ áp dụng carousel_quote. User điền đúng ô theo
        # nhãn UI (hook_text) vẫn bị coi là rỗng vì code kiểm tra sai field.
        # FALLBACK: Nếu project cũ (hoặc Gemini) lỡ sinh text vào hook_quote thay vì hook_text
        if req.hook_effect in {"typewriter_quote", "blackout_question"}:
            if not (req.hook_text or "").strip() and (req.hook_quote or "").strip():
                req.hook_text = req.hook_quote

        HOOK_TEXT_REQUIRED = {"blackout_question", "typewriter_quote"}
        if req.hook_effect in HOOK_TEXT_REQUIRED and not (req.hook_text or "").strip():
            logger.info(f"[Hook] '{req.hook_effect}' rỗng chữ — bỏ qua hook (hook_effect=none).")
            req.hook_effect = "none"

        # ── Hook đầu video: đẩy TOÀN BỘ mốc thời gian lùi lại để giọng đọc không bị
        # lớp phủ hook đè lên. Chỉ dời tiếng + phụ đề; lớp phủ hook vẫn ở 0-hook_duration.
        # Đặt SAU beat sync vì beat sync tự tính lại start_time từ duration.
        #
        # LỖI CŨ: điều kiện này chỉ khớp "carousel_quote" — khi thêm 3 hook mới
        # (blackout_question/typewriter_quote/breathing_vignette) không ai generalize
        # chỗ này, nên giọng đọc Cảnh 1 luôn bắt đầu ngay t=0, chạy đè bên dưới lớp phủ
        # hook mới trong suốt 1.5-3.0s. Giờ tra qua resolve_hook_timing() (nguồn chân lý
        # duy nhất, xem video_service.py) nên hook mới thêm sau này tự động được dời
        # đúng, không cần sửa file này nữa — kể cả khi thời lượng hook đó là ĐỘNG
        # (blackout_question/typewriter_quote tính theo độ dài hook_text, xem
        # DYNAMIC_DURATION_HOOKS) chứ không còn là số cố định.
        from services.video_service import resolve_hook_timing
        hook_timing = resolve_hook_timing(req.hook_effect, req.hook_text)
        if hook_timing:
            lead = hook_timing["narration_lead"]
            for s in scenes:
                s["start_time"] = s.get("start_time", 0.0) + lead
            await _update_job(
                job_id,
                message=f"Dời giọng đọc {lead:.2f}s để tránh đè hiệu ứng mở đầu...",
            )

        from services.motion_effects import apply_ken_burns, resolve_motion, normalize_stock_clip
        from services.video_service import ASPECT_RATIO_SIZES
        frame_size = ASPECT_RATIO_SIZES.get(aspect_ratio, (1080, 1920))

        # LỖI CŨ: mỗi cảnh (đúc Ken Burns / chuẩn hoá clip stock) chạy TUẦN TỰ dù không
        # phụ thuộc cảnh khác — chỉ đọc/ghi biến cục bộ của chính cảnh đó. N cảnh = N lệnh
        # ffmpeg nối đuôi nhau trong khi có thể chạy song song. Giới hạn bằng semaphore
        # (KHÔNG song song vô hạn): mỗi lệnh ffmpeg là 1 process CPU-bound, thả hết N cảnh
        # (có thể 20-30) cùng lúc sẽ tranh CPU/đĩa với chính nó và với job render khác
        # đang chạy song song trong cùng process (đường này không qua render_worker nên
        # không bị MAX_CONCURRENT_RENDERS chặn).
        _visual_sem = asyncio.Semaphore(min(4, os.cpu_count() or 4))
        _visual_done = 0

        async def _process_scene_visual(i: int, s: dict) -> dict:
            nonlocal _visual_done
            async with _visual_sem:
                scene_effect = s.get("visual_effect", "")
                img_path = s["image_path"]
                duration = s.get("computed_duration", 3.0)
                start_time = s.get("start_time", 0.0)

                # MỌI ảnh tĩnh đều phải đúc thành .mp4 đúng khung hình đích — kể cả khi
                # user tắt Ken Burns. Lý do là điều kiện vào FastAssembly: can_assemble()
                # đòi mọi cảnh vừa là video vừa đúng độ phân giải. Chỉ cần MỘT cảnh còn
                # là .png là cả job rơi về MoviePy (đơn luồng, không GPU) — 19 cảnh mất
                # 30-45 phút, trong khi FFmpeg làm cùng việc đó trong ~15-20 giây.
                # Cái giá phải trả: ~0.2s/cảnh để đúc clip đứng yên. Quá hời.
                is_video_asset = img_path.lower().endswith((".mp4", ".mov"))
                if not is_video_asset:
                    out_mp4 = img_path + f"_{i}.mp4"
                    if req.use_ken_burns:
                        # Hook Zoom Boost: cảnh đầu zoom mạnh hơn (1.0→1.35) tạo "cú đấm"
                        # thị giác giữ chân người xem trong 2-3 giây đầu. Đây là cờ
                        # bật/tắt thật sự. NẾU ĐÃ BẬT HOOK MÁY XÈNG (carousel_quote), thì
                        # huỷ bỏ zoom boost ở cảnh 1 vì Hook Máy Xèng đã diễn vai trò hút
                        # mắt với ảnh bìa rồi, lặp lại sẽ dư thừa.
                        hook_boost = bool(i == 0 and req.hook_zoom_boost and req.hook_effect != "carousel_quote")
                        pan_dir, kb_zoom_start, kb_zoom_end = resolve_motion(scene_effect, i, hook_boost=hook_boost)
                    else:
                        pan_dir, kb_zoom_start, kb_zoom_end = "center", 1.0, 1.0   # đứng im hoàn toàn
                    try:
                        await asyncio.to_thread(
                            apply_ken_burns,
                            image_path=img_path, output_path=out_mp4, duration=duration, fps=30,
                            pan_direction=pan_dir, zoom_start=kb_zoom_start, zoom_end=kb_zoom_end,
                            resolution=frame_size,
                        )
                        img_path = out_mp4
                    except Exception as kb_err:
                        # Giữ ảnh tĩnh: job vẫn chạy được (rơi về MoviePy, chậm) thay vì chết hẳn.
                        logger.error(
                            f"[Main] Cảnh {i+1}: đúc ảnh thành video thất bại ({kb_err}). Giữ ảnh tĩnh.",
                            exc_info=True,
                        )
                elif is_video_asset:
                    # Clip stock/Veo: cắt đúng thời lượng cảnh (ưu tiên đoạn giữa), ping-pong
                    # nếu ngắn, ép về đúng khung + đồng chất màu. Lỗi thì giữ nguyên file
                    # gốc — video_service vẫn tự xử lý được, chỉ là không đẹp bằng.
                    norm_mp4 = f"{os.path.splitext(img_path)[0]}_norm{i}.mp4"
                    try:
                        await asyncio.to_thread(
                            normalize_stock_clip,
                            video_path=img_path, output_path=norm_mp4, duration=duration,
                            resolution=frame_size, fps=30,
                        )
                        img_path = norm_mp4
                    except Exception as norm_err:
                        logger.warning(f"[StockNorm] Cảnh {i+1} chuẩn hoá thất bại ({norm_err}). Dùng clip gốc.")

                # Hook SFX: tự thêm 'riser' mở màn cho cảnh đầu nếu bật Hook Zoom Boost + SFX
                # và cảnh chưa có sẵn hiệu ứng âm thanh nào.
                scene_sfx = s.get("sfx", "")
                if i == 0 and req.hook_zoom_boost and req.use_sfx and not scene_sfx:
                    scene_sfx = "riser"

                result = {
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
                    # Vi chỉnh nhạc nền riêng cảnh này (0-1). None = theo mức chung.
                    "bgm_volume": s.get("bgm_volume"),
                    # True = ảnh gốc VỐN LÀ video (stock/Veo), không phải ảnh tĩnh đúc Ken
                    # Burns. ffmpeg_assembler dùng để né transition "bóp méo" (squeezeh/
                    # squeezev) giữa 2 cảnh quay người/vật thật — xem chú thích ở đó.
                    "is_stock_video": is_video_asset,
                }
                _visual_done += 1
                await _update_job(
                    job_id, message=f"Đang dựng hình/video cảnh: {_visual_done}/{len(scenes)}...",
                )
                return result

        # asyncio.gather GIỮ ĐÚNG thứ tự kết quả theo thứ tự coroutine đưa vào (không phải
        # thứ tự hoàn thành) — scene_assets[i] luôn khớp scenes[i], bgm_volume_segments và
        # mọi chỗ dùng index bên dưới không cần đổi gì.
        scene_assets = list(await asyncio.gather(
            *[_process_scene_visual(i, s) for i, s in enumerate(scenes)]
        ))

        # ── Nhạc nền theo từng cảnh ──
        # Chỉ gom những cảnh user CHỦ ĐỘNG chỉnh; cảnh không chỉnh không sinh đoạn nào,
        # nên video không dùng tính năng này vẫn ra đúng biểu thức `volume=` cũ.
        # Mốc thời gian lấy y như phụ đề và track giọng đọc (hook carousel là lớp phủ
        # `enable='lt(t,...)'`, KHÔNG đẩy timeline — xem ffmpeg_assembler.assemble).
        bgm_volume_segments = [
            (a["start_time"], a["start_time"] + a["duration"], float(a["bgm_volume"]))
            for a in scene_assets
            if a.get("bgm_volume") is not None
        ]
        if bgm_volume_segments:
            await _update_job(
                job_id,
                message=f"Áp dụng nhạc nền riêng cho {len(bgm_volume_segments)} cảnh...",
            )

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

        render_kwargs = build_render_kwargs(req, aspect_ratio, mode, master_audio_path)
        # Tổng thời lượng cho thanh tiến trình FFmpeg vẽ ở bước master.
        # PHẢI cộng cả outro: video_service làm video dài thêm đúng bằng chừng đó
        # (final_duration += outro_duration). Thiếu nó thì thanh tiến trình chạy hết 100%
        # rồi biến mất ở mấy giây cuối. Xem video_service.resolve_outro_timing().
        from services.video_service import resolve_outro_text, resolve_outro_timing
        # Nguồn chữ outro đi qua ĐÚNG MỘT hàm dùng chung với video_service và
        # /api/timing-profile — trước đây phép chọn này được gõ lại ở cả ba nơi và chỉ
        # được giữ khớp bằng một dòng comment dặn "PHẢI khớp từng chữ".
        outro_timing = resolve_outro_timing(
            req.outro_effect,
            resolve_outro_text(req.outro_text, req.cta_text, req.hook_text),
        )
        outro_duration = outro_timing["duration"] if outro_timing else 0.0
        video_total_duration = (max(
            (a["start_time"] + a["duration"]) for a in scene_assets
        ) if scene_assets else 0.0) + outro_duration

        actual_intro_bgm_duration = 0.0
        if intro_bgm_path and scene_assets:
            actual_intro_bgm_duration = req.intro_bgm_duration
            if actual_intro_bgm_duration <= 0.0:
                # "Hết cảnh 1" = thời điểm cảnh 1 KẾT THÚC TRÊN TIMELINE, không phải độ
                # dài của nó. Hai con số này lệch nhau đúng bằng phần dời do hook: với
                # carousel_quote (lead 4.5s), lấy nhầm `duration` làm nhạc intro tắt sớm
                # 4.5 giây — fade-out rơi vào GIỮA lời thoại cảnh 1, chỗ nghe rõ nhất.
                first = scene_assets[0]
                actual_intro_bgm_duration = first["start_time"] + first["duration"]

        master_kwargs = dict(
            bgm_path=bgm_path,
            intro_bgm_path=intro_bgm_path,
            intro_bgm_duration=actual_intro_bgm_duration,
            total_duration=video_total_duration,
            use_gpu=req.use_gpu_encode,
            bgm_volume=req.bgm_volume,
            watermark_text=req.watermark_text,
            watermark_logo=_watermark_logo_path(req.watermark_logo),
            color_grading=req.color_grading,
            subtitle_style=req.subtitle_style,
            hook_effect=req.hook_effect,
            bgm_volume_segments=bgm_volume_segments,
            use_audio_ducking=req.use_audio_ducking,
            narration_tone=req.narration_tone or "viral",
            use_pattern_interrupt=req.use_pattern_interrupt,
            # Cùng con số mà video_service dùng để dựng clip hook (hook_timing ở trên) —
            # bước master cần biết hook dài bao nhiêu để Pattern Interrupt không chớp đè
            # lên khung mở màn. Lệch nhau là cú chớp rơi vào giữa hook.
            hook_duration=(hook_timing or {}).get("duration", 0.0),
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
            # DÙNG LẠI chính render_kwargs của đường worker, không gõ lại danh sách tham
            # số lần thứ hai: trước đây hai chỗ này là hai bản liệt kê tay song song, sửa
            # một bên quên bên kia là video render inline ra khác video render qua worker.
            # Cảnh báo "đang chạy đường chậm" cũng phải tới được người dùng ở nhánh này.
            # Gom vào list rồi đẩy SAU khi render xong, thay vì gọi _update_job ngay:
            # callback chạy trong worker thread của to_thread, còn _update_job là coroutine
            # của event loop — gọi thẳng từ thread khác là sai luồng.
            fallback_notes: list[str] = []
            await asyncio.to_thread(
                video_service.render_final_video,
                scene_assets, raw_video,
                on_fallback=fallback_notes.append,
                **render_kwargs,
            )
            for note in fallback_notes:
                await _update_job(job_id, message=note)
            if mode != "photo_slideshow":
                await asyncio.to_thread(
                    video_service.generate_ass_file, scene_assets, output_srt_path,
                    mode, subtitle_style=req.subtitle_style,
                    hook_text=req.hook_text, hook_effect=req.hook_effect,
                    video_width=frame_size[0], video_height=frame_size[1],
                )
            await _update_job(job_id, message="Đang Mastering Âm thanh & Tối ưu Video...", progress=90)
            from services.audio_mix_service import master_audio_and_export
            from services.video_service import VOICE_SIDECHAIN_SUFFIX

            # Cùng quy ước hậu tố với đường worker — hai nhánh phải nhìn thấy cùng file.
            inline_sidechain = raw_video + VOICE_SIDECHAIN_SUFFIX
            if not os.path.isfile(inline_sidechain):
                inline_sidechain = None
            try:
                # DÙNG LẠI master_kwargs đã dựng cho đường worker ở trên, không gõ lại
                # ~13 tham số lần thứ hai (kể cả gọi _watermark_logo_path() lần nữa cho
                # cùng 1 input) — đúng lớp trùng lặp mà render_kwargs đã tránh được, nhưng
                # trước đây chưa áp dụng cho master_kwargs. Loại "subtitle_style" và
                # "hook_effect": 2 key này chỉ dành cho generate_ass_file() ở đường worker
                # (render_worker._worker_main), master_audio_and_export() không nhận.
                await asyncio.to_thread(
                    master_audio_and_export,
                    input_video_path=raw_video, output_path=output_video_path,
                    sidechain_audio_path=inline_sidechain,
                    ass_subtitle_path=output_srt_path if os.path.isfile(output_srt_path) else None,
                    **{k: v for k, v in master_kwargs.items() if k not in ("subtitle_style", "hook_effect")},
                )
                if os.path.isfile(raw_video):
                    os.remove(raw_video)
                if inline_sidechain and os.path.isfile(inline_sidechain):
                    os.remove(inline_sidechain)
            except Exception as err:
                logger.error(f"FFmpeg Mastering error: {err}", exc_info=True)
                if os.path.isfile(raw_video):
                    try:
                        for _ in range(3):
                            try:
                                os.replace(raw_video, output_video_path)
                                break
                            except PermissionError:
                                await asyncio.sleep(1)
                    except OSError:
                        pass

            # LỖI CŨ: luôn báo status="done" ở đây bất kể nhánh `except` phía trên có
            # thật sự tạo ra output_video_path hay không — mastering lỗi + raw_video
            # không tồn tại (hoặc os.replace() cũng lỗi, bị nuốt trong `except OSError:
            # pass`) vẫn báo "Hoàn tất!" kèm video_url trỏ tới file không tồn tại (404).
            # Chỉ báo done khi file thật sự nằm ở output_video_path.
            if os.path.isfile(output_video_path):
                await _update_job(
                    job_id, status="done", progress=100, message="Hoàn tất!",
                    video_url=f"/api/download/{job_id}.mp4",
                    srt_url=f"/api/download/{job_id}.ass" if mode != "photo_slideshow" else None,
                )
            else:
                await _update_job(
                    job_id, status="error",
                    error="Không tạo được file video đầu ra",
                    message=(
                        "❌ Mastering âm thanh lỗi và không phục hồi được video thô. "
                        "Xem backend/logs/main.log để biết chi tiết."
                    ),
                )
        else:
            # Worker đang chạy → poll file status và broadcast qua WebSocket
            from services.render_worker import cancel_render, cleanup_status, is_render_active

            # LỖI CŨ: mọi đường thoát khỏi vòng poll đều là `break` bình thường, nên khối
            # `except` bên dưới KHÔNG chạy và hàm rơi thẳng xuống phần dọn asset ở cuối —
            # xoá sạch ảnh + giọng đọc kể cả khi worker báo lỗi. Ngược hẳn ý đồ đã ghi
            # trong chính khối except ("giữ lại để resume, khỏi tốn API chạy lại").
            # Người dùng bấm render lại sau một lần lỗi là tốn quota Gemini/TTS lần nữa.
            while True:
                await asyncio.sleep(RENDER_POLL_INTERVAL)
                ws = read_render_status(job_id)

                if ws is not None:
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
                        render_failed = ws.get("status") == "error"
                        cleanup_status(job_id)
                        break

                # ── Hai lưới an toàn cho trường hợp worker KHÔNG kịp ghi trạng thái cuối ──
                #
                # LỖI CŨ: vòng lặp này chỉ thoát khi đọc được status "done"/"error". Nhưng
                # spawn_render() đã ghi sẵn status "rendering" TRƯỚC khi start process, nên
                # read_render_status không bao giờ trả None nữa. Nếu worker bị giết cứng —
                # MemoryError của MoviePy, Windows kill, PM2 max_memory_restart — thì khối
                # `except` trong _worker_main KHÔNG chạy, file status đứng nguyên ở
                # "rendering", và vòng này quay mãi mãi: WebSocket phát "Đang render..." vô
                # hạn còn người dùng ngồi chờ một job đã chết từ lâu.
                if not is_render_active(job_id):
                    logger.error(
                        "[Render] Worker của job %s đã chết mà không ghi trạng thái cuối.",
                        job_id,
                    )
                    cleanup_status(job_id)
                    await _update_job(
                        job_id, status="error", progress=0,
                        error="Render worker dừng đột ngột",
                        message=(
                            "❌ Tiến trình render dừng đột ngột (thường là hết RAM khi dựng "
                            "video dài). Ảnh và giọng đọc đã sinh vẫn được giữ lại — mở dự án "
                            "và render lại sẽ không tốn thêm quota API. "
                            "Chi tiết lỗi: backend/logs/render_worker.log"
                        ),
                    )
                    render_failed = True
                    break

                # Process còn sống nhưng im lặng quá lâu = treo (FFmpeg đợi I/O ổ mạng,
                # deadlock, driver GPU treo...).
                last_beat = (ws or {}).get("updated_at", 0)
                if last_beat and time.time() - last_beat > RENDER_STALL_TIMEOUT:
                    logger.error(
                        "[Render] Job %s không nhúc nhích %.0f giây — coi như treo, đang huỷ để giải phóng slot render.",
                        job_id, time.time() - last_beat,
                    )
                    # LỖI CŨ: chỉ báo lỗi cho user rồi break, KHÔNG thật sự giết process con
                    # (write_videofile/ffmpeg của MoviePy không có tham số timeout). Process
                    # treo vẫn nằm nguyên trong render_worker._active_processes, chiếm vĩnh
                    # viễn 1 trong 2 slot MAX_CONCURRENT_RENDERS dù UI đã báo lỗi — mọi job
                    # sau chỉ còn tranh nhau 1 slot, rồi 0. cancel_render() dùng đúng cơ chế
                    # kill process-tree của nút "Huỷ" thủ công, KHÔNG đụng tới ảnh/giọng đọc
                    # (những file đó là input của worker, không phải thứ cancel_render xoá).
                    try:
                        cancel_render(job_id)
                    except Exception as cancel_err:
                        logger.error(f"[Render] Không huỷ được worker treo của job {job_id}: {cancel_err}")
                    await _update_job(
                        job_id, status="error",
                        error="Render treo quá lâu",
                        message=(
                            f"⚠️ Không có tín hiệu nào từ tiến trình render trong "
                            f"{RENDER_STALL_TIMEOUT // 60} phút — đã tự huỷ để giải phóng slot render. "
                            f"Ảnh và giọng đọc đã sinh vẫn được giữ lại, render lại sẽ không tốn "
                            f"thêm quota API. Chi tiết: backend/logs/render_worker.log."
                        ),
                    )
                    render_failed = True
                    break

    except Exception as e:
        # exc_info=True: đây là lưới cuối của TOÀN BỘ pipeline. Chỉ log str(e) thì
        # mất sạch traceback — đúng cái đã khiến sự cố 2026-07-11 phải mò 17 ngày log
        # cũ mới tìm ra dòng gây lỗi. Có traceback là biết ngay module/dòng nào chết.
        logger.error(f"Exception in pipeline: {e}", exc_info=True)
        await _update_job(job_id, status="error", error=str(e), message=f"Lỗi: {e}")
        # Giữ lại ảnh/audio đã sinh khi lỗi để có thể sinh lại từng cảnh / resume,
        # thay vì xoá sạch khiến lần sau phải chạy lại toàn bộ.
        if req.upload_session_id:
            cleanup_upload(req.upload_session_id)
        return

    # Chỉ dọn asset tạm khi pipeline THẬT SỰ thành công. Render lỗi thì giữ nguyên ảnh
    # và giọng đọc để lần render lại nhặt được từ cache, khỏi tốn quota Gemini/TTS —
    # cùng lý do với khối `except` bên trên. Chúng vẫn được dọn sau 24h bởi
    # _cleanup_old_outputs(), nên không có nguy cơ tích rác vĩnh viễn.
    if not render_failed:
        shutil.rmtree(job_dir_audio, ignore_errors=True)
        shutil.rmtree(job_dir_images, ignore_errors=True)
    else:
        logger.info(
            "[Render] Job %s lỗi — giữ lại ảnh/giọng đọc trong %s và %s để render lại.",
            job_id, job_dir_audio, job_dir_images,
        )
    if req.upload_session_id:
        cleanup_upload(req.upload_session_id)


def _create_placeholder_image(path: str):
    """Ảnh placeholder đơn giản khi Imagen lỗi, để pipeline không bị chặn."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1080, 1920), color=(30, 30, 40))
    draw = ImageDraw.Draw(img)
    draw.text((100, 900), "AI Video Maker", fill=(200, 200, 210))
    img.save(path)


# ── Chính sách giữ file, tách theo GIÁ TRỊ của thứ bị xoá ───────────────────
#
# LỖI CŨ: video thành phẩm và file tạm dùng CHUNG một hạn 24 giờ, trong khi ảnh ghi đè
# được giữ 30 ngày. Thứ tự ưu tiên ngược hẳn: thứ tốn nhiều thời gian và quota API nhất
# để tạo ra lại là thứ bị xoá sớm nhất. Người dùng render buổi tối, hôm sau mở lại thấy
# mục dự án còn nguyên nhưng bấm tải thì 404 — không có cảnh báo nào.
#
# Nguyên tắc: càng khó tạo lại thì giữ càng lâu.
OUTPUT_MAX_AGE_DAYS = 14      # mp4/ass thành phẩm — tốn cả tiếng render + quota API
OVERRIDE_MAX_AGE_DAYS = 30    # ảnh người dùng tự chuẩn bị — không tái tạo được
JOB_ASSET_MAX_AGE_HOURS = 24  # audio/images từng cảnh — cache dựng lại được, và cồng kềnh
TEMP_MAX_AGE_HOURS = 6        # rác của MoviePy + bản nghe thử — vô giá trị


async def _cleanup_old_outputs():
    """Dọn file cũ theo hạn riêng của từng loại (xem các hằng số ngay trên)."""
    now = datetime.now(timezone.utc).timestamp()

    def _sweep_files(dirpath: str, max_age_seconds: float, label: str):
        removed = 0
        try:
            names = os.listdir(dirpath)
        except OSError:
            return
        for fname in names:
            fpath = os.path.join(dirpath, fname)
            try:
                if not os.path.isfile(fpath) or (now - os.path.getmtime(fpath)) <= max_age_seconds:
                    continue
                os.remove(fpath)
                removed += 1
            except OSError:
                pass  # đang bị mở → lượt dọn sau
        if removed:
            logger.info("[Cleanup] Xoá %d file quá hạn trong %s.", removed, label)

    # 1. Video/phụ đề thành phẩm
    _sweep_files(OUTPUT_DIR, OUTPUT_MAX_AGE_DAYS * 86400, "output")

    # 2. Ảnh/video người dùng tải lên để ghi đè một cảnh cụ thể. Phải sống qua nhiều
    #    phiên "Chỉnh sửa & Render lại" — xoá theo nhịp file tạm sẽ làm cảnh mất hình
    #    khi mở lại dự án hôm sau.
    _sweep_files(OVERRIDES_DIR, OVERRIDE_MAX_AGE_DAYS * 86400, "overrides")

    # 3. File tạm MoviePy bỏ lại khi encode chết giữa chừng, và bản nghe thử mà client
    #    ngắt kết nối trước khi BackgroundTask kịp xoá.
    _sweep_files(TEMP_DIR, TEMP_MAX_AGE_HOURS * 3600, "temp")

    # 4. Thư mục asset theo job (audio/, images/). Hạn ngắn vì đây là phần cồng kềnh
    #    nhất (images/ thường vài trăm MB) và cache media đã giữ bản dùng lại được.
    #    Cũng chính là lưới dọn cho asset của những job render lỗi mà pipeline cố ý
    #    giữ lại — xem cuối _run_render_pipeline.
    for base_dir in (AUDIO_DIR, IMAGES_DIR):
        try:
            job_folders = os.listdir(base_dir)
        except OSError:
            continue
        for job_folder in job_folders:
            job_path = os.path.join(base_dir, job_folder)
            try:
                if not os.path.isdir(job_path):
                    continue
                if (now - os.path.getmtime(job_path)) / 3600 <= JOB_ASSET_MAX_AGE_HOURS:
                    continue
            except OSError:
                continue
            shutil.rmtree(job_path, ignore_errors=True)


def _restore_jobs_from_disk() -> int:
    """Dựng lại JOBS sau khi backend khởi động lại. Trả về số job khôi phục được.

    VÌ SAO CẦN: JOBS là dict nằm trong RAM, mất sạch mỗi lần tiến trình chết. Nhưng
    ecosystem.config.js bật `autorestart: true` — tức kiến trúc ĐÃ TÍNH chuyện restart —
    và setup-pm2-autostart.bat còn dựng lại cả khi đăng nhập Windows. Sau mỗi lần đó,
    giao diện hỏi /api/job-status/{id} của job vừa nãy thì nhận 404 và WebSocket không
    bám lại được: người dùng mất dấu công việc của chính mình, kể cả những video đã
    render XONG và file mp4 vẫn nằm nguyên trên đĩa.

    Hai nguồn, theo thứ tự tin cậy giảm dần:
      1. render_status/*.json — job đang render dở lúc tiến trình chết.
      2. output/*.mp4        — job đã hoàn tất, chỉ mất bản ghi trong RAM.
    """
    restored = 0

    # ── 1. Job đang render dở ────────────────────────────────────────────────
    # Worker là process con daemon nên chết theo tiến trình cha; sau restart không còn
    # ai poll file status này nữa. Job nào chưa có mp4 thì coi như đứt gánh, đánh dấu
    # lỗi ngay để giao diện thôi quay vòng chờ.
    try:
        status_files = os.listdir(RENDER_STATUS_DIR)
    except OSError:
        status_files = []

    for fname in status_files:
        if not fname.endswith(".json"):
            continue
        job_id = fname[: -len(".json")]
        fpath = os.path.join(RENDER_STATUS_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            data = {}

        mp4 = os.path.join(OUTPUT_DIR, f"{job_id}.mp4")
        ass = os.path.join(OUTPUT_DIR, f"{job_id}.ass")
        finished = data.get("status") == "done" or os.path.isfile(mp4)

        JOBS[job_id] = JobState(
            job_id=job_id,
            status="done" if finished else "error",
            progress=100 if finished else data.get("progress", 0),
            message=(
                "Hoàn tất!" if finished else
                "❌ Backend khởi động lại giữa lúc đang render nên job này bị đứt. "
                "Ảnh và giọng đọc đã sinh vẫn còn — render lại sẽ không tốn thêm quota API."
            ),
            error=None if finished else "Bị gián đoạn do backend khởi động lại",
            video_url=f"/api/download/{job_id}.mp4" if os.path.isfile(mp4) else None,
            srt_url=f"/api/download/{job_id}.ass" if os.path.isfile(ass) else None,
            created_at=_mtime_utc(fpath),
        )
        restored += 1
        # File status đã hết vai trò: không còn worker nào ghi vào nó nữa.
        try:
            os.remove(fpath)
        except OSError:
            pass

    # ── 2. Video đã render xong còn trên đĩa ─────────────────────────────────
    # Để link tải trong lịch sử vẫn bấm được sau restart thay vì trả 404.
    try:
        output_files = os.listdir(OUTPUT_DIR)
    except OSError:
        output_files = []

    for fname in output_files:
        if not fname.endswith(".mp4"):
            continue
        job_id = fname[: -len(".mp4")]
        if job_id in JOBS:
            continue
        mp4 = os.path.join(OUTPUT_DIR, fname)
        ass = os.path.join(OUTPUT_DIR, f"{job_id}.ass")
        JOBS[job_id] = JobState(
            job_id=job_id, status="done", progress=100, message="Hoàn tất!",
            video_url=f"/api/download/{job_id}.mp4",
            srt_url=f"/api/download/{job_id}.ass" if os.path.isfile(ass) else None,
            created_at=_mtime_utc(mp4),
        )
        restored += 1

    # created_at lấy từ mtime nên _prune_old_jobs cắt đúng những job cũ nhất, thay vì
    # cắt bừa theo thứ tự đọc thư mục.
    _prune_old_jobs()
    return restored


def _mtime_utc(path: str) -> datetime:
    """mtime của file dưới dạng datetime UTC (mặc định về 'bây giờ' nếu file biến mất)."""
    try:
        return datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
    except OSError:
        return datetime.now(timezone.utc)


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

@app.delete("/api/jobs/{job_id}")
async def cancel_job(job_id: str):
    from services.render_worker import cancel_render
    success = cancel_render(job_id)
    if success:
        return {"status": "success", "message": "Đã huỷ render thành công."}
    else:
        raise HTTPException(status_code=404, detail="Job không tồn tại hoặc đã kết thúc.")

@app.get("/api/quota")
async def get_quota():
    return quota_service.get_quota()

def _balance_split_scenes(result, req: GenerateScriptRequest):
    """Cân lại nhịp các cảnh do Gemini chia ra từ kịch bản user dán vào (script_video).

    VÌ SAO CẦN: Gemini chia theo ý nghĩa nội dung chứ không theo đồng hồ, nên thường ra
    một cảnh 15 giây nằm cạnh một cảnh 1.5 giây. Ở mode này lời thoại là của user và
    được giữ nguyên văn 100%, nên việc dịch ranh giới cảnh KHÔNG đụng gì tới nội dung —
    chỉ đổi chỗ ngắt hình. image_prompt của cảnh chi phối được giữ lại (xem
    scene_balancer._build_scene) nên không tốn thêm một lần gọi Gemini nào.

    CHỈ áp dụng khi thật sự tốt hơn: cách chia của Gemini bám theo mạch kể, đổi nó mà
    không cải thiện được nhịp thì chỉ tổ làm mất công đạo diễn của nó.
    """
    from services import scene_balancer

    scenes = result.get("scenes") if isinstance(result, dict) else result
    if not scenes or len(scenes) < 2:
        return result

    try:
        balanced = scene_balancer.rebalance_scenes(scenes, req.voice, req.speech_rate)
    except Exception as e:
        # Cân nhịp là bước làm đẹp thêm — hỏng thì trả nguyên cách chia của Gemini,
        # tuyệt đối không để user mất cả kịch bản vừa sinh.
        logger.warning(f"[ScriptSplit] Bỏ qua bước cân nhịp: {e}", exc_info=True)
        return result

    before, after = balanced["report"]["before"], balanced["report"]["after"]
    tot_hon = after["off_pace"] < before["off_pace"] or (
        after["off_pace"] == before["off_pace"] and after["std"] < before["std"] * 0.8
    )
    if not tot_hon:
        logger.info("[ScriptSplit] Cách chia của Gemini đã đủ đều, giữ nguyên.")
        return result

    logger.info(
        f"[ScriptSplit] Cân lại nhịp: {before['scenes']} cảnh → {after['scenes']} cảnh, "
        f"cảnh dài nhất {before['longest']}s → {after['longest']}s, "
        f"lệch nhịp {before['off_pace']} → {after['off_pace']}."
    )
    if isinstance(result, dict):
        result = dict(result)
        result["scenes"] = balanced["scenes"]
        result["rebalance"] = balanced["report"]  # để UI nói cho user biết đã đổi gì
        return result
    return balanced["scenes"]


@app.post("/api/generate-script")
async def generate_script(req: GenerateScriptRequest):
    if req.mode not in VALID_MODES:
        raise HTTPException(status_code=400, detail=f"Mode không hợp lệ. Chọn 1 trong: {', '.join(VALID_MODES)}")
    
    try:
        scenes = []
        # Giữ lại nguyên bộ tham số sinh kịch bản để vòng VIẾT LẠI (nếu điểm chất lượng quá
        # thấp) dùng đúng cấu hình đó, chỉ khác ở `revision_notes`.
        gen_kwargs: dict | None = None
        if req.mode == "storyteller" or req.mode == "quiz_listicle":
            if not req.topic or not req.topic.strip():
                raise HTTPException(status_code=400, detail="Thiếu chủ đề (topic) cho mode này.")
            gen_kwargs = dict(
                topic=req.topic, num_scenes=req.num_scenes, mode=req.mode,
                art_style=req.art_style, api_key=req.gemini_api_key,
                target_duration=req.target_duration,
                narration_tone=req.narration_tone or "viral",
                character_description=req.character_description,
                sync_characters=req.sync_characters,
                content_niche=req.content_niche,
                variation_seed=req.variation_seed,
                prefer_stock_video=_wants_stock_footage(req),
            )
            scenes = await gemini_service.generate_script(**gen_kwargs)

        elif req.mode == "script_video":
            if not req.script_text or not req.script_text.strip():
                raise HTTPException(status_code=400, detail="Thiếu script text cho mode Script → Video.")
            scenes = await gemini_service.split_script_to_scenes(
                script_text=req.script_text, num_scenes=req.num_scenes,
                art_style=req.art_style, api_key=req.gemini_api_key,
                # Lời thoại vẫn giữ nguyên văn 100%; tone/niche chỉ quyết định
                # sfx/transition/emotion/nhịp đọc của từng cảnh.
                narration_tone=req.narration_tone or "viral",
                content_niche=req.content_niche,
                prefer_stock_video=_wants_stock_footage(req),
            )
            if req.auto_balance_scenes:
                scenes = _balance_split_scenes(scenes, req)

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
            # ── AI Script Reviewer (B2) ──
            try:
                _w_lo, _w_hi = gemini_service.scene_word_budget(
                    req.target_duration or "30s", req.num_scenes or 6
                )
                review_result = await gemini_service.review_script(
                    scenes, word_budget_hi=_w_hi, api_key=req.gemini_api_key,
                )
                # ── Viết lại 1 lượt nếu điểm dưới ngưỡng ──
                # Chỉ áp cho các mode SINH nội dung mới. script_video bị loại tuyệt đối: lời
                # thoại ở đó là của người dùng, giữ nguyên văn 100% là hợp đồng — "viết lại"
                # nghĩa là sửa lời người ta.
                if gen_kwargs and req.auto_retry_low_quality:
                    scenes, review_result = await gemini_service.regenerate_if_low_quality(
                        scenes, review_result,
                        word_budget_hi=_w_hi,
                        gen_kwargs=gen_kwargs,
                        api_key=req.gemini_api_key,
                    )
                scenes["review"] = review_result
            except Exception as review_err:
                logger.warning(f"Script Review skipped: {review_err}")
            return scenes
        else:
            # ── AI Script Reviewer (B2) ──
            response = {"scenes": scenes, "sentiment": "happy"}
            try:
                _w_lo, _w_hi = gemini_service.scene_word_budget(
                    req.target_duration or "30s", req.num_scenes or 6
                )
                review_result = await gemini_service.review_script(
                    response, word_budget_hi=_w_hi, api_key=req.gemini_api_key,
                )
                response["review"] = review_result
            except Exception as review_err:
                logger.warning(f"Script Review skipped: {review_err}")
            return response
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


class RebalanceRequest(BaseModel):
    scenes: List[Dict[str, Any]]
    voice: Optional[str] = None
    speech_rate: str = "+0%"


@app.post("/api/rebalance-scenes")
async def rebalance_scenes(req: RebalanceRequest):
    """Chia lại ranh giới cảnh cho đều nhịp, KHÔNG sửa nội dung.

    CHỈ TRẢ VỀ ĐỀ XUẤT — không tự lưu gì. Giao diện dựng preview trước/sau rồi để user
    quyết định áp dụng hay bỏ. Việc chia lại làm mất một số image_prompt (khi hai cảnh
    gộp làm một) nên không được phép tự động chạy sau lưng người dùng.
    """
    from services import scene_balancer

    if not req.scenes:
        raise HTTPException(status_code=400, detail="Chưa có cảnh nào để chia lại.")

    result = await asyncio.to_thread(
        scene_balancer.rebalance_scenes, req.scenes, req.voice, req.speech_rate
    )
    return result


class ResplitRequest(BaseModel):
    full_text: str
    scenes: List[Dict[str, Any]] = []
    voice: Optional[str] = None
    speech_rate: str = "+0%"
    # False = giữ đúng ranh giới người dùng đã chốt bằng dòng trống, không cân nhịp.
    rebalance: bool = True


@app.post("/api/resplit-script")
async def resplit_script(req: ResplitRequest):
    """
    Nhận TOÀN BỘ kịch bản đã sửa (một khối chữ, cảnh ngăn nhau bằng dòng trống) → chia
    lại thành cảnh, giữ nguyên ảnh/cảm xúc của các cảnh cũ tương ứng.

    CHỈ TRẢ VỀ ĐỀ XUẤT, giống /api/rebalance-scenes: chia lại có thể làm mất `image_prompt`
    của những cảnh bị gộp, nên tuyệt đối không chạy sau lưng người dùng.
    """
    from services import script_resplit

    if not (req.full_text or "").strip():
        raise HTTPException(status_code=400, detail="Kịch bản trống.")
    try:
        return await asyncio.to_thread(
            script_resplit.resplit, req.full_text, req.scenes,
            req.voice, req.speech_rate, req.rebalance,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class FullScriptPreviewRequest(BaseModel):
    scenes: List[Dict[str, Any]]
    voice: Optional[str] = None
    speech_rate: Optional[str] = "+0%"
    speech_pitch: Optional[str] = "+0Hz"


# Trần ký tự cho bản đọc thử cả bài. 12.000 ký tự ≈ 15 phút đọc — dài hơn mọi video
# ngắn, mà vẫn chặn được cú dán nhầm cả quyển sách vào ô nhập.
MAX_FULL_PREVIEW_CHARS = 12000


# Bản nghe thử để lại file trong TEMP_DIR cho tới khi trình duyệt tải về. Quá hạn này
# thì coi như user đã đóng tab — dọn đi, đừng để TEMP_DIR phình theo mỗi lần bấm.
FULL_PREVIEW_TTL_S = 3600


def _don_ban_nghe_thu_cu():
    """Xoá các file nghe thử quá hạn. Gọi mỗi lần tạo bản mới — rẻ và không cần cron."""
    gioi_han = time.time() - FULL_PREVIEW_TTL_S
    try:
        for ten in os.listdir(TEMP_DIR):
            if not ten.startswith("fullpreview_"):
                continue
            p = os.path.join(TEMP_DIR, ten)
            try:
                if os.path.isfile(p) and os.path.getmtime(p) < gioi_han:
                    os.remove(p)
            except OSError:
                pass
    except OSError:
        pass


async def _chay_nghe_thu_ca_bai(job_id: str, scene_texts: list[str], req: "FullScriptPreviewRequest"):
    """Sinh giọng cả bài dưới nền, cập nhật tiến độ qua JobState/WebSocket."""
    voice = req.voice or tts_service.DEFAULT_VOICE
    out_path = os.path.join(TEMP_DIR, f"fullpreview_{job_id}.mp3")
    da_bao: set = set()
    tong_canh = sum(1 for t in scene_texts if t.strip())

    async def _canh_bao(msg: str):
        if msg not in da_bao:
            da_bao.add(msg)
            await _update_job(job_id, message=msg)

    async def _tien_do(i: int, _n: int):
        xong = sum(1 for t in scene_texts[:i] if t.strip())
        await _update_job(
            job_id,
            progress=int(xong * 95 / max(1, tong_canh)),
            message=f"Đang đọc cảnh {i + 1}/{len(scene_texts)}...",
        )

    try:
        dur, scene_wbs, _ = await tts_service.synthesize_script_single_pass(
            scene_texts, out_path,
            voice=voice,
            rate=req.speech_rate or "+0%",
            pitch=req.speech_pitch or "+0Hz",
            warning_callback=_canh_bao,
            progress_callback=_tien_do,
        )
        written = tts_service._resolve_written_path(out_path)
        if not written:
            raise RuntimeError("Không sinh được giọng đọc (file rỗng).")

        # Mốc đầu/cuối của từng cảnh trên dải audio, để UI chạy con trỏ theo lời đọc.
        ranges = []
        for wbs in scene_wbs:
            if wbs:
                ranges.append([round(min(w["offset"] for w in wbs), 2),
                               round(max(w["offset"] + w["duration"] for w in wbs), 2)])
            else:
                ranges.append(None)

        await _update_job(
            job_id, status="done", progress=100,
            message=f"Đã đọc xong cả bài ({dur:.1f} giây).",
            audio_url=f"/api/preview-full-script/{job_id}/audio",
            scene_ranges=ranges,
            cache_scope=tts_service.narration_cache_scope(voice),
        )
    except Exception as e:
        logger.error(f"[FullPreview] Sinh giọng thất bại: {e}", exc_info=True)
        await _update_job(job_id, status="error", error=f"Không đọc thử được cả bài: {e}")


@app.post("/api/preview-full-script")
async def preview_full_script(req: FullScriptPreviewRequest, background_tasks: BackgroundTasks):
    """
    Đọc thử TOÀN BỘ kịch bản thành một dải audio liền. Chạy NỀN, trả về job_id.

    VÌ SAO KHÔNG LÀM ĐỒNG BỘ: đây là tính năng sinh ra cho giọng AI, mà giọng AI trên
    GPU máy này chạy chậm hơn thời gian thực ~8 lần (xem tts_service.get_omnivoice_rtf).
    Một kịch bản 20 cảnh = khoảng 15 phút — vượt xa mọi ngưỡng chờ của trình duyệt và
    proxy. Giữ đồng bộ thì đúng trường hợp cần dùng nhất lại là trường hợp chắc chắn
    hỏng, và user mất trắng cả 15 phút đó.

    Tiến độ đi qua CÙNG JobState/WebSocket với render, nên giao diện chỉ cần bám
    /api/job-status/{job_id} như mọi job khác.

    Giá trị kèm theo: bản đọc thử đi qua ĐÚNG synthesize_speech với ĐÚNG bộ tham số của
    lúc render, nên với giọng AI mỗi cảnh được nạp vào TTS cache — nghe xong một lượt là
    render không phải sinh lại giây nào (xem tts_service.narration_cache_scope).
    """
    if not req.scenes:
        raise HTTPException(status_code=400, detail="Chưa có cảnh nào để đọc thử.")

    scene_texts = [
        tts_service.strip_break_tags(
            tts_service._strip_emoji(s.get("text", "") or "")
        ).strip()
        for s in req.scenes
    ]
    tong = sum(len(t) for t in scene_texts)
    if not tong:
        raise HTTPException(status_code=400, detail="Kịch bản chưa có lời thoại nào.")
    if tong > MAX_FULL_PREVIEW_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Kịch bản dài {tong} ký tự, vượt giới hạn nghe thử {MAX_FULL_PREVIEW_CHARS}.",
        )

    _don_ban_nghe_thu_cu()
    job_id = str(uuid.uuid4())
    JOBS[job_id] = JobState(
        job_id=job_id, status="generating_assets", progress=0,
        message="Chuẩn bị đọc thử toàn bộ kịch bản...",
        mode="full_preview",
        cache_scope=tts_service.narration_cache_scope(req.voice or tts_service.DEFAULT_VOICE),
    )
    background_tasks.add_task(_chay_nghe_thu_ca_bai, job_id, scene_texts, req)
    return {
        "job_id": job_id,
        "scenes": len(scene_texts),
        "cache_scope": JOBS[job_id].cache_scope,
        # Ước tính dựa trên SỐ ĐO thật của máy này, None nếu chưa từng sinh giọng AI.
        "estimate": tts_service.uoc_tinh_thoi_gian_giong_ai(tong / 15.0),
    }


@app.get("/api/preview-full-script/{job_id}/audio")
async def preview_full_script_audio(job_id: str):
    """Tải bản đọc thử đã sinh xong. File sống tới FULL_PREVIEW_TTL_S để user tua lại."""
    from fastapi.responses import FileResponse

    safe = os.path.basename(job_id)
    written = tts_service._resolve_written_path(os.path.join(TEMP_DIR, f"fullpreview_{safe}.mp3"))
    if not written:
        raise HTTPException(status_code=404, detail="Bản đọc thử không còn — hãy bấm đọc lại.")
    return FileResponse(
        written,
        media_type="audio/wav" if written.endswith(".wav") else "audio/mpeg",
    )


@app.get("/api/timing-profile")
async def timing_profile(
    voice: str = "",
    rate: str = "+0%",
    hook_effect: str = "",
    hook_text: str = "",
    outro_effect: str = "",
    outro_text: str = "",
    cta_text: str = "",
):
    """Tốc độ đọc (từ/giây) + thời lượng hook/outro mà backend sẽ dùng khi render.

    Có endpoint này để giao diện KHÔNG phải giữ hằng số riêng: trước đây ScriptEditor
    tự nhân "12 từ/cảnh" trong khi backend tính bằng con số khác, nên cảnh báo trên màn
    hình và thời lượng video thật không bao giờ khớp nhau. Giờ UI hỏi đúng nguồn.
    `is_learned` cho biết con số đã được hiệu chỉnh từ số đo thật hay còn là mặc định.

    `hook`/`outro` trả về CÙNG con số mà pipeline render dùng thật (qua
    resolve_hook_timing / resolve_outro_timing). Tuyệt đối không tính lại bằng JS:
    blackout_question và typewriter_quote có thời lượng ĐỘNG theo độ dài chữ, nên một
    bản sao ở frontend sẽ lệch ngay khi ai đó chỉnh công thức ở Python.

    `narration_lead` khác `duration` ở carousel_quote: clip dài 4.5s nhưng lời thoại chỉ
    bị dời 2.35s vì pha Quote cố ý phủ lên đầu Cảnh 1.
    """
    from services import duration_model
    from services.video_service import (
        resolve_hook_timing,
        resolve_outro_text,
        resolve_outro_timing,
    )

    out = duration_model.profile_summary(voice or None, rate)

    ht = resolve_hook_timing(hook_effect, hook_text) if hook_effect else None
    out["hook"] = {
        "effect": hook_effect,
        "duration": round(ht["duration"], 2),
        "narration_lead": round(ht["narration_lead"], 2),
    } if ht else None

    # Cùng hàm chọn nguồn chữ mà pipeline render dùng thật — con số UI hiện ra không được
    # phép lệch với video xuất ra, và 2 hiệu ứng outro có thời lượng ĐỘNG theo độ dài chữ.
    ot = resolve_outro_timing(
        outro_effect, resolve_outro_text(outro_text, cta_text, hook_text)
    ) if outro_effect else None
    out["outro"] = {
        "effect": outro_effect,
        "duration": round(ot["duration"], 2),
    } if ot else None

    return out


@app.get("/api/tts-health")
async def tts_health():
    """Trạng thái hạ tầng TTS: OmniVoice/GPU/whisper-align sẵn sàng hay chưa."""
    return tts_service.get_tts_health()


# ---------------------------------------------------------------------------
# Voice Cloning (Phase 3) — upload mẫu giọng 5-10s → giọng OmniVoice cá nhân
# ---------------------------------------------------------------------------
ALLOWED_VOICE_SAMPLE_EXTS = {".wav", ".mp3", ".m4a", ".ogg", ".flac"}
MAX_VOICE_SAMPLE_SIZE = 15 * 1024 * 1024  # 15MB

# ── Tiền xử lý mẫu giọng clone ──────────────────────────────────────────────
# Chất lượng file mẫu quyết định TOÀN BỘ chất lượng giọng clone: OmniVoice sao chép cả
# tạp âm nền, tiếng ù điện và độ to bất thường của mẫu vào mọi cảnh của mọi video sau
# đó. Trước đây mẫu chỉ bị cắt cứng 15 giây rồi dùng thẳng.
#
#   highpass=80    — cắt ù điện 50/60Hz, tiếng gió chạm mic, rung bàn.
#   lowpass=8000   — cắt tiếng xì trên 8kHz; giọng người gần như không có gì ở dải này,
#                    còn model sinh ở 24kHz nên phần trên chỉ là nhiễu.
#   silenceremove  — gọt lặng ĐẦU; đảo băng rồi gọt tiếp = gọt lặng ĐUÔI. Khoảng lặng
#                    thừa làm model tưởng đó là nhịp nói của người này và bắt chước theo.
#   loudnorm       — chuẩn EBU R128 (-16 LUFS), để mẫu thu nhỏ tiếng và mẫu thu to
#                    tiếng cho ra cùng một mức, không còn giọng lúc to lúc bé giữa các
#                    giọng clone khác nhau.
# Thứ tự bắt buộc: lọc dải TRƯỚC gọt lặng (bỏ tiếng ù trước thì ngưỡng im lặng mới
# đúng), và loudnorm CUỐI CÙNG (nó đo cả bài, đo trên bản đã sạch mới ra đúng số).
VOICE_SAMPLE_FILTERS = (
    "highpass=f=80,"
    "lowpass=f=8000,"
    "silenceremove=start_periods=1:start_silence=0.1:start_threshold=-50dB,"
    "areverse,"
    "silenceremove=start_periods=1:start_silence=0.1:start_threshold=-50dB,"
    "areverse,"
    "loudnorm=I=-16:TP=-1.5:LRA=11"
)
# 10 giây, KHÔNG phải 15: README của OmniVoice ghi rõ "Use a 3–10 seconds reference
# audio clip. Longer audio slows down inference and may degrade cloning quality."
# Mẫu 15s vừa làm chậm mọi lần sinh giọng vừa hạ chất lượng bản clone.
VOICE_SAMPLE_MAX_SECONDS = 10.0
# Dưới ngưỡng này, OmniVoice không đủ dữ liệu để bắt được chất giọng: nó sẽ trôi về
# giọng mặc định và user tưởng phần mềm hỏng. Chặn ngay lúc upload, kèm số đo cụ thể,
# rẻ hơn nhiều so với để họ render xong một video 3 phút rồi mới nghe ra.
VOICE_SAMPLE_MIN_SPEECH = 3.0
_SILENCE_DUR_RE = re.compile(r"silence_duration:\s*([0-9.]+)")


def _measure_speech_seconds(wav_path: str) -> float:
    """
    Số giây CÓ TIẾNG NÓI trong file (tổng thời lượng trừ các quãng lặng bên trong).

    Chỉ đo độ dài file là chưa đủ: một mẫu 10 giây gồm 2 giây nói + 8 giây im vẫn qua
    cửa, rồi cho ra giọng clone tệ. Dùng silencedetect của FFmpeg để trừ đi phần im.
    """
    import imageio_ffmpeg

    total = tts_service._probe_audio_duration(wav_path) or 0.0
    if total <= 0:
        return 0.0
    try:
        proc = subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-nostats", "-i", wav_path,
             "-af", "silencedetect=noise=-45dB:d=0.35", "-f", "null", "-"],
            capture_output=True, text=True, errors="replace", timeout=120,
        )
        silent = sum(float(m) for m in _SILENCE_DUR_RE.findall(proc.stderr or ""))
    except Exception as e:
        logger.warning(f"[VoiceClone] Không đo được quãng lặng ({e}); dùng tổng thời lượng.")
        silent = 0.0
    return max(0.0, total - silent)


_SILENCE_START_RE = re.compile(r"silence_start:\s*([0-9.]+)")


def _diem_cat_theo_khoang_lang(wav_path: str) -> float | None:
    """
    Mốc cắt tốt nhất cho mẫu giọng: khoảng lặng CUỐI CÙNG nằm trong khoảng cho phép.

    VÌ SAO KHÔNG CẮT CỨNG THEO GIÂY: OmniVoice coi ref_text là phần mở đầu rồi đọc TIẾP
    sang văn bản đích. Cắt giữa câu thì transcript cũng dở dang ("...chuyển đến sống tại
    thành phố") và mô hình được mời nói nốt câu đó — đo được thật: bản đọc ra bắt đầu
    bằng "giúp đỡ các phòng phố," rồi mới vào nội dung thật. Cắt tại chỗ người nói ngừng
    lấy hơi thì mẫu kết thúc trọn vẹn, không còn gì để nói tiếp.

    Trả về None nếu không tìm được chỗ ngừng nào — khi đó phía gọi cắt cứng như cũ.
    """
    import imageio_ffmpeg
    try:
        proc = subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-nostats", "-i", wav_path,
             "-af", "silencedetect=noise=-40dB:d=0.18", "-f", "null", "-"],
            capture_output=True, text=True, errors="replace", timeout=120,
        )
    except Exception as e:
        logger.warning(f"[VoiceClone] Không dò được khoảng lặng ({e}); cắt cứng theo giây.")
        return None

    ung_vien = [
        float(m) for m in _SILENCE_START_RE.findall(proc.stderr or "")
        if VOICE_SAMPLE_MIN_SPEECH < float(m) <= VOICE_SAMPLE_MAX_SECONDS
    ]
    return max(ung_vien) if ung_vien else None


def _chuan_hoa_mau_giong(nguon: str, ref_wav: str, preview_mp3: str | None = None) -> str:
    """
    Chuẩn hoá một file bất kỳ thành mẫu giọng dùng được: lọc dải tần → gọt lặng hai đầu
    → chuẩn hoá độ to EBU R128 → cắt ở CUỐI MỘT CÂU dưới VOICE_SAMPLE_MAX_SECONDS,
    24kHz mono. Trả về transcript của đúng phần được giữ lại ("" nếu không chép được).

    Tách riêng khỏi /api/voice-clone vì đường SỬA giọng cũ phải chạy đúng y bộ lọc này —
    hai bản sao của cùng một chuỗi filter thì chỉ cần vá một bên là hai giọng nghe khác
    nhau mà không ai hiểu vì sao. Xem VOICE_SAMPLE_FILTERS để biết vì sao từng bước tồn tại.
    """
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    # Bước 1: lọc + chuẩn hoá, CHƯA cắt — cần bản đã sạch mới chép lời cho đúng.
    tmp = ref_wav + ".loc.wav"
    subprocess.run(
        [ffmpeg_exe, "-y", "-i", nguon, "-af", VOICE_SAMPLE_FILTERS,
         "-ar", "24000", "-ac", "1", tmp],
        check=True, capture_output=True, timeout=180,
    )
    ref_text = ""
    try:
        # Bước 2: cắt ở CUỐI MỘT CÂU, không cắt giữa chừng. Ưu tiên mốc câu của whisper;
        # dò khoảng lặng theo năng lượng chỉ là lưới hứng (người nói liên tục thì cả 10
        # giây không có quãng nào đủ im để nhận ra).
        cau = tts_service.chep_loi_theo_cau(tmp)
        cat, ref_text = tts_service.chon_diem_cat_mau(
            cau, VOICE_SAMPLE_MAX_SECONDS, VOICE_SAMPLE_MIN_SPEECH
        )
        if cat is None:
            cat = _diem_cat_theo_khoang_lang(tmp) or VOICE_SAMPLE_MAX_SECONDS
        subprocess.run(
            [ffmpeg_exe, "-y", "-i", tmp, "-t", f"{cat:.3f}",
             "-ar", "24000", "-ac", "1", ref_wav],
            check=True, capture_output=True, timeout=120,
        )
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass

    if preview_mp3:
        subprocess.run(
            [ffmpeg_exe, "-y", "-i", ref_wav, "-b:a", "128k", preview_mp3],
            check=True, capture_output=True, timeout=120,
        )
    return ref_text


@app.post("/api/voice-clone/{voice_id}/repair")
async def repair_voice_clone(voice_id: str):
    """
    Sửa một giọng clone đã tạo từ TRƯỚC khi có bộ lọc mẫu và bước đối chiếu transcript.

    Giọng cũ mang ba khuyết tật mà người dùng không nhìn thấy được:
      • file mẫu chưa qua lọc dải tần / gọt lặng / chuẩn hoá độ to — OmniVoice sao chép
        cả tiếng ù và khoảng lặng thừa vào mọi cảnh của mọi video;
      • file mẫu dài quá 10 giây (README OmniVoice: 3–10s, dài hơn thì CHẬM và GIẢM chất
        lượng bản clone);
      • transcript còn chữ số thô ("1943") trong khi file đọc thành chữ — cặp chữ↔tiếng
        lệch ngay tại con số, đúng kiểu lỗi làm giọng đọc chệch đi.

    Chạy lại đúng đường xử lý của bản mới, rồi chép lời lại từ chính file đã xử lý.
    File mẫu cũ được giữ lại (.bak) cho tới khi bản mới qua được cửa kiểm tra.
    """
    safe_id = os.path.basename(voice_id)
    if not safe_id.startswith("omnivoice_custom_"):
        raise HTTPException(status_code=400, detail="Chỉ sửa được giọng clone cá nhân.")
    cv = tts_service.get_custom_voice(safe_id)
    if cv is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy giọng clone này.")

    ref_wav = os.path.join(VOICES_PREVIEW_DIR, f"{safe_id}_ref.wav")
    if not os.path.isfile(ref_wav):
        raise HTTPException(status_code=400, detail="Không tìm thấy file mẫu giọng để sửa.")

    truoc = {
        "seconds": round(tts_service._probe_audio_duration(ref_wav) or 0, 1),
        "ref_text": cv.get("ref_text", ""),
    }
    # Bản lưu để lùi lại: đây là DỮ LIỆU DUY NHẤT của giọng này, hỏng là mất luôn giọng.
    backup = ref_wav + ".bak"
    await asyncio.to_thread(shutil.copy2, ref_wav, backup)
    preview_mp3 = os.path.join(VOICES_PREVIEW_DIR, f"{safe_id}.mp3")

    try:
        # Transcript về thẳng từ đây và ứng với ĐÚNG phần audio được giữ lại — chép lời
        # lần hai trên file đã cắt là mở đường cho hai bên lệch nhau lần nữa.
        heard = await asyncio.to_thread(_chuan_hoa_mau_giong, backup, ref_wav, preview_mp3)
        giay_noi = await asyncio.to_thread(_measure_speech_seconds, ref_wav)
        if giay_noi < VOICE_SAMPLE_MIN_SPEECH:
            raise RuntimeError(
                f"sau khi xử lý chỉ còn {giay_noi:.1f} giây tiếng nói "
                f"(cần tối thiểu {VOICE_SAMPLE_MIN_SPEECH:.0f})"
            )
        if not heard:
            heard = await asyncio.to_thread(tts_service.transcribe_vietnamese, ref_wav)
        if not heard:
            raise RuntimeError("không chép được lời từ file mẫu (whisper lỗi)")
    except Exception as e:
        # trả lại nguyên trạng, không để user mất giọng
        await asyncio.to_thread(shutil.move, backup, ref_wav)
        logger.error(f"[VoiceClone] Sửa giọng {safe_id} thất bại: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Không sửa được giọng clone: {e}")

    await asyncio.to_thread(os.remove, backup)

    # Số phải là CHỮ trong transcript: file đọc "một nghìn chín trăm bốn mươi ba", để
    # nguyên "1943" thì cặp chữ↔tiếng lệch đúng tại đó.
    heard = tts_service.normalize_vi_numbers(heard)
    entry = tts_service.update_custom_voice(
        safe_id, ref_text=heard, ref_text_match=1.0, ref_text_source="asr",
        gender=cv.get("gender"),
    )
    purged = tts_service.purge_voice_cache(safe_id)
    tts_service.invalidate_voice_prompt(safe_id)

    sau = {"seconds": round(tts_service._probe_audio_duration(ref_wav) or 0, 1),
           "speech_seconds": round(giay_noi, 1), "ref_text": heard}
    logger.info(f"[VoiceClone] Đã sửa {safe_id}: {truoc['seconds']}s → {sau['seconds']}s.")
    return {
        "message": (
            f"Đã sửa giọng clone: mẫu {truoc['seconds']}s → {sau['seconds']}s (đã lọc nhiễu, "
            f"chuẩn hoá độ to), chép lại lời mẫu, xoá {purged} file audio cũ trong bộ nhớ đệm."
        ),
        "before": truoc, "after": sau, "voice": entry, "purged_cache_files": purged,
    }


@app.post("/api/voice-clone")
async def create_voice_clone(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    transcript: Optional[str] = Form(None),
    gender: Optional[str] = Form(None),
    force_transcript: bool = Form(False),
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
        _chuan_hoa_mau_giong(raw_path, ref_wav_path, preview_mp3_path)

    def _cleanup_partial():
        for p in (raw_path, ref_wav_path, preview_mp3_path):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

    try:
        await asyncio.to_thread(_convert)
    except Exception as e:
        _cleanup_partial()
        detail = e.stderr.decode("utf-8", "replace")[-400:] if isinstance(e, subprocess.CalledProcessError) and e.stderr else str(e)
        raise HTTPException(status_code=400, detail=f"Không thể xử lý file âm thanh: {detail}")
    finally:
        if os.path.exists(raw_path):
            try:
                os.remove(raw_path)
            except OSError:
                pass

    speech_seconds = await asyncio.to_thread(_measure_speech_seconds, ref_wav_path)
    if speech_seconds < VOICE_SAMPLE_MIN_SPEECH:
        _cleanup_partial()
        raise HTTPException(
            status_code=400,
            detail=(
                f"Mẫu giọng chỉ có {speech_seconds:.1f} giây tiếng nói thật (sau khi cắt bỏ "
                f"khoảng lặng), cần tối thiểu {VOICE_SAMPLE_MIN_SPEECH:.0f} giây. "
                "Hãy thu lại một đoạn nói liên tục 5-10 giây, không ngắt quãng."
            ),
        )

    # ── Transcript PHẢI khớp file ghi âm ────────────────────────────────────
    # OmniVoice nhận (ref_audio, ref_text) như một CẶP: nó coi ref_text là lời của
    # ref_audio rồi đọc tiếp sang văn bản đích. Lệch cặp = mất mốc căn chữ↔tiếng = giọng
    # đọc ra thứ nghe rất giống tiếng Việt nhưng vô nghĩa.
    #
    # ĐÃ XẢY RA THẬT và không ai phát hiện ra suốt nhiều video: một giọng clone có
    # transcript ghi "Chào các bạn, tôi là ... giúp tự động hóa hoàn toàn quy trình..."
    # trong khi file mẫu đọc "Hãy yêu thương bản thân như cách đất trời nâng niu...".
    # Đo lại bằng cách cho model đọc thử: transcript sai → hoàn toàn vô nghĩa; thay đúng
    # transcript → đọc chuẩn. Vì thế cửa này chặn ngay từ lúc upload.
    heard = await asyncio.to_thread(tts_service.transcribe_vietnamese, ref_wav_path)
    user_text = (transcript or "").strip()
    match_score = 1.0
    ref_source = "asr"

    if user_text and heard:
        match_score = tts_service.transcript_similarity(user_text, heard)
        if match_score < tts_service.MIN_REF_TEXT_MATCH and not force_transcript:
            _cleanup_partial()
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Văn bản đọc mẫu bạn nhập KHÔNG khớp nội dung file ghi âm "
                    f"(độ khớp {match_score:.0%}).\n\n"
                    f"File ghi âm thực sự đọc:\n\"{heard}\"\n\n"
                    "Dùng sai cặp này thì giọng AI sẽ đọc ra tiếng Việt vô nghĩa. "
                    "Hãy sửa lại văn bản cho khớp, hoặc để trống để hệ thống tự chép lời."
                ),
            )
        ref_text, ref_source = user_text, "user"
    elif user_text:
        ref_text, ref_source = user_text, "user"      # không chép lời được → tin user
    else:
        ref_text = heard

    if not ref_text:
        ref_text = "Chào bạn, đây là giọng đọc tham khảo để đồng bộ video."
        match_score = 0.0

    display_name = (name or "").strip() or f"Giọng của tôi {voice_id[-4:]}"
    entry = tts_service.register_custom_voice(voice_id, display_name, ref_text, gender=gender)
    # Ghi lại điểm đối chiếu để lần dùng sau không phải chép lời lại (xem
    # ensure_clone_ref_text) — và để biết transcript này đã được kiểm chứng hay chưa.
    entry = tts_service.update_custom_voice(
        voice_id, ref_text_match=match_score, ref_text_source=ref_source
    ) or entry
    return {
        "voice_id": voice_id,
        "name": display_name,
        "ref_text": ref_text,
        "gender": entry.get("gender"),
        "speech_seconds": round(speech_seconds, 1),
        "transcript_match": round(match_score, 2),
        "transcript_source": ref_source,
        "heard": heard,
        "message": "Đã tạo giọng clone thành công. Chọn giọng này trong danh sách Giọng đọc.",
        "voice": entry,
    }


class VoiceCloneUpdateRequest(BaseModel):
    name: Optional[str] = None
    transcript: Optional[str] = None
    gender: Optional[str] = None
    # Chép lại lời từ chính file mẫu, bỏ qua transcript đang lưu. Đây là nút "chữa" cho
    # các giọng đã lỡ lưu transcript của một đoạn ghi âm khác.
    retranscribe: bool = False
    # Bỏ qua cửa đối chiếu (user khẳng định transcript của mình mới đúng).
    force_transcript: bool = False


@app.put("/api/voice-clone/{voice_id}")
async def update_voice_clone(voice_id: str, req: VoiceCloneUpdateRequest):
    """
    Sửa tên hiển thị / văn bản đọc mẫu (transcript) / giới tính của một giọng clone.

    Transcript là `ref_text` mà OmniVoice dùng để căn chỉnh giọng theo file mẫu — sai
    transcript thì phát âm và ngữ điệu lệch hẳn, nên đây là thứ user cần sửa được nhất
    (whisper tự nhận dạng rất hay sai dấu tiếng Việt).

    Sửa xong PHẢI xoá cache: mọi file audio đã sinh trước đó thuộc về bản ghi cũ, giữ
    lại thì lần render sau vẫn đọc bằng giọng cũ và user tưởng sửa không ăn thua.
    """
    safe_id = os.path.basename(voice_id)
    if not safe_id.startswith("omnivoice_custom_"):
        raise HTTPException(status_code=400, detail="Chỉ sửa được giọng clone cá nhân.")
    if req.name is not None and not req.name.strip() and req.transcript is None and req.gender is None:
        raise HTTPException(status_code=400, detail="Tên hiển thị không được để trống.")
    if tts_service.get_custom_voice(safe_id) is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy giọng clone này.")

    ref_wav = os.path.join(VOICES_PREVIEW_DIR, f"{safe_id}_ref.wav")
    new_transcript, match_score, ref_source = req.transcript, None, None
    heard = ""

    if req.retranscribe or (req.transcript and not req.force_transcript):
        if not os.path.isfile(ref_wav):
            raise HTTPException(status_code=400, detail="Không tìm thấy file mẫu giọng để đối chiếu.")
        heard = await asyncio.to_thread(tts_service.transcribe_vietnamese, ref_wav)

    if req.retranscribe:
        if not heard:
            raise HTTPException(status_code=502, detail="Không chép được lời từ file mẫu (whisper lỗi).")
        new_transcript, match_score, ref_source = heard, 1.0, "asr"
    elif req.transcript and heard:
        # Cùng cửa chặn như lúc upload — sửa transcript thành sai cặp cũng hỏng y hệt.
        match_score = tts_service.transcript_similarity(req.transcript, heard)
        if match_score < tts_service.MIN_REF_TEXT_MATCH and not req.force_transcript:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Văn bản đọc mẫu không khớp file ghi âm (độ khớp {match_score:.0%}).\n\n"
                    f"File ghi âm thực sự đọc:\n\"{heard}\"\n\n"
                    "Sai cặp này sẽ làm giọng AI đọc ra tiếng Việt vô nghĩa."
                ),
            )
        ref_source = "user"

    entry = tts_service.update_custom_voice(
        safe_id, name=req.name, ref_text=new_transcript, gender=req.gender,
        ref_text_match=match_score, ref_text_source=ref_source,
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy giọng clone này.")

    purged = tts_service.purge_voice_cache(safe_id)
    return {
        "message": f"Đã cập nhật giọng clone. Đã xoá {purged} file audio cũ trong bộ nhớ đệm.",
        "voice": entry,
        "purged_cache_files": purged,
        "heard": heard,
    }


@app.delete("/api/voice-clone/{voice_id}")
async def delete_voice_clone(voice_id: str):
    """Xóa giọng clone cá nhân (registry + file mẫu + audio đã cache)."""
    safe_id = os.path.basename(voice_id)
    if not safe_id.startswith("omnivoice_custom_"):
        raise HTTPException(status_code=400, detail="Chỉ xóa được giọng clone cá nhân.")
    # remove_custom_voice tự gọi purge_voice_cache — xem tts_service.
    if not tts_service.remove_custom_voice(safe_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy giọng clone này.")
    return {"message": "Đã xóa giọng clone và toàn bộ audio đã lưu đệm của giọng này."}


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


MAX_SFX_BYTES = 10 * 1024 * 1024
SFX_ALLOWED_EXTS = {".wav", ".mp3"}


@app.get("/api/sfx-list")
async def get_sfx_list():
    """Danh sách SFX do người dùng tự nạp."""
    custom_sfx = []
    try:
        names = os.listdir(CUSTOM_SFX_DIR)
    except OSError:
        names = []
    for f in sorted(names):
        if os.path.splitext(f)[1].lower() in SFX_ALLOWED_EXTS and f.startswith("custom_"):
            # định dạng: custom_<hex>_<tên gốc>.<đuôi>
            parts = f.split("_", 2)
            label = parts[2] if len(parts) > 2 else f
            custom_sfx.append({"value": f, "label": f"📁 {label}"})
    return {"sfx_list": custom_sfx}


@app.post("/api/upload-sfx")
async def upload_sfx(file: UploadFile = File(...)):
    """
    Nhận một file tiếng động do người dùng tự chuẩn bị.

    GHI VÀO CUSTOM_SFX_DIR (dưới DATA_DIR), KHÔNG phải SFX_DIR.
    LỖI CŨ: ghi thẳng vào backend/assets/sfx/ — thư mục mà config.py ghi rõ là "tài
    nguyên ĐI KÈM MÃ NGUỒN, chỉ đọc", và .gitignore có ngoại lệ `!backend/assets/sfx/*.wav`
    nên MỌI file người dùng tải lên đều hiện trong `git status` và lọt vào commit. Nó cũng
    phá vỡ điều kiện di dời kho dữ liệu sang ổ khác: file người dùng nằm lại ổ C.
    """
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in SFX_ALLOWED_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Định dạng {ext or '(không rõ)'} không hỗ trợ. Chấp nhận: "
                   + ", ".join(sorted(SFX_ALLOWED_EXTS)),
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="File rỗng.")
    if len(file_bytes) > MAX_SFX_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File nặng {len(file_bytes) / 1024 / 1024:.0f}MB, vượt giới hạn "
                   f"{MAX_SFX_BYTES // 1024 // 1024}MB.",
        )

    safe_name = "".join(c for c in os.path.basename(file.filename or "") if c.isalnum() or c in "._-")
    if not safe_name:
        safe_name = f"sfx{ext}"
    new_filename = f"custom_{uuid.uuid4().hex[:6]}_{safe_name}"
    path = os.path.join(CUSTOM_SFX_DIR, new_filename)

    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(file_bytes)

    # Chỉ đổi tên khi ĐÃ CHẮC là audio thật. Một file .wav giả (đổi đuôi từ .txt) lọt qua
    # được tới đây sẽ chỉ nổ lúc FFmpeg trộn — tức GIỮA một job render dài, đúng chỗ đắt
    # nhất để phát hiện. Cùng tinh thần với chốt Pillow ở /api/.../upload-image.
    try:
        import soundfile as sf

        info = await asyncio.to_thread(sf.info, tmp)
        if info.frames <= 0:
            raise ValueError("file không chứa mẫu âm thanh nào")
    except Exception as e:
        os.remove(tmp)
        raise HTTPException(status_code=400, detail=f"File không phải audio hợp lệ: {e}")

    os.replace(tmp, path)
    return {"status": "ok", "filename": new_filename, "label": f"📁 {safe_name}"}


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
        voice_path = os.path.join(VOICES_PREVIEW_DIR, f"{safe_id}.mp3")
        if os.path.isfile(voice_path):
            return FileResponse(voice_path)
    elif type == "sfx":
        # Tìm ở CẢ HAI kho: tiếng động đi kèm mã nguồn (SFX_DIR) và tiếng động người dùng
        # tự nạp (CUSTOM_SFX_DIR, dưới DATA_DIR — xem /api/upload-sfx). Thiếu vế thứ hai
        # thì nút nghe thử của mọi SFX tự nạp trả 404.
        names = [safe_id] if safe_id.endswith(('.wav', '.mp3')) else [f"{safe_id}.wav", f"{safe_id}.mp3"]
        for base in (SFX_DIR, CUSTOM_SFX_DIR):
            for name in names:
                sfx_path = os.path.join(base, name)
                if os.path.isfile(sfx_path):
                    return FileResponse(sfx_path)
    elif type == "hook_sfx":
        from services.video_service import HOOK_REEL_SOUNDS, DEFAULT_HOOK_REEL
        filename = HOOK_REEL_SOUNDS.get(safe_id, HOOK_REEL_SOUNDS.get(DEFAULT_HOOK_REEL, "reel_spin.wav"))
        hook_sfx_path = os.path.join(SFX_DIR, filename)
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
    # load_project_state() ở trên đã lọc job_id, nhưng nó ghép vào PROJECTS_DIR còn đây
    # là IMAGES_DIR — một gốc thư mục khác, phải tự lọc lại chứ không thừa hưởng được.
    job_dir_images = os.path.join(IMAGES_DIR, project_service.safe_job_id(job_id))
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

    # Cùng bộ chốt chặn với /api/scene-asset. Trước đây endpoint này KHÔNG kiểm tra gì:
    # đọc trọn file vào RAM rồi ghi thẳng thành scene_N.png — một file 4GB làm sập
    # backend, còn một file không phải ảnh thì lọt tới tận FFmpeg mới nổ, giữa lúc render.
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in OVERRIDE_IMAGE_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Định dạng {ext or '(không rõ)'} không hỗ trợ. Chấp nhận: "
                   + ", ".join(sorted(OVERRIDE_IMAGE_EXTS)),
        )
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File rỗng.")
    if len(content) > MAX_SCENE_IMAGE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Ảnh nặng {len(content) / 1024 / 1024:.0f}MB, vượt giới hạn "
                   f"{MAX_SCENE_IMAGE_BYTES // 1024 // 1024}MB.",
        )

    job_dir_images = os.path.join(IMAGES_DIR, project_service.safe_job_id(job_id))
    os.makedirs(job_dir_images, exist_ok=True)
    img_path = os.path.join(job_dir_images, f"scene_{scene_idx+1}.png")

    # Giải mã rồi ghi lại thành PNG THẬT, không đổ nguyên byte người dùng gửi lên.
    # Hai việc cùng lúc: chặn file không phải ảnh (Pillow ném lỗi ngay tại đây), và bảo
    # đảm nội dung khớp với cái tên .png mà toàn bộ downstream đang trông đợi — pipeline
    # tìm đúng "scene_N.png" nên không thể giữ đuôi gốc của file tải lên.
    def _write_png():
        import io
        from PIL import Image

        with Image.open(io.BytesIO(content)) as img:
            img.load()
            # PNG không nhận CMYK (ảnh JPEG xuất từ phần mềm in ấn) — quy về RGB trước.
            if img.mode not in ("RGB", "RGBA", "L", "P"):
                img = img.convert("RGB")
            img.save(img_path, format="PNG")

    try:
        await asyncio.to_thread(_write_png)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"File không phải ảnh hợp lệ: {e}")

    project_service.update_scene_asset(job_id, scene_idx, image_path=img_path)
    return {"message": f"Đã cập nhật ảnh tùy chỉnh cho cảnh {scene_idx+1}.", "image_path": img_path}


# ---------------------------------------------------------------------------
# Cấu hình kho lưu trữ (đổi ổ đĩa)
# ---------------------------------------------------------------------------
class StorageConfigRequest(BaseModel):
    path: str


@app.get("/api/storage-config")
async def get_storage_config(with_sizes: bool = False):
    """Kho dữ liệu đang nằm ở đâu, còn trống bao nhiêu."""
    # with_sizes=True quét toàn bộ DATA_DIR (os.walk + getsize từng file) — có thể là ổ
    # ngoài/mạng nếu user đã trỏ CUSTOM_ASSETS_DIR sang đó. Chạy đồng bộ sẽ chặn event
    # loop cho MỌI request/broadcast tiến độ render khác đang chạy song song.
    return await asyncio.to_thread(config.get_storage_info, with_sizes=with_sizes)


@app.post("/api/storage-config")
async def set_storage_config(req: StorageConfigRequest):
    """
    Đổi thư mục lưu dữ liệu sinh ra (ảnh, video, cache) sang ổ đĩa khác.

    CHỈ ghi vào .env — KHÔNG đổi đường dẫn của tiến trình đang chạy. Các module đã nạp
    giữ đường dẫn cũ trong biến module-level, và một job render đang chạy dở sẽ có nửa
    số file ở ổ cũ, nửa ở ổ mới. Buộc phải khởi động lại backend.
    """
    raw = (req.path or "").strip().strip('"')

    # Chuỗi rỗng = quay về mặc định (backend/assets).
    if not raw:
        config.write_env_value(config.ENV_KEY, "")
        return {
            "status": "ok",
            "path": "",
            "warnings": [],
            "requires_restart": True,
            "message": "Đã đặt lại về thư mục mặc định (backend/assets). Hãy tắt và bật lại cửa sổ CMD Backend.",
        }

    ok, err, warnings = config.validate_storage_path(raw)
    if not ok:
        raise HTTPException(status_code=400, detail=err)

    resolved = os.path.abspath(raw)
    try:
        config.write_env_value(config.ENV_KEY, resolved)
    except (OSError, ValueError) as e:
        raise HTTPException(status_code=500, detail=f"Không ghi được file .env: {e}")

    return {
        "status": "ok",
        "path": resolved,
        "warnings": warnings,
        "requires_restart": True,
        "message": (
            f"Đã lưu đường dẫn mới: {resolved}. "
            "Hãy TẮT và BẬT LẠI cửa sổ CMD Backend để áp dụng. "
            "Nhạc nền và tiếng động vẫn nằm cùng mã nguồn nên không cần chép đi đâu; "
            "preset và danh sách dự án sẽ tự chuyển sang trong lần khởi động tới."
        ),
    }


# ---------------------------------------------------------------------------
# Quản lý Key API (Gemini, Pexels, Pixabay, FAL)
# ---------------------------------------------------------------------------
class ApiKeysConfigRequest(BaseModel):
    gemini_api_keys: Optional[List[str]] = None
    pexels_api_key: Optional[str] = None
    pixabay_api_key: Optional[str] = None
    fal_key: Optional[str] = None


def _mask_secret(value: str) -> str:
    """Che bớt key khi hiển thị mặc định — chỉ lộ 4 ký tự đầu/cuối.

    Key thật CHỈ được trả về qua /api/api-keys-config/reveal, gọi bằng hành động
    bấm "Hiện Key" rõ ràng của người dùng — không còn lộ nguyên văn mỗi lần trang
    Cấu hình mở lên (GET /api/api-keys-config chạy tự động lúc mount component).
    """
    value = (value or "").strip()
    if not value:
        return ""
    if len(value) <= 10:
        return "•" * len(value)
    return f"{value[:4]}{'•' * 6}{value[-4:]}"


def _read_api_keys_from_env() -> dict:
    """Đọc nguyên văn các key từ biến môi trường — dùng cho cả GET thường (sẽ bị
    che ở tầng gọi) lẫn /reveal (trả thẳng, không che)."""
    gemini_keys_list = []
    main_g = (os.getenv("GEMINI_API_KEY") or "").strip()
    if main_g:
        gemini_keys_list.append(main_g)
    idx = 1
    while True:
        k = (os.getenv(f"GEMINI_API_KEY_{idx}") or "").strip()
        if not k:
            break
        if k not in gemini_keys_list:
            gemini_keys_list.append(k)
        idx += 1

    pexels_key = (os.getenv("PEXELS_API_KEY") or "").strip()
    pixabay_key = (os.getenv("PIXABAY_API_KEY") or "").strip()
    fal_key = (os.getenv("FAL_KEY") or "").strip()

    return {
        "gemini_api_keys": gemini_keys_list,
        "pexels_api_key": pexels_key,
        "pixabay_api_key": pixabay_key,
        "fal_key": fal_key,
        "status": {
            "gemini": len(gemini_keys_list) > 0,
            "pexels": len(pexels_key) > 0,
            "pixabay": len(pixabay_key) > 0,
            "fal": len(fal_key) > 0,
        }
    }


@app.get("/api/api-keys-config")
async def get_api_keys_config():
    """Trạng thái kết nối + key đã CHE BỚT (an toàn để tự động gọi lúc mở trang)."""
    raw = _read_api_keys_from_env()
    return {
        "gemini_api_keys": [_mask_secret(k) for k in raw["gemini_api_keys"]],
        "pexels_api_key": _mask_secret(raw["pexels_api_key"]),
        "pixabay_api_key": _mask_secret(raw["pixabay_api_key"]),
        "fal_key": _mask_secret(raw["fal_key"]),
        "status": raw["status"],
    }


@app.get("/api/api-keys-config/reveal")
async def reveal_api_keys_config():
    """Key API nguyên văn — CHỈ gọi khi người dùng chủ động bấm "Hiện Key",
    không tự động chạy lúc mở trang (khác GET /api/api-keys-config)."""
    return _read_api_keys_from_env()


@app.post("/api/api-keys-config")
async def set_api_keys_config(req: ApiKeysConfigRequest):
    """Cập nhật các API Key trực tiếp vào file .env và làm tươi hệ thống."""
    try:
        # 1. Update Gemini Keys
        if req.gemini_api_keys is not None:
            clean_g_keys = [k.strip() for k in req.gemini_api_keys if k and k.strip()]
            main_k = clean_g_keys[0] if clean_g_keys else ""
            config.write_env_value("GEMINI_API_KEY", main_k)
            os.environ["GEMINI_API_KEY"] = main_k

            # Ghi key dự phòng, và DỌN các slot cũ giờ không còn dùng.
            # `write_env_value(key, "")` giờ XOÁ dòng khỏi .env thay vì ghi `KEY=` (xem
            # config.write_env_value) — nên vòng dọn này không còn để lại rác.
            # Quét quá số key hiện có 20 slot: đủ để xoá hết dấu vết của lần cấu hình
            # trước, kể cả khi người dùng vừa hạ từ 15 key xuống 2.
            for i in range(1, max(len(clean_g_keys), 1) + 20):
                env_var = f"GEMINI_API_KEY_{i}"
                val = clean_g_keys[i] if i < len(clean_g_keys) else ""
                config.write_env_value(env_var, val)
                if val:
                    os.environ[env_var] = val
                else:
                    os.environ.pop(env_var, None)

        # 2. Update Pexels Key
        if req.pexels_api_key is not None:
            pval = req.pexels_api_key.strip()
            config.write_env_value("PEXELS_API_KEY", pval)
            os.environ["PEXELS_API_KEY"] = pval

        # 3. Update Pixabay Key
        if req.pixabay_api_key is not None:
            pxval = req.pixabay_api_key.strip()
            config.write_env_value("PIXABAY_API_KEY", pxval)
            os.environ["PIXABAY_API_KEY"] = pxval

        # 4. Update FAL Key
        if req.fal_key is not None:
            fval = req.fal_key.strip()
            config.write_env_value("FAL_KEY", fval)
            os.environ["FAL_KEY"] = fval

        # Reload KeyManager instances
        from services.key_manager import gemini_keys, fal_keys
        gemini_keys.__init__("GEMINI_API_KEY")
        fal_keys.__init__("FAL_KEY")

        return {
            "status": "ok",
            "message": "Đã lưu cài đặt API Keys vào file .env thành công!"
        }
    except Exception as e:
        logger.error(f"Lỗi khi lưu API Keys: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Không thể lưu API Keys: {e}")


# ---------------------------------------------------------------------------
# Minh bạch hoá bộ nhớ đệm — đèn 🟢 đã có sẵn / 🔴 sẽ tạo mới
# ---------------------------------------------------------------------------
class CacheProbeRequest(BaseModel):
    scenes: List[dict]
    voice: Optional[str] = None
    speech_rate: Optional[str] = "+0%"
    speech_pitch: Optional[str] = "+0Hz"
    use_breathing: bool = False
    aspect_ratio: str = "9:16"
    art_style: Optional[str] = None
    negative_prompt: Optional[str] = ""
    mode: str = "storyteller"
    # Ba trường này quyết định cảnh lấy hình từ ĐÂU (ảnh AI / video stock / Veo), mà mỗi
    # nguồn lại có kho cache riêng. Thiếu chúng thì đèn báo tra nhầm kho và luôn nói 🔴.
    visual_source: str = "auto"
    prefer_stock_video: bool = False
    use_veo: bool = False


def _cache_probe_sync(req: CacheProbeRequest) -> dict:
    """Thân thực sự của /api/cache-probe — tách ra để chạy qua asyncio.to_thread.

    LỖI CŨ: hàm route async này chạy vòng lặp has_media() (disk I/O, os.stat) THẲNG
    trên event loop, không một `await` nào. Theo comment của cache_service._find_cached,
    endpoint này bị giao diện gọi MỖI LẦN người dùng gõ phím trong ô sửa kịch bản — với
    19 cảnh x 2 lượt tra/cảnh, mỗi phím bấm là hàng chục lượt os.stat chặn cứng event
    loop, treo luôn việc broadcast tiến độ của job render khác đang chạy song song.
    """
    from services.cache_service import cache as media_cache

    voice = req.voice or tts_service.DEFAULT_VOICE
    results = []

    for scene in req.scenes:
        tts_text = tts_service._strip_emoji(scene.get("text", "") or "").strip()
        tts_text = re.sub(r'  +', ' ', tts_text)

        audio_cached = False
        if req.mode != "photo_slideshow" and tts_text:
            final_rate = _compose_speech_rate(
                req.speech_rate or "+0%", scene.get("speech_rate_modifier", "0%")
            )
            audio_cached = media_cache.has_media(
                "tts",
                text=tts_text, voice=voice, rate=final_rate, pitch=req.speech_pitch or "+0Hz",
                emotion=scene.get("emotion", "") or "", breathing=bool(req.use_breathing),
            )

        img_prompt = scene.get("image_prompt", "") or ""
        override = _resolve_override_asset(scene.get("override_asset"))

        # Phải tra ĐÚNG kho cache của nguồn hình mà cảnh này sẽ dùng, bằng chính hàm
        # _pick_visual_source mà pipeline dùng — nếu không, người bật "ưu tiên video
        # thật" sẽ luôn thấy 🔴 dù clip đã nằm sẵn trong cache.
        if override:
            image_cached, image_source = True, "override"
        elif req.use_veo:
            image_source = "veo"
            image_cached = media_cache.has_media(
                "veo",
                prompt=img_prompt, aspect_ratio=req.aspect_ratio,
                negative_prompt=req.negative_prompt or "", model="fast",
            )
        elif _pick_visual_source(req, scene, len(results)) == "stock_video":
            image_source = "stock_video"
            image_cached = media_cache.has_media(
                "stock", **_stock_cache_params(img_prompt, req.aspect_ratio)
            )
        else:
            image_source = "ai_image"
            image_cached = media_cache.has_media(
                "imagen",
                prompt=img_prompt,
                aspect_ratio=req.aspect_ratio,
                art_style=req.art_style or "",
                negative_prompt=req.negative_prompt or "",
            )

        results.append({
            "audio_cached": audio_cached,
            "image_cached": image_cached,
            "image_source": image_source,
            "has_override": bool(override),
        })

    return {"scenes": results}


@app.post("/api/cache-probe")
async def cache_probe(req: CacheProbeRequest):
    """
    Từng cảnh đã có sẵn giọng đọc / hình trong cache chưa.

    QUAN TRỌNG — các tham số cache ở đây phải khớp CHÍNH XÁC với lúc render, nếu không
    đèn báo sẽ nói dối. Cụ thể:
      • giọng đọc: tts_service.synthesize_speech dùng (text, voice, rate, pitch,
        emotion, breathing), trong đó `rate` là kết quả CỘNG DỒN tốc độ user với
        speech_rate_modifier của từng cảnh — xem _compose_speech_rate.
      • hình ảnh: image_router.generate_image_with_fallback dùng (prompt, aspect_ratio,
        art_style, negative_prompt).
    Đổi công thức khoá cache ở hai chỗ đó thì phải sửa cả đây (_cache_probe_sync).
    """
    return await asyncio.to_thread(_cache_probe_sync, req)


# ---------------------------------------------------------------------------
# Ghi đè asset thủ công cho từng cảnh
# ---------------------------------------------------------------------------
@app.post("/api/scene-asset")
async def upload_scene_asset(file: UploadFile = File(...)):
    """
    Nhận 1 ảnh/video user tự chuẩn bị để thay cho hình AI của một cảnh.

    Trả về `asset_id` — client gắn vào `scene.override_asset` rồi render bình thường.
    KHÔNG gắn với job_id: mỗi lần "Chỉnh sửa & Render lại" là một job_id mới, nên khoá
    file theo job sẽ làm hình vừa tải lên biến mất ngay lần render kế tiếp.
    """
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in OVERRIDE_ALLOWED_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Định dạng {ext or '(không rõ)'} không hỗ trợ. Chấp nhận: "
                   + ", ".join(sorted(OVERRIDE_ALLOWED_EXTS)),
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File rỗng.")
    if len(content) > MAX_OVERRIDE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File nặng {len(content) / 1024 / 1024:.0f}MB, vượt giới hạn "
                   f"{MAX_OVERRIDE_BYTES // 1024 // 1024}MB.",
        )

    asset_id = f"{uuid.uuid4().hex}{ext}"
    dest = os.path.join(OVERRIDES_DIR, asset_id)
    # Ghi qua file tạm rồi đổi tên: pipeline có thể đang quét thư mục này, không để nó
    # nhặt phải file mới ghi được một nửa.
    tmp = dest + ".part"
    with open(tmp, "wb") as f:
        f.write(content)
    os.replace(tmp, dest)

    return {
        "asset_id": asset_id,
        "url": f"/api/scene-asset/{asset_id}",
        "kind": "video" if ext in OVERRIDE_VIDEO_EXTS else "image",
        "size_mb": round(len(content) / 1024 / 1024, 2),
        "message": "Đã tải lên. Cảnh này sẽ dùng hình của bạn thay cho ảnh AI.",
    }


@app.get("/api/scene-asset/{asset_id}")
async def get_scene_asset(asset_id: str):
    """Xem lại file ghi đè (thumbnail trong trình sửa kịch bản)."""
    from fastapi.responses import FileResponse

    path = _resolve_override_asset(asset_id)
    if not path:
        raise HTTPException(status_code=404, detail="Không tìm thấy file ghi đè này.")
    return FileResponse(path)


@app.delete("/api/scene-asset/{asset_id}")
async def delete_scene_asset(asset_id: str):
    """Gỡ ghi đè, trả cảnh về cho AI sinh hình."""
    path = _resolve_override_asset(asset_id)
    if path:
        try:
            os.remove(path)
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"Không xoá được: {e}")
    return {"status": "ok", "message": "Đã gỡ hình ghi đè."}


# ---------------------------------------------------------------------------
# Quản lý bộ nhớ đệm
# ---------------------------------------------------------------------------
@app.get("/api/cache-stats")
async def cache_stats():
    """Bộ nhớ đệm đang chiếm bao nhiêu (ảnh/giọng đọc + kịch bản Gemini)."""
    from services.cache_service import cache as media_cache
    # get_cache_stats() liệt kê thư mục cache (có thể hàng nghìn file ở mức
    # MAX_CACHE_SIZE_GB) — cùng lý do to_thread như DELETE /api/cache ngay dưới.
    return await asyncio.to_thread(media_cache.get_cache_stats)


@app.delete("/api/cache")
async def clear_cache(include_script_cache: bool = False):
    """
    Xoá bộ nhớ đệm để giải phóng ổ đĩa.

    Mặc định chỉ xoá media (ảnh + giọng đọc) — phần chiếm dung lượng. Kịch bản Gemini
    chỉ vài KB nhưng sinh lại thì TỐN QUOTA API, nên phải truyền
    `?include_script_cache=true` mới đụng tới.
    """
    from services.cache_service import cache as media_cache
    result = await asyncio.to_thread(media_cache.clear, include_script_cache)
    return {
        "status": "ok",
        **result,
        "message": (
            f"Đã xoá {result['removed_files']} file, giải phóng {result['freed_mb']}MB. "
            "Các cảnh sẽ hiện 🔴 và được AI tạo lại ở lần render tới."
        ),
    }


# ---------------------------------------------------------------------------
# Nghe thử giọng đọc của MỘT cảnh
# ---------------------------------------------------------------------------
# Lợi ích kép: bản nghe thử đi qua ĐÚNG synthesize_speech với ĐÚNG bộ tham số mà
# pipeline sẽ dùng, nên nó nạp luôn vào TTS cache. Nghe thử xong, cảnh đó chuyển 🟢 và
# lúc render không phải sinh lại — nghe thử càng nhiều, render càng nhanh.
MAX_PREVIEW_CHARS = 800


class ScenePreviewRequest(BaseModel):
    text: str
    voice: Optional[str] = None
    speech_rate: Optional[str] = "+0%"
    speech_pitch: Optional[str] = "+0Hz"
    speech_rate_modifier: Optional[str] = "0%"
    emotion: Optional[str] = ""
    use_breathing: bool = False
    mode: str = "storyteller"


@app.post("/api/preview-scene-voice")
async def preview_scene_voice(req: ScenePreviewRequest):
    """Đọc thử lời thoại của một cảnh, kể cả nhịp nghỉ <break time="..."/>."""
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask

    tts_text = tts_service._strip_emoji(req.text or "").strip()
    tts_text = re.sub(r'  +', ' ', tts_text)
    if not tts_service.strip_break_tags(tts_text):
        raise HTTPException(status_code=400, detail="Cảnh này chưa có lời thoại để đọc thử.")
    if len(tts_text) > MAX_PREVIEW_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Lời thoại dài {len(tts_text)} ký tự, vượt giới hạn nghe thử "
                   f"{MAX_PREVIEW_CHARS}. Hãy tách bớt thành cảnh mới.",
        )

    out_path = os.path.join(TEMP_DIR, f"preview_{uuid.uuid4().hex}.mp3")
    # Nghe thử KHÔNG có WebSocket của job để đẩy cảnh báo, mà đây lại đúng lúc user cần
    # biết nhất: bấm nghe thử giọng clone mà nghe ra giọng Hoài My thì phải nói rõ là
    # OmniVoice đang hỏng, chứ không để họ tưởng bản clone nghe giống hệt giọng mặc định.
    warnings: list[str] = []

    async def _collect_warning(msg: str):
        warnings.append(msg)

    try:
        await tts_service.synthesize_speech(
            tts_text, out_path,
            voice=req.voice or tts_service.DEFAULT_VOICE,
            rate=_compose_speech_rate(req.speech_rate or "+0%", req.speech_rate_modifier or "0%"),
            pitch=req.speech_pitch or "+0Hz",
            mode=req.mode,
            emotion=req.emotion or "",
            use_breathing=req.use_breathing,
            warning_callback=_collect_warning,
        )
    except Exception as e:
        logger.error(f"[Preview] Sinh giọng thất bại: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Không sinh được giọng đọc: {e}")

    # Giọng ảo/OmniVoice có thể ghi ra .wav dù ta xin .mp3 — lấy đúng file đã ghi.
    written = tts_service._resolve_written_path(out_path)
    if not written:
        raise HTTPException(status_code=500, detail="Không sinh được giọng đọc (file rỗng).")

    # Header phải là latin-1: thông báo tiếng Việt đi qua nguyên văn sẽ làm Starlette
    # ném UnicodeEncodeError ngay lúc gửi. Percent-encode ở đây, decodeURIComponent ở UI.
    headers = {}
    if warnings:
        headers["X-TTS-Warning"] = quote(" ".join(warnings))

    # Xoá SAU khi đã gửi xong: bản thật đã nằm trong TTS cache, file này chỉ là bản sao
    # dùng một lần. Giữ lại sẽ làm TEMP_DIR phình lên theo mỗi lần bấm nghe thử.
    return FileResponse(
        written,
        media_type="audio/wav" if written.endswith(".wav") else "audio/mpeg",
        headers=headers,
        background=BackgroundTask(lambda: os.path.isfile(written) and os.remove(written)),
    )

