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
MAX_RETRIES = 3
BASE_DELAY = 2.0  # giây


def _retry_sync(func_factory, retries=MAX_RETRIES, base_delay=BASE_DELAY, key_manager=None):
    """
    Wrapper: gọi hàm đồng bộ với retry + exponential backoff.
    Nếu có lỗi 429/RESOURCE_EXHAUSTED và key_manager được cung cấp, tự động xoay vòng key.
    Lưu ý: func_factory là một hàm không nhận tham số và trả về kết quả gọi API.
    """
    last_error = None
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
                raise
                
            # Xoay vòng key nếu lỗi liên quan đến Quota/Rate Limit
            if key_manager and ("429" in error_str or "RESOURCE_EXHAUSTED" in error_str):
                new_key = key_manager.rotate()
                logger.warning(f"Quota Exceeded. Đã tự động xoay vòng API Key.")
                
            delay = base_delay * (2 ** attempt)
            logger.warning(f"API lỗi (attempt {attempt+1}/{retries+1}): {e}. Retry sau {delay}s...")
            time.sleep(delay)
    raise last_error


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
    sfx: str = Field(
        default="",
        description="Hiệu ứng âm thanh tại cảnh này (VD: whoosh, pop, punch, laugh, bell, suspense). Bỏ trống nếu không cần."
    )
    visual_effect: str = Field(
        default="zoom_in",
        description="Hiệu ứng chuyển động Camera (zoom_in, zoom_out, pan_left, pan_right, none)"
    )


class ScriptResponse(BaseModel):
    sentiment: str = Field(
        default="happy",
        description="Cảm xúc tổng thể của video (happy, sad, dramatic, suspense, chill, energetic). Dùng để chọn nhạc nền."
    )
    scenes: List[Scene]


# ---------------------------------------------------------------------------
# 2. Shared helper
# ---------------------------------------------------------------------------
from services.key_manager import gemini_keys

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
    return genai.Client(api_key=key)


# ---------------------------------------------------------------------------
# 3. MODE: Storyteller (mặc định) + Quiz/Listicle
# ---------------------------------------------------------------------------
async def generate_script(
    topic: str,
    num_scenes: int = 4,
    mode: str = "storyteller",
    art_style: str = "Cinematic",
    api_key: Optional[str] = None,
) -> List[dict]:
    """
    Gọi Gemini để sinh N phân cảnh từ 1 chủ đề (topic).
    Hỗ trợ mode: storyteller, quiz_listicle.
    Trả về list[dict] đã được validate đúng schema Scene.
    """
    num_scenes = max(4, min(20, num_scenes))

    if mode == "quiz_listicle":
        system_prompt = (
            "Bạn là biên kịch video giáo dục/giải trí chuyên nghiệp, "
            "chuyên làm video dạng 'Top N' hoặc 'Quiz hỏi-đáp' cho TikTok/Reels. "
            f"Nhiệm vụ: viết kịch bản gồm CHÍNH XÁC {num_scenes} phân cảnh theo dạng listicle hoặc quiz. "
            "Mỗi cảnh là 1 fact/item hoặc 1 câu hỏi+đáp thú vị. "
            "Cảnh đầu tiên là intro hook gây tò mò, cảnh cuối là kết thúc ấn tượng. "
            "Lời thoại (text) viết bằng tiếng Việt, ngắn gọn, hấp dẫn, dùng ngôn ngữ TikTok. "
            f"image_prompt viết bằng tiếng Anh, mô tả cực kỳ chi tiết theo phong cách '{art_style}', "
            "phù hợp để đưa vào mô hình sinh ảnh AI."
        )
    else:  # storyteller (default)
        system_prompt = (
            "Bạn là một biên kịch video ngắn (TikTok/Reels) chuyên nghiệp. "
            f"Nhiệm vụ: viết kịch bản gồm CHÍNH XÁC {num_scenes} phân cảnh cho chủ đề được cung cấp. "
            "Lời thoại (text) viết bằng tiếng Việt, tự nhiên, súc tích, hấp dẫn người xem trong vài giây đầu. "
            f"image_prompt viết bằng tiếng Anh, mô tả cực kỳ chi tiết theo phong cách nghệ thuật: '{art_style}', "
            "phù hợp để đưa vào mô hình sinh ảnh AI."
        )

    def _call():
        client = _get_client(api_key)
        try:
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
            parsed: ScriptResponse = response.parsed
            return parsed.model_dump()
        except Exception as e:
            logger.error(f"Gemini API failed: {e}. Using mock script to bypass rate limits.")
            return {
                "sentiment": "happy",
                "scenes": [
                    {
                        "scene": 1,
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

    return await asyncio.to_thread(_retry_sync, _call)


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
        "Phân tích nội dung từng ảnh và viết lời bình luận/kể chuyện tiếng Việt "
        "thật tự nhiên, hấp dẫn, phù hợp với nội dung ảnh. "
        "Cảnh đầu nên có hook gây chú ý, cảnh cuối nên có câu kết ấn tượng. "
        "image_prompt: viết mô tả tiếng Anh ngắn gọn về nội dung ảnh (dùng cho metadata)."
    )

    def _call():
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
            model="gemini-2.5-flash",
            contents=content_parts,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=ScriptResponse,
                temperature=0.8,
            ),
        )
        parsed: ScriptResponse = response.parsed
        return [scene.model_dump() for scene in parsed.scenes]

    return await asyncio.to_thread(_retry_sync, _call)


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
        "Mỗi cảnh (text) chứa 1-3 câu liên tiếp từ script gốc, giữ nguyên nội dung "
        "nhưng có thể chỉnh sửa nhẹ cho tự nhiên khi đọc thành lời. "
        "KHÔNG được bịa thêm nội dung mới ngoài script gốc. "
        f"image_prompt: mô tả hình ảnh tiếng Anh chi tiết theo phong cách '{art_style}', "
        "phản ánh đúng nội dung đoạn text đó."
    )

    def _call():
        client = _get_client(api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Kịch bản cần chia cảnh:\n\n{script_text}",
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=ScriptResponse,
                temperature=0.5,  # Thấp hơn vì cần chính xác với script gốc
            ),
        )
        parsed: ScriptResponse = response.parsed
        return [scene.model_dump() for scene in parsed.scenes]

    return await asyncio.to_thread(_retry_sync, _call)


# ---------------------------------------------------------------------------
# 6. Sinh ảnh thật bằng Imagen — giữ nguyên từ V1
# ---------------------------------------------------------------------------
async def generate_image(
    image_prompt: str,
    output_path: str,
    api_key: Optional[str] = None,
    aspect_ratio: str = "9:16",
    negative_prompt: str = ""
) -> str:
    """
    Sinh 1 ảnh từ image_prompt bằng Imagen, lưu vào output_path (.png/.jpg).
    Trả về output_path khi thành công.

    Lưu ý: nếu lỗi (hết quota, key sai, prompt bị filter an toàn chặn...),
    hàm sẽ raise Exception để main.py có thể fallback sang ảnh placeholder,
    tránh làm chết toàn bộ pipeline.
    """
    def _call():
        client = _get_client(api_key)
        kwargs = {
            "number_of_images": 1,
            "aspect_ratio": aspect_ratio,  # 9:16 cho video dọc, 16:9 cho ngang
            "safety_filter_level": "block_low_and_above",
            "person_generation": "allow_adult",
        }
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt
            
        result = client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=image_prompt,
            config=types.GenerateImagesConfig(**kwargs),
        )
        if not result.generated_images:
            raise RuntimeError("Imagen không trả về ảnh nào (có thể bị Safety Filter chặn).")

        image_bytes = result.generated_images[0].image.image_bytes
        with open(output_path, "wb") as f:
            f.write(image_bytes)
        return output_path

    return await asyncio.to_thread(_retry_sync, _call, key_manager=gemini_keys)
