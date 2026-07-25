# backend/services/hook_engine.py
import numpy as np
from moviepy import ImageClip, ColorClip, CompositeVideoClip, concatenate_videoclips


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
        print(f"Blurred BG error: {e}")
        return ColorClip((w, h), color=(15, 15, 25)).with_duration(duration)


def build_carousel_hook(
    cover_image_path: str,
    quote_text: str,
    video_width: int,
    video_height: int,
    duration: float = 3.5,
) -> CompositeVideoClip:
    """
    Clip mở màn với Slot Machine (trục quay) + Quote Reveal.
    0.0s - 1.0s: BÌA SÁCH THẬT cuộn dọc như trục máy xèng (reel scroll), nền blurred-fill.
    1.0s - 3.5s: Bìa dừng, thu nhẹ vào giữa, hiện Quote trên nền mờ (không viền đen).
    """
    w, h = video_width, video_height
    slot_dur = 1.0
    reveal_dur = duration - slot_dur

    # ── Bìa thật (fit vào ~70% ngang, ~45% cao) ──
    try:
        if cover_image_path.endswith(".mp4"):
            from moviepy.video.io.VideoFileClip import VideoFileClip
            with VideoFileClip(cover_image_path) as v:
                cover = ImageClip(v.get_frame(0))
        else:
            cover = ImageClip(cover_image_path)
        fit = min(w * 0.72 / cover.w, h * 0.46 / cover.h)
    except Exception as e:
        print(f"Hook cover error: {e}")
        cover = ColorClip((int(w * 0.6), int(h * 0.4)), color=(230, 230, 230))
        fit = 1.0
    cover_fit = cover.resized(fit)
    cw, ch = cover_fit.w, cover_fit.h
    cx = int((w - cw) / 2)
    cy = int(h / 2 - ch / 2)

    # ── Phase 1: Slot Machine — Chuỗi ảnh thật cuộn dọc, dừng đúng giữa ──
    bg1 = _blurred_fill_bg(cover_image_path, w, h, slot_dur, darken=0.35)
    gap = ch + int(h * 0.04)

    import os
    import glob
    import random
    from PIL import Image
    import numpy as np
    
    slot_covers_dir = os.path.join(os.path.dirname(__file__), "..", "assets", "slot_covers")
    fake_paths = []
    if os.path.isdir(slot_covers_dir):
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG", "*.JPEG"):
            fake_paths.extend(glob.glob(os.path.join(slot_covers_dir, ext)))
            
    num_fakes = 4
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
                real_img = Image.fromarray(v.get_frame(0)).resize((cw, ch), Image.Resampling.LANCZOS)
        else:
            real_img = Image.open(cover_image_path).convert("RGBA").resize((cw, ch), Image.Resampling.LANCZOS)
    except:
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
            fk_img = Image.open(fp).convert("RGBA").resize((cw, ch), Image.Resampling.LANCZOS)
        except Exception:
            fk_img = real_img
        strip_img.paste(fk_img, (0, int((i + 1) * gap)))

    strip_clip = ImageClip(np.array(strip_img))

    def _scroll(t):
        p = min(t / slot_dur, 1.0)
        # Ease-out BẬC 3, không phải bậc 2: bậc 2 tiến tới đích quá chậm, khung hình cuối
        # cùng của pha quay (t=0.967 ở 30fps) vẫn còn lệch ~18px so với vị trí chốt →
        # sang pha 2 ảnh nhảy một cái. Bậc 3 chỉ còn lệch ~0.1px, mắt không thấy.
        ease = 1 - (1 - p) ** 3
        return ease * num_fakes * gap      # cuộn vừa vặn num_fakes khoảng gap

    rc = strip_clip.with_position(lambda t: (cx, int(cy - num_fakes * gap + _scroll(t)))).with_duration(slot_dur)

    slot = CompositeVideoClip([bg1, rc], size=(w, h)).with_duration(slot_dur)

    # ── Phase 2: Reveal — bìa dừng giữa (thu nhẹ) + Quote, nền blurred-fill ──
    # darken PHẢI trùng bg1: trước đây 0.35 vs 0.4 làm nền sáng vọt ~15% ngay tại
    # đường nối 2 pha — thấy như một cú chớp sáng.
    bg2 = _blurred_fill_bg(cover_image_path, w, h, reveal_dur, darken=0.35)

    import math

    def _settle(t):
        """
        Cú "chốt" sau khi trục quay dừng: nảy nhẹ 1.0 → 1.05 → 1.0 (hệ số TƯƠNG ĐỐI).

        LỖI CŨ: hàm này bắt đầu ở 1.12*fit rồi co về fit. Khi trục quay còn dừng SAI bìa
        thì không ai để ý, vì dù sao cũng đang cắt sang ảnh khác. Sau khi trục quay dừng
        ĐÚNG bìa thật, cùng một tấm ảnh bỗng to vọt 12% ngay tại đường nối → thành cú giật.
        """
        p = min(t / 0.35, 1.0)
        return 1.0 + 0.05 * math.sin(math.pi * p)   # nửa chu kỳ sin, đỉnh 5% ở giữa

    # Phóng từ CHÍNH cover_fit của pha 1 (không phóng lại từ ảnh gốc). Nhờ vậy tại t=0
    # kích thước đúng bằng (cw, ch) và toạ độ đúng bằng cy — trùng khít pha 1 từng pixel.
    # Nếu tính lại từ `cover` với hệ số fit, phép làm tròn của resize lệch 1-2px so với
    # pha 1, đủ để thấy ảnh "nhích" một cái tại đường nối.
    cover_reveal = (
        cover_fit.resized(_settle)
        .with_position(lambda t: ("center", int(h / 2 - (ch * _settle(t)) / 2)))
        .with_duration(reveal_dur)
    )

    # KHÔNG bịa quote mặc định nữa. Trước đây khi user để trống, hook luôn hiện câu
    # "GIÁ TRỊ NẰM Ở SỰ LỰA CHỌN" — một câu chung chung không liên quan tới cuốn sách,
    # LẠI nằm đúng vùng phụ đề của Cảnh 1 nên hai khối chữ đè lên nhau. Để trống thì
    # hook chỉ còn bìa sách sạch sẽ, đúng ý đồ hơn.
    layers2 = [bg2, cover_reveal]
    if quote_text and quote_text.strip():
        from moviepy.video.VideoClip import TextClip
        from moviepy.video.fx.CrossFadeIn import CrossFadeIn
        txt_clip = (
            TextClip(
                text=quote_text.strip(),
                font="C:/Windows/Fonts/seguibl.ttf",  # Arial Black thiếu glyph ư/ơ tiếng Việt
                font_size=60,
                color="white",
                stroke_color="black",
                stroke_width=4,
                method="caption",
                size=(int(w * 0.88), None),
                text_align="center",
            )
            .with_position(("center", int(h * 0.74)))
            .with_duration(reveal_dur)
            .with_effects([CrossFadeIn(0.4)])
        )
        layers2.append(txt_clip)

    part2 = CompositeVideoClip(layers2, size=(w, h)).with_duration(reveal_dur)

    return concatenate_videoclips([slot, part2])
