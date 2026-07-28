# backend/services/hook_engine.py
import logging

import numpy as np
from moviepy import (
    ImageClip, ColorClip, CompositeVideoClip, TextClip,
    concatenate_videoclips,
)
from moviepy.video.fx import CrossFadeIn

logger = logging.getLogger(__name__)

# Font dùng chung cho MỌI hiệu ứng hook có chữ. PHẢI là đường dẫn file .ttf thật,
# không phải tên họ font: Windows/Pillow không tự dò tên font ra file, và ta đã từng
# ăn lỗi này với "Arial Black" thiếu glyph ư/ơ tiếng Việt — seguibl.ttf (Segoe UI Black)
# là font hệ thống đã xác nhận có đủ dấu tiếng Việt.
HOOK_FONT = "C:/Windows/Fonts/seguibl.ttf"


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
    """
    kwargs = dict(font=HOOK_FONT, font_size=font_size, method="caption",
                  text_align="center", **extra)
    if box_h is not None:
        return TextClip(text=text, size=(box_w, box_h), **kwargs)
    probe = TextClip(text=text, size=(box_w, None), **kwargs)
    padded_h = probe.h + 40
    probe.close()
    return TextClip(text=text, size=(box_w, padded_h), **kwargs)

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


def _blurred_fill_bg(cover_path: str, w: int, h: int, duration: float, darken: float = 0.5):
    """
    Nền LẤP ĐẦY khung 9:16 = bản phóng to + làm mờ của chính bìa (bỏ viền đen).
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
        img = img.resize((nw, nh)).filter(ImageFilter.GaussianBlur(35))
        left, top = (nw - w) // 2, (nh - h) // 2
        img = img.crop((left, top, left + w, top + h))
        arr = (np.array(img).astype(np.float32) * darken).astype(np.uint8)
        return ImageClip(arr).with_duration(duration)
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
    Clip mở màn với hiệu ứng Cinematic Float-In (Thay thế Slot Machine cũ).
    Bìa sách từ từ nổi lên và mờ dần rõ nét (Fade-in + Float up), tĩnh lặng và sang trọng.
    """
    w, h = video_width, video_height

    from PIL import Image, ImageOps

    # ── Bìa thật (fit vào tỷ lệ an toàn tùy theo màn dọc hay ngang) ──
    try:
        if cover_image_path.endswith(".mp4"):
            from moviepy.video.io.VideoFileClip import VideoFileClip
            with VideoFileClip(cover_image_path) as v:
                cover = ImageClip(v.get_frame(0))
        else:
            cover_img = ImageOps.exif_transpose(Image.open(cover_image_path)).convert("RGB")
            cover = ImageClip(np.array(cover_img))

        is_landscape = w > h
        if is_landscape:
            fit = min(w * 0.4 / cover.w, h * 0.7 / cover.h)
        else:
            fit = min(w * 0.72 / cover.w, h * 0.46 / cover.h)
    except Exception as e:
        logger.warning(f"Hook cover error: {e}")
        cover = ColorClip((int(w * 0.6), int(h * 0.4)), color=(230, 230, 230))
        fit = 1.0
        is_landscape = w > h
        
    cover_fit = cover.resized(fit)
    cw, ch = cover_fit.w, cover_fit.h
    cy = int(h / 2 - ch / 2)
    if is_landscape:
        cy = int(h * 0.1)

    # ── Nền mờ ──
    bg = _blurred_fill_bg(cover_image_path, w, h, duration, darken=0.4)

    # ── Hiệu ứng Cinematic Float-In cho bìa sách ──
    # Bìa sách mờ dần hiện ra và nổi nhẹ lên trên trong 1.5s đầu
    def _float_y(t):
        p = min(t / 1.5, 1.0)
        ease = 1 - (1 - p) ** 3 # Ease-out cubic
        return int(cy + 80 * (1 - ease))

    cover_clip = (
        cover_fit
        .with_position(lambda t: ("center", _float_y(t)))
        .with_duration(duration)
        .with_effects([CrossFadeIn(1.2)])
    )

    layers = [bg, cover_clip]

    # ── Trích dẫn (nếu có) ──
    if quote_text and quote_text.strip():
        text_y = int(cy + ch + 30) if is_landscape else int(h * 0.74)
        txt_clip = (
            _safe_caption_clip(
                text=quote_text.strip(),
                font_size=60,
                box_w=int(w * 0.88),
                color="white",
                stroke_color="black",
                stroke_width=4,
            )
            .with_position(("center", text_y))
            .with_start(0.8)
            .with_duration(duration - 0.8)
            .with_effects([CrossFadeIn(0.8)])
        )
        layers.append(txt_clip)

    return CompositeVideoClip(layers, size=(w, h)).with_duration(duration)

# ══════════════════════════════════════════════════════════════════════
# HOOK A1: Blackout Question
# ══════════════════════════════════════════════════════════════════════
def build_blackout_question_hook(
    quote_text: str,
    video_width: int,
    video_height: int,
    duration: float = 1.5,
    cover_image_path: str = "",
) -> CompositeVideoClip:
    '''Nền mờ siêu tối (cinematic blackout) từ bìa sách, một dòng chữ sáng bật ra.'''
    if cover_image_path:
        bg = _blurred_fill_bg(cover_image_path, video_width, video_height, duration, darken=0.4)
    else:
        bg = ColorClip(size=(video_width, video_height), color=(12, 12, 15)).with_duration(duration)

    text = (quote_text or "").strip()
    if not text:
        return bg

    try:
        # Chữ màu trắng sáng, font to, không có viền đen thừa mứa trên nền tối
        txt = _safe_caption_clip(
            text, int(video_width * 0.055), int(video_width * 0.85),
            color="#FFFFFF"
        )
        # Hiệu ứng Pop-in Scale: Phóng to từ nhỏ lên to
        def pop_scale(t):
            p = min(t / 0.2, 1.0)
            return 0.5 + 0.5 * (1 - (1 - p)**3) # Ease-out cubic

        txt = (
            txt.with_position("center")
            .with_duration(duration)
            .resized(pop_scale)
        )
        return CompositeVideoClip([bg, txt], size=(video_width, video_height)).with_duration(duration)
    except Exception as e:
        logger.error(f"Blackout hook error: {e}")
        return bg


# ══════════════════════════════════════════════════════════════════════
# HOOK A2: Typewriter Quote
# ══════════════════════════════════════════════════════════════════════
def build_typewriter_quote_hook(
    quote_text: str,
    video_width: int,
    video_height: int,
    duration: float = 2.5,
    cover_image_path: str = "",
) -> CompositeVideoClip:
    '''Nền tối, câu trích dẫn hiện dần theo TỪ (typewriter thật, không phải crossfade nguyên khối).'''
    if cover_image_path:
        bg = _blurred_fill_bg(cover_image_path, video_width, video_height, duration, darken=0.6)
    else:
        bg = ColorClip(size=(video_width, video_height), color=(15, 15, 20)).with_duration(duration)

    text = (quote_text or "").strip()
    if not text:
        return bg

    box_w = int(video_width * 0.8)
    font_size = int(video_width * 0.05)
    style = dict(color="white", stroke_color="black", stroke_width=3)

    try:
        # Đo khung chữ bằng CÂU ĐẦY ĐỦ một lần duy nhất qua _safe_caption_clip (đã lo
        # sẵn biên đệm chống cắt dòng cuối), rồi ép MỌI bước hiện chữ dùng đúng
        # size=(box_w, canvas_h) cố định đó — TextClip với size cố định luôn trả về
        # cùng shape mảng dù text ngắn hơn (đã verify); thiếu bước này thì mỗi bước gõ
        # chữ ra kích thước ảnh khác nhau, concatenate_videoclips vỡ ngay.
        probe = _safe_caption_clip(text, font_size, box_w, **style)
        canvas_h = probe.h
        probe.close()

        words = text.split()
        n_words = len(words)
        # Gõ xong ở 85% thời lượng, giữ nguyên câu đủ ở 15% cuối trước khi cắt sang cảnh 1 —
        # gõ xong đúng lúc cắt cảnh sẽ khiến người xem không kịp đọc trọn câu.
        reveal_dur = duration * 0.85
        hold_dur = duration - reveal_dur
        steps = max(1, min(n_words, 24))  # trần 24 bước: câu dài không dựng quá nhiều TextClip
        step_dur = reveal_dur / steps

        clips = []
        for i in range(1, steps + 1):
            word_count = max(1, round(n_words * i / steps))
            partial = " ".join(words[:word_count])
            
            # Thêm con trỏ nhấp nháy '|' (Blinking Cursor)
            cursor = "|" if (i % 2 == 1) else ""
            partial_with_cursor = partial + " " + cursor

            clips.append(
                _safe_caption_clip(partial_with_cursor, font_size, box_w, box_h=canvas_h, **style).with_duration(step_dur)
            )
        if hold_dur > 0:
            clips.append(_safe_caption_clip(text, font_size, box_w, box_h=canvas_h, **style).with_duration(hold_dur))

        txt_anim = concatenate_videoclips(clips).with_position("center")
        return CompositeVideoClip([bg, txt_anim], size=(video_width, video_height)).with_duration(duration)
    except Exception as e:
        logger.error(f"Typewriter hook error: {e}")
        return bg


# ══════════════════════════════════════════════════════════════════════
# HOOK C3: Breathing Vignette
# ══════════════════════════════════════════════════════════════════════
def _vignette_overlay_rgba(w: int, h: int, strength: float = 0.55) -> np.ndarray:
    """
    Ảnh RGBA tĩnh: trong suốt ở tâm (bán kính tới 55%), tối dần ra góc.
    Đây là vignette THẬT (chỉ tối 4 góc) — khác với overlay đen phủ đều cả khung
    (trước đây), vốn chỉ là một lớp fade phẳng, không tạo cảm giác "thu hẹp tầm nhìn".
    """
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = w / 2.0, h / 2.0
    dist = np.sqrt(((xx - cx) / (w / 2.0)) ** 2 + ((yy - cy) / (h / 2.0)) ** 2)
    falloff = np.clip((dist - 0.55) / 0.45, 0.0, 1.0)
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[..., 3] = (falloff * 255 * strength).astype(np.uint8)
    return rgba


def build_breathing_vignette_hook(
    cover_image_path: str,
    video_width: int,
    video_height: int,
    duration: float = 3.0,
) -> CompositeVideoClip:
    '''Ken Burns chậm + vignette tối 4 góc (không phải màn tối phẳng).'''
    from PIL import Image, ImageOps

    try:
        if cover_image_path.endswith(".mp4"):
            from moviepy.video.io.VideoFileClip import VideoFileClip
            with VideoFileClip(cover_image_path) as v:
                img = Image.fromarray(v.get_frame(0))
        else:
            img = ImageOps.exif_transpose(Image.open(cover_image_path)).convert("RGB")

        img_filled = ImageOps.fit(img, (video_width, video_height), Image.Resampling.LANCZOS)
        base_clip = ImageClip(np.array(img_filled))
    except Exception as e:
        logger.error(f"Breathing vignette cover error: {e}")
        base_clip = ColorClip(size=(video_width, video_height), color=(30, 30, 30))

    # Zoom chậm 1.0 → 1.04. API MoviePy 2.x là `.resized()`, không phải `.resize()` (1.x).
    def resize_func(t):
        return 1.0 + 0.04 * (t / duration)

    zoomed = base_clip.resized(resize_func).with_position("center").with_duration(duration)

    overlay_arr = _vignette_overlay_rgba(video_width, video_height)
    overlay = ImageClip(overlay_arr).with_duration(duration)

    return CompositeVideoClip([zoomed, overlay], size=(video_width, video_height)).with_duration(duration)


# ══════════════════════════════════════════════════════════════════════
# HOOK C4: Camera Shutter (Nháy máy ảnh)
# ══════════════════════════════════════════════════════════════════════
def build_camera_shutter_hook(
    cover_image_path: str,
    video_width: int,
    video_height: int,
    duration: float = 2.0,
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

    # Freeze frame sau flash chớp (sau 0.15s, thu nhỏ lại một chút 0.95 scale)
    def resize_shutter(t):
        if t < 0.15:
            return 1.05
        return 0.92

    photo_clip = base_clip.resized(resize_shutter).with_position("center")
    
    # Flash chớp trắng (0 -> 0.15s)
    flash = ColorClip(size=(video_width, video_height), color=(255, 255, 255)).with_duration(0.15).with_opacity(0.8)

    return CompositeVideoClip([bg, photo_clip, flash], size=(video_width, video_height)).with_duration(duration)


# ══════════════════════════════════════════════════════════════════════
# HOOK C5: Cyber Glitch (Nhiễu sóng)
# ══════════════════════════════════════════════════════════════════════
def build_cyber_glitch_hook(
    cover_image_path: str,
    video_width: int,
    video_height: int,
    duration: float = 2.0,
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

    def glitch_filter(get_frame, t):
        frame = get_frame(t)
        # Glitch trong 0.4s đầu
        if t < 0.4:
            # Nháy âm bản ở t=0.1, t=0.3
            if (0.1 < t < 0.15) or (0.25 < t < 0.3):
                frame = 255 - frame
            # Dịch sọc ngang (RGB split giả)
            if (0.05 < t < 0.2) or (0.3 < t < 0.35):
                shift = int(video_width * 0.05)
                # Dịch kênh Đỏ sang phải
                frame_shifted = np.copy(frame)
                frame_shifted[:, shift:, 0] = frame[:, :-shift, 0]
                return frame_shifted
        return frame

    glitched = base_clip.transform(glitch_filter)
    return CompositeVideoClip([glitched], size=(video_width, video_height)).with_duration(duration)


# ══════════════════════════════════════════════════════════════════════
# HOOK C6: Vintage Film Burn (Cháy phim)
# ══════════════════════════════════════════════════════════════════════
def build_vintage_film_burn_hook(
    cover_image_path: str,
    video_width: int,
    video_height: int,
    duration: float = 2.5,
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

    # Zoom chậm ra
    zoomed = base_clip.resized(lambda t: 1.05 - 0.02 * (t / duration)).with_position("center").with_duration(duration)

    # Vệt cháy phim: ColorClip cam, opacity lên xuống theo thời gian
    burn = ColorClip(size=(video_width, video_height), color=(255, 100, 30)).with_duration(duration)
    
    def burn_opacity(t):
        if t < 0.3: return 0.6 * (t / 0.3)
        if t < 0.6: return 0.6
        if t < 1.0: return 0.6 * (1 - (t - 0.6)/0.4)
        return 0.0

    burn = burn.with_opacity(burn_opacity)

    return CompositeVideoClip([zoomed, burn], size=(video_width, video_height)).with_duration(duration)

