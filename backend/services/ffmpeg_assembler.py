"""
ffmpeg_assembler.py — Dựng toàn bộ timeline bằng MỘT lệnh FFmpeg thay cho MoviePy.

VÌ SAO CÓ MODULE NÀY
--------------------
Khâu chậm nhất của pipeline là MoviePy sinh từng khung hình bằng Python: đơn luồng,
không dùng GPU, và mỗi lớp (resize, mặt nạ crossfade, overlay) nhân chi phí lên. Đo trên
máy dự án: 3.54 fps → một video 3 phút ngốn gần nửa tiếng chỉ để ghép hình.

FFmpeg làm đúng việc đó bằng C, đa luồng, và encode được bằng NVENC.

ĐIỀU KIỆN TIÊN QUYẾT (do `normalize_stock_clip` + `apply_ken_burns` bảo đảm):
mọi cảnh đã là file video ĐÚNG khung hình đích và ĐÚNG thời lượng. Bộ lọc `xfade`
của FFmpeg bắt buộc hai đầu vào cùng độ phân giải/fps/pixel format — trước khi có
bước chuẩn hoá đó thì không thể dùng hướng này.

Không đủ điều kiện → `can_assemble()` trả False và pipeline tự quay về MoviePy.
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from typing import List, Dict, Any, Optional, Tuple

import imageio_ffmpeg

logger = logging.getLogger(__name__)

# transition nội bộ → tên bộ lọc xfade của FFmpeg.
# Vài hiệu ứng không có bản tương đương chính xác thì lấy cái gần nhất về CẢM GIÁC
# (whip_pan là cú quét nhanh → slideleft; page_flip là lật trang → squeezeh).
TRANSITION_TO_XFADE = {
    "crossfade":    "fade",
    "fade_black":   "fadeblack",
    "fade_white":   "fadewhite",
    "zoom_through": "zoomin",
    "zoom_punch":   "zoomin",
    "slide_left":   "slideleft",
    "slide_right":  "slideright",
    "slide_up":     "slideup",
    "slide_down":   "slidedown",
    "whip_pan":     "slideleft",
    "page_flip":    "squeezeh",
    "droplet":      "circleopen",
    "wipe_right":   "wiperight",
    "wipe_down":    "wipedown",
}
DEFAULT_XFADE = "fade"

HIGHLIGHT_FONT = "C:/Windows/Fonts/seguibl.ttf"   # Arial Black thiếu glyph ư/ơ
HIGHLIGHT_DURATION = 1.2
HIGHLIGHT_FADE = 0.2


def _ff() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _esc_path(p: str) -> str:
    """
    Đường dẫn Windows dùng trong filtergraph: đổi \\ thành /, escape dấu ':' của ổ đĩa.
    Không escape thì FFmpeg coi 'C:' là ranh giới tham số → 'Invalid argument'.
    """
    return p.replace("\\", "/").replace(":", r"\:")


def _esc_expr(e: str) -> str:
    """
    Biểu thức trong filtergraph (enable, alpha...): phải escape dấu ',' vì dấu phẩy là
    ký tự NGĂN CÁCH GIỮA CÁC BỘ LỌC. Dấu nháy đơn KHÔNG bảo vệ được nó —
    đã kiểm chứng: `enable='lt(t,1.2)'` bị từ chối, `enable='lt(t\\,1.2)'` chạy tốt.
    """
    return e.replace(",", r"\,")


def _probe(path: str) -> Optional[Tuple[int, int, float]]:
    """(width, height, duration) của một file video, None nếu không đọc được."""
    import re
    try:
        r = subprocess.run([_ff(), "-hide_banner", "-i", path],
                           capture_output=True, text=True, timeout=20, errors="replace")
        m = re.search(r"Video:.*?,\s*(\d{2,5})x(\d{2,5})", r.stderr)
        d = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", r.stderr)
        if not m:
            return None
        dur = (int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3))) if d else 0.0
        return int(m.group(1)), int(m.group(2)), dur
    except Exception:
        return None


def can_assemble(scene_assets: List[Dict[str, Any]], width: int, height: int) -> Tuple[bool, str]:
    """
    Đường nhanh chỉ dùng được khi MỌI cảnh đã là video đúng khung hình đích.
    Trả (được hay không, lý do) — lý do được log để còn biết vì sao rơi về MoviePy.
    """
    if not scene_assets:
        return False, "không có cảnh nào"
    for i, a in enumerate(scene_assets):
        p = a.get("image_path") or ""
        if not p.lower().endswith((".mp4", ".mov")):
            return False, f"cảnh {i+1} không phải video ({os.path.basename(p)})"
        if not os.path.isfile(p):
            return False, f"cảnh {i+1} thiếu file"
        info = _probe(p)
        if info is None:
            return False, f"cảnh {i+1} không đọc được thông số"
        if (info[0], info[1]) != (width, height):
            return False, f"cảnh {i+1} là {info[0]}x{info[1]}, cần {width}x{height}"
    return True, "ok"


def _has_nvenc() -> bool:
    try:
        r = subprocess.run([_ff(), "-hide_banner", "-encoders"],
                           capture_output=True, text=True, timeout=15)
        return "h264_nvenc" in r.stdout
    except Exception:
        return False


# Dấu hiệu NVENC chết trong stderr. `-encoders` chỉ nói driver CÓ encoder, không nói
# còn phiên trống — nên hết trần phiên chỉ lộ ra lúc chạy thật.
_NVENC_FAILURE_MARKERS = (
    "too many nvenc sessions",
    "openencodesessionex failed",
    "no capable devices found",
    "cannot load nvcuda",
    "driver does not support",
    "incompatible client key",
    "out of memory",
)


def _is_nvenc_failure(stderr: str) -> bool:
    """Chỉ gọi khi lệnh NVENC đã lỗi: bắt rộng thì cùng lắm tốn một lần thử lại."""
    s = (stderr or "").lower()
    return "nvenc" in s or any(m in s for m in _NVENC_FAILURE_MARKERS)


def assemble(
    scene_assets: List[Dict[str, Any]],
    output_path: str,
    width: int,
    height: int,
    fps: int = 30,
    crossfade_dur: float = 0.4,
    audio_path: Optional[str] = None,
    hook_video: Optional[str] = None,
    hook_duration: float = 0.0,
    outro_video: Optional[str] = None,
    outro_start: float = 0.0,
    outro_duration: float = 0.0,
    use_gpu: bool = True,
    timeout: int = 3600,
) -> str:
    """
    Ghép các cảnh thành 1 video bằng chuỗi bộ lọc `xfade`, kèm chữ nhấn (drawtext),
    lớp phủ hook và track âm thanh đã trộn sẵn.

    Ném exception nếu FFmpeg lỗi — caller phải bắt để quay về MoviePy.
    """
    n = len(scene_assets)
    base_start = float(scene_assets[0].get("start_time", 0.0))
    lead_in = max(0.0, base_start)   # khoảng trống đầu video dành cho hook (xem HOOK_NARRATION_LEAD)

    cmd = [_ff(), "-y"]
    for a in scene_assets:
        cmd += ["-i", a["image_path"]]
    # Index input cho FFmpeg: cảnh chiếm 0..n-1, rồi tới hook / outro / audio theo đúng
    # thứ tự chúng được nối vào lệnh. BỘ ĐẾM CHẠY, không suy ra từ len(cmd).
    #
    # LỖI CŨ: `hook_idx = len(cmd) // 2`. Công thức đó ngầm giả định `cmd` bắt đầu bằng
    # ĐÚNG MỘT phần tử trước các cặp "-i <path>", nhưng nó khởi tạo là [ffmpeg, "-y"] —
    # hai phần tử. Kết quả lệch đúng +1 ở MỌI số cảnh, nên cả ba index đều trỏ vào input
    # không tồn tại và FFmpeg chết ngay lúc phân tích tham số:
    #     Invalid input file index: 2.
    #     Failed to set value '2:a' for option 'map'
    # Đường nhanh hỏng hoàn toàn ở mọi cấu hình có tiếng, job lặng lẽ rơi về MoviePy —
    # 19 cảnh mất 30-45 phút thay vì 15-20 giây, mà vẫn báo "Hoàn tất!".
    #
    # Bộ đếm chạy thay vì biểu thức lồng kiểu `n + (1 if hook else 0)`: thêm input thứ tư
    # sau này chỉ là chép thêm một khối, không phải tính lại số học của các khối trước —
    # chính chỗ đó đã gãy khi outro_video được nối vào.
    hook_idx = outro_idx = audio_idx = None
    next_idx = n
    if hook_video and os.path.isfile(hook_video):
        hook_idx = next_idx
        next_idx += 1
        cmd += ["-i", hook_video]
    if outro_video and os.path.isfile(outro_video):
        outro_idx = next_idx
        next_idx += 1
        cmd += ["-i", outro_video]
    if audio_path and os.path.isfile(audio_path):
        audio_idx = next_idx
        next_idx += 1
        cmd += ["-i", audio_path]

    fc: List[str] = []
    tmp_texts: List[str] = []

    # ── 1. Chuẩn hoá từng cảnh + chữ nhấn ──
    for i, a in enumerate(scene_assets):
        dur = float(a.get("duration", 3.0))
        lbl = f"s{i}"
        chain = (f"[{i}:v]trim=duration={dur:.3f},setpts=PTS-STARTPTS,"
                 f"fps={fps},format=yuv420p")

        hl = (a.get("highlight_text") or "").strip()
        if hl:
            # Dùng textfile thay vì text= để khỏi phải escape dấu tiếng Việt và ký tự đặc biệt
            fd, tf = tempfile.mkstemp(suffix=".txt")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(hl.upper())
            tmp_texts.append(tf)
            hl_dur = min(HIGHLIGHT_DURATION, dur)
            fade = min(HIGHLIGHT_FADE, hl_dur / 3)
            alpha = (f"if(lt(t,{fade:.3f}),t/{fade:.3f},"
                     f"if(lt(t,{hl_dur - fade:.3f}),1,max(0,({hl_dur:.3f}-t)/{fade:.3f})))")
            chain += (
                f",drawtext=fontfile='{_esc_path(HIGHLIGHT_FONT)}':"
                f"textfile='{_esc_path(tf)}':"
                f"fontsize=120:fontcolor=yellow:borderw=6:bordercolor=black:"
                f"x=(w-text_w)/2:y=h*0.25:"
                f"alpha='{_esc_expr(alpha)}':"
                f"enable='{_esc_expr(f'lt(t,{hl_dur:.3f})')}'"
            )
        fc.append(f"{chain}[{lbl}]")

    # ── 2. Chuỗi xfade ──
    # offset của phép chuyển thứ k = mốc bắt đầu của cảnh k+1 trên dòng thời gian đầu ra.
    # start_time đã tính sẵn phần chồng lấn nên lấy thẳng, chỉ trừ đi lead-in.
    if n == 1:
        fc.append("[s0]null[vcat]")
    else:
        cur = "[s0]"
        for k in range(n - 1):
            trans = TRANSITION_TO_XFADE.get(
                scene_assets[k].get("transition", "crossfade"), DEFAULT_XFADE
            )
            offset = float(scene_assets[k + 1].get("start_time", 0.0)) - base_start
            out = f"[x{k}]" if k < n - 2 else "[vcat]"
            fc.append(
                f"{cur}[s{k+1}]xfade=transition={trans}:"
                f"duration={crossfade_dur:.3f}:offset={offset:.3f}{out}"
            )
            cur = out

    chain_lbl = "[vcat]"

    # ── 3. Chèn khoảng trống đầu cho hook và cuối cho outro ──
    # Pad đầu video
    if lead_in > 0.01:
        fc.append(f"{chain_lbl}tpad=start_duration={lead_in:.3f}:start_mode=add:color=black[vpad1]")
        chain_lbl = "[vpad1]"
        
    # Pad cuối video nếu outro làm tăng thời lượng
    # Do outro overlay lên, nếu outro nằm ngoài thời lượng hiện tại của video, ta cần pad thêm
    if outro_idx is not None and outro_duration > 0:
        # Ở video_service.py chúng ta sẽ tự tính final_duration đã bao gồm outro hay chưa.
        # Nhưng an toàn nhất là pad cuối video một khoảng thời lượng bằng outro_duration
        # để chắc chắn có nền đen cho outro nếu video chưa đủ dài.
        fc.append(f"{chain_lbl}tpad=stop_duration={outro_duration:.3f}:stop_mode=clone[vpad2]")
        chain_lbl = "[vpad2]"

    # ── 4. Lớp phủ hook và outro ──
    if hook_idx is not None:
        fc.append(f"[{hook_idx}:v]fps={fps},format=yuv420p,setpts=PTS-STARTPTS[hk]")
        fc.append(f"{chain_lbl}[hk]overlay=0:0:enable='lt(t,{hook_duration:.3f})'[vout1]")
        chain_lbl = "[vout1]"
        
    if outro_idx is not None:
        # DỜI clip outro tới đúng mốc nó phải xuất hiện, không chỉ bật/tắt bằng `enable`.
        #
        # LỖI CŨ: `setpts=PTS-STARTPTS` đặt clip về mốc 0, nên nó chạy hết 2 giây của mình
        # ngay lúc video mới bắt đầu; tới khi `enable='gte(t,27.8)'` bật lên thì clip đã
        # kết thúc từ lâu và FFmpeg giữ nguyên KHUNG CUỐI (eof_action=repeat mặc định).
        # Khán giả thấy một khung hình đứng im, không phải hiệu ứng — với MỌI loại outro.
        # typewriter_quote không hiện nổi một chữ vì chữ chạy xong từ giây thứ 2.
        #
        # Hook KHÔNG dính lỗi này vì `enable='lt(t, hook_duration)'` vốn khớp sẵn với clip
        # bắt đầu tại 0.
        #
        # Đã đo bằng overlay sáng-dần-đều: bản cũ cho 250/250 tại hai mốc đầu-cuối cửa sổ
        # (đóng băng), bản này cho 25/229 (chạy đúng).
        fc.append(
            f"[{outro_idx}:v]fps={fps},format=yuv420p,"
            f"setpts=PTS-STARTPTS+{outro_start:.3f}/TB[outrov]"
        )
        fc.append(f"{chain_lbl}[outrov]overlay=0:0:enable='gte(t,{outro_start:.3f})'[vout2]")
        chain_lbl = "[vout2]"
        
    if hook_idx is None and outro_idx is None:
        fc.append(f"{chain_lbl}null[vout]")
        chain_lbl = "[vout]"

    cmd += ["-filter_complex", ";".join(fc), "-map", chain_lbl]
    if audio_idx is not None:
        cmd += ["-map", f"{audio_idx}:a"]

    tail = ["-pix_fmt", "yuv420p"]
    if audio_idx is not None:
        tail += ["-c:a", "aac", "-b:a", "192k"]
    tail += [output_path]

    def _build(use_nvenc: bool) -> List[str]:
        """Dựng lại lệnh trọn vẹn cho từng encoder — xem ghi chú fallback bên dưới."""
        if use_nvenc:
            # File này là bản TRUNG GIAN — audio_mix_service sẽ encode lại lần nữa, nên
            # ở đây ưu tiên GIỮ CHẤT LƯỢNG (chống mất mát qua hai đời nén), không phải
            # ép dung lượng. Vì vậy cq 19 chứ không phải 23 như bước master.
            # Đo trên video của dự án: cq 19 cho SSIM 0.99760, ngang với `-b:v 10M` cũ,
            # nhưng file nhỏ hơn ~8% và tự co lại rất nhiều ở cảnh ảnh tĩnh — thứ mà
            # bitrate cố định không làm được.
            enc = ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr",
                   "-cq", "19", "-b:v", "0", "-maxrate", "16M", "-bufsize", "32M"]
        else:
            enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                   "-threads", str(os.cpu_count() or 4)]
        return cmd + enc + tail

    gpu = use_gpu and _has_nvenc()
    # Báo CẢ outro, không chỉ hook: đường nhanh từng ghép outro sai (clip chạy hết ở
    # đầu video rồi đứng hình) mà dòng log này không hề nhắc tới nó, nên không có cách
    # nào biết outro có tới được FFmpeg hay không ngoài việc mở video ra xem.
    logger.info(
        f"[FFmpegAssembler] {n} cảnh, lead-in {lead_in:.2f}s, "
        f"hook={'có' if hook_idx is not None else 'không'}, "
        f"outro={f'có @{outro_start:.2f}s dài {outro_duration:.2f}s' if outro_idx is not None else 'không'}, "
        f"encoder={'NVENC' if gpu else 'libx264'}"
    )
    try:
        r = subprocess.run(_build(gpu), capture_output=True, text=True,
                           timeout=timeout, errors="replace")
        # GeForce tiêu dùng chỉ cho 3-5 phiên NVENC đồng thời; render song song vượt
        # trần thì phiên mới chết ngay lúc khởi tạo. Thử lại bằng CPU trước khi bỏ
        # cuộc — chậm hơn nhiều nhưng không có trần phiên.
        if r.returncode != 0 and gpu and _is_nvenc_failure(r.stderr):
            logger.warning("[FFmpegAssembler] NVENC không dùng được → thử lại bằng libx264")
            r = subprocess.run(_build(False), capture_output=True, text=True,
                               timeout=timeout, errors="replace")
        if r.returncode != 0:
            raise RuntimeError(f"FFmpeg lỗi (mã {r.returncode}): {r.stderr[-1500:]}")
    finally:
        for t in tmp_texts:
            try:
                os.remove(t)
            except OSError:
                pass

    if not os.path.isfile(output_path) or os.path.getsize(output_path) < 10000:
        raise RuntimeError("FFmpeg chạy xong nhưng file ra rỗng/quá nhỏ")
    return output_path
