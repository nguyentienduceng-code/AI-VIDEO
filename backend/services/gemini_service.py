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


# ---------------------------------------------------------------------------
# 1. Định nghĩa Schema bằng Pydantic — đây chính là "Structured Output".
#    Gemini sẽ bị BẮT phải trả JSON khớp 100% với schema này.
# ---------------------------------------------------------------------------
class LLMScene(BaseModel):
    scene: int
    text: str = Field(description="Lời thoại đọc voice-over. Không chứa ngoặc đơn hoặc ký hiệu. Nếu scene_type là quote_card, trường này PHẢI rỗng.")
    image_prompt: str = Field(description="Prompt bằng tiếng Anh chi tiết để AI sinh ảnh (dùng các từ khóa điện ảnh như 8k, photorealistic). Bắt buộc phải có.")
    highlight_text: str = Field(description="Từ khóa quan trọng nhất trong cảnh (tối đa 1-3 từ).")
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
    hook_text: str = Field(default="", description="Tiêu đề giật gân, cực ngắn (dưới 10 chữ) hiển thị to ở đầu video.")
    hook_variants: List[str] = Field(default_factory=list, description="3 biến thể hook_text khác nhau để người dùng lựa chọn (A/B testing).")
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

EMOTION_VISUAL_COUPLING = {
    "hook": "image_style: dramatic, high contrast, bold composition | visual_effect: zoom_in_fast, high energy | color_mood: warm tones, saturated, attention-grabbing | lighting: rim light, dramatic shadows",
    "calm": "image_style: peaceful, soft, natural | visual_effect: slow pan, gentle zoom | color_mood: cool tones, pastel, soothing | lighting: soft diffused, golden hour",
    "dramatic": "image_style: cinematic, moody, intense | visual_effect: slow_motion, dramatic_angle | color_mood: desaturated, high contrast, cinematic | lighting: chiaroscuro, single source",
    "excited": "image_style: vibrant, dynamic, energetic | visual_effect: fast cuts, multiple angles | color_mood: bright, saturated, warm | lighting: bright, colorful, high energy"
}

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
PROMPT_REVISION = "2026-07-26-sprint1"

# Cùng vai trò cho split_script_to_scenes. Tách riêng để sửa prompt chia cảnh không xoá
# oan cache của generate_script (và ngược lại). LỖI CŨ: cache key của "split_script" hoàn
# toàn không có trường revision, nên mọi lần sửa prompt đều bị cache cũ đè — sửa xong
# không thấy gì thay đổi.
SPLIT_PROMPT_REVISION = "2026-07-26-niche-effects"

# Cùng vai trò cho generate_script_from_images. Trước đây cache key của nó KHÔNG có
# trường revision — sửa prompt xong vẫn nhận lại kịch bản cũ từ cache, y hệt lỗi của
# split_script mô tả ở trên.
IMAGE_PROMPT_REVISION = "2026-07-26-scene-word-budget"

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

# Trần số cảnh. Nâng 20 → 30 vì video dài (từ 180s) bị trần 20 ép mỗi cảnh phải gánh
# 25-40 từ, tức 8-13 giây/cảnh — chậm lê thê dù prompt có nói gì đi nữa.
MAX_SCENES = 30
MIN_SCENES = 4

DURATION_CONFIG = {
    "15s":  {"words": "30-40"},
    "30s":  {"words": "70-80"},
    "60s":  {"words": "140-160"},
    "90s":  {"words": "210-240"},
    "120s": {"words": "280-320"},
    "180s": {"words": "420-480"},
    "240s": {"words": "560-640"},   # Long-form kể chuyện
    "300s": {"words": "700-800"},   # Long-form kể chuyện
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
NARRATION_TONE_PROMPTS = {
    "drama": "Tone: Đanh thép, kịch tính, dồn dập. Dùng từ ngữ mạnh, hơi hướng giật gân, tạo ra cảm giác bí ẩn, đe doạ hoặc bất ngờ tột độ. Không dùng từ thừa.",
    "educational": "Tone: Cuốn hút, khai mở trí óc. Giống như một bí mật vừa được bật mí, tiết lộ sự thật gây shock nhưng vẫn đáng tin cậy. Dùng số liệu để đè bẹp sự nghi ngờ.",
    "humorous": "Tone: Cà khịa, châm biếm, hài hước sâu cay. Chơi chữ, dùng từ ngữ trending của Gen Z hoặc văn phong 'troll' nhẹ nhàng nhưng thâm thúy.",
    "inspirational": "Tone: Cảm xúc, hùng hồn, truyền động lực mãnh liệt. Đánh vào trái tim người nghe, dùng từ ngữ khơi gợi khát vọng và vượt qua giới hạn.",
    "storytelling": "Tone: Trầm lắng, chiêm nghiệm, dẫn chuyện như một người kể chuyện tài hoa. Giọng văn điện ảnh, giàu cảm xúc nhưng KHÔNG lên gân. Mỗi cảnh kết bằng một câu tạo tò mò nhẹ (soft cliffhanger) để người xem muốn nghe tiếp.",
}


# ── PALETTE HIỆU ỨNG THEO TONE ──────────────────────────────────────
# Chỉ dẫn cho AI chọn transition/sfx/nhịp ĐÚNG CHẤT từng thể loại (đồng bộ với
# .agents/skills/content-cinematic/references/content-frameworks.md).
# Nhờ vậy "hiệu ứng đi kèm" tự khớp niche thay vì mặc định crossfade toàn bộ.
TONE_EFFECT_PALETTES = {
    "viral": (
        "PALETTE HIỆU ỨNG (viral): transition chủ đạo 'whip_pan'/'zoom_punch' ở các cú chuyển dồn dập, "
        "'fade_white' cho khoảnh khắc bất ngờ, 'crossfade' cho đoạn nối thường. "
        "sfx: hook dùng 'riser', twist dùng 'bass_drop' hoặc 'impact', chốt dùng 'ding'. "
        "speech_rate_modifier: hook '+15%', thân '0%', climax '+10%'."
    ),
    "storytelling": (
        "PALETTE HIỆU ỨNG (kể chuyện): transition chủ đạo 'crossfade' và 'fade_black' (chuyển đoạn), "
        "'page_flip' khi sang chương/bước ngoặt mới (hợp review sách), 'droplet' cho khoảnh khắc cảm xúc/kết. "
        "sfx: ĐỂ TRỐNG hầu hết cảnh; chỉ 'riser' hoặc 'suspense' ở đúng 1-2 điểm cao trào, 'shimmer' ở khoảnh khắc nhận ra. "
        "speech_rate_modifier: mở '+5%', thân '0%' hoặc '-5%', cao trào '-3%' (chậm để nhấn)."
    ),
    "educational": (
        "PALETTE HIỆU ỨNG (giáo dục/tài chính): transition 'slide_left'/'slide_right' khi liệt kê ý, "
        "'zoom_punch' khi nêu CON SỐ gây sốc, 'wipe_right' khi so sánh 2 vế, 'crossfade' mặc định. "
        "sfx: 'tick' khi liệt kê, 'bass_drop' khi chốt con số quan trọng, 'ding' ở kết luận. "
        "speech_rate_modifier: hook '+10%', giải thích '0%', số liệu '-3%'."
    ),
    "emotional": (
        "PALETTE HIỆU ỨNG (cảm xúc/tâm lý): transition 'crossfade' chậm rãi chủ đạo, 'droplet' ở khoảnh khắc chạm, "
        "'fade_black' khi lắng đọng. TRÁNH whip_pan/zoom_punch (phá cảm xúc). "
        "sfx: gần như KHÔNG dùng; tối đa 'shimmer' 1 lần ở insight, 'heartbeat' nếu hồi hộp nội tâm. "
        "speech_rate_modifier: toàn bài '-5%', câu đắt nhất '-8%'."
    ),
    "humorous": (
        "PALETTE HIỆU ỨNG (hài hước): transition 'zoom_punch'/'whip_pan' cho cú bẻ lái, 'slide_up' cho ý mới. "
        "sfx: 'pop' cho tình huống ngộ nghĩnh, 'laugh' SAU cú đấm hài (dùng tiết chế 1-2 lần), 'ding' cho chốt. "
        "speech_rate_modifier: setup '0%', punchline '+10%'."
    ),
}


# ── PALETTE + BLUEPRINT THEO NICHE (chính xác hơn tone) ─────────────
# Khi FE truyền content_niche, dùng palette + bản vẽ vị trí riêng của niche đó
# (đồng bộ .agents/skills/content-cinematic/references/scene-blueprints.md).
# "N" = tổng số cảnh; các mốc % được AI tự quy ra vị trí cảnh.
NICHE_BLUEPRINTS = {
    "book": (
        "NICHE: REVIEW/KỂ CHUYỆN SÁCH-PHIM.\n"
        "BẢN VẼ VỊ TRÍ (bắt buộc bám theo): Cảnh 1 = Lời giới thiệu/dẫn đề cuốn hút (VÍ DỤ: 'Hôm nay chúng ta cùng khám phá...'). "
        "TUYỆT ĐỐI KHÔNG mô tả bìa sách ở Cảnh 1 nữa, vì 3.5 giây đầu video đã được hệ thống chèn hiệu ứng Máy Xèng (Slot Machine) hiển thị bìa rồi. "
        "Hãy tập trung mô tả hình ảnh tác giả, bối cảnh hoặc hình tượng nội dung cho image_prompt của Cảnh 1. "
        "~15% đầu = bối cảnh nhân vật (calm, crossfade). "
        "Giữa = mỗi cảnh 1 nút thắt kết bằng soft cliffhanger; dùng 'page_flip' khi sang chương mới. "
        "~45% = MINI-TWIST giữ chân (suspense, sfx 'suspense', 'fade_black'). "
        "~80% = CAO TRÀO tiết lộ lớn nhất (sfx 'riser' ngay trước, transition 'zoom_punch' hoặc 'fade_white', rate '-3%'). "
        "Sau cao trào = dư âm (sfx 'shimmer' 1 lần lúc ngộ ra, transition 'droplet'). "
        "Cảnh cuối = BẮT BUỘC phải là KẾT BÀI (tổng kết bài học hoặc kêu gọi hành động - Call to Action) để video không bị cụt (closing, 'fade_black', rate '-5%'). SFX để trống mọi cảnh còn lại."
    ),
    "finance": (
        "NICHE: TÀI CHÍNH/LÀM GIÀU/KINH DOANH.\n"
        "BẮT BUỘC mỗi cảnh có CON SỐ/tỉ lệ/mốc thời gian cụ thể. "
        "BẢN VẼ: Cảnh 1 = nghịch lý tiền + con số sốc (sfx 'riser', 'whip_pan', rate '+15%'). "
        "Kế = đào sâu nỗi đau ('slide_left'). Giữa = cơ chế từng ý ('slide_right'/'wipe_right' khi so sánh, sfx 'tick' khi liệt kê). "
        "Con số chốt = sfx 'bass_drop' + 'zoom_punch' (rate '-3%'). Nguyên tắc vàng = sfx 'impact' + 'fade_white'. "
        "Kết = hành động cụ thể + CTA (sfx 'ding', 'fade_black')."
    ),
    "history": (
        "NICHE: LỊCH SỬ/BÍ ẨN.\n"
        "BẢN VẼ: Cảnh 1 = bí ẩn mở màn kiểu 'suốt X năm...' (sfx 'suspense', 'fade_black'). "
        "~25% đầu = dựng bối cảnh (calm, crossfade). Giữa = chuỗi manh mối, mỗi cảnh 1 manh mối + câu hỏi "
        "(suspense, sfx 'heartbeat' đúng 1 lần giữa chuỗi). ~70% = manh mối LẬT NGƯỢC ('wipe_down'). "
        "~85% = TIẾT LỘ sự thật (sfx 'impact', 'zoom_punch'). Kết = ý nghĩa hiện tại + câu hỏi mở ('droplet' rồi 'fade_black', rate '-5%')."
    ),
    "psychology": (
        "NICHE: TÂM LÝ/SELF-HELP.\n"
        "BẢN VẼ: Cảnh 1 = insight khoét nỗi đau thầm kín (KHÔNG sfx). Kế = đồng cảm 'không phải vì bạn lười...' (rate '-5%'). "
        "Giữa = giải thích hiện tượng CÓ TÊN GỌI (hiệu ứng X). ~70% = khoảnh khắc NGỘ RA (sfx 'shimmer', transition 'droplet', rate '-8%'). "
        "Kế = 1 hành động nhỏ áp dụng được ngay. Kết = câu hỏi tự vấn (closing, 'fade_black'). "
        "TRÁNH whip_pan/zoom_punch; transition chủ đạo 'crossfade' chậm."
    ),
    "truecrime": (
        "NICHE: TRUE CRIME/VỤ ÁN (nếu vụ án có thật: KHÔNG bịa chi tiết, không nêu tên chưa xác thực).\n"
        "BẢN VẼ: Cảnh 1 = hiện trường/biến mất + 1 chi tiết rùng mình (sfx 'heartbeat', 'fade_black'). "
        "Kế = dòng thời gian (suspense, crossfade). Giữa = nghi vấn → manh mối (sfx 'suspense'). "
        "~70% = manh mối LẬT NGƯỢC (sfx 'bass_drop', 'whip_pan'). ~85% = sự thật (sfx 'impact', 'zoom_punch'). "
        "Kết = kết cục + suy ngẫm ('droplet', rate '-5%')."
    ),
    "travel": (
        "NICHE: DU LỊCH/KHÁM PHÁ.\n"
        "BẢN VẼ: Cảnh 1 = teaser cảnh đẹp nhất + lời thách 'nơi này...' (sfx 'swoosh_soft', 'slide_up', rate '+10%'). "
        "Kế = đường đến/không khí ('wipe_right'). Giữa = điểm độc nhất (sfx 'pop', 'zoom_through') "
        "+ chi tiết GIÁC QUAN mùi/vị/âm thanh (sfx 'shimmer', crossfade, rate '-3%'). "
        "Kết = chốt + rủ đi/tag bạn (sfx 'ding', 'fade_black')."
    ),
    "art_masterpiece": (
        "NICHE: TRANH & TÁC PHẨM NGHỆ THUẬT KINH ĐIỂN.\n"
        "BẢN VẼ: Cảnh 1 = zoom cận cảnh chi tiết ẩn/bí ẩn nhất của bức tranh (sfx 'riser', 'zoom_through', rate '+5%'). "
        "Kế = bối cảnh ra đời & tâm kịch họa sĩ (calm, crossfade). "
        "Giữa = giải mã kỹ thuật vẽ, ánh sáng chiaroscuro hoặc ẩn dụ (sfx 'shimmer' khi có phát hiện đắt giá). "
        "~70% = MINI-TWIST bí ẩn ít ai biết về tác phẩm (sfx 'suspense', 'page_flip'). "
        "~85% = CAO TRÀO giá trị thời đại & triết lý sống (sfx 'impact', 'zoom_punch', rate '-5%'). "
        "Kết = dư âm chiêm nghiệm + câu hỏi mở bình luận ('droplet', 'fade_black')."
    ),
    "poetry_literature": (
        "NICHE: THƠ CA & VĂN HỌC NGHỆ THUẬT.\n"
        "BẮT BUỘC nhịp đọc chậm rãi (-8% đến -12%), ngắt nghỉ sâu lắng giữa các vần thơ.\n"
        "BẢN VẼ: Cảnh 1 = 2-4 câu thơ đắt giá nhất hiển thị quote mờ nghệ thuật (sfx 'shimmer', 'crossfade', rate '-10%'). "
        "Kế = gợi mở hoàn cảnh sáng tác & hồn thơ (calm, crossfade). "
        "Giữa = bình giải từng hình tượng thơ, nét vẽ ngôn từ (crossfade chậm). "
        "~75% = ĐIỂM CHẠM CẢM XÚC lớn nhất của bài thơ (sfx 'droplet', rate '-12%'). "
        "Kết = dư âm thi ca + lời nhắn chiêm nghiệm cuộc sống (closing, 'fade_black')."
    ),
    "architecture_wonders": (
        "NICHE: CÔNG TRÌNH & KỲ QUAN KIẾN TRÚC.\n"
        "BẢN VẼ: Cảnh 1 = con số kỷ lục hoặc mật mã kỹ thuật kỳ lạ (VD: '2.3 triệu khối đá không 1 giọt vữa...') (sfx 'riser', 'whip_pan', rate '+10%'). "
        "Kế = bối cảnh lịch sử & tham vọng triều đại ('slide_left'). "
        "Giữa = kỳ tích kỹ thuật, vật liệu độc đáo, kết cấu chịu lực (sfx 'tick' khi liệt kê số liệu). "
        "~70% = NGUY CƠ/THÁCH THỨC suýt làm sụp đổ công trình (sfx 'suspense', 'zoom_punch'). "
        "~85% = CAO TRÀO sự trường tồn qua hàng thế kỷ (sfx 'bass_drop', 'fade_white', rate '-5%'). "
        "Kết = di sản thế giới + kêu gọi ghé thăm/bình luận ('ding', 'fade_black')."
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
    "- LỖI CHẾT NGƯỜI: {SCENE_WORD_RULE} Nếu câu dài, BẮT BUỘC tách thành nhiều cảnh liên tiếp để video đổi cảnh liên tục.\n"
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
) -> List[dict]:
    """
    Gọi Gemini để sinh N phân cảnh từ 1 chủ đề (topic).
    Hỗ trợ mode: storyteller, quiz_listicle.
    Trả về list[dict] đã được validate đúng schema Scene.
    """
    num_scenes = max(MIN_SCENES, min(MAX_SCENES, num_scenes))

    # Ngân sách từ MỖI CẢNH suy ra từ (tổng số từ của thời lượng ÷ số cảnh thực tế).
    # Con số này thay cho luật cứng "15-20 từ" trước đây — xem scene_word_budget().
    _w_lo, _w_hi = scene_word_budget(target_duration, num_scenes)
    # Lấy tốc độ ĐÃ HỌC thay vì hằng số: nói với Gemini "12 từ ≈ 4 giây" trong khi giọng
    # thật đọc 2.7 từ/giây (≈4.4 giây) là tự đẩy kịch bản lố ngay từ khâu sinh chữ.
    _wps = _default_wps()
    _sec_lo = _w_lo / (_wps + 0.2)
    _sec_hi = _w_hi / max(0.5, _wps - 0.4)
    scene_word_rule = (
        f"Mỗi phân cảnh tuyệt đối KHÔNG ĐƯỢC VƯỢT QUÁ {_w_hi} từ "
        f"(lý tưởng {_w_lo}-{_w_hi} từ, tương đương {_sec_lo:.1f}-{_sec_hi:.1f} giây đọc)."
    )

    # ── Master Storyteller Base Prompt ──
    base_storyteller = (
        "Bạn là đạo diễn và biên kịch video ngắn HÀNG ĐẦU thế giới, chuyên tạo nội dung Triệu View trên TikTok/Reels/Shorts.\n\n"
        "CẤU TRÚC KỂ CHUYỆN (Curiosity Gap & PAS):\n"
        "1. HOOK (Cảnh 1): Móc câu sắc bén. Phải tạo ra một 'Curiosity Gap' (Lỗ hổng tò mò). Nếu xem xong cảnh 1 mà khán giả không bị sốc, bạn thất bại.\n"
        "2. TENSION (Các cảnh giữa): Xoáy sâu vào vấn đề bằng các chi tiết gây sốc. Không kể lể dài dòng.\n"
        "3. CLIMAX (Cảnh áp chót): Đưa ra Sự thật bất ngờ nhất (Plot Twist) hoặc Giải pháp tột đỉnh.\n"
        "4. CTA (Cảnh cuối): Kêu gọi hành động khéo léo và tự nhiên nhất có thể.\n\n"
        "QUY TẮC CẤM KỴ (BẮT BUỘC TUÂN THỦ):\n"
        "- LỖI CHẾT NGƯỜI: Cảnh quá dài. {SCENE_WORD_RULE} Nếu câu văn dài, BẮT BUỘC phải cắt đôi thành 2-3 cảnh liên tiếp!\n"
        "- CẤM dùng các câu mở đầu sáo rỗng: 'Xin chào các bạn', 'Hôm nay mình sẽ chia sẻ', 'Cùng tìm hiểu nhé', 'Bạn có biết'.\n"
        "- CẤM nói đạo lý suông, cấm dùng từ ngữ hàn lâm. Mọi luận điểm phải đính kèm hình ảnh so sánh thực tế.\n\n"
        "QUY TẮC ĐẠO DIỄN HÌNH ẢNH (CINEMATIC CAMERA - BẮT BUỘC):\n"
        "- BẮT BUỘC mở đầu mỗi 'image_prompt' bằng các góc máy điện ảnh chuyên nghiệp. Ví dụ: 'Extreme close-up shot of...', 'Low-angle drone shot of...', 'Over-the-shoulder shot of...', 'Wide establishing shot of...'\n"
        "- BẮT BUỘC giữ TÍNH NHẤT QUÁN: Nếu có nhân vật, phải tả lặp lại chính xác ngoại hình (tuổi, giới tính, trang phục) xuyên suốt TẤT CẢ các cảnh.\n"
        "- BẮT BUỘC dùng chung 1 tông màu ánh sáng cho toàn video (VD: 'cinematic teal and orange lighting, volumetric dust').\n"
        "- Kết hợp: Góc máy + Đối tượng + Hành động + Ánh sáng + Bối cảnh + Phẩm chất nghệ thuật (8k, photorealistic, Unreal Engine 5).\n\n"
        "QUY TẮC NHỊP ĐỘ GIỌNG ĐỌC (DYNAMIC PACING):\n"
        "- Sử dụng 'speech_rate_modifier' để điều khiển nhịp điệu: Hook (nhanh dồn dập '+15%'), Giải thích (chậm rãi '-5%'), Climax (bình thường '0%').\n\n"
        "KỸ THUẬT VĂN NÓI:\n"
        "- Dùng 'bạn' trực tiếp: 'Bạn có biết...', 'Hãy tưởng tượng...'\n"
        "- Tuyệt đối giữ 1 người kể chuyện xuyên suốt. Văn phong mạch lạc, nối tiếp.\n"
        "- TUYỆT ĐỐI KHÔNG dùng từ ngữ hàn lâm, không dùng Markdown (*, #).\n\n"
        "QUY TẮC TRANSITION (bắt buộc):\n"
        "- Chuyển chủ đề/bất ngờ → 'fade_black'\n"
        "- Liên tục/kể tiếp → 'crossfade'\n"
        "- Cao trào/chi tiết → 'zoom_through'\n\n"
        "- CẤM lạm dụng SFX liên tục. Đa số các cảnh phải ĐỂ TRỐNG sfx. Chỉ dùng sfx ở Cảnh 1 (Hook) và đúng 1-2 cảnh có Plot Twist hoặc Câu chốt.\n"
    )

    # Chế độ KỂ CHUYỆN long-form (tone=storytelling): dùng base prompt riêng, style @sachhay_chondoc
    if narration_tone == "storytelling" and mode != "quiz_listicle":
        system_prompt = (
            BASE_STORYTELLING +
            f"\nNhiệm vụ: kể câu chuyện cho chủ đề được cung cấp thành CHÍNH XÁC {num_scenes} phân cảnh nối tiếp mạch lạc. "
            f"image_prompt viết bằng tiếng Anh (mô tả cảnh quay thật để tìm footage stock)."
        )
    elif mode == "quiz_listicle":
        system_prompt = (
            base_storyteller +
            f"\nCHẾ ĐỘ: Quiz/Listicle — viết kịch bản gồm CHÍNH XÁC {num_scenes} phân cảnh theo dạng 'Top N' hoặc hỏi-đáp. "
            "Mỗi cảnh là 1 fact/item hoặc 1 câu hỏi+đáp thú vị. "
            f"image_prompt viết bằng tiếng Anh, cực kỳ chi tiết. Phong cách hình ảnh và nghệ thuật bắt buộc (Art Style): '{get_enhanced_art_style(art_style)}'. "
            "BẮT BUỘC phải đồng bộ màu sắc, ánh sáng và hiệu ứng hình ảnh với cảm xúc (Emotion) của cảnh theo bảng chuẩn: "
            f"{EMOTION_VISUAL_COUPLING} "
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

    # Palette hiệu ứng (niche blueprint ưu tiên, fallback theo tone) được resolve_blueprint()
    # tính toán sau khi có scenes — không cần xử lý gì thêm ở đây.

    # ── Thêm hướng dẫn về số lượng từ dựa trên thời lượng mục tiêu ──
    dur_cfg = DURATION_CONFIG.get(target_duration)
    if dur_cfg:
        duration_guide = (
            f"Video dài ~{target_duration}. Bắt buộc: TOÀN BỘ kịch bản gộp lại "
            f"(tổng chữ của tất cả các cảnh) chỉ được dài khoảng {dur_cfg['words']} từ."
        )
        system_prompt += f"\n\nLƯU Ý QUAN TRỌNG: {duration_guide}"

    # ── Inject Character Consistency (Style Guide) ──
    if sync_characters and character_description:
        consistency_guide = (
            f"ĐỒNG NHẤT NHÂN VẬT & PHONG CÁCH:\n"
            f"BẮT BUỘC chèn ĐÚNG ĐOẠN TEXT SAU vào đầu mọi trường 'image_prompt' của tất cả các cảnh:\n"
            f"[{character_description}]\n"
            f"Điều này là bắt buộc để hệ thống vẽ ảnh (Image AI) giữ nguyên nhân vật xuyên suốt video!"
        )
        system_prompt += f"\n\n{consistency_guide}"

    # Thay token ngân sách từ (có mặt trong cả base_storyteller lẫn BASE_STORYTELLING).
    system_prompt = system_prompt.replace("{SCENE_WORD_RULE}", scene_word_rule)

    def _call():
        cached_result = cache.get("gen_script", topic=topic, num_scenes=num_scenes, mode=mode, art_style=art_style, target_duration=target_duration, narration_tone=narration_tone, niche=content_niche or "", char_desc=character_description or "", sync=sync_characters, seed=variation_seed, prompt_rev=PROMPT_REVISION)
        if cached_result:
            logger.info("Using cached result for generate_script")
            return cached_result
        client = _get_client(api_key)
        try:
            BATCH_SIZE = 12
            all_scenes = []
            global_fields = {}
            
            for batch_idx in range(0, num_scenes, BATCH_SIZE):
                current_batch_size = min(BATCH_SIZE, num_scenes - batch_idx)
                
                # Cập nhật số cảnh cho lô hiện tại
                batch_prompt = system_prompt.replace(f"CHÍNH XÁC {num_scenes} phân cảnh", f"CHÍNH XÁC {current_batch_size} phân cảnh")
                batch_prompt = batch_prompt.replace("Mỗi phân cảnh tuyệt đối", f"Bạn đang tạo Lô {batch_idx//BATCH_SIZE + 1} (Cảnh {batch_idx+1} đến {batch_idx+current_batch_size}). Mỗi phân cảnh tuyệt đối")
                
                batch_content = f"Chủ đề video: {topic}\n"
                if batch_idx > 0:
                    prev_context = "\n".join([f"Cảnh {s.scene}: {s.text}" for s in all_scenes[-2:]])
                    batch_content += f"\nNgữ cảnh 2 cảnh trước đó (chỉ để nối tiếp mạch truyện, KHÔNG sinh lại nội dung này):\n{prev_context}"
                    batch_content += f"\nTiếp tục viết từ cảnh {batch_idx+1} đến {batch_idx+current_batch_size}."
                else:
                    batch_content += "\nHãy tạo phần đầu của kịch bản."
                
                response = client.models.generate_content(
                    model="gemini-flash-latest",
                    contents=batch_content,
                    config=types.GenerateContentConfig(
                        system_instruction=batch_prompt,
                        response_mime_type="application/json",
                        response_schema=LLMScriptResponse,
                        temperature=0.9,
                    ),
                )
                try:
                    from services import quota_service
                    quota_service.increment_quota(1)
                except Exception:
                    pass
                parsed: LLMScriptResponse = response.parsed
                
                if batch_idx == 0:
                    global_fields = {
                        "sentiment": parsed.sentiment,
                        "recommended_bgm": parsed.recommended_bgm,
                        "hook_text": parsed.hook_text,
                        "hook_variants": parsed.hook_variants,
                        "cta_text": parsed.cta_text,
                    }
                
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
                cta_text=global_fields.get("cta_text", ""),
                scenes=final_scenes
            )
            result = final_result.model_dump()
            cache.set("gen_script", result, topic=topic, num_scenes=num_scenes, mode=mode, art_style=art_style, target_duration=target_duration, narration_tone=narration_tone, niche=content_niche or "", char_desc=character_description or "", sync=sync_characters, seed=variation_seed, prompt_rev=PROMPT_REVISION)
            return result
        except Exception as e:
            # KHÔNG trả kịch bản mock (trước đây trả video "Python" bất kể chủ đề, âm thầm
            # nuốt lỗi khiến user nhận nội dung sai lệch). Ném lỗi thật để pipeline báo lên UI.
            logger.error(f"Gemini generate_script thất bại cho chủ đề '{topic}': {e}")
            raise

    return await asyncio.to_thread(_retry_sync, _call, key_manager=gemini_keys)


# ---------------------------------------------------------------------------
# 3.5. AI SCRIPT REVIEWER — Kiểm soát chất lượng tự động (B2)
# ---------------------------------------------------------------------------
# Lớp QC chạy sau generate_script, trước khi trả kịch bản cho FE.
# Gọi thêm 1 lần Gemini (model flash, temperature=0.3 cho deterministic)
# nhưng chỉ với prompt ngắn + input là kịch bản đã sinh → tăng ~0.3-0.5x token.
# Với 2 API key, hệ thống tự xoay vòng nếu 1 key cạn quota.
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


def _local_review(scenes: list, word_budget_hi: int) -> ScriptReviewResult:
    """
    Review LOCAL (không tốn API): phát hiện cụm từ sáo rỗng, cảnh quá dài,
    thiếu CTA ở cảnh cuối. Nhanh và miễn phí — luôn chạy.
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
        if len(words) > word_budget_hi:
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
        last_text = (scenes[-1].get("text", "") or "").lower()
        cta_keywords = ["theo dõi", "subscribe", "chia sẻ", "bình luận", "comment",
                        "like", "thích", "đăng ký", "share", "tag"]
        has_cta = any(kw in last_text for kw in cta_keywords)
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


async def review_script(
    script_result: dict,
    word_budget_hi: int = 20,
    api_key: str | None = None,
) -> dict:
    """
    Kiểm soát chất lượng kịch bản AI sinh ra.
    Tầng 1 (local): kiểm tra cụm từ sáo rỗng, word budget, CTA — luôn chạy, miễn phí.
    Trả về dict chứa quality_score, review_notes, passed.
    """
    scenes = script_result.get("scenes", [])
    if not scenes:
        return ScriptReviewResult(quality_score=0, review_notes=[], passed=False).model_dump()

    review = _local_review(scenes, word_budget_hi)

    # Ghi log cho debugging
    if review.review_notes:
        logger.info(f"Script Review: score={review.quality_score}, issues={len(review.review_notes)}")
        for note in review.review_notes:
            logger.info(f"  [{note.severity}] Cảnh {note.scene_index}: {note.message}")

    return review.model_dump()


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

    # Ngân sách từ mỗi cảnh, suy ra từ CÙNG hằng số với generate_script để hai đường
    # sinh kịch bản không lệch nhịp đọc. Cố ý KHÔNG đặt cứng "15-20 từ": xem ghi chú
    # ở scene_word_budget() — luật cứng đó từng đá nhau với luật tổng số từ, và Gemini
    # chọn phá luật số từ, làm cảnh dài 8+ giây.
    _w_hi = WORDS_PER_SCENE_TARGET + 3
    _sec_hi = _w_hi / _default_wps()

    system_prompt = (
        "Bạn là biên kịch video chuyên nghiệp. "
        f"Người dùng cung cấp {num_images} bức ảnh.{topic_hint} "
        f"Nhiệm vụ: viết CHÍNH XÁC {num_images} phân cảnh (mỗi ảnh = 1 cảnh). "
        "Phân tích nội dung từng ảnh và viết lời bình luận tiếng Việt dưới dạng 'văn nói'. "
        "Sử dụng câu ngắn, ngắt nghỉ bằng dấu phẩy hợp lý, KHÔNG dùng các ký tự Markdown (như *, **, #). "
        "Kịch bản phải tuân theo cấu trúc: [Hook (3s đầu)] -> [Thân bài] -> [Bài học] -> [Call-to-Action kết thúc bằng câu hỏi mở]. "
        "HÃY chủ động dùng dấu chấm lửng `...` vào phần lời thoại (text) tại những vị trí cần ngắt nghỉ, tạm dừng để tạo cảm xúc sâu lắng. "
        "image_prompt: viết mô tả tiếng Anh ngắn gọn về nội dung ảnh (dùng cho metadata). "
        f"\n\nĐỘ DÀI LỜI THOẠI (BẮT BUỘC): đây là video DỌC 9:16, phụ đề chạy đè lên "
        f"khung hình nên câu dài sẽ tràn ra ngoài màn hình. Mỗi phân cảnh tuyệt đối "
        f"KHÔNG ĐƯỢC VƯỢT QUÁ {_w_hi} từ (~{_sec_hi:.1f} giây đọc). "
        "Câu dài phải CẮT thành nhiều phân cảnh ngắn. TUYỆT ĐỐI không viết đoạn văn dài."
    )

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
        try:
            from services import quota_service
            quota_service.increment_quota(1)
        except Exception:
            pass
        parsed: LLMScriptResponse = response.parsed
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
async def split_script_to_scenes(
    script_text: str,
    num_scenes: int = 6,
    art_style: str = "Cinematic",
    api_key: Optional[str] = None,
    narration_tone: str = "viral",
    content_niche: Optional[str] = None,
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

    system_prompt = (
        "Bạn là biên kịch video chuyên nghiệp. "
        f"Người dùng cung cấp 1 đoạn văn bản/kịch bản viết sẵn. "
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
        f"image_prompt: luôn mô tả bằng tiếng Anh theo phong cách '{art_style}' nhưng phải trung thành tuyệt đối với mô tả của người dùng."
    )

    # Bản vẽ cơ học được xử lý phía Python, không tiêm vào Prompt nữa
    def _call():
        # Trim script_text for hashing to avoid too long string issue, or hash it inside _get_key
        cached_result = cache.get("split_script", script_len=len(script_text), text_hash=hashlib.md5(script_text.encode("utf-8")).hexdigest(), num_scenes=num_scenes, art_style=art_style, tone=narration_tone, niche=content_niche or "", prompt_rev=SPLIT_PROMPT_REVISION)
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
        try:
            from services import quota_service
            quota_service.increment_quota(1)
        except Exception:
            pass
        
        parsed: LLMScriptResponse = response.parsed
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
            cta_text=parsed.cta_text,
            scenes=final_scenes
        )
        
        result = final_result.model_dump()
        cache.set("split_script", result, script_len=len(script_text), text_hash=hashlib.md5(script_text.encode("utf-8")).hexdigest(), num_scenes=num_scenes, art_style=art_style, tone=narration_tone, niche=content_niche or "", prompt_rev=SPLIT_PROMPT_REVISION)
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

async def extract_search_keyword(image_prompt: str, api_key: Optional[str] = None) -> str:
    """
    Trích xuất từ khóa ngắn (2-4 từ) từ image_prompt dài để tìm kiếm trên Pexels/Pixabay
    (Offline, không dùng Gemini để tiết kiệm Quota).

    Lưu ý: prompt template BẮT BUỘC mở đầu bằng góc máy ("Extreme close-up shot of...",
    "Low-angle drone shot of..."), nên phải loại bỏ toàn bộ thuật ngữ quay phim trước khi
    trích chủ thể — nếu không Pexels sẽ nhận từ khóa rác kiểu "extreme close-up" và trả
    video ngẫu nhiên không đúng chủ đề.
    """
    # Từ thông dụng + THUẬT NGỮ GÓC MÁY/quay phim không mang nội dung chủ thể
    stopwords = {
        # common
        "a", "an", "the", "in", "on", "at", "with", "and", "or", "of", "to", "for",
        "is", "are", "his", "her", "its", "their",
        # chất lượng / render
        "cinematic", "style", "lighting", "photo", "image", "picture", "realistic",
        "photorealistic", "4k", "8k", "uhd", "hdr", "detailed", "highly", "quality",
        "unreal", "engine", "octane", "render", "volumetric", "dust", "film", "grain",
        "teal", "orange", "dramatic", "moody", "epic", "professional",
        # góc máy / camera jargon
        "shot", "close-up", "closeup", "close", "up", "extreme", "wide", "medium",
        "full", "establishing", "low-angle", "high-angle", "angle", "low", "high",
        "drone", "aerial", "over-the-shoulder", "over", "shoulder", "tracking",
        "dolly", "pan", "panning", "zoom", "pov", "macro", "portrait", "landscape",
        "view", "scene", "frame", "camera", "lens", "depth", "field", "bokeh",
    }

    lower_prompt = image_prompt.lower()

    # Ưu tiên phần SAU cụm " of " đầu tiên: "Extreme close-up shot of a lion roaring..."
    # → chủ thể thật nằm sau "of". Chỉ áp dụng khi phần đầu đúng là cụm góc máy.
    if " of " in lower_prompt:
        prefix, _, subject_part = lower_prompt.partition(" of ")
        prefix_words = [w.strip(",.!?") for w in prefix.split()]
        if prefix_words and all(w in stopwords for w in prefix_words):
            lower_prompt = subject_part

    # Chuẩn hóa chuỗi, bỏ dấu câu cơ bản
    clean_prompt = lower_prompt.replace(",", " ").replace(".", " ").replace("!", " ").replace("?", " ")
    words = [w for w in clean_prompt.split() if w]

    # Lọc stopwords
    filtered_words = [w for w in words if w not in stopwords]

    # Lấy tối đa 3 từ đầu mang nghĩa (chủ thể + hành động/bối cảnh)
    if filtered_words:
        return " ".join(filtered_words[:3])
    # Fallback an toàn
    return "nature"
