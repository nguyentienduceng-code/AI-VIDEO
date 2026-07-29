"""
Test cho cặp HIỆU ỨNG ↔ TIẾNG ĐỘNG của Hook/Outro Engine.

Chạy:  python tests/test_hook_sfx.py    (từ thư mục backend/)
       pytest tests/test_hook_sfx.py

Ba loại lỗi được canh ở đây, cả ba đều CÂM — video vẫn ra, không lỗi nào, chỉ là sai:

  1. SAI TIẾNG. Các nhánh hiệu ứng từng đọc `HOOK_REEL_SOUNDS.get(reel_key, "<tên file
     gõ tay>")`. Fallback đó chỉ nổ khi reel_key không phải khoá hợp lệ — nhưng ca hỏng
     thật lại là khoá HỢP LỆ mà SAI hiệu ứng: mặc định của model là "tick_wood", nên một
     request chọn camera_shutter mà không đụng ô âm thanh sẽ phát TIẾNG MÁY XÈNG cho cú
     bấm máy ảnh. Giao diện có chặn, backend thì không.

  2. THIẾU FILE. Fallback gõ tay còn trỏ vào những file chẳng liên quan (tick.wav cho
     máy ảnh, whoosh.wav cho glitch, suspense.wav cho cháy phim) — và "tick_wood.mp3",
     một file CHƯA BAO GIỜ tồn tại.

  3. TRÀN TIẾNG SANG LỜI THOẠI. Đo trên chính kho tiếng của dự án: ambient_mystic dài
     19.7 giây trên cửa sổ hiệu ứng 3.0 giây — gần 17 giây tiếng nền đè lên lời dẫn mở
     đầu, đúng đoạn quan trọng nhất để giữ chân người xem.
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.video_service import (
    HOOK_EFFECT_SOUNDS,
    HOOK_EFFECTS,
    HOOK_REEL_SOUNDS,
    HOOK_SFX_TAIL,
    hook_sfx_max_dur,
    resolve_effect_sfx,
)
from config import SFX_DIR

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CONSTANTS_JS = os.path.join(_ROOT, "frontend", "src", "constants.js")
_VIDEO_SERVICE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "services", "video_service.py"
)


def _sfx_duration(path: str) -> float | None:
    import imageio_ffmpeg

    r = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", path],
        capture_output=True, text=True, errors="replace",
    )
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


# ── Hợp đồng với giao diện ───────────────────────────────────────────────────
def test_danh_sach_tieng_khop_giao_dien():
    """HOOK_EFFECT_SOUNDS (backend) phải khớp HOOK_SFX_OPTIONS (frontend).

    Lệch nhau thì người dùng chọn được một tiếng mà backend từ chối phát, hoặc ngược
    lại — và cả hai chiều đều im lặng.
    """
    with open(_CONSTANTS_JS, encoding="utf-8") as f:
        js = f.read()
    block = re.search(r"HOOK_SFX_OPTIONS\s*=\s*\{(.*?)\n\};", js, re.S)
    assert block, "không tìm thấy HOOK_SFX_OPTIONS trong constants.js"

    for effect, keys in HOOK_EFFECT_SOUNDS.items():
        m = re.search(rf"{effect}:\s*(\[.*?\]|HOOK_REEL_SOUNDS)", block.group(1), re.S)
        assert m, f"constants.js không khai báo tiếng cho hiệu ứng {effect}"
        if m.group(1) == "HOOK_REEL_SOUNDS":
            continue  # carousel dùng nguyên bộ tiếng trục quay
        js_keys = set(re.findall(r"value:\s*'([a-z0-9_]+)'", m.group(1)))
        assert js_keys == set(keys), (
            f"{effect}: backend {sorted(keys)} ≠ giao diện {sorted(js_keys)}"
        )


def test_moi_hieu_ung_deu_co_tieng_khai_bao():
    """Thêm hiệu ứng mới mà quên khai báo tiếng = hiệu ứng câm, không ai báo."""
    thieu = sorted(set(HOOK_EFFECTS) - set(HOOK_EFFECT_SOUNDS))
    assert not thieu, f"hiệu ứng không có tiếng nào: {thieu}"


# ── File có thật ─────────────────────────────────────────────────────────────
def test_moi_tieng_deu_tro_toi_file_co_that():
    loi = []
    for effect, keys in HOOK_EFFECT_SOUNDS.items():
        for k in keys:
            assert k in HOOK_REEL_SOUNDS, f"{effect}: khoá {k!r} không có trong HOOK_REEL_SOUNDS"
            p = os.path.join(SFX_DIR, HOOK_REEL_SOUNDS[k])
            if not os.path.isfile(p):
                loi.append(f"{effect}/{k} → {HOOK_REEL_SOUNDS[k]}")
    assert not loi, "tiếng động khai báo nhưng không có file: " + ", ".join(loi)


def test_khong_con_ten_file_go_tay_trong_nhanh_hieu_ung():
    """Fallback gõ tay là nguồn của cả hai lỗi 'sai tiếng' và 'thiếu file'.

    "tick_wood.mp3" từng nằm trong mã nguồn suốt một thời gian — nó là tên KHOÁ, file
    thật là reel_spin.wav, nên fallback đó luôn trỏ vào hư không.
    """
    with open(_VIDEO_SERVICE, encoding="utf-8") as f:
        code = "\n".join(
            line for line in f.read().splitlines() if not line.strip().startswith("#")
        )
    con_lai = re.findall(r"HOOK_REEL_SOUNDS\.get\([^)]*\)", code)
    assert not con_lai, (
        f"còn {len(con_lai)} chỗ tra tiếng không qua resolve_effect_sfx(): {con_lai[:3]}"
    )


# ── Hành vi của resolver ─────────────────────────────────────────────────────
def test_khoa_cua_hieu_ung_khac_bi_keo_ve_dung_tieng():
    """ĐÂY LÀ LỖI CHÍNH: hook_reel_sfx mặc định của model là "tick_wood" (chỉ hợp lệ cho
    Máy Xèng). Chọn camera_shutter mà không đụng ô âm thanh thì KHÔNG được phát tiếng
    máy xèng."""
    got = resolve_effect_sfx("camera_shutter", "tick_wood")
    assert got and os.path.basename(got) == HOOK_REEL_SOUNDS["camera_shutter"], (
        f"camera_shutter + tick_wood → {os.path.basename(got or '')}, "
        f"phải là {HOOK_REEL_SOUNDS['camera_shutter']}"
    )


def test_moi_hieu_ung_deu_tu_ve_tieng_cua_chinh_no():
    for effect, keys in HOOK_EFFECT_SOUNDS.items():
        got = resolve_effect_sfx(effect, "khoa_khong_ton_tai")
        assert got and os.path.basename(got) == HOOK_REEL_SOUNDS[keys[0]], (
            f"{effect}: khoá rác phải rơi về {keys[0]}"
        )


def test_none_va_hieu_ung_la_deu_khong_phat_gi():
    assert resolve_effect_sfx("carousel_quote", "none") is None
    assert resolve_effect_sfx("carousel_quote", "") is None
    assert resolve_effect_sfx("none", "tick_wood") is None
    assert resolve_effect_sfx("hieu_ung_la", "tick_wood") is None


def test_moi_lua_chon_hop_le_deu_giu_nguyen():
    for effect, keys in HOOK_EFFECT_SOUNDS.items():
        for k in keys:
            got = resolve_effect_sfx(effect, k)
            assert got and os.path.basename(got) == HOOK_REEL_SOUNDS[k], (
                f"{effect}/{k} bị đổi thành {os.path.basename(got or '')}"
            )


# ── Nhịp điệu: tiếng không được lấn sang lời thoại ───────────────────────────
def test_tran_am_bi_chan_lai_trong_cua_so_hieu_ung():
    """Tiếng mở màn là ĐIỂM NHẤN, không phải nền nhạc: được ngân thêm HOOK_SFX_TAIL giây
    qua mốc kết thúc hiệu ứng, không hơn.

    Không có trần này thì ambient_mystic (19.7s) phủ gần 17 giây lên lời dẫn của cảnh 1.
    """
    qua_dai = []
    for effect, keys in HOOK_EFFECT_SOUNDS.items():
        window = HOOK_EFFECTS[effect]["duration"]
        tran = hook_sfx_max_dur(window)
        assert tran <= window + HOOK_SFX_TAIL + 1e-9, f"{effect}: trần vượt cửa sổ + đuôi"
        for k in keys:
            d = _sfx_duration(os.path.join(SFX_DIR, HOOK_REEL_SOUNDS[k]))
            if d and d > tran:
                qua_dai.append(f"{effect}/{k} {d:.1f}s > trần {tran:.1f}s")
    # Dài hơn trần là BÌNH THƯỜNG — miễn là có trần để cắt. Test này chốt rằng trần
    # tồn tại và đúng công thức; danh sách dưới đây chỉ để biết cái nào đang bị cắt.
    print(f"    (bị cắt bởi trần: {qua_dai or 'không có'})")


def test_moi_tieng_hieu_ung_deu_duoc_dat_tran():
    """Chốt ở tầng MÃ NGUỒN: mọi lần đặt tiếng hiệu ứng vào timeline phải có max_dur
    (phần tử thứ 5). Thiếu nó là tiếng chạy tự do tới hết file."""
    with open(_VIDEO_SERVICE, encoding="utf-8") as f:
        code = f.read()
    thieu = []
    for m in re.finditer(r"audio_placements\.append\(\(\s*([a-z_]+_sfx|reel)\b(.*?)\)\)", code, re.S):
        ten, phan_con_lai = m.group(1), m.group(2)
        # Tiếng gõ lặp theo nhịp (tick từng chữ) vốn đã ngắn và lặp — không tính.
        if ten == "tick_sfx":
            continue
        if "hook_sfx_max_dur" not in phan_con_lai and "HOOK_NARRATION_LEAD" not in phan_con_lai \
                and "hook_dur" not in phan_con_lai and "outro_duration *" not in phan_con_lai:
            thieu.append(ten + phan_con_lai.strip()[:60])
    assert not thieu, "tiếng hiệu ứng không có trần độ dài:\n  " + "\n  ".join(thieu)



# ── Cân bằng âm lượng ────────────────────────────────────────────────────────
def test_moi_tieng_deu_co_he_so_can_bang():
    """Thiếu hệ số = tiếng đó phát ở mức thô của file, lệch hẳn so với phần còn lại."""
    from services.video_service import HOOK_SFX_GAIN

    thieu = sorted(set(HOOK_REEL_SOUNDS) - set(HOOK_SFX_GAIN))
    assert not thieu, f"chưa có hệ số cân bằng cho: {thieu}"


def test_am_luong_can_bang_khong_con_lech_qua_muc():
    """LỖI CŨ: file gốc lệch 27.7 dB RMS, cộng thêm hệ số gõ tay mỗi nhánh một kiểu
    (×3.0 cho impact, ×0.13 hiệu dụng cho arcade...) → đỉnh sau khi nhân trải từ 0.25
    tới 2.56, tiếng to nhất gấp 10 LẦN tiếng nhỏ nhất."""
    import numpy as np
    import sys as _s
    _s.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    from fit_hook_sfx import _decode
    from services.video_service import HOOK_SFX_GAIN

    levels = {}
    for k, f in HOOK_REEL_SOUNDS.items():
        x = _decode(os.path.join(SFX_DIR, f))
        rms = 20 * np.log10(float(np.sqrt(np.mean(x ** 2))) + 1e-12)
        levels[k] = rms + 20 * np.log10(HOOK_SFX_GAIN[k])

    spread = max(levels.values()) - min(levels.values())
    assert spread <= 12.0, (
        f"chênh lệch âm lượng {spread:.1f} dB, quá lớn: "
        + ", ".join(f"{k}={v:.0f}dB" for k, v in sorted(levels.items(), key=lambda kv: kv[1]))
    )


def test_thanh_truot_nguoi_dung_khong_the_lam_sfx_lan_giong():
    from services.video_service import hook_sfx_level, HOOK_SFX_CEILING

    for k in HOOK_REEL_SOUNDS:
        assert hook_sfx_level(k, 2.0) <= HOOK_SFX_CEILING + 1e-9


def test_tieng_phu_tro_khong_muon_he_so_cua_tieng_khac():
    """ding/tick/whoosh là file CỐ ĐỊNH. Nếu chúng lấy hệ số theo lựa chọn của người
    dùng thì chọn arcade_8bit (hệ số 0.13) sẽ làm tắt ngóm chúng."""
    from services.video_service import HOOK_SFX_GAIN

    for k in ("_ding", "_tick", "_whoosh"):
        assert k in HOOK_SFX_GAIN, f"thiếu hệ số riêng cho tiếng phụ trợ {k}"


def test_khong_con_he_so_go_tay_trong_nhanh_hieu_ung():
    """Mỗi nhánh nhân một hằng số riêng chính là cách 20 dB chênh lệch len vào."""
    with open(_VIDEO_SERVICE, encoding="utf-8") as f:
        code = "\n".join(
            line for line in f.read().splitlines() if not line.strip().startswith("#")
        )
    con = re.findall(r"min\([\d.]+,\s*(?:effective_volume|outro_sfx_volume)", code)
    assert not con, f"còn {len(con)} hệ số âm lượng gõ tay, phải dùng hook_sfx_level()"


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
