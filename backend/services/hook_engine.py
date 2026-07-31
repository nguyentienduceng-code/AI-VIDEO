# backend/services/hook_engine.py
import functools
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
        # GIỮ NGUYÊN darken=0.4 + blur mặc định: "siêu tối" là chủ đích của hiệu ứng này,
        # nền cố tình không cạnh tranh với chữ (khác typewriter, nơi nền mờ đặc chỉ là
        # tác dụng phụ ngoài ý muốn). Chỉ thêm phần còn THIẾU: chuyển động.
        # Không có zoom thì đây cũng là một khung ImageClip chết — pop-in của chữ chỉ chạy
        # 0.2s đầu, phần còn lại đứng hình y hệt lỗi đã đo được ở typewriter.
        bg = _blurred_fill_bg(
            cover_image_path, video_width, video_height, duration,
            darken=0.4, zoom_to=1.05,
        )
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

        clips = []
        for a, b in zip(moc, moc[1:]):
            if b - a < 0.02:      # khoảng vụn do 2 lưới mốc rơi sát nhau
                continue
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


def build_breathing_vignette_hook(
    cover_image_path: str,
    video_width: int,
    video_height: int,
    duration: float = 3.0,
    quote_text: str = "",
    quick_reveal: bool = False,
) -> CompositeVideoClip:
    """
    LÀM LẠI TỪ ĐẦU — bản cũ chỉ là Ken Burns + vignette tối góc TĨNH, yếu nhất trong 7
    hook: không có khoảnh khắc "mở màn" nào cả, gần như không phân biệt được với một
    cảnh thường (đã xác nhận bằng ảnh render thật, xem ghi chú phiên đánh giá hook).

    Giờ có 2 chuyển động thật, đúng tinh thần "breathing":
    1. SPOTLIGHT REVEAL (~35% đầu thời lượng, hoặc gần như tức thì nếu `quick_reveal`):
       đốm sáng loang từ tâm khung ra trên nền đen, ease-out — người xem THẤY một hành
       động đang diễn ra ngay khung hình đầu.
    2. VIGNETTE "THỞ" THẬT: độ tối 4 góc dao động nhẹ theo hình sin SUỐT video (chu kỳ
       ~2.4s) thay vì một lớp tối cố định — đây là phần biến cái tên "breathing" từ
       ẩn dụ suông thành một chuyển động mắt thấy được.

    `quick_reveal=True` (dùng cho OUTRO): pha loang sáng chỉ ~0.2s thay vì tới 35% thời
    lượng. Pha loang dài hợp để mở màn (tạo tò mò trước khi lộ ảnh), nhưng ở outro thì
    chỉ là gần 1 giây đầu người xem chưa thấy gì — đúng lúc họ đã sẵn sàng lướt đi.
    """
    from PIL import Image, ImageOps
    from moviepy.video.VideoClip import VideoClip
    import math as _math

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

    base_clip = base_clip.with_duration(duration)
    dist = _radial_dist(video_width, video_height)

    # ── Pha 1: đốm sáng loang từ tâm trên nền đen ──
    REVEAL_DUR = 0.2 if quick_reveal else min(1.0, duration * 0.35)
    REVEAL_EDGE = 0.16   # bề rộng vùng mờ ở mép đốm sáng (tỉ lệ theo bán kính chuẩn hoá)

    def _reveal_alpha(t: float) -> np.ndarray:
        p = min(1.0, t / REVEAL_DUR)
        ease = 1.0 - (1.0 - p) ** 3        # ease-out cubic: loang nhanh lúc đầu, chậm dần
        radius = 1.5 * ease                # 1.5 > ~1.41 (góc xa nhất) để phủ hết khung
        return np.clip((radius - dist) / REVEAL_EDGE + 0.5, 0.0, 1.0)

    # Áp mask NGAY TRÊN base_clip (kích thước cố định video_width×video_height), CHƯA
    # zoom — .resized() của MoviePy đổi THẬT kích thước mảng khung hình theo thời gian,
    # trong khi mask ở đây dựng sẵn đúng 1 kích thước cố định; ghép mask sau khi đã zoom
    # sẽ lệch shape giữa 2 mảng và vỡ ngay (đã ăn lỗi này thật ở vintage_film_burn, xem
    # ghi chú tại đó — cùng một lớp lỗi, sửa cùng một cách: mask/texture luôn đứng TRƯỚC
    # resize trong chuỗi biến đổi).
    reveal_mask = VideoClip(_reveal_alpha, is_mask=True).with_duration(duration)
    black_bg = ColorClip(size=(video_width, video_height), color=(0, 0, 0)).with_duration(duration)
    revealed = base_clip.with_mask(reveal_mask)

    # ── Pha 2: vignette dao động sin (thở) thay vì tối cố định ──
    falloff = np.clip((dist - 0.55) / 0.45, 0.0, 1.0)
    BREATH_PERIOD = 2.4    # giây/nhịp — đủ chậm để cảm nhận, không gây chóng mặt
    VIGNETTE_BASE = 0.45
    VIGNETTE_SWING = 0.15

    def _vignette_alpha(t: float) -> np.ndarray:
        breathe = VIGNETTE_BASE + VIGNETTE_SWING * _math.sin(2 * _math.pi * t / BREATH_PERIOD)
        return falloff * breathe

    vignette_mask = VideoClip(_vignette_alpha, is_mask=True).with_duration(duration)
    vignette = (
        ColorClip(size=(video_width, video_height), color=(0, 0, 0))
        .with_duration(duration)
        .with_mask(vignette_mask)
    )

    # Ghép xong 3 lớp ở kích thước cố định RỒI mới zoom TOÀN BỘ khối đã ghép — zoom lúc
    # này chỉ còn là 1 phép resize duy nhất trên 1 clip duy nhất, không còn mask nào cần
    # khớp shape theo sau nó nữa.
    inner = CompositeVideoClip([black_bg, revealed, vignette], size=(video_width, video_height)).with_duration(duration)

    def resize_func(t):
        return 1.0 + 0.05 * (t / duration)

    zoomed = inner.resized(resize_func).with_position("center").with_duration(duration)

    layers = [zoomed]
    # Chờ pha loang sáng xong hẳn mới hiện chữ — hiện giữa lúc ảnh còn tối 1 nửa thì khó đọc.
    caption = _hook_caption_overlay(
        quote_text, video_width, video_height, duration, delay=REVEAL_DUR + 0.1, y_frac=0.80
    )
    if caption is not None:
        layers.append(caption)

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

