# backend/services/hook_engine.py
import numpy as np
from moviepy import ImageClip, ColorClip, CompositeVideoClip, concatenate_videoclips


def _blurred_fill_bg(cover_path: str, w: int, h: int, duration: float, darken: float = 0.5):
    """
    Nền LẤP ĐẦY khung 9:16 = bản phóng to + làm mờ của chính bìa (bỏ viền đen).
    Kỹ thuật chuẩn của mọi kênh review sách để ảnh dọc không để lại dải đen.
    """
    try:
        from PIL import Image, ImageFilter
        img = Image.open(cover_path).convert("RGB")
        scale = max(w / img.width, h / img.height)
        nw, nh = int(img.width * scale) + 2, int(img.height * scale) + 2
        img = img.resize((nw, nh)).filter(ImageFilter.GaussianBlur(35))
        left, top = (nw - w) // 2, (nh - h) // 2
        img = img.crop((left, top, left + w, top + h))
        arr = (np.array(img).astype(np.float32) * darken).astype(np.uint8)
        return ImageClip(arr).with_duration(duration)
    except Exception:
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
        cover = ImageClip(cover_image_path)
        fit = min(w * 0.72 / cover.w, h * 0.46 / cover.h)
    except Exception:
        cover = ColorClip((int(w * 0.6), int(h * 0.4)), color=(230, 230, 230))
        fit = 1.0
    cover_fit = cover.resized(fit)
    cw, ch = cover_fit.w, cover_fit.h
    cx = int((w - cw) / 2)
    cy = int(h / 2 - ch / 2)

    # ── Phase 1: Slot Machine — 2 bản bìa cuộn dọc, giảm tốc, dừng đúng giữa ──
    bg1 = _blurred_fill_bg(cover_image_path, w, h, slot_dur, darken=0.35)
    gap = ch + int(h * 0.04)

    def _scroll(t):
        p = min(t / slot_dur, 1.0)
        ease = 1 - (1 - p) ** 2          # ease-out: cuộn nhanh rồi chậm dần
        return (ease * gap * 4.0) % gap  # cuộn qua 4 "bìa", dừng ở 0 (đúng giữa) tại t=1

    reel1 = cover_fit.with_position(lambda t: (cx, int(cy - _scroll(t)))).with_duration(slot_dur)
    reel2 = cover_fit.with_position(lambda t: (cx, int(cy - _scroll(t) + gap))).with_duration(slot_dur)
    slot = CompositeVideoClip([bg1, reel1, reel2], size=(w, h)).with_duration(slot_dur)

    # ── Phase 2: Reveal — bìa dừng giữa (thu nhẹ) + Quote, nền blurred-fill ──
    bg2 = _blurred_fill_bg(cover_image_path, w, h, reveal_dur, darken=0.4)

    def _settle(t):
        p = min(t / 0.4, 1.0)
        ease = 1 - (1 - p) ** 3
        return fit * (1.12 - 0.12 * ease)   # từ hơi to → về đúng size (hiệu ứng "chốt")

    cover_reveal = cover.resized(_settle).with_position("center").with_duration(reveal_dur)

    if not quote_text or not quote_text.strip():
        quote_text = "GIÁ TRỊ NẰM Ở SỰ LỰA CHỌN"

    from moviepy.video.VideoClip import TextClip
    from moviepy.video.fx.CrossFadeIn import CrossFadeIn
    txt_clip = (
        TextClip(
            text=quote_text,
            font="C:/Windows/Fonts/arialbd.ttf",
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

    part2 = CompositeVideoClip([bg2, cover_reveal, txt_clip], size=(w, h)).with_duration(reveal_dur)

    return concatenate_videoclips([slot, part2])
