# backend/services/beat_sync.py
"""
MODULE MỚI - beat_sync.py
==========================
Phát hiện các điểm nhịp (beat) trong nhạc nền (BGM) và "snap" các điểm cắt cảnh
gần nhất về đúng nhịp nhạc. Đây là kỹ thuật dựng phim mà CapCut/Reels/TikTok
templates thịnh hành đều dùng để tạo cảm giác video "có nhịp điệu, không tẻ nhạt".

Yêu cầu: pip install librosa soundfile numpy
(librosa hơi nặng khi cài lần đầu vì phụ thuộc numba/llvmlite, nhưng chạy ổn định).
"""

import logging
import os
from typing import List

import numpy as np
import librosa

logger = logging.getLogger(__name__)

# BGM lấy từ một tập nhỏ file cố định trong BGM_DIR (bundled) — preset dùng đi dùng
# lại đúng vài track đó qua rất nhiều lần render. librosa.load + HPSS + beat_track là
# bước nặng nhất trong beat_sync (decode toàn bộ file nhạc + tách dải âm), không có
# lý do chạy lại cho cùng 1 file. Cache theo (path, mtime, size) — tự invalidate nếu
# user tự thay file nhạc nền vào đúng tên cũ.
_beat_cache: dict[tuple, List[float]] = {}


def detect_beats(bgm_path: str) -> List[float]:
    """
    Trả về danh sách các mốc thời gian (giây) tại đó xảy ra nhịp gõ mạnh (Bass/Snare)
    trong bgm_path bằng thuật toán HPSS (Harmonic-Percussive Source Separation).
    """
    try:
        st = os.stat(bgm_path)
        key = (bgm_path, st.st_mtime, st.st_size)
    except OSError:
        key = None
    if key is not None and key in _beat_cache:
        return _beat_cache[key]

    y, sr = librosa.load(bgm_path, sr=None, mono=True)

    # Phân tách dải âm Harmonic (giai điệu/giọng hát) và Percussive (tiếng gõ/nhịp)
    y_harmonic, y_percussive = librosa.effects.hpss(y)

    # Phát hiện nhịp (beat tracking) chỉ trên dải âm gõ (percussive)
    tempo, beat_frames = librosa.beat.beat_track(y=y_percussive, sr=sr, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    tempo_val = float(tempo[0]) if isinstance(tempo, np.ndarray) else float(tempo)
    logger.info(f"[BeatSync Advanced] Tempo ước tính: {tempo_val:.1f} BPM, "
                f"{len(beat_times)} điểm nhịp gõ (Percussive) phát hiện được trong {bgm_path}")
    result = beat_times.tolist()
    if key is not None:
        _beat_cache[key] = result
    return result


def snap_cut_points_to_beats(
    cut_points: List[float],
    beat_times: List[float],
    max_shift: float = 0.35,
) -> List[float]:
    """
    Với mỗi điểm cắt cảnh dự kiến (cut_points, tính bằng giây - thường lấy từ
    "start_time" trong build_scene_timeline() ở motion_effects.py), tìm beat gần nhất
    trong beat_times và dịch điểm cắt về đúng beat đó, NẾU khoảng lệch không vượt quá
    max_shift giây (tránh làm lệch nhịp nói quá nhiều gây mất tự nhiên).

    Trả về danh sách cut_points mới đã được "snap" theo nhạc.
    """
    if not beat_times:
        return cut_points

    beat_arr = np.array(beat_times)
    snapped = []

    for cp in cut_points:
        if cp == 0:
            snapped.append(0.0)
            continue

        nearest_idx = int(np.argmin(np.abs(beat_arr - cp)))
        nearest_beat = float(beat_arr[nearest_idx])

        if abs(nearest_beat - cp) <= max_shift:
            snapped.append(nearest_beat)
        else:
            # Lệch quá xa so với beat gần nhất -> giữ nguyên điểm cắt gốc
            # (ưu tiên đồng bộ giọng đọc hơn là ép nhịp nhạc)
            snapped.append(cp)

    return snapped


def apply_beat_sync_to_timeline(
    scenes: List[dict], bgm_path: str, max_shift: float = 0.35, min_duration: float = 0.3,
) -> List[dict]:
    """
    Hàm tiện ích gọi trực tiếp từ pipeline render:
    - Lấy "start_time" hiện có của từng scene (đã tính từ build_scene_timeline)
    - Snap về beat gần nhất
    - Cập nhật lại "start_time" (và điều chỉnh "computed_duration" của scene liền trước
      cho khớp, để timeline không bị chồng lấn hoặc có khoảng trống).

    Lưu ý: chỉ nên bật tính năng này khi có BGM rõ nhịp (nhạc điện tử, nhạc có beat
    mạnh). Với nhạc nền êm/ambient không có nhịp rõ, beat detection sẽ không ổn định
    -> nên có config `use_beat_sync: bool` để người dùng tự bật/tắt (xem main_patch.py).
    """
    beat_times = detect_beats(bgm_path)
    original_starts = [s["start_time"] for s in scenes]
    snapped_starts = snap_cut_points_to_beats(original_starts, beat_times, max_shift=max_shift)

    # LỖI CŨ: snap_cut_points_to_beats snap TỪNG điểm ĐỘC LẬP, không đảm bảo thứ tự.
    # Hai điểm cắt gốc gần nhau có thể cùng snap về 1 beat (hoặc snap chéo thứ tự) —
    # computed_duration của cảnh trước tính ra 0 hoặc ÂM, hỏng timeline ngay từ bước
    # dựng lệnh FFmpeg. Ép non-decreasing + floor dương NGAY SAU khi snap, thay vì tin
    # danh sách snap luôn hợp lệ.
    for i in range(1, len(snapped_starts)):
        if snapped_starts[i] < snapped_starts[i - 1] + min_duration:
            snapped_starts[i] = snapped_starts[i - 1] + min_duration

    for i, scene in enumerate(scenes):
        scene["start_time"] = snapped_starts[i]
        if i > 0:
            prev = scenes[i - 1]
            prev["computed_duration"] = scene["start_time"] - prev["start_time"]

    return scenes
