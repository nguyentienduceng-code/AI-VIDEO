"""
Test cho ffmpeg_assembler — ĐƯỜNG RENDER MẶC ĐỊNH của dự án (use_fast_assembly=True).

Chạy:  python tests/test_ffmpeg_assembler.py    (từ thư mục backend/)
       pytest tests/test_ffmpeg_assembler.py

VÌ SAO PHẢI CÓ: module này ghép cả timeline bằng MỘT lệnh FFmpeg và nhanh hơn MoviePy
khoảng 100 lần (19 cảnh: 15-20 giây so với 30-45 phút). Nhưng khi nó hỏng, render_final_video
BẮT exception rồi lặng lẽ quay về MoviePy — job vẫn báo "Hoàn tất!", chỉ chậm gấp trăm lần.
Dấu vết duy nhất là một dòng log. Nghĩa là module quan trọng nhất về tốc độ lại là module
hỏng êm nhất, và trước bộ test này nó KHÔNG có test nào.

Sự cố thật đang canh: bản thêm Outro thay số học đánh index input bằng `len(cmd) // 2`.
Công thức đó ngầm giả định `cmd` mở đầu bằng đúng MỘT phần tử trước các cặp "-i <path>",
trong khi nó là [ffmpeg, "-y"] — hai. Lệch +1 ở mọi số cảnh, FFmpeg chết ngay lúc phân
tích tham số ("Invalid input file index: 2"), và MỌI render kể từ đó đi đường chậm.

Test xương sống ở đây là test_moi_index_deu_tro_vao_input_co_that: nó không quan tâm ai
tính index bằng cách gì, chỉ khẳng định mọi tham chiếu đều nằm trong số input thật.
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import ffmpeg_assembler as fa


class _Captured(Exception):
    def __init__(self, cmd):
        self.cmd = cmd


def _scene(d: str, i: int, **extra) -> dict:
    p = os.path.join(d, f"scene_{i}.mp4")
    with open(p, "wb") as f:
        f.write(b"\0" * 64)
    return {
        "image_path": p,
        "start_time": float(i) * 3.0,
        "duration": 3.0,
        "highlight_text": extra.pop("highlight_text", ""),
        **extra,
    }


def _build_cmd(n_scenes: int = 2, hook: bool = False, outro: bool = False,
               audio: bool = True, **kwargs) -> list:
    """Dựng lệnh FFmpeg mà assemble() SẼ chạy, không thật sự chạy nó."""
    d = tempfile.mkdtemp(prefix="avm_fa_")
    scenes = [_scene(d, i) for i in range(n_scenes)]

    def _extra(name):
        p = os.path.join(d, name)
        with open(p, "wb") as f:
            f.write(b"\0" * 64)
        return p

    def _fake_run(cmd, *a, **kw):
        raise _Captured(cmd)

    orig_run, orig_nvenc = fa.subprocess.run, fa._has_nvenc
    fa.subprocess.run = _fake_run
    fa._has_nvenc = lambda: False
    try:
        fa.assemble(
            scenes, os.path.join(d, "out.mp4"),
            width=1080, height=1920,
            audio_path=_extra("mix.wav") if audio else None,
            hook_video=_extra("hook.mp4") if hook else None,
            hook_duration=2.0 if hook else 0.0,
            outro_video=_extra("outro.mp4") if outro else None,
            outro_start=float(n_scenes) * 3.0 if outro else 0.0,
            outro_duration=2.0 if outro else 0.0,
            **kwargs,
        )
    except _Captured as c:
        return c.cmd
    finally:
        fa.subprocess.run, fa._has_nvenc = orig_run, orig_nvenc
    raise AssertionError("không tóm được lệnh FFmpeg")


def _n_inputs(cmd: list) -> int:
    return sum(1 for x in cmd if x == "-i")


def _referenced_indices(cmd: list) -> set:
    """Mọi chỉ số input mà filtergraph và -map nhắc tới."""
    idx = set()
    if "-filter_complex" in cmd:
        fg = cmd[cmd.index("-filter_complex") + 1]
        idx |= {int(m) for m in re.findall(r"\[(\d+):[av]\]", fg)}
    for i, x in enumerate(cmd):
        if x == "-map" and i + 1 < len(cmd):
            m = re.fullmatch(r"\[?(\d+):[av]\]?", cmd[i + 1])
            if m:
                idx.add(int(m.group(1)))
    return idx


# ── Bất biến xương sống ──────────────────────────────────────────────────────
def test_moi_index_deu_tro_vao_input_co_that():
    """LỖI CŨ: `len(cmd)//2` cho index lệch +1 → 'Invalid input file index'.

    Test này không quan tâm index được tính bằng công thức nào, chỉ đòi mọi tham chiếu
    phải nằm trong số input thật — nên nó bắt được mọi cách tính sai, kể cả cách chưa
    ai nghĩ ra. Quét đủ 8 tổ hợp hook × outro × audio, ở nhiều số cảnh.
    """
    for n in (1, 2, 5):
        for hook in (False, True):
            for outro in (False, True):
                for audio in (False, True):
                    cmd = _build_cmd(n, hook=hook, outro=outro, audio=audio)
                    tong = _n_inputs(cmd)
                    dung_toi = _referenced_indices(cmd)
                    qua = sorted(i for i in dung_toi if i >= tong)
                    assert not qua, (
                        f"n={n} hook={hook} outro={outro} audio={audio}: "
                        f"có {tong} input nhưng lệnh trỏ tới index {qua}"
                    )


def test_so_input_dung_bang_so_thanh_phan():
    """Thừa/thiếu một input là mọi index phía sau lệch theo."""
    for n in (1, 4):
        for hook in (False, True):
            for outro in (False, True):
                for audio in (False, True):
                    cmd = _build_cmd(n, hook=hook, outro=outro, audio=audio)
                    assert _n_inputs(cmd) == n + int(hook) + int(outro) + int(audio)


# ── Từng thành phần trỏ đúng chỗ ─────────────────────────────────────────────
def test_audio_map_tro_vao_dung_file_tieng():
    """Đây chính là dòng đã làm gãy đường nhanh: -map '2:a' khi chỉ có 2 input."""
    cmd = _build_cmd(n_scenes=1, hook=False, outro=False, audio=True)
    # input 0 = cảnh duy nhất, input 1 = mix.wav
    assert "-map" in cmd and "1:a" in cmd, f"map audio sai: {[c for c in cmd if ':a' in str(c)]}"


def test_thu_tu_hook_roi_outro_roi_audio():
    """Thứ tự nối input phải khớp thứ tự đánh index, nếu không hook nhận nhầm file tiếng."""
    cmd = _build_cmd(n_scenes=3, hook=True, outro=True, audio=True)
    paths = [cmd[i + 1] for i, x in enumerate(cmd) if x == "-i"]
    assert os.path.basename(paths[3]) == "hook.mp4"
    assert os.path.basename(paths[4]) == "outro.mp4"
    assert os.path.basename(paths[5]) == "mix.wav"

    fg = cmd[cmd.index("-filter_complex") + 1]
    assert "[3:v]" in fg, "hook phải là input 3"
    assert "[4:v]" in fg, "outro phải là input 4"
    assert "5:a" in " ".join(cmd), "audio phải là input 5"


def test_khong_co_tieng_thi_khong_map_audio():
    cmd = _build_cmd(n_scenes=2, audio=False)
    assert not any(re.fullmatch(r"\[?\d+:a\]?", str(x)) for x in cmd)
    assert "-c:a" not in cmd


def test_mot_canh_khong_hook_khong_outro_van_dung():
    """Trường hợp tối giản — cũng là trường hợp đã lộ ra bug."""
    cmd = _build_cmd(n_scenes=1, hook=False, outro=False, audio=True)
    assert _n_inputs(cmd) == 2
    assert max(_referenced_indices(cmd)) == 1


# ── Slack cho xfade (bug đứng hình 01/08) ────────────────────────────────────
def test_moi_canh_ngoai_canh_cuoi_co_du_khung_cho_xfade():
    """LỖI CŨ: trim mỗi cảnh đúng khít `duration`, offset của xfade cũng đúng bằng
    ngần đó — 0 giây dư cho xfade hoà trộn. Với clip tổng hợp FFmpeg vẫn chạy được,
    nhưng với clip thật (stock/Ken Burns) nó lặng lẽ drop gần hết khung hình sau đó
    (rc=0, không exception) — video ra đúng độ dài (audio ép container) nhưng hình
    đứng im từ ngay transition đầu tiên. Đo trực tiếp bằng cách render tay: nhân bản
    khung cuối cảnh thêm đúng crossfade_dur giây thì lỗi biến mất.

    Test này khẳng định MỌI cảnh trừ cảnh cuối đều được tpad thêm đúng crossfade_dur
    giây (nhân bản khung cuối) trước khi vào chuỗi xfade — cảnh cuối thì không cần,
    nó không phải vế "đầu vào" của xfade nào.
    """
    for n in (2, 5):
        cmd = _build_cmd(n_scenes=n, crossfade_dur=0.4)
        fg = cmd[cmd.index("-filter_complex") + 1]
        chains = fg.split(";")
        for i in range(n):
            chain = next(c for c in chains if c.endswith(f"[s{i}]"))
            has_pad = "tpad=stop_duration=0.400:stop_mode=clone" in chain
            if i < n - 1:
                assert has_pad, f"cảnh {i}/{n} thiếu tpad — xfade sẽ hết khung để hoà trộn"
            else:
                assert not has_pad, f"cảnh cuối {i}/{n} không cần tpad (không phải vế xfade nào)"


def test_mot_canh_duy_nhat_khong_can_tpad():
    """Chỉ 1 cảnh thì không có xfade nào cả — tpad chỉ tổ tốn thời gian encode."""
    cmd = _build_cmd(n_scenes=1)
    fg = cmd[cmd.index("-filter_complex") + 1]
    assert "tpad" not in fg


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
