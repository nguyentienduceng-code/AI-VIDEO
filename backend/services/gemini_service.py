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
    raise last_error


# ---------------------------------------------------------------------------
# 1. Định nghĩa Schema bằng Pydantic — đây chính là "Structured Output".
#    Gemini sẽ bị BẮT phải trả JSON khớp 100% với schema này.
# ---------------------------------------------------------------------------
class Scene(BaseModel):
    scene: int = Field(description="Số thứ tự phân cảnh, bắt đầu từ 1")
    text: str = Field(description="Lời thoại tiếng Việt sẽ được đọc bằng TTS. TUYỆT ĐỐI KHÔNG chèn emoji, icon, hoặc ký tự đặc biệt Unicode vào trường này. Chỉ dùng chữ cái, số, dấu câu tiêu chuẩn.")
    image_prompt: str = Field(
        description="Mô tả hình ảnh bằng tiếng Anh, dùng để sinh ảnh AI (Imagen)"
    )
    sfx: str = Field(
        default="",
        description="Hiệu ứng âm thanh tại cảnh này. CHỈ ĐƯỢC DÙNG 1 trong các giá trị: whoosh, pop, ding, riser, suspense, impact, bell, laugh. Bỏ trống nếu không cần."
    )
    visual_effect: str = Field(
        default="zoom_in",
        description="Hiệu ứng chuyển động Camera (zoom_in, zoom_out, pan_left, pan_right, none)"
    )
    emotion: str = Field(
        default="calm",
        description="Cảm xúc giọng đọc tại cảnh này: hook, calm, dramatic, excited, suspense, closing"
    )
    speech_rate_modifier: str = Field(
        default="0%",
        description="Thay đổi nhịp độ giọng đọc (Dynamic Pacing) cho cảnh này. Giá trị là chuỗi % (ví dụ: '+20%' cho đọc nhanh dồn dập, '-10%' cho đọc chậm điềm tĩnh, '0%' là bình thường). Dùng tốc độ nhanh ở Hook, chậm lại ở giải thích, và bình thường ở Climax."
    )
    highlight_text: str = Field(
        default="",
        description="B-Roll Text: Trích xuất 1-3 từ khoá ĐẮT GIÁ nhất mang tính 'Giật tít' (Clickbait) từ 'text'. Ví dụ: 'SỐC!', 'SỰ THẬT', 'ĐỪNG XEM', '99% SAI LẦM'. Các từ này sẽ đập thẳng vào mắt người xem. Bỏ trống nếu không có từ nào giật gân."
    )
    transition: str = Field(
        default="crossfade",
        description="Kiểu chuyển cảnh SAU cảnh này sang cảnh tiếp theo: crossfade, fade_black, zoom_through. Cảnh cuối dùng fade_black."
    )


class ScriptResponse(BaseModel):
    sentiment: str = Field(
        default="happy",
        description="Cảm xúc tổng thể của video (happy, sad, dramatic, suspense, chill, energetic)."
    )
    recommended_bgm: str = Field(
        default="moment_of_peace",
        description="Mã bài nhạc nền phù hợp nhất với cảm xúc kịch bản. CHỈ CHỌN 1 trong các mã sau: afro_pop, black_light_all_good_folks_main, comedy_cartoon, deep_abstract_ambient, fluffy_clouds_fugu_vibes_main_version, hype_drill, lofi_jazzy_love, moment_of_peace, music_promotion, new_age_nature, no_sleep_hiphop, rap_beat, running_night, type_beat"
    )
    hook_text: str = Field(
        default="",
        description="Tiêu đề giật gân, cực ngắn (dưới 10 chữ) hiển thị to ở đầu video để thu hút người xem (Ví dụ: 'Sự thật rùng mình...', 'Đừng xem nếu bạn...')."
    )
    cta_text: str = Field(
        default="",
        description="Câu Call To Action (Kêu gọi hành động) ở cuối video (Ví dụ: 'Comment để nhận link', 'Theo dõi ngay!')."
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
# ── Bảng cấu hình thời lượng → số từ + số cảnh đề xuất ──────────────
DURATION_CONFIG = {
    "15s":  {"words": "30-40",    "suggested_scenes": 4},
    "30s":  {"words": "70-80",    "suggested_scenes": 5},
    "60s":  {"words": "140-160",  "suggested_scenes": 7},
    "90s":  {"words": "210-240",  "suggested_scenes": 9},
    "120s": {"words": "280-320",  "suggested_scenes": 12},
    "180s": {"words": "420-480",  "suggested_scenes": 16},
    "240s": {"words": "560-640",  "suggested_scenes": 18},   # Long-form kể chuyện
    "300s": {"words": "700-800",  "suggested_scenes": 20},   # Long-form kể chuyện
}

# ── Bảng tone kể chuyện ─────────────────────────────────────────────
NARRATION_TONE_PROMPTS = {
    "drama": "Tone: Đanh thép, kịch tính, dồn dập. Dùng từ ngữ mạnh, hơi hướng giật gân, tạo ra cảm giác bí ẩn, đe doạ hoặc bất ngờ tột độ. Không dùng từ thừa.",
    "educational": "Tone: Cuốn hút, khai mở trí óc. Giống như một bí mật vừa được bật mí, tiết lộ sự thật gây shock nhưng vẫn đáng tin cậy. Dùng số liệu để đè bẹp sự nghi ngờ.",
    "humorous": "Tone: Cà khịa, châm biếm, hài hước sâu cay. Chơi chữ, dùng từ ngữ trending của Gen Z hoặc văn phong 'troll' nhẹ nhàng nhưng thâm thúy.",
    "inspirational": "Tone: Cảm xúc, hùng hồn, truyền động lực mãnh liệt. Đánh vào trái tim người nghe, dùng từ ngữ khơi gợi khát vọng và vượt qua giới hạn.",
    "storytelling": "Tone: Trầm lắng, chiêm nghiệm, dẫn chuyện như một người kể chuyện tài hoa. Giọng văn điện ảnh, giàu cảm xúc nhưng KHÔNG lên gân. Mỗi cảnh kết bằng một câu tạo tò mò nhẹ (soft cliffhanger) để người xem muốn nghe tiếp.",
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
    "QUY TẮC ÂM THANH: KHÔNG lạm dụng sfx. Để trống 'sfx' ở hầu hết cảnh, chỉ dùng 'riser' hoặc 'suspense' "
    "ở đúng 1-2 điểm cao trào.\n"
    "QUY TẮC CẢM XÚC: 'emotion' phần lớn là 'calm' hoặc 'dramatic'/'suspense' ở cao trào; 'closing' ở cảnh cuối.\n"
)

async def generate_script(
    topic: str,
    num_scenes: int = 4,
    mode: str = "storyteller",
    art_style: str = "Cinematic",
    api_key: Optional[str] = None,
    target_duration: str = "30s",
    narration_tone: str = "viral",
    character_description: Optional[str] = None,
    sync_characters: bool = False,
) -> List[dict]:
    """
    Gọi Gemini để sinh N phân cảnh từ 1 chủ đề (topic).
    Hỗ trợ mode: storyteller, quiz_listicle.
    Trả về list[dict] đã được validate đúng schema Scene.
    """
    num_scenes = max(4, min(20, num_scenes))

    # ── Master Storyteller Base Prompt ──
    base_storyteller = (
        "Bạn là đạo diễn và biên kịch video ngắn HÀNG ĐẦU thế giới, chuyên tạo nội dung Triệu View trên TikTok/Reels/Shorts.\n\n"
        "CẤU TRÚC KỂ CHUYỆN (Curiosity Gap & PAS):\n"
        "1. HOOK (Cảnh 1): Móc câu sắc bén. Phải tạo ra một 'Curiosity Gap' (Lỗ hổng tò mò). Nếu xem xong cảnh 1 mà khán giả không bị sốc, bạn thất bại.\n"
        "2. TENSION (Các cảnh giữa): Xoáy sâu vào vấn đề bằng các chi tiết gây sốc. Không kể lể dài dòng.\n"
        "3. CLIMAX (Cảnh áp chót): Đưa ra Sự thật bất ngờ nhất (Plot Twist) hoặc Giải pháp tột đỉnh.\n"
        "4. CTA (Cảnh cuối): Kêu gọi hành động khéo léo và tự nhiên nhất có thể.\n\n"
        "QUY TẮC CẤM KỴ (BẮT BUỘC TUÂN THỦ):\n"
        "- CẤM dùng các câu mở đầu sáo rỗng: 'Xin chào các bạn', 'Hôm nay mình sẽ chia sẻ', 'Cùng tìm hiểu nhé', 'Bạn có biết'.\n"
        "- CẤM nói đạo lý suông, cấm dùng từ ngữ hàn lâm. Mọi luận điểm phải đính kèm hình ảnh so sánh thực tế.\n\n"
        "QUY TẮC ĐẠO DIỄN HÌNH ẢNH (CINEMATIC CAMERA - BẮT BUỘC):\n"
        "- BẮT BUỘC mở đầu mỗi 'image_prompt' bằng các góc máy điện ảnh chuyên nghiệp. Ví dụ: 'Extreme close-up shot of...', 'Low-angle drone shot of...', 'Over-the-shoulder shot of...', 'Wide establishing shot of...'\n"
        "- BẮT BUỘC tả LẶP LẠI ngoại hình nhân vật chính xuyên suốt các cảnh.\n"
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
        "QUY TẮC ÂM THANH (SOUND DESIGN):\n"
        "- Hạn chế lạm dụng 'sfx' liên tục. Cảnh đầu (hook): nên dùng 'whoosh' hoặc 'riser'. Cảnh cuối (closing): dùng 'ding' hoặc 'bell'.\n"
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

    def _call():
        cached_result = cache.get("gen_script", topic=topic, num_scenes=num_scenes, mode=mode, art_style=art_style, target_duration=target_duration, narration_tone=narration_tone)
        if cached_result:
            logger.info("Using cached result for generate_script")
            return cached_result
        client = _get_client(api_key)
        try:
            response = client.models.generate_content(
                model="gemini-flash-latest",
                contents=f"Chủ đề video: {topic}",
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=ScriptResponse,
                    temperature=0.9,
                ),
            )
            try:
                from services import quota_service
                quota_service.increment_quota(1)
            except Exception:
                pass
            parsed: ScriptResponse = response.parsed
            result = parsed.model_dump()
            cache.set("gen_script", result, topic=topic, num_scenes=num_scenes, mode=mode, art_style=art_style, target_duration=target_duration, narration_tone=narration_tone)
            return result
        except Exception as e:
            # KHÔNG trả kịch bản mock (trước đây trả video "Python" bất kể chủ đề, âm thầm
            # nuốt lỗi khiến user nhận nội dung sai lệch). Ném lỗi thật để pipeline báo lên UI.
            logger.error(f"Gemini generate_script thất bại cho chủ đề '{topic}': {e}")
            raise

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
            model="gemini-flash-latest",
            contents=content_parts,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=ScriptResponse,
                temperature=0.8,
            ),
        )
        try:
            from services import quota_service
            quota_service.increment_quota(1)
        except Exception:
            pass
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
        "QUY TẮC CỰC KỲ QUAN TRỌNG VÀ BẮT BUỘC (GIỮ NGUYÊN 100% Ý NGƯỜI DÙNG): "
        "1. Nếu kịch bản gốc có phân biệt rõ các phần (như 'Voice-over:', 'Lời thoại:', 'Chuyển động:', 'Text on-screen:'), "
        "BẮT BUỘC CHỈ TRÍCH XUẤT phần Voice-over/Lời thoại vào trường `text` để hệ thống TTS đọc. "
        "TUYỆT ĐỐI giữ đúng nguyên văn 100% từng từ ngữ của lời thoại, KHÔNG ĐƯỢC tự ý sửa đổi, paraphrase hay thêm bớt. "
        "2. Sử dụng các chỉ dẫn đạo diễn (Chuyển động, Hình ảnh) để dịch chuẩn xác 100% sang tiếng Anh thành `image_prompt`. "
        "KHÔNG được tự phóng tác thêm chi tiết hình ảnh mà người dùng không yêu cầu. "
        "3. Nếu kịch bản chỉ là văn xuôi bình thường, hãy chia mỗi cảnh 1-3 câu liên tiếp và giữ nguyên văn nhiều nhất có thể. "
        "4. Tuyệt đối không đưa chỉ dẫn đạo diễn vào trường `text`. "
        f"image_prompt: luôn mô tả bằng tiếng Anh theo phong cách '{art_style}' nhưng phải trung thành tuyệt đối với mô tả của người dùng."
    )

    def _call():
        # Trim script_text for hashing to avoid too long string issue, or hash it inside _get_key
        cached_result = cache.get("split_script", script_len=len(script_text), text_hash=hashlib.md5(script_text.encode("utf-8")).hexdigest(), num_scenes=num_scenes, art_style=art_style)
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
                response_schema=ScriptResponse,
                temperature=0.1,  # Cực kỳ thấp để AI bám sát 100% text gốc, không phóng tác
            ),
        )
        try:
            from services import quota_service
            quota_service.increment_quota(1)
        except Exception:
            pass
        parsed: ScriptResponse = response.parsed
        result = [scene.model_dump() for scene in parsed.scenes]
        cache.set("split_script", result, script_len=len(script_text), text_hash=hashlib.md5(script_text.encode("utf-8")).hexdigest(), num_scenes=num_scenes, art_style=art_style)
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
