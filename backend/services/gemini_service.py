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
import hashlib
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
MAX_RETRIES = 5
BASE_DELAY = 2.0  # giây

import re

def _retry_sync(func_factory, retries=MAX_RETRIES, base_delay=BASE_DELAY, key_manager=None):
    """
    Wrapper: gọi hàm đồng bộ với retry + exponential backoff.
    Nếu có lỗi 429/RESOURCE_EXHAUSTED, tự động xoay vòng key hoặc chờ theo retryDelay.
    """
    last_error = None
    rotations = 0
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
                if "503" in error_str or "UNAVAILABLE" in error_str:
                    raise RuntimeError("Máy chủ AI của Google hiện đang quá tải do nghẽn mạng toàn cầu (Lỗi 503). Hệ thống đã thử lại nhiều lần nhưng không thành công. Xin vui lòng chờ vài phút rồi thử lại!")
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    raise RuntimeError("API Key của bạn đã cạn kiệt dung lượng (Lỗi 429). Hệ thống đã cố xoay vòng key nhưng không thành công. Vui lòng thêm Key mới hoặc chờ Google reset!")
                raise
                
            delay = base_delay * (2 ** attempt)
            # A25 fix: Thêm jitter ±25% để tránh thundering herd khi API hồi phục.
            import random
            delay *= (0.75 + random.random() * 0.5)  # ±25% random spread
            
            # Xử lý riêng cho Quota/Rate Limit (429)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                num_keys = len(key_manager.keys) if key_manager else 1
                
                # Nếu còn key dự phòng thì thử xoay vòng trước
                if key_manager and rotations < num_keys - 1:
                    key_manager.rotate()
                    rotations += 1
                    logger.warning("Quota Exceeded. Đã tự động xoay vòng API Key.")
                    delay = 0.5
                else:
                    # Nếu đã hết key dự phòng hoặc dùng key fix cứng, thì chờ
                    match = re.search(r"Please retry in (\d+\.?\d*)s", error_str)
                    if match:
                        delay = float(match.group(1)) + 1.0 # Cộng thêm 1s bù hao
                    elif "retryDelay" in error_str:
                        delay = 20.0 # Mặc định chờ 20s
                    else:
                        delay = max(delay, 10.0)
            
            logger.warning(f"API lỗi (attempt {attempt+1}/{retries+1}). Retry sau {delay}s... Lỗi: {error_str[:100]}...")
            time.sleep(delay)
    if last_error:
        raise last_error
    raise RuntimeError("_retry_sync: hết lượt thử nhưng không ghi nhận lỗi nào.")


def _track_quota() -> None:
    """Ghi nhận 1 lượt gọi Gemini vào bộ đếm quota trong ngày (xem quota_service).
    Lỗi ở đây KHÔNG được làm hỏng luồng chính — quota.json hỏng thì chịu đếm sai,
    chứ không được chặn cả tính năng sinh kịch bản/ảnh."""
    try:
        from services import quota_service
        quota_service.increment_quota(1)
    except Exception:
        logger.warning("[Quota] Không ghi nhận được quota call. Kiểm tra quota_service.")


def _require_parsed(response, where: str):
    """response.parsed là None khi Gemini trả JSON không khớp schema (structured output
    thất bại) — dereference thẳng ném AttributeError khó hiểu ở tận nơi dùng, thay vì lỗi
    rõ ràng ngay tại đây. Chuỗi lỗi generic "NoneType..." cũng không khớp is_retryable
    trong _retry_sync nên sẽ không được thử lại — coi như một lỗi khác hẳn 429/503."""
    if response.parsed is None:
        raise RuntimeError(
            f"Gemini không trả về dữ liệu hợp lệ ({where}) — có thể do lỗi schema hoặc nội dung bị chặn."
        )
    return response.parsed


# ---------------------------------------------------------------------------
# 1. Định nghĩa Schema bằng Pydantic — đây chính là "Structured Output".
#    Gemini sẽ bị BẮT phải trả JSON khớp 100% với schema này.
# ---------------------------------------------------------------------------
class LLMScene(BaseModel):
    scene: int
    text: str = Field(description="Lời thoại đọc voice-over. Không chứa ngoặc đơn hoặc ký hiệu. Nếu scene_type là quote_card, trường này PHẢI rỗng.")
    image_prompt: str = Field(description="Prompt bằng tiếng Anh chi tiết để AI sinh ảnh (dùng các từ khóa điện ảnh như 8k, photorealistic). Bắt buộc phải có.")
    # Gốc rễ của 2 lỗi đo được trên video thật (a67a0fa9, 30 cảnh): Gemini gán từ khoá theo
    # Ý CHÍNH của cả đoạn nên các cảnh cùng một ý nhận CÙNG một cụm — 12/24 cặp liền kề
    # trùng y nguyên ("ĐỪNG CHỈ TRÍCH" nhấp 4 lần trong 20 giây). Và chỉ 7/24 cụm thực sự
    # có mặt trong lời của chính cảnh đó, nên chữ hiện ra chẳng ăn nhập gì với lời đang đọc.
    # motion_effects.plan_scene_highlights() đã dập cả hai ở tầng render, nhưng chặn ngay từ
    # đây thì tầng đó không phải vứt bớt công của model nữa.
    highlight_text: str = Field(
        description=(
            "Từ khóa quan trọng nhất trong cảnh (tối đa 1-3 từ, viết HOA). "
            "BẮT BUỘC là cụm từ XUẤT HIỆN NGUYÊN VĂN trong `text` của CHÍNH cảnh này — "
            "chữ sẽ hiện lên đúng lúc câu đó được đọc, nên cụm không có trong lời sẽ lạc đề. "
            "KHÔNG lặp lại từ khoá của cảnh liền trước; cảnh nào không có cụm nào thật sự "
            "đắt thì để RỖNG."
        )
    )
    scene_type: str = Field(default="narration", description="Loại cảnh: 'narration' (kể chuyện có giọng đọc) hoặc 'quote_card' (hiển thị trích dẫn chữ to trên nền tối, không giọng đọc).")
    source_quote: Optional[str] = Field(default=None, description="Nguyên văn trích dẫn từ tài liệu gốc, dùng để đối chiếu chống bịa nội dung.")
    source_ref: Optional[str] = Field(default=None, description="Vị trí chứa đoạn trích trong tài liệu (VD: Chương 1, trang 27).")
    subtitle_text: Optional[str] = Field(default=None, description="Chữ hiển thị trên màn hình nếu khác với text đọc voice (đặc biệt hữu ích cho quote_card).")
    bgm_volume: Optional[float] = Field(default=None, description="Âm lượng nhạc nền tại cảnh này (VD: 0.0 tắt nhạc, 1.0 bình thường, 1.5 bùng nổ). Để None nếu không cần đổi.")

class Scene(LLMScene):
    sfx: str = ""
    visual_effect: str = "none"
    emotion: str = "calm"
    speech_rate_modifier: str = "0%"
    transition: str = "crossfade"
    visual_source: str = "auto"
    pause_after_ms: int = 0
    bgm_volume: Optional[float] = None

class LLMScriptResponse(BaseModel):
    sentiment: str = Field(default="happy", description="Cảm xúc tổng thể của video (happy, sad, dramatic, suspense, chill, energetic).")
    recommended_bgm: str = Field(default="moment_of_peace", description="Mã bài nhạc nền phù hợp nhất với cảm xúc kịch bản.")
    # TUYỆT ĐỐI KHÔNG lặp lại tên sách: chữ này được vẽ ĐÈ LÊN chính ảnh bìa, mà bìa đã
    # in tên sách cỡ lớn sẵn rồi. Đo trên video thật (a67a0fa9): hook "ĐẮC NHÂN TÂM: BÍ
    # QUYẾT ĐƯỢC LÒNG NGƯỜI" nằm chồng lên bìa "ĐẮC NHÂN TÂM" khổng lồ — người xem đọc
    # cùng ba chữ hai lần, một mờ một nét, chồng nhau. Giây đầu tiên quý giá bị tiêu vào
    # thông tin người xem đã có.
    hook_text: str = Field(
        default="",
        description=(
            "Tiêu đề giật gân, cực ngắn (dưới 10 chữ) hiển thị to ở đầu video, HOẶC câu "
            "trích dẫn dùng cho hiệu ứng Gõ chữ (typewriter_quote) và Màn đen (blackout_question). "
            "TUYỆT ĐỐI KHÔNG lặp lại tên sách/tên tác giả/chủ đề — chữ này hiện ĐÈ LÊN "
            "ảnh bìa vốn đã in sẵn những thứ đó, lặp lại là phí giây đầu tiên. "
            "Hãy nêu MÂU THUẪN hoặc LỜI HỨA khiến người xem phải ở lại (câu hỏi nhức "
            "nhối, con số bất ngờ, điều ngược với trực giác)."
        ),
    )
    hook_variants: List[str] = Field(default_factory=list, description="3 biến thể hook_text khác nhau để người dùng lựa chọn (A/B testing). Cùng ràng buộc như hook_text: không nhắc lại tên sách.")
    # KHÁC hook_text: hook_text là TIÊU ĐỀ giật gân vẽ đè lên ảnh bìa (hiệu ứng word_by_word,
    # full_shake, blackout_question, typewriter_quote); hook_quote là CÂU TRÍCH dùng cho 
    # carousel_quote — bìa thu nhỏ vào giữa rồi câu này hiện ra 2.5 giây.
    # LỖI CŨ: RenderVideoRequest có field `hook_quote`, video_service có
    # build_carousel_hook(cover, hook_quote, ...), tài liệu skill coi nó là BẮT BUỘC cho niche
    # sách — nhưng schema Gemini không có trường này, nên nó chưa bao giờ được sinh tự động.
    # Ai muốn dùng hiệu ứng bìa-sách-kèm-quote đều phải tự gõ tay câu quote.
    hook_quote: str = Field(
        default="",
        description=(
            "Câu trích ĐẮT NHẤT của nội dung, dùng cho hiệu ứng mở màn dạng carousel_quote "
            "(hiện bìa sách rồi nảy ra quote). Viết HOA, dưới 15 từ, tốt nhất là 2 vế đối "
            "lập hoặc một sự thật lật ngược — VD 'NGƯỜI NGHÈO LÀM VIỆC VÌ TIỀN. NGƯỜI GIÀU "
            "BẮT TIỀN LÀM VIỆC CHO MÌNH.'. Phải là mệnh đề CỤ THỂ, đứng một mình vẫn đáng "
            "trích; KHÔNG chung chung ('sách rất hay', 'bài học sâu sắc') và KHÔNG chỉ là "
            "tên chủ đề. Để RỖNG nếu nội dung không có câu nào thật sự đắt."
        ),
    )
    cta_text: str = Field(default="", description="Câu Call To Action (Kêu gọi hành động) ở cuối video.")
    scenes: List[LLMScene]

class ScriptResponse(LLMScriptResponse):
    estimated_duration_s: float = Field(default=0.0, description="Thời lượng ước tính của toàn bộ video (giây)")
    source_coverage: float = Field(default=0.0, description="Tỷ lệ cảnh có chứa nguồn gốc (để chống bịa)")
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

# ── CẤU HÌNH PROMPTS NÂNG CAO (V2.1 - Prompts Improvement) ──
ART_STYLES = {
    "cinematic_realistic": {
        "keywords": "photorealistic, natural lighting, cinema verite, shallow depth of field",
        "color_grading": "teal orange cinematic lut, desaturated shadows",
        "composition": "rule of thirds, wide establishing shots",
        "mood": "epic, dramatic, emotional"
    },
    "3d_animation": {
        "keywords": "3D render, blender, octane render, volumetric lighting, ray tracing",
        "color_grading": "vibrant colors, high contrast, saturated",
        "composition": "dynamic angles, epic wide shots",
        "mood": "energetic, playful, adventure"
    },
    "cyberpunk": {
        "keywords": "neon lights, cyberpunk city, rain, reflections, hdr",
        "color_grading": "cyan magenta color scheme, high contrast neon",
        "composition": "urban environment, futuristic",
        "mood": "tense, futuristic, mysterious"
    },
    "minimalist_clean": {
        "keywords": "minimal, clean lines, plenty of whitespace, modern design",
        "color_grading": "soft pastels, muted tones",
        "composition": "centered, symmetrical, ample negative space",
        "mood": "calm, professional, trustworthy"
    },
    "oil_painting_classic": {
        "keywords": "oil painting, textured canvas brushstrokes, Renaissance style, chiaroscuro lighting, Da Vinci aesthetic, museum quality",
        "color_grading": "warm amber tones, rich dark shadows, classic museum lighting",
        "composition": "artistic framing, classical portrait or landscape",
        "mood": "mysterious, artistic, timeless"
    },
    "ink_wash_oriental": {
        "keywords": "traditional Asian ink wash painting, Shan Shui watercolor, misty paper texture, rice paper",
        "color_grading": "monochrome ink tones, subtle watercolor wash, soft gold accent",
        "composition": "ample negative space, minimalist asian landscape",
        "mood": "poetic, serene, spiritual, ancient"
    },
    "architectural_cinematic": {
        "keywords": "architectural render, cinematic wide angle, dramatic lighting, 8k detail, epic scale",
        "color_grading": "twilight blue and golden lights, high contrast metallic and stone texture",
        "composition": "low angle monumental view, dramatic perspective lines",
        "mood": "awe-inspiring, majestic, engineering marvel"
    },
    "blueprint_sketch": {
        "keywords": "architectural blueprint sketch, technical drawing lines, white ink on deep blue paper, isometric wireframe",
        "color_grading": "cyan and cobalt blue, crisp white technical lines",
        "composition": "technical diagram, architectural section elevation",
        "mood": "analytical, precise, historical engineering"
    }
}

# ĐÃ BỎ: EMOTION_VISUAL_COUPLING.
# Bảng này từng được tiêm vào prompt chế độ quiz_listicle bằng `f"{EMOTION_VISUAL_COUPLING}"`
# — tức dump nguyên văn repr của một dict Python vào system_instruction, kèm dấu ngoặc và
# dấu nháy. Nhưng nó chỉ có nghĩa nếu Gemini biết cảm xúc của cảnh nó đang viết, mà từ khi
# resolve_blueprint() gán `emotion` ở Python theo băng vị trí thì Gemini KHÔNG còn chọn
# emotion nữa: nó không có cách nào biết cảnh này là 'hook' hay 'calm' để áp đúng dòng.
# Việc ghép tông màu theo cảm xúc giờ do color_grading + motion_effects lo ở tầng render.

NEGATIVE_PROMPT_TEMPLATES = {
    "default": "blurry, low quality, distorted, deformed, ugly, bad anatomy, extra limbs, poorly drawn face",
    "cinematic": "flat lighting, amateur, phone camera quality, compressed, artifacts, cartoon, illustration",
    "3d_animation": "2d, flat colors, stiff, robotic movements, uncanny valley, photorealistic",
}

def get_enhanced_art_style(style: str) -> str:
    key = style.lower().replace(" ", "_")
    if key in ART_STYLES:
        cfg = ART_STYLES[key]
        return f"{cfg['keywords']}, {cfg['color_grading']}, {cfg['composition']}, {cfg['mood']}"
    return style

# 3. MODE: Storyteller (mặc định) + Quiz/Listicle
# ---------------------------------------------------------------------------
# ── Bảng cấu hình thời lượng → số từ ────────────────────────────────
# Đổi chuỗi này mỗi khi luật prompt thay đổi → cache kịch bản cũ tự hết hiệu lực.
PROMPT_REVISION = "2026-07-30-hookquote-retry-nojargon"

# Cùng vai trò cho split_script_to_scenes. Tách riêng để sửa prompt chia cảnh không xoá
# oan cache của generate_script (và ngược lại). LỖI CŨ: cache key của "split_script" hoàn
# toàn không có trường revision, nên mọi lần sửa prompt đều bị cache cũ đè — sửa xong
# không thấy gì thay đổi.
SPLIT_PROMPT_REVISION = "2026-07-30-image-prompt-source"

# Cùng vai trò cho generate_script_from_images. Trước đây cache key của nó KHÔNG có
# trường revision — sửa prompt xong vẫn nhận lại kịch bản cũ từ cache, y hệt lỗi của
# split_script mô tả ở trên.
IMAGE_PROMPT_REVISION = "2026-07-30-photo-content-rules"

# Tốc độ đọc thực đo trên chính pipeline này (Edge-TTS giọng Việt, rate 0%): ~3.0 từ/giây.
# Luật cũ ghi "15-20 từ ≈ 3-5 giây" là BẤT KHẢ THI về số học — 18 từ cần ~6 giây, không
# thể 3-5 giây. Chính sự sai lệch đó khiến cảnh dài gấp rưỡi so với ý đồ. Muốn nhịp
# 3-5 giây/cảnh thật thì ngân sách phải là ~12 từ.
# GIỮ tên cũ cho tương thích, nhưng giá trị giờ lấy từ duration_model — nơi con số này
# tự hiệu chỉnh theo số đo thật của từng giọng. Đây từng là một trong BA hằng số ước
# lượng lệch nhau nằm rải rác trong hệ thống (xem docstring duration_model.py).
def _default_wps() -> float:
    from services import duration_model

    return duration_model.words_per_second()


# Mỗi lần chuyển cảnh tốn thêm ~0.5s (crossfade + nhịp nghỉ giữa hai câu).
SCENE_TRANSITION_OVERHEAD = 0.5


def _estimate_script_duration(scenes) -> float:
    """Thời lượng dự kiến của TOÀN kịch bản, để hiển thị cho user trước khi render.

    Tính qua duration_model nên tự khớp với tốc độ đọc thật đã học được, và tính cả các
    thẻ <break/> mà biên kịch chèn vào — công thức cũ `total_words / 3.0` bỏ qua cả hai,
    nên với kịch bản dùng nhiều nhịp nghỉ thì ước lượng hụt tới vài giây.
    """
    from services import duration_model

    total = 0.0
    for s in scenes:
        text = getattr(s, "text", "") or ""
        pause_ms = getattr(s, "pause_after_ms", 0) or 0
        total += duration_model.estimate_duration(text, pause_after_ms=pause_ms)
    return round(total + len(scenes) * SCENE_TRANSITION_OVERHEAD, 1)


VIETNAMESE_WORDS_PER_SECOND = 3.0
WORDS_PER_SCENE_TARGET = 12   # ≈ 4 giây/cảnh

# Trần số cảnh. Nâng 30 → 75 cho phép tạo kịch bản Podcast / Kể chuyện dài (lên tới 15 phút)
# giữ đúng nhịp 12-18 từ/cảnh (≈ 4-6 giây/cảnh).
MAX_SCENES = 75
MIN_SCENES = 4

DURATION_CONFIG = {
    "15s":  {"words": "30-40"},
    "30s":  {"words": "70-80"},
    "60s":  {"words": "140-160"},
    "90s":  {"words": "210-240"},
    "120s": {"words": "280-320"},
    "180s": {"words": "420-480"},
    "240s": {"words": "560-640"},   # Long-form kể chuyện (4 min)
    "300s": {"words": "700-800"},   # Long-form kể chuyện (5 min)
    "480s": {"words": "1100-1300"}, # Long-form Podcast (8 min)
    "600s": {"words": "1400-1600"}, # Long-form Podcast (10 min)
    "900s": {"words": "2100-2400"}, # Long-form Podcast (15 min)
}


def _parse_word_range(words: str) -> tuple[int, int]:
    lo, _, hi = words.partition("-")
    return int(lo), int(hi or lo)


# `suggested_scenes` SUY RA từ tổng số từ chứ không đặt tay nữa.
# LÝ DO: bảng cũ đặt cứng cả hai nên chúng đá nhau — VD 300s ghi 700-800 từ / 20 cảnh
# = 35-40 từ/cảnh, trong khi prompt lại ra lệnh "tuyệt đối không quá 15-20 từ/cảnh".
# Từ mốc 90s trở lên là mâu thuẫn, và Gemini chọn phá luật số từ → cảnh dài 8+ giây,
# video ì. Giờ chỉ còn MỘT nguồn chân lý: tổng số từ ÷ WORDS_PER_SCENE_TARGET.
for _cfg in DURATION_CONFIG.values():
    _lo, _hi = _parse_word_range(_cfg["words"])
    _cfg["suggested_scenes"] = max(
        MIN_SCENES, min(MAX_SCENES, round(((_lo + _hi) / 2) / WORDS_PER_SCENE_TARGET))
    )


def scene_word_budget(target_duration: str, num_scenes: int) -> tuple[int, int]:
    """
    Số từ cho phép MỖI CẢNH, tính từ tổng số từ của thời lượng mục tiêu chia cho
    số cảnh user thực sự chọn. Nhờ vậy luật số từ và luật tổng thời lượng không thể
    mâu thuẫn nữa, dù user chọn số cảnh bất kỳ.
    """
    cfg = DURATION_CONFIG.get(target_duration)
    if not cfg or num_scenes <= 0:
        return 15, 20
    lo, hi = _parse_word_range(cfg["words"])
    per_lo = max(6, round(lo / num_scenes))
    per_hi = max(per_lo + 2, round(hi / num_scenes))
    return per_lo, per_hi

# ── Bảng tone kể chuyện ─────────────────────────────────────────────
# KHOÁ PHẢI KHỚP frontend/src/constants.js › NARRATION_TONES.
# LỖI CŨ: bảng này đánh khoá theo bộ từ vựng riêng (drama/inspirational) trong khi UI chỉ
# gửi viral/storytelling/educational/emotional/humorous. Vì tra bằng `.get(tone, "")`, hai
# tone ĐƯỢC DÙNG NHIỀU NHẤT — `viral` (mặc định, nút đầu tiên) và `emotional` — nhận về
# chuỗi RỖNG: kịch bản viral chưa từng được nói cho biết nó phải "viral" ra sao. Đồng thời
# "drama"/"inspirational" là prompt chết vì không UI nào gửi tới. Nay khoá chính là 5 giá
# trị thật của UI; hai tên cũ giữ làm alias cho preset đã lưu từ trước.
NARRATION_TONE_PROMPTS = {
    "viral": (
        "Tone: Đanh thép, dồn dập, giật gân có cơ sở. Câu ngắn như đấm. Mỗi câu bỏ được một "
        "chữ thì phải bỏ. Ưu tiên động từ mạnh và con số; tránh tính từ rỗng ('tuyệt vời', "
        "'kinh khủng'). Nói như đang tiết lộ điều lẽ ra không nên nói ra — nhưng KHÔNG bịa, "
        "không hứa hẹn quá lời."
    ),
    "storytelling": (
        "Tone: Trầm lắng, chiêm nghiệm, dẫn chuyện như một người kể chuyện tài hoa. Giọng văn "
        "điện ảnh, giàu cảm xúc nhưng KHÔNG lên gân. Mỗi cảnh kết bằng một câu tạo tò mò nhẹ "
        "(soft cliffhanger) để người xem muốn nghe tiếp."
    ),
    "educational": (
        "Tone: Cuốn hút, khai mở trí óc. Giống như một bí mật vừa được bật mí: tiết lộ sự thật "
        "gây sốc nhưng vẫn đáng tin cậy. Dùng số liệu để đè bẹp sự nghi ngờ. Giải thích bằng "
        "phép so sánh đời thường, không dùng từ hàn lâm."
    ),
    "emotional": (
        "Tone: Sâu sắc, chạm tim, nói thật chậm. Đi vào một chi tiết nhỏ rồi ở lại đó (bàn tay, "
        "lá thư, một câu nói cũ) thay vì kể lướt nhiều chuyện. Chèn '...' ở chỗ cần lặng. "
        "TUYỆT ĐỐI không lên gân, không hô hào, không dạy đời."
    ),
    "humorous": (
        "Tone: Cà khịa, châm biếm, hài hước sâu cay. Chơi chữ, dùng từ ngữ trending của Gen Z "
        "hoặc văn phong 'troll' nhẹ nhàng nhưng thâm thúy. Cú punchline luôn nằm ở CUỐI cảnh, "
        "không giải thích lại câu hài vừa nói."
    ),
    # ── Alias tương thích preset cũ ──
    "drama": (
        "Tone: Đanh thép, kịch tính, dồn dập. Dùng từ ngữ mạnh, hơi hướng giật gân, tạo cảm "
        "giác bí ẩn hoặc bất ngờ tột độ. Không dùng từ thừa."
    ),
    "inspirational": (
        "Tone: Cảm xúc, hùng hồn, truyền động lực mãnh liệt. Đánh vào trái tim người nghe, "
        "dùng từ ngữ khơi gợi khát vọng và vượt qua giới hạn."
    ),
}


# ── CÔNG THỨC HOOK 3 GIÂY ĐẦU (đồng bộ references/hook-library.md) ──
# Prompt cũ chỉ ra lệnh trừu tượng "phải tạo Curiosity Gap" rồi để Gemini tự bơi — nên
# hook hay rơi về mẫu an toàn nhất ("Bạn có biết..."), đúng thứ mà CLICHE_PHRASES trừ điểm.
# Đưa hẳn công thức vào thì model có khuôn để điền.
HOOK_FORMULAS = {
    "viral": (
        "- Phủ định gây sốc: 'Đừng [làm X]... nếu bạn chưa biết điều này.'\n"
        "- Sự thật ẩn giấu: 'Sự thật rùng mình về [chủ đề] mà không ai nói cho bạn.'\n"
        "- Con số sốc: '99% người [làm X] đều sai ngay ở bước đầu.'\n"
        "- Nghịch lý: '[Điều tưởng tốt] mới chính là thứ đang phá bạn.'"
    ),
    "storytelling": (
        "- Mở màn bí ẩn: 'Câu chuyện bắt đầu với [tình huống lạ], nhưng không ai ngờ...'\n"
        "- Nghịch lý nhân vật: 'Cùng một [người/vật], nhưng lại có hai [số phận] trái ngược.'\n"
        "- Lời hứa hé lộ: 'Cuốn sách này giấu một bí mật về [chủ đề] — và nó đổi cách bạn nghĩ.'"
    ),
    "educational": (
        "- Đảo chiều nhận thức: 'Hoá ra [điều tưởng đúng] lại hoàn toàn sai. Đây là lý do.'\n"
        "- Con số mở màn: '[Con số cụ thể] — và gần như không ai giải thích được vì sao.'"
    ),
    "emotional": (
        "- Khoét insight thầm kín: 'Lý do bạn luôn [trạng thái] không phải vì [lời buộc tội "
        "quen thuộc]. Mà vì điều này.'\n"
        "- Chi tiết nhỏ mở màn: bắt đầu từ MỘT hình ảnh cụ thể (lá thư, cuộc gọi lỡ) rồi mới "
        "hé ra nó là chuyện gì."
    ),
    "humorous": (
        "- Tự thú hài: '[Hành động ai cũng làm] và đây là lý do nó ngớ ngẩn hơn bạn tưởng.'\n"
        "- Bẻ lái: dựng một kỳ vọng rất nghiêm túc ở câu đầu rồi đập vỡ nó ở câu thứ hai."
    ),
}


# ── LUẬT CHỐNG "CONTENT CHUNG CHUNG" (SKILL.md §1.5) ────────────────
# Đây là phần tách content hay khỏi content nhạt, và trước đây nó CHỈ nằm trong tài liệu
# skill dành cho agent viết tay — kịch bản do chính app sinh ra không hề được hưởng.
SPECIFICITY_RULES = (
    "QUY TẮC CỤ THỂ (đây là thứ tách content HAY khỏi content NHẠT — BẮT BUỘC):\n"
    "- Mỗi cảnh phải có ÍT NHẤT MỘT trong: con số, tên riêng, mốc thời gian, hoặc chi tiết "
    "giác quan (thấy/nghe/ngửi/chạm được). 'Rất giàu' → 'kiếm 1 triệu đô năm 26 tuổi'. "
    "'Một cuốn sách hay' → 'cuốn 200 trang, bán 40 triệu bản'.\n"
    "- SHOW, DON'T TELL: viết 'cô run rẩy mở lá thư', KHÔNG viết 'cô rất lo lắng'. Tả hành "
    "động sinh ra cảm xúc, đừng thông báo cảm xúc.\n"
    "- MỖI CẢNH PHẢI CÓ ĐÚNG 1 LÝ DO GIỮ CHÂN: một tình tiết mới, một câu hỏi bỏ lửng, hoặc "
    "một tiết lộ. Cảnh nào không thêm gì mới so với cảnh trước thì viết lại, đừng giữ.\n"
    "- CẢNH SAU NỐI Ý CẢNH TRƯỚC ('Nhưng...', 'Và đúng lúc đó...', 'Vấn đề là...'). Không "
    "viết các cảnh rời rạc như gạch đầu dòng.\n"
    "- KHÔNG mở đầu cảnh nào bằng lời chào, lời dẫn hay lời cảm ơn. Vào thẳng nội dung."
)

# CTA thật, cấm khan hiếm giả (hook-library.md § CTA). Prompt cũ chỉ nói "kêu gọi hành động
# khéo léo" nên Gemini hay tự sinh 'lưu ngay kẻo video bị gỡ' — vừa giả vừa dễ vi phạm policy.
CTA_RULES = (
    "QUY TẮC CTA (cảnh cuối + trường cta_text):\n"
    "- Dùng CTA THẬT: 'Lưu lại để không quên nhé.' / 'Bạn nghĩ sao? Comment cho mình biết.' / "
    "'Theo dõi để xem phần 2.' / 'Tag người bạn muốn cùng xem.'\n"
    "- CẤM khan hiếm giả: 'lưu ngay trước khi video bị gỡ', 'xem nhanh kẻo mất', hoặc bất kỳ "
    "con số thống kê bịa ra để tạo áp lực.\n"
    "- CTA phải dính vào nội dung vừa kể, không phải câu chốt dán được vào video bất kỳ."
)

# Lời thoại cho TTS (Edge-TTS/OmniVoice). '...' được pipeline hiểu là chỗ ngắt nghỉ thật —
# trước đây chỉ prompt photo_narration biết mẹo này, hai đường sinh kịch bản kia không.
TTS_WRITING_RULES = (
    "KỸ THUẬT VĂN NÓI (đọc bằng giọng AI):\n"
    "- Xưng 'bạn' trực tiếp. Câu ngắn, mỗi câu một ý.\n"
    "- Chèn '...' vào `text` ở đúng chỗ cần lặng/nhấn — hệ thống hiểu và ngắt nghỉ thật.\n"
    "- Giữ MỘT người kể chuyện xuyên suốt, văn phong không đổi giữa các cảnh.\n"
    "- TUYỆT ĐỐI không Markdown (*, #), không emoji, không ký hiệu lạ trong `text` "
    "(giọng đọc sẽ đọc thành tiếng hoặc phát âm sai)."
)

# ── LUẬT VIẾT image_prompt — RẼ THEO NGUỒN HÌNH ─────────────────────
# Vì sao phải rẽ: khi user render bằng video stock, main.py lấy từ khoá tìm Pexels từ
# chính image_prompt qua extract_search_keyword(). Prompt cũ BẮT BUỘC mở đầu bằng
# "Extreme close-up shot of..." + gắn "8k, Unreal Engine 5" cho MỌI chế độ, nên
# extract_search_keyword phải có một danh sách ~40 stopword chỉ để gỡ lại đúng những chữ
# mà prompt vừa ép model viết ra. Hai tầng đánh nhau, và cái nào lọt lưới thì thành query
# rác → Pexels trả video sai chủ đề. Nay chế độ stock được yêu cầu viết chủ thể đời thực
# ngay từ đầu (khớp .agents/skills/.../stock-footage-guide.md).
IMAGE_PROMPT_RULES_AI = (
    "QUY TẮC ĐẠO DIỄN HÌNH ẢNH — CHẾ ĐỘ ẢNH AI (BẮT BUỘC):\n"
    "- Mở đầu mỗi `image_prompt` bằng góc máy điện ảnh: 'Extreme close-up shot of...', "
    "'Low-angle drone shot of...', 'Over-the-shoulder shot of...', 'Wide establishing shot of...'\n"
    "- Công thức: Góc máy + Đối tượng + Hành động + Ánh sáng + Bối cảnh + Phẩm chất nghệ "
    "thuật (8k, photorealistic, Unreal Engine 5).\n"
    "- NHẤT QUÁN NHÂN VẬT: nếu có nhân vật, lặp lại CHÍNH XÁC ngoại hình (tuổi, giới tính, "
    "trang phục) ở TẤT CẢ các cảnh — hệ thống vẽ từng cảnh riêng biệt, thiếu tả lại là đổi "
    "diễn viên giữa video.\n"
    "- Dùng CHUNG một tông màu ánh sáng cho toàn video "
    "(VD 'cinematic teal and orange lighting, volumetric dust')."
)
IMAGE_PROMPT_RULES_STOCK = (
    "QUY TẮC ĐẠO DIỄN HÌNH ẢNH — CHẾ ĐỘ VIDEO STOCK THẬT (BẮT BUỘC):\n"
    "- Hệ thống sẽ lấy `image_prompt` làm TỪ KHOÁ TÌM VIDEO trên kho stock. Vì vậy phải tả "
    "một cảnh QUAY THẬT, đời thường, tìm được: 'a hand writing a letter by candlelight', "
    "'car headlights on a rainy night street', 'lonely person walking in autumn park'.\n"
    "- CẤM mở đầu bằng thuật ngữ máy quay ('Extreme close-up shot of', 'Low-angle drone "
    "shot of') và CẤM từ khoá render ('8k', 'Unreal Engine', 'Octane', 'photorealistic') — "
    "chúng biến thành từ khoá rác và kho stock sẽ trả về video sai chủ đề.\n"
    "- Viết CHỦ THỂ trước tiên, 3-8 từ tiếng Anh, không dấu câu rườm rà.\n"
    "- TRÁNH hình ảnh giả tưởng/anime/CGI (rồng, phép thuật, nhân vật hoạt hình) — không có "
    "footage thật nào khớp.\n"
    "- Ưu tiên khớp CẢM XÚC của lời kể hơn là minh hoạ đúng từng chữ: bàn tay, ánh đèn, "
    "khung cửa sổ, thư từ, đường phố, thiên nhiên, đồ vật gợi hoài niệm."
)


# Bước tự kiểm ĐẾM TỪ. Đo trên kịch bản thật (tài chính, 6 cảnh, trần 14 từ): 2/6 cảnh ra
# 15 từ — lố đúng 1 từ. Model không "cảm" được số từ nếu không được yêu cầu đếm tường minh,
# nên nói thẳng ra thành một bước phải làm trước khi trả kết quả.
WORD_COUNT_SELF_CHECK = (
    "TRƯỚC KHI TRẢ KẾT QUẢ: đếm lại số từ của TỪNG cảnh. Cảnh nào vượt trần thì tự cắt bớt "
    "chữ hoặc tách thành hai cảnh — đừng trả về cảnh đã biết là quá dài."
)

# Biên dung sai của lớp review với ngân sách từ. Lố 1 từ trên trần 14 không phá nhịp video
# (≈0.35 giây), nhưng bản cũ vẫn gắn severity 'error' và trừ 8 điểm cho nó — người dùng thấy
# hai lỗi ĐỎ trên một kịch bản hoàn toàn dùng được, rồi mất niềm tin vào cả lớp review. Cảnh
# dài thật (18-20 từ trên trần 14) vẫn bị bắt đúng.
WORD_BUDGET_TOLERANCE_RATIO = 0.1


def _cliche_ban_rule() -> str:
    """Danh sách cụm sáo rỗng bị cấm, sinh TỪ CHÍNH `CLICHE_PHRASES`.

    LỖI CŨ: prompt liệt kê tay 4 cụm, còn `_local_review` trừ điểm theo 15 cụm khác. Model
    bị phạt vì những cụm chưa ai nói cho nó biết là cấm ('nói cách khác', 'tóm lại là',
    'và đó chính là'...). Giờ hai đầu dùng CÙNG một nguồn chân lý, không thể lệch lại.
    """
    joined = "; ".join(f"'{p}'" for p in CLICHE_PHRASES)
    return (
        "- CẤM TUYỆT ĐỐI các cụm sáo rỗng sau (có lớp kiểm duyệt tự động trừ điểm nếu "
        f"xuất hiện): {joined}."
    )


def _batch_scope_rule(batch_idx: int, batch_size: int, total_scenes: int) -> str:
    """Chỉ dẫn phạm vi cho một LÔ khi kịch bản dài phải sinh nhiều lần.

    LỖI CŨ: mỗi lô đều nhận nguyên system prompt có dòng '4. CTA (Cảnh cuối): Kêu gọi hành
    động', nên với 30 cảnh (3 lô: 12+12+6) Gemini viết CTA + lời chốt ở cuối CẢ BA lô —
    video có ba cái kết, hai cái nằm giữa bài (cảnh 12 và 24). Cách sửa cũ chỉ thay chuỗi
    'CHÍNH XÁC N phân cảnh' nên không chạm tới vấn đề này.
    """
    first = batch_idx == 0
    last = batch_idx + batch_size >= total_scenes
    start, end = batch_idx + 1, batch_idx + batch_size
    if first and last:
        return ""  # kịch bản gọn trong 1 lô: giữ nguyên vòng cung đầy đủ

    head = (
        f"PHẠM VI LÔ HIỆN TẠI: bạn đang viết cảnh {start} đến {end} của một video gồm "
        f"{total_scenes} cảnh.\n"
    )
    if last:
        return head + (
            "Lô này CHỨA CẢNH CUỐI của video: đặt CAO TRÀO ở khoảng 80% tổng số cảnh, rồi "
            "đúc kết và CTA ở cảnh cuối cùng. Đây là chỗ duy nhất được phép có lời kết."
        )
    if first:
        return head + (
            "Lô này là PHẦN MỞ ĐẦU. TUYỆT ĐỐI KHÔNG viết cảnh kết, không đúc kết, không CTA, "
            "không câu chốt kiểu 'và đó là lý do...' — video còn dài. Cảnh cuối của lô phải "
            "BỎ LỬNG để lô sau tiếp mạch."
        )
    return head + (
        "Lô này là PHẦN GIỮA. KHÔNG viết lại hook mở màn, KHÔNG viết cảnh kết/đúc kết/CTA. "
        "Nối tiếp trực tiếp mạch của cảnh trước và để cảnh cuối lô BỎ LỬNG."
    )


# ── BẢN VẼ NỘI DUNG THEO NICHE (thứ biến content từ "chung chung" thành "đúng chất") ──
# Đồng bộ .agents/skills/content-cinematic/references/content-frameworks.md +
# scene-blueprints.md. "~X%" = vị trí tương đối trong tổng số cảnh; Gemini tự quy ra
# cảnh số mấy.
#
# HAI LỖI ĐÃ SỬA Ở BẢN NÀY:
#
# 1. TOÀN BỘ BẢNG NÀY TỪNG LÀ CODE CHẾT. Nó được viết ra, được ghi vào tài liệu
#    (docs/HeThong_SoanContent_AI_Video.md), nhưng KHÔNG một dòng nào tiêm nó vào
#    system_instruction — grep `NICHE_BLUEPRINTS` chỉ ra đúng 1 kết quả: chính chỗ định
#    nghĩa. Nghĩa là chọn niche "Tài chính" trên UI chỉ đổi được sfx/transition (phần cơ
#    học do resolve_blueprint gán ở Python), còn LỜI THOẠI vẫn y hệt niche khác. Giờ
#    build_script_system_prompt() nối nó vào thật.
# 2. Mọi chỉ dẫn cơ học (sfx 'riser', transition 'zoom_punch', rate '-3%') đã bị BỎ khỏi
#    đây. Chúng vô nghĩa với Gemini: LLMScene không có các trường đó, và
#    resolve_blueprint() ghi đè toàn bộ bằng NICHE_PERCENT_BLUEPRINTS ngay sau khi parse.
#    Giữ lại chỉ tốn token và làm loãng phần chỉ dẫn NỘI DUNG — thứ duy nhất Gemini thật
#    sự điều khiển được. Bảng % cơ học vẫn là NICHE_PERCENT_BLUEPRINTS bên dưới.
NICHE_BLUEPRINTS = {
    "book": (
        "NICHE: REVIEW/KỂ CHUYỆN SÁCH-PHIM.\n"
        "BẢN VẼ NỘI DUNG (bắt buộc bám theo vị trí):\n"
        "- Cảnh 1 — `image_prompt`: PHẢI là ảnh bìa sách hoặc một vật thể biểu tượng rõ nét, "
        "vì hệ thống lấy CHÍNH ảnh cảnh 1 làm bìa cho hiệu ứng Máy Xèng (Slot Machine) 3.5 giây đầu. "
        "Cảnh 1 — `text`: TUYỆT ĐỐI KHÔNG tả bìa, không đọc lại tên sách/tên tác giả (người xem đang "
        "nhìn thấy bìa rồi). Vào thẳng nghịch lý hoặc câu hỏi nhức nhối mà cuốn sách trả lời.\n"
        "- ~15% đầu: dựng bối cảnh & nhân vật bằng một tình huống cụ thể, KHÔNG spoiler cái kết.\n"
        "- Phần giữa: mỗi cảnh đúng 1 nút thắt, kết bằng soft cliffhanger "
        "('Nhưng điều cô không ngờ tới là...', 'Câu trả lời anh nhận được nghe thật vô lý...').\n"
        "- ~45%: MINI-TWIST giữ chân — một chi tiết lật lại điều người xem vừa tin.\n"
        "- ~80%: CAO TRÀO — tiết lộ lớn nhất của cuốn sách, câu trị giá cả cuốn.\n"
        "- Sau cao trào: một cảnh dư âm, khoảnh khắc nhân vật (hoặc người đọc) ngộ ra.\n"
        "- Cảnh cuối: BẮT BUỘC là KẾT BÀI — bài học đọng lại + mời đọc/CTA. Không được cụt."
    ),
    "finance": (
        "NICHE: TÀI CHÍNH/LÀM GIÀU/KINH DOANH.\n"
        "BẮT BUỘC mỗi cảnh có CON SỐ/tỉ lệ/mốc thời gian cụ thể. Cấm đạo lý suông.\n"
        "BẢN VẼ NỘI DUNG:\n"
        "- Cảnh 1: nghịch lý tiền bạc + một con số sốc (VD 'Căn nhà bạn đang ở có thể đang âm thầm "
        "rút cạn ví bạn mỗi tháng 12 triệu').\n"
        "- Kế tiếp: đào sâu nỗi đau — người xem tự nhận ra mình đang mắc.\n"
        "- Giữa: giải thích CƠ CHẾ, mỗi cảnh một ý (tài sản vs tiêu sản), có ví dụ thật hoặc so sánh 2 vế.\n"
        "- ~70%: con số chốt hạ, cái làm người xem phải dừng lại tính nhẩm.\n"
        "- ~85%: nguyên tắc vàng, phát biểu được thành một câu nhớ được.\n"
        "- Cảnh cuối: một hành động cụ thể làm được ngay hôm nay + CTA."
    ),
    "history": (
        "NICHE: LỊCH SỬ/BÍ ẨN.\n"
        "BẢN VẼ NỘI DUNG:\n"
        "- Cảnh 1: bí ẩn mở màn kiểu 'Suốt 100 năm, thứ này bị xoá khỏi sách sử. Cho đến khi...'.\n"
        "- ~25% đầu: dựng bối cảnh thời đại bằng chi tiết cụ thể (năm, địa danh, tên riêng).\n"
        "- Giữa: chuỗi manh mối — mỗi cảnh đúng 1 manh mối, kết bằng một câu hỏi.\n"
        "- ~70%: manh mối LẬT NGƯỢC toàn bộ giả thuyết vừa dựng.\n"
        "- ~85%: TIẾT LỘ sự thật.\n"
        "- Cảnh cuối: ý nghĩa với hiện tại + một câu hỏi mở cho người xem."
    ),
    "psychology": (
        "NICHE: TÂM LÝ/SELF-HELP.\n"
        "BẢN VẼ NỘI DUNG:\n"
        "- Cảnh 1: insight khoét vào nỗi đau thầm kín ('Lý do bạn luôn mệt mỏi không phải vì lười').\n"
        "- Kế tiếp: đồng cảm, gỡ cảm giác tội lỗi cho người xem.\n"
        "- Giữa: giải thích hiện tượng và ĐẶT TÊN cho nó (hiệu ứng/hội chứng X), kèm ví dụ đời thường.\n"
        "- ~70%: khoảnh khắc NGỘ RA — câu khiến người xem thốt lên 'đúng là mình'.\n"
        "- Kế tiếp: đúng 1 hành động nhỏ áp dụng được ngay.\n"
        "- Cảnh cuối: một câu hỏi tự vấn để người xem mang theo."
    ),
    "truecrime": (
        "NICHE: TRUE CRIME/VỤ ÁN. Nếu vụ án có thật: KHÔNG bịa chi tiết, KHÔNG nêu tên "
        "nạn nhân/nghi phạm chưa được xác thực. Nếu là hư cấu, phải nói rõ.\n"
        "BẢN VẼ NỘI DUNG:\n"
        "- Cảnh 1: hiện trường hoặc sự biến mất + đúng 1 chi tiết rùng mình cụ thể.\n"
        "- Kế tiếp: dòng thời gian (giờ, ngày) dựng nghi vấn.\n"
        "- Giữa: từng nghi vấn dẫn tới từng manh mối.\n"
        "- ~70%: manh mối LẬT NGƯỢC hướng điều tra.\n"
        "- ~85%: sự thật.\n"
        "- Cảnh cuối: kết cục + một suy ngẫm, không phán xét thay người xem."
    ),
    "travel": (
        "NICHE: DU LỊCH/KHÁM PHÁ.\n"
        "BẢN VẼ NỘI DUNG:\n"
        "- Cảnh 1: teaser cảnh đẹp nhất + lời thách ('Nơi này Google Maps cũng khó tìm').\n"
        "- Kế tiếp: đường đến và không khí nơi đó.\n"
        "- Giữa: điểm độc nhất không nơi nào có, kèm chi tiết GIÁC QUAN (mùi, vị, âm thanh) — "
        "đây là thứ khiến video du lịch hay hơn ảnh đẹp.\n"
        "- ~80%: trải nghiệm đắt nhất, khoảnh khắc đáng đi.\n"
        "- Cảnh cuối: chốt chi phí/thời điểm nên đi + rủ bạn cùng đi."
    ),
    "art_masterpiece": (
        "NICHE: TRANH & TÁC PHẨM NGHỆ THUẬT KINH ĐIỂN.\n"
        "BẢN VẼ NỘI DUNG:\n"
        "- Cảnh 1: chi tiết ẩn/bí ẩn nhất trong bức tranh, tả cận như đang soi kính lúp.\n"
        "- Kế tiếp: bối cảnh ra đời & bi kịch của người họa sĩ (năm, thành phố, hoàn cảnh).\n"
        "- Giữa: giải mã kỹ thuật vẽ, ánh sáng, hoặc ẩn dụ — mỗi cảnh một phát hiện.\n"
        "- ~70%: MINI-TWIST, bí mật ít ai biết về tác phẩm.\n"
        "- ~85%: CAO TRÀO — vì sao bức tranh này còn sống sau hàng thế kỷ.\n"
        "- Cảnh cuối: dư âm chiêm nghiệm + câu hỏi mở mời bình luận."
    ),
    "poetry_literature": (
        "NICHE: THƠ CA & VĂN HỌC NGHỆ THUẬT.\n"
        "Lời thoại phải giữ NGUYÊN VĂN câu thơ khi trích; không diễn giải thành văn xuôi rồi "
        "gọi đó là thơ. Chèn '...' ở chỗ cần lặng giữa các vần.\n"
        "BẢN VẼ NỘI DUNG:\n"
        "- Cảnh 1: 2-4 câu thơ đắt giá nhất.\n"
        "- Kế tiếp: hoàn cảnh sáng tác & hồn thơ (năm, biến cố của tác giả).\n"
        "- Giữa: bình giải từng hình tượng, chỉ ra chữ nào làm nên câu thơ.\n"
        "- ~75%: ĐIỂM CHẠM CẢM XÚC lớn nhất của bài.\n"
        "- Cảnh cuối: dư âm + lời nhắn chiêm nghiệm."
    ),
    "architecture_wonders": (
        "NICHE: CÔNG TRÌNH & KỲ QUAN KIẾN TRÚC.\n"
        "BẢN VẼ NỘI DUNG:\n"
        "- Cảnh 1: con số kỷ lục hoặc mật mã kỹ thuật kỳ lạ (VD '2.3 triệu khối đá, không một "
        "giọt vữa').\n"
        "- Kế tiếp: bối cảnh lịch sử & tham vọng của người xây.\n"
        "- Giữa: kỳ tích kỹ thuật — vật liệu, kết cấu chịu lực, cách họ làm được khi chưa có máy móc.\n"
        "- ~70%: NGUY CƠ suýt làm công trình sụp đổ.\n"
        "- ~85%: CAO TRÀO — vì sao nó trường tồn qua hàng thế kỷ.\n"
        "- Cảnh cuối: giá trị di sản hôm nay + kêu gọi ghé thăm/bình luận."
    ),
}


# ── Base prompt riêng cho chế độ KỂ CHUYỆN LONG-FORM (style @sachhay_chondoc) ──
# Khác hẳn base_storyteller (tối ưu hook giật gân 15-60s): đây là kể lại cốt truyện
# sách/phim dạng dài, trầm lắng, footage thật khớp cảm xúc.
BASE_STORYTELLING = (
    "Bạn là người kể chuyện sách/phim bậc thầy trên TikTok/YouTube, chuyên tóm tắt & kể lại "
    "cốt truyện tiểu thuyết, phim theo lối điện ảnh cuốn hút hàng triệu view.\n\n"
    "CẤU TRÚC KỂ CHUYỆN LONG-FORM:\n"
    "1. MỞ (Cảnh 1-2): Giới thiệu bối cảnh & nhân vật bằng một tình huống gợi tò mò, KHÔNG spoiler cái kết.\n"
    "2. DIỄN BIẾN (phần thân): Kể tuần tự các nút thắt của câu chuyện. Mỗi cảnh là một bước ngoặt nhỏ.\n"
    "3. CAO TRÀO: Nút thắt lớn nhất, tình tiết bất ngờ nhất.\n"
    "4. KẾT & ĐÚC KẾT: Gỡ nút + một câu suy ngẫm đọng lại, rồi mời người xem đọc/tìm hiểu thêm.\n\n"
    "QUY TẮC VĂN KỂ (BẮT BUỘC):\n"
    "- LỖI CHẾT NGƯỜI: {SCENE_WORD_RULE} Nếu câu dài, BẮT BUỘC tách thành nhiều cảnh liên tiếp để video đổi cảnh liên tục. {WORD_COUNT_SELF_CHECK}\n"
    "- Mỗi cảnh kết bằng một câu tạo tò mò nhẹ (soft cliffhanger), VD: 'Nhưng điều cô không ngờ tới là...', "
    "'Câu trả lời anh nhận được nghe thật vô lý...'.\n"
    "- Văn nói tự nhiên, trầm lắng, mạch lạc. TUYỆT ĐỐI không dùng Markdown, không emoji.\n"
    "- Giữ ĐÚNG tên nhân vật/địa danh trong tác phẩm gốc nếu chủ đề nhắc tới.\n\n"
    "QUY TẮC HÌNH ẢNH (CỰC KỲ QUAN TRỌNG — DÙNG FOOTAGE THẬT):\n"
    "- image_prompt PHẢI mô tả một cảnh QUAY THẬT, đời thường, giàu cảm xúc, CÓ THỂ tìm thấy trên kho video "
    "stock (Pexels): VD 'a hand writing a letter by candlelight', 'car headlights on a rainy night street', "
    "'lonely person walking in autumn park', 'cloudy sky at dusk'.\n"
    "- TUYỆT ĐỐI TRÁNH hình ảnh giả tưởng/anime/CGI không có thật (rồng, phép thuật, nhân vật hoạt hình) — "
    "vì sẽ không tìm được footage thật khớp.\n"
    # Đo trên kịch bản thật (Nhà Giả Kim, 10 cảnh, tone storytelling): 3/10 image_prompt vẫn
    # kèm 'photorealistic, 8k', 'cinematic lighting', 'stock footage style'. Base này dặn "tả
    # cảnh quay thật" nhưng chưa CẤM tường minh các keyword đó, mà chúng chính là thứ biến câu
    # truy vấn Pexels thành rác.
    "- CẤM các keyword render/chất lượng trong image_prompt: '8k', 'photorealistic', "
    "'cinematic lighting', 'stock footage style', 'Unreal Engine', 'Octane'. Chúng là từ khoá "
    "rác khi hệ thống đi tìm video thật. Chỉ tả CHỦ THỂ và HÀNH ĐỘNG.\n"
    "- Ưu tiên: bàn tay, ánh đèn, khung cửa sổ, thư từ, đường phố, thiên nhiên, đồ vật gợi hoài niệm — "
    "khớp CẢM XÚC của lời kể hơn là minh hoạ đúng từng chữ.\n\n"
    "QUY TẮC ÂM THANH (RẤT QUAN TRỌNG): TUYỆT ĐỐI KHÔNG lạm dụng sfx. Hầu hết các cảnh PHẢI ĐỂ TRỐNG trường 'sfx' (để giá trị rỗng). Chỉ được phép chèn sfx ở Cảnh 1 và đúng 1 cảnh Cao trào.\n"
    "QUY TẮC CẢM XÚC: 'emotion' phần lớn là 'calm' hoặc 'dramatic'/'suspense' ở cao trào; 'closing' ở cảnh cuối.\n"
)


# ── BẢN VẼ % CHO NICHE VÀ TONE (Sprint 1) ──
# Tuple: (start_pct, end_pct, emotion, sfx, transition, speech_rate, visual_effect)
NICHE_PERCENT_BLUEPRINTS = {
    "book": [
        (0.00, 0.06, "hook",     "",         "fade_black", "+5%", "zoom_in"),
        (0.06, 0.20, "calm",     "",         "crossfade",  "0%", "none"),
        (0.20, 0.42, "calm",     "",         "page_flip",  "0%", "none"),
        (0.42, 0.50, "suspense", "suspense", "fade_black", "-3%", "zoom_in"),   # mini-twist
        (0.50, 0.75, "dramatic", "",         "crossfade",  "0%", "none"),
        (0.75, 0.83, "dramatic", "riser",    "zoom_punch", "-3%", "zoom_in"),   # cao trào
        (0.83, 0.92, "calm",     "shimmer",  "droplet",    "-5%", "none"),   # dư âm
        (0.92, 1.01, "closing",  "ding",     "fade_black", "-5%", "none"),
    ],
    "finance": [
        (0.00, 0.15, "hook",     "riser",    "whip_pan",   "+15%", "zoom_in"),
        (0.15, 0.30, "dramatic", "",         "slide_left", "+5%", "none"),
        (0.30, 0.50, "calm",     "tick",     "slide_right","0%", "none"),
        (0.50, 0.70, "excited",  "bass_drop","zoom_punch", "-3%", "zoom_in"),
        (0.70, 0.90, "dramatic", "impact",   "fade_white", "0%", "none"),
        (0.90, 1.01, "closing",  "ding",     "fade_black", "+5%", "none"),
    ],
    "history": [
        (0.00, 0.10, "hook",     "suspense", "fade_black", "+5%", "zoom_in"),
        (0.10, 0.25, "calm",     "",         "crossfade",  "0%", "none"),
        (0.25, 0.65, "suspense", "heartbeat","crossfade",  "-3%", "none"),
        (0.65, 0.75, "dramatic", "suspense", "wipe_down",  "-3%", "none"),
        (0.75, 0.85, "dramatic", "impact",   "zoom_punch", "-3%", "zoom_in"),
        (0.85, 1.01, "closing",  "",         "droplet",    "-5%", "none"),
    ],
    "psychology": [
        (0.00, 0.15, "hook",     "",         "crossfade",  "0%", "zoom_in"),
        (0.15, 0.30, "calm",     "",         "crossfade",  "-5%", "none"),
        (0.30, 0.70, "calm",     "",         "crossfade",  "-5%", "none"),
        (0.70, 0.85, "dramatic", "shimmer",  "droplet",    "-8%", "zoom_in"),
        (0.85, 1.01, "closing",  "",         "fade_black", "-8%", "none"),
    ],
    "truecrime": [
        (0.00, 0.15, "hook",     "heartbeat","fade_black", "+5%", "zoom_in"),
        (0.15, 0.35, "suspense", "",         "crossfade",  "0%", "none"),
        (0.35, 0.65, "suspense", "suspense", "fade_black", "0%", "none"),
        (0.65, 0.80, "dramatic", "bass_drop","whip_pan",   "+5%", "zoom_in"),
        (0.80, 0.90, "dramatic", "impact",   "zoom_punch", "-3%", "zoom_in"),
        (0.90, 1.01, "closing",  "",         "droplet",    "-5%", "none"),
    ],
    "travel": [
        (0.00, 0.20, "hook",     "swoosh_soft","slide_up", "+10%", "zoom_in"),
        (0.20, 0.40, "excited",  "",         "wipe_right", "0%", "none"),
        (0.40, 0.60, "excited",  "pop",      "zoom_through","0%", "zoom_in"),
        (0.60, 0.80, "calm",     "shimmer",  "crossfade",  "-3%", "none"),
        (0.80, 1.01, "closing",  "ding",     "fade_black", "+5%", "none"),
    ],
    # ── 3 niche bổ sung (trước đây thiếu bản vẽ %, fallback về tone chung) ──
    "art_masterpiece": [
        (0.00, 0.10, "hook",     "riser",    "zoom_through","+5%", "zoom_in"),   # zoom cận chi tiết bí ẩn
        (0.10, 0.25, "calm",     "",         "crossfade",   "0%", "none"),       # bối cảnh họa sĩ
        (0.25, 0.50, "calm",     "",         "crossfade",   "0%", "none"),       # giải mã kỹ thuật
        (0.50, 0.65, "calm",     "shimmer",  "crossfade",   "0%", "none"),       # phát hiện đắt giá
        (0.65, 0.75, "suspense", "suspense", "page_flip",   "-3%", "zoom_in"),   # mini-twist bí ẩn
        (0.75, 0.88, "dramatic", "impact",   "zoom_punch",  "-5%", "zoom_in"),   # cao trào giá trị
        (0.88, 1.01, "closing",  "",         "droplet",     "-5%", "none"),       # dư âm chiêm nghiệm
    ],
    "poetry_literature": [
        (0.00, 0.12, "hook",     "shimmer",  "crossfade",   "-10%", "zoom_in"),  # câu thơ đắt giá
        (0.12, 0.30, "calm",     "",         "crossfade",   "-8%", "none"),      # hoàn cảnh sáng tác
        (0.30, 0.60, "calm",     "",         "crossfade",   "-8%", "none"),      # bình giải hình tượng
        (0.60, 0.80, "dramatic", "droplet",  "droplet",     "-12%", "zoom_in"),  # điểm chạm cảm xúc
        (0.80, 1.01, "closing",  "",         "fade_black",  "-10%", "none"),     # dư âm thi ca
    ],
    "architecture_wonders": [
        (0.00, 0.12, "hook",     "riser",    "whip_pan",    "+10%", "zoom_in"),  # con số kỷ lục
        (0.12, 0.25, "calm",     "",         "slide_left",  "0%", "none"),       # bối cảnh lịch sử
        (0.25, 0.50, "calm",     "tick",     "crossfade",   "0%", "none"),       # kỹ thuật xây dựng
        (0.50, 0.70, "suspense", "suspense", "zoom_punch",  "-3%", "zoom_in"),   # thách thức sụp đổ
        (0.70, 0.85, "dramatic", "bass_drop","fade_white",  "-5%", "zoom_in"),   # cao trào trường tồn
        (0.85, 1.01, "closing",  "ding",     "fade_black",  "0%", "none"),       # di sản thế giới
    ],
}

TONE_PERCENT_PALETTES = {
    "viral": [
        (0.0, 0.2, "hook", "riser", "whip_pan", "+15%", "zoom_in"),
        (0.2, 0.7, "calm", "", "crossfade", "0%", "none"),
        (0.7, 0.9, "excited", "bass_drop", "zoom_punch", "+10%", "zoom_in"),
        (0.9, 1.01, "closing", "ding", "fade_black", "0%", "none")
    ],
    "storytelling": [
        (0.0, 0.2, "hook", "", "fade_black", "+5%", "zoom_in"),
        (0.2, 0.8, "calm", "", "crossfade", "0%", "none"),
        (0.8, 0.9, "dramatic", "suspense", "droplet", "-3%", "zoom_in"),
        (0.9, 1.01, "closing", "", "fade_black", "-5%", "none")
    ],
    "educational": [
        (0.0, 0.2, "hook", "tick", "slide_left", "+10%", "zoom_in"),
        (0.2, 0.8, "calm", "", "crossfade", "0%", "none"),
        (0.8, 0.9, "dramatic", "bass_drop", "zoom_punch", "-3%", "zoom_in"),
        (0.9, 1.01, "closing", "ding", "fade_black", "0%", "none")
    ],
    "emotional": [
        (0.0, 0.2, "hook", "", "crossfade", "-5%", "zoom_in"),
        (0.2, 0.8, "calm", "", "crossfade", "-5%", "none"),
        (0.8, 0.9, "dramatic", "shimmer", "droplet", "-8%", "zoom_in"),
        (0.9, 1.01, "closing", "", "fade_black", "-5%", "none")
    ],
    "humorous": [
        (0.0, 0.2, "hook", "pop", "slide_up", "0%", "zoom_in"),
        (0.2, 0.7, "calm", "", "crossfade", "0%", "none"),
        (0.7, 0.9, "excited", "laugh", "whip_pan", "+10%", "zoom_in"),
        (0.9, 1.01, "closing", "ding", "fade_black", "0%", "none")
    ]
}


def resolve_blueprint(niche: str, tone: str, total_scenes: int) -> list[dict]:
    bp = NICHE_PERCENT_BLUEPRINTS.get(niche) or TONE_PERCENT_PALETTES.get(tone) or TONE_PERCENT_PALETTES["viral"]
    out = []
    for i in range(total_scenes):
        p = i / max(total_scenes - 1, 1)
        # fallback band
        band = bp[-1]
        for b in bp:
            if b[0] <= p < b[1]:
                band = b
                break
        out.append({
            "emotion": band[2],
            "sfx": band[3],
            "transition": band[4],
            "speech_rate_modifier": band[5],
            "visual_effect": band[6],
        })
    return out

def scene_word_rule_text(target_duration: str, num_scenes: int) -> str:
    """Câu luật số từ/cảnh, quy ra cả số GIÂY đọc theo tốc độ giọng đã học được.

    Tách ra khỏi generate_script để test được và để mọi đường sinh kịch bản dùng chung một
    cách phát biểu — trước đây mỗi hàm tự viết một kiểu.
    """
    w_lo, w_hi = scene_word_budget(target_duration, num_scenes)
    # Lấy tốc độ ĐÃ HỌC thay vì hằng số: nói với Gemini "12 từ ≈ 4 giây" trong khi giọng
    # thật đọc 2.7 từ/giây (≈4.4 giây) là tự đẩy kịch bản lố ngay từ khâu sinh chữ.
    wps = _default_wps()
    sec_lo = w_lo / (wps + 0.2)
    sec_hi = w_hi / max(0.5, wps - 0.4)
    return (
        f"Mỗi phân cảnh tuyệt đối KHÔNG ĐƯỢC VƯỢT QUÁ {w_hi} từ "
        f"(lý tưởng {w_lo}-{w_hi} từ, tương đương {sec_lo:.1f}-{sec_hi:.1f} giây đọc)."
    )


# ── Master Viral Base Prompt ──
# Đã BỎ ba mục "DYNAMIC PACING", "QUY TẮC TRANSITION" và "CẤM lạm dụng SFX" của bản cũ:
# LLMScene không có các trường speech_rate_modifier/transition/sfx (xem class LLMScene), và
# resolve_blueprint() ghi đè toàn bộ chúng bằng bảng % ngay sau khi parse xong. Ra lệnh cho
# Gemini về những trường nó không thể trả về vừa vô ích vừa hút mất sự chú ý khỏi phần nó
# THẬT SỰ điều khiển: lời thoại và image_prompt. Chỗ trống đó giờ dành cho SPECIFICITY_RULES
# và HOOK_FORMULAS — những luật vốn chỉ nằm trong tài liệu skill.
BASE_VIRAL = (
    "Bạn là đạo diễn và biên kịch video ngắn HÀNG ĐẦU thế giới, chuyên tạo nội dung Triệu "
    "View trên TikTok/Reels/Shorts.\n\n"
    "CẤU TRÚC KỂ CHUYỆN (Curiosity Gap & PAS):\n"
    "1. HOOK (Cảnh 1): Móc câu sắc bén, tạo một 'Curiosity Gap' (lỗ hổng tò mò). Nếu xem "
    "xong cảnh 1 mà khán giả không muốn biết tiếp, bạn thất bại.\n"
    "2. TENSION (các cảnh giữa): Xoáy sâu vào vấn đề bằng chi tiết cụ thể, mỗi cảnh nâng "
    "mức căng lên một bậc. Không kể lể dài dòng.\n"
    "3. CLIMAX (~80% thời lượng): Sự thật bất ngờ nhất (plot twist) hoặc giải pháp tột đỉnh.\n"
    "4. CTA (cảnh cuối): Chốt lại rồi kêu gọi hành động tự nhiên.\n\n"
    "CÔNG THỨC HOOK — chọn ĐÚNG MỘT mẫu rồi điền, không viết chung chung:\n"
    "{HOOK_FORMULAS}\n\n"
    "QUY TẮC CẤM KỴ (BẮT BUỘC TUÂN THỦ):\n"
    "- LỖI CHẾT NGƯỜI: Cảnh quá dài. {SCENE_WORD_RULE} Nếu câu văn dài, BẮT BUỘC cắt thành "
    "2-3 cảnh liên tiếp! {WORD_COUNT_SELF_CHECK}\n"
    "{CLICHE_BAN}\n"
    "- CẤM nói đạo lý suông, cấm từ ngữ hàn lâm. Mọi luận điểm phải kèm con số hoặc hình "
    "ảnh so sánh thực tế.\n\n"
    "{SPECIFICITY_RULES}\n\n"
    "{TTS_WRITING_RULES}\n\n"
    "{CTA_RULES}\n\n"
    "{IMAGE_PROMPT_RULES}\n"
)


def build_script_system_prompt(
    *,
    num_scenes: int,
    mode: str = "storyteller",
    art_style: str = "Cinematic",
    target_duration: str = "30s",
    narration_tone: str = "viral",
    content_niche: Optional[str] = None,
    character_description: Optional[str] = None,
    sync_characters: bool = False,
    prefer_stock_video: bool = False,
    batch_idx: int = 0,
    batch_size: Optional[int] = None,
    revision_notes: Optional[List[str]] = None,
) -> str:
    """Dựng TOÀN BỘ system_instruction cho generate_script — hàm THUẦN, không gọi mạng.

    Trước đây khối này nằm lẫn trong thân generate_script nên không test nào chạm được, và
    hai lỗi câm đã sống ở đó rất lâu: bản vẽ niche không bao giờ được tiêm, và mọi lô của
    kịch bản dài đều tự viết một cái kết (xem _batch_scope_rule).

    `batch_idx`/`batch_size` chỉ khác mặc định khi kịch bản dài phải chia lô; khi đó
    `num_scenes` vẫn là TỔNG số cảnh của video, còn `batch_size` là số cảnh của lô này.
    """
    total_scenes = num_scenes
    this_batch = batch_size or num_scenes

    image_rules = IMAGE_PROMPT_RULES_STOCK if prefer_stock_video else IMAGE_PROMPT_RULES_AI

    # Chế độ KỂ CHUYỆN long-form (tone=storytelling): base prompt riêng, style @sachhay_chondoc.
    # Base này đã tự có luật hình ảnh footage thật nên không nối image_rules vào nữa.
    if narration_tone == "storytelling" and mode != "quiz_listicle":
        system_prompt = BASE_STORYTELLING + (
            f"\nNhiệm vụ: kể câu chuyện cho chủ đề được cung cấp thành CHÍNH XÁC "
            f"{this_batch} phân cảnh nối tiếp mạch lạc. "
            "image_prompt viết bằng tiếng Anh (mô tả cảnh quay thật để tìm footage stock)."
        )
        system_prompt += f"\n\n{SPECIFICITY_RULES}\n\n{TTS_WRITING_RULES}"
    elif mode == "quiz_listicle":
        system_prompt = BASE_VIRAL + (
            f"\nCHẾ ĐỘ: Quiz/Listicle — viết kịch bản gồm CHÍNH XÁC {this_batch} phân cảnh "
            "theo dạng 'Top N' hoặc hỏi-đáp. Mỗi cảnh là 1 fact/item hoặc 1 câu hỏi+đáp thú "
            "vị, và mỗi item phải có một chi tiết người xem chưa biết. "
            "image_prompt viết bằng tiếng Anh, cực kỳ chi tiết. "
            f"Phong cách hình ảnh bắt buộc (Art Style): '{get_enhanced_art_style(art_style)}'."
        )
    else:  # storyteller (mặc định)
        system_prompt = BASE_VIRAL + (
            f"\nNhiệm vụ: viết kịch bản gồm CHÍNH XÁC {this_batch} phân cảnh cho chủ đề "
            "được cung cấp. image_prompt viết bằng tiếng Anh, mô tả cực kỳ chi tiết theo "
            f"phong cách nghệ thuật: '{art_style}'."
        )

    # ── Bản vẽ NỘI DUNG theo niche (ưu tiên cao nhất: cụ thể hơn tone) ──
    niche_blueprint = NICHE_BLUEPRINTS.get(content_niche or "", "")
    if niche_blueprint:
        system_prompt += f"\n\n{niche_blueprint}"

    # ── Tone kể chuyện ──
    tone_prompt = NARRATION_TONE_PROMPTS.get(narration_tone, "")
    if tone_prompt:
        system_prompt += f"\n\n{tone_prompt}"

    # ── Ngân sách từ theo thời lượng mục tiêu ──
    dur_cfg = DURATION_CONFIG.get(target_duration)
    if dur_cfg:
        system_prompt += (
            f"\n\nLƯU Ý QUAN TRỌNG: Video dài ~{target_duration}. Bắt buộc: TOÀN BỘ kịch bản "
            f"gộp lại (tổng chữ của tất cả {total_scenes} cảnh) chỉ được dài khoảng "
            f"{dur_cfg['words']} từ."
        )

    # ── Đồng nhất nhân vật ──
    if sync_characters and character_description:
        system_prompt += (
            "\n\nĐỒNG NHẤT NHÂN VẬT & PHONG CÁCH:\n"
            "BẮT BUỘC chèn ĐÚNG ĐOẠN TEXT SAU vào đầu mọi trường 'image_prompt' của tất cả "
            f"các cảnh:\n[{character_description}]\n"
            "Điều này là bắt buộc để hệ thống vẽ ảnh giữ nguyên nhân vật xuyên suốt video!"
        )

    # ── Hook cấp video: ba trường riêng, rất dễ bị nhầm lẫn với nhau ──
    # `hook_quote` trước đây không có trong schema nên chưa bao giờ được sinh tự động, dù
    # RenderVideoRequest và video_service.build_carousel_hook() đều chờ nó.
    system_prompt += (
        "\n\nHOOK CẤP VIDEO (3 trường riêng, KHÔNG phải lời thoại của cảnh nào):\n"
        "- `hook_text`: TIÊU ĐỀ giật gân dưới 10 chữ, được vẽ ĐÈ LÊN ảnh bìa. Vì bìa đã in "
        "sẵn tên chủ đề/tên sách, hook_text lặp lại chúng là phí giây đầu tiên — hãy nêu MÂU "
        "THUẪN hoặc LỜI HỨA khiến người xem phải ở lại.\n"
        "- `hook_variants`: 3 biến thể hook_text thật sự KHÁC NHAU (khác cả góc tiếp cận, "
        "không phải đổi vài chữ), để người dùng A/B test.\n"
        "- `hook_quote`: CÂU TRÍCH đắt nhất của nội dung, viết HOA, dưới 15 từ, tốt nhất là "
        "2 vế đối lập ('NGƯỜI NGHÈO LÀM VIỆC VÌ TIỀN. NGƯỜI GIÀU BẮT TIỀN LÀM VIỆC CHO "
        "MÌNH.'). Đứng một mình vẫn đáng trích. Để RỖNG nếu không có câu nào thật đắt."
    )

    # ── Nguồn dẫn chứng (làm cho source_coverage có nghĩa) ──
    # LỖI CŨ: ScriptResponse.source_coverage được tính từ `source_quote` và hiển thị như
    # "tỷ lệ cảnh có nguồn gốc (chống bịa)", nhưng KHÔNG prompt nào từng yêu cầu điền
    # source_quote — nên chỉ số này luôn bằng 0.0 với mọi video.
    system_prompt += (
        "\n\nNGUỒN DẪN CHỨNG (chống bịa): nếu chủ đề gắn với một tác phẩm, tài liệu hoặc sự "
        "kiện THẬT mà bạn nhớ chắc chắn, hãy điền `source_quote` (nguyên văn đoạn trích) và "
        "`source_ref` (vị trí, VD 'Chương 3'). Nếu không chắc, để RỖNG — thà trống còn hơn "
        "bịa một câu trích không tồn tại."
    )

    # ── Phạm vi lô (chỉ có khi kịch bản dài phải sinh nhiều lần) ──
    batch_rule = _batch_scope_rule(batch_idx, this_batch, total_scenes)
    if batch_rule:
        system_prompt += f"\n\n{batch_rule}"

    # ── Góp ý từ lần viết trước (chỉ có ở lượt viết lại) ──
    if revision_notes:
        danh_sach = "\n".join(f"- {n}" for n in revision_notes)
        system_prompt += (
            "\n\nĐÂY LÀ LƯỢT VIẾT LẠI. Bản trước đã bị lớp biên tập đánh giá KHÔNG ĐẠT vì "
            f"những điểm dưới đây. Hãy viết một kịch bản MỚI khắc phục đúng chúng, đừng lặp "
            f"lại cách viết cũ:\n{danh_sach}"
        )

    # Thay các token của template (có mặt trong cả BASE_VIRAL lẫn BASE_STORYTELLING).
    hook_formulas = HOOK_FORMULAS.get(narration_tone) or HOOK_FORMULAS["viral"]
    return (
        system_prompt.replace("{SCENE_WORD_RULE}", scene_word_rule_text(target_duration, total_scenes))
        .replace("{HOOK_FORMULAS}", hook_formulas)
        .replace("{CLICHE_BAN}", _cliche_ban_rule())
        .replace("{SPECIFICITY_RULES}", SPECIFICITY_RULES)
        .replace("{TTS_WRITING_RULES}", TTS_WRITING_RULES)
        .replace("{CTA_RULES}", CTA_RULES)
        .replace("{IMAGE_PROMPT_RULES}", image_rules)
        .replace("{WORD_COUNT_SELF_CHECK}", WORD_COUNT_SELF_CHECK)
    )


async def generate_script(
    topic: str,
    variation_seed: int = 0,
    num_scenes: int = 4,
    mode: str = "storyteller",
    art_style: str = "Cinematic",
    api_key: Optional[str] = None,
    target_duration: str = "30s",
    narration_tone: str = "viral",
    character_description: Optional[str] = None,
    sync_characters: bool = False,
    content_niche: Optional[str] = None,
    prefer_stock_video: bool = False,
    revision_notes: Optional[List[str]] = None,
) -> List[dict]:
    """
    Gọi Gemini để sinh N phân cảnh từ 1 chủ đề (topic).
    Hỗ trợ mode: storyteller, quiz_listicle.
    Trả về list[dict] đã được validate đúng schema Scene.

    `prefer_stock_video` quyết định KIỂU image_prompt: True → tả cảnh quay thật tìm được
    trên kho stock; False → prompt cinematic cho mô hình sinh ảnh. Rẽ nhánh ở đây thay vì
    để extract_search_keyword() gỡ lại đống thuật ngữ máy quay ở tầng sau.

    `revision_notes` chỉ được truyền ở LƯỢT VIẾT LẠI (xem `regenerate_if_low_quality`): đó là
    các nhận xét của lớp review về bản trước, được nối vào prompt để bản mới sửa đúng chỗ.
    Nó cũng nằm trong cache key — nếu không, lượt viết lại sẽ nhận lại y nguyên bản vừa bị
    đánh giá là kém.
    """
    num_scenes = max(MIN_SCENES, min(MAX_SCENES, num_scenes))
    _notes_key = hashlib.md5("|".join(revision_notes or []).encode("utf-8")).hexdigest()[:8]

    def _call():
        cached_result = cache.get("gen_script", topic=topic, num_scenes=num_scenes, mode=mode, art_style=art_style, target_duration=target_duration, narration_tone=narration_tone, niche=content_niche or "", char_desc=character_description or "", sync=sync_characters, seed=variation_seed, stock=prefer_stock_video, notes=_notes_key, prompt_rev=PROMPT_REVISION)
        if cached_result:
            logger.info("Using cached result for generate_script")
            return cached_result
        try:
            BATCH_SIZE = 12
            all_scenes = []
            global_fields = {}

            for batch_idx in range(0, num_scenes, BATCH_SIZE):
                current_batch_size = min(BATCH_SIZE, num_scenes - batch_idx)

                # Prompt của lô được DỰNG LẠI với đúng phạm vi, thay vì vá chuỗi trên
                # prompt tổng như trước (cách vá đó không thể diễn tả nổi "lô này không
                # được có cảnh kết" — nên video 30 cảnh có tới ba cái kết).
                batch_prompt = build_script_system_prompt(
                    num_scenes=num_scenes,
                    mode=mode,
                    art_style=art_style,
                    target_duration=target_duration,
                    narration_tone=narration_tone,
                    content_niche=content_niche,
                    character_description=character_description,
                    sync_characters=sync_characters,
                    prefer_stock_video=prefer_stock_video,
                    batch_idx=batch_idx,
                    batch_size=current_batch_size,
                    revision_notes=revision_notes,
                )

                batch_content = f"Chủ đề video: {topic}\n"
                if batch_idx > 0:
                    prev_context = "\n".join([f"Cảnh {s.scene}: {s.text}" for s in all_scenes[-2:]])
                    batch_content += f"\nNgữ cảnh 2 cảnh trước đó (chỉ để nối tiếp mạch truyện, KHÔNG sinh lại nội dung này):\n{prev_context}"
                    batch_content += f"\nTiếp tục viết từ cảnh {batch_idx+1} đến {batch_idx+current_batch_size}."
                else:
                    batch_content += "\nHãy tạo phần đầu của kịch bản."

                def _call_one_batch(_prompt=batch_prompt, _content=batch_content):
                    # _get_client() LẤY LẠI mỗi lần thử (không dùng client dựng sẵn ở
                    # ngoài): nếu _retry_sync bên dưới vừa xoay vòng key vì 429, lần thử
                    # kế tiếp phải cầm key MỚI, không phải client cũ còn giữ key đã cạn.
                    client = _get_client(api_key)
                    response = client.models.generate_content(
                        model="gemini-flash-latest",
                        contents=_content,
                        config=types.GenerateContentConfig(
                            system_instruction=_prompt,
                            response_mime_type="application/json",
                            response_schema=LLMScriptResponse,
                            temperature=0.9,
                        ),
                    )
                    _track_quota()
                    return _require_parsed(response, "generate_script")

                # LỖI CŨ: cả hàm _call() này (bao trọn vòng lặp batch) được bọc MỘT LẦN
                # bởi _retry_sync ở cuối hàm generate_script(). 429/503 thoáng qua ở batch
                # CUỐI (vd batch 3/3 của kịch bản 30 cảnh) khiến TOÀN BỘ vòng lặp — kể cả
                # các batch trước đã gọi API thành công — chạy lại TỪ ĐẦU mỗi lần retry,
                # nhân quota tiêu tốn lên gấp nhiều lần, đúng thứ RuntimeError bên dưới
                # đang cảnh báo user. Bọc _retry_sync ở CẤP TỪNG BATCH: batch đã xong
                # không bao giờ bị gọi lại.
                parsed: LLMScriptResponse = _retry_sync(_call_one_batch, key_manager=gemini_keys)

                if batch_idx == 0:
                    global_fields = {
                        "sentiment": parsed.sentiment,
                        "recommended_bgm": parsed.recommended_bgm,
                        "hook_text": parsed.hook_text,
                        "hook_variants": parsed.hook_variants,
                        "hook_quote": parsed.hook_quote,
                        "cta_text": parsed.cta_text,
                    }
                # CTA lấy từ lô CUỐI: chỉ lô cuối mới biết video kết thúc ở đâu, nên CTA của
                # nó mới dính được vào nội dung vừa kể. Lấy từ lô 1 như trước là lấy câu chốt
                # do một model chưa hề viết phần kết nghĩ ra.
                if batch_idx + current_batch_size >= num_scenes and (parsed.cta_text or "").strip():
                    global_fields["cta_text"] = parsed.cta_text

                # Fix scene index just in case the LLM resets to 1
                for i, s in enumerate(parsed.scenes):
                    s.scene = batch_idx + i + 1
                    
                all_scenes.extend(parsed.scenes)
                
            # Đã sinh đủ tất cả các cảnh, giờ resolve blueprint
            resolved = resolve_blueprint(content_niche, narration_tone, len(all_scenes))
            final_scenes = []
            for i, scene_data in enumerate(all_scenes):
                mech = resolved[i]
                final_scenes.append(Scene(
                    scene=scene_data.scene,
                    text=scene_data.text,
                    image_prompt=scene_data.image_prompt,
                    highlight_text=scene_data.highlight_text,
                    scene_type=scene_data.scene_type,
                    source_quote=scene_data.source_quote,
                    source_ref=scene_data.source_ref,
                    subtitle_text=scene_data.subtitle_text,
                    emotion=mech['emotion'],
                    sfx=mech['sfx'],
                    transition=mech['transition'],
                    speech_rate_modifier=mech['speech_rate_modifier'],
                    visual_effect=mech['visual_effect'],
                    visual_source="auto",
                    pause_after_ms=0,
                    bgm_volume=scene_data.bgm_volume
                ))
            
            # Calculate source_coverage (Anti-hallucination metric)
            scenes_with_quotes = sum(1 for s in final_scenes if s.source_quote and s.source_quote.strip())
            source_coverage = scenes_with_quotes / max(1, len(final_scenes))

            est_duration = _estimate_script_duration(final_scenes)
            
            final_result = ScriptResponse(
                estimated_duration_s=round(est_duration, 1),
                source_coverage=round(source_coverage, 2),
                sentiment=global_fields.get("sentiment", "happy"),
                recommended_bgm=global_fields.get("recommended_bgm", ""),
                hook_text=global_fields.get("hook_text", ""),
                hook_variants=global_fields.get("hook_variants", []),
                hook_quote=global_fields.get("hook_quote", ""),
                cta_text=global_fields.get("cta_text", ""),
                scenes=final_scenes
            )
            result = final_result.model_dump()
            cache.set("gen_script", result, topic=topic, num_scenes=num_scenes, mode=mode, art_style=art_style, target_duration=target_duration, narration_tone=narration_tone, niche=content_niche or "", char_desc=character_description or "", sync=sync_characters, seed=variation_seed, stock=prefer_stock_video, notes=_notes_key, prompt_rev=PROMPT_REVISION)
            return result
        except Exception as e:
            # KHÔNG trả kịch bản mock (trước đây trả video "Python" bất kể chủ đề, âm thầm
            # nuốt lỗi khiến user nhận nội dung sai lệch). Ném lỗi thật để pipeline báo lên UI.
            logger.error(f"Gemini generate_script thất bại cho chủ đề '{topic}': {e}")
            raise

    # KHÔNG bọc _call bằng _retry_sync ở đây nữa — retry đã chuyển vào cấp từng batch
    # bên trong _call() (xem _call_one_batch). Bọc thêm một lớp retry NGOÀI nữa sẽ quay
    # lại đúng lỗi cũ: lỗi không-retryable ở bước resolve_blueprint/Scene(...) (không
    # phải 429/503) trước đây cũng KHÔNG được _retry_sync thử lại (is_retryable=False),
    # nên bỏ lớp ngoài không đổi hành vi cho nhánh đó — chỉ khác ở đúng nhánh 429/503.
    return await asyncio.to_thread(_call)


# ---------------------------------------------------------------------------
# 3.5. AI SCRIPT REVIEWER — Kiểm soát chất lượng tự động (B2)
# ---------------------------------------------------------------------------
# Lớp QC chạy sau generate_script, trước khi trả kịch bản cho FE. Hai tầng:
#   Tầng 1 (_local_review): heuristic chuỗi — cụm sáo rỗng/độ dài/CTA. Miễn phí, luôn chạy.
#   Tầng 2 (_gemini_narrative_review): 1 lần gọi Gemini (model flash, temperature=0.3
#     cho deterministic, prompt ngắn) đánh giá hook/cao trào/mạch cảm xúc — thứ heuristic
#     chuỗi không "hiểu" được. Best-effort: lỗi (quota/mạng) bị nuốt êm trong review_script,
#     không chặn luồng sinh kịch bản chính.
# ---------------------------------------------------------------------------

# ── Danh sách cụm từ sáo rỗng bị CẤM ──
CLICHE_PHRASES = [
    "xin chào các bạn", "hôm nay mình sẽ", "cùng tìm hiểu nhé",
    "bạn có biết rằng", "các bạn ơi", "như chúng ta đã biết",
    "không thể phủ nhận", "nói cách khác", "tóm lại là",
    "điều đáng nói ở đây", "thực chất là", "đúng như bạn nghĩ",
    "và đó chính là", "hãy cùng khám phá", "chào mừng bạn đến với",
]


class SceneReviewNote(BaseModel):
    scene_index: int = Field(description="Số thứ tự cảnh (1-indexed)")
    issue_type: str = Field(description="Loại lỗi: 'cliche' | 'too_long' | 'weak_hook' | 'missing_cta' | 'flat_pacing'")
    severity: str = Field(description="Mức độ: 'error' | 'warning' | 'info'")
    message: str = Field(description="Mô tả lỗi ngắn gọn tiếng Việt")
    suggestion: str = Field(default="", description="Gợi ý sửa (nếu có)")


class ScriptReviewResult(BaseModel):
    quality_score: int = Field(description="Điểm chất lượng tổng thể (0-100)")
    review_notes: List[SceneReviewNote] = Field(default_factory=list)
    passed: bool = Field(description="True nếu kịch bản đạt chất lượng tối thiểu (≥60)")


class NarrativeReviewNote(BaseModel):
    scene_index: int = Field(description="Số thứ tự cảnh liên quan nhất (1-indexed). Dùng 0 nếu là nhận xét cho toàn bộ kịch bản, không riêng cảnh nào.")
    issue_type: str = Field(description="Loại lỗi: 'weak_hook' | 'weak_climax' | 'flat_emotion' | 'pacing_issue' | 'narrative_gap'")
    severity: str = Field(description="Mức độ: 'error' | 'warning' | 'info'")
    message: str = Field(description="Nhận xét ngắn gọn bằng tiếng Việt")
    suggestion: str = Field(default="", description="Gợi ý sửa cụ thể, hành động được")


class NarrativeReviewResult(BaseModel):
    narrative_score: int = Field(description="Điểm 0-100 CHỈ đánh giá hook mở đầu, cao trào/plot twist, và mạch cảm xúc xuyên suốt — không tính lỗi câu chữ hay độ dài")
    notes: List[NarrativeReviewNote] = Field(default_factory=list)


def _local_review(
    scenes: list, word_budget_hi: int, cta_text: str = ""
) -> ScriptReviewResult:
    """
    Review LOCAL (không tốn API): phát hiện cụm từ sáo rỗng, cảnh quá dài,
    thiếu CTA ở cảnh cuối. Nhanh và miễn phí — luôn chạy.

    `cta_text` là CTA cấp video (trường riêng, không thuộc cảnh nào). Phải xét tới nó vì
    `video_service.resolve_outro_text()` đem đúng chuỗi này ra làm chữ ở đuôi video — kịch bản
    có cta_text thì video CÓ CTA, dù không cảnh nào chứa chữ 'like/share'. Bỏ qua nó là báo
    động sai: đo trên kịch bản thật (Nhà Giả Kim, 90 điểm) thì note 'thiếu CTA' nổ lên trong
    khi cta_text = 'Hãy tìm đọc cuốn sách tuyệt vời này nhé!' đã sẵn sàng hiện ở outro.
    """
    notes = []
    total_score = 100

    for i, scene in enumerate(scenes):
        text = scene.get("text", "") or ""
        words = text.split()

        # ── Check cụm từ sáo rỗng ──
        text_lower = text.lower()
        for cliche in CLICHE_PHRASES:
            if cliche in text_lower:
                notes.append(SceneReviewNote(
                    scene_index=i + 1,
                    issue_type="cliche",
                    severity="warning",
                    message=f"Chứa cụm từ sáo rỗng: '{cliche}'",
                    suggestion=f"Thay bằng câu cụ thể hơn, ví dụ: con số, câu hỏi gây sốc, hoặc tình huống."
                ))
                total_score -= 5

        # ── Check cảnh quá dài ──
        # Có biên dung sai: xem WORD_BUDGET_TOLERANCE_RATIO. Lố 1 từ không phá nhịp, nhưng
        # bản cũ vẫn gắn 'error' + trừ 8 điểm cho nó.
        tolerance = max(1, round(word_budget_hi * WORD_BUDGET_TOLERANCE_RATIO))
        if len(words) > word_budget_hi + tolerance:
            notes.append(SceneReviewNote(
                scene_index=i + 1,
                issue_type="too_long",
                severity="error",
                message=f"Cảnh có {len(words)} từ, vượt ngân sách {word_budget_hi} từ",
                suggestion="Tách thành 2-3 cảnh liên tiếp ngắn hơn."
            ))
            total_score -= 8

    # ── Check CTA ở cảnh cuối ──
    if scenes:
        last_text = (scenes[-1].get("text", "") or "").strip()
        last_lower = last_text.lower()
        cta_keywords = ["theo dõi", "subscribe", "chia sẻ", "bình luận", "comment",
                        "like", "thích", "đăng ký", "share", "tag", "lưu lại", "lưu ngay"]
        # CÂU HỎI MỞ cũng là CTA hợp lệ — đây còn là kiểu CTA được chính hook-library.md
        # khuyến nghị ('Bạn nghĩ sao về điều này?'). Đo trên kịch bản thật: cảnh cuối
        # "Trích ngay 10% thu nhập tháng này để đầu tư. Bạn dám thử không?" bị báo THIẾU CTA
        # chỉ vì không chứa chữ 'like/share/follow' — cảnh báo sai làm người dùng đi sửa một
        # cảnh vốn đã đúng, và trừ oan 3 điểm.
        has_cta = (
            any(kw in last_lower for kw in cta_keywords)
            or last_text.endswith("?")
            or bool((cta_text or "").strip())
        )
        if not has_cta:
            notes.append(SceneReviewNote(
                scene_index=len(scenes),
                issue_type="missing_cta",
                severity="info",
                message="Cảnh cuối chưa có CTA rõ ràng (kêu gọi like/share/follow)",
                suggestion="Thêm câu hỏi mở hoặc lời kêu gọi hành động tự nhiên."
            ))
            total_score -= 3

    # ── Check hook cảnh 1 ──
    if scenes:
        first_text = (scenes[0].get("text", "") or "").lower()
        hook_weak_starts = ["xin chào", "hôm nay", "chào các bạn", "trong video này"]
        if any(first_text.startswith(ws) for ws in hook_weak_starts):
            notes.append(SceneReviewNote(
                scene_index=1,
                issue_type="weak_hook",
                severity="error",
                message="Hook mở đầu yếu — dùng câu chào hỏi thay vì gây tò mò",
                suggestion="Thay bằng câu hỏi gây sốc, con số bất ngờ, hoặc tình huống kịch tính."
            ))
            total_score -= 10

    total_score = max(0, min(100, total_score))
    return ScriptReviewResult(
        quality_score=total_score,
        review_notes=notes,
        passed=total_score >= 60,
    )


_NARRATIVE_REVIEW_PROMPT = """Bạn là biên tập viên kịch bản video ngắn (TikTok/Reels) giàu kinh nghiệm.
Đánh giá CHỈ 3 khía cạnh sau của kịch bản dưới đây, KHÔNG chấm lỗi chính tả/câu chữ/độ dài
(đã có lớp kiểm tra khác lo việc đó):

1. HOOK (cảnh 1): có đủ gây tò mò/sốc để giữ chân người xem trong 3 giây đầu không?
2. CAO TRÀO: kịch bản có một điểm nhấn/plot twist/thông tin bất ngờ rõ ràng ở đâu đó không,
   hay kể đều đều từ đầu đến cuối?
3. MẠCH CẢM XÚC: cảm xúc có tăng dần hợp lý không, hay bị đứt quãng/phẳng lì/lặp lại?

Với mỗi vấn đề THỰC SỰ đáng kể tìm thấy, ghi 1 note cụ thể (scene_index liên quan, gợi ý sửa
hành động được). Đừng bịa lỗi nếu kịch bản đã ổn — narrative_score cao và notes rỗng là kết quả
hợp lệ. Chấm điểm trung thực, không thiên vị."""


def _gemini_narrative_review(scenes: list, api_key: str | None) -> NarrativeReviewResult:
    """
    Tầng 2 (Gemini thật) của B2 — bổ sung cho _local_review (chỉ bắt cụm sáo rỗng/độ
    dài/CTA bằng chuỗi, không "hiểu" hook/cao trào/cảm xúc như tên gọi "AI Script
    Reviewer" ngụ ý). Model flash, temperature thấp, prompt ngắn — đúng thiết kế đã
    ghi trong comment ở đầu section này nhưng trước đó chưa ai nối vào.

    Đây là lớp BEST-EFFORT: lỗi ở đây (quota, mạng, timeout) KHÔNG được làm hỏng cả
    luồng sinh kịch bản — người gọi (review_script) phải bọc try/except quanh hàm này.
    """
    client = _get_client(api_key)
    script_text = "\n".join(
        f"Cảnh {s.get('scene', i + 1)}: {(s.get('text') or '').strip()}"
        for i, s in enumerate(scenes)
        if (s.get("text") or "").strip()
    )
    response = client.models.generate_content(
        model="gemini-flash-latest",
        contents=script_text,
        config=types.GenerateContentConfig(
            system_instruction=_NARRATIVE_REVIEW_PROMPT,
            response_mime_type="application/json",
            response_schema=NarrativeReviewResult,
            temperature=0.3,
        ),
    )
    _track_quota()
    return _require_parsed(response, "_gemini_narrative_review")


async def review_script(
    script_result: dict,
    word_budget_hi: int = 20,
    api_key: str | None = None,
) -> dict:
    """
    Kiểm soát chất lượng kịch bản AI sinh ra.
    Tầng 1 (local): kiểm tra cụm từ sáo rỗng, word budget, CTA — luôn chạy, miễn phí.
    Tầng 2 (Gemini): đánh giá hook/cao trào/mạch cảm xúc — best-effort, bỏ qua êm nếu
    lỗi (quota/mạng) để không chặn luồng sinh kịch bản chính.
    Trả về dict chứa quality_score, review_notes, passed.
    """
    scenes = script_result.get("scenes", [])
    if not scenes:
        return ScriptReviewResult(quality_score=0, review_notes=[], passed=False).model_dump()

    review = _local_review(
        scenes, word_budget_hi, cta_text=script_result.get("cta_text", "") or ""
    )

    try:
        narrative = await asyncio.to_thread(_gemini_narrative_review, scenes, api_key)
    except Exception as e:
        logger.warning(f"Script Review (tầng Gemini): bỏ qua — {e}")
        narrative = None

    if narrative is not None:
        review.review_notes.extend(
            SceneReviewNote(
                scene_index=n.scene_index,
                issue_type=n.issue_type,
                severity=n.severity,
                message=n.message,
                suggestion=n.suggestion,
            )
            for n in narrative.notes
        )
        # Trung bình cộng 2 tầng: không để riêng 1 tầng (VD Gemini chấm khắt khe hơn
        # bình thường) kéo điểm xuống một mình, nhưng vẫn phản ánh đủ nếu cả hai đồng
        # thuận điểm thấp.
        review.quality_score = round((review.quality_score + narrative.narrative_score) / 2)
        review.passed = review.quality_score >= 60

    # Ghi log cho debugging
    if review.review_notes:
        logger.info(f"Script Review: score={review.quality_score}, issues={len(review.review_notes)}")
        for note in review.review_notes:
            logger.info(f"  [{note.severity}] Cảnh {note.scene_index}: {note.message}")

    return review.model_dump()


# ── Vòng VIẾT LẠI khi điểm chất lượng quá thấp ──────────────────────
# Tài liệu dự án từng khẳng định "nếu không đạt điểm tối thiểu 60/100, kịch bản sẽ bị ép sinh
# lại" — điều đó chưa từng đúng: điểm được tính, ghi log, trả cho UI, rồi kịch bản kém vẫn đi
# thẳng vào bước render. Đây là phần bù lại lời hứa đó, với ba chốt an toàn:
#   1. ĐÚNG MỘT lượt viết lại (mỗi lượt tốn thêm quota).
#   2. Bản mới phải ĐIỂM CAO HƠN mới được nhận — viết lại có thể ra bản tệ hơn, và im lặng
#      thay bằng bản tệ hơn thì còn hại hơn không làm gì.
#   3. Lỗi ở lượt viết lại (quota/mạng) bị bỏ qua êm: trả về bản đầu, không làm chết request.
REGENERATE_SCORE_THRESHOLD = 60

# Chỉ những loại lỗi mà VIẾT LẠI mới sửa được thì mới đáng tốn một lượt gọi. `too_long` bị
# loại cố ý: scene_balancer + luật số từ trong prompt đã lo, và một cảnh lố 2 từ không xứng
# một lượt quota.
_REGENERATE_WORTHY_ISSUES = {
    "weak_hook", "weak_climax", "flat_emotion", "flat_pacing", "narrative_gap", "cliche",
}


def _revision_notes_from_review(review: dict) -> List[str]:
    """Lọc các nhận xét đáng đưa vào lượt viết lại, gộp thành câu hành động được."""
    ra = []
    for n in review.get("review_notes", []):
        if n.get("issue_type") not in _REGENERATE_WORTHY_ISSUES:
            continue
        cau = n.get("message", "").strip()
        goi_y = (n.get("suggestion") or "").strip()
        idx = n.get("scene_index") or 0
        vi_tri = f"Cảnh {idx}: " if idx else ""
        ra.append(f"{vi_tri}{cau}{' → ' + goi_y if goi_y else ''}")
    return ra


async def regenerate_if_low_quality(
    script_result: dict,
    review_result: dict,
    *,
    word_budget_hi: int,
    gen_kwargs: dict,
    api_key: str | None = None,
) -> tuple[dict, dict]:
    """Viết lại kịch bản ĐÚNG MỘT LẦN nếu điểm dưới ngưỡng, rồi giữ bản điểm cao hơn.

    Trả về `(script_result, review_result)` — của bản được chọn. `review_result` của bản mới
    có thêm khoá `regenerated` để UI nói cho người dùng biết đã viết lại, và `previous_score`
    để họ thấy nó tốt lên bao nhiêu.
    """
    if review_result.get("quality_score", 0) >= REGENERATE_SCORE_THRESHOLD:
        return script_result, review_result

    notes = _revision_notes_from_review(review_result)
    if not notes:
        # Điểm thấp nhưng toàn lỗi mà viết lại không sửa được → đừng tốn quota.
        logger.info("Script Review: điểm thấp nhưng không có lỗi nào viết lại sửa được.")
        return script_result, review_result

    diem_cu = review_result.get("quality_score", 0)
    logger.info(f"Script Review: {diem_cu} < {REGENERATE_SCORE_THRESHOLD} — viết lại 1 lượt.")

    try:
        ban_moi = await generate_script(**gen_kwargs, revision_notes=notes)
        review_moi = await review_script(
            ban_moi, word_budget_hi=word_budget_hi, api_key=api_key
        )
    except Exception as e:
        logger.warning(f"Viết lại kịch bản thất bại, giữ bản đầu — {e}")
        return script_result, review_result

    diem_moi = review_moi.get("quality_score", 0)
    if diem_moi <= diem_cu:
        logger.info(f"Bản viết lại không tốt hơn ({diem_moi} ≤ {diem_cu}) — giữ bản đầu.")
        review_result = dict(review_result)
        review_result["regenerated"] = False
        review_result["rejected_retry_score"] = diem_moi
        return script_result, review_result

    logger.info(f"Đã nhận bản viết lại: {diem_cu} → {diem_moi} điểm.")
    review_moi = dict(review_moi)
    review_moi["regenerated"] = True
    review_moi["previous_score"] = diem_cu
    return ban_moi, review_moi


# ---------------------------------------------------------------------------

# 4. MODE: Photo Narration — Gemini multimodal phân tích ảnh
# ---------------------------------------------------------------------------
def build_photo_system_prompt(*, num_images: int, topic: Optional[str] = None) -> str:
    """system_instruction cho `generate_script_from_images` — hàm THUẦN, không gọi mạng.

    Tách ra cùng lý do như hai hàm build_* kia. Nhân dịp này prompt cũng được hưởng các luật
    nội dung dùng chung (cụ thể/show-don't-tell/cấm sáo rỗng/CTA thật) mà trước đây chỉ
    generate_script mới có — đường photo_narration vốn chỉ được dặn "viết văn nói, câu ngắn",
    nên lời bình cho ảnh hay ra kiểu chú thích album chứ không giữ chân được người xem.
    """
    topic_hint = f" Chủ đề gợi ý: '{topic}'." if topic else ""

    # Ngân sách từ mỗi cảnh, suy ra từ CÙNG hằng số với generate_script để hai đường
    # sinh kịch bản không lệch nhịp đọc. Cố ý KHÔNG đặt cứng "15-20 từ": xem ghi chú
    # ở scene_word_budget() — luật cứng đó từng đá nhau với luật tổng số từ, và Gemini
    # chọn phá luật số từ, làm cảnh dài 8+ giây.
    w_hi = WORDS_PER_SCENE_TARGET + 3
    sec_hi = w_hi / _default_wps()

    return (
        "Bạn là biên kịch video chuyên nghiệp. "
        f"Người dùng cung cấp {num_images} bức ảnh.{topic_hint} "
        f"Nhiệm vụ: viết CHÍNH XÁC {num_images} phân cảnh (mỗi ảnh = 1 cảnh). "
        "Phân tích nội dung từng ảnh và viết lời bình luận tiếng Việt dưới dạng 'văn nói'. "
        "Lời bình phải nói ĐIỀU NGƯỜI XEM KHÔNG TỰ THẤY ĐƯỢC trong ảnh (bối cảnh, cảm xúc, "
        "câu chuyện đằng sau) — nếu chỉ tả lại thứ đang hiện trên màn hình thì cảnh đó vô ích. "
        "Kịch bản phải tuân theo cấu trúc: [Hook (3s đầu)] -> [Thân bài] -> [Bài học] -> "
        "[Call-to-Action kết thúc bằng câu hỏi mở]. "
        "image_prompt: viết mô tả tiếng Anh ngắn gọn về nội dung ảnh (dùng cho metadata).\n\n"
        f"{_cliche_ban_rule().lstrip('- ')}\n\n"
        f"{SPECIFICITY_RULES}\n\n"
        f"{TTS_WRITING_RULES}\n\n"
        f"{CTA_RULES}\n\n"
        "ĐỘ DÀI LỜI THOẠI (BẮT BUỘC): đây là video DỌC 9:16, phụ đề chạy đè lên khung hình "
        f"nên câu dài sẽ tràn ra ngoài màn hình. Mỗi phân cảnh tuyệt đối KHÔNG ĐƯỢC VƯỢT QUÁ "
        f"{w_hi} từ (~{sec_hi:.1f} giây đọc). Câu dài phải CẮT thành nhiều phân cảnh ngắn. "
        "TUYỆT ĐỐI không viết đoạn văn dài.\n"
        f"{WORD_COUNT_SELF_CHECK}"
    )


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
    system_prompt = build_photo_system_prompt(num_images=num_images, topic=topic)

    def _call():
        # Use content hashing for deterministic cache key instead of basename
        import hashlib
        hasher = hashlib.md5()
        for p in image_paths:
            if os.path.isfile(p):
                with open(p, "rb") as f:
                    hasher.update(f.read())
        paths_hash = hasher.hexdigest()
        cached_result = cache.get("gen_script_imgs", topic=topic, num_images=num_images, paths=paths_hash, prompt_rev=IMAGE_PROMPT_REVISION)
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
            model="gemini-flash-latest",
            contents=content_parts,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=LLMScriptResponse,
                temperature=0.8,
            ),
        )
        _track_quota()
        parsed: LLMScriptResponse = _require_parsed(response, "generate_script_from_images")
        resolved = resolve_blueprint("", "", len(parsed.scenes))
        final_scenes = []
        for i, scene_data in enumerate(parsed.scenes):
            mech = resolved[i]
            final_scenes.append(Scene(
                scene=scene_data.scene,
                text=scene_data.text,
                image_prompt=scene_data.image_prompt,
                highlight_text=scene_data.highlight_text,
                emotion=mech['emotion'],
                sfx=mech['sfx'],
                transition=mech['transition'],
                speech_rate_modifier=mech['speech_rate_modifier'],
                visual_effect=mech['visual_effect']
            ))
        result = [scene.model_dump() for scene in final_scenes]
        cache.set("gen_script_imgs", result, topic=topic, num_images=num_images, paths=paths_hash, prompt_rev=IMAGE_PROMPT_REVISION)
        return result

    return await asyncio.to_thread(_retry_sync, _call, key_manager=gemini_keys)


# ---------------------------------------------------------------------------
# 5. MODE: Script → Video — User paste script, Gemini chia cảnh + sinh image_prompt
# ---------------------------------------------------------------------------
def build_split_system_prompt(
    *,
    num_scenes: int,
    art_style: str = "Cinematic",
    prefer_stock_video: bool = False,
) -> str:
    """system_instruction cho `split_script_to_scenes` — hàm THUẦN, không gọi mạng.

    Tách ra khỏi thân hàm async vì cùng lý do đã tách build_script_system_prompt(): prompt
    nằm trong closure `_call()` thì không test nào chạm nổi, và đây chính là đường sinh kịch
    bản có yêu cầu KHẮT KHE NHẤT (giữ nguyên văn 100% lời của người dùng) — hỏng ở đây là
    sửa lời người ta mà không ai biết.
    """
    return (
        "Bạn là biên kịch video chuyên nghiệp. "
        "Người dùng cung cấp 1 đoạn văn bản/kịch bản viết sẵn. "
        f"Nhiệm vụ: chia nội dung thành CHÍNH XÁC {num_scenes} phân cảnh để làm video. "
        "QUY TẮC CỰC KỲ QUAN TRỌNG VÀ BẮT BUỘC (GIỮ NGUYÊN 100% Ý NGƯỜI DÙNG): "
        "1. Nếu kịch bản gốc có phân biệt rõ các phần (như 'Voice-over:', 'Lời thoại:', 'Chuyển động:', 'Text on-screen:'), "
        "BẮT BUỘC CHỈ TRÍCH XUẤT phần Voice-over/Lời thoại vào trường `text` để hệ thống TTS đọc. "
        "TUYỆT ĐỐI giữ đúng nguyên văn 100% từng từ ngữ của lời thoại, KHÔNG ĐƯỢC tự ý sửa đổi, paraphrase hay thêm bớt. "
        "2. Sử dụng các chỉ dẫn đạo diễn (Chuyển động, Hình ảnh) để dịch chuẩn xác 100% sang tiếng Anh thành `image_prompt`. "
        "KHÔNG được tự phóng tác thêm chi tiết hình ảnh mà người dùng không yêu cầu. "
        "3. Nếu kịch bản chỉ là văn xuôi bình thường, hãy chia mỗi cảnh 1-3 câu liên tiếp và giữ nguyên văn nhiều nhất có thể. "
        "Chia sao cho số từ giữa các cảnh xấp xỉ bằng nhau, để nhịp đổi cảnh của video đều đặn. "
        "4. Tuyệt đối không đưa chỉ dẫn đạo diễn vào trường `text`. "
        "5. Nếu một cảnh có nhãn 'Text on-screen:' (hoặc 'Chữ trên màn hình:'), BẮT BUỘC đưa nguyên văn "
        "phần đó vào trường `highlight_text` (viết HOA, tối đa 3 từ) và KHÔNG đưa vào `text`. "
        "Nếu nhãn đó để trống hoặc không có, để `highlight_text` rỗng — KHÔNG tự bịa từ giật tít. "
        "6. Nếu kịch bản có dòng 'BGM:' hoặc 'CTA:' (thường ở cuối), đó là chỉ dẫn cho hệ thống, "
        "KHÔNG phải lời thoại: đưa vào `recommended_bgm` và `cta_text`, và TUYỆT ĐỐI không để lẫn "
        "vào `text` của cảnh cuối. "
        f"image_prompt: luôn mô tả bằng tiếng Anh theo phong cách '{art_style}' nhưng phải "
        "trung thành tuyệt đối với mô tả của người dùng."
        # Cùng lý do như generate_script: nếu video sẽ dựng bằng footage stock thì
        # image_prompt chính là câu truy vấn tìm video, nên không được chứa thuật ngữ
        # máy quay/render.
        f"\n\n{IMAGE_PROMPT_RULES_STOCK if prefer_stock_video else IMAGE_PROMPT_RULES_AI}"
    )


async def split_script_to_scenes(
    script_text: str,
    num_scenes: int = 6,
    art_style: str = "Cinematic",
    api_key: Optional[str] = None,
    narration_tone: str = "viral",
    content_niche: Optional[str] = None,
    prefer_stock_video: bool = False,
) -> dict:
    """
    Nhận đoạn văn dài (script viết sẵn bởi user).
    Gemini chia thành N scenes hợp lý + sinh image_prompt cho mỗi scene.

    Lời thoại LUÔN được giữ nguyên văn 100%; narration_tone/content_niche CHỈ dùng để
    chọn hiệu ứng (sfx, transition, emotion, nhịp đọc) — xem effect_guide bên dưới.
    """
    # Trần 30 khớp MAX_SCENES của generate_script và slider của Frontend (max 30).
    # LỖI CŨ: trần cứng 20 ở đây trong khi FE cho kéo tới 30 → user chọn 26 cảnh thì bị
    # âm thầm hạ xuống 20, mỗi cảnh phải gánh gấp rưỡi số từ (~13 giây/cảnh với kịch bản
    # 800 từ) mà không có cảnh báo nào.
    num_scenes = max(MIN_SCENES, min(MAX_SCENES, num_scenes))

    system_prompt = build_split_system_prompt(
        num_scenes=num_scenes,
        art_style=art_style,
        prefer_stock_video=prefer_stock_video,
    )

    # Bản vẽ cơ học được xử lý phía Python, không tiêm vào Prompt nữa
    def _call():
        # Trim script_text for hashing to avoid too long string issue, or hash it inside _get_key
        cached_result = cache.get("split_script", script_len=len(script_text), text_hash=hashlib.md5(script_text.encode("utf-8")).hexdigest(), num_scenes=num_scenes, art_style=art_style, tone=narration_tone, niche=content_niche or "", stock=prefer_stock_video, prompt_rev=SPLIT_PROMPT_REVISION)
        if cached_result:
            logger.info("Using cached result for split_script_to_scenes")
            return cached_result

        client = _get_client(api_key)
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=f"Kịch bản cần chia cảnh:\n\n{script_text}",
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=LLMScriptResponse,
                temperature=0.1,  # Cực kỳ thấp để AI bám sát 100% text gốc, không phóng tác
            ),
        )
        _track_quota()
        parsed: LLMScriptResponse = _require_parsed(response, "split_script_to_scenes")
        resolved = resolve_blueprint(content_niche, narration_tone, len(parsed.scenes))
        final_scenes = []
        for i, scene_data in enumerate(parsed.scenes):
            mech = resolved[i]
            final_scenes.append(Scene(
                scene=scene_data.scene,
                text=scene_data.text,
                image_prompt=scene_data.image_prompt,
                highlight_text=scene_data.highlight_text,
                emotion=mech['emotion'],
                sfx=mech['sfx'],
                transition=mech['transition'],
                speech_rate_modifier=mech['speech_rate_modifier'],
                visual_effect=mech['visual_effect']
            ))
            
        est_duration = _estimate_script_duration(final_scenes)
        final_result = ScriptResponse(
            estimated_duration_s=round(est_duration, 1),
            sentiment=parsed.sentiment,
            recommended_bgm=parsed.recommended_bgm,
            hook_text=parsed.hook_text,
            hook_quote=parsed.hook_quote,
            cta_text=parsed.cta_text,
            scenes=final_scenes
        )
        
        result = final_result.model_dump()
        cache.set("split_script", result, script_len=len(script_text), text_hash=hashlib.md5(script_text.encode("utf-8")).hexdigest(), num_scenes=num_scenes, art_style=art_style, tone=narration_tone, niche=content_niche or "", stock=prefer_stock_video, prompt_rev=SPLIT_PROMPT_REVISION)
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
    negative_prompt: str = "",
    seed: Optional[int] = None
) -> str:
    """
    Sinh 1 ảnh từ image_prompt bằng gemini-3.1-flash-image, lưu vào output_path (.png/.jpg).
    Trả về output_path khi thành công.

    Lưu ý: nếu lỗi (hết quota, key sai, prompt bị filter an toàn chặn...),
    hàm sẽ raise Exception để main.py có thể fallback sang ảnh placeholder hoặc Pollinations,
    tránh làm chết toàn bộ pipeline.
    """
    # Tự động gộp Negative Prompt Nâng cao
    base_neg = NEGATIVE_PROMPT_TEMPLATES.get("default", "")
    if "cinematic" in image_prompt.lower():
        base_neg = NEGATIVE_PROMPT_TEMPLATES.get("cinematic", "")
    elif "3d" in image_prompt.lower() or "animation" in image_prompt.lower():
        base_neg = NEGATIVE_PROMPT_TEMPLATES.get("3d_animation", "")
    negative_prompt = f"{base_neg}, {negative_prompt}".strip(", ")

    def _call():
        client = _get_client(api_key)
        
        # Tạo prompt tối ưu cho gemini-3.1-flash-image
        prompt_with_config = image_prompt
        if aspect_ratio:
            prompt_with_config += f", aspect ratio {aspect_ratio}"
        if negative_prompt:
            prompt_with_config += f", avoid: {negative_prompt}"
            
        result = client.models.generate_content(
            model="gemini-3.1-flash-image",
            contents=prompt_with_config,
        )
        
        image_bytes = None
        for candidate in result.candidates:
            if candidate.content and candidate.content.parts:
                for part in candidate.content.parts:
                    if getattr(part, "inline_data", None) is not None:
                        image_bytes = part.inline_data.data
                        break
                    if hasattr(part, "image_bytes") and part.image_bytes:
                        image_bytes = part.image_bytes
                        break
                if image_bytes:
                    break
                    
        if not image_bytes:
            raise RuntimeError("Gemini không trả về dữ liệu ảnh nào.")

        with open(output_path, "wb") as f:
            f.write(image_bytes)
        return output_path

    return await asyncio.to_thread(_retry_sync, _call, key_manager=gemini_keys, retries=1)

# ── TRÍCH TỪ KHOÁ TÌM FOOTAGE ───────────────────────────────────────
# Từ thông dụng + THUẬT NGỮ GÓC MÁY/quay phim không mang nội dung chủ thể.
STOCK_STOPWORDS = {
    # common
    "a", "an", "the", "and", "or", "of", "is", "are", "his", "her", "its", "their",
    # chất lượng / render
    "cinematic", "style", "lighting", "photo", "image", "picture", "realistic",
    "photorealistic", "4k", "8k", "uhd", "hdr", "detailed", "highly", "quality",
    "unreal", "engine", "octane", "render", "volumetric", "dust", "film", "grain",
    "teal", "orange", "dramatic", "moody", "epic", "professional",
    # Đo trên kịch bản thật: Gemini hay chốt image_prompt bằng "stock footage style".
    # Không lọc thì query gửi Pexels là "stock footage" — tức đi tìm video về CHÍNH KHÁI
    # NIỆM video stock, trả về đủ thứ ngẫu nhiên.
    "stock", "footage", "shot's", "breath-taking", "breathtaking", "serene", "feeling",
    # góc máy / camera jargon
    "shot", "close-up", "closeup", "close", "up", "extreme", "wide", "medium",
    "full", "establishing", "low-angle", "high-angle", "angle", "low", "high",
    "drone", "aerial", "over-the-shoulder", "over", "shoulder", "tracking",
    "dolly", "pan", "panning", "zoom", "pov", "macro", "portrait", "landscape",
    "view", "scene", "frame", "camera", "lens", "depth", "field", "bokeh",
}

# Giới từ MỞ RA MỆNH ĐỀ BỐI CẢNH: chủ thể luôn nằm TRƯỚC chúng.
# "a vintage leather book lying ON a dark wooden table NEAR a warm lantern"
#                                ^ cắt ở đây, phần sau chỉ là bối cảnh phụ.
_BACKGROUND_PREPS = {
    "in", "on", "at", "under", "near", "beside", "behind", "next", "against", "among",
    "amid", "amidst", "through", "throughout", "across", "onto", "inside", "outside",
    "atop", "below", "beneath", "underneath", "above", "during", "while", "from", "by",
    "towards", "toward", "around", "to", "between", "beyond", "within", "opposite",
    "before", "after", "past",
}

# Giới từ CHÈN GIỮA cụm động từ — bỏ chính nó nhưng GIỮ tân ngữ đằng sau:
# "hands digging INTO soft soil" → "digging soft soil" (không được cắt mất "soil").
_FILLER_PREPS = {"into", "for", "with", "about", "along"}


def stock_query_from_prompt(image_prompt: str) -> str:
    """Từ khoá tìm footage, trích OFFLINE từ image_prompt (không tốn quota Gemini).

    THUẬT TOÁN CŨ SAI Ở ĐÂU: nó lọc stopword rồi lấy **3 từ ĐẦU**. Nhưng tiếng Anh đặt
    danh từ chính ở CUỐI cụm danh từ, nên 3 từ đầu thường chỉ là chuỗi tính từ. Đo trên
    13 image_prompt Gemini thật thì 4 trong số đó MẤT HẲN chủ thể:

        "a vintage closed leather book lying on a dark wooden table"
            cũ  → "vintage closed leather"   (không còn chữ "book"!)
        "hands cleaning delicate crystal glasses in a rustic shop"
            cũ  → "hands cleaning delicate"  (mất "crystal glasses")
        "close up of hands digging into soft soil under an old tree"
            cũ  → "hands digging into"       (kết bằng giới từ, mất "soil")
        "a lonely person looking up at the starry night sky"
            cũ  → "lonely person looking"    (looking cái gì?)

    Đây là lý do footage "hơi đúng mà không đúng chủ đề".

    BỐN BƯỚC MỚI:
      1. Bỏ tiền tố góc máy ("Extreme close-up shot of ...").
      2. CẮT ở giới từ mở mệnh đề bối cảnh — giữ lại đúng cụm chủ thể.
      3. Bỏ phân từ/giới từ LỦNG LẲNG ở cuối ("looking", "lying", "stretching") khi còn
         đủ từ mang nghĩa — chúng mất tân ngữ nên chỉ làm loãng truy vấn.
      4. Lấy 3 từ CUỐI của cụm (head-final), tức luôn giữ được danh từ chính.
    """
    lower_prompt = (image_prompt or "").lower()

    # (1) Ưu tiên phần SAU cụm " of " đầu tiên: "Extreme close-up shot of a lion roaring..."
    # → chủ thể thật nằm sau "of". Chỉ áp dụng khi phần đầu đúng là cụm góc máy.
    if " of " in lower_prompt:
        prefix, _, subject_part = lower_prompt.partition(" of ")
        prefix_words = [w.strip(",.!?") for w in prefix.split()]
        if prefix_words and all(w in STOCK_STOPWORDS for w in prefix_words):
            lower_prompt = subject_part

    clean = re.sub(r"[,.!?;:]", " ", lower_prompt)
    words = [w for w in clean.split() if w]

    # (2) Cắt ở giới từ bối cảnh đầu tiên (bỏ qua vị trí 0 để không cắt sạch câu).
    for i, w in enumerate(words):
        if i > 0 and w in _BACKGROUND_PREPS:
            words = words[:i]
            break

    core = [w for w in words if w not in STOCK_STOPWORDS and w not in _FILLER_PREPS]

    # (3) Gọt phân từ/giới từ lủng lẳng ở cuối. Giữ tối thiểu 2 từ: với cụm ngắn như
    # "hooded figure walking" thì hành động chính là thứ đáng tìm.
    while len(core) > 2 and (core[-1].endswith("ing") or core[-1] in _BACKGROUND_PREPS):
        core.pop()

    # (4) Head-final: 3 từ CUỐI mới là chủ thể + phẩm chất sát nó nhất.
    if core:
        return " ".join(core[-3:])
    return "nature"


def build_stock_queries(image_prompt: str) -> List[str]:
    """BẬC THANG truy vấn, từ cụ thể nhất tới rộng nhất.

    Trước đây chỉ có ĐÚNG MỘT truy vấn: Pexels trả 0 kết quả là rơi thẳng về ảnh AI, dù
    chỉ cần bỏ một tính từ là tìm thấy. Bậc thang giữ được chế độ footage thật thay vì
    âm thầm đổi nguồn hình giữa video (khiến vài cảnh là video, vài cảnh là ảnh tĩnh).
    """
    full = stock_query_from_prompt(image_prompt)
    tu = full.split()
    ladder = [full]
    if len(tu) >= 3:
        ladder.append(" ".join(tu[-2:]))
    if len(tu) >= 2:
        ladder.append(tu[-1])  # chỉ còn danh từ chính
    # Bỏ trùng, giữ nguyên thứ tự
    thay = set()
    return [q for q in ladder if q and not (q in thay or thay.add(q))]


async def extract_search_keyword(image_prompt: str, api_key: Optional[str] = None) -> str:
    """Giữ nguyên chữ ký async cũ cho các chỗ đang gọi. Lõi là `stock_query_from_prompt`."""
    return stock_query_from_prompt(image_prompt)
