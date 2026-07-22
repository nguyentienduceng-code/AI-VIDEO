# backend/services/render_export.py
"""
MODULE MỚI - render_export.py
===============================
Thay thế bước export cuối cùng (hiện đang dùng clip.write_videofile() của MoviePy,
chạy bằng CPU libx264) bằng lệnh ffmpeg trực tiếp có GPU encode (NVENC).

CHỈ dùng module này nếu server có GPU NVIDIA. Nếu chạy trên máy không có GPU
(CPU-only), set use_gpu=False để tự động fallback về libx264 CPU như cũ.

Lợi ích: giảm thời gian encode 3-4 lần so với CPU encode ở cùng chất lượng,
quan trọng khi có nhiều user render đồng thời (đúng với mục Technical Debt #2
bạn đã tự ghi trong tài liệu - chuẩn bị sẵn cho việc scale multi-user).
"""

import subprocess
import logging
import shutil

logger = logging.getLogger(__name__)


def _has_nvenc() -> bool:
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    
    # We always have ffmpeg through imageio_ffmpeg
    try:
        result = subprocess.run(
            [ffmpeg_exe, "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10,
        )
        return "h264_nvenc" in result.stdout
    except Exception:
        return False


def export_final_video(
    input_video_path: str,
    ass_subtitle_path: str,
    audio_path: str,
    output_path: str,
    use_gpu: bool = True,
    resolution: str = "1080x1920",
    fps: int = 30,
    crf_or_bitrate: str = "8M",
    watermark_text: str = None,
) -> str:
    """
    Ghép video (đã có scene được nối sẵn) + phụ đề ASS (burned-in bằng filter
    `ass=`) + audio track cuối cùng, xuất ra file MP4 thành phẩm.

    use_gpu=True  -> dùng h264_nvenc (yêu cầu GPU NVIDIA + driver hỗ trợ NVENC)
    use_gpu=False -> dùng libx264 CPU (giống hành vi hiện tại của bạn qua MoviePy)

    ass_subtitle_path: file .ass bạn đã tạo sẵn ở Phụ lục 4 (karaoke captions),
    KHÔNG thay đổi logic sinh phụ đề, chỉ thay đổi bước "đốt" phụ đề vào video.
    """
    gpu_available = use_gpu and _has_nvenc()
    codec = "h264_nvenc" if gpu_available else "libx264"

    # Xây dựng filter scale + ass
    vf_filter = f"scale={resolution.replace('x', ':')}"
    if ass_subtitle_path:
        import os
        # Dùng relative path để tránh lỗi dấu hai chấm (:) của ổ đĩa Windows (C:) trong filter ass
        ass_rel = os.path.relpath(ass_subtitle_path)
        ass_safe = ass_rel.replace('\\', '/')
        vf_filter += f",ass={ass_safe}"

    # Đóng dấu bản quyền (Watermark) nếu có
    if watermark_text:
        wm_text = watermark_text.replace("'", "").replace(":", "")  # sanitize basic
        # Trên Windows cần chỉ định rõ fontfile cho drawtext để tránh crash
        font_path = "C\\:/Windows/Fonts/arial.ttf"
        vf_filter += f",drawtext=fontfile='{font_path}':text='{wm_text}':fontcolor=white@0.6:fontsize=32:x=(w-text_w)/2:y=80:borderw=1:bordercolor=black"

    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    cmd = [
        ffmpeg_exe, "-y",
        "-i", input_video_path,
        "-i", audio_path,
        "-vf", vf_filter,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", codec,
    ]

    if gpu_available:
        cmd += ["-preset", "p4", "-b:v", crf_or_bitrate, "-rc", "vbr"]
    else:
        cmd += ["-preset", "medium", "-crf", "20"]

    cmd += [
        "-c:a", "aac", "-b:a", "192k",
        "-r", str(fps),
        "-pix_fmt", "yuv420p",
        output_path,
    ]

    logger.info(f"[Export] Encode bằng {codec} (GPU={'CÓ' if gpu_available else 'KHÔNG'}) -> {output_path}")
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path
