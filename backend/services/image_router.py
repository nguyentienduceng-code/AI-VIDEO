import os
import asyncio
import logging
from typing import Optional
from services.gemini_service import generate_image as generate_image_google
import urllib.parse
import uuid

logger = logging.getLogger(__name__)

async def _generate_pollinations(prompt: str, output_path: str, aspect_ratio: str = "9:16", negative_prompt: str = ""):
    width, height = (1080, 1920) if aspect_ratio == "9:16" else (1920, 1080)
    if aspect_ratio == "1:1": width, height = 1080, 1080
    
    # Thêm prompt enhance để ảnh nhìn cinematic hơn
    enhance = "masterpiece, best quality, highly detailed, cinematic lighting, 8k resolution"
    if negative_prompt:
        enhance += f", avoid: {negative_prompt}"
        
    full_prompt = f"{prompt}, {enhance}"
    safe_prompt = urllib.parse.quote(full_prompt)
    seed = uuid.uuid4().int % 100000
    
    # Sử dụng model FLUX - mô hình AI vẽ ảnh siêu nét miễn phí hiện tại
    url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width={width}&height={height}&nologo=true&seed={seed}&model=flux"
    
    def _download():
        import requests
        r = requests.get(url, timeout=45)
        r.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(r.content)
            
    await asyncio.to_thread(_download)
    return output_path

async def generate_image_with_fallback(
    image_prompt: str,
    output_path: str,
    aspect_ratio: str = "9:16",
    banana_api_key: Optional[str] = None,
    google_api_key: Optional[str] = None,
    banana_mode: bool = False,
    negative_prompt: str = ""
) -> str:
    """
    Router sinh ảnh: Cố gắng dùng Google Imagen 3. Nếu thất bại (do chưa nạp tiền Billing),
    sẽ tự động chuyển sang bên thứ 3 (Pollinations AI - Flux model) miễn phí 100%.
    """
    final_prompt = image_prompt
    if banana_mode:
        final_prompt = f"Minion style, 3D animated, cute yellow minions doing: {image_prompt}. Cinematic lighting, highly detailed."
        logger.info(f"🍌 Kích hoạt Banana Mode. Prompt: {final_prompt}")
        
    try:
        # Thử dùng Google Imagen 3 trước
        return await generate_image_google(final_prompt, output_path, google_api_key, aspect_ratio, negative_prompt=negative_prompt)
    except Exception as e:
        logger.warning(f"Google Imagen API thất bại ({e}). Chuyển sang API bên thứ 3 (Pollinations FLUX)...")
        return await _generate_pollinations(final_prompt, output_path, aspect_ratio, negative_prompt=negative_prompt)

