# backend/services/audio_mix_service.py
import subprocess
import logging
import os
import imageio_ffmpeg

logger = logging.getLogger(__name__)

def _ffmpeg_ass_path(ass_path: str) -> str:
    """
    Chuẩn hoá đường dẫn file .ass cho filter `ass=` của FFmpeg.
    Ưu tiên relative path để tránh dấu hai chấm ổ đĩa (C:). Nếu file nằm khác ổ đĩa với CWD
    (relpath ném ValueError) thì dùng absolute path có escape dấu ':' và '\\'.
    """
    try:
        rel = os.path.relpath(ass_path)
        return rel.replace('\\', '/')
    except ValueError:
        # Khác ổ đĩa trên Windows → escape absolute path
        abs_path = os.path.abspath(ass_path).replace('\\', '/')
        return abs_path.replace(':', '\\:')


def _has_nvenc() -> bool:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    try:
        result = subprocess.run(
            [ffmpeg_exe, "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10,
        )
        return "h264_nvenc" in result.stdout
    except Exception:
        return False

def _probe_width(video_path: str) -> int:
    """Bề ngang video, dùng để dựng dải thanh tiến trình đúng cỡ. 0 nếu không đọc được."""
    import re
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    try:
        res = subprocess.run(
            [ffmpeg_exe, "-hide_banner", "-i", video_path],
            capture_output=True, text=True, timeout=15, errors="replace",
        )
        m = re.search(r"Video:.*?,\s*(\d{2,5})x(\d{2,5})", res.stderr)
        return int(m.group(1)) if m else 0
    except Exception:
        return 0


def _has_audio_stream(video_path: str) -> bool:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    try:
        res = subprocess.run(
            [ffmpeg_exe, "-hide_banner", "-i", video_path],
            capture_output=True, text=True, timeout=5
        )
        return "Audio:" in res.stderr
    except Exception:
        return False

COLOR_GRADING_FILTERS = {
    "warm_cinematic": "eq=contrast=1.06:saturation=1.12,colorbalance=rs=0.06:gs=0.01:bs=-0.06:rh=0.04:gh=0.01:bh=-0.04",
    "cool_matrix": "eq=contrast=1.10:saturation=0.88,colorbalance=rs=-0.06:gs=0.04:bs=0.06:rh=-0.04:gh=0.02:bh=0.04",
    "vintage_film": "eq=contrast=1.04:saturation=0.90:brightness=0.02,colorbalance=rs=0.04:gs=0.02:bs=-0.04",
    "vivid_pop": "eq=contrast=1.12:saturation=1.25:brightness=0.01",
    "noir_dramatic": "hue=s=0,eq=contrast=1.25:brightness=-0.02",
    "none": "",
}

def master_audio_and_export(
    input_video_path: str,
    output_path: str,
    bgm_path: str = None,
    ass_subtitle_path: str = None,
    use_gpu: bool = False,
    bgm_volume: float = 0.15,
    watermark_text: str = None,
    color_grading: str = "warm_cinematic",
    add_vignette: bool = True,
    progress_bar: bool = True,
    total_duration: float = 0.0,
) -> str:
    """
    Bước cuối: trộn BGM, master âm thanh, lọc màu, vignette, thanh tiến trình, phụ đề, encode.

    `add_vignette` và `progress_bar` TRƯỚC ĐÂY được MoviePy vẽ ở từng khung hình bằng
    Python — hai lớp phủ toàn màn hình đó một mình đã ngốn 1.93 lần tốc độ render
    (6.83 → 3.54 fps, đo trên máy này). Chuyển xuống đây thì chúng chỉ là 2 filter trong
    lượt encode vốn đã bắt buộc phải chạy, và được NVENC tăng tốc luôn.
    """
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    gpu_available = use_gpu and _has_nvenc()
    vcodec = "h264_nvenc" if gpu_available else "libx264"

    cmd = [
        ffmpeg_exe, "-y",
        "-i", input_video_path
    ]

    has_bgm = bgm_path and os.path.isfile(bgm_path)
    if has_bgm:
        cmd.extend(["-stream_loop", "-1", "-i", bgm_path])

    input_has_audio = _has_audio_stream(input_video_path)
    filter_complex = []
    
    if input_has_audio:
        if has_bgm:
            filter_complex.append(f"[1:a]equalizer=f=2000:t=q:w=2:g=-6,volume={bgm_volume}[bgm_eq]")
            filter_complex.append("[0:a]bass=g=5:f=110,acompressor=threshold=-15dB:ratio=3:attack=5:release=50[voice_eq_raw]")
            filter_complex.append("[voice_eq_raw]asplit=2[voice_eq1][voice_eq2]")
            filter_complex.append("[bgm_eq][voice_eq1]sidechaincompress=threshold=0.05:ratio=8:attack=5:release=300[bgm_ducked]")
            filter_complex.append("[voice_eq2][bgm_ducked]amix=inputs=2:duration=first[mixed]")
            audio_out = "[mixed]"
        else:
            filter_complex.append("[0:a]bass=g=5:f=110,acompressor=threshold=-15dB:ratio=3:attack=5:release=50[voice_eq]")
            audio_out = "[voice_eq]"
        filter_complex.append(f"{audio_out}loudnorm=I=-14:TP=-1.5:LRA=11,alimiter=limit=0.95:attack=5:release=50[audio_master]")
    else:
        if has_bgm:
            filter_complex.append(f"[1:a]equalizer=f=2000:t=q:w=2:g=-6,volume={bgm_volume}[bgm_eq]")
            filter_complex.append(f"[bgm_eq]loudnorm=I=-14:TP=-1.5:LRA=11,alimiter=limit=0.95:attack=5:release=50[audio_master]")

    video_chain = "[0:v]"

    # ── Cinematic Color Grading Filter ──
    cg_filter = COLOR_GRADING_FILTERS.get(color_grading, "")
    if cg_filter:
        filter_complex.append(f"{video_chain}{cg_filter}[v_cg]")
        video_chain = "[v_cg]"

    # ── Vignette: làm tối 4 góc (thay lớp ImageClip RGBA của MoviePy) ──
    if add_vignette:
        filter_complex.append(f"{video_chain}vignette=angle=PI/5:mode=forward[v_vig]")
        video_chain = "[v_vig]"

    # ── Thanh tiến trình vàng dưới đáy ──
    # Kỹ thuật: một dải vàng đúng bề ngang khung hình, TRƯỢT vào từ bên trái.
    # Phần lộ ra = W*t/tổng_thời_lượng, tức đúng một thanh tiến trình chạy dần.
    # KHÔNG dùng drawbox: đã đo trên chính FFmpeg 7.1 của dự án — drawbox chỉ tính biểu
    # thức `w` MỘT LẦN lúc khởi tạo nên thanh luôn full width ở mọi khung. Riêng overlay
    # thì đánh giá x/y theo từng khung (đo được 80/270/458 px đúng mốc 15/50/85%).
    bar_w = _probe_width(input_video_path) if (progress_bar and total_duration > 0) else 0
    if bar_w:
        filter_complex.append(f"color=c=0xFFD700:s={bar_w}x12:d={total_duration:.3f}[pbar]")
        filter_complex.append(
            f"{video_chain}[pbar]overlay=x='-{bar_w}+{bar_w}*t/{total_duration:.3f}':y=H-12[v_pb]"
        )
        video_chain = "[v_pb]"

    if watermark_text:
        wm_text = watermark_text.replace("'", "").replace(":", "")
        font_path = "C\\:/Windows/Fonts/segoeuib.ttf"
        filter_complex.append(f"{video_chain}drawtext=fontfile='{font_path}':text='{wm_text}':fontcolor=white@0.45:fontsize=56:x=w-text_w-60:y=100:borderw=2:bordercolor=black@0.3[v_wm]")
        video_chain = "[v_wm]"

    if ass_subtitle_path and os.path.isfile(ass_subtitle_path):
        ass_safe = _ffmpeg_ass_path(ass_subtitle_path)
        filter_complex.append(f"{video_chain}ass={ass_safe}[video_out]")
        video_chain = "[video_out]"

    if filter_complex:
        cmd.extend(["-filter_complex", ";".join(filter_complex)])
    
    if video_chain != "[0:v]":
        cmd.extend(["-map", video_chain])
    else:
        cmd.extend(["-map", "0:v"])
        
    if input_has_audio or has_bgm:
        cmd.extend(["-map", "[audio_master]"])

    cmd.extend([
        "-c:v", vcodec,
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p"
    ])

    if gpu_available:
        cmd.extend(["-preset", "p4", "-b:v", "8M", "-rc", "vbr"])
    else:
        cmd.extend(["-preset", "medium", "-crf", "20"])

    cmd.extend(["-shortest", output_path])

    logger.info(f"[AudioMaster] Processing: {'NVENC' if gpu_available else 'CPU'}. BGM: {has_bgm}")
    # timeout 30 phút: chặn treo vô hạn nếu FFmpeg kẹt (video dài + CPU encode).
    subprocess.run(cmd, check=True, timeout=1800)

    return output_path
