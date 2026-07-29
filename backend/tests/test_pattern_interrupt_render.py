"""
Test RENDER THẬT + ĐO PIXEL cho Pattern Interrupt (B4) — không chỉ đọc code.

VÌ SAO CÓ FILE NÀY: bộ lọc `eq=brightness=...` trong audio_mix_service.py từng thiếu
`eval=frame` — cú pháp FFmpeg hoàn toàn hợp lệ, chạy không báo lỗi gì, "kiểm tra cú
pháp" (đọc code, chạy thử lệnh xem có exception) không bắt được. Hậu quả thật: biểu
thức theo `t` bị khoá cứng lúc khởi tạo, điều kiện `lt(mod(t,3.2),0.1)` luôn đúng, và
TOÀN BỘ video cháy trắng xoá (YAVG=255) từ khung đầu tới khung cuối.

Test này dựng 1 clip xám 64x64 thật, chạy qua ĐÚNG hàm `master_audio_and_export`,
rồi đo YAVG từng khung bằng `ffmpeg signalstats` — đúng phương pháp đã lộ ra bug B4.
Nếu ai đó vô tình bỏ `eval=frame` (hoặc đổi filter theo cách tương tự) trong tương
lai, test này báo đỏ mà không cần render cả video thật để phát hiện bằng mắt.
"""
import os
import re
import subprocess
import sys
import tempfile

import imageio_ffmpeg

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.audio_mix_service import master_audio_and_export

_DURATION = 7.0  # đủ phủ 2 chu kỳ giật (3.2s/lần: khung tại 0.0s / 3.2s / 6.4s)

_gray_input_path = None


def _gray_input() -> str:
    """Clip xám 64x64 dùng chung cho mọi test trong file — dựng 1 lần, cache lại."""
    global _gray_input_path
    if _gray_input_path and os.path.isfile(_gray_input_path):
        return _gray_input_path
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    tmpdir = tempfile.mkdtemp(prefix="avm_pattern_interrupt_")
    path = os.path.join(tmpdir, "in.mp4")
    subprocess.run(
        [ffmpeg_exe, "-y", "-f", "lavfi", "-i", "color=c=gray:s=64x64:d=7:r=20",
         "-pix_fmt", "yuv420p", "-c:v", "libx264", path],
        check=True, capture_output=True, timeout=30,
    )
    _gray_input_path = path
    return path


def _render_and_measure(narration_tone: str) -> list[tuple[float, float]]:
    """Chạy master_audio_and_export thật, trả về [(pts_time, YAVG), ...] của output."""
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    input_path = _gray_input()
    out_path = input_path + f".{narration_tone}.out.mp4"
    master_audio_and_export(
        input_video_path=input_path,
        output_path=out_path,
        use_gpu=False,
        add_vignette=False,  # tối 4 góc sẽ làm nhiễu số đo — tắt để chỉ còn Pattern Interrupt
        progress_bar=False,
        color_grading="none",
        use_pattern_interrupt=True,
        narration_tone=narration_tone,
        total_duration=_DURATION,
    )
    try:
        r = subprocess.run(
            [ffmpeg_exe, "-i", out_path, "-vf", "signalstats,metadata=print:file=-",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=30,
        )
        pts = [float(x) for x in re.findall(r"pts_time:([\d.]+)", r.stdout)]
        yavg = [float(x) for x in re.findall(r"YAVG=([\d.]+)", r.stdout)]
        return list(zip(pts, yavg))
    finally:
        if os.path.isfile(out_path):
            os.remove(out_path)


def test_pattern_interrupt_khong_chay_trang_xoa_toan_video():
    """Lưới chặn CHÍNH cho bug B4: nếu `eval=frame` bị bỏ (quay lại eval=init mặc
    định), MỌI khung hình sẽ cháy trắng ở mức bão hoà — không còn khung nào giữ mức
    xám nền. Test thất bại ngay khi phần lớn khung hình vượt ngưỡng sáng cao."""
    data = _render_and_measure("viral")
    ys = [y for _, y in data]

    assert len(ys) > 50, "Không đọc được đủ khung hình để đo — kiểm tra lại lệnh ffmpeg"

    # Bug cũ: TOÀN BỘ khung hình bị đẩy lên gần 255. Chỉ một vài khung (đúng cửa sổ
    # flash 0.1s mỗi 3.2s) được phép sáng bất thường.
    sang_bat_thuong = [y for y in ys if y > 150]
    assert len(sang_bat_thuong) < len(ys) * 0.3, (
        f"{len(sang_bat_thuong)}/{len(ys)} khung hình bị sáng bất thường (>150) — "
        "nghi ngờ quay lại lỗi eval=init (thiếu eval=frame) làm cháy trắng cả video."
    )

    # Không khung nào được bão hoà trắng hoàn toàn (255) — brightness=0.2 chỉ được
    # phép nhô sáng rõ, không được cháy trắng xoá như hồi brightness=0.6+eval=init.
    assert max(ys) < 230, f"Khung sáng nhất đo được {max(ys)} — nghi cháy trắng xoá."

    # Đa số khung hình (ngoài cửa sổ flash) phải giữ đúng mức xám nền, không bị kéo
    # sáng lên do khoá cứng biểu thức ở t=0.
    nen = [y for y in ys if y <= 150]
    assert nen, "Không còn khung nào giữ mức nền — nghi cháy trắng toàn video."
    assert max(nen) - min(nen) < 5, f"Mức nền dao động bất thường: {nen}"


def test_pattern_interrupt_giat_dung_chu_ky_va_khong_bao_hoa():
    """Đo đúng ĐẶC TÍNH của hiệu ứng: giật sáng ngắn quanh mốc 0s/3.2s/6.4s, mức nền
    còn lại giữ nguyên gần bằng màu gốc — không phải "lâu lâu sáng random" hay
    "luôn sáng suốt video"."""
    data = _render_and_measure("viral")

    flash_windows = [(0.0, 0.15), (3.2, 3.35), (6.4, 6.55)]
    for start, end in flash_windows:
        trong_cua_so = [y for t, y in data if start <= t < end]
        assert trong_cua_so and max(trong_cua_so) > 150, (
            f"Không thấy giật sáng trong cửa sổ [{start},{end}) — hiệu ứng có thể đã hỏng."
        )

    # Khung hình NGOÀI mọi cửa sổ flash (kể cả biên độ trễ pts_time do encode) phải
    # gần mức nền — không bị "rò" sáng ra ngoài cửa sổ 0.1s như thiết kế.
    ngoai_cua_so = [
        y for t, y in data
        if not any(start - 0.1 <= t < end + 0.1 for start, end in flash_windows)
    ]
    assert ngoai_cua_so, "Không có khung nào ngoài cửa sổ flash để so sánh."
    assert max(ngoai_cua_so) < 150, (
        f"Khung ngoài cửa sổ flash vẫn sáng bất thường: max={max(ngoai_cua_so)} — "
        "nghi cửa sổ flash bị rộng ra cả video."
    )


def test_pattern_interrupt_tat_han_o_tone_storytelling():
    """Khoá an toàn của B4: tone Storytelling/Emotional phải TẮT HẲN Pattern
    Interrupt (giữ không khí trầm), không chỉ giảm nhẹ. Nếu `narration_tone` không
    tới được `master_audio_and_export` (đúng bug đã gặp — field khai báo nhưng main.py
    quên nhét vào master_kwargs), giá trị sẽ luôn rơi về mặc định "viral" và bài test
    này sẽ bắt được ngay vì hiệu ứng vẫn chạy."""
    for tone in ("storytelling", "emotional"):
        data = _render_and_measure(tone)
        ys = [y for _, y in data]
        assert max(ys) - min(ys) < 5, (
            f"tone={tone}: dao động sáng {max(ys) - min(ys):.1f} — Pattern Interrupt "
            "lẽ ra phải tắt hẳn ở tone này nhưng vẫn giật sáng."
        )


if __name__ == "__main__":
    from services.log_setup import force_utf8_streams
    force_utf8_streams()

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {fn.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} test đạt")
    sys.exit(1 if failed else 0)
