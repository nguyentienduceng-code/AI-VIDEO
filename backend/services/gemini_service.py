"""
gemini_service.py
------------------
NÂNG CẤP:
1. Migrate từ `google.generativeai` (deprecated) sang SDK mới `google.genai`.
2. Dùng Structured Output (response_schema bằng Pydantic) để Gemini LUÔN trả
   JSON đúng cấu trúc — không cần parse / regex / try-except JSON nữa.
3. Thêm hàm sinh ảnh thật bằng Imagen, dùng cho từng scene.

Cách hoạt động:
- `genai.Client()` tự đọc API key từ biến môi trường GEMINI_API_KEY hoặc
  GOOGLE_GENAI_API_KEY. Nếu người dùng nhập API key riêng trên Frontend,
  ta truyền `api_key=...` trực tiếp khi tạo Client cho từng request.
"""

from __future__ import annotations

import asyncio
import base64
import os
from typing import List, Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field


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


class ScriptResponse(BaseModel):
    scenes: List[Scene]


# ---------------------------------------------------------------------------
# 2. Sinh kịch bản (text) — thay thế hoàn toàn logic cũ
# ---------------------------------------------------------------------------
def _get_client(api_key: Optional[str] = None) -> genai.Client:
    """
    Tạo Client cho mỗi request. Nếu người dùng nhập API key trên FE thì
    dùng key đó; nếu không thì fallback về biến môi trường trong .env.
    """
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError(
            "Thiếu Gemini API Key. Hãy nhập trên giao diện hoặc khai báo "
            "GEMINI_API_KEY trong file backend/.env"
        )
    return genai.Client(api_key=key)


async def generate_script(topic: str, art_style: str = "Cinematic", api_key: Optional[str] = None) -> List[dict]:
    """
    Gọi Gemini để sinh 4 phân cảnh từ 1 chủ đề (topic).
    Trả về list[dict] đã được validate đúng schema Scene — không thể sai cấu trúc.
    """
    client = _get_client(api_key)

    system_prompt = (
        "Bạn là một biên kịch video ngắn (TikTok/Reels) chuyên nghiệp. "
        "Nhiệm vụ: viết kịch bản gồm CHÍNH XÁC 4 phân cảnh cho chủ đề được cung cấp. "
        "Lời thoại (text) viết bằng tiếng Việt, tự nhiên, súc tích, hấp dẫn người xem trong vài giây đầu. "
        f"image_prompt viết bằng tiếng Anh, mô tả cực kỳ chi tiết theo phong cách nghệ thuật: '{art_style}', "
        "phù hợp để đưa vào mô hình sinh ảnh AI."
    )

    # google.genai SDK chạy đồng bộ (sync) -> chạy trong thread riêng để
    # không block event loop của FastAPI (xem fix #1 trong tts_service.py)
    def _call():
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
        # Khi dùng response_schema, SDK cung cấp sẵn .parsed (đã validate)
        parsed: ScriptResponse = response.parsed
        return [scene.model_dump() for scene in parsed.scenes]

    return await asyncio.to_thread(_call)


# ---------------------------------------------------------------------------
# 3. Sinh ảnh thật bằng Imagen — thay cho placeholder ngẫu nhiên
# ---------------------------------------------------------------------------
async def generate_image(
    image_prompt: str,
    output_path: str,
    api_key: Optional[str] = None,
    aspect_ratio: str = "9:16",
) -> str:
    """
    Sinh 1 ảnh từ image_prompt bằng Imagen, lưu vào output_path (.png/.jpg).
    Trả về output_path khi thành công.

    Lưu ý: nếu lỗi (hết quota, key sai, prompt bị filter an toàn chặn...),
    hàm sẽ raise Exception để main.py có thể fallback sang ảnh placeholder,
    tránh làm chết toàn bộ pipeline.
    """
    client = _get_client(api_key)

    def _call():
        result = client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=image_prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio=aspect_ratio,  # 9:16 cho video dọc Tiktok/Reels
                safety_filter_level="block_low_and_above",
                person_generation="allow_adult",
            ),
        )
        if not result.generated_images:
            raise RuntimeError("Imagen không trả về ảnh nào (có thể bị Safety Filter chặn).")

        image_bytes = result.generated_images[0].image.image_bytes
        with open(output_path, "wb") as f:
            f.write(image_bytes)
        return output_path

    return await asyncio.to_thread(_call)
