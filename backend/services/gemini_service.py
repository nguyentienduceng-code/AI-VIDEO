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
        "- BẮT BUỘC thêm 1 từ khóa tông màu ánh sáng (VD: 'cinematic teal and orange lighting' hoặc 'moody dark lighting') vào TẤT CẢ các image_prompt để đảm bảo Color Grading đồng nhất toàn video.\n\n"
        "QUY TẮC ÂM THANH (SOUND DESIGN - BẮT BUỘC):\n"
        "- BẮT BUỘC điền trường 'sfx' cho từng cảnh. CHỈ ĐƯỢC DÙNG 1 TRONG CÁC GIÁ TRỊ SAU: whoosh, pop, ding, riser, suspense, impact, bell, laugh.\n"
        "- Dùng 'whoosh' cho chuyển cảnh nhanh/bất ngờ, 'pop' khi hiện text quan trọng, 'ding' hoặc 'bell' cho điểm nhấn tích cực.\n"
        "- Dùng 'riser' hoặc 'suspense' cho cao trào, 'impact' cho sự kiện chấn động, 'laugh' cho tình huống hài hước.\n"
        "- Cảnh đầu (hook): dùng 'whoosh' hoặc 'riser'. Cảnh cuối (closing): dùng 'ding' hoặc 'bell'.\n"
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
            logger.error(f"Gemini API failed: {e}. Using mock script to bypass rate limits.")
            return {
                "sentiment": "happy",
                "scenes": [
                    {
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
        cached_result = cache.get("split_script", script_len=len(script_text), text_hash=hash(script_text), num_scenes=num_scenes, art_style=art_style)
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
    Trích xuất từ khóa ngắn (1-3 từ) từ image_prompt dài để tìm kiếm trên Pexels/Pixabay (Offline, không dùng Gemini để tiết kiệm Quota).
    """
    # Xóa các từ thông dụng không mang ý nghĩa chính
    stopwords = {"a", "an", "the", "in", "on", "at", "with", "and", "or", "of", "to", "for", "is", "are", "cinematic", "style", "lighting", "photo", "image", "picture", "realistic", "4k", "8k"}
    
    # Chuẩn hóa chuỗi, bỏ dấu câu cơ bản
    clean_prompt = image_prompt.replace(",", " ").replace(".", " ").replace("!", " ").replace("?", " ").lower()
    words = clean_prompt.split()
    
    # Lọc stopwords
    filtered_words = [w for w in words if w not in stopwords]
    
    # Lấy 2-3 từ đầu tiên mang ý nghĩa (chủ thể)
    if len(filtered_words) >= 2:
        return " ".join(filtered_words[:2])
    elif len(filtered_words) == 1:
        return filtered_words[0]
    else:
        # Fallback an toàn
        return "nature"
