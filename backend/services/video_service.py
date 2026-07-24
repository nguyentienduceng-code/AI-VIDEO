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
import re
from typing import List, Optional, TypedDict
import datetime as dt

from moviepy import (
    AudioFileClip,
    VideoFileClip,
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
CROSSFADE_DURATION = 0.4       # giây — crossfade mượt giữa 2 cảnh (tăng từ 0.2 lên 0.4 cho tự nhiên hơn)
SLIDESHOW_CROSSFADE = 0.8      # giây — crossfade dài hơn cho slideshow
AUDIO_FADEOUT_DURATION = 0.3   # giây — audio fade-out cuối mỗi cảnh để tránh ngắt đột ngột
SLIDESHOW_SCENE_DURATION = 5.0 # giây — mỗi ảnh hiển thị bao lâu trong slideshow

# QUAN TRỌNG: font hỗ trợ dấu tiếng Việt (Unicode Latin Extended).
# Windows: segoeuib.ttf. Linux: DejaVuSans.ttf
SUBTITLE_FONT_PATH = "C:/Windows/Fonts/ariblk.ttf"

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
    highlight_text: str    # B-Roll Text


# ─────────────────────────────────────────────────────────────────────
# Transition Engine — đa dạng hoá chuyển cảnh
# ─────────────────────────────────────────────────────────────────────
# Danh sách transition hợp lệ (đồng bộ với frontend constants.TRANSITIONS)
VALID_TRANSITIONS = {
    "crossfade", "fade_black", "fade_white", "zoom_through",
    "slide_left", "slide_right", "slide_up", "whip_pan",
    "page_flip", "droplet",
}


def _apply_transition(scene, transition, add_crossfade_in, crossfade_dur, video_width, video_height):
    """
    Áp hiệu ứng chuyển cảnh cho ENTRANCE của 1 scene (blend/slide/reveal chồng lên cảnh
    trước trong vùng overlap). Luôn CrossFadeOut ở cuối để cảnh sau có nền blend.

    Mọi hiệu ứng "fancy" (slide/page_flip/droplet) được bọc try/except → nếu MoviePy lỗi
    thì tự động fallback crossfade, KHÔNG bao giờ làm hỏng render.
    """
    from moviepy.video.fx import CrossFadeIn, CrossFadeOut, FadeIn, FadeOut
    cf = crossfade_dur

    # Cảnh đầu tiên: không có entrance transition, chỉ fade out cuối để nối cảnh sau
    if not add_crossfade_in:
        return scene.with_effects([CrossFadeOut(cf)])

    try:
        if transition == "fade_black":
            return scene.with_effects([FadeIn(cf), FadeOut(cf)])

        if transition == "fade_white":
            from moviepy import ColorClip
            flash = (
                ColorClip((video_width, video_height), color=(255, 255, 255))
                .with_duration(cf)
                .with_effects([CrossFadeOut(cf)])
            )
            scene = scene.with_effects([CrossFadeIn(cf * 0.5), CrossFadeOut(cf)])
            return CompositeVideoClip([scene, flash], size=(video_width, video_height)).with_duration(scene.duration)

        if transition == "zoom_through":
            return scene.with_effects([CrossFadeIn(cf * 0.8), CrossFadeOut(cf * 0.8)])

        if transition in ("slide_left", "slide_right", "slide_up", "whip_pan", "page_flip"):
            slide_dur = cf * (0.5 if transition == "whip_pan" else 1.0)

            def _pos(t, tr=transition, d=slide_dur):
                p = min(t / d, 1.0) if d > 0 else 1.0
                ease = 1 - (1 - p) ** 3  # ease-out cubic cho cảm giác "đẩy" mượt
                if tr in ("slide_left", "whip_pan", "page_flip"):
                    return (int(video_width * (1 - ease)), 0)     # vào từ phải
                if tr == "slide_right":
                    return (int(-video_width * (1 - ease)), 0)    # vào từ trái
                if tr == "slide_up":
                    return (0, int(video_height * (1 - ease)))    # vào từ dưới
                return (0, 0)

            scene = scene.with_position(_pos)

            if transition == "page_flip":
                # Ép ngang nhẹ lúc "lật" rồi bung ra → cảm giác lật trang sách
                def _scale(t, d=slide_dur):
                    p = min(t / d, 1.0) if d > 0 else 1.0
                    return 0.82 + 0.18 * p

                scene = scene.resized(_scale)

            scene = scene.with_effects([CrossFadeOut(cf)])
            return CompositeVideoClip([scene], size=(video_width, video_height)).with_duration(scene.duration)

        if transition == "droplet":
            # Giọt nước: mặt nạ hình tròn lan rộng từ tâm ra (ripple reveal)
            import numpy as np
            from moviepy import VideoClip
            w, h = video_width, video_height
            max_r = ((w ** 2 + h ** 2) ** 0.5) / 2.0
            yy, xx = np.ogrid[:h, :w]
            dist = np.sqrt((xx - w / 2.0) ** 2 + (yy - h / 2.0) ** 2)

            def _mask_frame(t, d=cf):
                p = min(t / d, 1.0) if d > 0 else 1.0
                ease = 1 - (1 - p) ** 2
                return (dist <= ease * max_r).astype(float)

            mask = VideoClip(_mask_frame, is_mask=True).with_duration(scene.duration)
            return scene.with_mask(mask).with_effects([CrossFadeOut(cf)])
    except Exception as e:
        print(f"[Transition] '{transition}' lỗi ({e}), fallback crossfade.")

    # Mặc định: crossfade
    return scene.with_effects([CrossFadeIn(cf), CrossFadeOut(cf)])


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
    transition: str = "crossfade",
) -> CompositeVideoClip:
    """Ghép 1 ảnh + 1 audio + phụ đề burn-in thành 1 clip hoàn chỉnh."""
    duration = asset["duration"]
    visual_effect = asset.get("visual_effect", "zoom_in")

    # ── Media clip (Video/Image) ──
    is_video = asset["image_path"].lower().endswith((".mp4", ".mov"))
    if is_video:
        media_clip = VideoFileClip(asset["image_path"])
        # Loop video nếu ngắn hơn duration
        if media_clip.duration < duration:
            import math
            from moviepy import concatenate_videoclips
            loops = math.ceil(duration / media_clip.duration)
            media_clip = concatenate_videoclips([media_clip] * loops)
        media_clip = media_clip.subclipped(0, duration)
        media_clip = media_clip.resized(height=video_height)
    else:
        media_clip = (
            ImageClip(asset["image_path"])
            .with_duration(duration)
            .resized(height=video_height)
        )
        
    # Cắt để tỷ lệ luôn đúng trước khi zoom
    if media_clip.w < video_width:
        media_clip = media_clip.resized(width=video_width)

    # Hiệu ứng chuyển động (Ken Burns) đã được xử lý bằng FFmpeg trong motion_effects.py trước đó
    # Nên media_clip ở đây (dù là ảnh tĩnh hay video .mp4) chỉ cần giữ đúng tỷ lệ và center
    media_clip = media_clip.with_position("center")

    layers = [media_clip]
    
    # ── B-Roll Text (Highlight Text) ──
    highlight_text = asset.get("highlight_text", "")
    if highlight_text:
        from moviepy.video.VideoClip import TextClip
        from moviepy.video.fx.CrossFadeIn import CrossFadeIn
        from moviepy.video.fx.CrossFadeOut import CrossFadeOut
        
        # Chỉ hiện chớp nhoáng 1.2s để làm điểm nhấn, không che mặt nhân vật quá lâu
        hl_dur = min(1.2, duration)
        
        txt_clip = (
            TextClip(
                text=highlight_text,
                font="C:/Windows/Fonts/arialbd.ttf",
                font_size=120,
                color="yellow",
                stroke_color="black",
                stroke_width=4,
                method="label"
            )
            .with_position(("center", 0.25), relative=True)  # Đẩy lên 25% phía trên
            .with_duration(hl_dur)
            .with_effects([CrossFadeIn(0.2), CrossFadeOut(0.2)])
        )
        layers.append(txt_clip)

    # ── Audio KHÔNG được gắn vào clip video ──
    # LÝ DO: Khi concatenate_videoclips dùng padding âm (crossfade), 
    # MoviePy sẽ mix audio của 2 clip chồng lấp → giọng đọc bị trùng.
    # Audio sẽ được xây dựng thành track riêng biệt trong render_final_video().

    scene = CompositeVideoClip(layers, size=(video_width, video_height))

    # ── Transition Engine (đa dạng: crossfade/slide/page_flip/droplet/...) ──
    scene = _apply_transition(
        scene, transition, add_crossfade_in, crossfade_dur, video_width, video_height
    )

    return scene


# BGM Mix and Mastering are now delegated to FFmpeg in audio_mix_service.py


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
    master_audio_path: Optional[str] = None,
    use_sfx: bool = True,
    sfx_volume: float = 0.5,
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
    audio_tracks = []
    speech_segments = []
    final_duration = 0.0

    for i, asset in enumerate(scene_assets):
        dur = asset.get("duration", 3.0)
        start_time = asset.get("start_time", 0.0)
        has_audio = bool(asset.get("audio_path"))
        
        # Audio ducking tracking
        if has_audio:
            speech_segments.append((start_time, start_time + dur))
            
        # ── Build Audio Track (Đảm bảo các file âm thanh KHÔNG chồng lên nhau) ──
        scene_audio_clips = []
        if has_audio and os.path.isfile(asset["audio_path"]):
            from moviepy.audio.io.AudioFileClip import AudioFileClip
            scene_audio_clips.append(AudioFileClip(asset["audio_path"]))
            
        sfx_name = asset.get("sfx", "")
        if use_sfx and sfx_name:
            sfx_path = os.path.join(BASE_DIR, "assets", "sfx", f"{sfx_name}.wav")
            if os.path.isfile(sfx_path):
                from moviepy.audio.io.AudioFileClip import AudioFileClip
                scene_audio_clips.append(AudioFileClip(sfx_path).with_volume_scaled(sfx_volume))
                
        if scene_audio_clips:
            from moviepy.audio.AudioClip import CompositeAudioClip
            from moviepy.audio.fx.AudioFadeOut import AudioFadeOut
            
            if len(scene_audio_clips) > 1:
                ac = CompositeAudioClip(scene_audio_clips)
            else:
                ac = scene_audio_clips[0]
                
            # Không cắt cụt audio (đặc biệt là giọng đọc TTS) để tránh mất chữ cuối
            # Dù Hình ảnh bị rút ngắn do Beat Sync, Audio vẫn phát đủ câu nói.
            ac = ac.with_effects([AudioFadeOut(AUDIO_FADEOUT_DURATION)])
            
            # Đặt đúng vị trí trên timeline tổng
            ac = ac.with_start(start_time)
            audio_tracks.append(ac)

        
        c = _build_scene_clip(
            asset,
            add_crossfade_in=(i > 0),
            video_width=video_width,
            video_height=video_height,
            crossfade_dur=crossfade_dur,
            show_subtitle=show_subtitle,
            subtitle_font_size=subtitle_font_size,
            subtitle_color=subtitle_color,
            transition=asset.get("transition", "crossfade"),
        )
        
        c = c.with_start(start_time)
        clips.append(c)
        final_duration = max(final_duration, start_time + dur)
        
    final = CompositeVideoClip(clips, size=(video_width, video_height)).with_duration(final_duration)

    # Gắn track âm thanh tuần tự vào video
    if audio_tracks:
        from moviepy.audio.AudioClip import CompositeAudioClip
        final_audio = CompositeAudioClip(audio_tracks)
        final = final.with_audio(final_audio)

    # Nếu dùng Continuous TTS (có master_audio_path)
    if master_audio_path and os.path.exists(master_audio_path):
        from moviepy.audio.io.AudioFileClip import AudioFileClip
        master_audio = AudioFileClip(master_audio_path)
        
        # Audio gốc dài hơn video do padding, ta cắt lại cho khớp với video final
        master_audio = master_audio.subclipped(0, min(final.duration, master_audio.duration))
        final = final.with_audio(master_audio)
        
        # Vì giọng nói liền mạch, ducking BGM toàn bộ video
        speech_segments = [(0.0, final.duration)]

    # BGM mixing now happens via FFmpeg in audio_mix_service.py

    # ── Thêm Hiệu ứng Hình ảnh (Vignette & Progress Bar) ──
    import numpy as np
    from moviepy.video.VideoClip import ImageClip, VideoClip
    
    overlays = [final]
    
    # 1. Vignette (Làm tối 4 góc)
    x = np.linspace(-1, 1, video_width)
    y = np.linspace(-1, 1, video_height)
    X, Y = np.meshgrid(x, y)
    radius = np.sqrt(X**2 + Y**2)
    opacity = np.clip(radius - 0.6, 0, 1) * 0.7
    vig_img = np.zeros((video_height, video_width, 4), dtype=np.uint8)
    vig_img[:, :, 3] = (opacity * 255).astype(np.uint8)
    vig_clip = ImageClip(vig_img, is_mask=False).with_duration(final.duration)
    overlays.append(vig_clip)
    
    # 2. Progress Bar (Dưới cùng)
    bar_height = 12
    def make_progress_frame(t):
        w = int(video_width * (t / final.duration))
        if w == 0: w = 1
        frame = np.zeros((bar_height, video_width, 4), dtype=np.uint8)
        frame[:, :w, 0] = 255
        frame[:, :w, 1] = 215
        frame[:, :w, 2] = 0
        frame[:, :w, 3] = 255
        return frame
        
    progress_clip = VideoClip(make_progress_frame, is_mask=False, has_constant_size=True).with_duration(final.duration).with_position(("left", "bottom"))
    overlays.append(progress_clip)
    
    final = CompositeVideoClip(overlays, size=(video_width, video_height)).with_audio(final.audio)


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
def _strip_emoji_for_subtitle(text: str) -> str:
    """Xóa triệt để emoji/icons khỏi text phụ đề để tránh hiện ký tự lạ trong video."""
    # Dải chính: Supplementary Multilingual Plane (hầu hết emoji hiện đại)
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    # Dải phụ: Miscellaneous Symbols, Dingbats, Misc Technical, Arrows, etc.
    text = re.sub(r'[\u2600-\u27ff\u2300-\u23ff\u2B50-\u2B55\u2B06\u2934\u2935\u200d\ufe0f\u00a9\u00ae\u203c\u2049\u2122\u2139\u2194-\u21aa\u231a-\u231b\u25aa-\u25fe\u2702-\u27b0\u3030\u303d\u3297\u3299]', '', text)
    return text.strip()


def generate_ass_file(scene_assets: List[SceneAsset], output_path: str, mode: str = "storyteller", subtitle_style: str = "karaoke_bold", hook_text: str = None, hook_effect: str = "word_by_word") -> str:
    """
    Sinh file phụ đề .ass (Advanced SubStation Alpha).
    Hỗ trợ 2 phong cách:
    - karaoke_bold: Viền dày, hiệu ứng nảy (pop-in), màu vàng nổi bật, tự động in hoa.
    - cinematic_box: Chữ trắng trên nền hộp mờ (box/backdrop) kéo ngang, tĩnh, chữ thường.
    """
    ass_content = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
    ]
    
    # ── ĐỊNH NGHĨA STYLE DỰA TRÊN USER SETTING ──
    if subtitle_style == "cinematic_box":
        font_name = "Arial Black"  # Font hiện đại, sạch sẽ
        font_size = 55
        primary_color = "&H00FFFFFF"     # White
        secondary_color = "&H00FFFFFF"
        outline_color = "&H00000000"     # No outline needed
        back_color = "&H99000000"        # Semi-transparent black (99 is alpha)
        # BorderStyle=3 (Opaque box), Outline=8 (Box padding/margin)
        style_line = f"Style: Default,{font_name},{font_size},{primary_color},{secondary_color},{outline_color},{back_color},-1,0,0,0,100,100,0,0,3,8,0,2,60,60,250,1"
    elif subtitle_style == "minimal_white":
        font_name = "Arial Black"
        font_size = 50
        primary_color = "&H00FFFFFF"     # White
        secondary_color = "&H00FFFFFF"
        outline_color = "&H00000000"
        back_color = "&H66000000"        # Soft shadow (alpha 66)
        # BorderStyle=1 (Outline), Outline=0, Shadow=3
        style_line = f"Style: Default,{font_name},{font_size},{primary_color},{secondary_color},{outline_color},{back_color},0,0,0,0,100,100,0,0,1,0,3,2,40,40,250,1"
    else: # karaoke_bold & hormozi_bold (Default)
        # Sử dụng Arial Black cho cảm giác Cinematic và hiện đại (hỗ trợ 100% tiếng Việt).
        font_name = "Arial Black"
        font_size = 65 if mode == "quiz_listicle" else 75
        primary_color = "&H0000FFFF"     # Yellow highlight
        secondary_color = "&H00FFFFFF"   # White base
        outline_color = "&H00000000"     # Black outline
        back_color = "&H00000000"        # Black shadow
        # BorderStyle=1 (Outline), Outline=6, Shadow=4
        style_line = f"Style: Default,{font_name},{font_size},{primary_color},{secondary_color},{outline_color},{back_color},-1,0,0,0,100,100,0,0,1,6,5,2,40,40,500,1"
        
    ass_content.append(style_line)
    
    # ── HOOK STYLE (cho Tiêu đề 3s đầu) ──
    # Chữ to, vàng, nằm ở top (MarginV=150)
    hook_style_line = f"Style: HookTitle,Arial Black,75,&H0000FFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,8,5,8,40,40,150,1"
    ass_content.append(hook_style_line)
    
    ass_content.append("")
    ass_content.append("[Events]")
    ass_content.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")

    def format_ass_time(td):
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        centiseconds = int(td.microseconds / 10000)
        return f"{hours:01d}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"

    # Add hook_text (duration 3 seconds max)
    if hook_text and hook_text.strip():
        import textwrap
        wrapped_hook = "\\N".join(textwrap.wrap(hook_text.strip().upper(), width=16))
        
        if hook_effect == "full_shake":
            # Effect: fade in 200ms, fade out 500ms, start large and scale down (bounce)
            hook_ass = f"{{\\fad(200,500)\\fscx130\\fscy130\\t(0,200,\\fscx100\\fscy100)}}{wrapped_hook}"
            ass_content.append(f"Dialogue: 1,0:00:00.00,0:00:03.00,HookTitle,,0,0,0,,{hook_ass}")
        else: # word_by_word
            # Generate cumulative lines for word-by-word pop-in
            words = hook_text.strip().upper().split()
            cursor_s = 0.0
            word_dur = 0.25 # pop a new word every 0.25s
            
            # Since ASS requires manual positioning if we pop word by word, the easiest way 
            # to do word-by-word popping without changing position is to use \alpha
            # But standard ASS supports {\alpha&HFF&} for transparent text.
            # We can write the FULL string, but set the upcoming words to transparent!
            
            for i in range(len(words)):
                start_s = i * word_dur
                if start_s >= 2.5: break # don't start appearing too late
                end_s = 3.0
                
                start_td = dt.timedelta(seconds=start_s)
                end_td = dt.timedelta(seconds=end_s)
                
                # Cắt chuỗi làm 2 phần: phần đã hiện (từ 0 đến i), phần chưa hiện (từ i+1 trở đi)
                # Phần đã hiện thì giữ nguyên. Từ đang hiện thì nảy to. Phần chưa hiện thì ẩn (alpha FF).
                
                text_parts = []
                for j, w in enumerate(words):
                    if j < i:
                        text_parts.append(w)
                    elif j == i:
                        text_parts.append(f"{{\\fscx150\\fscy150\\t(0,100,\\fscx100\\fscy100)}}{w}{{\\fscx100\\fscy100}}")
                    else:
                        text_parts.append(f"{{\\alpha&HFF&}}{w}{{\\alpha}}")
                
                full_text = " ".join(text_parts)
                # Apply word wrapping (we should replace space with \N manually based on length, or just keep it simple)
                import textwrap
                # Tricky to textwrap when there are tags. Let's just do a simple replacement.
                # Since hook text is short, we can rely on standard spacing or manual break
                
                fad_tag = r"{\fad(100,500)}" if i == 0 else r"{\fad(0,500)}"
                full_text_formatted = full_text.replace(r"{\alpha}", r"{\alpha&H00&}")
                
                event_line = f"Dialogue: 1,{format_ass_time(start_td)},{format_ass_time(end_td)},HookTitle,,0,0,0,,{fad_tag}{full_text_formatted}"
                ass_content.append(event_line)

    cursor = 0.0
    for asset in scene_assets:
        duration = asset["duration"]
        # Dùng đúng mốc thời gian tuyệt đối (start_time đã tính overlap crossfade trong
        # build_scene_timeline) để phụ đề khớp 100% với giọng đọc. Trước đây hàm này tự
        # cộng dồn `cursor += duration` KHÔNG trừ overlap → phụ đề lệch dần theo số cảnh.
        scene_start = asset.get("start_time")
        if scene_start is None:
            scene_start = cursor
        if asset.get("text") and asset["text"].strip():
            start_td = dt.timedelta(seconds=scene_start)
            end_td = dt.timedelta(seconds=scene_start + duration)
            
            start_str = format_ass_time(start_td)
            end_str = format_ass_time(end_td)
            
            # Xử lý Text & Effect
            pop_effect = r"{\fscx30\fscy30\t(0,100,\fscx150\fscy150)\t(100,250,\fscx100\fscy100)}"
            word_boundaries = asset.get("word_boundaries", [])
            
            if subtitle_style == "cinematic_box":
                # Tĩnh, không pop-in, không highlight từng từ
                import textwrap
                raw_text = _strip_emoji_for_subtitle(asset["text"]).replace('\n', ' ')
                wrapped = "\\N".join(textwrap.wrap(raw_text, width=32))
                ass_text = wrapped
            elif subtitle_style == "minimal_white":
                # Tĩnh chữ trắng nhỏ, có hiệu ứng fade nhẹ 200ms
                import textwrap
                raw_text = _strip_emoji_for_subtitle(asset["text"]).replace('\n', ' ')
                wrapped = "\\N".join(textwrap.wrap(raw_text, width=35))
                ass_text = f"{{\\fad(200,200)}}{wrapped}"
            else:
                # Karaoke & Hormozi Style (có highlight, pop-in)
                if word_boundaries:
                    def _chunk_word_boundaries(wbs, max_chars=14):
                        chunks = []
                        curr = []
                        curr_len = 0
                        for w in wbs:
                            if curr_len + len(w["text"]) > max_chars and curr:
                                chunks.append(curr)
                                curr = []
                                curr_len = 0
                            curr.append(w)
                            curr_len += len(w["text"]) + 1
                        if curr:
                            chunks.append(curr)
                        return chunks

                    chunks = _chunk_word_boundaries(word_boundaries, max_chars=14)
                    import random
                    hormozi_colors = ["&H0000FFFF", "&H000000FF", "&H0000FF00", "&H0000A5FF"] # Yellow, Red, Green, Orange
                    _VN_STOPWORDS = {
                        "CỦA", "VÀ", "LÀ", "CÓ", "CHO", "ĐỂ", "MỘT", "CÁC", "NHỮNG",
                        "TRONG", "KHÔNG", "ĐƯỢC", "NÀY", "ĐÓ", "VỚI", "TRÊN", "THEO",
                        "NHƯ", "HAY", "HOẶC", "NHƯNG", "TỪ", "ĐẾN", "VỀ", "BỞI",
                        "CŨNG", "ĐÃ", "SẼ", "ĐANG", "VẪN", "MÀ", "THÌ", "KHI",
                        "NẾU", "HƠN", "RẤT", "QUÁ", "BẠN", "TÔI", "ĐI", "LẠI",
                        "RA", "LÊN", "XUỐNG", "VÀO", "SAU", "TRƯỚC", "NÊN", "CHỈ",
                        "CÒN", "HAI", "BA", "BỐN", "NĂM",
                    }

                    for chunk in chunks:
                        # chunk_start = offset of first word, chunk_end = offset + duration of last word
                        chunk_start_td = dt.timedelta(seconds=scene_start + chunk[0]["offset"])
                        chunk_end_td = dt.timedelta(seconds=scene_start + chunk[-1]["offset"] + chunk[-1]["duration"])
                        chunk_start_str = format_ass_time(chunk_start_td)
                        chunk_end_str = format_ass_time(chunk_end_td)

                        ass_text = pop_effect
                        for i, wb in enumerate(chunk):
                            dur_cs = max(1, int(wb["duration"] * 100))
                            text = wb["text"].upper()
                            prefix = " " if i > 0 else ""
                            if text.startswith(" "):
                                prefix = " "
                                text = text.strip()

                            is_strong = (
                                len(text) > 2
                                and text not in _VN_STOPWORDS
                            ) or any(p in text for p in ['!', '?'])
                            
                            if is_strong:
                                color = random.choice(hormozi_colors) if subtitle_style == "hormozi_bold" else "&H0000FFFF"
                                ass_text += f"{prefix}{{\\K{dur_cs}\\c{color}\\fscx130\\fscy130\\t(0,{dur_cs*10},\\fscx100\\fscy100)}}{text}{{\\c&H0000FFFF\\fscx100\\fscy100}}"
                            else:
                                ass_text += f"{prefix}{{\\K{dur_cs}}}{text}"
                        
                        event_line = f"Dialogue: 0,{chunk_start_str},{chunk_end_str},Default,,0,0,0,,{ass_text}"
                        ass_content.append(event_line)
                else:
                    import textwrap
                    text = _strip_emoji_for_subtitle(asset["text"]).replace('\n', ' ').upper()
                    wrapped = "\\N".join(textwrap.wrap(text, width=28))
                    ass_text = f"{pop_effect}{wrapped}"
                    event_line = f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{ass_text}"
                    ass_content.append(event_line)
            
            if subtitle_style in ("cinematic_box", "minimal_white"):
                event_line = f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{ass_text}"
                ass_content.append(event_line)
            
        cursor += duration

    with open(output_path, "w", encoding="utf-8-sig") as f:
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
