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
AUDIO_FADEOUT_DURATION = 0.12  # giây — fade-out cuối mỗi cảnh, chỉ đủ chống "pop".
                               # Trước là 0.3s: dài hơn cả đuôi im lặng Edge-TTS sinh ra
                               # (~0.1-0.2s) nên ăn vào âm cuối của TỪ CUỐI mỗi cảnh.
SLIDESHOW_SCENE_DURATION = 5.0 # giây — mỗi ảnh hiển thị bao lâu trong slideshow
HOOK_CAROUSEL_DURATION = 3.5   # giây — độ dài clip hook carousel_quote chèn đầu video
# Giọng đọc vào SAU khi trục quay chốt xong. Trục quay chạy 0→1.0s, tiếng "chốt" (ding)
# nổ ở 1.0s; 1.35s là lúc phần đanh nhất của tiếng chốt đã tắt.
# LÝ DO: trước đây giọng đọc bắt đầu ngay 0.0s nên câu dẫn đầu video bị tiếng máy xèng
# đè lên toàn bộ — nghe lùng bùng đúng đoạn quan trọng nhất để giữ chân người xem.
# Phần hình KHÔNG bị đẩy lùi: hook vẫn là lớp phủ 3.5s, chỉ mốc vào tiếng dời đi.
HOOK_NARRATION_LEAD = 1.35

# ── Thư viện tiếng trục quay cho Hook Máy Xèng ──────────────────────
# Thêm tiếng mới: chạy `python tools/fit_hook_sfx.py <file tải về> --name <id>`,
# công cụ đó tự cắt/chuẩn hoá rồi ghi vào assets/sfx/reel_<id>.wav; sau đó khai báo
# thêm 1 dòng ở đây và 1 dòng trong frontend/src/constants.js (HOOK_REEL_SOUNDS).
HOOK_REEL_SOUNDS = {
    "tick_wood":     "reel_spin.wav",             # mặc định — tiếng gõ khớp từng bìa lướt qua
    "arcade_8bit":   "reel_spin_v1_arcade.wav",   # bản 8-bit cũ
    "money_counter": "reel_money_counter.wav",    # tiếng máy đếm tiền (user tự nạp)
}
DEFAULT_HOOK_REEL = "tick_wood"
SFX_MIX_GAIN = 0.6             # hệ số giảm âm lượng SFX chung (tránh SFX thô/to lấn giọng đọc)

# QUAN TRỌNG: font PHẢI có glyph tiếng Việt đầy đủ, đặc biệt ư/Ư (U+01B0/01AF)
# và ơ/Ơ (U+01A1/01A0).
# CẢNH BÁO: "Arial Black" (ariblk.ttf) KHÔNG có các glyph này — đã kiểm chứng bằng
# fontTools trên chính máy này. Khi thiếu glyph, libass thay thế từng ký tự bằng font
# khác nên chữ "trước" hiện thành "trƯớc": sai giữa từ, thấy rõ ở mọi phụ đề.
# Segoe UI Black (seguibl.ttf) cùng độ dày mà phủ đủ tiếng Việt.
SUBTITLE_FONT_NAME = "Segoe UI Black"
SUBTITLE_FONT_PATH = "C:/Windows/Fonts/seguibl.ttf"

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
    "slide_left", "slide_right", "slide_up", "slide_down", "whip_pan",
    "page_flip", "droplet", "zoom_punch", "wipe_right", "wipe_down",
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

        if transition == "zoom_punch":
            # Giật zoom vào: cảnh phóng to 1.4 rồi thu về 1.0 khi xuất hiện (đấm thị giác)
            def _punch(t, d=cf):
                p = min(t / d, 1.0) if d > 0 else 1.0
                ease = 1 - (1 - p) ** 3
                return 1.4 - 0.4 * ease

            scene = scene.resized(_punch).with_position("center")
            scene = scene.with_effects([CrossFadeIn(cf * 0.5), CrossFadeOut(cf)])
            return CompositeVideoClip([scene], size=(video_width, video_height)).with_duration(scene.duration)

        if transition in ("slide_left", "slide_right", "slide_up", "slide_down", "whip_pan", "page_flip"):
            slide_dur = cf * (0.5 if transition == "whip_pan" else 1.0)

            def _pos(t, tr=transition, d=slide_dur):
                p = min(t / d, 1.0) if d > 0 else 1.0
                ease = 1 - (1 - p) ** 3  # ease-out cubic cho cảm giác "đẩy" mượt
                if tr in ("slide_left", "whip_pan", "page_flip"):
                    return (int(video_width * (1 - ease)), 0)      # vào từ phải
                if tr == "slide_right":
                    return (int(-video_width * (1 - ease)), 0)     # vào từ trái
                if tr == "slide_up":
                    return (0, int(video_height * (1 - ease)))     # vào từ dưới
                if tr == "slide_down":
                    return (0, int(-video_height * (1 - ease)))    # vào từ trên
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

        if transition in ("droplet", "wipe_right", "wipe_down"):
            # Mặt nạ reveal: droplet=tròn lan từ tâm; wipe_right=lộ trái→phải; wipe_down=trên→dưới
            import numpy as np
            from moviepy import VideoClip
            w, h = video_width, video_height
            if transition == "droplet":
                max_r = ((w ** 2 + h ** 2) ** 0.5) / 2.0
                yy, xx = np.ogrid[:h, :w]
                dist = np.sqrt((xx - w / 2.0) ** 2 + (yy - h / 2.0) ** 2)

                def _mask_frame(t, d=cf):
                    p = min(t / d, 1.0) if d > 0 else 1.0
                    ease = 1 - (1 - p) ** 2
                    return (dist <= ease * max_r).astype(float)
            else:
                col_idx = np.arange(w).reshape(1, w)
                row_idx = np.arange(h).reshape(h, 1)

                def _mask_frame(t, d=cf, tr=transition):
                    p = min(t / d, 1.0) if d > 0 else 1.0
                    ease = 1 - (1 - p) ** 2
                    if tr == "wipe_right":
                        m = (col_idx <= ease * w).astype(float)
                        return np.broadcast_to(m, (h, w)).copy()
                    m = (row_idx <= ease * h).astype(float)
                    return np.broadcast_to(m, (h, w)).copy()

            mask = VideoClip(_mask_frame, is_mask=True).with_duration(scene.duration)
            return scene.with_mask(mask).with_effects([CrossFadeOut(cf)])
    except Exception as e:
        print(f"[Transition] '{transition}' lỗi ({e}), fallback crossfade.")

    # Mặc định: crossfade
    return scene.with_effects([CrossFadeIn(cf), CrossFadeOut(cf)])


# ─────────────────────────────────────────────────────────────────────
# Chuẩn hoá khung hình — thay viền đen bằng nền mờ lấp đầy
# ─────────────────────────────────────────────────────────────────────
# Lệch tỉ lệ dưới ngưỡng này thì CROP cho lấp đầy khung (mất rìa không đáng kể,
# đẹp hơn mọi loại nền). Vượt ngưỡng mới cần nền mờ.
CROP_FILL_TOLERANCE = 0.18


def _blurred_fill_bg_from_frame(frame, w: int, h: int, duration: float, darken: float = 0.45):
    """
    Nền LẤP ĐẦY khung từ chính khung hình đầu tiên của media: phóng to + làm mờ + tối đi.

    LÝ DO: trước đây media lệch tỉ lệ được fit vào giữa trên nền ColorClip ĐEN. Video stock
    Pexels rất hay trả clip 1080x1350 / 16:9 nên khung 9:16 lòi 2 dải đen dày — thứ giết
    cảm giác "video xịn" nhanh nhất. Nền mờ lấp đầy là cách các editor thật vẫn dùng.
    Nhận sẵn mảng frame thay vì đường dẫn để không phải decode lại file lần hai.
    """
    try:
        from PIL import Image, ImageFilter
        import numpy as np

        img = Image.fromarray(frame).convert("RGB")
        scale = max(w / img.width, h / img.height)
        nw, nh = int(img.width * scale) + 2, int(img.height * scale) + 2
        img = img.resize((nw, nh)).filter(ImageFilter.GaussianBlur(35))
        left, top = (nw - w) // 2, (nh - h) // 2
        img = img.crop((left, top, left + w, top + h))
        arr = (np.array(img).astype(np.float32) * darken).astype(np.uint8)
        return ImageClip(arr).with_duration(duration)
    except Exception as e:
        print(f"[BlurredFill] Lỗi tạo nền mờ ({e}). Dùng nền tối trơn.")
        from moviepy import ColorClip
        return ColorClip((w, h), color=(12, 12, 18)).with_duration(duration)


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
        media_ratio = media_clip.w / media_clip.h
    else:
        media_clip = (
            ImageClip(asset["image_path"])
            .with_duration(duration)
        )
        media_ratio = media_clip.w / media_clip.h

    # Chuẩn hoá về đúng khung: lệch ít → crop lấp đầy; lệch nhiều → nền mờ lấp đầy
    # (KHÔNG dùng viền đen nữa, xem _blurred_fill_bg_from_frame).
    target_ratio = video_width / video_height
    if abs(target_ratio - media_ratio) <= CROP_FILL_TOLERANCE:
        scale_fill = max(video_width / media_clip.w, video_height / media_clip.h)
        media_clip = media_clip.resized(scale_fill).with_position("center")
    else:
        try:
            first_frame = media_clip.get_frame(0)
        except Exception as e:
            print(f"[BlurredFill] Không đọc được frame đầu ({e}).")
            first_frame = None

        if first_frame is not None:
            bg = _blurred_fill_bg_from_frame(first_frame, video_width, video_height, duration)
        else:
            from moviepy import ColorClip
            bg = ColorClip((video_width, video_height), color=(12, 12, 18)).with_duration(duration)

        scale_fit = min(video_width / media_clip.w, video_height / media_clip.h)
        fg = media_clip.resized(scale_fit).with_position("center")
        media_clip = CompositeVideoClip([bg, fg], size=(video_width, video_height)).with_duration(duration)

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


def _mix_audio_tracks(placements, total_duration, sr: int = 44100):
    """
    Trộn nhiều đoạn audio thành 1 AudioArrayClip bằng numpy.

    Mỗi phần tử: (path, start_time, volume, fadeout) hoặc (path, start, volume, fadeout, max_dur).
    `max_dur` (tuỳ chọn) CẮT CỨNG độ dài đoạn đó — dùng cho SFX mà người dùng tự nạp vào,
    để một file dài (VD tiếng máy đếm tiền 5 giây tải trên mạng) không thể tràn sang phần
    lời dẫn. Đây là chốt chặn ở tầng trộn, không phụ thuộc file nguồn dài bao nhiêu.

    LÝ DO KHÔNG dùng CompositeAudioClip: MoviePy 2.1.2 có bug — frame_function dùng
    `if (part is not False)` mà `part` là mảng numpy khi ghi audio theo chunk, khiến nó gọi
    get_frame trên MỌI clip cho MỌI thời điểm (kể cả ngoài cửa sổ). SFX ngắn (vd tick.wav
    0.05s) bị đọc tại t=1.0s → lỗi "Accessing time t=... with clip duration=...".
    Trộn thủ công bằng numpy đọc mỗi file ĐÚNG độ dài của nó nên tuyệt đối an toàn.
    """
    import math
    import numpy as np
    import soundfile as sf
    from moviepy.audio.AudioClip import AudioArrayClip

    def _read(path):
        """Đọc audio ĐÚNG độ dài file bằng soundfile (WAV & MP3), resample về sr nếu lệch.
        soundfile không đọc chunk vượt biên như MoviePy nên an toàn với file ngắn (tick 0.05s)."""
        data, file_sr = sf.read(path, dtype="float32", always_2d=True)  # (n, ch)
        if file_sr != sr and len(data) > 0:
            import librosa
            data = librosa.resample(data.T, orig_sr=file_sr, target_sr=sr).T
        return np.ascontiguousarray(data, dtype=np.float32)

    total_samples = int(math.ceil(max(total_duration, 0.1) * sr)) + sr  # +1s đệm an toàn
    master = np.zeros((total_samples, 2), dtype=np.float32)
    used = False

    for item in placements:
        # Chấp nhận cả tuple 4 phần tử (cũ) lẫn 5 phần tử có max_dur
        path, start, volume, fadeout = item[:4]
        max_dur = item[4] if len(item) > 4 else None
        try:
            arr = _read(path)
        except Exception as e:
            # Fallback: đọc qua MoviePy nếu soundfile không xử lý được định dạng
            try:
                from moviepy.audio.io.AudioFileClip import AudioFileClip
                clip = AudioFileClip(path)
                arr = np.asarray(clip.to_soundarray(fps=sr), dtype=np.float32)
                clip.close()
                if arr.ndim == 1:
                    arr = arr[:, None]
            except Exception as e2:
                print(f"[AudioMix] Bỏ qua {os.path.basename(path)}: {e2}")
                continue

        # Chuẩn hoá về stereo (n, 2)
        if arr.ndim == 1:
            arr = np.column_stack([arr, arr])
        elif arr.shape[1] == 1:
            arr = np.repeat(arr, 2, axis=1)
        elif arr.shape[1] > 2:
            arr = arr[:, :2]

        # Cắt cứng theo max_dur + gọt mềm 40ms cuối để chỗ cắt không kêu "pắc"
        if max_dur and max_dur > 0:
            limit = int(max_dur * sr)
            if 0 < limit < len(arr):
                arr = arr[:limit].copy()
                soft = min(int(0.04 * sr), len(arr))
                if soft > 1:
                    arr[-soft:] *= np.linspace(1.0, 0.0, soft)[:, None]

        if volume != 1.0:
            arr = arr * float(volume)

        if fadeout and fadeout > 0:
            fs = int(fadeout * sr)
            if 0 < fs < len(arr):
                arr[-fs:] *= np.linspace(1.0, 0.0, fs)[:, None]

        s = int(start * sr)
        if s >= total_samples or len(arr) == 0:
            continue
        e = min(s + len(arr), total_samples)
        master[s:e] += arr[: e - s]
        used = True

    if not used:
        return None

    # Chống vỡ tiếng (clipping) nếu tổng biên độ vượt 1.0
    peak = float(np.max(np.abs(master))) if master.size else 0.0
    if peak > 1.0:
        master /= peak

    return AudioArrayClip(master, fps=sr)


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
    audio_placements = []  # (path, start_time, volume, fadeout) — trộn bằng numpy sau vòng lặp
    speech_segments = []
    final_duration = 0.0

    # ── Hook Engine (Overlay clip carousel_quote lên đầu video) ──
    hook_duration = 0.0
    hook_clip_overlay = None
    if kwargs.get("hook_effect") == "carousel_quote":
        try:
            from services.hook_engine import build_carousel_hook
            cover_img = scene_assets[0]["image_path"]
            hook_quote = kwargs.get("hook_quote", "")
            hook_clip_overlay = build_carousel_hook(cover_img, hook_quote, video_width, video_height, HOOK_CAROUSEL_DURATION)
            hook_clip_overlay = hook_clip_overlay.with_start(0.0).with_position("center")
            
            # KHÔNG append vào clips vì clips sẽ vẽ theo thứ tự, có thể bị che. 
            # Ta sẽ thêm vào overlays sau khi final được dựng.
            # Audio cho hook: tiếng trục quay (reel_spin) 0-1s + tiếng "chốt" (ding) khi bìa dừng
            sfx_dir = os.path.join(BASE_DIR, "assets", "sfx")
            reel_key = kwargs.get("hook_reel_sfx") or DEFAULT_HOOK_REEL
            reel_file = HOOK_REEL_SOUNDS.get(reel_key)
            if not reel_file:
                print(f"[Hook] Không biết tiếng trục quay '{reel_key}', dùng mặc định.")
                reel_file = HOOK_REEL_SOUNDS[DEFAULT_HOOK_REEL]
            reel = os.path.join(sfx_dir, reel_file)
            if not os.path.isfile(reel):
                print(f"[Hook] Thiếu {reel_file}, quay về {HOOK_REEL_SOUNDS[DEFAULT_HOOK_REEL]}.")
                reel = os.path.join(sfx_dir, HOOK_REEL_SOUNDS[DEFAULT_HOOK_REEL])
            ding = os.path.join(sfx_dir, "ding.wav")

            # max_dur = HOOK_NARRATION_LEAD: dù người dùng nạp file dài bao nhiêu, tiếng
            # trục quay LUÔN tắt trước khi lời dẫn vào. Chốt chặn cứng ở tầng trộn.
            if os.path.isfile(reel):
                audio_placements.append((reel, 0.0, 0.6, 0.0, HOOK_NARRATION_LEAD))
            if os.path.isfile(ding):
                audio_placements.append((ding, 1.0, 0.45, 0.0))
        except Exception as e:
            print(f"Hook Engine Error: {e}")

    for i, asset in enumerate(scene_assets):
        dur = asset.get("duration", 3.0)
        # KHÔNG mutate asset["start_time"] (gây cộng dồn nếu render lại + double-offset với
        # generate_ass_file). Chỉ dùng biến local; phụ đề tự cộng offset qua hook_effect.
        start_time = asset.get("start_time", 0.0) + hook_duration
        has_audio = bool(asset.get("audio_path"))
        
        # Audio ducking tracking
        if has_audio:
            speech_segments.append((start_time, start_time + dur))
            
        # ── Build Audio Track ──
        # QUAN TRỌNG: KHÔNG composite giọng đọc + SFX vào chung 1 clip. Composite chung khiến
        # MoviePy đọc SFX NGẮN (vd tick.wav 0.05s) vượt quá độ dài của nó khi giọng đọc dài hơn
        # → lỗi "Accessing time t=... with clip duration=...". Đặt mỗi thứ thành TRACK RIÊNG
        # trên timeline tổng; composite ngoài tôn trọng cửa sổ start/end nên không đọc quá.
        # Thu thập vị trí audio để TRỘN bằng numpy sau vòng lặp (xem _mix_audio_tracks).
        # Track giọng đọc (TTS) — fade-out nhẹ cuối để không cụt chữ.
        if has_audio and os.path.isfile(asset["audio_path"]):
            audio_placements.append((asset["audio_path"], start_time, 1.0, AUDIO_FADEOUT_DURATION))

        # SFX chọn RIÊNG cho từng cảnh LUÔN phát (không bị toggle global chặn). Muốn tắt riêng
        # 1 cảnh thì chọn "Không tiếng". Toggle use_sfx global chỉ điều khiển riser mở màn (main.py).
        sfx_name = asset.get("sfx", "")
        if sfx_name:
            sfx_path = os.path.join(BASE_DIR, "assets", "sfx", f"{sfx_name}.wav")
            if os.path.isfile(sfx_path):
                # Giảm âm lượng SFX chung để không thô/to lấn giọng đọc
                audio_placements.append((sfx_path, start_time, sfx_volume * SFX_MIX_GAIN, 0.0))

        
        # Transition của scene[i] nghĩa là "chuyển cảnh SANG cảnh sau" (đúng như UI).
        # Biên i→i+1 hiển thị qua LỐI VÀO của cảnh i+1, nên lối vào của cảnh hiện tại
        # phải dùng transition của cảnh TRƯỚC nó (sửa off-by-one: trước đây cảnh 0 bị bỏ).
        entrance_transition = scene_assets[i - 1].get("transition", "crossfade") if i > 0 else "crossfade"

        c = _build_scene_clip(
            asset,
            add_crossfade_in=(i > 0),
            video_width=video_width,
            video_height=video_height,
            crossfade_dur=crossfade_dur,
            show_subtitle=show_subtitle,
            subtitle_font_size=subtitle_font_size,
            subtitle_color=subtitle_color,
            transition=entrance_transition,
        )
        
        c = c.with_start(start_time)
        clips.append(c)
        final_duration = max(final_duration, start_time + dur)
        
    final = CompositeVideoClip(clips, size=(video_width, video_height)).with_duration(final_duration)

    # Chế độ đọc liền mạch (Single-Pass Narration): cả bài chỉ có 1 dải giọng duy nhất,
    # đặt tại mốc 0.0 như một track nữa trên timeline.
    # TRƯỚC ĐÂY nhánh này gọi `final.with_audio(master_audio)` SAU khi đã trộn xong —
    # tức là THAY TRẮNG toàn bộ track vừa trộn, xoá sạch SFX từng cảnh lẫn tiếng Máy Xèng
    # mở màn. Giờ nó tham gia vào cùng một lần trộn nên mọi thứ cùng vang lên.
    if master_audio_path and os.path.exists(master_audio_path):
        audio_placements.append((master_audio_path, 0.0, 1.0, 0.0))
        speech_segments = [(0.0, final_duration)]

    # Trộn toàn bộ audio (giọng đọc + SFX) bằng numpy → 1 track duy nhất (an toàn, không bug)
    if audio_placements:
        final_audio = _mix_audio_tracks(audio_placements, final_duration)
        if final_audio is not None:
            final = final.with_audio(final_audio)

    # BGM mixing now happens via FFmpeg in audio_mix_service.py

    # ── Thêm Hiệu ứng Hình ảnh (Vignette & Progress Bar) ──
    import numpy as np
    from moviepy.video.VideoClip import ImageClip, VideoClip
    
    # ── OVERLAYS (Vignette, Text Hook, Progress Bar, Carousel Hook) ──
    overlays = [final]
    
    if hook_clip_overlay is not None:
        overlays.append(hook_clip_overlay)

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
        font_name = SUBTITLE_FONT_NAME  # Font dày, hiện đại, phủ đủ tiếng Việt
        font_size = 55
        primary_color = "&H00FFFFFF"     # White
        secondary_color = "&H00FFFFFF"
        outline_color = "&H00000000"     # No outline needed
        back_color = "&H99000000"        # Semi-transparent black (99 is alpha)
        # BorderStyle=3 (Opaque box), Outline=8 (Box padding/margin)
        style_line = f"Style: Default,{font_name},{font_size},{primary_color},{secondary_color},{outline_color},{back_color},-1,0,0,0,100,100,0,0,3,8,0,2,60,60,250,1"
    elif subtitle_style == "minimal_white":
        font_name = SUBTITLE_FONT_NAME
        font_size = 50
        primary_color = "&H00FFFFFF"     # White
        secondary_color = "&H00FFFFFF"
        outline_color = "&H00000000"
        back_color = "&H66000000"        # Soft shadow (alpha 66)
        # BorderStyle=1 (Outline), Outline=0, Shadow=3
        style_line = f"Style: Default,{font_name},{font_size},{primary_color},{secondary_color},{outline_color},{back_color},0,0,0,0,100,100,0,0,1,0,3,2,40,40,250,1"
    else: # karaoke_bold & hormozi_bold (Default)
        # Font dày cho cảm giác Cinematic, phủ đủ tiếng Việt (xem SUBTITLE_FONT_NAME).
        font_name = SUBTITLE_FONT_NAME
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
    hook_style_line = f"Style: HookTitle,{SUBTITLE_FONT_NAME},75,&H0000FFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,8,5,8,40,40,150,1"
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
    if hook_text and hook_text.strip() and hook_effect != "carousel_quote":
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

    # Hook carousel_quote giờ đã được chuyển thành OVERLAY, không đẩy lùi thời gian video nữa.
    # Do đó hook_offset luôn = 0.0 để lồng tiếng và phụ đề Cảnh 1 bắt đầu ngay từ 0.0s.
    hook_offset = 0.0

    cursor = 0.0
    for _idx, asset in enumerate(scene_assets):
        duration = asset["duration"]
        # Dùng đúng mốc thời gian tuyệt đối (start_time đã tính overlap crossfade trong
        # build_scene_timeline) để phụ đề khớp 100% với giọng đọc. Trước đây hàm này tự
        # cộng dồn `cursor += duration` KHÔNG trừ overlap → phụ đề lệch dần theo số cảnh.
        scene_start = asset.get("start_time")
        if scene_start is None:
            scene_start = cursor
        scene_start += hook_offset

        # Phụ đề phải TẮT trước khi cảnh sau bắt đầu.
        # LỖI CŨ: end = scene_start + duration, mà `duration` đã bao gồm phần chồng lấn
        # crossfade (start_{i+1} = start_i + dur_i - overlap). Hệ quả: ở MỌI chuyển cảnh có
        # đúng `overlap` giây mà HAI khối phụ đề cùng hiển thị, chồng đè lên nhau — với
        # style hộp mờ thì thành hai hộp đen chồng nhau, rất lộ.
        scene_end = scene_start + duration
        if _idx + 1 < len(scene_assets):
            next_start = scene_assets[_idx + 1].get("start_time")
            if next_start is not None:
                scene_end = min(scene_end, next_start + hook_offset)

        if asset.get("text") and asset["text"].strip():
            start_td = dt.timedelta(seconds=scene_start)
            end_td = dt.timedelta(seconds=scene_end)

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
                        # Kẹp về scene_end để chunk cuối không tràn sang phụ đề cảnh sau
                        chunk_end_td = dt.timedelta(
                            seconds=min(
                                scene_start + chunk[-1]["offset"] + chunk[-1]["duration"],
                                scene_end,
                            )
                        )
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
