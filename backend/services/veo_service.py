# backend/services/veo_service.py
"""
PHIÊN BẢN NÂNG CẤP - veo_service.py
====================================
Bổ sung 3 tính năng cốt lõi của Veo 3.1 mà bản gốc chưa khai thác:

1. Character/Style Reference Images (Ingredients to Video)
   -> Giữ nhân vật/phong cách nhất quán xuyên suốt toàn bộ video (chống identity drift).
2. First-frame -> Last-frame chaining giữa các scene
   -> Video liền mạch như một cuốn phim thật, không còn cảm giác "ghép ảnh rời rạc".
3. Scene Extension (tuỳ chọn) cho các câu chuyện liên tục (storyteller mode)
   -> Video dài hơn 8s mà vẫn giữ chuyển động + âm thanh liên tục.

LƯU Ý TÍCH HỢP:
- File này giả định bạn dùng SDK `google-genai` (import google.genai as genai).
  Nếu bạn đang gọi REST API trực tiếp qua requests/httpx, giữ nguyên logic
  điều phối (orchestration) bên dưới, chỉ thay phần gọi model bằng http call
  tương ứng - cấu trúc payload (reference_images, image/last_frame) là như nhau.
- Cần cài: pip install google-genai ffmpeg-python
- Cần ffmpeg có sẵn trong PATH để trích last-frame từ clip.
"""

import os
import uuid
import asyncio
import logging
from typing import List, Optional, Dict, Any

import ffmpeg
from google import genai
from google.genai import types

from .key_manager import gemini_keys  # giữ nguyên key rotation hiện có

logger = logging.getLogger(__name__)

ASSETS_DIR = "assets"
IMAGES_DIR = os.path.join(ASSETS_DIR, "images")
VIDEO_TMP_DIR = os.path.join(ASSETS_DIR, "veo_tmp")
os.makedirs(VIDEO_TMP_DIR, exist_ok=True)

VEO_MODEL_QUALITY = "veo-3.1-generate-preview"   # dùng cho bản final render
VEO_MODEL_FAST = "veo-3.1-fast-generate-preview"  # dùng cho preview / nháp nhanh


def _get_client() -> genai.Client:
    """Lấy client Gemini với API key đang xoay vòng (key_manager có sẵn)."""
    api_key = gemini_keys.rotate()
    return genai.Client(api_key=api_key)


# ---------------------------------------------------------------------------
# 1. TẠO ẢNH NHÂN VẬT GỐC (CHARACTER SHEET) - dùng làm reference xuyên suốt
# ---------------------------------------------------------------------------
async def generate_character_reference(
    description: str,
    art_style: str = "Cinematic",
    num_variants: int = 1,
) -> List[str]:
    """
    Sinh 1-3 ảnh "character sheet" bằng Imagen 3 (gọi qua image_router.py hiện có
    của bạn) để dùng làm reference_images cho MỌI cảnh Veo tiếp theo.

    Trả về danh sách đường dẫn file ảnh cục bộ (không phải mảng byte),
    vì Veo API nhận ảnh qua path/bytes tùy SDK.

    Cách dùng trong pipeline:
        char_refs = await generate_character_reference(
            description="cô gái tóc ngắn đen, mặc áo khoác bomber xanh lá, kính tròn",
            art_style="Cinematic, warm lighting"
        )
        # -> truyền char_refs vào generate_scene_video() cho TẤT CẢ các scene
    """
    from .image_router import generate_image_with_fallback

    prompt = (
        f"Character reference sheet, {description}, {art_style}, "
        f"neutral pose, clear face, well-lit studio lighting, front view, "
        f"consistent identity for AI video reference"
    )
    paths = []
    for i in range(num_variants):
        img_path = os.path.join(VIDEO_TMP_DIR, f"char_ref_{uuid.uuid4().hex[:8]}.png")
        await generate_image_with_fallback(
            image_prompt=prompt, 
            output_path=img_path,
            aspect_ratio="1:1"
        )
        paths.append(img_path)
    return paths


# ---------------------------------------------------------------------------
# 2. TRÍCH XUẤT KHUNG HÌNH CUỐI CỦA 1 CLIP (để nối cảnh mượt)
# ---------------------------------------------------------------------------
def extract_last_frame(video_path: str, out_image_path: Optional[str] = None) -> str:
    """
    Dùng ffmpeg trích khung hình cuối cùng của video_path, lưu thành ảnh PNG.
    Ảnh này sẽ được dùng làm "last_frame" / "first frame của scene kế tiếp"
    để Veo 3.1 tạo chuyển cảnh mượt (frame-to-frame transition).
    """
    if out_image_path is None:
        out_image_path = os.path.join(VIDEO_TMP_DIR, f"lastframe_{uuid.uuid4().hex[:8]}.png")

    probe = ffmpeg.probe(video_path)
    duration = float(probe["format"]["duration"])
    # Lùi lại 0.05s để tránh lỗi decode ở đúng frame cuối
    seek_time = max(0, duration - 0.05)

    (
        ffmpeg
        .input(video_path, ss=seek_time)
        .output(out_image_path, vframes=1)
        .overwrite_output()
        .run(quiet=True)
    )
    return out_image_path


# ---------------------------------------------------------------------------
# 3. SINH VIDEO CHO 1 SCENE - có reference_images + first_frame optional
# ---------------------------------------------------------------------------
async def generate_scene_video(
    scene_prompt: str,
    aspect_ratio: str = "9:16",
    reference_images: Optional[List[str]] = None,
    first_frame_image: Optional[str] = None,
    last_frame_image: Optional[str] = None,
    use_fast_model: bool = False,
    negative_prompt: str = "",
) -> str:
    """
    Gọi Veo 3.1 để sinh video cho 1 cảnh (có Cache), có hỗ trợ:
      - reference_images: tối đa 3-4 ảnh giữ nhân vật/phong cách nhất quán
      - first_frame_image: ảnh mở đầu cảnh (thường = last_frame của cảnh trước)
      - last_frame_image: ảnh kết thúc cảnh (dùng khi muốn ép transition có đích đến rõ)

    Trả về đường dẫn file video (.mp4) đã tải về máy chủ.
    """
    # ── Cache Check (chỉ cache khi KHÔNG dùng frame chaining) ──
    # Frame chaining yêu cầu output khác nhau cho mỗi lần gọi dù prompt giống
    from .cache_service import cache as media_cache
    cache_params = dict(
        prompt=scene_prompt, aspect_ratio=aspect_ratio,
        negative_prompt=negative_prompt or "",
        model="fast" if use_fast_model else "quality",
    )
    use_cache = not first_frame_image and not last_frame_image
    
    if use_cache:
        out_path_check = os.path.join(VIDEO_TMP_DIR, f"scene_{uuid.uuid4().hex[:8]}.mp4")
        if media_cache.get_media("veo", out_path_check, **cache_params):
            return out_path_check

    client = _get_client()
    model = VEO_MODEL_FAST if use_fast_model else VEO_MODEL_QUALITY

    config_kwargs: Dict[str, Any] = {
        "aspect_ratio": aspect_ratio,          # native 9:16, không cần crop hậu kỳ
        "negative_prompt": negative_prompt or None,
    }

    # --- Character/style consistency ---
    if reference_images:
        loaded_refs = []
        for path in reference_images[:3]:  # Veo 3.1 tối đa 3 ảnh reference ổn định
            loaded_refs.append(types.Image.from_file(path))
        config_kwargs["reference_images"] = loaded_refs

    # --- Frame-to-frame transition (nối cảnh mượt) ---
    image_arg = None
    if first_frame_image:
        image_arg = types.Image.from_file(first_frame_image)
    if last_frame_image:
        config_kwargs["last_frame"] = types.Image.from_file(last_frame_image)

    logger.info(f"[Veo] Đang tạo scene: model={model}, aspect={aspect_ratio}, "
                f"has_ref={bool(reference_images)}, chained={bool(first_frame_image)}")

    operation = client.models.generate_videos(
        model=model,
        prompt=scene_prompt,
        image=image_arg,
        config=types.GenerateVideosConfig(**config_kwargs),
    )

    # Veo generation là async operation -> poll cho tới khi xong
    while not operation.done:
        await asyncio.sleep(5)
        operation = client.operations.get(operation)

    video_result = operation.result.generated_videos[0]
    out_path = os.path.join(VIDEO_TMP_DIR, f"scene_{uuid.uuid4().hex[:8]}.mp4")
    video_result.video.save(out_path)
    
    # ── Cache Save ──
    if use_cache:
        media_cache.set_media("veo", out_path, **cache_params)
    
    return out_path


# ---------------------------------------------------------------------------
# 4. ĐIỀU PHỐI TOÀN BỘ CHUỖI CẢNH - đây là hàm bạn gọi từ video_service.py
# ---------------------------------------------------------------------------
async def generate_scene_chain(
    scenes: List[Dict[str, Any]],
    aspect_ratio: str = "9:16",
    character_description: Optional[str] = None,
    art_style: str = "Cinematic",
    use_frame_chaining: bool = True,
    use_fast_model: bool = False,
) -> List[str]:
    """
    Sinh toàn bộ chuỗi video cho các scenes, tự động:
      - Tạo character reference 1 lần dùng chung cho mọi cảnh (nếu có character_description)
      - Nối last_frame của cảnh N làm first_frame của cảnh N+1 (nếu use_frame_chaining=True)

    scenes: list các dict, mỗi dict cần có key "prompt" (mô tả cảnh quay).
    Trả về list đường dẫn video (.mp4) theo đúng thứ tự scenes.
    """
    reference_images: List[str] = []
    if character_description:
        reference_images = await generate_character_reference(
            description=character_description,
            art_style=art_style,
        )

    video_paths: List[str] = []
    previous_last_frame: Optional[str] = None

    for idx, scene in enumerate(scenes):
        first_frame = previous_last_frame if (use_frame_chaining and idx > 0) else None

        video_path = await generate_scene_video(
            scene_prompt=scene["prompt"],
            aspect_ratio=aspect_ratio,
            reference_images=reference_images or None,
            first_frame_image=first_frame,
            use_fast_model=use_fast_model,
            negative_prompt=scene.get("negative_prompt", ""),
        )
        video_paths.append(video_path)

        if use_frame_chaining:
            previous_last_frame = extract_last_frame(video_path)

    return video_paths
