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
    Clip mở màn với Slot Machine (trục quay) + Quote Reveal.
    0.0s - 2.0s: BÌA SÁCH THẬT cuộn dọc như trục máy xèng (reel scroll), nền blurred-fill.
    2.0s - 4.5s: Bìa dừng hẳn ở giữa (KHÔNG nảy), hiện Quote trên nền mờ.
    """
    w, h = video_width, video_height
    slot_dur = SLOT_DURATION
    reveal_dur = duration - slot_dur

    # Import chung ở đầu hàm: cần cho cả bìa thật (dưới đây) lẫn strip ảnh giả (bên dưới),
    # bất kể nhánh .mp4 hay ảnh tĩnh có chạy hay không.
    from PIL import Image, ImageOps

    # ── Bìa thật (fit vào tỷ lệ an toàn tùy theo màn dọc hay ngang) ──
    try:
        if cover_image_path.endswith(".mp4"):
            from moviepy.video.io.VideoFileClip import VideoFileClip
            with VideoFileClip(cover_image_path) as v:
                cover = ImageClip(v.get_frame(0))
        else:
            # ImageClip(path) đọc pixel thô, KHÔNG tự xoay theo cờ EXIF Orientation —
            # ảnh dọc chụp bằng điện thoại (lưu mảng pixel ngang + tag "rotate 90") khiến
            # cover.w/cover.h bị đọc ngược. (cw, ch) tính từ đây sai lệch kéo theo
            # ImageOps.fit() ở strip máy xèng bên dưới cắt méo mọi bìa (thật lẫn giả).
            # Phải tự exif_transpose trước khi giao cho ImageClip.
            cover_img = ImageOps.exif_transpose(Image.open(cover_image_path)).convert("RGB")
            cover = ImageClip(np.array(cover_img))

        is_landscape = w > h
        if is_landscape:
            # Ngang 16:9: bìa cao hơn (70% màn hình), chữ sẽ nằm phía dưới hoặc cạnh
            fit = min(w * 0.4 / cover.w, h * 0.7 / cover.h)
        else:
            # Dọc 9:16: fit ~70% ngang, ~45% cao
            fit = min(w * 0.72 / cover.w, h * 0.46 / cover.h)
    except Exception as e:
        logger.warning(f"Hook cover error: {e}")
        cover = ColorClip((int(w * 0.6), int(h * 0.4)), color=(230, 230, 230))
        fit = 1.0
        
    cover_fit = cover.resized(fit)
    cw, ch = cover_fit.w, cover_fit.h
    cx = int((w - cw) / 2)
    cy = int(h / 2 - ch / 2)
    if is_landscape:
        cy = int(h * 0.1)  # Đẩy bìa lên cao một chút để nhường chỗ cho quote ở dưới

    # ── Phase 1: Slot Machine — Chuỗi ảnh thật cuộn dọc, dừng đúng giữa ──
    bg1 = _blurred_fill_bg(cover_image_path, w, h, slot_dur, darken=0.35)
    gap = ch + int(h * 0.04)

    import os
    import glob
    import random

    from config import SLOT_COVERS_DIR
    slot_covers_dir = SLOT_COVERS_DIR
    fake_paths = []
    if os.path.isdir(slot_covers_dir):
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG", "*.JPEG"):
            fake_paths.extend(glob.glob(os.path.join(slot_covers_dir, ext)))
            
    num_fakes = NUM_FAKES
    if fake_paths:
        selected_fakes = [random.choice(fake_paths) for _ in range(num_fakes)]
    else:
        selected_fakes = [cover_image_path] * num_fakes

    # Tạo một bức ảnh dài (strip) ghép các ảnh lại
    strip_h = int(gap * num_fakes + ch)
    strip_img = Image.new('RGBA', (cw, strip_h), (0,0,0,0))
    
    # Load bìa thật
    try:
        if cover_image_path.endswith(".mp4"):
            from moviepy.video.io.VideoFileClip import VideoFileClip
            with VideoFileClip(cover_image_path) as v:
                raw_real = Image.fromarray(v.get_frame(0))
                real_img = ImageOps.fit(raw_real, (cw, ch), Image.Resampling.LANCZOS).convert("RGBA")
        else:
            raw_real = ImageOps.exif_transpose(Image.open(cover_image_path))
            real_img = ImageOps.fit(raw_real, (cw, ch), Image.Resampling.LANCZOS).convert("RGBA")
    except Exception as e:
        logger.warning(f"Hook slot real_img error: {e}")
        real_img = Image.new('RGBA', (cw, ch), (255,255,255,255))
        
    # ── TOẠ ĐỘ STRIP (đọc kỹ trước khi sửa) ──
    # Strip trôi XUỐNG: y của nó chạy từ (cy - num_fakes*gap) đến cy.
    # Ảnh nằm ở toạ độ local L sẽ hiện GIỮA màn hình khi strip_y + L == cy.
    #   • t=0 → strip_y = cy - num_fakes*gap → ảnh ở L = num_fakes*gap nằm giữa.
    #   • t=1 → strip_y = cy                 → ảnh ở L = 0 nằm giữa.
    # Vậy ảnh dừng lại cuối cùng là ảnh ở ĐỈNH strip (L=0) ⇒ BÌA THẬT PHẢI Ở L=0,
    # các bìa giả xếp bên dưới.
    # LỖI CŨ: bìa thật bị đặt ở ĐÁY strip (L = num_fakes*gap) nên nó nằm giữa ngay từ t=0
    # rồi trôi đi mất; máy xèng kết thúc trên một bìa GIẢ và Phase 2 cắt phựt sang bìa thật.
    strip_img.paste(real_img, (0, 0))
    for i, fp in enumerate(selected_fakes):
        try:
            raw_fk = ImageOps.exif_transpose(Image.open(fp))
            fk_img = ImageOps.fit(raw_fk, (cw, ch), Image.Resampling.LANCZOS).convert("RGBA")
        except Exception:
            fk_img = real_img
        strip_img.paste(fk_img, (0, int((i + 1) * gap)))

    strip_clip = ImageClip(np.array(strip_img))

    def _scroll(t):
        p = min(t / slot_dur, 1.0)
        # Ease-out BẬC 3, không phải bậc 2: bậc 2 tiến tới đích quá chậm, khung hình cuối
        # cùng của pha quay vẫn còn lệch ~18px so với vị trí chốt → sang pha 2 ảnh nhảy
        # một cái. Bậc 3 thì sai số dưới 0.1px, mắt không thấy.
        # (Với slot_dur=2.0s @30fps: khung cuối p=0.983 → lệch còn ~0.04px.)
        ease = 1 - (1 - p) ** 3
        return ease * num_fakes * gap      # cuộn vừa vặn num_fakes khoảng gap

    rc = strip_clip.with_position(lambda t: (cx, int(cy - num_fakes * gap + _scroll(t)))).with_duration(slot_dur)

    slot = CompositeVideoClip([bg1, rc], size=(w, h)).with_duration(slot_dur)

    # ── Phase 2: Reveal — bìa dừng giữa (thu nhẹ) + Quote, nền blurred-fill ──
    # darken PHẢI trùng bg1: trước đây 0.35 vs 0.4 làm nền sáng vọt ~15% ngay tại
    # đường nối 2 pha — thấy như một cú chớp sáng.
    bg2 = _blurred_fill_bg(cover_image_path, w, h, reveal_dur, darken=0.35)

    # ── Bìa đứng YÊN sau khi chốt (bỏ hẳn cú nảy zoom) ──
    # Trước đây có hàm _settle() làm bìa phồng lên 5% rồi co lại theo nửa chu kỳ sin
    # trong 0.35s. Người dùng thấy nó lắc nên đã bỏ.
    #
    # Bỏ LUÔN cả .resized(): hệ số giờ là hằng số 1.0, nhưng hễ truyền một HÀM vào
    # resized() là MoviePy coi như biến thiên theo thời gian và resize lại cả tấm bìa
    # ở MỌI khung hình — trả giá CPU cho một phép biến đổi không thay đổi gì. Dùng
    # thẳng cover_fit vừa đúng ý đồ vừa nhanh hơn.
    #
    # Vẫn dùng CHÍNH cover_fit và cy của pha 1 (không tính lại từ ảnh gốc): nhờ vậy
    # kích thước và toạ độ trùng khít pha 1 từng pixel, không "nhích" tại đường nối.
    cover_reveal = cover_fit.with_position(("center", cy)).with_duration(reveal_dur)

    # KHÔNG bịa quote mặc định nữa. Trước đây khi user để trống, hook luôn hiện câu
    # "GIÁ TRỊ NẰM Ở SỰ LỰA CHỌN" — một câu chung chung không liên quan tới cuốn sách,
    # LẠI nằm đúng vùng phụ đề của Cảnh 1 nên hai khối chữ đè lên nhau. Để trống thì
    # hook chỉ còn bìa sách sạch sẽ, đúng ý đồ hơn.
    layers2 = [bg2, cover_reveal]
    if quote_text and quote_text.strip():
        # Ngang 16:9: chữ nằm dưới bìa (cy + ch + khoảng trống) hoặc 85% chiều cao.
        text_y = int(cy + ch + 30) if is_landscape else int(h * 0.74)

        # _safe_caption_clip thay vì TextClip trực tiếp: quote 2+ dòng bị cắt cụt dòng
        # cuối nếu tự đo chiều cao thẳng từ MoviePy (đã verify bằng ảnh thật — không
        # liên quan riêng gì tới carousel, xảy ra với mọi TextClip(method="caption")
        # đa dòng trong file này).
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
            .with_duration(reveal_dur)
            .with_effects([CrossFadeIn(0.4)])
        )
        layers2.append(txt_clip)

    part2 = CompositeVideoClip(layers2, size=(w, h)).with_duration(reveal_dur)

    return concatenate_videoclips([slot, part2])

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
        bg = _blurred_fill_bg(cover_image_path, video_width, video_height, duration, darken=0.15)
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
) -> CompositeVideoClip:
    '''Nền tối, câu trích dẫn hiện dần theo TỪ (typewriter thật, không phải crossfade nguyên khối).'''
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

