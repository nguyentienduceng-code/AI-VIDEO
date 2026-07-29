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
            .with_start(slot_dur + 0.1)
            .with_duration(duration - slot_dur - 0.1)
            .with_effects([CrossFadeIn(0.5)])
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

    return CompositeVideoClip([zoomed, burn], size=(video_width, video_height)).with_duration(duration)

