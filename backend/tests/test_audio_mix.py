"""
Test hồi quy cho _mix_audio_tracks — tầng trộn audio bằng numpy của video_service.

Chạy:  python tests/test_audio_mix.py     (từ thư mục backend/, không cần pytest)
       pytest tests/test_audio_mix.py     (nếu có pytest thì cũng chạy được y hệt)

VÌ SAO CÓ FILE NÀY: mọi lỗi ở tầng trộn đều là lỗi CÂM — video vẫn render xong, vẫn
phát được, chỉ là âm lượng sai. Không có test thì cách duy nhất để phát hiện là ngồi
nghe lại từng bản render, và những gì đã lọt lưới theo đúng kiểu đó:
  1. `master /= peak` kéo tụt giọng đọc toàn video chỉ vì một đỉnh SFX ở giây thứ 2;
  2. SFX dài tràn sang phần lời dẫn khi thiếu max_dur;
  3. đệm 1 giây cuối lọt ra ngoài, mọi video thừa một giây câm.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import soundfile as sf

from services.video_service import _mix_audio_tracks

SR = 44100
_TMP = tempfile.mkdtemp(prefix="avm_audio_test_")


def _wav(name: str, seconds: float, amplitude: float = 1.0, sr: int = SR) -> str:
    """Ghi ra một file WAV hằng số biên độ để kiểm tra mức âm lượng cho dễ đoán."""
    path = os.path.join(_TMP, name)
    data = np.full((max(1, int(seconds * sr)), 2), amplitude, dtype=np.float32)
    sf.write(path, data, sr)
    return path


def _array(clip) -> np.ndarray:
    return np.asarray(clip.to_soundarray(fps=SR), dtype=np.float32)


# ── Limiter mềm ──────────────────────────────────────────────────────────────
def test_limiter_giu_nguyen_am_luong_giong_doc():
    """Đỉnh SFX ở đầu video KHÔNG được phép làm bé tiếng phần giọng đọc phía sau.

    Đây là bản chất của lỗi cũ: chuẩn hoá theo đỉnh toàn cục chia cả track cho 3,
    nên nghe như 'video tự nhiên bé tiếng' ở đoạn chẳng liên quan gì tới SFX.
    """
    voice = _wav("voice.wav", 3.0, 0.5)
    sfx = _wav("sfx_loud.wav", 0.5, 1.0)

    arr = _array(_mix_audio_tracks(
        [(voice, 0.0, 1.0, 0.0), (sfx, 0.0, 2.5, 0.0)], 3.0
    ))

    tail = arr[int(SR * 1.5):]  # đoạn chỉ còn giọng đọc
    assert abs(float(np.mean(np.abs(tail))) - 0.5) < 1e-4, (
        f"giọng đọc bị đổi âm lượng: {float(np.mean(np.abs(tail))):.4f} (phải là 0.5)"
    )


def test_limiter_khong_bao_gio_cham_tran():
    """Dù cộng dồn tới biên độ 5.0, đầu ra vẫn phải nằm dưới 0 dBFS (không vỡ tiếng)."""
    sfx = _wav("sfx_huge.wav", 1.0, 1.0)

    arr = _array(_mix_audio_tracks(
        [(sfx, 0.0, 2.5, 0.0), (sfx, 0.0, 2.5, 0.0)], 1.0
    ))

    assert float(np.max(np.abs(arr))) < 1.0, "đầu ra chạm/vượt 0 dBFS → encoder sẽ rè"


def test_tin_hieu_duoi_nguong_khong_bi_dung_toi():
    """Không có gì vượt ngưỡng thì track phải đi qua limiter nguyên vẹn từng mẫu."""
    voice = _wav("voice_quiet.wav", 2.0, 0.4)

    arr = _array(_mix_audio_tracks([(voice, 0.0, 1.0, 0.0)], 2.0))

    assert np.allclose(np.abs(arr), 0.4, atol=1e-4), "tín hiệu nhỏ bị limiter đụng vào"


# ── max_dur: chốt chặn SFX tràn sang phần lời dẫn ────────────────────────────
def test_max_dur_cat_dung_do_dai():
    """Tuple 5 phần tử phải cắt cứng SFX, phần sau mốc cắt là im lặng tuyệt đối."""
    long_sfx = _wav("sfx_long.wav", 5.0, 0.5)

    arr = _array(_mix_audio_tracks([(long_sfx, 0.0, 1.0, 0.0, 1.0)], 5.0))

    assert float(np.max(np.abs(arr[int(SR * 1.2):]))) == 0.0, "SFX tràn qua mốc max_dur"
    assert float(np.max(np.abs(arr[: int(SR * 0.5)]))) > 0.4, "phần trước mốc cắt bị mất"


def test_max_dur_co_got_mem_chong_tieng_pac():
    """40ms cuối phải được vuốt nhỏ dần, nếu không chỗ cắt kêu 'pắc'."""
    long_sfx = _wav("sfx_long2.wav", 5.0, 0.5)

    arr = _array(_mix_audio_tracks([(long_sfx, 0.0, 1.0, 0.0, 1.0)], 5.0))

    tai_moc_cat = float(np.max(np.abs(arr[int(SR * 0.995): int(SR * 1.0)])))
    assert tai_moc_cat < 0.1, f"cắt cụt không có fade (biên độ còn {tai_moc_cat:.3f})"


def test_tuple_4_phan_tu_van_chay():
    """Placement kiểu cũ (không có max_dur) phải tiếp tục hoạt động y như trước."""
    sfx = _wav("sfx_old.wav", 1.0, 0.5)

    arr = _array(_mix_audio_tracks([(sfx, 0.0, 1.0, 0.0)], 1.0))

    assert float(np.max(np.abs(arr))) > 0.4


def test_sfx_cuc_ngan_va_max_dur_lon_hon_file():
    """tick.wav dài 0.05s với max_dur 1.02s (đúng tình huống hook typewriter): không
    được ném IndexError/ValueError, chỉ đơn giản là không cắt gì cả."""
    tick = _wav("tick.wav", 0.05, 0.8)

    placements = [(tick, i * 0.1, 1.0, 0.0, 1.02) for i in range(10)]
    arr = _array(_mix_audio_tracks(placements, 2.0))

    assert float(np.max(np.abs(arr))) > 0.5, "chuỗi tick bị mất"


def test_bo_qua_file_hong_khong_lam_chet_job():
    """File không đọc được phải bị bỏ qua kèm cảnh báo, các track còn lại vẫn trộn."""
    good = _wav("good.wav", 1.0, 0.5)
    broken = os.path.join(_TMP, "broken.wav")
    with open(broken, "wb") as f:
        f.write(b"day khong phai file wav")

    arr = _array(_mix_audio_tracks([(broken, 0.0, 1.0, 0.0), (good, 0.0, 1.0, 0.0)], 1.0))

    assert float(np.max(np.abs(arr))) > 0.4


def test_khong_tra_ve_phan_dem_1_giay():
    """Đệm an toàn 1s dùng để tính toán, KHÔNG được lọt ra ngoài — nếu lọt thì mọi
    video đều thừa đúng một giây câm ở cuối."""
    sfx = _wav("sfx_short.wav", 0.5, 0.5)

    clip = _mix_audio_tracks([(sfx, 0.0, 1.0, 0.0)], 3.0)

    assert abs(clip.duration - 3.0) < 0.01, f"độ dài audio {clip.duration}s, phải là 3.0s"


def test_khong_co_track_nao_thi_tra_ve_none():
    """Danh sách rỗng → None, để caller biết là video không có audio."""
    assert _mix_audio_tracks([], 3.0) is None


# ── SCENE_SFX_GAIN: cân bằng âm lượng 13 SFX per-scene ───────────────────────
def test_moi_scene_sfx_deu_tro_toi_file_co_that():
    from config import SFX_DIR
    from services.video_service import SCENE_SFX_GAIN

    thieu = [
        name for name in SCENE_SFX_GAIN
        if not os.path.isfile(os.path.join(SFX_DIR, f"{name}.wav"))
    ]
    assert not thieu, f"SCENE_SFX_GAIN khai báo nhưng không có file: {thieu}"


def test_scene_sfx_can_bang_am_luong():
    """LỖI CŨ: 13 SFX per-scene (whoosh/pop/tick/ding/bell/shimmer/riser/bass_drop/
    impact/suspense/heartbeat/laugh/swoosh_soft) đều nhân đúng một công thức phẳng —
    đo bằng ffmpeg volumedetect thấy chênh 33.7 dB (shimmer.wav -42dB vs suspense.wav
    -8.3dB), cùng thanh trượt âm lượng mà tiếng gần như câm, tiếng thì chói hẳn.

    shimmer.wav là NGOẠI LỆ CÓ CHỦ Ý (xem chú thích SCENE_SFX_GAIN) — trần gain 3.5x
    thay vì khuếch đại đúng 10x theo RMS, vì file gần như toàn im lặng với một cú lấp
    lánh ngắn (max_volume chỉ -4.5dB): khuếch đại đúng theo RMS sẽ biến hiệu ứng tinh tế
    này thành một tiếng chói ngay khung hình nó vang lên. Tách riêng để không bắt nhầm
    lỗi khi so các SFX còn lại.
    """
    import sys as _s
    _s.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    from fit_hook_sfx import _decode
    from config import SFX_DIR
    from services.video_service import SCENE_SFX_GAIN

    levels = {}
    for name, gain in SCENE_SFX_GAIN.items():
        x = _decode(os.path.join(SFX_DIR, f"{name}.wav"))
        rms = 20 * np.log10(float(np.sqrt(np.mean(x ** 2))) + 1e-12)
        levels[name] = rms + 20 * np.log10(gain)

    thuong = {k: v for k, v in levels.items() if k != "shimmer"}
    spread = max(thuong.values()) - min(thuong.values())
    # Trần 5dB, không phải 0: gain trong SCENE_SFX_GAIN tính từ `ffmpeg volumedetect`,
    # còn RMS ở đây tính bằng numpy sau khi `_decode` giải mã lại 44.1kHz mono — hai
    # đường đo cho số hơi khác nhau (đo thật: full 2.3dB), không phải sai số bằng 0.
    # 5dB vẫn xa dưới trần 12dB mà test_hook_sfx.py chấp nhận cho nhóm hook/outro.
    assert spread <= 5.0, (
        f"chênh lệch âm lượng {spread:.1f} dB giữa các SFX thường (trừ shimmer): "
        + ", ".join(f"{k}={v:.1f}dB" for k, v in sorted(thuong.items(), key=lambda kv: kv[1]))
    )

    # shimmer được PHÉP êm hơn phần còn lại (trần gain có chủ ý), nhưng phải nằm trong
    # khoảng dự kiến — bắt lỗi nếu ai đó đổi file shimmer.wav sang bản khác mà quên
    # tính lại gain, khiến nó lại rơi về gần-câm hoặc bất ngờ chói lên.
    assert -35.0 <= levels["shimmer"] <= -25.0, (
        f"shimmer lệch khỏi khoảng dự kiến (-35..-25 dB): {levels['shimmer']:.1f} dB — "
        "có thể file đã đổi, cần tính lại gain trong SCENE_SFX_GAIN"
    )


if __name__ == "__main__":
    # Chạy trực tiếp bằng python.exe thì stdout là cp1252 và mọi dòng kết quả có dấu
    # tiếng Việt sẽ ném UnicodeEncodeError — xem services/log_setup.py.
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
