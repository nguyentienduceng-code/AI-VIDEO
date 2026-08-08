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

import os
import re
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
    # Clip ra phải ĐÚNG khung hình đích, không phải khung của ảnh nguồn.
    #
    # LỖI CŨ (nút thắt cổ chai hiệu năng): `s={w}x{h}` lấy w,h từ kích thước ẢNH NGUỒN
    # — tham số `resolution` chỉ được dùng khi PIL đọc lỗi. Ảnh Imagen sinh ra là
    # 867x1300 / 861x1300 / 1040x1300..., nên clip ra cũng mang đúng cỡ lẻ đó. Mà
    # `ffmpeg_assembler.can_assemble` đòi MỌI cảnh phải đúng bằng khung đích mới cho đi
    # đường FastAssembly; lệch một pixel là rơi hết về MoviePy — đơn luồng, không GPU,
    # chậm gấp hàng trăm lần. Nghĩa là FastAssembly chưa từng chạy với cảnh ảnh, kể cả
    # khi Ken Burns đang BẬT.
    w, h = resolution
    w -= w % 2      # libx264 đòi cạnh chẵn
    h -= h % 2

    # max(1,...) chặn chia cho 0 trong zoom_expr khi cảnh quá ngắn (duration < 1/fps).
    total_frames = max(1, int(duration * fps))

    # Công thức zoom tuyến tính từ zoom_start -> zoom_end trong suốt clip
    zoom_expr = f"'{zoom_start}+({zoom_end}-{zoom_start})*on/{total_frames}'"

    pan_map = {
        "center": ("iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
        "left_to_right": ("(iw-iw/zoom)*on/{}".format(total_frames), "ih/2-(ih/zoom/2)"),
        "right_to_left": ("(iw-iw/zoom)*(1-on/{})".format(total_frames), "ih/2-(ih/zoom/2)"),
        "top_to_bottom": ("iw/2-(iw/zoom/2)", "(ih-ih/zoom)*on/{}".format(total_frames)),
    }
    x_expr, y_expr = pan_map.get(pan_direction, pan_map["center"])

    # Phủ kín khung TRƯỚC khi zoompan: ảnh nguồn thường là 2:3 còn khung đích là 9:16,
    # đưa thẳng vào zoompan thì nó kéo giãn cho vừa `s=` → mặt người bị bóp méo.
    # scale(increase)+crop = "cover", cắt bớt hai bên thay vì bóp, và không để viền đen.
    fit = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"

    zoompan_filter = (
        f"{fit},zoompan=z={zoom_expr}:x='{x_expr}':y='{y_expr}':"
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
    # timeout 10 phút: 1 cảnh Ken Burns không nên lâu hơn thế; chặn treo do FFmpeg kẹt.
    subprocess.run(cmd, check=True, capture_output=True, timeout=600)
    return output_path


def pick_pan_direction(scene_index: int) -> str:
    """
    Xen kẽ hướng pan giữa các cảnh để tránh lặp lại 1 kiểu chuyển động
    nhàm chán xuyên suốt video (dấu hiệu nhận biết ngay của video AI kém đầu tư).
    """
    directions = ["left_to_right", "right_to_left", "center", "top_to_bottom"]
    return directions[scene_index % len(directions)]


def resolve_motion(
    visual_effect: str,
    scene_index: int,
    hook_boost: bool = False,
) -> Tuple[str, float, float]:
    """
    Dịch `visual_effect` do Gemini sinh ra sang tham số thật của `apply_ken_burns`.
    Trả về (pan_direction, zoom_start, zoom_end).

    LÝ DO TỒN TẠI: schema Scene của gemini_service chỉ sinh các giá trị
    zoom_in / zoom_out / pan_left / pan_right / none, trong khi `pan_map` của
    apply_ken_burns lại nhận center / left_to_right / right_to_left / top_to_bottom.
    Hai bảng từ vựng không giao nhau nên `.get()` LUÔN rơi về "center" → mọi cảnh ảnh
    đều zoom center giống hệt nhau, đúng cái cảm giác slideshow mà module này sinh ra
    để chống. Hàm này là cầu nối giữa 2 bảng từ vựng đó.

    Quy ước hướng: "pan_left" = máy quay lia sang TRÁI, tức khung nhìn chạy từ phải
    sang trái trên ảnh → "right_to_left".
    """
    effect = (visual_effect or "").strip().lower()

    if hook_boost:
        # Cảnh mở màn: luôn là cú đấm zoom vào, bất kể Gemini gán gì.
        return "center", 1.0, 1.35

    if effect == "zoom_in":
        return "center", 1.0, 1.18
    if effect == "zoom_out":
        return "center", 1.18, 1.0
    if effect == "pan_left":
        return "right_to_left", 1.08, 1.16
    if effect == "pan_right":
        return "left_to_right", 1.08, 1.16
    if effect == "pan_up":
        return "top_to_bottom", 1.08, 1.16

    # "none", rỗng, hoặc giá trị lạ → xen kẽ theo chỉ số cảnh để không đơn điệu.
    direction = pick_pan_direction(scene_index)
    if direction == "center":
        return "center", 1.0, 1.15
    return direction, 1.08, 1.16


# ---------------------------------------------------------------------------
# 1b. CHUẨN HOÁ CLIP STOCK — cắt đoạn giữa, ping-pong, đúng khung, đồng chất màu
# ---------------------------------------------------------------------------
# Lệch tỉ lệ vượt ngưỡng này thì crop-to-fill sẽ phá bố cục (VD clip 16:9 nhét vào
# 9:16 mất 68% bề ngang) → dùng nền mờ lấp đầy thay vì cắt.
_STOCK_CROP_TOLERANCE = 0.35

# Look Unifier: kéo mọi clip stock về cùng một baseline tương phản/độ nét. Cố ý NHẸ —
# bộ lọc màu tổng (color_grading) vẫn chạy sau ở audio_mix_service cho toàn video.
_STOCK_UNIFY_FILTER = "eq=contrast=1.04:saturation=1.06,unsharp=5:5:0.35"


def _probe_video(path: str) -> Tuple[float, int, int]:
    """Trả (duration, width, height) của 1 file video."""
    from moviepy.video.io.VideoFileClip import VideoFileClip
    with VideoFileClip(path) as v:
        return float(v.duration), int(v.w), int(v.h)


def _build_fit_filter(src_w: int, src_h: int, w: int, h: int, unify: bool) -> str:
    """
    Sinh chuỗi filter đưa clip về ĐÚNG khung w×h, không bao giờ để viền đen.
    Lệch ít  → scale + crop (cover).
    Lệch nhiều → nền mờ lấp đầy + clip gốc fit ở giữa (đúng cách editor thật làm).
    """
    grade = f",{_STOCK_UNIFY_FILTER}" if unify else ""
    src_ratio = (src_w / src_h) if src_h else (w / h)

    if abs((w / h) - src_ratio) <= _STOCK_CROP_TOLERANCE:
        return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}{grade}"

    return (
        f"split=2[bg][fg];"
        f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
        f"gblur=sigma=30,eq=brightness=-0.18[bgb];"
        f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[fgs];"
        f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2{grade}"
    )


def _detect_scene_cuts(video_path: str, ffmpeg_exe: str, threshold: float = 0.35) -> List[float]:
    """
    Trả danh sách mốc thời gian (giây) có CẮT CẢNH CỨNG bên trong 1 file stock.

    LÝ DO CẦN HÀM NÀY: clip stock dài (VD Pexels 10s) thường thực ra là 2-3 shot
    khác nhau nối lại (đổi góc quay, đổi vị trí camera) chứ không phải 1 cú quay
    liên tục. "Cắt đoạn giữa" theo điểm giữa hình học của normalize_stock_clip có
    thể vô tình lấy đúng đoạn NẰM VẮT NGANG một mối nối đó — hậu quả thực tế đã gặp:
    cảnh "lật trang sách" ở giữa xuất hiện cú nhảy hình đột ngột, chữ trong sách từ
    đọc được chuyển sang lộn ngược vì nửa sau đoạn cắt là một shot quay từ phía đối
    diện bàn. Không tự phát hiện được bằng mắt lúc chọn stock vì chỉ xem preview.

    Best-effort: lỗi ở bước này (ffmpeg lạ phiên bản, timeout...) chỉ log rồi trả
    rỗng, KHÔNG được làm hỏng luồng chuẩn hoá clip chính.
    """
    try:
        r = subprocess.run(
            [ffmpeg_exe, "-i", video_path, "-filter:v",
             f"select='gt(scene\\,{threshold})',showinfo", "-f", "null", "-"],
            capture_output=True, text=True, timeout=60,
        )
        return [float(m.group(1)) for m in re.finditer(r"pts_time:(\d+\.?\d*)", r.stderr)]
    except Exception as e:
        logger.warning(f"[StockNorm] Không dò được scene cut ({e}), bỏ qua bước né cắt cảnh.")
        return []


def _pick_cutfree_start(src_dur: float, duration: float, cuts: List[float], margin: float = 0.08) -> float:
    """
    Chọn điểm bắt đầu cho đoạn dài `duration` trong clip `src_dur` giây sao cho
    không có scene cut nào ở [cuts] lọt vào GIỮA đoạn (chỉ chấp nhận cắt đúng ở 2
    đầu mút, tức là mép ngoài của đoạn được lấy).

    Ưu tiên đoạn có tâm gần tâm clip nhất trong số các đoạn "sạch" tìm được, để giữ
    đúng tinh thần cũ (né phần đầu/cuối clip hay đứng yên/fade). Nếu không đoạn nào
    đủ dài mà sạch hoàn toàn (VD clip toàn cảnh cắt liên tục), quay về công thức cũ:
    lấy giữa hình học và CHẤP NHẬN cắt cảnh — còn hơn từ chối cả file.
    """
    default_start = max(0.0, (src_dur - duration) / 2.0)
    if not cuts:
        return default_start

    bounds = [0.0] + sorted(c for c in cuts if 0.0 < c < src_dur) + [src_dur]
    candidates = [(a, b) for a, b in zip(bounds, bounds[1:]) if (b - a) >= duration + margin * 2]
    if not candidates:
        return default_start

    target_center = src_dur / 2.0
    a, b = min(candidates, key=lambda ab: abs((ab[0] + ab[1]) / 2.0 - target_center))
    start = ((a + b) / 2.0) - duration / 2.0
    return max(a + margin, min(start, b - margin - duration))


def normalize_stock_clip(
    video_path: str,
    output_path: str,
    duration: float,
    resolution: Tuple[int, int] = (1080, 1920),
    fps: int = 30,
    unify_look: bool = True,
) -> str:
    """
    Chuẩn hoá 1 clip stock tải về trước khi đưa vào timeline:

    1. Đủ dài  → CẮT ĐOẠN GIỮA (bỏ đầu/cuối, nơi clip stock hay fade hoặc đứng yên)
       thay vì luôn lấy từ giây 0.
    2. Quá ngắn → PING-PONG (xuôi + ngược) rồi lặp liền mạch, thay cho việc nối
       `[clip]*n` của MoviePy vốn tạo cú giật jump-cut ở mỗi vòng lặp.
    3. Ép về đúng khung hình (crop hoặc nền mờ) → downstream không còn viền đen.
    4. Look Unifier: cùng một baseline tương phản/độ nét cho mọi clip.

    Lỗi ở bất kỳ bước nào → raise để caller tự quyết fallback (giữ file gốc).
    """
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    w, h = resolution

    src_dur, src_w, src_h = _probe_video(video_path)
    vf = _build_fit_filter(src_w, src_h, w, h, unify_look)
    tmp_pingpong = None
    # Dư ra 1 frame: chặn trường hợp làm tròn frame khiến clip ngắn hơn cảnh vài ms,
    # buộc video_service phải nối lặp thừa. Phần dư bị cắt bỏ ở bước dựng timeline.
    out_dur = duration + (1.0 / fps)

    try:
        if src_dur >= duration + 0.15:
            # Cắt đoạn giữa: bỏ qua phần đầu tĩnh/fade-in của clip stock, đồng thời
            # né các mối nối shot bên trong clip (xem _detect_scene_cuts).
            cuts = _detect_scene_cuts(video_path, ffmpeg_exe)
            start = _pick_cutfree_start(src_dur, duration, cuts)
            cmd = [
                ffmpeg_exe, "-y", "-ss", f"{start:.3f}", "-i", video_path,
                "-t", f"{out_dur:.3f}",
                "-filter_complex", f"[0:v]{vf},fps={fps}[v]", "-map", "[v]",
                "-an", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "fast",
                output_path,
            ]
            subprocess.run(cmd, check=True, capture_output=True, timeout=600)
        else:
            # Ping-pong: xuôi rồi ngược → điểm nối đầu-cuối trùng nhau nên lặp liền mạch.
            tmp_pingpong = output_path + ".pp.mp4"
            pp_cmd = [
                ffmpeg_exe, "-y", "-i", video_path,
                "-filter_complex",
                "[0:v]split=2[a][b];[b]reverse[r];[a][r]concat=n=2:v=1[v]",
                "-map", "[v]", "-an", "-pix_fmt", "yuv420p",
                "-c:v", "libx264", "-preset", "fast", tmp_pingpong,
            ]
            subprocess.run(pp_cmd, check=True, capture_output=True, timeout=600)

            cmd = [
                ffmpeg_exe, "-y", "-stream_loop", "-1", "-i", tmp_pingpong,
                "-t", f"{out_dur:.3f}",
                "-filter_complex", f"[0:v]{vf},fps={fps}[v]", "-map", "[v]",
                "-an", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "fast",
                output_path,
            ]
            subprocess.run(cmd, check=True, capture_output=True, timeout=600)

        logger.info(
            f"[StockNorm] {src_w}x{src_h} {src_dur:.1f}s -> {w}x{h} {duration:.1f}s "
            f"({'cắt giữa' if src_dur >= duration + 0.15 else 'ping-pong'})"
        )
        return output_path
    finally:
        if tmp_pingpong and os.path.exists(tmp_pingpong):
            try:
                os.remove(tmp_pingpong)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# 2. ĐỒNG BỘ THỜI LƯỢNG CẢNH THEO GIỌNG ĐỌC THỰC TẾ
# ---------------------------------------------------------------------------
def compute_scene_duration_from_audio(
    word_boundaries: List[Dict[str, Any]],
    fallback_duration: float = 2.0,
    min_duration: float = 2.0,
    padding_start: float = 0.15,
    padding_end: float = 0.40,
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


def build_timeline_from_narration(
    scenes: List[Dict[str, Any]],
    scene_wbs: List[List[Dict[str, Any]]],
    total_audio_dur: float,
    overlap_dur: float = 0.0,
    lead_in: float = 0.12,
    tail_pad: float = 0.5,
    min_scene: float = 1.2,
) -> List[Dict[str, Any]]:
    """
    V4.0 — Suy ngược timeline TỪ GIỌNG ĐỌC THẬT (chế độ đọc liền mạch).

    Khác `build_scene_timeline`: ở đó mỗi cảnh có file audio riêng nên thời lượng cảnh =
    độ dài file + đệm CỨNG 0.65s, khiến nhịp máy móc như nhau ở mọi cảnh. Ở đây cả bài
    chỉ có một dải audio duy nhất, nên mốc cắt cảnh được lấy thẳng từ thời điểm giọng đọc
    bước sang câu của cảnh kế tiếp — hình đi theo tiếng, thay vì tiếng phải chờ hình.

    `scene_wbs` là word boundaries mốc TUYỆT ĐỐI. Hàm này ghi lại chúng theo mốc TƯƠNG ĐỐI
    so với start_time của cảnh, vì generate_ass_file cộng `scene_start + wb["offset"]`.
    """
    n = len(scenes)
    if n == 0:
        return scenes

    # Mốc giọng đọc tuyệt đối của từng cảnh
    speech_start: List[float] = []
    speech_end: List[float] = []
    prev_end = 0.0
    for wbs in scene_wbs:
        if wbs:
            s = min(w["offset"] for w in wbs)
            e = max(w["offset"] + w["duration"] for w in wbs)
        else:
            s = e = prev_end  # cảnh không lời (hiếm) → nhận một lát mỏng tại chỗ
        speech_start.append(s)
        speech_end.append(e)
        prev_end = e

    # Mốc VÀO HÌNH: sớm hơn giọng một nhịp lead_in để cú cắt không rơi đúng vào từ đầu.
    visual_start: List[float] = [0.0] * n
    for i in range(1, n):
        lo = visual_start[i - 1] + min_scene
        hi = speech_start[i]  # KHÔNG được vượt quá mốc giọng, nếu không word boundary
        #                       tương đối sẽ âm → timestamp phụ đề hỏng.
        visual_start[i] = min(hi, max(lo, speech_start[i] - lead_in))

    for i, scene in enumerate(scenes):
        if i < n - 1:
            duration = visual_start[i + 1] - visual_start[i] + overlap_dur
            # LỖI CŨ: ép duration lên tối thiểu min_scene mà KHÔNG kéo theo
            # visual_start[i+1] — khi gap tự nhiên giữa 2 mốc vào hình nhỏ hơn
            # min_scene (xảy ra khi speech_start[i] ở nhánh `hi` phía trên kéo
            # visual_start[i] xuống dưới sàn `lo`), cảnh này bị "kéo dài" ĐÈ LÊN
            # cảnh kế tiếp thay vì chỉ ngắn hơn mong muốn. Ưu tiên đúng thứ tự
            # timeline hơn đạt đủ min_scene: chỉ floor bằng epsilon dương nhỏ.
            duration = max(duration, 0.1)
        else:
            duration = total_audio_dur + tail_pad - visual_start[i]
            duration = max(duration, min_scene)

        scene["start_time"] = visual_start[i]
        scene["computed_duration"] = duration
        # Rebase về mốc tương đối của cảnh (đảm bảo >= 0 nhờ ràng buộc `hi` ở trên)
        scene["word_boundaries"] = [
            {
                "offset": max(0.0, w["offset"] - visual_start[i]),
                "duration": w["duration"],
                "text": w["text"],
            }
            for w in scene_wbs[i]
        ]

    logger.info(
        f"[Narration] Timeline theo giọng: {n} cảnh, tổng {total_audio_dur + tail_pad:.2f}s "
        f"(cảnh ngắn nhất {min(s['computed_duration'] for s in scenes):.2f}s)"
    )
    return scenes


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


# ---------------------------------------------------------------------------
# 4. KÍCH THƯỚC CHỮ NHẤN (HIGHLIGHT TEXT) TỰ CO THEO ĐỘ DÀI
# ---------------------------------------------------------------------------
def fit_highlight_fontsize(
    text: str,
    font_path: str,
    max_width: int,
    base_size: int = 120,
    min_size: int = 46,
) -> int:
    """
    Chữ nhấn (highlight_text/B-Roll Text) trước đây LUÔN vẽ ở fontsize=120 bất kể
    độ dài chuỗi. Với cụm từ khoá 3-4 tiếng có dấu (VD "MIỆT MÀI KIẾM TIỀN",
    "LINH HỒN TIỀN TỆ") ở 120px chữ hoa đậm, bề rộng thực tế vượt quá khung 1080px
    và bị cắt cụt ở CẢ HAI mép trái/phải — vì cả drawtext (FFmpeg, x=(w-text_w)/2)
    lẫn TextClip (MoviePy, position="center") đều chỉ canh giữa, không tự co chữ.

    Đo bằng font thật (PIL) để biết bề rộng chính xác ở base_size, rồi co tỉ lệ
    xuống vừa max_width. Chữ ngắn giữ nguyên base_size (không phóng to quá cỡ).
    """
    try:
        from PIL import ImageFont
        font = ImageFont.truetype(font_path, base_size)
        bbox = font.getbbox(text)
        text_w = bbox[2] - bbox[0]
    except Exception:
        logger.warning("[Highlight] Không đo được bề rộng chữ, giữ fontsize mặc định.")
        return base_size

    if text_w <= max_width or text_w <= 0:
        return base_size

    scaled = int(base_size * max_width / text_w)
    return max(min_size, scaled)


# ---------------------------------------------------------------------------
# 5. LỊCH HIỆN CHỮ NHẤN — NEO VÀO LÚC CỤM ĐÓ THỰC SỰ ĐƯỢC ĐỌC
# ---------------------------------------------------------------------------
def _chuan_hoa_tu(s: str) -> str:
    """Bỏ dấu câu + hạ chữ thường, GIỮ NGUYÊN dấu tiếng Việt.

    Bỏ dấu tiếng Việt sẽ làm "chỉ" khớp nhầm "chi", "trích" khớp "trich" của cụm khác —
    đổi lại chẳng lợi gì vì cả hai vế đều lấy từ cùng một kịch bản, cùng bảng mã.
    """
    return "".join(c for c in (s or "").lower() if c.isalnum() or c.isspace()).strip()


def _tim_moc_doc(cum: str, word_boundaries: list) -> float | None:
    """Mốc (giây, tính từ đầu cảnh) mà `cum` bắt đầu được đọc, hoặc None nếu không có.

    Khớp theo CHUỖI TỪ LIÊN TIẾP chứ không phải "chứa chuỗi con": lời đọc là danh sách
    từ rời có kèm dấu câu ("trích,"), nối lại rồi tìm chuỗi con sẽ khớp cả những chỗ
    vắt qua ranh giới từ.
    """
    tu_cum = _chuan_hoa_tu(cum).split()
    if not tu_cum or not word_boundaries:
        return None
    tu_loi = [_chuan_hoa_tu(w.get("text") or w.get("word") or "") for w in word_boundaries]
    for i in range(len(tu_loi) - len(tu_cum) + 1):
        if tu_loi[i:i + len(tu_cum)] == tu_cum:
            try:
                return max(0.0, float(word_boundaries[i].get("offset", 0.0)))
            except (TypeError, ValueError):
                return None
    return None


def plan_scene_highlights(scene_assets: list, hl_duration: float = 1.2) -> dict:
    """
    Cảnh nào được hiện chữ nhấn, và hiện ở giây thứ mấy CỦA CẢNH ĐÓ.

    Trả về {chỉ_số_cảnh: mốc_bắt_đầu_giây}. Cảnh không có trong dict = KHÔNG hiện chữ.

    HAI VẤN ĐỀ ĐO ĐƯỢC TRÊN VIDEO THẬT (a67a0fa9, 30 cảnh) mà hàm này sinh ra để dập:

    1. Chữ nhấn LẶP Y NGUYÊN ở các cảnh liên tiếp — 12/24 cặp. "ĐỪNG CHỈ TRÍCH" nhấp
       lại 4 lần trong 20 giây (cảnh 14-17), cùng màu cùng vị trí, trong khi lời đọc bên
       dưới mỗi lần một khác. Gemini gán từ khoá theo Ý CHÍNH của cả đoạn nên các cảnh
       cùng một ý luôn nhận cùng một cụm.

    2. Chữ nhấn hiện KHÔNG ĐÚNG LÚC. Bản cũ luôn vẽ ở 1.2s ĐẦU cảnh, bất kể cụm đó được
       đọc lúc nào — đo được: chỉ 7/24 cảnh thực sự nói cụm đang hiện, và ngay cả 7 cảnh
       đó cũng đọc muộn hơn 0.98-5.32 giây so với lúc chữ hiện ra. Cảnh 1 đọc "Xin chào
       tất cả mọi người" mà trên màn hình là "THIỆN CHÍ" — mãi cảnh 2 mới nói tới.

    CÁCH LÀM: gom các cảnh LIỀN KỀ có cùng cụm thành một cụm-đoạn, rồi trong mỗi đoạn chỉ
    chọn ĐÚNG MỘT cảnh để hiện — ưu tiên cảnh thực sự đọc cụm đó, neo vào đúng mốc đọc.
    Không cảnh nào đọc (cách đọc khác cách viết, VD "30 TRIỆU BẢN" đọc thành "ba mươi
    triệu bản") thì rơi về cảnh đầu đoạn ở mốc 0 — đúng hành vi cũ, chỉ khác là chỉ còn
    một lần thay vì lặp.

    Chỉ gom các cảnh LIỀN KỀ: cùng một cụm quay lại sau vài chục giây là nhắc lại có chủ
    đích, không phải lặp gây nhàm.
    """
    ke_hoach = {}
    i = 0
    n = len(scene_assets)
    while i < n:
        cum = (scene_assets[i].get("highlight_text") or "").strip()
        if not cum:
            i += 1
            continue
        # Biên của đoạn các cảnh liền kề dùng CÙNG một cụm.
        j = i
        while j + 1 < n and _chuan_hoa_tu(
            (scene_assets[j + 1].get("highlight_text") or "").strip()
        ) == _chuan_hoa_tu(cum):
            j += 1

        chon, moc = None, 0.0
        for k in range(i, j + 1):
            m = _tim_moc_doc(cum, scene_assets[k].get("word_boundaries") or [])
            if m is not None:
                chon, moc = k, m
                break
        if chon is None:
            chon, moc = i, 0.0

        # Không để chữ tràn qua mốc kết thúc cảnh: thà hiện sớm hơn vài trăm ms còn hơn
        # bị cắt cụt giữa chừng lúc chuyển cảnh.
        # "duration" ĐÚNG là key của scene_assets (khác `scenes` ở bước build timeline
        # sớm hơn): main.py dòng ~1205 đọc "computed_duration" từ `scenes` rồi ĐỔI TÊN
        # thành "duration" lúc đóng gói scene_assets — ffmpeg_assembler.py và
        # video_service._build_scene_clip cũng đều đọc "duration" cho đúng cảnh này.
        # (Đã thử đổi sang "computed_duration" — vỡ 2 test trong test_scene_highlight.py
        # vì scene_assets không có key đó, luôn rơi về mặc định 3.0.)
        dur = float(scene_assets[chon].get("duration", 3.0) or 3.0)
        hl = min(hl_duration, dur)
        ke_hoach[chon] = max(0.0, min(moc, dur - hl))
        i = j + 1
    return ke_hoach
