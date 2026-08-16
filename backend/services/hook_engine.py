# backend/services/hook_engine.py
import functools
import logging
import platform as _sys_platform

import numpy as np
from moviepy import (
    ImageClip, ColorClip, CompositeVideoClip, TextClip,
    concatenate_videoclips,
)


from moviepy.video.fx import CrossFadeIn

logger = logging.getLogger(__name__)


def _resolve_font_path(relative_name: str) -> str:
    system = _sys_platform.system()
    if system == "Windows":
        return f"C:/Windows/Fonts/{relative_name}"
    elif system == "Darwin":
        return f"/System/Library/Fonts/{relative_name}"
    else:  # Linux and others
        try:
            import subprocess
            result = subprocess.run(
                ["fc-match", "-f", "%{file}", relative_name],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return f"/usr/share/fonts/truetype/{relative_name}/{relative_name}.ttf"


# Font dùng chung cho MỌI hiệu ứng hook có chữ. PHẢI là đường dẫn file .ttf thật,
# không phải tên họ font: Windows/Pillow không tự dò tên font ra file, và ta đã từng
# ăn lỗi này với "Arial Black" thiếu glyph ư/ơ tiếng Việt — seguibl.ttf (Segoe UI Black)
# là font hệ thống đã xác nhận có đủ dấu tiếng Việt.
HOOK_FONT = _resolve_font_path("seguibl.ttf")

# ==============================================================================
# MONKEY-PATCH MOVIEPY 2.X COMPOSE_MASK BUG
# Lỗi: Khi một clip (hoặc mask của clip) di chuyển RA KHỎI màn hình (ví dụ pos=(x, -875)
# mà height=864, khiến cạnh dưới là y_end = -11), MoviePy tính ra y_start=0, y_end=-11.
# Điều này làm cho numpy slice background_mask[0:-11] trở thành lấy từ 0 tới (N-11),
# gây ra lỗi broadcast shapes (0, 1080) và (1909, 1080).
# Patch: Ép y_end và x_end không bao giờ bị âm, và nếu clip hoàn toàn ra khỏi màn hình
# thì trả về background_mask gốc (không compose gì cả).
# ==============================================================================
import moviepy.video.VideoClip as _vc
from moviepy.video.VideoClip import compute_position as _compute_position

_original_compose_mask = _vc.VideoClip.compose_mask

def _patched_compose_mask(self, background_mask: np.ndarray, t: float) -> np.ndarray:
    ct = t - self.start
    clip_mask = self.get_frame(ct).astype("float")

    bg_h, bg_w = background_mask.shape
    clip_h, clip_w = clip_mask.shape

    pos = self.pos(ct)
    pos = _compute_position((clip_w, clip_h), (bg_w, bg_h), pos, self.relative_pos)

    x_start = int(max(pos[0], 0))
    x_end = int(max(0, min(pos[0] + clip_w, bg_w)))
    y_start = int(max(pos[1], 0))
    y_end = int(max(0, min(pos[1] + clip_h, bg_h)))

    # Fix: Nếu ra khỏi khung hoàn toàn, không compose
    if y_end <= y_start or x_end <= x_start:
        return background_mask

    clip_x_start = int(max(0, -pos[0]))
    clip_x_end = int(clip_x_start + min((x_end - x_start), (clip_w - clip_x_start)))
    clip_y_start = int(max(0, -pos[1]))
    clip_y_end = int(clip_y_start + min((y_end - y_start), (clip_h - clip_y_start)))

    background_mask[y_start:y_end, x_start:x_end] = background_mask[
        y_start:y_end, x_start:x_end
    ] + clip_mask[clip_y_start:clip_y_end, clip_x_start:clip_x_end] * (
        1 - background_mask[y_start:y_end, x_start:x_end]
    )
    return background_mask

_vc.VideoClip.compose_mask = _patched_compose_mask
# ==============================================================================


def _dynamic_opacity(clip, op_func):
    """Áp dụng opacity động theo thời gian cho clip trong MoviePy 2.x (with_opacity chỉ nhận float).

    QUAN TRỌNG: Dùng mask ĐỘNG (VideoClip) thay vì ColorClip tĩnh.
    Nếu clip đã bị resized(lambda t: ...) trước đó, frame.shape thay đổi theo t.
    Mask tĩnh (ColorClip với size cố định) sẽ gây ValueError khi compose_mask
    cố phép tính broadcast giữa (H_dynamic, W) và (H_static, W).
    """
    from moviepy.video.VideoClip import VideoClip as _VideoClip

    def _make_mask_frame(gf, t):
        """Tạo mask frame cùng shape với frame thật của clip tại thời điểm t."""
        frame = gf(t)                           # (H, W) – mask đã là grayscale
        h, w = frame.shape[:2]
        return np.full((h, w), min(1.0, max(0.0, op_func(t))), dtype=np.float32)

    if getattr(clip, "mask", None) is None:
        mask_clip = _VideoClip(lambda t: np.ones((clip.size[1], clip.size[0]), dtype=np.float32)).with_duration(clip.duration)
        clip = clip.with_mask(mask_clip)

    clip.mask = clip.mask.transform(_make_mask_frame)
    return clip


@functools.lru_cache(maxsize=32)
def _load_hook_font(font_size: int):
    """ImageFont.truetype(HOOK_FONT, size) cache theo size — build_typewriter_quote_hook
    gọi lại hàm đo bề rộng chữ (_ngat_dong) một lần cho mỗi mốc thời gian trong timeline,
    mỗi lần đều đọc + parse lại file .ttf từ đĩa dù font/size không đổi giữa các lần gọi."""
    from PIL import ImageFont
    return ImageFont.truetype(HOOK_FONT, font_size)


def _safe_caption_clip(text: str, font_size: int, box_w: int, box_h: int | None = None, **extra) -> TextClip:
    """
    TextClip(method="caption", size=(box_w, None)) tự đo chiều cao NHƯNG THIẾU vài pixel
    khi chữ tràn ≥2 dòng — dòng cuối bị cắt cụt (verify bằng ảnh thật, xảy ra cả khi
    KHÔNG có stroke, nên không phải do viền: MoviePy căn giữa text theo chiều dọc trong
    khung tự đo, khít đến mức không còn chỗ thở). Đo 2 bước: lấy chiều cao tự nhiên rồi
    CỘNG THÊM biên đệm, ép render lại đúng khung đó — dùng cho MỌI TextClip caption nhiều
    dòng trong hook, tránh lặp lại workaround này ở từng hàm.

    Truyền `box_h` để ép chiều cao khung có sẵn (dùng khi cần nhiều clip cùng shape,
    như từng bước của hiệu ứng gõ chữ); để None thì tự đo + đệm.

    KHUNG CỐ ĐỊNH THÌ NEO ĐỈNH, KHÔNG NEO GIỮA. `vertical_align` mặc định của MoviePy là
    "center": khối chữ luôn được căn giữa theo chiều dọc trong khung. Với khung cố định
    (dựng theo câu ĐẦY ĐỦ), lúc chữ mới có 1 dòng nó nằm giữa khung, tới khi mọc dòng thứ
    2 thì khối chữ cao lên và dòng 1 BỊ ĐẨY NGƯỢC LÊN — đo thật: dòng đầu nhảy từ y=61
    lên y=24, tức giật đứng 37px đúng khoảnh khắc xuống dòng. Neo đỉnh cho ra y=4 ở cả
    hai trường hợp: dòng 1 đứng im, dòng mới mọc xuống dưới đúng như máy chữ thật.
    """
    kwargs = dict(font=HOOK_FONT, font_size=font_size, method="caption",
                  text_align="center", **extra)
    if box_h is not None:
        kwargs.setdefault("vertical_align", "top")
        return TextClip(text=text, size=(box_w, box_h), **kwargs)
    probe = TextClip(text=text, size=(box_w, None), **kwargs)
    padded_h = probe.h + 40
    probe.close()
    return TextClip(text=text, size=(box_w, padded_h), **kwargs)


def _ngat_dong(tokens: list, font_size: int, max_w: int, stroke_width: int = 3) -> list:
    """Tự ngắt dòng theo BỀ RỘNG ĐO ĐƯỢC, trả về danh sách các dòng (mỗi dòng là list token).

    VÌ SAO PHẢI TỰ NGẮT thay vì để MoviePy lo: con trỏ máy chữ nằm TRONG chuỗi đem đi đo,
    nên bật/tắt nó làm đổi luôn điểm xuống dòng — đo thật với đúng font/cỡ chữ của hook:
    "Cuốn sách triệu bản suýt bị giấu" vừa khít 1 dòng (103px) nhưng thêm " |" thành 2
    dòng (172px). Trước đây phải bỏ hẳn nhấp nháy để né, đổi lại con trỏ đứng chết dính.

    Tự tính điểm ngắt MỘT LẦN dựa trên chuỗi CÓ con trỏ, rồi ghép lại bằng "\\n" tường
    minh, thì bỏ con trỏ ra không thể làm đổi bố cục nữa — nhấp nháy trở lại an toàn.

    Ngưỡng lấy hụt so với `max_w` (trừ viền chữ + đệm) để MoviePy không tự ngắt lại theo
    ngưỡng của nó và phá mất bố cục ta vừa tính.
    """
    try:
        font = _load_hook_font(font_size)
    except Exception:
        logger.warning("[Typewriter] Không đo được bề rộng chữ — dồn hết vào một dòng.")
        return [list(tokens)]

    nguong = max(1, max_w - 2 * stroke_width - 8)

    def _rong(cum: list) -> int:
        s = " ".join(cum)
        bbox = font.getbbox(s)
        return bbox[2] - bbox[0]

    dong, hien_tai = [], []
    for tk in tokens:
        if hien_tai and _rong(hien_tai + [tk]) > nguong:
            dong.append(hien_tai)
            hien_tai = [tk]
        else:
            hien_tai.append(tk)
    if hien_tai:
        dong.append(hien_tai)
    return dong


def _hook_caption_overlay(
    text: str,
    w: int,
    h: int,
    duration: float,
    delay: float = 0.0,
    y_frac: float = 0.80,
    font_size_frac: float = 0.055,
    color: str = "white",
    stroke_color: str = "black",
    stroke_width: int = 4,
    fade: float = 0.35,
):
    """
    Chữ trích dẫn DÙNG CHUNG cho 4 hook thuần hiệu ứng hình (camera_shutter/cyber_glitch/
    vintage_film_burn/breathing_vignette) — trước đây 4 hàm này KHÔNG nhận tham số chữ
    nào cả, chỉ là bộ lọc phủ lên ảnh bìa. Hậu quả: hook không truyền tải được lời hứa/
    câu hỏi nào trong giây đầu, dù đây chính là nhiệm vụ cốt lõi của một "hook" — người
    xem chỉ thấy hiệu ứng đẹp mà không biết VÌ SAO nên ở lại xem tiếp.

    `delay` để chữ xuất hiện SAU khi hiệu ứng riêng (chớp máy ảnh, glitch...) chạy xong,
    tránh chữ bị hiệu ứng che/xé ngay lúc vừa hiện ra. Trả None nếu không có chữ, để
    caller chỉ nối layer khi thực sự cần (giữ hành vi cũ y hệt nếu người dùng không nhập
    trích dẫn cho hook này).
    """
    text = (text or "").strip()
    if not text:
        return None
    clip_dur = max(0.1, duration - delay)
    txt = _safe_caption_clip(
        text, int(w * font_size_frac), int(w * 0.85),
        color=color, stroke_color=stroke_color, stroke_width=stroke_width,
    )
    # Kẹp trong [20, h-txt.h-20]: y_frac chỉ là điểm neo MONG MUỐN cho trích dẫn ngắn
    # (1-2 dòng). Trích dẫn dài hơn dự kiến (người dùng tự nhập, không giới hạn độ dài)
    # sẽ có txt.h lớn — nếu không kẹp, nửa dưới khối chữ tràn thẳng qua mép đáy khung
    # hình (đã thấy thật khi test với câu dài 4 dòng: dòng cuối gần như mất hẳn).
    y = max(20, min(int(h * y_frac - txt.h / 2), h - txt.h - 20))
    return (
        txt.with_position(("center", y))
        .with_start(delay)
        .with_duration(clip_dur)
        .with_effects([CrossFadeIn(min(fade, clip_dur / 2))])
    )

# ── Thông số Hook Máy Xèng — NGUỒN CHÂN LÝ DUY NHẤT ──────────────────────
# Pha trục quay dài bao lâu và lướt qua bao nhiêu bìa. Bốn chỗ khác PHẢI khớp,
# đổi ở đây thì phải đổi hết, nếu không hình và tiếng lệch nhau:
#   • video_service.HOOK_CAROUSEL_DURATION = SLOT_DURATION + 2.5 (pha Quote giữ nguyên 2.5s)
#   • video_service.HOOK_NARRATION_LEAD    = SLOT_DURATION + 0.35
#   • video_service: mốc đặt tiếng "ding" — đã import SLOT_DURATION nên tự khớp
#   • tools/make_reel_sfx.py (SLOT_DUR, NUM_FAKES) và tools/fit_hook_sfx.py
#     (TARGET_DUR = SLOT_DURATION + 0.18) → sửa xong PHẢI CHẠY LẠI để sinh lại
#     reel_*.wav, vì file .wav cũ đã nướng cứng độ dài pha quay vào trong nó.
SLOT_DURATION = 2.0   # giây — độ dài pha trục quay
NUM_FAKES = 8         # số bìa giả lướt qua trước khi chốt vào bìa thật


def _blurred_fill_bg(
    cover_path: str,
    w: int,
    h: int,
    duration: float,
    darken: float = 0.5,
    blur: int = 35,
    zoom_to: float = 0.0,
):
    """
    Nền LẤP ĐẦY khung 9:16 = bản phóng to + làm mờ của chính bìa (bỏ viền đen).

    `blur`    bán kính Gaussian. 35 là mức "xoá sạch chi tiết" — hợp khi nền chỉ để
              lấp khung phía sau một khối nội dung khác, KHÔNG hợp khi nó là toàn bộ
              thứ người xem nhìn thấy trong nhiều giây (xem zoom_to).
    `zoom_to` >1.0 thì nền phóng chậm LIÊN TỤC từ 1.0 tới mức này trong suốt `duration`
              (Ken Burns). Mặc định 0.0 = đứng yên, giữ nguyên hành vi cũ cho các hook
              vốn đã có chuyển động riêng.

              VÌ SAO CẦN: ImageClip là MỘT khung hình bất động. Hook nào không tự có
              chuyển động hình sẽ ĐỨNG HÌNH TUYỆT ĐỐI suốt thời lượng của nó — đã đo
              được đúng 2.75 giây bất động ở đầu một video thật (lệch giữa các khung
              chỉ 0.01/255). Đây cùng một lớp lỗi đã phải vá cho camera_shutter và
              cyber_glitch trước đây; chỗ nào dựng nền từ ImageClip tĩnh cũng dính.
    """
    try:
        from PIL import Image, ImageFilter
        if cover_path.endswith(".mp4"):
            from moviepy.video.io.VideoFileClip import VideoFileClip
            with VideoFileClip(cover_path) as v:
                frame = v.get_frame(0)
            img = Image.fromarray(frame).convert("RGB")
        else:
            img = Image.open(cover_path).convert("RGB")

        scale = max(w / img.width, h / img.height)
        nw, nh = int(img.width * scale) + 2, int(img.height * scale) + 2
        img = img.resize((nw, nh)).filter(ImageFilter.GaussianBlur(blur))
        left, top = (nw - w) // 2, (nh - h) // 2
        img = img.crop((left, top, left + w, top + h))
        arr = (np.array(img).astype(np.float32) * darken).astype(np.uint8)
        clip = ImageClip(arr).with_duration(duration)
        if zoom_to and zoom_to > 1.0 and duration > 0:
            # CHỈ phóng TO (≥1.0), không bao giờ thu nhỏ: nền phải phủ kín khung ở mọi
            # thời điểm, tụt dưới 1.0 là hở mép. Phải kèm with_position("center"), nếu
            # không CompositeVideoClip neo góc trái-trên và nền trôi chéo thay vì phóng
            # từ tâm.
            _k = (zoom_to - 1.0) / duration
            clip = clip.resized(lambda t: 1.0 + _k * t).with_position("center")
        return clip
    except Exception as e:
        logger.warning(f"Blurred BG error: {e}")
        return ColorClip((w, h), color=(15, 15, 25)).with_duration(duration)


def build_carousel_hook(
    cover_image_path: str,
    quote_text: str,
    video_width: int,
    video_height: int,
    duration: float = 4.5,
) -> CompositeVideoClip:
    """
    Clip mở màn với hiệu ứng Slot Machine (trục quay) + Quote Reveal.
    0.0s - 2.0s: Chuỗi bìa giả cuộn dọc tốc độ cao, dừng chốt ở bìa thật.
    2.0s - End : Bìa thật nảy nhẹ, hiện Quote.
    """
    w, h = video_width, video_height
    slot_dur = SLOT_DURATION
    
    import os
    import glob
    import random
    from PIL import Image, ImageOps, ImageFilter
    import numpy as np

    # ── Bìa thật (fit vào tỷ lệ an toàn tùy theo màn dọc hay ngang) ──
    try:
        if cover_image_path.endswith(".mp4"):
            from moviepy.video.io.VideoFileClip import VideoFileClip
            with VideoFileClip(cover_image_path) as v:
                cover_img = Image.fromarray(v.get_frame(0))
        else:
            cover_img = ImageOps.exif_transpose(Image.open(cover_image_path)).convert("RGBA")
            
        is_landscape = w > h
        if is_landscape:
            fit = min(w * 0.4 / cover_img.width, h * 0.7 / cover_img.height)
        else:
            fit = min(w * 0.72 / cover_img.width, h * 0.46 / cover_img.height)
    except Exception as e:
        logger.warning(f"Hook cover error: {e}")
        cover_img = Image.new("RGBA", (int(w * 0.6), int(h * 0.4)), (230, 230, 230, 255))
        fit = 1.0
        is_landscape = w > h

    cw, ch = int(cover_img.width * fit), int(cover_img.height * fit)
    real_img = cover_img.resize((cw, ch), Image.Resampling.LANCZOS)
    
    cy = int(h / 2 - ch / 2)
    if is_landscape:
        cy = int(h * 0.1)

    # ── Nền mờ ──
    bg = _blurred_fill_bg(cover_image_path, w, h, duration, darken=0.4)

    # ── Phase 1: Slot Machine (Strip cuộn dọc) ──
    # Tìm các bìa giả
    slot_covers_dir = os.path.join(os.path.dirname(__file__), "..", "assets", "slot_covers")
    fake_paths = []
    if os.path.isdir(slot_covers_dir):
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG", "*.JPEG"):
            fake_paths.extend(glob.glob(os.path.join(slot_covers_dir, ext)))
            
    if fake_paths:
        selected_fakes = [random.choice(fake_paths) for _ in range(NUM_FAKES)]
    else:
        selected_fakes = [cover_image_path] * NUM_FAKES

    gap = int(ch + h * 0.04) # Khoảng cách giữa các bìa
    strip_h = gap * NUM_FAKES + ch
    strip_img = Image.new('RGBA', (cw, strip_h), (0,0,0,0))
    
    # Bìa thật ở cuối (nằm ở toạ độ 0 theo trục Y của strip để nó dừng ở cuối chu trình)
    strip_img.paste(real_img, (0, 0))
    
    # Gắn bìa giả vào phần trên của strip
    for i, fake_path in enumerate(selected_fakes):
        try:
            fake_img = ImageOps.exif_transpose(Image.open(fake_path)).convert("RGBA")
            aspect_ratio = cw / ch
            f_ar = fake_img.width / fake_img.height
            if f_ar > aspect_ratio:
                new_w = int(fake_img.height * aspect_ratio)
                left = (fake_img.width - new_w) // 2
                fake_img = fake_img.crop((left, 0, left + new_w, fake_img.height))
            elif f_ar < aspect_ratio:
                new_h = int(fake_img.width / aspect_ratio)
                top = (fake_img.height - new_h) // 2
                fake_img = fake_img.crop((0, top, fake_img.width, top + new_h))
                
            f_img = fake_img.resize((cw, ch), Image.Resampling.LANCZOS)
        except Exception:
            f_img = Image.new("RGBA", (cw, ch), (150, 150, 150, 255))
        
        strip_img.paste(f_img, (0, (i + 1) * gap))

    strip_clip = ImageClip(np.array(strip_img)).with_duration(slot_dur)

    # Hiệu ứng cuộn: ease out cubic
    def slot_y(t):
        p = t / slot_dur
        ease = 1 - (1 - p) ** 3
        start_y = cy - NUM_FAKES * gap
        end_y = cy
        return int(start_y + (end_y - start_y) * ease)

    strip_clip = strip_clip.with_position(lambda t: ("center", slot_y(t)))

    # ── Phase 2: Bìa thật dừng và Quotes ──
    def bounce_y(t):
        t_bounce = min(t, 0.4)
        bounce = np.sin(t_bounce * np.pi / 0.4) * 15 * (1 - t_bounce/0.4)
        return int(cy + bounce)
        
    real_clip = (
        ImageClip(np.array(real_img))
        .with_position(lambda t: ("center", bounce_y(t)))
        .with_start(slot_dur)
        .with_duration(duration - slot_dur)
    )

    layers = [bg, strip_clip, real_clip]

    # ── Trích dẫn (nếu có) ──
    if quote_text and quote_text.strip():
        quote_clip = _safe_caption_clip(
            text=quote_text.strip(),
            font_size=60,
            box_w=int(w * 0.88),
            color="white",
            stroke_color="black",
            stroke_width=4,
        )
        if is_landscape:
            text_y = int(cy + ch + 30)
        else:
            # ĐẶT TRÊN bìa (khoảng nền mờ trống phía trên), KHÔNG đặt dưới bìa như
            # trước (h*0.74 cố định): bìa dọc luôn được canh GIỮA khung theo chiều
            # dọc (cy = h/2 - ch/2) nên khoảng trống PHÍA DƯỚI bìa trùng thẳng vào
            # đúng vùng phụ đề lời dẫn bám đáy khung (Alignment=2, MarginV=250 —
            # xem generate_ass_file). Hậu quả thật đã thấy: quote 2 dòng và phụ đề
            # đè chồng lên nhau không đọc nổi, đúng lúc narration bắt đầu ở
            # HOOK_NARRATION_LEAD (2.35s) — tức giây đầu quan trọng nhất của hook.
            # Khoảng trống PHÍA TRÊN bìa (0..cy) không phụ thuộc size bìa và
            # KHÔNG BAO GIỜ có phụ đề vẽ tới, nên luôn an toàn.
            text_y = max(20, int((cy - quote_clip.h) / 2))
        txt_clip = (
            quote_clip
            .with_position(("center", text_y))
            .with_start(slot_dur + 0.1)
            .with_duration(duration - slot_dur - 0.1)
            .with_effects([CrossFadeIn(0.5)])
        )
        layers.append(txt_clip)

    return CompositeVideoClip(layers, size=(w, h)).with_duration(duration)

# ══════════════════════════════════════════════════════════════════════
# HOOK A2: Typewriter Quote
# ══════════════════════════════════════════════════════════════════════
def build_typewriter_quote_hook(
    quote_text: str,
    video_width: int,
    video_height: int,
    duration: float = 2.5,
    cover_image_path: str = "",
    instant: bool = False,
) -> CompositeVideoClip:
    '''Nền tối, câu trích dẫn hiện dần theo TỪ (typewriter thật, không phải crossfade nguyên khối).

    `instant=True` (dùng cho OUTRO): bỏ hẳn animation gõ chữ, hiện TRỌN câu ngay từ
    khung hình đầu. Kiểu gõ dần hợp để "câu view" ở hook (tạo tò mò xem gõ ra chữ gì),
    nhưng ở outro thì ngược tác dụng — người xem đã sẵn sàng lướt đi, bắt họ CHỜ đọc
    hết câu chỉ làm mất thêm vài trăm ms mà không đổi lại gì.'''
    if cover_image_path:
        # blur 35 → 20 và darken 0.6 → 0.66: ở mức cũ, ĐO TRÊN VIDEO THẬT thì 3 giây mở
        # đầu chỉ là một khối nâu-xanh không nhận ra nổi đó là bìa sách gì. Nền của hook
        # này không nấp sau thứ gì khác — nó chiếm trọn khung suốt thời lượng, nên phải
        # còn đủ nhận dạng. Vẫn thừa tương phản cho chữ trắng viền đen nằm trên.
        # zoom_to: xem chú thích ĐỨNG HÌNH TUYỆT ĐỐI ở _blurred_fill_bg.
        bg = _blurred_fill_bg(
            cover_image_path, video_width, video_height, duration,
            darken=0.66, blur=20, zoom_to=1.06,
        )
    else:
        bg = ColorClip(size=(video_width, video_height), color=(15, 15, 20)).with_duration(duration)

    text = (quote_text or "").strip()
    if not text:
        return bg

    # Khớp với các hook có chữ khác (_hook_caption_overlay và blackout_question đều dùng
    # 0.055 / 0.85): trước đây typewriter là hook chữ NHỎ NHẤT (0.05 / 0.8) dù chữ chính
    # là toàn bộ nội dung nó hiển thị.
    box_w = int(video_width * 0.85)
    font_size = int(video_width * 0.055)
    style = dict(color="white", stroke_color="black", stroke_width=3)

    if instant:
        try:
            txt = (
                _safe_caption_clip(text, font_size, box_w, **style)
                .with_position("center")
                .with_duration(duration)
                .with_effects([CrossFadeIn(0.2)])
            )
            return CompositeVideoClip([bg, txt], size=(video_width, video_height)).with_duration(duration)
        except Exception as e:
            logger.error(f"Typewriter hook (instant) error: {e}")
            return bg

    try:
        # Đo khung chữ bằng CÂU ĐẦY ĐỦ một lần duy nhất qua _safe_caption_clip (đã lo
        # sẵn biên đệm chống cắt dòng cuối), rồi ép MỌI bước hiện chữ dùng đúng
        # size=(box_w, canvas_h) cố định đó — TextClip với size cố định luôn trả về
        # cùng shape mảng dù text ngắn hơn (đã verify); thiếu bước này thì mỗi bước gõ
        # chữ ra kích thước ảnh khác nhau, concatenate_videoclips vỡ ngay.
        # Con trỏ KHÔNG còn tham gia phép ngắt dòng: _ngat_dong() tính điểm ngắt MỘT LẦN
        # trên chuỗi CÓ con trỏ rồi ghép lại bằng "\n" tường minh, nên bỏ con trỏ ra không
        # thể làm đổi bố cục. Nhờ vậy khôi phục được nhấp nháy mà không tái phát cú giật
        # ngang của bản cũ (xem chú thích ở _ngat_dong).
        CURSOR = "|"
        words = text.split()
        n_words = len(words)

        def _chuoi(so_tu: int, hien_con_tro: bool) -> str:
            dong = _ngat_dong(words[:so_tu] + [CURSOR], font_size, box_w,
                              style["stroke_width"])
            if not hien_con_tro:
                # Bỏ ĐÚNG token con trỏ, giữ nguyên mọi điểm ngắt dòng. Dòng cuối có thể
                # thành rỗng — vẫn phải giữ lại để số dòng (và chiều cao) không đổi.
                dong = [list(d) for d in dong]
                dong[-1] = dong[-1][:-1]
            return "\n".join(" ".join(d) for d in dong)

        probe = _safe_caption_clip(_chuoi(n_words, True), font_size, box_w, **style)
        canvas_h = probe.h
        probe.close()

        # Gõ xong ở 85% thời lượng, giữ nguyên câu đủ ở 15% cuối trước khi cắt sang cảnh 1 —
        # gõ xong đúng lúc cắt cảnh sẽ khiến người xem không kịp đọc trọn câu.
        reveal_dur = duration * 0.85
        steps = max(1, min(n_words, 24))  # trần 24 bước: câu dài không dựng quá nhiều TextClip
        step_dur = reveal_dur / steps

        # Cắt dòng thời gian tại HỢP của hai loại mốc: mốc gõ thêm từ, và mốc nhấp nháy.
        # Gộp nhịp nháy vào nhịp gõ (bản cũ nháy theo i%2) khiến tốc độ nháy chạy theo độ
        # dài câu — câu 20 từ thì con trỏ giật liên hồi, câu 4 từ thì nháy ì ạch.
        NHAY = 0.45  # nửa chu kỳ, xấp xỉ con trỏ dòng lệnh thật
        moc = {0.0, duration, reveal_dur}
        moc |= {i * step_dur for i in range(steps + 1)}
        moc |= {k * NHAY for k in range(int(duration / NHAY) + 2)}
        moc = sorted(m for m in moc if 0.0 <= m <= duration)

        cleaned_moc = []
        for m in moc:
            if not cleaned_moc:
                cleaned_moc.append(m)
            elif m - cleaned_moc[-1] < 0.02:
                if m in (duration, reveal_dur):
                    cleaned_moc[-1] = m
            else:
                cleaned_moc.append(m)

        clips = []
        for a, b in zip(cleaned_moc, cleaned_moc[1:]):
            if a >= reveal_dur:
                so_tu = n_words
            else:
                buoc = int(a / step_dur) + 1
                so_tu = max(1, min(n_words, round(n_words * buoc / steps)))
            # Pha nháy tính NGƯỢC TỪ ĐIỂM KẾT THÚC, không phải từ t=0. Hai lý do:
            #  - khung hình cuối trước lúc cắt sang Cảnh 1 luôn rơi vào nhịp TẮT, nên
            #    không đọng lại dấu '|' bất động (bản trước gõ cứng con trỏ vào cả pha
            #    giữ, nhìn như gõ thừa phím chứ không phải hiệu ứng);
            #  - đếm xuôi rồi ép tắt riêng khoảng cuối thì hai luật chồng nhau, ĐO ĐƯỢC
            #    con trỏ tắt liền 0.77s cuối — một quãng chết ngay lúc câu vừa hiện đủ.
            hien = int((duration - a) / NHAY) % 2 == 1
            clips.append(
                _safe_caption_clip(_chuoi(so_tu, hien), font_size, box_w,
                                   box_h=canvas_h, **style).with_duration(b - a)
            )

        txt_anim = concatenate_videoclips(clips).with_position("center")
        return CompositeVideoClip([bg, txt_anim], size=(video_width, video_height)).with_duration(duration)
    except Exception as e:
        logger.error(f"Typewriter hook error: {e}")
        return bg


# ══════════════════════════════════════════════════════════════════════
# HOOK C3: Breathing Vignette
# ══════════════════════════════════════════════════════════════════════
def _radial_dist(w: int, h: int) -> np.ndarray:
    """
    Khoảng cách CHUẨN HOÁ từ tâm khung (ellip theo tỉ lệ khung hình: 1.0 = chạm điểm
    giữa mép ngắn nhất, ~1.41 = chạm góc xa nhất). Dùng chung cho vignette tối góc VÀ
    mask "đốm sáng loang" của breathing hook bên dưới — cùng một hệ toạ độ hình học thì
    2 hiệu ứng luôn khớp tâm, không cần tính lại 2 lần.
    """
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = w / 2.0, h / 2.0
    return np.sqrt(((xx - cx) / (w / 2.0)) ** 2 + ((yy - cy) / (h / 2.0)) ** 2)


# ══════════════════════════════════════════════════════════════════════
# HOOK A1: Blackout Question (Màn đen câu hỏi)
# ══════════════════════════════════════════════════════════════════════
def build_blackout_question_hook(
    quote_text: str,
    video_width: int,
    video_height: int,
    duration: float = 1.5,
    cover_image_path: str = "",
) -> CompositeVideoClip:
    """Màn hình đen với câu hỏi/tiêu đề hiện theo pop-in ở đầu.

    Dùng nền đen tuyệt đối để tương phản cao với chữ trắng. Nền có chuyển
    động Ken Burns (zoom chậm) để tránh đứng hình tuyệt đối — cùng lớp lỗi
    đã vá cho typewriter_quote qua `_blurred_fill_bg`.

    `duration` có thể cố định hoặc động (qua DYNAMIC_DURATION_HOOKS /
    resolve_hook_timing), tuỳ user chọn trên UI.
    """
    layers: list = []

    # Nền đen tuyệt đối với Ken Burns nhẹ để tránh đứng hình tuyệt đối.
    # zoom_to=1.04 tạo độ lệch ~0.2/255 giữa các khung — vừa đủ để test
    # nền chuyển động đo được mà không gây chú ý cho người xem.
    if cover_image_path:
        try:
            bg = _blurred_fill_bg(
                cover_image_path, video_width, video_height, duration,
                darken=0.88, blur=45, zoom_to=1.04,
            )
        except Exception:
            bg = ColorClip((video_width, video_height), color=(10, 10, 15)).with_duration(duration)
    else:
        bg = ColorClip((video_width, video_height), color=(10, 10, 15)).with_duration(duration)
    layers.append(bg)

    text = (quote_text or "").strip()
    if not text:
        return CompositeVideoClip(layers, size=(video_width, video_height)).with_duration(duration)

    # Chữ to giữa màn hình, pop-in ở đầu rồi đứng yên
    box_w = int(video_width * 0.85)
    font_size = int(video_width * 0.065)   # lớn hơn typewriter một chút — không có nền mờ che
    style = dict(color="white", stroke_color="black", stroke_width=4)

    try:
        txt_clip = _safe_caption_clip(text, font_size, box_w, **style).with_duration(duration)

        # Pop-in: chữ nhảy từ scale 0 → 1 trong ~0.2s đầu, rồi đứng yên
        POP_DUR = 0.2
        pop_in = txt_clip.with_position("center")

        # scale tạo animation pop-in mượt (hỗ trợ moviepy v2)
        try:
            scaled = pop_in.resized(lambda t: min(1.0, max(0.01, t / POP_DUR)))
        except Exception:
            # fallback: crossfade thường
            scaled = pop_in.with_effects([CrossFadeIn(POP_DUR)])

        # Giữ chữ đứng yên phần còn lại
        stay = (
            txt_clip
            .with_position("center")
            .with_start(POP_DUR)
            .with_duration(max(0.05, duration - POP_DUR))
        )

        layers.append(scaled)
        layers.append(stay)
    except Exception as e:
        logger.warning(f"Blackout question text render error: {e}")

    return CompositeVideoClip(layers, size=(video_width, video_height)).with_duration(duration)


# ══════════════════════════════════════════════════════════════════════
# HOOK C4: Camera Shutter (Nháy máy ảnh)
# ══════════════════════════════════════════════════════════════════════
def build_camera_shutter_hook(
    cover_image_path: str,
    video_width: int,
    video_height: int,
    duration: float = 2.0,
    quote_text: str = "",
) -> CompositeVideoClip:
    '''Chớp nháy trắng lóa mỏng 0.15s, sau đó ảnh bị thu nhỏ lại (chụp ảnh) và đứng yên.'''
    from PIL import Image, ImageOps

    try:
        if cover_image_path.endswith(".mp4"):
            from moviepy.video.io.VideoFileClip import VideoFileClip
            with VideoFileClip(cover_image_path) as v:
                img = Image.fromarray(v.get_frame(0))
        else:
            img = ImageOps.exif_transpose(Image.open(cover_image_path)).convert("RGB")

        img_filled = ImageOps.fit(img, (video_width, video_height), Image.Resampling.LANCZOS)
        base_clip = ImageClip(np.array(img_filled)).with_duration(duration)
    except Exception as e:
        logger.error(f"Camera Shutter cover error: {e}")
        base_clip = ColorClip(size=(video_width, video_height), color=(30, 30, 30)).with_duration(duration)

    # Nền mờ cho phần viền (khi ảnh bị thu nhỏ)
    bg = _blurred_fill_bg(cover_image_path, video_width, video_height, duration, darken=0.3)

    # Freeze frame sau flash chớp (sau 0.15s, thu nhỏ lại một chút 0.92 scale), rồi zoom
    # RẤT CHẬM 0.92→0.97 suốt phần còn lại. LỖI CŨ: đứng yên tuyệt đối 1.85/2.0 giây sau
    # cú chớp — đo bằng render thật thấy y hệt một khung hình chết, dễ khiến người xem
    # tưởng video bị treo/lỗi đúng lúc quan trọng nhất.
    def resize_shutter(t):
        if t < 0.15:
            return 1.05
        p = min(1.0, (t - 0.15) / max(duration - 0.15, 1e-6))
        return 0.92 + 0.05 * p

    photo_clip = base_clip.resized(resize_shutter).with_position("center")
    
    # Flash chớp trắng (0 -> 0.15s)
    flash = ColorClip(size=(video_width, video_height), color=(255, 255, 255)).with_duration(0.15).with_opacity(0.8)

    layers = [bg, photo_clip, flash]
    # Delay 0.3s: chờ ảnh co lại xong (t=0.15s) rồi mới hiện chữ, giống caption dưới
    # một tấm ảnh polaroid vừa "rửa" xong — hiện ngay lúc co sẽ bị cảm giác giật cùng lúc.
    caption = _hook_caption_overlay(quote_text, video_width, video_height, duration, delay=0.3, y_frac=0.84)
    if caption is not None:
        layers.append(caption)

    return CompositeVideoClip(layers, size=(video_width, video_height)).with_duration(duration)


# ══════════════════════════════════════════════════════════════════════
# HOOK C5: Cyber Glitch (Nhiễu sóng)
# ══════════════════════════════════════════════════════════════════════
def _glitch_caption_layers(text: str, w: int, h: int, duration: float, delay: float = 0.45, y_frac: float = 0.78):
    """
    Chữ nhấn kiểu 'chromatic aberration' cho cyber_glitch: 2 lớp màu đỏ/lục-lam lệch
    vài pixel đằng sau lớp trắng chính — giống ảnh RGB tách kênh của chính hiệu ứng
    glitch trên ảnh bìa (glitch_filter ở dưới), thay vì dùng lại pop-in trắng thuần
    của các hook khác (nhạt, không khớp tinh thần "nhiễu sóng số" của hiệu ứng này).
    """
    text = (text or "").strip()
    if not text:
        return []
    clip_dur = max(0.1, duration - delay)
    box_w = int(w * 0.85)
    fs = int(w * 0.055)
    red = _safe_caption_clip(text, fs, box_w, color="#FF2A2A")
    cyan = _safe_caption_clip(text, fs, box_w, color="#2AFFEA")
    white = _safe_caption_clip(text, fs, box_w, color="white", stroke_color="black", stroke_width=3)
    # Kẹp trong khung — xem lý do ở _hook_caption_overlay (câu dài tự nhập có thể cao
    # hơn dự kiến, tràn quá mép đáy nếu chỉ neo cứng theo y_frac).
    y = max(20, min(int(h * y_frac - white.h / 2), h - white.h - 20))
    shift = max(2, int(w * 0.004))
    fade = min(0.2, clip_dur / 2)
    layers = []
    # Toạ độ x TĨNH (không phải hàm theo t): lệch màu ở đây chỉ là một ảnh ghost cố
    # định, không animate — dùng số nguyên thẳng, tránh bẫy late-binding của Python
    # closure nếu để lambda bắt biến vòng lặp `clip`/`dx` theo tham chiếu.
    for clip, dx in ((red, -shift), (cyan, shift)):
        x = int(w / 2 - clip.w / 2 + dx)
        layers.append(
            clip.with_position((x, y)).with_start(delay).with_duration(clip_dur)
            .with_effects([CrossFadeIn(fade)])
        )
    layers.append(
        white.with_position(("center", y)).with_start(delay).with_duration(clip_dur)
        .with_effects([CrossFadeIn(fade)])
    )
    return layers


def build_cyber_glitch_hook(
    cover_image_path: str,
    video_width: int,
    video_height: int,
    duration: float = 2.0,
    quote_text: str = "",
) -> CompositeVideoClip:
    '''Nhiễu sọc ngang, nháy đen trắng vài khung hình đầu.'''
    from PIL import Image, ImageOps

    try:
        if cover_image_path.endswith(".mp4"):
            from moviepy.video.io.VideoFileClip import VideoFileClip
            with VideoFileClip(cover_image_path) as v:
                img = Image.fromarray(v.get_frame(0))
        else:
            img = ImageOps.exif_transpose(Image.open(cover_image_path)).convert("RGB")

        img_filled = ImageOps.fit(img, (video_width, video_height), Image.Resampling.LANCZOS)
        base_clip = ImageClip(np.array(img_filled)).with_duration(duration)
    except Exception as e:
        logger.error(f"Glitch cover error: {e}")
        base_clip = ColorClip(size=(video_width, video_height), color=(30, 30, 30)).with_duration(duration)

    # Zoom rất nhẹ xuyên suốt để khung hình không "chết" hẳn giữa các đợt glitch.
    def resize_func(t):
        return 1.0 + 0.03 * (t / duration)

    zoomed = base_clip.resized(resize_func).with_position("center")

    # LỖI CŨ: glitch chỉ nổ ĐÚNG MỘT LẦN trong 0.4s đầu — 1.6/2.0 giây còn lại đứng hình
    # tuyệt đối (đo bằng render thật: y hệt khung hình chết, phản tác dụng với chính cái
    # tên "nhiễu sóng"). Giờ lặp lại một đợt glitch NGẮN mỗi BURST_PERIOD giây suốt hook.
    BURST_PERIOD = 0.7
    BURST_LEN = 0.18

    def glitch_filter(get_frame, t):
        frame = get_frame(t)
        local = t % BURST_PERIOD
        if local < BURST_LEN:
            p = local / BURST_LEN  # tiến độ 0..1 TRONG đợt hiện tại
            # Nháy âm bản ở giữa đợt
            if 0.25 < p < 0.45:
                frame = 255 - frame
            # Dịch sọc ngang (RGB split giả) suốt phần lớn đợt
            if p < 0.75:
                shift = int(video_width * 0.035)
                frame_shifted = np.copy(frame)
                frame_shifted[:, shift:, 0] = frame[:, :-shift, 0]
                return frame_shifted
        return frame

    glitched = zoomed.transform(glitch_filter)
    layers = [glitched] + _glitch_caption_layers(quote_text, video_width, video_height, duration)
    return CompositeVideoClip(layers, size=(video_width, video_height)).with_duration(duration)


# ══════════════════════════════════════════════════════════════════════
# HOOK C6: Vintage Film Burn (Cháy phim)
# ══════════════════════════════════════════════════════════════════════
def build_fallback_hook(
    cover_image_path: str,
    video_width: int,
    video_height: int,
    duration: float,
) -> CompositeVideoClip:
    """
    Lớp phủ TỐI GIẢN dùng khi một builder hiệu ứng ném lỗi: chỉ ảnh bìa, hơi zoom.

    VÌ SAO CẦN: main.py dời toàn bộ timeline theo resolve_hook_timing() TRƯỚC khi render,
    dựa trên hiệu ứng người dùng chọn chứ không dựa trên việc builder có dựng nổi hay
    không. Nên khi một builder chết, cảnh 1 vẫn bắt đầu muộn đúng chừng ấy giây mà KHÔNG
    CÓ GÌ lấp vào — khán giả nhận một khoảng đen câm ngay đầu video. Đã xảy ra thật với
    vintage_film_burn: 2.5 giây đen (19/255) và im lặng (−124 dB).

    Hàm này không cứu được hiệu ứng, nhưng biến "đen câm" thành "một khung hình tĩnh" —
    xấu hơn ý đồ, còn hơn là mất trắng khoảnh khắc giữ chân người xem.
    """
    from PIL import Image, ImageOps

    try:
        if str(cover_image_path).lower().endswith((".mp4", ".mov")):
            from moviepy.video.io.VideoFileClip import VideoFileClip
            with VideoFileClip(cover_image_path) as v:
                img = Image.fromarray(v.get_frame(0))
        else:
            img = ImageOps.exif_transpose(Image.open(cover_image_path)).convert("RGB")
        filled = ImageOps.fit(img, (video_width, video_height), Image.Resampling.LANCZOS)
        base = ImageClip(np.array(filled)).with_duration(duration)
    except Exception as e:
        # Không còn gì để cứu — ít nhất cho một nền xám thay vì đen tuyền.
        logger.warning("[Hook] Lớp phủ dự phòng cũng không đọc được ảnh bìa: %s", e)
        base = ColorClip(size=(video_width, video_height), color=(24, 24, 28)).with_duration(duration)

    zoomed = (
        base.resized(lambda t: 1.04 - 0.02 * (t / max(duration, 1e-6)))
        .with_position("center")
        .with_duration(duration)
    )
    return CompositeVideoClip([zoomed], size=(video_width, video_height)).with_duration(duration)


def build_vintage_film_burn_hook(
    cover_image_path: str,
    video_width: int,
    video_height: int,
    duration: float = 2.5,
    quote_text: str = "",
) -> CompositeVideoClip:
    '''Vệt sáng màu cam/đỏ mờ lan tỏa trên khung hình phim cổ điển.'''
    from PIL import Image, ImageOps

    try:
        if cover_image_path.endswith(".mp4"):
            from moviepy.video.io.VideoFileClip import VideoFileClip
            with VideoFileClip(cover_image_path) as v:
                img = Image.fromarray(v.get_frame(0))
        else:
            img = ImageOps.exif_transpose(Image.open(cover_image_path)).convert("RGB")

        img_filled = ImageOps.fit(img, (video_width, video_height), Image.Resampling.LANCZOS)
        base_clip = ImageClip(np.array(img_filled)).with_duration(duration)
    except Exception as e:
        logger.error(f"Film burn cover error: {e}")
        base_clip = ColorClip(size=(video_width, video_height), color=(30, 30, 30)).with_duration(duration)

    # ── Texture phim thật: hạt phim + nhấp nháy máy chiếu + vết trầy + vignette ──
    # LỖI CŨ: hiệu ứng "vintage" chỉ có ĐÚNG vệt sáng cam quét ngang trên một tấm ảnh
    # hiện đại sắc nét — không ai nhận ra đây là "phim cổ điển" vì thiếu texture. Giờ
    # thêm 4 lớp giả lập phim nhựa thật, sinh MỚI mỗi khung hình (không phải noise tĩnh
    # phủ đè chết cứng), cộng dồn trong MỘT lượt transform cho rẻ.
    #
    # QUAN TRỌNG: transform NÀY PHẢI CHẠY TRƯỚC `.resized()` bên dưới, không phải sau.
    # `.resized()` trong MoviePy đổi THẬT kích thước mảng khung hình mỗi lúc gọi
    # get_frame() (không chỉ là hệ số dùng lúc ghép) — grain/vignette ở đây lại dựng sẵn
    # mảng đúng (video_height, video_width, 1). Transform sau resize sẽ nhận khung đã
    # phóng to hơn/khác kích thước và vỡ ngay `ValueError: operands could not be
    # broadcast together` (đã ăn lỗi này thật khi test).
    import math

    _rng = np.random.default_rng()
    _dist = _radial_dist(video_width, video_height)
    _vignette_falloff = np.clip((_dist - 0.6) / 0.4, 0.0, 1.0)[..., None]

    def _film_texture(get_frame, t):
        frame = get_frame(t).astype(np.float32)

        # Hạt phim: nhiễu đơn sắc nhẹ, khác giá trị MỖI khung — hạt phim thật luôn "sống",
        # noise cố định trông giống một lớp lọc Instagram hơn là phim nhựa.
        grain = _rng.standard_normal((video_height, video_width, 1)).astype(np.float32) * 9.0
        frame = frame + grain

        # Nhấp nháy ánh sáng máy chiếu: dao động độ sáng đều + rung nhỏ ngẫu nhiên.
        flicker = 1.0 + 0.05 * math.sin(t * 22.0) + _rng.uniform(-0.015, 0.015)
        frame = frame * flicker

        # Vết trầy: thỉnh thoảng một vạch dọc mảnh sáng/tối chớp qua rồi biến mất.
        if _rng.random() < 0.12:
            x = int(_rng.integers(0, video_width))
            hw = int(_rng.integers(1, 3))
            delta = 45.0 if _rng.random() < 0.5 else -45.0
            x0, x1 = max(0, x - hw), min(video_width, x + hw)
            frame[:, x0:x1, :] += delta

        # Vignette tối 4 góc — khung phim chiếu thật luôn tối dần ra mép, không đều sáng.
        frame = frame * (1.0 - 0.35 * _vignette_falloff)

        return np.clip(frame, 0, 255).astype(np.uint8)

    textured = base_clip.transform(_film_texture)

    # Zoom chậm ra — áp dụng SAU khi đã có texture, đúng kích thước cố định lúc dựng noise.
    zoomed = textured.resized(lambda t: 1.05 - 0.02 * (t / duration)).with_position("center").with_duration(duration)

    # ── Vệt cháy phim: dải sáng cam quét NGANG màn hình ──────────────────────
    #
    # LỖI CŨ, hai tầng:
    #
    # 1. `burn.with_opacity(burn_opacity)` truyền một HÀM vào chỗ MoviePy 2.x chỉ nhận
    #    số. Nó ném `unsupported operand type(s) for *: 'function' and 'float'`, exception
    #    thoát ra tận video_service và hook bị bỏ hẳn. Nhưng main.py ĐÃ dời timeline theo
    #    resolve_hook_timing() từ trước, nên khán giả nhận 2.5 GIÂY MÀN HÌNH ĐEN CÂM
    #    (đo trên bản render thật: độ sáng 19/255, âm thanh −124 dB) — đúng khoảnh khắc
    #    quan trọng nhất để giữ chân người xem. Đã xảy ra ở 5 job từ 28/07.
    #    Opacity biến thiên theo thời gian trong MoviePy 2.x phải đi qua MASK CLIP.
    #
    # 2. Kể cả khi chạy được, ColorClip phủ TOÀN khung chỉ làm cả màn hình ngả cam —
    #    không phải "vệt sáng lướt ngang" như đặc tả. Nay là một dải gaussian quét từ
    #    ngoài mép trái sang ngoài mép phải, giống tia sáng rọi qua phim nhựa.
    from moviepy.video.VideoClip import VideoClip

    BURN_PEAK = 0.55          # độ đậm tối đa của vệt
    BURN_WIDTH = 0.11         # bề rộng dải, theo tỉ lệ bề ngang khung
    _xs = np.linspace(0.0, 1.0, video_width, dtype=np.float32)

    def _burn_mask_frame(t: float) -> np.ndarray:
        prog = min(max(t / max(duration, 1e-6), 0.0), 1.0)
        centre = -0.25 + 1.5 * prog                     # xuất phát và kết thúc ngoài khung
        band = np.exp(-((_xs - centre) ** 2) / (2.0 * BURN_WIDTH ** 2))
        # Tắt dần ở cuối để vệt không bị cắt cụt lúc hook kết thúc.
        fade = 1.0 if prog < 0.8 else (1.0 - (prog - 0.8) / 0.2)
        return np.tile(band * (BURN_PEAK * fade), (video_height, 1)).astype(np.float32)

    burn = (
        ColorClip(size=(video_width, video_height), color=(255, 120, 40))
        .with_duration(duration)
        .with_mask(VideoClip(_burn_mask_frame, is_mask=True).with_duration(duration))
    )

    layers = [zoomed, burn]
    # Màu kem ấm (không phải trắng thuần) để chữ hợp tông với ánh cam của vệt cháy phim.
    caption = _hook_caption_overlay(
        quote_text, video_width, video_height, duration,
        delay=0.2, y_frac=0.80, color="#FFEFD2",
    )
    if caption is not None:
        layers.append(caption)

    return CompositeVideoClip(layers, size=(video_width, video_height)).with_duration(duration)


# ══════════════════════════════════════════════════════════════════════
# OUTRO C7: CTA Card — CHỈ DÀNH CHO OUTRO, không xuất hiện ở dropdown Hook
# ══════════════════════════════════════════════════════════════════════
# LÝ DO RIÊNG MỘT HIỆU ỨNG: 6 hiệu ứng còn lại đều là hiệu ứng HÌNH ẢNH dùng chung cho
# cả hook lẫn outro — hợp lý cho hook (mở màn cần một cú "giật gân" thị giác), nhưng
# outro cần một thứ khác hẳn: một lời kêu gọi hành động RÕ RÀNG (thích/theo dõi/chia
# sẻ), không phải thêm một hiệu ứng thị giác nữa. Dùng lại carousel_quote làm outro
# (chạy lại nguyên màn Máy Xèng quay bìa giả) đặc biệt lạc chỗ — khán giả đã biết bìa
# thật từ đầu video, quay lại chỉ gây khó hiểu. Card này thay bằng: bìa nhỏ + 3 huy
# hiệu hành động (Thích/Theo dõi/Chia sẻ) nảy ra lần lượt + dòng CTA.
def _draw_heart_icon(draw, cx: float, cy: float, size: float, color: tuple) -> None:
    """Trái tim bằng 2 hình tròn + 1 tam giác — KHÔNG dùng glyph font. seguibl.ttf
    không đảm bảo có ký hiệu ♥ (bài học cũ về glyph thiếu, xem vietnamese-font-arial-
    black: Arial Black/Impact thiếu cả glyph tiếng Việt cơ bản); vẽ vector thuần đảm
    bảo hiển thị giống hệt nhau trên mọi máy, không phụ thuộc font cài sẵn."""
    r = size * 0.28
    draw.ellipse([cx - r * 2, cy - r * 1.4, cx, cy + r * 0.6], fill=color)
    draw.ellipse([cx, cy - r * 1.4, cx + r * 2, cy + r * 0.6], fill=color)
    draw.polygon(
        [(cx - r * 2, cy - r * 0.15), (cx + r * 2, cy - r * 0.15), (cx, cy + r * 2.1)],
        fill=color,
    )


def _draw_plus_icon(draw, cx: float, cy: float, size: float, color: tuple) -> None:
    """Dấu cộng (Theo dõi) — 2 thanh bo góc bắt chéo."""
    t = size * 0.22
    l = size * 0.78
    draw.rounded_rectangle([cx - t / 2, cy - l / 2, cx + t / 2, cy + l / 2], radius=t / 2, fill=color)
    draw.rounded_rectangle([cx - l / 2, cy - t / 2, cx + l / 2, cy + t / 2], radius=t / 2, fill=color)


def _draw_share_icon(draw, cx: float, cy: float, size: float, color: tuple) -> None:
    """Mũi tên chéo lên-phải (Chia sẻ) — 1 nét + 1 đầu mũi tên tam giác."""
    t = max(2, size * 0.16)
    x0, y0 = cx - size * 0.38, cy + size * 0.38
    x1, y1 = cx + size * 0.38, cy - size * 0.38
    draw.line([x0, y0, x1, y1], fill=color, width=int(t))
    head = size * 0.34
    draw.polygon([(x1, y1), (x1 - head, y1), (x1, y1 + head)], fill=color)


_CTA_ICON_DRAWERS = {"heart": _draw_heart_icon, "plus": _draw_plus_icon, "share": _draw_share_icon}


def _draw_cta_badge(label: str, icon: str, size: int, accent: tuple) -> "np.ndarray":
    """Vẽ 1 huy hiệu tròn (nền màu + icon vector trắng + nhãn chữ dưới) ra 1 ảnh RGBA."""
    from PIL import Image, ImageDraw

    label_h = int(size * 0.34)
    img = Image.new("RGBA", (size, size + label_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size / 2, size / 2
    r = size * 0.46
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*accent, 235))
    _CTA_ICON_DRAWERS[icon](draw, cx, cy, size * 0.5, (255, 255, 255, 255))

    font = _load_hook_font(max(10, int(size * 0.155)))
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    draw.text((cx - tw / 2 - bbox[0], size + label_h * 0.1), label, font=font, fill=(255, 255, 255, 255))
    return np.array(img)


def build_cta_card_hook(
    cover_image_path: str,
    quote_text: str,
    video_width: int,
    video_height: int,
    duration: float = 2.4,
) -> CompositeVideoClip:
    """
    Thẻ kết thúc: bìa nhỏ hiện lên, rồi 3 huy hiệu Thích/Theo dõi/Chia sẻ nảy ra lần
    lượt, cuối cùng là dòng CTA. Chỉ dùng cho outro (xem chú thích ở đầu section).
    """
    from PIL import Image, ImageOps

    w, h = video_width, video_height
    bg = _blurred_fill_bg(cover_image_path, w, h, duration, darken=0.35)

    try:
        if cover_image_path.endswith(".mp4"):
            from moviepy.video.io.VideoFileClip import VideoFileClip
            with VideoFileClip(cover_image_path) as v:
                cover_img = Image.fromarray(v.get_frame(0))
        else:
            cover_img = ImageOps.exif_transpose(Image.open(cover_image_path)).convert("RGB")
        fit = min(w * 0.5 / cover_img.width, h * 0.26 / cover_img.height)
        cw, ch = int(cover_img.width * fit), int(cover_img.height * fit)
        cover_arr = np.array(cover_img.resize((cw, ch), Image.Resampling.LANCZOS))
    except Exception as e:
        logger.warning(f"CTA card cover error: {e}")
        cover_arr = np.full((int(h * 0.26), int(w * 0.5), 3), 40, dtype=np.uint8)
        ch = cover_arr.shape[0]

    cover_top = int(h * 0.10)
    cover_clip = (
        ImageClip(cover_arr)
        .with_position(("center", cover_top))
        .with_duration(duration)
        .with_effects([CrossFadeIn(0.3)])
    )

    # ── 3 huy hiệu Thích/Theo dõi/Chia sẻ, nảy ra lần lượt ──
    badge_size = int(w * 0.22)
    gap = int(w * 0.06)
    total_w = badge_size * 3 + gap * 2
    start_x = (w - total_w) / 2.0
    badges_cy = cover_top + ch + int(h * 0.10) + badge_size // 2

    # LỖI CŨ: stagger 0.2s/badge (0.35→0.55→0.75) làm dòng CTA — thứ quan trọng nhất —
    # mãi 1.18s mới hiện. Outro cần "gây ấn tượng nhanh, không dài dòng": rút stagger
    # xuống 0.1s để 3 huy hiệu gần như nảy cùng lúc (vẫn đủ lệch để mắt thấy hiệu ứng
    # nảy, không phải bật hết cùng 1 khung hình), CTA hiện sớm hơn ~0.4s.
    POP_DUR = 0.22
    STAGGER = 0.1
    badge_specs = [
        ("heart", "THÍCH", (233, 30, 99), 0.3),
        ("plus", "THEO DÕI", (124, 58, 237), 0.3 + STAGGER),
        ("share", "CHIA SẺ", (16, 163, 163), 0.3 + STAGGER * 2),
    ]
    badge_layers = []
    for i, (icon, label, accent, delay) in enumerate(badge_specs):
        arr = _draw_cta_badge(label, icon, badge_size, accent)
        bh, bw = arr.shape[0], arr.shape[1]
        bx = start_x + badge_size / 2.0 + i * (badge_size + gap)
        by = badges_cy

        def _scale_fn(t, _pop=POP_DUR):
            p = min(1.0, max(0.0, t) / _pop)
            ease = 1 - (1 - p) ** 3
            return 0.3 + 0.7 * ease

        def _pos_fn(t, _bw=bw, _bh=bh, _bx=bx, _by=by, _scale_fn=_scale_fn):
            s = _scale_fn(t)
            return (_bx - _bw * s / 2.0, _by - _bh * s * 0.42)

        clip = (
            ImageClip(arr)
            .resized(_scale_fn)
            .with_position(_pos_fn)
            .with_start(delay)
            .with_duration(max(0.1, duration - delay))
        )
        badge_layers.append(clip)

    # ── Dòng CTA, hiện sau cùng khi cả 3 huy hiệu đã nảy xong ──
    cta_delay = badge_specs[-1][3] + POP_DUR + 0.15
    caption = _hook_caption_overlay(
        quote_text, w, h, duration, delay=cta_delay,
        y_frac=(badges_cy + badge_size * 0.65) / h + 0.09,
    )

    layers = [bg, cover_clip] + badge_layers
    if caption is not None:
        layers.append(caption)

    return CompositeVideoClip(layers, size=(w, h)).with_duration(duration)


# ══════════════════════════════════════════════════════════════════════
# HOOK MỚI 1: Smash Cut Blackout
# ══════════════════════════════════════════════════════════════════════
def build_smash_cut_hook(
    quote_text: str,
    video_width: int,
    video_height: int,
    duration: float = 1.5,
    cover_image_path: str = "",
) -> CompositeVideoClip:
    """
    Smash Cut: 0.5s đầu chiếu ảnh bìa Zoom in gắt, sau đó cắt cứng (Cut) sang màn hình đen đặc,
    chữ trắng bự bật lên giữa màn hình. Hiệu ứng hụt hẫng (Kích hoạt mất mát).
    """
    from PIL import Image, ImageOps
    
    try:
        if cover_image_path.endswith(".mp4"):
            from moviepy.video.io.VideoFileClip import VideoFileClip
            with VideoFileClip(cover_image_path) as v:
                img = Image.fromarray(v.get_frame(0))
        else:
            img = ImageOps.exif_transpose(Image.open(cover_image_path)).convert("RGB")
        img_filled = ImageOps.fit(img, (video_width, video_height), Image.Resampling.LANCZOS)
        base_clip = ImageClip(np.array(img_filled)).with_duration(0.5)
    except Exception as e:
        logger.error(f"Smash Cut cover error: {e}")
        base_clip = ColorClip(size=(video_width, video_height), color=(30, 30, 30)).with_duration(0.5)

    def hard_zoom(t):
        return 1.0 + 0.5 * (t / 0.5)
        
    intro_clip = base_clip.resized(hard_zoom).with_position("center").with_start(0.0)
    
    black_bg = ColorClip(size=(video_width, video_height), color=(0, 0, 0)).with_start(0.5).with_duration(duration - 0.5)
    
    text = (quote_text or "").strip()
    layers = [intro_clip, black_bg]
    
    if text:
        try:
            txt = _safe_caption_clip(
                text, int(video_width * 0.08), int(video_width * 0.9),
                color="#FFFFFF", stroke_width=0
            )
            txt_clip = txt.with_position("center").with_start(0.51).with_duration(duration - 0.51)
            layers.append(txt_clip)
        except Exception as e:
            logger.error(f"Smash cut text error: {e}")
            
    return CompositeVideoClip(layers, size=(video_width, video_height)).with_duration(duration)


# ══════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════
# HOOK MỚI 3: Cinematic Letterbox
# ══════════════════════════════════════════════════════════════════════
def build_cinematic_letterbox_hook(
    cover_image_path: str,
    video_width: int,
    video_height: int,
    duration: float = 3.0,
    quote_text: str = "",
) -> CompositeVideoClip:
    """
    Hai thanh viền đen điện ảnh trượt dần từ mép trên và mép dưới vào trong khung 9:16.
    """
    from PIL import Image, ImageOps
    
    try:
        if cover_image_path.endswith(".mp4"):
            from moviepy.video.io.VideoFileClip import VideoFileClip
            with VideoFileClip(cover_image_path) as v:
                img = Image.fromarray(v.get_frame(0))
        else:
            img = ImageOps.exif_transpose(Image.open(cover_image_path)).convert("RGB")
        img_filled = ImageOps.fit(img, (video_width, video_height), Image.Resampling.LANCZOS)
        base_clip = ImageClip(np.array(img_filled)).with_duration(duration)
    except Exception as e:
        logger.error(f"Letterbox cover error: {e}")
        base_clip = ColorClip(size=(video_width, video_height), color=(30, 30, 30)).with_duration(duration)

    bg = base_clip.resized(lambda t: 1.0 + 0.04 * (t/duration)).with_position("center")
    
    bar_height = int(video_height * 0.22)
    top_bar = ColorClip(size=(video_width, bar_height), color=(0,0,0)).with_duration(duration)
    bot_bar = ColorClip(size=(video_width, bar_height), color=(0,0,0)).with_duration(duration)
    
    def top_pos(t):
        p = min(1.0, t / 1.5)
        ease = 1 - (1 - p)**3
        y = -bar_height + (bar_height * ease)
        return ("center", int(y))
        
    def bot_pos(t):
        p = min(1.0, t / 1.5)
        ease = 1 - (1 - p)**3
        y = video_height - (bar_height * ease)
        return ("center", int(y))
        
    top_clip = top_bar.with_position(top_pos)
    bot_clip = bot_bar.with_position(bot_pos)
    
    layers = [bg, top_clip, bot_clip]
    
    caption = _hook_caption_overlay(quote_text, video_width, video_height, duration, delay=1.0, y_frac=0.5, font_size_frac=0.05, stroke_width=2)
    if caption is not None:
        layers.append(caption)
        
    return CompositeVideoClip(layers, size=(video_width, video_height)).with_duration(duration)



# ══════════════════════════════════════════════════════════════════════
# VIRAL HOOK 1: Paper Rip (Split Reveal)
# ══════════════════════════════════════════════════════════════════════
def build_paper_rip_hook(
    cover_image_path: str,
    video_width: int,
    video_height: int,
    duration: float = 2.0,
    quote_text: str = "",
) -> CompositeVideoClip:
    """
    Xé đôi màn hình (Split Reveal).
    """
    from PIL import Image, ImageOps
    
    try:
        if cover_image_path.endswith(".mp4"):
            from moviepy.video.io.VideoFileClip import VideoFileClip
            with VideoFileClip(cover_image_path) as v:
                img = Image.fromarray(v.get_frame(0))
        else:
            img = ImageOps.exif_transpose(Image.open(cover_image_path)).convert("RGB")
        img_filled = ImageOps.fit(img, (video_width, video_height), Image.Resampling.LANCZOS)
        bg_array = np.array(img_filled)
    except Exception as e:
        logger.error(f"Paper rip cover error: {e}")
        bg_array = np.zeros((video_height, video_width, 3), dtype=np.uint8)

    bg_color = ColorClip(size=(video_width, video_height), color=(20, 20, 20)).with_duration(duration)
    
    caption = _hook_caption_overlay(quote_text, video_width, video_height, duration, delay=0.0, y_frac=0.5)
    
    left_img = bg_array[:, :video_width//2]
    right_img = bg_array[:, video_width//2:]
    
    left_clip = ImageClip(left_img).with_duration(duration)
    right_clip = ImageClip(right_img).with_duration(duration)
    
    def left_pos(t):
        if t < 0.2: return ("left", "center")
        p = min(1.0, (t - 0.2) / 0.3)
        return (int(-video_width//2 * p), "center")
        
    def right_pos(t):
        if t < 0.2: return ("right", "center")
        p = min(1.0, (t - 0.2) / 0.3)
        return (int(video_width//2 + video_width//2 * p), "center")

    left_anim = left_clip.with_position(left_pos)
    right_anim = right_clip.with_position(right_pos)
    
    layers = [bg_color]
    if caption: layers.append(caption)
    layers.extend([left_anim, right_anim])
    
    return CompositeVideoClip(layers, size=(video_width, video_height)).with_duration(duration)

# ══════════════════════════════════════════════════════════════════════
# VIRAL HOOK 2: Fake iOS Message
# ══════════════════════════════════════════════════════════════════════
def build_smart_quote_animation_hook(
    cover_image_path: str,
    video_width: int,
    video_height: int,
    duration: float = 3.0,
    quote_text: str = "",
) -> CompositeVideoClip:
    """
    Smart Quote Animation: Chữ hiện theo kiểu "đọc từng từ"
    với animation đẹp mắt, không dùng typewriter cũ.
    Thay thế fake_ios_message vì concept tin nhắn iOS không phù hợp với nội dung sách.
    """
    from PIL import Image, ImageOps

    try:
        if cover_image_path.endswith(".mp4"):
            from moviepy.video.io.VideoFileClip import VideoFileClip
            with VideoFileClip(cover_image_path) as v:
                img = Image.fromarray(v.get_frame(0))
        else:
            img = ImageOps.exif_transpose(Image.open(cover_image_path)).convert("RGB")
        img_filled = ImageOps.fit(img, (video_width, video_height), Image.Resampling.LANCZOS)
        bg_clip = ImageClip(np.array(img_filled)).with_duration(duration)
    except:
        bg_clip = ColorClip(size=(video_width, video_height), color=(40, 40, 40)).with_duration(duration)

    text = (quote_text or "").strip()
    if not text:
        return bg_clip

    bg_dark = CompositeVideoClip([
        bg_clip,
        ColorClip(size=(video_width, video_height), color=(0, 0, 0)).with_duration(duration).with_opacity(0.5)
    ])

    words = text.split()
    num_words = len(words)
    word_dur = min(0.4, max(0.15, (duration - 0.5) / num_words if num_words > 0 else 0.3))

    layers = [bg_dark]

    for i, word in enumerate(words):
        start_time = 0.3 + i * word_dur
        if start_time >= duration:
            break

        word_duration = min(word_dur * 0.8, duration - start_time)

        try:
            word_clip = _safe_caption_clip(
                word,
                font_size=int(video_width * 0.06),
                box_w=int(video_width * 0.9),
                color="white",
                stroke_color="black",
                stroke_width=3
            )
        except:
            word_clip = TextClip(text=word, font=HOOK_FONT, font_size=int(video_width * 0.06),
                                color="white", method="caption")

        def make_scale_fn(start_t):
            def scale_fn(t):
                if t < start_t:
                    return 0.01
                local_t = t - start_t
                if local_t < 0.15:
                    p = local_t / 0.15
                    ease = 1 - (1 - p) ** 3
                    return 0.5 + 0.5 * ease
                return 1.0
            return scale_fn

        word_anim = (
            word_clip
            .resized(make_scale_fn(start_time))
            .with_position("center")
            .with_start(start_time)
            .with_duration(word_duration)
        )
        layers.append(word_anim)

    return CompositeVideoClip(layers, size=(video_width, video_height)).with_duration(duration)


# ══════════════════════════════════════════════════════════════════════
# ARTISTIC HOOK 1: Double Exposure Reveal
# ══════════════════════════════════════════════════════════════════════
def build_double_exposure_hook(
    cover_image_path: str,
    video_width: int,
    video_height: int,
    duration: float = 3.0,
    quote_text: str = "",
) -> CompositeVideoClip:
    """
    Ảnh ma (Ghost Overlay) — kỹ thuật nhiếp ảnh nghệ thuật double exposure.
    Ảnh bìa hiện như bóng mờ trong suốt, trôi nổi trên nền ảnh
    chính (bản phóng to + blur). Hai lớp hòa trộn bằng blend mode
    overlay để tạo chiều sâu như ảnh phim cổ điển.
    """
    from PIL import Image, ImageOps, ImageEnhance, ImageFilter

    try:
        if cover_image_path.endswith(".mp4"):
            from moviepy.video.io.VideoFileClip import VideoFileClip
            with VideoFileClip(cover_image_path) as v:
                img = Image.fromarray(v.get_frame(0))
        else:
            img = ImageOps.exif_transpose(Image.open(cover_image_path)).convert("RGB")
        img_filled = ImageOps.fit(img, (video_width, video_height), Image.Resampling.LANCZOS)
    except Exception as e:
        logger.error(f"Double exposure cover error: {e}")
        img_filled = Image.new("RGB", (video_width, video_height), (30, 30, 30))

    w, h = video_width, video_height

    # Lớp nền: bản phóng + blur nặng (nền ấm)
    bg_blurry = img_filled.copy().filter(ImageFilter.GaussianBlur(45))
    bg_arr = np.array(bg_blurry).astype(np.float32) * 0.35
    bg_clip = ImageClip(bg_arr.astype(np.uint8)).with_duration(duration)

    # Lớp ảnh chính: bão hòa nhẹ, màu ấm
    enhancer = ImageEnhance.Color(img_filled)
    colored = enhancer.enhance(1.15)
    warm_arr = np.array(colored)
    main_clip = ImageClip(warm_arr).with_duration(duration)

    # Lớp ma: ảnh đen trắng, mờ, lệch nhẹ (double exposure thật)
    bw = ImageOps.grayscale(img_filled)
    bw_arr = np.array(bw.convert("RGB"))
    bw_clip = ImageClip(bw_arr.astype(np.float32) / 255.0)

    def ghost_pos(t):
        p = t / duration
        # Lệch nhẹ từ trái sang phải trong nửa đầu, rồi về giữa
        if p < 0.5:
            offset = int(w * 0.04 * (p / 0.5))
        else:
            offset = int(w * 0.04 * (1 - (p - 0.5) / 0.5))
        return (offset, "center")

    def ghost_opacity(t):
        # Mờ ở đầu, rõ dần rồi mờ lại ở cuối (hít vào)
        p = t / duration
        if p < 0.3:
            return 0.25 + 0.45 * (p / 0.3)
        elif p > 0.75:
            return 0.70 * (1 - (p - 0.75) / 0.25)
        return 0.70

    ghost_anim = _dynamic_opacity(bw_clip.resized(lambda t: 1.0 + 0.03 * (t / duration)).with_position(ghost_pos), ghost_opacity)

    # Viền mỏng film-like ở 2 bên (giống ảnh phim cổ điển)
    border_w = int(w * 0.02)
    left_border = ColorClip((border_w, h), color=(15, 12, 10)).with_duration(duration)
    right_border = ColorClip((border_w, h), color=(15, 12, 10)).with_duration(duration)
    top_border = ColorClip((w, border_w), color=(15, 12, 10)).with_duration(duration)
    bot_border = ColorClip((w, border_w), color=(15, 12, 10)).with_duration(duration)

    layers = [bg_clip, main_clip, ghost_anim,
              left_border.with_position(("left", "top")),
              right_border.with_position(("right", "top")),
              top_border.with_position(("left", "top")),
              bot_border.with_position(("left", "bottom"))]

    caption = _hook_caption_overlay(quote_text, w, h, duration, delay=0.5, y_frac=0.76)
    if caption:
        layers.append(caption)

    return CompositeVideoClip(layers, size=(w, h)).with_duration(duration)


# ══════════════════════════════════════════════════════════════════════
# ARTISTIC HOOK 2: Light Paint Ingress
# ══════════════════════════════════════════════════════════════════════
def build_light_paint_hook(
    cover_image_path: str,
    video_width: int,
    video_height: int,
    duration: float = 3.0,
    quote_text: str = "",
) -> CompositeVideoClip:
    """
    Vẽ bằng ánh sáng — tia sáng quét qua khung hình, để lại
    vệt sáng trên đường đi, rồi bung ra reveal toàn bộ ảnh.
    Tia sáng di chuyển theo bezier path ngẫu nhiên mỗi lần chạy.
    """
    from PIL import Image, ImageOps
    import math

    w, h = video_width, video_height

    bg = ColorClip((w, h), color=(0, 0, 0)).with_duration(duration)

    try:
        if cover_image_path.endswith(".mp4"):
            from moviepy.video.io.VideoFileClip import VideoFileClip
            with VideoFileClip(cover_image_path) as v:
                img = Image.fromarray(v.get_frame(0))
        else:
            img = ImageOps.exif_transpose(Image.open(cover_image_path)).convert("RGB")
        img_filled = ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS)
    except Exception:
        img_filled = Image.new("RGB", (w, h), (40, 40, 40))

    img_arr = np.array(img_filled).astype(np.float32)

    # Precompute radial distance field từ 5 beam sources (vectorized NumPy)
    # Điểm bắt đầu: 4 góc + 1 điểm ngẫu nhiên
    _rng = np.random.default_rng()
    bx0, by0 = 0, 0
    bx1, by1 = w - 1, 0
    bx2, by2 = 0, h - 1
    bx3, by3 = w - 1, h - 1
    bx4, by4 = _rng.integers(w // 4, 3 * w // 4), _rng.integers(h // 4, 3 * h // 4)

    _yy, _xx = np.mgrid[0:h, 0:w].astype(np.float32)
    _d0 = np.sqrt((_xx - bx0) ** 2 + (_yy - by0) ** 2)
    _d1 = np.sqrt((_xx - bx1) ** 2 + (_yy - by1) ** 2)
    _d2 = np.sqrt((_xx - bx2) ** 2 + (_yy - by2) ** 2)
    _d3 = np.sqrt((_xx - bx3) ** 2 + (_yy - by3) ** 2)
    _d4 = np.sqrt((_xx - bx4) ** 2 + (_yy - by4) ** 2)
    _dist_field = np.minimum(np.minimum(_d0, _d1), np.minimum(np.minimum(_d2, _d3), _d4))
    _max_dist = math.sqrt(w ** 2 + h ** 2)

    def _light_paint_frame(t: float):
        p = min(1.0, t / duration)

        if p < 0.55:
            max_d = p / 0.55 * _max_dist * 0.8
        elif p < 0.80:
            max_d = _max_dist * 0.8
        else:
            max_d = _max_dist * 1.5

        # Mask vùng được beam chiếu — expand_dims để broadcast với (H, W, 3)
        beam_mask = (_dist_field <= max_d).astype(np.float32)              # (H, W)
        edge_dist = np.clip(max_d - _dist_field, 0, None)
        edge_glow = np.clip(edge_dist / (max_d * 0.15 + 1e-6), 0, 1.0)   # (H, W)

        beam_mask_3 = beam_mask[..., np.newaxis]       # (H, W, 1) → broadcast với (H, W, 3)
        edge_glow_3 = edge_glow[..., np.newaxis]

        # Ảnh sáng lên + glow ấm vàng
        lit = img_arr * (1.0 + beam_mask_3 * 0.6)
        glow = np.concatenate([
            beam_mask_3 * edge_glow_3 * 100,
            beam_mask_3 * edge_glow_3 * 78,
            beam_mask_3 * edge_glow_3 * 47,
        ], axis=-1)
        frame = np.clip(lit + glow, 0, 255).astype(np.uint8)

        # Phase 3: full reveal với fade
        if p >= 0.80:
            reveal_p = (p - 0.80) / 0.20
            frame = np.clip(img_arr * reveal_p, 0, 255).astype(np.uint8)

        return frame

    from moviepy.video.VideoClip import VideoClip
    light_clip = VideoClip(_light_paint_frame).with_duration(duration)

    layers = [bg, light_clip]

    caption = _hook_caption_overlay(quote_text, w, h, duration, delay=duration * 0.80, y_frac=0.80)
    if caption:
        layers.append(caption)

    return CompositeVideoClip(layers, size=(w, h)).with_duration(duration)


# ══════════════════════════════════════════════════════════════════════
# ARTISTIC HOOK 3: Memory Resurface
# ══════════════════════════════════════════════════════════════════════
def build_memory_resurface_hook(
    cover_image_path: str,
    video_width: int,
    video_height: int,
    duration: float = 3.0,
    quote_text: str = "",
) -> CompositeVideoClip:
    """
    Bề mặt ký ức — ảnh bắt đầu desaturated hoàn toàn + defocused.
    Màu sắc tràn vào từ một điểm sáng, khôi phục độ nét.
    Như chiếu đèn pin vào tấm ảnh cũ trong phòng tối.
    """
    import math
    from PIL import Image, ImageOps

    w, h = video_width, video_height

    try:
        if cover_image_path.endswith(".mp4"):
            from moviepy.video.io.VideoFileClip import VideoFileClip
            with VideoFileClip(cover_image_path) as v:
                img = Image.fromarray(v.get_frame(0))
        else:
            img = ImageOps.exif_transpose(Image.open(cover_image_path)).convert("RGB")
        img_filled = ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS)
    except Exception:
        img_filled = Image.new("RGB", (w, h), (40, 40, 40))

    img_arr = np.array(img_filled).astype(np.float32)
    # Grayscale: dùng PIL cho nhanh, reshape thành (h, w)
    gray_np = np.array(ImageOps.grayscale(img_filled)).astype(np.float32)
    gray_3ch = np.stack([gray_np, gray_np, gray_np], axis=-1)

    # Precompute normalized radial distance từ tâm ảnh (0=tâm, 1=góc xa nhất)
    _mem_cx, _mem_cy = w / 2.0, h / 2.0
    _mem_yy, _mem_xx = np.mgrid[0:h, 0:w].astype(np.float32)
    _mem_raw_dist = np.sqrt((_mem_xx - _mem_cx) ** 2 + (_mem_yy - _mem_cy) ** 2)
    _mem_max_dist = math.sqrt(_mem_cx ** 2 + _mem_cy ** 2) + 1e-6
    _mem_dist = _mem_raw_dist / _mem_max_dist  # normalized [0, ~1]

    def _mem_frame(t: float):
        p = min(1.0, t / duration)

        if p < 0.65:
            reveal_p = p / 0.65
            sat = reveal_p
            vignette_p = 0.35 + 0.08 * math.sin(2 * math.pi * t / 2.4)
        else:
            reveal_p = 1.0
            sat = 1.0
            vignette_p = 0.30 + 0.06 * math.sin(2 * math.pi * t / 2.4)

        # Vectorized: color_mix từ 0→1 theo radial distance
        # Gần tâm → sớm có màu, xa tâm → trễ hơn
        dist = _mem_dist  # alias cho rõ nghĩa
        color_mix = np.clip((reveal_p * 1.2 - dist) / 1.2, 0.0, 1.0)
        color_mix = np.expand_dims(color_mix, axis=-1)  # (h, w, 1)

        # Blend: grayscale ↔ color, rồi tăng saturation
        blended = gray_3ch * (1.0 - color_mix) + img_arr * color_mix
        saturated = blended * (0.5 + 0.5 * sat) + img_arr * (sat * 0.5)

        # Vignette breathing
        vignette_strength = vignette_p * np.clip((dist - 0.55) / 0.45, 0.0, 1.0)
        vignette_strength = np.expand_dims(vignette_strength, axis=-1)
        out = saturated * (1.0 - vignette_strength * 0.5)

        return np.clip(out, 0, 255).astype(np.uint8)

    from moviepy.video.VideoClip import VideoClip
    mem_clip = VideoClip(_mem_frame).with_duration(duration)

    layers = [mem_clip]
    caption = _hook_caption_overlay(quote_text, w, h, duration, delay=duration * 0.70, y_frac=0.78)
    if caption:
        layers.append(caption)

    return CompositeVideoClip(layers, size=(w, h)).with_duration(duration)


# ══════════════════════════════════════════════════════════════════════
# ARTISTIC HOOK 4: Forbidden Uncover (Censored Reveal)
# ══════════════════════════════════════════════════════════════════════
def build_forbidden_uncover_hook(
    cover_image_path: str,
    video_width: int,
    video_height: int,
    duration: float = 2.5,
    quote_text: str = "",
) -> CompositeVideoClip:
    """
    Lật mở bí mật — màn hình "censorsored" bị xé tách ra
    từ giữa, reveal ảnh bìa bên dưới. Giống cảnh lật hồ sơ mật trong phim.
    """
    import math
    from PIL import Image, ImageOps, ImageDraw

    w, h = video_width, video_height

    # Nền đen
    bg = ColorClip((w, h), color=(8, 8, 12)).with_duration(duration)

    try:
        if cover_image_path.endswith(".mp4"):
            from moviepy.video.io.VideoFileClip import VideoFileClip
            with VideoFileClip(cover_image_path) as v:
                img = Image.fromarray(v.get_frame(0))
        else:
            img = ImageOps.exif_transpose(Image.open(cover_image_path)).convert("RGB")
        img_filled = ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS)
    except Exception:
        img_filled = Image.new("RGB", (w, h), (30, 30, 30))

    img_arr = np.array(img_filled)

    # Tạo lớp "censorsored": nửa trên đỏ đục, nửa dưới đỏ đục, giữa có khe hở
    panel_h = int(h * 0.45)
    top_panel_h = panel_h
    bot_panel_h = h - panel_h
    panel_color = (180, 20, 20)  # đỏ đậm
    stripe_color = (220, 30, 30)  # đỏ nhạt hơn cho sọc

    top_panel = Image.new("RGB", (w, top_panel_h), panel_color)
    bot_panel = Image.new("RGB", (w, bot_panel_h), panel_color)

    draw_top = ImageDraw.Draw(top_panel)
    draw_bot = ImageDraw.Draw(bot_panel)

    # Vẽ các vạch chéo đỏ (classic censored look)
    stripe_w = int(w * 0.08)
    for sx in range(-h, w + h, stripe_w * 2):
        draw_top.line([(sx, 0), (sx + top_panel_h, top_panel_h)], fill=stripe_color, width=4)
        draw_bot.line([(sx, 0), (sx + bot_panel_h, bot_panel_h)], fill=stripe_color, width=4)

    # Chữ "CLASSIFIED" ở giữa panel
    try:
        clf_font = _load_hook_font(int(w * 0.04))
    except Exception:
        clf_font = None

    mid_y_top = top_panel_h // 2
    mid_y_bot = bot_panel_h // 2
    label = "— CLASSIFIED —"
    if clf_font:
        tb = draw_top.textbbox((0, 0), label, font=clf_font)
        tw = tb[2] - tb[0]
        th = tb[3] - tb[1]
        draw_top.text(((w - tw) // 2, mid_y_top - th // 2), label, font=clf_font, fill=(255, 200, 200))
        draw_bot.text(((w - tw) // 2, mid_y_bot - th // 2), label, font=clf_font, fill=(255, 200, 200))

    top_arr = np.array(top_panel)
    bot_arr = np.array(bot_panel)

    # Định nghĩa timing: khi nào panel bắt đầu tách, khi nào xong
    PEEL_START = 0.3    # giây: panel bắt đầu tách
    PEEL_DUR = 0.9      # giây: thời gian tách

    def top_panel_pos(t):
        if t < PEEL_START:
            return ("center", 0)
        pt = min(1.0, (t - PEEL_START) / PEEL_DUR)
        ease = 1.0 - (1.0 - pt) ** 3
        return ("center", int(-(h // 2) * ease))

    def bot_panel_pos(t):
        if t < PEEL_START:
            return ("center", top_panel_h)
        pt = min(1.0, (t - PEEL_START) / PEEL_DUR)
        ease = 1.0 - (1.0 - pt) ** 3
        return ("center", int(top_panel_h + (h // 2) * ease))

    # Ảnh reveal: mờ ở đầu, rõ dần
    reveal_img_clip = ImageClip(img_arr).with_duration(duration)

    def reveal_opacity(t):
        if t < PEEL_START + PEEL_DUR:
            return 0.0
        p = min(1.0, (t - PEEL_START - PEEL_DUR) / 0.4)
        return 0.3 + 0.7 * (1.0 - (1.0 - p) ** 2)

    reveal_anim = _dynamic_opacity(reveal_img_clip, reveal_opacity)

    top_clip = ImageClip(top_arr).with_position(top_panel_pos).with_duration(duration)
    bot_clip = ImageClip(bot_arr).with_position(bot_panel_pos).with_duration(duration)

    # Flash trắng khi panels tách xong
    flash_delay = PEEL_START + PEEL_DUR
    flash = ColorClip((w, h), color=(255, 255, 255)).with_duration(0.08).with_start(flash_delay).with_opacity(0.7)

    layers = [bg, reveal_anim, top_clip, bot_clip, flash]

    caption_delay = flash_delay + 0.2
    caption = _hook_caption_overlay(quote_text, w, h, duration, delay=caption_delay, y_frac=0.78)
    if caption:
        layers.append(caption)

    return CompositeVideoClip(layers, size=(w, h)).with_duration(duration)


# ══════════════════════════════════════════════════════════════════════
# ARTISTIC HOOK 5: Ink Bleed Revelation
# ══════════════════════════════════════════════════════════════════════
def build_ink_bleed_hook(
    cover_image_path: str,
    video_width: int,
    video_height: int,
    duration: float = 3.0,
    quote_text: str = "",
) -> CompositeVideoClip:
    """
    Nhập nhòe mực — màn hình trắng, mực đen từ từ lan ra từ tâm,
    hình thành bóng ảnh. Cuối cùng: flash trắng → reveal ảnh rõ nét.
    Kỹ thuật ink diffusion photography.
    """
    import math
    from PIL import Image, ImageOps

    w, h = video_width, video_height

    try:
        if cover_image_path.endswith(".mp4"):
            from moviepy.video.io.VideoFileClip import VideoFileClip
            with VideoFileClip(cover_image_path) as v:
                img = Image.fromarray(v.get_frame(0))
        else:
            img = ImageOps.exif_transpose(Image.open(cover_image_path)).convert("RGB")
        img_filled = ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS)
    except Exception:
        img_filled = Image.new("RGB", (w, h), (40, 40, 40))

    img_arr = np.array(img_filled).astype(np.float32)

    # Precompute radial distance từ tâm (vectorized)
    _yy, _xx = np.mgrid[0:h, 0:w].astype(np.float32)
    _cx, _cy = w / 2.0, h / 2.0
    _radial_dist_arr = np.sqrt((_xx - _cx) ** 2 + (_yy - _cy) ** 2)
    _max_d = math.sqrt(_cx ** 2 + _cy ** 2)

    # Paper noise cache (fixed per-frame — fast, deterministic)
    _paper_noise = np.random.default_rng(42).standard_normal((h, w, 1)).astype(np.float32) * 4.0

    def _ink_frame(t: float):
        p = min(1.0, t / duration)

        if p < 0.60:
            spread_p = p / 0.60
        elif p < 0.78:
            spread_p = 1.0
        else:
            spread_p = 1.0

        # Bán kính mực lan: center gần → sớm, xa → trễ
        base_r = spread_p * _max_d * 1.3
        noise_offset = _radial_dist_arr / _max_d * _max_d * 0.15
        spread_r = base_r - noise_offset

        # Mask: vùng có mực (inside spread radius)
        ink_mask = (_radial_dist_arr <= spread_r).astype(np.float32)
        edge_soft = np.clip(spread_r - _radial_dist_arr, 0, None) / (spread_r * 0.08 + 1e-6)
        ink_amount = np.clip(ink_mask * 0.85 + edge_soft * ink_mask * 0.15, 0.0, 1.0)

        ink_col = np.array([15, 12, 18], dtype=np.float32)
        white_bg = np.array([250, 248, 245], dtype=np.float32)

        # Blend: mực ↔ giấy/ảnh
        paper = white_bg + _paper_noise * 0.5
        blended_ink = paper * (1.0 - ink_amount[..., None]) + ink_col * ink_amount[..., None]

        # Vùng chưa có mực: blend giấy ↔ ảnh bìa (theo spread_p)
        img_blend = img_arr * spread_p + paper * (1.0 - spread_p)

        frame = blended_ink * ink_amount[..., None] + img_blend * (1.0 - ink_amount[..., None])

        # Phase 3: flash trắng → reveal ảnh
        if 0.78 <= p < 0.90:
            flash_p = (p - 0.78) / 0.12
            frame = frame * (1.0 - flash_p * 0.5) + img_arr * (flash_p * 0.5)

        if p >= 0.90:
            reveal_p = (p - 0.90) / 0.10
            frame = img_arr * reveal_p + frame * (1.0 - reveal_p)

        return np.clip(frame, 0, 255).astype(np.uint8)

    from moviepy.video.VideoClip import VideoClip
    ink_clip = VideoClip(_ink_frame).with_duration(duration)

    layers = [ink_clip]
    caption = _hook_caption_overlay(quote_text, w, h, duration, delay=duration * 0.82, y_frac=0.78)
    if caption:
        layers.append(caption)

    return CompositeVideoClip(layers, size=(w, h)).with_duration(duration)


# ══════════════════════════════════════════════════════════════════════
# ARTISTIC HOOK 7: Minimal Text Reveal
# ══════════════════════════════════════════════════════════════════════
def build_scene_assembly_hook(
    cover_image_path: str,
    video_width: int,
    video_height: int,
    duration: float = 3.0,
    quote_text: str = "",
) -> CompositeVideoClip:
    """
    Lắp ráp hiện thực — particles (mảnh vụn từ ảnh) trôi nổi ngẫu nhiên
    trên nền đen, rồi hội tụ từ từ về đúng vị trí grid để ghép lại thành
    ảnh hoàn chỉnh. Spring physics để các mảnh "rơi vào đúng chỗ".
    Giống cảnh nhớ lại trong phim của Christopher Nolan.
    """
    import math
    from PIL import Image, ImageOps

    w, h = video_width, video_height

    try:
        if cover_image_path.endswith(".mp4"):
            from moviepy.video.io.VideoFileClip import VideoFileClip
            with VideoFileClip(cover_image_path) as v:
                img = Image.fromarray(v.get_frame(0))
        else:
            img = ImageOps.exif_transpose(Image.open(cover_image_path)).convert("RGB")
        img_filled = ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS)
    except Exception:
        img_filled = Image.new("RGB", (w, h), (40, 40, 40))

    img_arr = np.array(img_filled)

    # Tạo particles: grid GRID_X × GRID_Y, mỗi particle là 1 ô màu
    GRID_X = 60
    GRID_Y = 107
    TILE_W = w // GRID_X
    TILE_H = h // GRID_Y
    TILE_W = max(1, TILE_W)
    TILE_H = max(1, TILE_H)

    # Precompute particle properties: vị trí bắt đầu (ngẫu nhiên) + màu
    rng_init = np.random.default_rng(2026)
    particles = []
    for gy in range(GRID_Y):
        for gx in range(GRID_X):
            # Vị trí grid thật
            tx = gx * TILE_W
            ty = gy * TILE_H
            # Vị trí bắt đầu: ngẫu nhiên trên toàn khung
            sx = rng_init.integers(0, w)
            sy = rng_init.integers(0, h)
            # Màu: sample từ ảnh tại vị trí grid
            px = max(0, min(tx, w - 1))
            py = max(0, min(ty, h - 1))
            color = tuple(int(c) for c in img_arr[py, px])
            # Độ trễ: particle ở xa giữa → bắt đầu muộn hơn (parallax)
            center_x, center_y = w / 2, h / 2
            dist_from_center = math.sqrt((tx - center_x) ** 2 + (ty - center_y) ** 2)
            max_dist = math.sqrt(center_x ** 2 + center_y ** 2)
            delay = (dist_from_center / max_dist) * 0.6  # 0-0.6s delay

            particles.append({
                "sx": sx, "sy": sy, "tx": tx, "ty": ty,
                "color": color,
                "delay": delay,
                "tw": TILE_W, "th": TILE_H,
            })

    def _assemble_frame(t: float):
        frame = np.zeros((h, w, 3), dtype=np.float32)
        # Nền đen với subtle gradient
        for py in range(h):
            for px in range(0, w, 3):
                cx, cy = w / 2, h / 2
                d = math.sqrt((px - cx) ** 2 + (cy) ** 2 + (py - cy) ** 2) / (math.sqrt(cx ** 2 + cy ** 2) + 1e-6)
                val = 5 + int(d * 12)
                frame[py:py + 1, px:px + 3] = [val, val, val + 2]

        for p in particles:
            local_t = t - p["delay"]
            if local_t <= 0:
                # Chưa bắt đầu: ở vị trí scatter
                px_p = p["sx"]
                py_p = p["sy"]
            else:
                # Ease out cubic về target
                pt = min(1.0, local_t / (duration - p["delay"]))
                ease = 1.0 - (1.0 - pt) ** 3
                px_p = p["sx"] + (p["tx"] - p["sx"]) * ease
                py_p = p["sy"] + (p["ty"] - p["sy"]) * ease

            # Vẽ particle (tile)
            for dy in range(p["th"]):
                for dx in range(p["tw"]):
                    fpx = int(px_p) + dx
                    fpy = int(py_p) + dy
                    if 0 <= fpx < w and 0 <= fpy < h:
                        frame[fpy, fpx] = p["color"]

        return np.clip(frame, 0, 255).astype(np.uint8)

    from moviepy.video.VideoClip import VideoClip
    particles_clip = VideoClip(_assemble_frame).with_duration(duration)

    # Subtle glow ở tâm khi particles gần hoàn thành
    cx_g, cy_g = w // 2, h // 2
    _gd = np.sqrt((np.arange(w) - cx_g) ** 2 + np.arange(h)[:, None] ** 2)
    _glow_base = np.clip(1.0 - _gd / (cx_g * 0.4 + 1e-6), 0, 1.0) ** 2

    def _glow_frame(t):
        p = t / duration
        if p < 0.5:
            return np.zeros((h, w, 3), dtype=np.uint8)
        gp = (p - 0.5) / 0.5
        intensity = gp * 0.35
        glow = (_glow_base * intensity * 255).astype(np.uint8)[..., None]
        glow_rgb = np.concatenate([np.full_like(glow, 255), np.full_like(glow, 240), np.full_like(glow, 200)], axis=-1)
        return np.clip(glow_rgb, 0, 255).astype(np.uint8)

    glow_rgb_clip = VideoClip(_glow_frame).with_duration(duration)
    glow_alpha_arr = np.clip(_glow_base * 0.6 * 255, 0, 255).astype(np.uint8)
    glow_alpha_clip = VideoClip(lambda t: glow_alpha_arr).with_duration(duration).with_effects([])
    glow_clip = CompositeVideoClip([
        _dynamic_opacity(glow_rgb_clip, lambda t: min(1.0, max(0.0, (t / duration - 0.5) / 0.5 * 0.8)))
    ]).with_duration(duration)

    layers = [particles_clip, glow_clip]

    caption = _hook_caption_overlay(quote_text, w, h, duration, delay=duration * 0.85, y_frac=0.78)
    if caption:
        layers.append(caption)

    return CompositeVideoClip(layers, size=(w, h)).with_duration(duration)


# ─────────────────────────────────────────────────────────────────────────────
# HOOK REGISTRY — single dispatch table replacing elif chains in video_service.py
# Add a new hook type here: no changes needed in video_service.py
# ─────────────────────────────────────────────────────────────────────────────

_HOOK_AUDIO_SPECS = {
    # Hook audio specs
    "carousel_quote":          dict(type="ding_reel",  sfx_key="carousel_quote",   fallback="ding.wav",               start=0.0, vol_scale=1.0),
    "typewriter_quote":        dict(type="typewriter", sfx_key="typewriter_quote",  fallback=None,              start=0.0, vol_scale=1.0, tick_pct=0.85),
    "blackout_question":       dict(type="tick_burst", sfx_key="typewriter_quote", fallback=None,              start=0.0, vol_scale=1.0, tick_pct=0.85),
    "camera_shutter":          dict(type="sfx",       sfx_key="camera_shutter",   fallback=None,              start=0.0, vol_scale=1.0),
    "cyber_glitch":            dict(type="sfx",       sfx_key="cyber_glitch",     fallback=None,              start=0.0, vol_scale=1.0),
    "vintage_film_burn":      dict(type="sfx",       sfx_key="vintage_film_burn",fallback=None,              start=0.0, vol_scale=1.0),
    "smash_cut_blackout":      dict(type="bass_drop", sfx_key="impact",           fallback="impact_boom.wav",  start=0.5, vol_scale=1.5),
    "cinematic_letterbox":      dict(type="swell",     sfx_key="cinematic_letterbox",fallback="ambient_mystic.wav",start=0.0,vol_scale=1.0),
    "paper_rip_split":        dict(type="bass_drop", sfx_key="impact",           fallback="impact_boom.wav",  start=0.2, vol_scale=1.0),
    "double_exposure":         dict(type="swell",     sfx_key="double_exposure",   fallback="cinematic_swell.wav",start=0.0,vol_scale=1.0),
    "light_paint_ingress":    dict(type="swell",     sfx_key="light_paint_ingress",fallback="cinematic_swell.wav",start=0.0,vol_scale=1.0),
    "memory_resurface":        dict(type="ambient",   sfx_key="ambient_mystic",    fallback="ambient_mystic.wav",start=0.0, vol_scale=1.0),
    "forbidden_uncover":       dict(type="bass_drop", sfx_key="smash_cut_blackout",fallback="impact_boom.wav",start=1.2,vol_scale=1.0),
    "ink_bleed":              dict(type="ambient",   sfx_key="ink_bleed",         fallback="ambient_mystic.wav",start=0.0, vol_scale=1.0),
    "scene_assembly":          dict(type="swell",     sfx_key="scene_assembly",    fallback="cinematic_swell.wav",start=0.0,vol_scale=1.0),
    # Outro audio specs
    "carousel_quote_outro":   dict(type="carousel",   sfx_key="carousel_quote",   fallback=None,              start=0.0, vol_scale=1.0),
    "typewriter_quote_outro": dict(type="typewriter", sfx_key="typewriter_quote",fallback=None,              start=0.0, vol_scale=1.0, tick_pct=0.0),
    "blackout_question_outro":dict(type="tick_burst", sfx_key="typewriter_quote",fallback=None,              start=0.0, vol_scale=1.0, tick_pct=0.0),
    "camera_shutter_outro":  dict(type="sfx",       sfx_key="camera_shutter",  fallback=None,              start=0.0, vol_scale=1.0),
    "cyber_glitch_outro":    dict(type="sfx",       sfx_key="cyber_glitch",    fallback=None,              start=0.0, vol_scale=1.0),
    "vintage_film_burn_outro":dict(type="sfx",       sfx_key="vintage_film_burn",fallback=None,              start=0.0, vol_scale=1.0),
    "cta_card":              dict(type="cta",         sfx_key="cta_card",         fallback="cta_chime.wav",   start=0.0, vol_scale=1.0),
    "smart_quote_animation":  dict(type="ambient",   sfx_key="ambient_mystic",  fallback="ambient_mystic.wav", start=0.0, vol_scale=1.0),
}

_HOOK_BUILDER_MAP = {
    "carousel_quote":           (build_carousel_hook,           "carousel_quote"),
    "typewriter_quote":        (build_typewriter_quote_hook,    "typewriter_quote"),
    "blackout_question":        (build_blackout_question_hook,   "blackout_question"),
    "camera_shutter":           (build_camera_shutter_hook,     "camera_shutter"),
    "cyber_glitch":             (build_cyber_glitch_hook,       "cyber_glitch"),
    "vintage_film_burn":        (build_vintage_film_burn_hook,   "vintage_film_burn"),
    "smash_cut_blackout":        (build_smash_cut_hook,          "smash_cut_blackout"),
    "cinematic_letterbox":       (build_cinematic_letterbox_hook,"cinematic_letterbox"),
    "paper_rip_split":         (build_paper_rip_hook,          "paper_rip_split"),
    "double_exposure":          (build_double_exposure_hook,     "double_exposure"),
    "light_paint_ingress":     (build_light_paint_hook,         "light_paint_ingress"),
    "memory_resurface":         (build_memory_resurface_hook,    "memory_resurface"),
    "forbidden_uncover":        (build_forbidden_uncover_hook,   "forbidden_uncover"),
    "ink_bleed":               (build_ink_bleed_hook,            "ink_bleed"),
    "scene_assembly":           (build_scene_assembly_hook,       "scene_assembly"),
    "carousel_quote_outro":    (build_carousel_hook,            "carousel_quote_outro"),
    "typewriter_quote_outro":  (build_typewriter_quote_hook,    "typewriter_quote_outro"),
    "blackout_question_outro": (build_blackout_question_hook,   "blackout_question_outro"),
    "camera_shutter_outro":   (build_camera_shutter_hook,      "camera_shutter_outro"),
    "cyber_glitch_outro":     (build_cyber_glitch_hook,        "cyber_glitch_outro"),
    "vintage_film_burn_outro":(build_vintage_film_burn_hook,   "vintage_film_burn_outro"),
    "cta_card":               (build_cta_card_hook,            "cta_card"),
    "smart_quote_animation":  (build_smart_quote_animation_hook, "smart_quote_animation"),
}


# ─────────────────────────────────────────────────────────────────────────────
# HOOK REGISTRY — single dispatch table replacing elif chains in video_service.py
# Add a new hook type here: no changes needed in video_service.py
# ─────────────────────────────────────────────────────────────────────────────

import os as _os

_HOOK_AUDIO_SPECS = {
    # Hook audio specs
    "carousel_quote":          dict(type="ding_reel",  sfx_key="carousel_quote",   fallback="ding.wav",               start=0.0, vol_scale=1.0),
    "typewriter_quote":        dict(type="typewriter", sfx_key="typewriter_quote",  fallback=None,              start=0.0, vol_scale=1.0, tick_pct=0.85),
    "blackout_question":       dict(type="tick_burst", sfx_key="typewriter_quote", fallback=None,              start=0.0, vol_scale=1.0, tick_pct=0.85),
    "camera_shutter":          dict(type="sfx",       sfx_key="camera_shutter",   fallback=None,              start=0.0, vol_scale=1.0),
    "cyber_glitch":            dict(type="sfx",       sfx_key="cyber_glitch",     fallback=None,              start=0.0, vol_scale=1.0),
    "vintage_film_burn":       dict(type="sfx",       sfx_key="vintage_film_burn",fallback=None,              start=0.0, vol_scale=1.0),
    "smash_cut_blackout":      dict(type="bass_drop", sfx_key="impact",           fallback="impact_boom.wav",  start=0.5, vol_scale=1.5),
    "cinematic_letterbox":     dict(type="swell",     sfx_key="cinematic_letterbox",fallback="ambient_mystic.wav",start=0.0,vol_scale=1.0),
    "paper_rip_split":        dict(type="bass_drop", sfx_key="impact",           fallback="impact_boom.wav",  start=0.2, vol_scale=1.0),
    "double_exposure":         dict(type="swell",     sfx_key="double_exposure",   fallback="cinematic_swell.wav",start=0.0,vol_scale=1.0),
    "light_paint_ingress":     dict(type="swell",     sfx_key="light_paint_ingress",fallback="cinematic_swell.wav",start=0.0,vol_scale=1.0),
    "memory_resurface":        dict(type="ambient",   sfx_key="ambient_mystic",    fallback="ambient_mystic.wav",start=0.0, vol_scale=1.0),
    "forbidden_uncover":       dict(type="bass_drop", sfx_key="smash_cut_blackout",fallback="impact_boom.wav",start=1.2,vol_scale=1.0),
    "ink_bleed":              dict(type="ambient",   sfx_key="ink_bleed",         fallback="ambient_mystic.wav",start=0.0, vol_scale=1.0),
    "scene_assembly":          dict(type="swell",     sfx_key="scene_assembly",    fallback="cinematic_swell.wav",start=0.0,vol_scale=1.0),
    # Outro audio specs (different SFX patterns)
    "carousel_quote_outro":   dict(type="carousel",   sfx_key="carousel_quote",   fallback=None,              start=0.0, vol_scale=1.0),
    "typewriter_quote_outro":  dict(type="typewriter", sfx_key="typewriter_quote",fallback=None,              start=0.0, vol_scale=1.0, tick_pct=0.0),
    "blackout_question_outro":dict(type="tick_burst", sfx_key="typewriter_quote",fallback=None,              start=0.0, vol_scale=1.0, tick_pct=0.0),
    "camera_shutter_outro":   dict(type="sfx",       sfx_key="camera_shutter",  fallback=None,              start=0.0, vol_scale=1.0),
    "cyber_glitch_outro":     dict(type="sfx",       sfx_key="cyber_glitch",    fallback=None,              start=0.0, vol_scale=1.0),
    "vintage_film_burn_outro": dict(type="sfx",       sfx_key="vintage_film_burn",fallback=None,              start=0.0, vol_scale=1.0),
    "cta_card":               dict(type="cta",         sfx_key="cta_card",         fallback="cta_chime.wav",   start=0.0, vol_scale=1.0),
    # Hook mới:
    "smart_quote_animation":  dict(type="ambient",   sfx_key="ambient_mystic",  fallback="ambient_mystic.wav", start=0.0, vol_scale=1.0),
}

_HOOK_BUILDER_MAP = {
    "carousel_quote":           (build_carousel_hook,           "carousel_quote"),
    "typewriter_quote":         (build_typewriter_quote_hook,    "typewriter_quote"),
    "blackout_question":         (build_blackout_question_hook,    "blackout_question"),
    "camera_shutter":           (build_camera_shutter_hook,      "camera_shutter"),
    "cyber_glitch":             (build_cyber_glitch_hook,        "cyber_glitch"),
    "vintage_film_burn":        (build_vintage_film_burn_hook,   "vintage_film_burn"),
    "smash_cut_blackout":       (build_smash_cut_hook,          "smash_cut_blackout"),
    "cinematic_letterbox":      (build_cinematic_letterbox_hook,"cinematic_letterbox"),
    "paper_rip_split":         (build_paper_rip_hook,          "paper_rip_split"),
    "double_exposure":          (build_double_exposure_hook,      "double_exposure"),
    "light_paint_ingress":      (build_light_paint_hook,        "light_paint_ingress"),
    "memory_resurface":         (build_memory_resurface_hook,   "memory_resurface"),
    "forbidden_uncover":         (build_forbidden_uncover_hook,  "forbidden_uncover"),
    "ink_bleed":               (build_ink_bleed_hook,          "ink_bleed"),
    "scene_assembly":           (build_scene_assembly_hook,      "scene_assembly"),
    "carousel_quote_outro":     (build_carousel_hook,            "carousel_quote_outro"),
    "typewriter_quote_outro":   (build_typewriter_quote_hook,    "typewriter_quote_outro"),
    "blackout_question_outro":  (build_blackout_question_hook,   "blackout_question_outro"),
    "camera_shutter_outro":     (build_camera_shutter_hook,     "camera_shutter_outro"),
    "cyber_glitch_outro":      (build_cyber_glitch_hook,       "cyber_glitch_outro"),
    "vintage_film_burn_outro":  (build_vintage_film_burn_hook,  "vintage_film_burn_outro"),
    "cta_card":                (build_cta_card_hook,            "cta_card"),
    "smart_quote_animation":   (build_smart_quote_animation_hook, "smart_quote_animation"),
}

# Public dispatch table
HOOK_REGISTRY = {k: {"builder_fn": v[0], "audio": _HOOK_AUDIO_SPECS[v[1]]}
                  for k, v in _HOOK_BUILDER_MAP.items()}


def build_audio_placements(audio_spec, effect_type, duration, sfx_dir, reel_key, volume,
                          resolve_effect_sfx_fn, hook_sfx_level_fn, hook_sfx_max_dur_fn,
                          start_offset=0.0):
    placements = []
    atype     = audio_spec.get("type", "none")
    sfx_key   = audio_spec.get("sfx_key")
    fallback  = audio_spec.get("fallback")
    start     = start_offset + audio_spec.get("start", 0.0)
    vol_scale = audio_spec.get("vol_scale", 1.0)
    tick_pct  = audio_spec.get("tick_pct", 0.0)

    def sfx_path(name):
        return _os.path.join(sfx_dir, name) if name else ""

    def max_dur(d):
        return hook_sfx_max_dur_fn(d)

    DING_VARIANTS = {"arcade_8bit": "ding_v1_arcade.wav"}
    DEFAULT_DING   = "ding.wav"

    lvl = hook_sfx_level_fn(reel_key, volume) * vol_scale

    if atype == "ding_reel":
        reel = resolve_effect_sfx_fn(sfx_key, reel_key) if sfx_key else None
        ding  = sfx_path(DING_VARIANTS.get(reel_key, DEFAULT_DING))
        if reel:
            placements.append((reel, start, lvl, 0.0, duration))
        if _os.path.isfile(ding):
            placements.append((ding, start + 2.0, hook_sfx_level_fn("_ding", volume) * vol_scale, 0.0))

    elif atype == "typewriter":
        typewriter_sfx = resolve_effect_sfx_fn(sfx_key, reel_key) if sfx_key else None
        tick_dur = duration * tick_pct if tick_pct > 0 else 0
        if typewriter_sfx and tick_dur > 0:
            placements.append((typewriter_sfx, start, lvl, 0.0, tick_dur))
        if tick_pct > 0:
            tick_sfx = sfx_path("tick.wav")
            if _os.path.isfile(tick_sfx):
                steps    = max(1, min(10, 24))
                step_dur = tick_dur / max(1, steps)
                lvl_tick = hook_sfx_level_fn("_tick", volume)
                for i in range(steps):
                    placements.append((tick_sfx, start + i * step_dur, lvl_tick, 0.0, step_dur + 0.05))

    elif atype == "tick_burst":
        if tick_pct > 0:
            tick_dur  = duration * tick_pct
            tick_sfx  = sfx_path("tick.wav")
            if _os.path.isfile(tick_sfx):
                steps    = max(1, min(10, 24))
                step_dur = tick_dur / max(1, steps)
                lvl_tick = hook_sfx_level_fn("_tick", volume)
                for i in range(steps):
                    placements.append((tick_sfx, start + i * step_dur, lvl_tick, 0.0, step_dur + 0.05))

    elif atype == "sfx":
        sfx = resolve_effect_sfx_fn(sfx_key, reel_key) if sfx_key else None
        if sfx:
            placements.append((sfx, start, lvl, 0.0, max_dur(duration)))

    elif atype == "bass_drop":
        bass = resolve_effect_sfx_fn(sfx_key, reel_key) or sfx_path(fallback or "impact_boom.wav")
        if _os.path.isfile(bass):
            offset = audio_spec.get("start", 0.0)
            placements.append((bass, start, lvl, 0.0, max_dur(max(0.1, duration - offset))))

    elif atype == "swell":
        swell = resolve_effect_sfx_fn(sfx_key, reel_key) or sfx_path(fallback or "cinematic_swell.wav")
        if _os.path.isfile(swell):
            placements.append((swell, start, lvl, 0.0, max_dur(duration)))

    elif atype == "ambient":
        amb = resolve_effect_sfx_fn(sfx_key, reel_key) or sfx_path(fallback or "ambient_mystic.wav")
        if _os.path.isfile(amb):
            placements.append((amb, start, lvl, 0.0))

    elif atype == "cta":
        ding = resolve_effect_sfx_fn(sfx_key, reel_key) or sfx_path(fallback or "cta_chime.wav")
        if _os.path.isfile(ding):
            placements.append((ding, start, lvl, 0.0))

    elif atype == "carousel":
        reel_sfx = resolve_effect_sfx_fn(sfx_key, reel_key) if sfx_key else None
        whoosh   = sfx_path("whoosh.wav")
        ding     = sfx_path(DING_VARIANTS.get(reel_key, DEFAULT_DING))
        if _os.path.isfile(whoosh):
            placements.append((whoosh, start, hook_sfx_level_fn("_whoosh", volume) * vol_scale, 0.0, max_dur(duration)))
        if reel_sfx:
            slot_dur = SLOT_DURATION
            placements.append((reel_sfx, start + slot_dur, lvl, 0.0, max_dur(duration - slot_dur)))
        if _os.path.isfile(ding):
            carousel_dur = 4.5
            placements.append((ding, start + carousel_dur - 0.5,
                              hook_sfx_level_fn("_ding", volume) * vol_scale, 0.0, max_dur(0.5)))

    return placements


def build_hook(hook_type, cover_img, quote_text, w, h, duration, *, instant=False):
    entry = _HOOK_BUILDER_MAP.get(hook_type)
    if entry is None:
        return None
    builder_fn, _ = entry
    type1_hooks = ("typewriter_quote", "typewriter_quote_outro", "blackout_question", "blackout_question_outro", "smash_cut_blackout")
    type2_hooks = ("carousel_quote", "carousel_quote_outro", "cta_card")
    
    if hook_type in type1_hooks:
        if "typewriter" in hook_type:
            return builder_fn(quote_text, w, h, duration, cover_img, instant=instant)
        return builder_fn(quote_text, w, h, duration, cover_img)
    elif hook_type in type2_hooks:
        return builder_fn(cover_img, quote_text, w, h, duration)
    else:
        return builder_fn(cover_img, w, h, duration, quote_text)


def get_hook_audio_spec(hook_type):
    entry = _HOOK_BUILDER_MAP.get(hook_type)
    if entry is None:
        return None
    _, spec_name = entry
    return _HOOK_AUDIO_SPECS.get(spec_name)
