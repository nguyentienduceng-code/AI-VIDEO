"""
video_service.py
-----------------
NÂNG CẤP:
1. Cập nhật cú pháp sang MoviePy v2.x (breaking changes so với v1):
   - import từ `moviepy` thay vì `moviepy.editor`
   - `.set_start()` -> `.with_start()`, dùng `.with_effects([...])`
2. FIX NỢ KỸ THUẬT #5 (Đứt gãy Audio-Video): thêm CrossFadeIn/CrossFadeOut
   giữa các phân cảnh để chuyển cảnh mượt, không còn giật cục.
3. Thêm sinh phụ đề .srt (Roadmap mục 2), đốt thẳng (burn-in) phụ đề bằng
   TextClip lên video — không cần người xem tự tải file .srt riêng.
"""

from __future__ import annotations

import os
from typing import List, TypedDict

import srt
import datetime as dt

from moviepy import (
    AudioFileClip,
    ImageClip,
    CompositeVideoClip,
    TextClip,
    concatenate_videoclips,
)
from moviepy.video.fx import CrossFadeIn, CrossFadeOut

# Kích thước khung hình dọc chuẩn Tiktok/Reels
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30
CROSSFADE_DURATION = 0.6  # giây — thời gian chuyển cảnh mượt giữa 2 ảnh

# QUAN TRỌNG: chỉ định rõ font hỗ trợ đầy đủ dấu tiếng Việt (Latin Extended).
# Nếu để Pillow tự chọn font mặc định, có nguy cơ rơi vào bitmap font
# không có dấu tiếng Việt -> phụ đề hiển thị sai/ thiếu dấu.
# DejaVu Sans được cài sẵn trên hầu hết bản Linux/Ubuntu và hỗ trợ đủ
# Unicode tiếng Việt; trên Windows hãy đổi sang đường dẫn arial.ttf hoặc
# một font Unicode đầy đủ khác (ví dụ "C:/Windows/Fonts/arial.ttf").
SUBTITLE_FONT_PATH = "C:/Windows/Fonts/arial.ttf"


class SceneAsset(TypedDict):
    image_path: str
    audio_path: str
    text: str
    duration: float  # độ dài audio (giây), lấy từ tts_service.synthesize_speech


def _build_scene_clip(asset: SceneAsset, add_crossfade_in: bool) -> CompositeVideoClip:
    """Ghép 1 ảnh + 1 audio + phụ đề burn-in thành 1 clip hoàn chỉnh."""
    duration = asset["duration"]

    image_clip = (
        ImageClip(asset["image_path"])
        .with_duration(duration)
        .resized(height=VIDEO_HEIGHT)
    )
    # Cắt để tỷ lệ luôn là 9:16 trước khi zoom
    if image_clip.w < VIDEO_WIDTH:
        image_clip = image_clip.resized(width=VIDEO_WIDTH)
    
    # Hiệu ứng Ken Burns (Zoom in nhẹ 10% trong suốt thời gian)
    def get_zoom_factor(t):
        return 1.0 + 0.1 * (t / duration)
        
    image_clip = image_clip.resized(get_zoom_factor).with_position("center")

    audio_clip = AudioFileClip(asset["audio_path"])

    subtitle_clip = (
        TextClip(
            text=asset["text"],
            font=SUBTITLE_FONT_PATH,
            font_size=52,
            color="white",
            stroke_color="black",
            stroke_width=2,
            method="caption",
            size=(int(VIDEO_WIDTH * 0.92), None),
            text_align="center",
        )
        .with_duration(duration)
        .with_position(("center", VIDEO_HEIGHT * 0.78))
    )

    scene = CompositeVideoClip(
        [image_clip, subtitle_clip], size=(VIDEO_WIDTH, VIDEO_HEIGHT)
    ).with_audio(audio_clip)

    if add_crossfade_in:
        scene = scene.with_effects([CrossFadeIn(CROSSFADE_DURATION)])
    scene = scene.with_effects([CrossFadeOut(CROSSFADE_DURATION)])

    return scene


def render_final_video(scene_assets: List[SceneAsset], output_path: str) -> str:
    """
    Ghép toàn bộ các scene thành 1 video .mp4 hoàn chỉnh, có crossfade
    chuyển cảnh mượt giữa mỗi phân đoạn. Trả về output_path.
    """
    clips = [
        _build_scene_clip(asset, add_crossfade_in=(i > 0))
        for i, asset in enumerate(scene_assets)
    ]

    # padding âm = các clip overlap nhau đúng bằng thời gian crossfade,
    # tạo hiệu ứng tan-vào-nhau thay vì cắt cứng giữa 2 cảnh
    final = concatenate_videoclips(clips, method="compose", padding=-CROSSFADE_DURATION)

    final.write_videofile(
        output_path,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        threads=4,
        preset="medium",
    )

    # Giải phóng tài nguyên ngay sau khi render xong (giảm áp lực RAM)
    for c in clips:
        c.close()
    final.close()

    return output_path


def generate_srt_file(scene_assets: List[SceneAsset], output_path: str) -> str:
    """
    Sinh file phụ đề .srt độc lập từ danh sách scene (Roadmap mục 2).
    Hữu ích nếu người dùng muốn tải phụ đề riêng để chỉnh sửa / đăng kèm
    video gốc lên các nền tảng cho phép upload .srt riêng.
    """
    subtitles = []
    cursor = 0.0
    for i, asset in enumerate(scene_assets, start=1):
        start = dt.timedelta(seconds=cursor)
        end = dt.timedelta(seconds=cursor + asset["duration"])
        subtitles.append(
            srt.Subtitle(index=i, start=start, end=end, content=asset["text"])
        )
        cursor += asset["duration"]

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(srt.compose(subtitles))

    return output_path
