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
CROSSFADE_DURATION = 0.2       # giây — crossfade nhanh giữa 2 cảnh cho video ngắn (Tiktok style)
SLIDESHOW_CROSSFADE = 0.8      # giây — crossfade dài hơn cho slideshow
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
    sfx: str               # Tên hiệu ứng âm thanh (whoosh, pop...)
    visual_effect: str     # zoom_in, zoom_out, pan_left, pan_right


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
    visual_effect = asset.get("visual_effect", "zoom_in")

    # ── Image clip ──
    image_clip = (
        ImageClip(asset["image_path"])
        .with_duration(duration)
        .resized(height=video_height)
    )
    # Cắt để tỷ lệ luôn đúng trước khi zoom
    if image_clip.w < video_width:
        image_clip = image_clip.resized(width=video_width)

    # Hiệu ứng chuyển động (Dynamic VFX)
    def get_zoom_factor(t):
        if visual_effect == "zoom_out":
            return 1.1 - 0.1 * (t / duration)
        elif visual_effect == "none":
            return 1.0
        return 1.0 + 0.1 * (t / duration) # zoom_in default

    image_clip = image_clip.resized(get_zoom_factor)

    if visual_effect == "pan_left":
        # Make it wider so we can pan
        pan_width = int(video_width * 1.1)
        image_clip = image_clip.resized(width=pan_width)
        image_clip = image_clip.with_position(lambda t: ('center' if duration == 0 else int(-0.1 * video_width * (t / duration)), 'center'))
    elif visual_effect == "pan_right":
        pan_width = int(video_width * 1.1)
        image_clip = image_clip.resized(width=pan_width)
        image_clip = image_clip.with_position(lambda t: ('center' if duration == 0 else int(-0.1 * video_width * (1 - t / duration)), 'center'))
    else:
        image_clip = image_clip.with_position("center")

    layers = [image_clip]

    # ── Audio clip (nếu có) ──
    audio_clip = None
    audio_clips = []
    
    if asset.get("audio_path") and os.path.isfile(asset["audio_path"]):
        audio_clips.append(AudioFileClip(asset["audio_path"]))

    # ── SFX ──
    sfx_name = asset.get("sfx", "")
    if sfx_name:
        sfx_path = os.path.join(BASE_DIR, "assets", "sfx", f"{sfx_name}.mp3")
        if os.path.isfile(sfx_path):
            sfx_clip = AudioFileClip(sfx_path).with_volume_scaled(0.5)
            audio_clips.append(sfx_clip)

    if audio_clips:
        if len(audio_clips) > 1:
            audio_clip = CompositeAudioClip(audio_clips)
        else:
            audio_clip = audio_clips[0]

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
def _mix_bgm(final_clip, bgm_path: str, bgm_volume: float = 0.15, speech_segments: list = None):
    """
    Mix nhạc nền dưới audio chính của video.
    BGM được loop nếu ngắn hơn video, fade in/out, và auto-ducking (hạ âm lượng khi có giọng nói).
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

    # Auto-ducking: hạ volume xuống 30% mức bgm_volume trong các đoạn có speech
    if speech_segments:
        import numpy as np
        def make_duck_frame(get_frame):
            def duck_frame(t):
                frame = get_frame(t)
                vol = np.ones_like(t) if isinstance(t, np.ndarray) else 1.0
                if isinstance(t, np.ndarray):
                    for start, end in speech_segments:
                        mask = (t >= (start - 0.5)) & (t <= (end + 0.5))
                        vol = np.where(mask, 0.3, vol)
                    # Expand dims to match frame shape N x 2
                    vol = vol[:, np.newaxis] if frame.ndim == 2 else vol
                else:
                    for start, end in speech_segments:
                        if (start - 0.5) <= t <= (end + 0.5):
                            vol = 0.3
                            break
                return frame * vol
            return duck_frame
        bgm = bgm.with_updated_frame_function(make_duck_frame(bgm.get_frame))

    # Fade in / Fade out
    from moviepy.audio.fx.CrossFadeIn import CrossFadeIn
    from moviepy.audio.fx.CrossFadeOut import CrossFadeOut
    bgm = bgm.with_effects([CrossFadeIn(2.0), CrossFadeOut(2.0)])

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
    **kwargs
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

    clips = []
    speech_segments = []
    current_time = 0.0

    for i, asset in enumerate(scene_assets):
        dur = asset.get("duration", 3.0)
        has_audio = bool(asset.get("audio_path"))
        
        # Audio ducking tracking
        if has_audio:
            speech_segments.append((current_time, current_time + dur))
        
        c = _build_scene_clip(
            asset,
            add_crossfade_in=(i > 0),
            video_width=video_width,
            video_height=video_height,
            crossfade_dur=crossfade_dur,
            show_subtitle=show_subtitle,
            subtitle_font_size=subtitle_font_size,
            subtitle_color=subtitle_color,
        )
        clips.append(c)
        
        # Move timeline forward (considering overlap padding for the next clip)
        if i < len(scene_assets) - 1:
            current_time += (dur - crossfade_dur)
        else:
            current_time += dur

    # padding âm = các clip overlap nhau đúng bằng thời gian crossfade,
    # tạo hiệu ứng tan-vào-nhau thay vì cắt cứng giữa 2 cảnh
    final = concatenate_videoclips(clips, method="compose", padding=-crossfade_dur)

    # ── Mix BGM (nếu có) ──
    if bgm_path:
        final = _mix_bgm(final, bgm_path, bgm_volume, speech_segments=speech_segments)

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
def generate_ass_file(scene_assets: List[SceneAsset], output_path: str, mode: str = "storyteller") -> str:
    """
    Sinh file phụ đề .ass (Advanced SubStation Alpha) để có hiệu ứng chữ nảy (pop-in),
    viền đen dày và font Impact bắt mắt theo chuẩn video Tiktok/Reels.
    """
    # Header ASS
    ass_content = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
    ]
    
    # Định nghĩa Style
    font_name = "Impact"
    font_size = 65 if mode == "quiz_listicle" else 75
    primary_color = "&H0000FFFF" if mode == "quiz_listicle" else "&H00FFFFFF" # BGR format: Vàng / Trắng
    
    # Cấu trúc: 1=Border, 5=Outline width, 0=Shadow, 2=Bottom center alignment, 180=MarginV
    style_line = f"Style: Default,{font_name},{font_size},{primary_color},&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,6,0,2,40,40,250,1"
    ass_content.append(style_line)
    ass_content.append("")
    ass_content.append("[Events]")
    ass_content.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")

    cursor = 0.0
    for asset in scene_assets:
        duration = asset["duration"]
        if asset.get("text") and asset["text"].strip():
            # Format time HH:MM:SS.cs
            start_td = dt.timedelta(seconds=cursor)
            end_td = dt.timedelta(seconds=cursor + duration)
            
            def format_ass_time(td):
                total_seconds = int(td.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                centiseconds = int(td.microseconds / 10000)
                return f"{hours:01d}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"

            start_str = format_ass_time(start_td)
            end_str = format_ass_time(end_td)
            
            # Xử lý text (break dòng)
            import textwrap
            text = asset["text"].replace('\n', ' ')
            wrapped = "\\N".join(textwrap.wrap(text, width=28))
            
            # Hiệu ứng nảy (pop-in) bằng cách scale từ 30% lên 110% rồi về 100%
            # \fscx30\fscy30 : Bắt đầu ở 30%
            # \t(0,100,\fscx110\fscy110) : Trong 100ms đầu scale lên 110%
            # \t(100,200,\fscx100\fscy100) : 100ms tiếp theo về 100%
            pop_effect = r"{\fscx30\fscy30\t(0,150,\fscx110\fscy110)\t(150,250,\fscx100\fscy100)}"
            ass_text = f"{pop_effect}{wrapped}"
            
            event_line = f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{ass_text}"
            ass_content.append(event_line)
            
        cursor += duration

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(ass_content))

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
