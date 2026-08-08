"""
Test cho filtergraph âm thanh của bước master (audio_mix_service).

Chạy:  python tests/test_audio_filtergraph.py    (từ thư mục backend/)
       pytest tests/test_audio_filtergraph.py

VÌ SAO KHÔNG TEST BẰNG RENDER THẬT: một job render đầy đủ cần quota Gemini + vài phút
encode, và khi nó ra sai thì triệu chứng là "nghe hơi lạ" — không ai dựng lại được. Ở đây
ta chặn `subprocess.run`, đọc thẳng chuỗi `-filter_complex` mà FFmpeg SẼ nhận, rồi khẳng
định trên đó. Chạy trong vài mili giây và nói chính xác cái gì sai.

Ba lỗi thật mà bộ test này canh:
  1. `amix` mặc định normalize=1 → CHIA biên độ cho số input. Bật nhạc mở màn làm nhạc
     nền cả video tụt 6dB so với khi tắt; loudnorm chuẩn hoá tổng nên không lộ ở âm lượng
     chung, chỉ TỈ LỆ nhạc/giọng đổi — nghe ra nhưng không ai lần ra nguyên nhân.
  2. Điều kiện `-map` dùng `has_bgm` thay vì `bgm_stream` → video chỉ có nhạc mở màn
     (không giọng) ra CÂM HOÀN TOÀN, không một dòng lỗi.
  3. Sidechain ducking lấy track đã trộn lẫn SFX làm tín hiệu điều khiển → mỗi tiếng
     whoosh/impact tự dìm nhạc nền y như giọng nói.
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import audio_mix_service as ams


class _Captured(Exception):
    """Thoát khỏi master_audio_and_export ngay khi đã tóm được lệnh."""

    def __init__(self, cmd):
        self.cmd = cmd


def _build_cmd(**kwargs) -> list:
    """Dựng lệnh FFmpeg mà master_audio_and_export SẼ chạy, không thật sự chạy nó."""
    tmp = tempfile.mkdtemp(prefix="avm_fg_")
    video = os.path.join(tmp, "raw.mp4")
    open(video, "wb").write(b"\0" * 32)

    def _fake_run(cmd, *a, **kw):
        raise _Captured(cmd)

    # PHẢI lấy ra TRƯỚC lời gọi: nhét vào lambda thì nó chỉ chạy lúc _has_audio_stream
    # được gọi — tức sau khi **kwargs đã bung, và "_has_voice" lọt vào hàm thật.
    has_voice = kwargs.pop("_has_voice", True)

    orig = (ams.subprocess.run, ams._has_audio_stream, ams._probe_width, ams._has_nvenc)
    ams.subprocess.run = _fake_run
    ams._has_audio_stream = lambda p: has_voice
    ams._probe_width = lambda p: 0          # tắt thanh tiến trình cho gọn
    ams._has_nvenc = lambda: False
    try:
        ams.master_audio_and_export(
            input_video_path=video,
            output_path=os.path.join(tmp, "out.mp4"),
            progress_bar=False,
            **kwargs,
        )
    except _Captured as c:
        return c.cmd
    finally:
        (ams.subprocess.run, ams._has_audio_stream, ams._probe_width, ams._has_nvenc) = orig
    raise AssertionError("không tóm được lệnh FFmpeg")


def _fg(cmd: list) -> str:
    return cmd[cmd.index("-filter_complex") + 1] if "-filter_complex" in cmd else ""


def _audio_file(dirpath: str, name: str) -> str:
    p = os.path.join(dirpath, name)
    open(p, "wb").write(b"\0" * 1024)
    return p


def _tmpdir() -> str:
    return tempfile.mkdtemp(prefix="avm_fg_src_")


# ── amix không được tự chia biên độ ──────────────────────────────────────────
def test_moi_amix_deu_tat_normalize():
    """LỖI CŨ: amix mặc định chia biên độ cho số input, bóp cả giọng lẫn nhạc còn một nửa."""
    d = _tmpdir()
    for ducking in (True, False):
        fg = _fg(_build_cmd(bgm_path=_audio_file(d, "main.mp3"), use_audio_ducking=ducking))
        for chunk in fg.split(";"):
            if "amix=" in chunk:
                assert "normalize=0" in chunk, f"amix thiếu normalize=0: {chunk}"


# ── Chuyển tông Intro BGM ────────────────────────────────────────────────────
def test_intro_va_main_dung_acrossfade():
    """afade+amix tạo chỗ trũng âm lượng giữa crossfade VÀ làm nhạc chính trôi mất T giây
    đầu. acrossfade giữ năng lượng phẳng và cho nhạc chính vào từ giây 0 của nó."""
    d = _tmpdir()
    fg = _fg(_build_cmd(
        bgm_path=_audio_file(d, "main.mp3"),
        intro_bgm_path=_audio_file(d, "intro.mp3"),
        intro_bgm_duration=8.0,
    ))
    assert "acrossfade" in fg, "không dùng acrossfade"
    assert "atrim=0:8.000" in fg, "phải cắt nhạc intro về đúng T giây trước khi crossfade"


def test_intro_ngan_hon_fade_khong_sinh_fade_am():
    """intro 1 giây thì fade phải co lại còn 0.5s, không được là 2s (âm st)."""
    d = _tmpdir()
    fg = _fg(_build_cmd(
        bgm_path=_audio_file(d, "main.mp3"),
        intro_bgm_path=_audio_file(d, "intro.mp3"),
        intro_bgm_duration=1.0,
    ))
    assert "acrossfade=d=0.500" in fg, f"fade không co lại theo intro ngắn: {fg}"


def test_chi_co_intro_bgm_van_ra_tieng():
    """LỖI CŨ: điều kiện -map dùng `has_bgm` nên trường hợp CHỈ có nhạc mở màn dựng đủ
    [audio_master] nhưng không map — video ra câm hoàn toàn, không lỗi nào."""
    d = _tmpdir()
    cmd = _build_cmd(
        intro_bgm_path=_audio_file(d, "intro.mp3"),
        intro_bgm_duration=5.0,
        _has_voice=False,
    )
    assert "[audio_master]" in cmd, "quên map track âm thanh → video câm"


def test_khong_co_bgm_nao_thi_khong_dung_toi_bgm_filter():
    fg = _fg(_build_cmd())
    assert "acrossfade" not in fg and "bgm_eq" not in fg


# ── Sidechain ducking ────────────────────────────────────────────────────────
def test_ducking_uu_tien_track_chi_giong():
    """Có track chỉ-giọng thì phải dùng nó làm tín hiệu điều khiển, KHÔNG tách đôi track
    đã trộn — nếu không, mỗi tiếng SFX lại tự dìm nhạc nền."""
    d = _tmpdir()
    fg = _fg(_build_cmd(
        bgm_path=_audio_file(d, "main.mp3"),
        sidechain_audio_path=_audio_file(d, "voice.wav"),
        use_audio_ducking=True,
    ))
    assert "[sc_key]" in fg, "không dùng track sidechain riêng"
    assert "asplit" not in fg, "vẫn tách đôi track đã trộn dù đã có track chỉ-giọng"


def test_ducking_khong_co_track_rieng_thi_tach_doi():
    """Thiếu track chỉ-giọng vẫn phải ducking được — kém hơn, nhưng không được tắt hẳn."""
    d = _tmpdir()
    fg = _fg(_build_cmd(bgm_path=_audio_file(d, "main.mp3"), use_audio_ducking=True))
    assert "asplit=2" in fg and "sidechaincompress" in fg


def test_release_du_dai_de_khong_phong_trong_khoang_lang_giua_canh():
    """LỖI CŨ: release=350ms gần đúng bằng khoảng lặng 0.45s cố định mà TTS chèn giữa
    MỌI cặp cảnh — nhạc nền kịp "phồng" gần hết biên độ trong đúng khoảng lặng đó rồi bị
    đè xuống ngay khi câu sau bắt đầu, lặp lại y hệt ở TẤT CẢ điểm chuyển cảnh trong cả
    video (đo trên video thật 12 cảnh: cả 11 điểm nối đều lặng đúng 0.45s). Đo bằng cách
    render thật với release=350 vs 650: 650 cho mức BGM trong khoảng lặng thấp hơn rõ rệt
    (3-4dB) — chốt lại yêu cầu release phải VƯỢT khoảng lặng 0.45s để không hồi kịp trong
    đúng cửa sổ đó, nhưng không quá 1000ms (nhạc không kịp nổi lên ở khoảng nghỉ dài, nghe
    như tắt hẳn suốt đoạn thoại — lỗi NGƯỢC đã gặp trước khi hạ xuống 350ms)."""
    import re

    d = _tmpdir()
    fg = _fg(_build_cmd(
        bgm_path=_audio_file(d, "main.mp3"),
        sidechain_audio_path=_audio_file(d, "voice.wav"),
        use_audio_ducking=True,
    ))
    m = re.search(r"sidechaincompress=[^\[]*?release=(\d+)", fg)
    assert m, "không tìm thấy release= trong sidechaincompress"
    release_ms = int(m.group(1))
    assert 450 < release_ms <= 1000, (
        f"release={release_ms}ms — phải > 450ms (khoảng lặng cố định giữa cảnh) để không "
        f"hồi kịp trong đúng cửa sổ đó, và <= 1000ms để không tắt nhạc suốt đoạn thoại"
    )


def test_tat_ducking_thi_khong_co_sidechain():
    d = _tmpdir()
    fg = _fg(_build_cmd(
        bgm_path=_audio_file(d, "main.mp3"),
        sidechain_audio_path=_audio_file(d, "voice.wav"),
        use_audio_ducking=False,
    ))
    assert "sidechaincompress" not in fg


def test_track_sidechain_khong_bi_phat_ra_loa():
    """Nó chỉ là tín hiệu điều khiển. Lọt vào amix là giọng đọc vang lên hai lần."""
    d = _tmpdir()
    sc = _audio_file(d, "voice.wav")
    fg = _fg(_build_cmd(
        bgm_path=_audio_file(d, "main.mp3"), sidechain_audio_path=sc, use_audio_ducking=True,
    ))
    mix_chunks = [c for c in fg.split(";") if "amix=" in c]
    assert mix_chunks, "không có bước trộn nào"
    for c in mix_chunks:
        assert "[sc_key]" not in c, f"track điều khiển bị đưa vào bản trộn: {c}"


def test_thu_tu_input_sidechain_dung_khi_co_du_ca_hai_bgm():
    """Index stream phải đếm đúng: video=0, main=1, intro=2, sidechain=3. Lệch một bậc là
    FFmpeg lấy nhầm nhạc nền làm tín hiệu điều khiển."""
    d = _tmpdir()
    fg = _fg(_build_cmd(
        bgm_path=_audio_file(d, "main.mp3"),
        intro_bgm_path=_audio_file(d, "intro.mp3"),
        intro_bgm_duration=5.0,
        sidechain_audio_path=_audio_file(d, "voice.wav"),
        use_audio_ducking=True,
    ))
    assert "[3:a]" in fg, f"sidechain phải là input số 3: {fg}"


# ── Dấu đóng bản quyền: logo + chữ ───────────────────────────────────────────
# LỖI THẬT ĐÃ VÁ: logo (120px ở y=40 → chiếm 40..160) và chữ (fontsize 56 ở y=100 →
# chiếm 100..156) được đặt bằng hai con số gõ tay rời nhau, nên bật CẢ HAI thì chữ chạy
# xuyên qua logo. Không test nào bắt được vì mỗi thứ riêng lẻ đều trông đúng.
_LOGO_THAT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "watermarks", "logo_ntd.png",
)


def _hinh_hoc_logo(fg: str) -> tuple:
    """(box, alpha, y_dinh) của lớp logo trong filtergraph."""
    sc = re.search(r"scale=(\d+):(\d+):force_original_aspect_ratio=decrease", fg)
    aa = re.search(r"colorchannelmixer=aa=([\d.]+)\[wm_logo\]", fg)
    ov = re.search(r"\[wm_logo\]overlay=W-w-(\d+):(\d+)\[v_wm_logo\]", fg)
    assert sc and aa and ov, f"không đọc được lớp logo: {fg}"
    return int(sc.group(1)), float(aa.group(1)), int(ov.group(2))


def _y_chu(fg: str) -> int:
    m = re.search(r"drawtext=[^;]*?:y=(\d+)", fg)
    assert m, f"không tìm thấy drawtext: {fg}"
    return int(m.group(1))


def test_chu_watermark_khong_chong_len_logo():
    """Bật cả logo và chữ thì chữ phải nằm HOÀN TOÀN dưới đáy logo."""
    fg = _fg(_build_cmd(watermark_text="@artciphers", watermark_logo=_LOGO_THAT))
    box, _, y_logo = _hinh_hoc_logo(fg)
    day_logo = y_logo + box   # force_original_aspect_ratio=decrease → cao luôn ≤ box
    assert _y_chu(fg) >= day_logo, (
        f"chữ ở y={_y_chu(fg)} nhưng logo kéo tới y={day_logo} — chồng lên nhau."
    )


def test_chi_co_chu_thi_khong_doi_bo_cuc_cu():
    """Không bật logo thì chữ phải ở ĐÚNG chỗ cũ — đừng đổi bố cục video của người chỉ
    dùng chữ, chỉ vì tính năng logo được thêm vào."""
    fg = _fg(_build_cmd(watermark_text="@artciphers"))
    assert _y_chu(fg) == ams.WATERMARK_TEXT_Y_SOLO == 100
    assert "[wm_logo]" not in fg


def test_logo_co_vao_trong_khung_vuong():
    """`scale=W:-1` để logo ngang bẹt cao hơn khung tính toán → chữ lại chồng lên logo.
    force_original_aspect_ratio=decrease chốt chiều cao ≤ box với MỌI tỉ lệ logo."""
    fg = _fg(_build_cmd(watermark_logo=_LOGO_THAT))
    box, alpha, _ = _hinh_hoc_logo(fg)
    assert box == ams.WATERMARK_LOGO_BOX
    assert alpha == ams.WATERMARK_LOGO_ALPHA
    # 120px @ 0.45 là bản cũ, gần như vô hình trên màn điện thoại.
    assert box >= 160 and alpha >= 0.6, f"logo bị hạ lại quá nhỏ/quá mờ: {box}px @ {alpha}"


def test_logo_khong_ton_tai_thi_bo_qua_khong_lam_chet_lenh():
    """Đường dẫn logo sai không được làm vỡ filtergraph — chỉ đơn giản là không có logo."""
    fg = _fg(_build_cmd(watermark_text="@x", watermark_logo=r"C:\khong\ton\tai.png"))
    assert "[wm_logo]" not in fg
    # và chữ quay về chỗ của trường hợp chỉ-có-chữ
    assert _y_chu(fg) == ams.WATERMARK_TEXT_Y_SOLO


# ── Đầu ra ───────────────────────────────────────────────────────────────────
def test_luon_ep_ve_48khz():
    """loudnorm động tự nâng nội bộ lên 192kHz và giữ nguyên ở đầu ra; AAC không hỗ trợ
    nên rơi xuống 96kHz — phình luồng audio mà không thêm chút thông tin nào."""
    d = _tmpdir()
    fg = _fg(_build_cmd(bgm_path=_audio_file(d, "main.mp3")))
    assert f"aresample={ams.OUTPUT_AUDIO_RATE}" in fg


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
