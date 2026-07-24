import os
import asyncio
import logging
from typing import Optional
from services.gemini_service import generate_image as generate_image_google
import urllib.parse
import uuid

logger = logging.getLogger(__name__)

def _create_artistic_gradient_image(output_path: str, aspect_ratio: str = "9:16"):
    """Tạo ảnh Gradient nghệ thuật điện ảnh đẹp mắt phòng khi mất mạng hoàn toàn."""
    from PIL import Image, ImageDraw
    width, height = (1080, 1920) if aspect_ratio == "9:16" else (1920, 1080)
    if aspect_ratio == "1:1": width, height = 1080, 1080

    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)

    # Gradient từ tím đậm sang xanh đậm điện ảnh
    c1 = (15, 23, 42)    # Deep Navy Slate
    c2 = (88, 28, 135)   # Deep Purple
    c3 = (15, 118, 110)  # Dark Teal

    for y in range(height):
        t = y / height
        if t < 0.5:
            factor = t * 2
            r = int(c1[0] * (1 - factor) + c2[0] * factor)
            g = int(c1[1] * (1 - factor) + c2[1] * factor)
            b = int(c1[2] * (1 - factor) + c2[2] * factor)
        else:
            factor = (t - 0.5) * 2
            r = int(c2[0] * (1 - factor) + c3[0] * factor)
            g = int(c2[1] * (1 - factor) + c3[1] * factor)
            b = int(c2[2] * (1 - factor) + c3[2] * factor)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    img.save(output_path, "PNG")

async def fetch_pexels_photo(query: str, output_path: str, aspect_ratio: str = "9:16", api_key: Optional[str] = None) -> str:
    """Tải ảnh HD thực tế từ Pexels API theo từ khóa kịch bản."""
    import json
    import requests
    if not api_key:
        api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        raise RuntimeError("Thiếu PEXELS_API_KEY")
        
    orientation = "portrait"
    if aspect_ratio == "16:9":
        orientation = "landscape"
    elif aspect_ratio == "1:1":
        orientation = "square"
        
    clean_query = query.replace("\n", " ").strip()[:100]
    url = f"https://api.pexels.com/v1/search?query={urllib.parse.quote(clean_query)}&per_page=1&orientation={orientation}"
    headers = {"Authorization": api_key, "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    def _fetch():
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        photos = data.get("photos", [])
        if not photos:
            raise RuntimeError(f"Pexels không tìm thấy ảnh cho từ khóa: '{clean_query}'")
        img_url = photos[0]["src"]["large2x"]
        r_img = requests.get(img_url, timeout=30)
        r_img.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(r_img.content)
        return output_path

    logger.info(f"📸 Tải ảnh thực tế Pexels với từ khóa: '{clean_query}'")
    return await asyncio.to_thread(_fetch)

async def _generate_pollinations(prompt: str, output_path: str, aspect_ratio: str = "9:16", negative_prompt: str = "", seed: Optional[int] = None):
    width, height = (1080, 1920) if aspect_ratio == "9:16" else (1920, 1080)
    if aspect_ratio == "1:1": width, height = 1080, 1080
    
    # Rút gọn và làm sạch prompt để không bị lỗi URL hoặc timeout
    clean_prompt = prompt.replace("\n", " ").replace("\r", " ").strip()
    if len(clean_prompt) > 200:
        clean_prompt = clean_prompt[:200]
        
    safe_prompt = urllib.parse.quote(clean_prompt)
    if seed is None:
        seed = uuid.uuid4().int % 100000
    
    # Sử dụng model FLUX - mô hình AI vẽ ảnh siêu nét miễn phí hiện tại
    url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width={width}&height={height}&nologo=true&seed={seed}&model=flux"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    def _download():
        import requests
        import time
        for attempt in range(3):
            try:
                r = requests.get(url, headers=headers, timeout=30)
                r.raise_for_status()
                with open(output_path, "wb") as f:
                    f.write(r.content)
                return
            except Exception as e:
                logger.warning(f"Pollinations attempt {attempt+1} failed: {e}")
                time.sleep(1)
        raise Exception("Pollinations failed after 3 attempts")
            
    await asyncio.to_thread(_download)
    return output_path

async def generate_image_with_fallback(
    image_prompt: str,
    output_path: str,
    aspect_ratio: str = "9:16",
    banana_api_key: Optional[str] = None,
    google_api_key: Optional[str] = None,
    banana_mode: bool = False,
    negative_prompt: str = "",
    seed: Optional[int] = None,
    art_style: Optional[str] = None
) -> str:
    """
    Router sinh ảnh 4 Tầng (có Cache):
    0. Cache check — nếu prompt trùng 100% → trả file cũ.
    1. Google Gemini 3.1 Flash Image.
    2. Pexels HD Photo Stock (dùng PEXELS_API_KEY).
    3. Pollinations FLUX AI (với User-Agent Chrome).
    4. Artistic Dynamic Gradient (Offline).
    """
    final_prompt = image_prompt
    if banana_mode:
        final_prompt = f"Minion style, 3D animated, cute yellow minions doing: {image_prompt}. Cinematic lighting, highly detailed."
        logger.info(f"🍌 Kích hoạt Banana Mode. Prompt: {final_prompt}")

    # Các tham số dùng để tạo cache key
    cache_params = dict(
        prompt=final_prompt, aspect_ratio=aspect_ratio,
        art_style=art_style or "", negative_prompt=negative_prompt or "",
    )

    # ── Tầng 0: Cache Check ──
    from services.cache_service import cache as media_cache
    if media_cache.get_media("imagen", output_path, **cache_params):
        return output_path
        
    # Tự động lấy Key từ .env thông qua gemini_keys nếu FE không truyền key thủ công
    if not google_api_key:
        from services.gemini_service import gemini_keys
        google_api_key = gemini_keys.get_key()

    # Tầng 1: Google Gemini 3.1 Flash Image
    if google_api_key:
        try:
            result = await generate_image_google(final_prompt, output_path, google_api_key, aspect_ratio, negative_prompt, seed)
            media_cache.set_media("imagen", result, **cache_params)
            return result
        except Exception as e:
            logger.warning(f"Google Gemini Image API thất bại ({e}). Chuyển sang Tầng 2 (Pexels / Pollinations)...")

    # Tầng 2: Pexels API (nếu có PEXELS_API_KEY trong .env)
    pexels_key = os.getenv("PEXELS_API_KEY")
    if pexels_key:
        try:
            result = await fetch_pexels_photo(image_prompt, output_path, aspect_ratio, pexels_key)
            media_cache.set_media("imagen", result, **cache_params)
            return result
        except Exception as pex_err:
            logger.warning(f"Pexels Photo fallback thất bại ({pex_err}). Chuyển sang Pollinations FLUX...")

    # Tầng 3: Pollinations FLUX AI (với User-Agent Chrome)
    try:
        result = await _generate_pollinations(final_prompt, output_path, aspect_ratio, negative_prompt, seed)
        media_cache.set_media("imagen", result, **cache_params)
        return result
    except Exception as pol_err:
        logger.error(f"Tất cả dịch vụ sinh ảnh trực tuyến đều thất bại: {pol_err}. Tạo ảnh Gradient điện ảnh nghệ thuật dự phòng.")
        _create_artistic_gradient_image(output_path, aspect_ratio)
        return output_path

async def fetch_pexels_video(query: str, output_path: str, aspect_ratio: str, api_key: str) -> str:
    """
    Tìm và tải video từ Pexels API. Trả về đường dẫn file .mp4.

    QUAN TRỌNG: Pexels API trả 403 Forbidden nếu request THIẾU User-Agent.
    (Đây là lý do trước đây video stock không bao giờ xuất hiện — pipeline luôn
    rơi về ảnh AI tĩnh.) Bắt buộc gửi kèm User-Agent như trình duyệt thật.
    """
    import requests
    orientation = "portrait"
    if aspect_ratio == "16:9":
        orientation = "landscape"
    elif aspect_ratio == "1:1":
        orientation = "square"

    clean_query = query.replace("\n", " ").strip()[:100]
    url = f"https://api.pexels.com/videos/search?query={urllib.parse.quote(clean_query)}&per_page=5&orientation={orientation}"
    headers = {
        "Authorization": api_key,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    # Kích thước mục tiêu theo tỉ lệ để chọn file gần nhất (tránh tải file 4K quá nặng)
    target_h = 1920 if orientation == "portrait" else (1080 if orientation == "landscape" else 1080)

    def _fetch():
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        videos = data.get("videos", [])
        if not videos:
            raise RuntimeError(f"Pexels không có video cho từ khóa: '{clean_query}'")

        video = videos[0]
        files = video.get("video_files", [])
        if not files:
            raise RuntimeError("Không tìm thấy link video trong kết quả Pexels.")

        # Chọn file có chiều cao gần target nhất (API mới trả quality=None nên không lọc theo 'hd')
        def _score(vf):
            h = vf.get("height") or 0
            return abs(h - target_h) if h else 10 ** 9
        selected = sorted(files, key=_score)[0]

        download_url = selected["link"]
        tmp_path = output_path if output_path.endswith(".mp4") else output_path + ".mp4"
        rv = requests.get(download_url, headers={"User-Agent": headers["User-Agent"]}, timeout=90)
        rv.raise_for_status()
        with open(tmp_path, "wb") as f:
            f.write(rv.content)
        return tmp_path

    logger.info(f"🔍 Tìm kiếm video Pexels với từ khóa: '{clean_query}'")
    return await asyncio.to_thread(_fetch)
