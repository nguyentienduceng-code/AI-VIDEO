# backend/services/motion_effects.py
"""
MODULE MỚI - motion_effects.py
================================
Xử lý 2 vấn đề "video bị đứng hình / cảm giác slideshow":

1. Ken Burns effect (zoom + pan chậm) cho các cảnh dùng ẢNH TĨNH
   (trường hợp fallback không dùng Veo, hoặc mode Photo Narration / Slideshow).
2. Đồng bộ THỜI LƯỢNG mỗi cảnh theo đúng độ dài giọng đọc thực tế
   (dùng dữ liệu word_boundaries đã có sẵn từ tts_service.py),
   thay vì set cứng ví dụ 4 giây / cảnh.

Yêu cầu: ffmpeg đã có sẵn trong hệ thống (bạn đang dùng MoviePy nên chắc chắn có).
"""

import subprocess
import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. KEN BURNS EFFECT - biến ảnh tĩnh thành clip có chuyển động mượt
# ---------------------------------------------------------------------------
def apply_ken_burns(
    image_path: str,
    output_path: str,
    duration: float,
    fps: int = 30,
    zoom_start: float = 1.0,
    zoom_end: float = 1.15,
    pan_direction: str = "center",
    resolution: Tuple[int, int] = (1080, 1920),  # mặc định 9:16
) -> str:
    """
    Dùng ffmpeg filter `zoompan` để tạo hiệu ứng Ken Burns (zoom + pan chậm).
    Đây là kỹ thuật bắt buộc phải có với các cảnh ảnh tĩnh (Pollinations fallback),
    nếu không video sẽ trông rất "chết" khi so với các cảnh Veo có chuyển động thật.

    pan_direction: "center" | "left_to_right" | "right_to_left" | "top_to_bottom"
    """
    total_frames = int(duration * fps)
    w, h = resolution

    # Công thức zoom tuyến tính từ zoom_start -> zoom_end trong suốt clip
    zoom_expr = f"'{zoom_start}+({zoom_end}-{zoom_start})*on/{total_frames}'"

    pan_map = {
        "center": ("iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
        "left_to_right": ("(iw-iw/zoom)*on/{}".format(total_frames), "ih/2-(ih/zoom/2)"),
        "right_to_left": ("(iw-iw/zoom)*(1-on/{})".format(total_frames), "ih/2-(ih/zoom/2)"),
        "top_to_bottom": ("iw/2-(iw/zoom/2)", "(ih-ih/zoom)*on/{}".format(total_frames)),
    }
    x_expr, y_expr = pan_map.get(pan_direction, pan_map["center"])

    zoompan_filter = (
        f"zoompan=z={zoom_expr}:x='{x_expr}':y='{y_expr}':"
        f"d={total_frames}:s={w}x{h}:fps={fps}"
    )

    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    cmd = [
        ffmpeg_exe, "-y",
        "-loop", "1",
        "-i", image_path,
        "-vf", zoompan_filter,
        "-t", str(duration),
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264",
        "-preset", "fast",
        output_path,
    ]

    logger.info(f"[KenBurns] {image_path} -> {output_path} (dur={duration}s, pan={pan_direction})")
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def pick_pan_direction(scene_index: int) -> str:
    """
    Xen kẽ hướng pan giữa các cảnh để tránh lặp lại 1 kiểu chuyển động
    nhàm chán xuyên suốt video (dấu hiệu nhận biết ngay của video AI kém đầu tư).
    """
    directions = ["left_to_right", "right_to_left", "center", "top_to_bottom"]
    return directions[scene_index % len(directions)]


# ---------------------------------------------------------------------------
# 2. ĐỒNG BỘ THỜI LƯỢNG CẢNH THEO GIỌNG ĐỌC THỰC TẾ
# ---------------------------------------------------------------------------
def compute_scene_duration_from_audio(
    word_boundaries: List[Dict[str, Any]],
    fallback_duration: float = 2.0,
    min_duration: float = 2.0,
    padding_start: float = 0.15,
    padding_end: float = 0.65,
) -> float:
    """
    Tính thời lượng thực tế của 1 cảnh dựa trên word_boundaries do Edge-TTS trả về
    (mỗi phần tử có "duration" tính bằng giây, giống dữ liệu bạn đang dùng cho
    phụ đề karaoke trong video_service.py).

    Việc này thay thế cho scene duration cố định (VD: luôn 4s/cảnh), giúp:
    - Cảnh có câu thoại dài sẽ tự động dài hơn, không bị cắt cụt lời.
    - Cảnh có câu thoại ngắn sẽ không bị kéo dài lê thê gây chán.

    padding_start/padding_end: thời gian đệm đầu/cuối để cảnh không bị "hụt hơi"
    ngay khi giọng đọc vừa dứt.
    """
    if not word_boundaries:
        # Nếu không có word boundaries (lỗi hoặc do virtual voice minion),
        # ưu tiên dùng độ dài thật của audio (fallback_duration) cộng thêm padding.
        # Nếu audio bị lỗi (duration=0) thì mới fallback về min_duration.
        if fallback_duration > 0:
            return max(fallback_duration + padding_end, min_duration)
        return min_duration

    # Tính thời điểm từ kết thúc cuối cùng (max_end).
    # Vì file âm thanh gốc KHÔNG bị cắt phần im lặng ở đầu trong video_service.py,
    # độ dài cảnh phải bao trùm toàn bộ thời gian từ 0 đến max_end.
    max_end = max(wb["offset"] + wb["duration"] for wb in word_boundaries)
    
    # Cộng thêm khoảng nghỉ (padding_end) để giọng đọc dứt hẳn mới chuyển cảnh
    scene_duration = max_end + padding_end
    return max(scene_duration, min_duration)


def build_scene_timeline(scenes_with_audio: List[Dict[str, Any]], overlap_dur: float = 0.0) -> List[Dict[str, Any]]:
    """
    Input: list scene, mỗi scene có key "word_boundaries" (từ tts_service.py).
    Output: cùng list đó nhưng đã gắn thêm "computed_duration" và "start_time"
    (mốc thời gian tuyệt đối để ghép timeline cuối cùng + để đồng bộ beat-sync).
    
    Nếu có overlap_dur > 0, các scene sẽ đè lên nhau 1 khoảng bằng overlap_dur
    để tạo hiệu ứng Crossfade mượt mà trên MoviePy.
    """
    cursor = 0.0
    for i, scene in enumerate(scenes_with_audio):
        wb = scene.get("word_boundaries", [])
        raw_dur = scene.get("computed_duration", 2.0)
        
        duration = compute_scene_duration_from_audio(wb, fallback_duration=raw_dur)
        scene["computed_duration"] = duration
        scene["start_time"] = cursor
        
        cursor += duration
        if i < len(scenes_with_audio) - 1:
            cursor -= overlap_dur
            
    return scenes_with_audio
