# backend/services/hook_engine.py
import random
from typing import Optional
from moviepy import ImageClip, ColorClip, CompositeVideoClip, concatenate_videoclips

def build_carousel_hook(
    cover_image_path: str,
    quote_text: str,
    video_width: int,
    video_height: int,
    duration: float = 3.5
) -> CompositeVideoClip:
    """
    Tạo clip mở màn 3.5s với hiệu ứng Slot Machine + Quote Reveal.
    0.0s - 1.0s: Các khối màu/ảnh giả lướt nhanh như máy xèng.
    1.0s - 3.5s: Ảnh bìa thật hiện ra, thu nhỏ vào giữa khung hình, hiện Quote.
    """
    
    # 1. Tạo hiệu ứng Slot machine (1 giây đầu)
    slot_clips = []
    num_slots = 10
    slot_dur = 1.0 / num_slots
    
    colors = [(255,100,100), (100,255,100), (100,100,255), (255,200,100), (255,100,255)]
    for i in range(num_slots):
        c = random.choice(colors)
        cw, ch = int(video_width * 0.6), int(video_height * 0.4)
        bg = ColorClip((video_width, video_height), color=(20, 20, 30)).with_duration(slot_dur)
        book = ColorClip((cw, ch), color=c).with_position("center").with_duration(slot_dur)
        slot_clips.append(CompositeVideoClip([bg, book], size=(video_width, video_height)).with_duration(slot_dur))
        
    fast_carousel = concatenate_videoclips(slot_clips)
    
    # 2. Xử lý ảnh thật (Cover)
    try:
        real_cover = ImageClip(cover_image_path)
    except Exception:
        real_cover = ColorClip((int(video_width*0.6), int(video_height*0.4)), color=(255,255,255))
        
    scale_fit = min(video_width * 0.8 / real_cover.w, video_height * 0.5 / real_cover.h)
    
    def cover_resize(t):
        p = min(t / 0.5, 1.0)
        ease = 1 - (1-p)**3
        return scale_fit * (1.5 - 0.5 * ease)
        
    cover_clip = real_cover.resized(cover_resize).with_position("center").with_duration(2.5)
    
    dark_bg = ColorClip((video_width, video_height), color=(15, 15, 25)).with_duration(2.5)
    
    # 3. Xử lý Quote Text
    if not quote_text or quote_text.strip() == "":
        quote_text = "GIÁ TRỊ NẰM Ở SỰ LỰA CHỌN"
        
    from moviepy.video.VideoClip import TextClip
    txt_clip = (
        TextClip(
            text=quote_text,
            font="C:/Windows/Fonts/arialbd.ttf",
            font_size=65,
            color="white",
            stroke_color="black",
            stroke_width=4,
            method="caption",
            size=(int(video_width * 0.9), None)
        )
        .with_position(("center", int(video_height * 0.75)))
        .with_duration(2.5)
    )
    
    from moviepy.video.fx.CrossFadeIn import CrossFadeIn
    txt_clip = txt_clip.with_effects([CrossFadeIn(0.5)])
    
    part2 = CompositeVideoClip([dark_bg, cover_clip, txt_clip], size=(video_width, video_height)).with_duration(2.5)
    
    final_hook = concatenate_videoclips([fast_carousel, part2])
    return final_hook
