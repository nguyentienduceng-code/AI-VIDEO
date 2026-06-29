"""
video_service.py
-----------------
NÂNG CẤP V2:
1. Đa tỉ lệ khung hình: 9:16 (TikTok/Reels), 16:9 (YouTube), 1:1 (Instagram).
2. BGM mixing: overlay nhạc nền dưới giọng đọc (volume ~15%).
3. Slideshow mode: ảnh + BGM, không TTS, Ken Burns mạnh, crossfade dài.
4. Quiz mode: text overlay lớn hơn, màu nhấn khác.
5. Giữ nguyên tất cả fix nợ kỹ thuật V1 (MoviePy v2, crossfade, subtitle burn-in).
"""

from __future__ import annotations

import os
from typing import List, Optional, TypedDict

import srt
import datetime as dt

from moviepy import (
    AudioFileClip,
    ImageClip,
    CompositeVideoClip,
    CompositeAudioClip,
    TextClip,
    concatenate_videoclips,
)
from moviepy.video.fx import CrossFadeIn, CrossFadeOut

# ── Kích thước khung hình theo aspect ratio ──────────────────────────
ASPECT_RATIO_SIZES = {
    "9:16": (1080, 1920),   # TikTok/Reels (dọc)
    "16:9": (1920, 1080),   # YouTube (ngang)
    "1:1":  (1080, 1080),   # Instagram (vuông)
}

FPS = 30
CROSSFADE_DURATION = 0.6       # giây — crossfade giữa 2 cảnh (narration modes)
SLIDESHOW_CROSSFADE = 1.2      # giây — crossfade dài hơn cho slideshow
SLIDESHOW_SCENE_DURATION = 5.0 # giây — mỗi ảnh hiển thị bao lâu trong slideshow

# QUAN TRỌNG: font hỗ trợ dấu tiếng Việt (Unicode Latin Extended).
# Windows: arial.ttf hoặc segoeuil.ttf. Linux: DejaVuSans.ttf
SUBTITLE_FONT_PATH = "C:/Windows/Fonts/arial.ttf"

# ── Thư mục BGM ─────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BGM_DIR = os.path.join(BASE_DIR, "assets", "bgm")


class SceneAsset(TypedDict):
    image_path: str
    audio_path: str        # có thể rỗng "" cho slideshow mode
    text: str              # có thể rỗng "" cho slideshow mode
    duration: float        # độ dài audio (giây), hoặc SLIDESHOW_SCENE_DURATION


# ─────────────────────────────────────────────────────────────────────
# Build 1 scene clip
# ─────────────────────────────────────────────────────────────────────
def _build_scene_clip(
    asset: SceneAsset,
    add_crossfade_in: bool,
    video_width: int,
    video_height: int,
    crossfade_dur: float = CROSSFADE_DURATION,
    show_subtitle: bool = True,
    subtitle_font_size: int = 52,
    subtitle_color: str = "white",
) -> CompositeVideoClip:
    """Ghép 1 ảnh + 1 audio + phụ đề burn-in thành 1 clip hoàn chỉnh."""
    duration = asset["duration"]

    # ── Image clip ──
    image_clip = (
        ImageClip(asset["image_path"])
        .with_duration(duration)
        .resized(height=video_height)
    )
    # Cắt để tỷ lệ luôn đúng trước khi zoom
    if image_clip.w < video_width:
        image_clip = image_clip.resized(width=video_width)

    # Hiệu ứng Ken Burns (Zoom in nhẹ 10% trong suốt thời gian)
    def get_zoom_factor(t):
        return 1.0 + 0.1 * (t / duration)

    image_clip = image_clip.resized(get_zoom_factor).with_position("center")

    layers = [image_clip]

    # ── Audio clip (nếu có) ──
    audio_clip = None
    if asset.get("audio_path") and os.path.isfile(asset["audio_path"]):
        audio_clip = AudioFileClip(asset["audio_path"])

    # ── Subtitle clip (nếu có text và được bật) ──
    if show_subtitle and asset.get("text") and asset["text"].strip():
        subtitle_clip = (
            TextClip(
                text=asset["text"],
                font=SUBTITLE_FONT_PATH,
                font_size=subtitle_font_size,
                color=subtitle_color,
                stroke_color="black",
                stroke_width=2,
                method="caption",
                size=(int(video_width * 0.92), None),
                text_align="center",
            )
            .with_duration(duration)
            .with_position(("center", video_height * 0.78))
        )
        layers.append(subtitle_clip)

    scene = CompositeVideoClip(layers, size=(video_width, video_height))

    if audio_clip:
        scene = scene.with_audio(audio_clip)

    if add_crossfade_in:
        scene = scene.with_effects([CrossFadeIn(crossfade_dur)])
    scene = scene.with_effects([CrossFadeOut(crossfade_dur)])

    return scene


# ─────────────────────────────────────────────────────────────────────
# BGM helper
# ─────────────────────────────────────────────────────────────────────
def _mix_bgm(final_clip, bgm_path: str, bgm_volume: float = 0.15):
    """
    Mix nhạc nền dưới audio chính của video.
    BGM được loop nếu ngắn hơn video, và fade out 2s cuối.
    """
    if not bgm_path or not os.path.isfile(bgm_path):
        return final_clip

    bgm = AudioFileClip(bgm_path)
    video_duration = final_clip.duration

    # Loop BGM nếu ngắn hơn video
    if bgm.duration < video_duration:
        loops_needed = int(video_duration / bgm.duration) + 1
        from moviepy import concatenate_audioclips
        bgm = concatenate_audioclips([bgm] * loops_needed)

    bgm = bgm.subclipped(0, video_duration)
    bgm = bgm.with_volume_scaled(bgm_volume)

    # Mix: nếu video đã có audio (narration), composite cả 2
    if final_clip.audio is not None:
        mixed = CompositeAudioClip([final_clip.audio, bgm])
        return final_clip.with_audio(mixed)
    else:
        return final_clip.with_audio(bgm)


# ─────────────────────────────────────────────────────────────────────
# Main render function
# ─────────────────────────────────────────────────────────────────────
def render_final_video(
    scene_assets: List[SceneAsset],
    output_path: str,
    aspect_ratio: str = "9:16",
    bgm_path: Optional[str] = None,
    mode: str = "storyteller",
    bgm_volume: float = 0.15,
) -> str:
    """
    Ghép toàn bộ các scene thành 1 video .mp4 hoàn chỉnh.
    Hỗ trợ đa aspect ratio, BGM mixing, và mode-specific rendering.
    Trả về output_path.
    """
    video_width, video_height = ASPECT_RATIO_SIZES.get(aspect_ratio, (1080, 1920))

    # ── Mode-specific settings ──
    is_slideshow = (mode == "photo_slideshow")
    crossfade_dur = SLIDESHOW_CROSSFADE if is_slideshow else CROSSFADE_DURATION
    show_subtitle = not is_slideshow  # Slideshow không có subtitle
    subtitle_font_size = 58 if mode == "quiz_listicle" else 52
    subtitle_color = "#FFD700" if mode == "quiz_listicle" else "white"

    # Slideshow mode: BGM volume cao hơn vì không có narration
    if is_slideshow:
        bgm_volume = 0.8

    clips = [
        _build_scene_clip(
            asset,
            add_crossfade_in=(i > 0),
            video_width=video_width,
            video_height=video_height,
            crossfade_dur=crossfade_dur,
            show_subtitle=show_subtitle,
            subtitle_font_size=subtitle_font_size,
            subtitle_color=subtitle_color,
        )
        for i, asset in enumerate(scene_assets)
    ]

    # padding âm = các clip overlap nhau đúng bằng thời gian crossfade,
    # tạo hiệu ứng tan-vào-nhau thay vì cắt cứng giữa 2 cảnh
    final = concatenate_videoclips(clips, method="compose", padding=-crossfade_dur)

    # ── Mix BGM (nếu có) ──
    if bgm_path:
        final = _mix_bgm(final, bgm_path, bgm_volume)

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


# ─────────────────────────────────────────────────────────────────────
# SRT generation
# ─────────────────────────────────────────────────────────────────────
def generate_srt_file(scene_assets: List[SceneAsset], output_path: str) -> str:
    """
    Sinh file phụ đề .srt độc lập từ danh sách scene.
    Bỏ qua scenes không có text (slideshow mode).
    """
    subtitles = []
    cursor = 0.0
    idx = 1
    for asset in scene_assets:
        start = dt.timedelta(seconds=cursor)
        end = dt.timedelta(seconds=cursor + asset["duration"])
        if asset.get("text") and asset["text"].strip():
            subtitles.append(
                srt.Subtitle(index=idx, start=start, end=end, content=asset["text"])
            )
            idx += 1
        cursor += asset["duration"]

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(srt.compose(subtitles))

    return output_path


# ─────────────────────────────────────────────────────────────────────
# BGM listing helper
# ─────────────────────────────────────────────────────────────────────
def get_available_bgm() -> List[dict]:
    """Trả về danh sách nhạc nền có sẵn trong assets/bgm/."""
    if not os.path.isdir(BGM_DIR):
        return []

    bgm_list = []
    LABELS = {
        "chill_lofi": "Chill Lo-Fi",
        "epic_cinematic": "Epic Cinematic",
        "upbeat_pop": "Upbeat Pop",
        "soft_piano": "Soft Piano",
        "corporate_minimal": "Corporate Minimal",
    }

    for fname in sorted(os.listdir(BGM_DIR)):
        if fname.lower().endswith((".mp3", ".wav", ".ogg")):
            name_key = os.path.splitext(fname)[0]
            bgm_list.append({
                "id": fname,
                "name": LABELS.get(name_key, name_key.replace("_", " ").title()),
                "path": os.path.join(BGM_DIR, fname),
            })

    return bgm_list
