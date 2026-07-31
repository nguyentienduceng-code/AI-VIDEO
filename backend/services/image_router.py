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
    negative_prompt: str = "",
    seed: Optional[int] = None,
    art_style: Optional[str] = None,
    source_meta: Optional[dict] = None,
) -> str:
    """
    Router sinh ảnh 4 Tầng (có Cache):
    0. Cache check — nếu prompt trùng 100% → trả file cũ.
    1. Google Gemini 3.1 Flash Image.
    2. Pollinations FLUX AI (miễn phí, không quota — với User-Agent Chrome).
    3. Pexels HD Photo Stock (dùng PEXELS_API_KEY).
    4. Artistic Dynamic Gradient (Offline).

    THỨ TỰ TẦNG 2 ↔ 3 ĐÃ ĐẢO. Bản cũ đặt Pexels photo TRƯỚC Pollinations, nên khi quota
    ảnh Gemini cạn (free tier rất mỏng) thì hàm này — vốn được gọi CHÍNH XÁC vì người dùng
    muốn ẢNH AI — lại trả về một tấm ảnh STOCK TĨNH. Đó là đổi nguồn hình sau lưng người
    dùng, và là nguyên nhân thứ hai của triệu chứng "Gemini sinh ảnh khá ít, đa số video
    lấy từ Pexels". Pollinations FLUX miễn phí và không quota nên nó mới là tầng dự phòng
    đúng nghĩa cho ảnh AI; Pexels photo lùi về làm lưới cuối trước ảnh gradient.

    `source_meta`: dict để hàm ghi lại TẦNG NÀO thật sự tạo ra file. Trước đây không có
    cách nào biết — mọi tầng đều `return output_path` như nhau, còn thất bại của tầng trên
    chỉ nằm ở log WARNING. Hệ quả: hết quota ảnh Gemini thì cả video âm thầm thành ảnh
    stock tĩnh / Pollinations mà người dùng không hề hay, và cũng không ai đo được tỉ lệ
    thật của từng nguồn để mà tối ưu.
    """
    def _ghi(nguon: str) -> None:
        if source_meta is not None:
            source_meta["source"] = nguon
    # Các tham số dùng để tạo cache key
    cache_params = dict(
        prompt=image_prompt, aspect_ratio=aspect_ratio,
        art_style=art_style or "", negative_prompt=negative_prompt or "",
    )

    # ── Tầng 0: Cache Check ──
    from services.cache_service import cache as media_cache
    if media_cache.get_media("imagen", output_path, **cache_params):
        _ghi("cache:image")
        return output_path
        
    # Tự động lấy Key từ .env thông qua gemini_keys nếu FE không truyền key thủ công
    if not google_api_key:
        from services.gemini_service import gemini_keys
        google_api_key = gemini_keys.get_key()

    # Tầng 1: Google Gemini 3.1 Flash Image
    if google_api_key:
        try:
            result = await generate_image_google(image_prompt, output_path, google_api_key, aspect_ratio, negative_prompt, seed)
            media_cache.set_media("imagen", result, **cache_params)
            _ghi("gemini_image")
            return result
        except Exception as e:
            logger.warning(f"Google Gemini Image API thất bại ({e}). Chuyển sang Tầng 2 (Pollinations FLUX)...")

    # Tầng 2: Pollinations FLUX AI (miễn phí, không quota) — dự phòng ĐÚNG NGHĨA cho ảnh AI
    try:
        result = await _generate_pollinations(image_prompt, output_path, aspect_ratio, negative_prompt, seed)
        media_cache.set_media("imagen", result, **cache_params)
        _ghi("pollinations_flux")
        return result
    except Exception as pol_err:
        logger.warning(f"Pollinations FLUX thất bại ({pol_err}). Chuyển sang Pexels Photo...")

    # Tầng 3: Pexels Photo — LƯỚI CUỐI, chỉ khi cả hai nguồn ảnh AI đều chết.
    # Từ khoá phải qua `stock_query_from_prompt`: LỖI CŨ truyền NGUYÊN `image_prompt` dài
    # (cắt cứng 100 ký tự) làm câu tìm kiếm, tức gửi cả "Extreme close-up shot of ... 8k,
    # photorealistic, Unreal Engine 5" cho Pexels — đúng loại truy vấn rác mà
    # `stock_query_from_prompt` sinh ra để tránh.
    pexels_key = os.getenv("PEXELS_API_KEY")
    if pexels_key:
        try:
            from services.gemini_service import stock_query_from_prompt

            result = await fetch_pexels_photo(
                stock_query_from_prompt(image_prompt), output_path, aspect_ratio, pexels_key
            )
            media_cache.set_media("imagen", result, **cache_params)
            _ghi("pexels_photo")
            return result
        except Exception as pex_err:
            logger.warning(f"Pexels Photo (lưới cuối) thất bại: {pex_err}")

    logger.error("Tất cả dịch vụ sinh ảnh đều thất bại. Tạo ảnh Gradient điện ảnh dự phòng.")
    _create_artistic_gradient_image(output_path, aspect_ratio)
    _ghi("gradient_offline")
    return output_path

ASPECT_TARGETS = {
    "9:16": ("portrait", 1080, 1920),
    "16:9": ("landscape", 1920, 1080),
    "1:1": ("square", 1080, 1080),
}


def _score_stock_candidate(video: dict, target_ratio: float, target_h: int, needed_dur: float) -> float:
    """
    Điểm PHẠT của 1 ứng viên video Pexels — càng THẤP càng tốt.

    Trước đây pipeline luôn lấy `videos[0]` dù đã tải sẵn 5 kết quả: clip đầu bảng
    thường là clip phổ biến nhất chứ không phải clip vừa khung, đủ dài hay đủ nét.
    Ba tiêu chí dưới đây là 3 thứ người xem nhận ra ngay khi sai.
    """
    w = video.get("width") or 0
    h = video.get("height") or 0
    src_dur = float(video.get("duration") or 0)

    # 1) Lệch tỉ lệ khung — nặng nhất: lệch nhiều là phải bù nền mờ hoặc cắt sâu.
    if w and h:
        ratio_penalty = abs(target_ratio - (w / h)) * 3.0
    else:
        ratio_penalty = 1.0

    # 2) Ngắn hơn thời lượng cảnh → phải ping-pong/lặp, kém tự nhiên hơn clip đủ dài.
    if needed_dur > 0 and src_dur > 0 and src_dur < needed_dur:
        dur_penalty = min((needed_dur - src_dur) / needed_dur, 1.0) * 0.8
    else:
        dur_penalty = 0.0

    # 3) Độ phân giải thấp hơn khung đích → phóng to sẽ vỡ/mờ.
    best_h = max((vf.get("height") or 0) for vf in video.get("video_files", [])) if video.get("video_files") else h
    res_penalty = max(0.0, (target_h - best_h) / target_h) * 1.2 if target_h else 0.0

    return ratio_penalty + dur_penalty + res_penalty


_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class StockIrrelevantError(RuntimeError):
    """Kho stock CÓ trả kết quả, nhưng không kết quả nào thật sự liên quan tới truy vấn.

    Đây là lỗi riêng để caller phân biệt với "không có kết quả": cả hai đều nên hạ bậc
    truy vấn / đổi nhà cung cấp, nhưng riêng trường hợp này còn là dấu hiệu chủ thể VỐN
    KHÔNG TỒN TẠI trong kho footage (khái niệm trừu tượng) — lúc đó ảnh AI mới là câu trả
    lời đúng, chứ không phải một clip stock gần gần.
    """


def _stem(tu: str) -> str:
    """Rút gọn số nhiều rất thô: glasses→glass, dunes→dune. Đủ cho việc đối chiếu từ khoá."""
    t = tu.strip("-_").lower()
    for duoi in ("ies", "es", "s"):
        if len(t) > 4 and t.endswith(duoi):
            return t[: -len(duoi)]
    return t


def _pool_is_relevant(pool: list, clean_query: str) -> bool:
    """Có ÍT NHẤT MỘT ứng viên nhắc lại một từ của truy vấn hay không?

    VÌ SAO CẦN: Pexels gần như KHÔNG BAO GIỜ trả 0 kết quả — nó match mờ. Nên bậc thang
    truy vấn một mình là chưa đủ: truy vấn vô vọng vẫn "thành công" và mang về clip sai
    hẳn chủ đề. Đo trên Pexels thật:

        "zoroastrian fire altar"       → 3094 kết quả, khớp 0/6
                                         (day-of-the-dead, woman holding candle in church)
        "quantum entanglement diagram" →  715 kết quả, khớp 0/6
                                         (blue spiral pattern, woman trapped in spider web)
        "closed leather book"          → khớp 3/6    "digging soft soil" → khớp 5/6
        "delicate crystal glasses"     → khớp 2/6    "endless sand dunes" → khớp 4/6

    Ngưỡng cố ý ĐẶT Ở MỨC KHẮT KHE NHẤT (chỉ loại khi TOÀN BỘ pool không khớp lấy một từ)
    để không bao giờ loại oan một kết quả tốt.
    """
    tu_khoa = {_stem(w) for w in clean_query.split() if len(w) > 2}
    if not tu_khoa:
        return True
    co_nhan = False
    for c in pool:
        nhan = str(c.get("_label") or "").replace("-", " ").replace(",", " ").strip()
        if not nhan:
            continue
        co_nhan = True
        if tu_khoa & {_stem(w) for w in nhan.split()}:
            return True
    # Không ứng viên nào có nhãn để đối chiếu → KHÔNG kết luận được, và không kết luận
    # được thì phải cho qua. Chặn ở đây sẽ loại oan cả một nhà cung cấp chỉ vì API của họ
    # đổi tên trường mô tả.
    return not co_nhan


def _select_and_download(
    candidates: list,
    provider: str,
    clean_query: str,
    output_path: str,
    aspect_ratio: str,
    needed_duration: float,
    used_ids: Optional[set],
    out_meta: Optional[dict],
) -> str:
    """Chấm điểm ứng viên → chọn clip tốt nhất → tải về. Dùng CHUNG cho mọi nhà cung cấp.

    Ứng viên phải ở dạng chuẩn hoá kiểu Pexels: {id, width, height, duration, video_files}.
    Tách ra để thêm nhà cung cấp mới không phải chép lại luật chọn clip (chấm điểm khung
    hình/thời lượng/độ phân giải + chống trùng clip trong cùng một job).
    """
    import requests

    _, target_w, target_h = ASPECT_TARGETS.get(aspect_ratio, ASPECT_TARGETS["9:16"])
    target_ratio = target_w / target_h

    if not candidates:
        raise RuntimeError(f"{provider} không có video cho từ khóa: '{clean_query}'")

    if not _pool_is_relevant(candidates, clean_query):
        raise StockIrrelevantError(
            f"{provider} có {len(candidates)} kết quả cho '{clean_query}' nhưng không cái "
            "nào liên quan (match mờ) — bỏ qua để không lấy clip sai chủ đề."
        )

    seen = used_ids if used_ids is not None else set()
    fresh = [v for v in candidates if v.get("id") not in seen]
    # Hết clip mới thì thà dùng lại còn hơn không có hình — nhưng chỉ khi hết thật.
    pool = fresh or candidates
    if not fresh:
        logger.info(f"[StockCurator] Hết clip mới cho '{clean_query}', buộc phải dùng lại.")

    video = min(pool, key=lambda v: _score_stock_candidate(v, target_ratio, target_h, needed_duration))
    files = video.get("video_files", [])
    if not files:
        raise RuntimeError(f"Không tìm thấy link video trong kết quả {provider}.")

    if used_ids is not None and video.get("id") is not None:
        used_ids.add(video["id"])
    if out_meta is not None:
        out_meta["id"] = video.get("id")
        out_meta["provider"] = provider
        out_meta["query"] = clean_query

    # Ưu tiên file ĐỦ độ phân giải rồi mới tới gần target nhất (tránh tải 4K vô ích)
    def _file_score(vf):
        h = vf.get("height") or 0
        if not h:
            return 10 ** 9
        return (h - target_h) if h >= target_h else (target_h - h) * 4

    selected = sorted(files, key=_file_score)[0]

    vw, vh = video.get("width") or 0, video.get("height") or 0
    logger.info(
        f"[StockCurator/{provider}] '{clean_query}': chọn id={video.get('id')} "
        f"{vw}x{vh} {video.get('duration')}s trong {len(pool)} ứng viên "
        f"(cần ~{needed_duration:.1f}s)"
    )

    tmp_path = output_path if output_path.endswith(".mp4") else output_path + ".mp4"
    # stream=True + iter_content: clip stock HD có thể vài chục MB. rv.content buffer
    # TOÀN BỘ response vào RAM trước khi ghi ra đĩa — với video nhiều cảnh tải song
    # song, đỉnh RAM cộng dồn không cần thiết. Ghi thẳng theo từng chunk khi tải về.
    with requests.get(
        selected["link"], headers={"User-Agent": _BROWSER_UA}, timeout=90, stream=True
    ) as rv:
        rv.raise_for_status()
        with open(tmp_path, "wb") as f:
            for chunk in rv.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
    return tmp_path


async def fetch_pexels_video(
    query: str,
    output_path: str,
    aspect_ratio: str,
    api_key: str,
    needed_duration: float = 0.0,
    used_ids: Optional[set] = None,
    out_meta: Optional[dict] = None,
) -> str:
    """
    Tìm và tải video từ Pexels API. Trả về đường dẫn file .mp4.

    QUAN TRỌNG: Pexels API trả 403 Forbidden nếu request THIẾU User-Agent.
    (Đây là lý do trước đây video stock không bao giờ xuất hiện — pipeline luôn
    rơi về ảnh AI tĩnh.) Bắt buộc gửi kèm User-Agent như trình duyệt thật.

    `used_ids`: tập id video đã dùng trong CÙNG một job — để 2 cảnh có từ khoá gần
    giống nhau không nhận về đúng một đoạn phim (lỗi lộ liễu nhất của video stock).

    `out_meta`: dict để hàm ghi lại id clip đã chọn. Caller lưu id này vào cache, và ở
    lần render sau — khi clip lấy thẳng từ cache, không gọi Pexels nữa — vẫn nạp lại
    được id vào `used_ids` để cơ chế chống trùng clip tiếp tục hoạt động.
    """
    import requests

    orientation, _, _ = ASPECT_TARGETS.get(aspect_ratio, ASPECT_TARGETS["9:16"])
    clean_query = query.replace("\n", " ").strip()[:100]
    # per_page 5 → 15: cần đủ ứng viên để chấm điểm mới có cái để chọn.
    url = (
        f"https://api.pexels.com/videos/search?query={urllib.parse.quote(clean_query)}"
        f"&per_page=15&orientation={orientation}"
    )
    headers = {"Authorization": api_key, "User-Agent": _BROWSER_UA}

    def _fetch():
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        videos = r.json().get("videos", [])
        # Pexels không trả tags, nhưng `url` chứa slug mô tả — đó là văn bản duy nhất có
        # thể dùng để đối chiếu độ liên quan (xem _pool_is_relevant).
        for v in videos:
            slug = (v.get("url") or "").rstrip("/").split("/")[-1]
            v["_label"] = "-".join(slug.split("-")[:-1]) or slug
        return _select_and_download(
            videos, "Pexels", clean_query, output_path,
            aspect_ratio, needed_duration, used_ids, out_meta,
        )

    logger.info(f"🔍 Tìm kiếm video Pexels với từ khóa: '{clean_query}'")
    return await asyncio.to_thread(_fetch)


def _pixabay_to_candidate(hit: dict) -> dict:
    """Chuẩn hoá 1 hit Pixabay về đúng dạng ứng viên kiểu Pexels.

    Pixabay KHÔNG trả width/height ở cấp hit (chỉ có trong từng biến thể `videos.*`), và
    API video của họ cũng KHÔNG có tham số `orientation`. Vì vậy phải tự suy kích thước từ
    biến thể lớn nhất rồi để `_score_stock_candidate` lọc theo tỉ lệ khung — nếu không,
    video 16:9 sẽ lọt vào video dọc 9:16 và bị lấp nền mờ hai bên.
    """
    files = []
    for v in (hit.get("videos") or {}).values():
        if isinstance(v, dict) and v.get("url"):
            files.append({
                "height": v.get("height") or 0,
                "width": v.get("width") or 0,
                "link": v["url"],
            })
    best = max(files, key=lambda f: f["height"], default={"width": 0, "height": 0})
    return {
        # Tiền tố nhà cung cấp: id Pixabay và id Pexels là hai không gian số riêng biệt,
        # trộn thẳng vào cùng một `used_ids` sẽ có lúc trùng số một cách vô nghĩa.
        "id": f"pixabay-{hit.get('id')}",
        "width": best["width"],
        "height": best["height"],
        "duration": hit.get("duration") or 0,
        "video_files": files,
        # Pixabay CÓ trả `tags` — chính xác hơn slug URL của Pexels.
        "_label": hit.get("tags") or "",
    }


async def fetch_pixabay_video(
    query: str,
    output_path: str,
    aspect_ratio: str,
    api_key: str,
    needed_duration: float = 0.0,
    used_ids: Optional[set] = None,
    out_meta: Optional[dict] = None,
) -> str:
    """Tìm và tải video từ Pixabay — nhà cung cấp THỨ HAI, catalog khác Pexels.

    VÌ SAO CẦN: trước đây chỉ có Pexels. Pexels trả 0 kết quả (hoặc hết clip mới cho một
    từ khoá) là cả cảnh đó âm thầm đổi sang ảnh AI tĩnh — video thành nửa footage thật nửa
    ảnh tĩnh, lộ ngay khi xem. Pixabay dùng chung luật chấm điểm và chung `used_ids`, nên
    hai nguồn không bao giờ đưa về hai clip giống nhau trong cùng một video.

    Key miễn phí lấy ở https://pixabay.com/api/docs/ — đặt `PIXABAY_API_KEY` trong
    `backend/.env`. Không có key thì tầng này tự bỏ qua.
    """
    import requests

    clean_query = query.replace("\n", " ").strip()[:100]
    url = (
        "https://pixabay.com/api/videos/"
        f"?key={urllib.parse.quote(api_key)}&q={urllib.parse.quote(clean_query)}"
        "&per_page=20&safesearch=true&video_type=film"
    )

    def _fetch():
        r = requests.get(url, headers={"User-Agent": _BROWSER_UA}, timeout=15)
        r.raise_for_status()
        hits = r.json().get("hits", [])
        return _select_and_download(
            [_pixabay_to_candidate(h) for h in hits], "Pixabay", clean_query, output_path,
            aspect_ratio, needed_duration, used_ids, out_meta,
        )

    logger.info(f"🔍 Tìm kiếm video Pixabay với từ khóa: '{clean_query}'")
    return await asyncio.to_thread(_fetch)
