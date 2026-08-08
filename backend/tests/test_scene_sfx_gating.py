"""
Test cho luật chọn/bỏ SFX per-scene — plan_scene_sfx() + scene_sfx_jitter().

Chạy:  python tests/test_scene_sfx_gating.py   (từ thư mục backend/, không cần pytest)
       pytest tests/test_scene_sfx_gating.py

VÌ SAO CÓ FILE NÀY: luật này trước đây nằm LẪN trong thân `render_final_video`, nên
không một bộ test nào chạm tới được. Hậu quả thật: một lần thay luật đã đi qua trọn bộ
110 test mà không ai hay, và bản thay thế đó vừa bỏ hẳn tiếng NHẤN ở cao trào
(impact/bass_drop) vừa giữ nguyên mật độ tiếng LẤP CHỖ — tức làm ngược đúng mục tiêu
"chống nhàm tai" mà nó tự nhận. Đo trên 32 kịch bản Gemini thật (296 cảnh) thì luật đó
còn không kích hoạt lần nào: khoảng cách SFX nhỏ nhất là 3.67s.

Cũng giống test_audio_mix.py: mọi lỗi ở tầng này đều là lỗi CÂM — video vẫn render xong,
vẫn phát được, chỉ là nghe sai. Không có test thì cách duy nhất để phát hiện là ngồi
nghe lại từng bản render.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.video_service import (
    SCENE_SFX_FILLER,
    SCENE_SFX_FILLER_MIN_GAP,
    SCENE_SFX_GAIN,
    SCENE_SFX_GAIN_JITTER,
    SCENE_SFX_PITCH_JITTER,
    SCENE_SFX_REPEAT_MIN_GAP,
    plan_scene_sfx,
    scene_sfx_jitter,
)


def test_nhom_nhan_mien_cooldown_lap_cho():
    """Tiếng NHẤN ở cao trào không được bị xoá chỉ vì một tiếng chuyển cảnh vừa vang.

    Đây chính là hồi quy đã xảy ra: 'impact' đặt có chủ đích ở cú twist bị bỏ hẳn vì
    một 'whoosh' vô thưởng vô phạt phát trước đó 1 giây.
    """
    plan = plan_scene_sfx([("whoosh", 0.0), ("impact", 1.0), ("bass_drop", 1.5)])
    assert plan == {0, 1, 2}, f"nhóm nhấn bị chặn oan: {plan}"


def test_lap_cho_qua_sat_bi_bo_han():
    """Hai tiếng lấp chỗ sát nhau: cái thứ hai BỎ HẲN, không đổi sang tên khác.

    Đổi tên chỉ xoay âm sắc mà giữ nguyên mật độ — không giảm được gì.
    """
    plan = plan_scene_sfx([("whoosh", 0.0), ("pop", 1.0)])
    assert plan == {0}, f"tiếng lấp chỗ thứ hai lẽ ra phải bị bỏ: {plan}"


def test_lap_cho_du_xa_thi_van_phat():
    plan = plan_scene_sfx([("whoosh", 0.0), ("pop", SCENE_SFX_FILLER_MIN_GAP + 0.1)])
    assert plan == {0, 1}, f"cách đủ xa mà vẫn bị chặn: {plan}"


def test_cooldown_do_tu_lan_PHAT_THAT_khong_phai_lan_duoc_gan():
    """whoosh(0.0) phát → pop(1.0) bị bỏ → tick(3.2) phải ĐƯỢC phát.

    tick cách lần phát thật gần nhất (0.0) đúng 3.2s > 3.0s. Nếu cooldown đo nhầm từ
    cảnh bị bỏ (1.0) thì tick sẽ bị chặn oan — mốc đo sai một tầng là cả chuỗi sau lệch.
    """
    plan = plan_scene_sfx([("whoosh", 0.0), ("pop", 1.0), ("tick", 3.2)])
    assert plan == {0, 2}, f"cooldown đo sai mốc: {plan}"


def test_trung_ten_qua_sat_bi_bo_ke_ca_nhom_nhan():
    """Miễn cooldown lấp chỗ KHÔNG có nghĩa là miễn luôn luật trùng tên."""
    plan = plan_scene_sfx([("impact", 0.0), ("impact", 1.0)])
    assert plan == {0}, f"cùng một file impact phát lại sau 1s: {plan}"


def test_chuoi_trung_ten_bi_chan_lien_tuc():
    """3 cảnh 'tick' cách nhau 1s: chỉ cảnh đầu được phát.

    Luật trùng tên phải so với cảnh ĐƯỢC GÁN gần nhất (kể cả bị chặn), không phải cảnh
    PHÁT gần nhất — nếu so nhầm, cảnh thứ 3 sẽ thấy mình cách cảnh 1 đúng 2.0s > 1.8s
    và lọt lưới, thành ra nghe vẫn là một nhịp trống đơn điệu.
    """
    plan = plan_scene_sfx([("tick", 0.0), ("tick", 1.0), ("tick", 2.0)])
    assert plan == {0}, f"chuỗi trùng tên lọt lưới: {plan}"


def test_sfx_user_tu_tai_len_khong_bi_vut():
    """Tên lạ (không phân loại được) mặc định là nhóm NHẤN — không tự ý vứt của user."""
    plan = plan_scene_sfx([("whoosh", 0.0), ("tieng_cua_toi", 0.5)])
    assert plan == {0, 1}, f"SFX user tự tải lên bị vứt: {plan}"


def test_file_thieu_khong_chiem_suat_cooldown():
    """Một tên gõ sai / file đã xoá không được phép chặn tiếng hợp lệ phía sau.

    whoosh(0.0) KHÔNG có file → pop(1.0) phải được phát dù chỉ cách 1s, vì thực tế
    chưa có tiếng lấp chỗ nào vang lên cả.
    """
    plan = plan_scene_sfx(
        [("whoosh", 0.0), ("pop", 1.0)],
        exists=lambda n: n != "whoosh",
    )
    assert plan == {1}, f"file thiếu vẫn chiếm suất cooldown: {plan}"


def test_canh_khong_co_sfx_khong_lam_lech_chi_so():
    """Chỉ số trả về phải khớp chỉ số CẢNH, không phải chỉ số trong danh sách đã lọc."""
    plan = plan_scene_sfx([("", 0.0), ("", 2.0), ("impact", 4.0)])
    assert plan == {2}, f"chỉ số lệch: {plan}"


def test_kich_ban_gemini_that_khong_bi_anh_huong():
    """Nhịp SFX do Gemini sinh (thưa, cách nhau ≥3.67s) phải đi qua nguyên vẹn.

    Con số 3.67s là khoảng cách NHỎ NHẤT đo được trên 32 kịch bản thật trong cache.
    Luật chống nhàm chỉ nên chạm tới trường hợp user tự thêm SFX dày cho từng cảnh.
    """
    entries = [("whoosh", 0.0), ("tick", 3.67), ("impact", 9.3), ("pop", 15.0)]
    plan = plan_scene_sfx(entries)
    assert plan == {0, 1, 2, 3}, f"kịch bản AI bình thường bị cắt SFX: {plan}"


def test_moi_ten_trong_filler_deu_co_trong_bang_gain():
    """Chống gõ sai tên: một tên lấp chỗ viết sai sẽ âm thầm rơi sang nhóm NHẤN."""
    thieu = sorted(SCENE_SFX_FILLER - set(SCENE_SFX_GAIN))
    assert not thieu, (
        f"SCENE_SFX_FILLER có tên không tồn tại trong SCENE_SFX_GAIN: {thieu} — "
        "gõ sai tên thì luật cooldown im lặng không áp dụng"
    )


def test_nguong_lap_cho_khong_chat_hon_nguong_trung_ten():
    """Hai ngưỡng phải nhất quán: lấp chỗ là luật CHẶT HƠN chồng lên luật trùng tên."""
    assert SCENE_SFX_FILLER_MIN_GAP >= SCENE_SFX_REPEAT_MIN_GAP, (
        f"{SCENE_SFX_FILLER_MIN_GAP} < {SCENE_SFX_REPEAT_MIN_GAP} — "
        "ngưỡng lấp chỗ lỏng hơn ngưỡng chung thì nó vô nghĩa"
    )


def test_jitter_tai_lap_duoc():
    """Render lại cùng một dự án phải ra cùng một bản mix."""
    a = scene_sfx_jitter("D:/AI VIDEO/output/job-abc.mp4", 3, "whoosh")
    b = scene_sfx_jitter("D:/AI VIDEO/output/job-abc.mp4", 3, "whoosh")
    assert a == b, f"jitter không tái lập được: {a} != {b}"


def test_jitter_khac_nhau_giua_cac_canh():
    """Nhưng vẫn phải khác nhau giữa các lần phát, nếu không thì mất hẳn tác dụng."""
    vals = {scene_sfx_jitter("job.mp4", i, "whoosh") for i in range(6)}
    assert len(vals) == 6, f"nhiều cảnh dùng chung một giá trị jitter: {vals}"


def test_jitter_trong_bien_do_cho_phep():
    for i in range(50):
        gain, pitch = scene_sfx_jitter("job.mp4", i, "tick")
        assert 1.0 - SCENE_SFX_GAIN_JITTER <= gain <= 1.0 + SCENE_SFX_GAIN_JITTER, gain
        assert 1.0 - SCENE_SFX_PITCH_JITTER <= pitch <= 1.0 + SCENE_SFX_PITCH_JITTER, pitch


def _placements_thuc_te(scene_sfx, durations):
    """Chạy ĐÚNG vòng lặp cảnh của render_final_video, thu lại SFX tới được bộ trộn.

    Chặn ngay tại `_mix_audio_tracks` rồi ném sentinel để khỏi phải encode cả video —
    phần cần kiểm là CHỖ NỐI giữa plan_scene_sfx() và audio_placements, không phải
    chất lượng file xuất ra.
    """
    import tempfile

    import numpy as np
    from PIL import Image

    import services.video_service as vs

    class _Stop(Exception):
        pass

    tmp = tempfile.mkdtemp(prefix="avm_sfx_wire_")
    img = os.path.join(tmp, "f.png")
    Image.fromarray(np.full((128, 72, 3), 128, np.uint8)).save(img)

    assets, t = [], 0.0
    for name, d in zip(scene_sfx, durations):
        assets.append({
            "image_path": img, "duration": d, "start_time": t,
            "sfx": name, "audio_path": "", "text": "x",
        })
        t += d

    captured = []

    def _fake_mix(placements, *a, **kw):
        captured.extend(placements)
        raise _Stop()

    goc = vs._mix_audio_tracks
    vs._mix_audio_tracks = _fake_mix
    try:
        vs.render_final_video(
            assets, os.path.join(tmp, "out.mp4"),
            use_sfx=True, sfx_volume=0.5, progress_logger=None,
            hook_effect="none", outro_effect="none",
        )
    except _Stop:
        pass
    finally:
        vs._mix_audio_tracks = goc

    return [
        (os.path.splitext(os.path.basename(p[0]))[0], round(p[1], 2))
        for p in captured
        if os.path.dirname(p[0]).endswith("sfx")
    ]


def test_noi_day_plan_toi_audio_placements():
    """plan_scene_sfx() phải THẬT SỰ điều khiển SFX đi vào bản mix.

    Dòng bug tái diễn của dự án này không nằm trong logic một hàm mà ở CHỖ NỐI giữa các
    tầng: field khai báo xong không ai đọc, kwargs không được nhét vào dict truyền đi.
    Một plan đúng tuyệt đối vẫn vô nghĩa nếu vòng lặp render không hỏi tới nó.
    """
    assert _placements_thuc_te(["whoosh", "pop"], [1.0, 3.0]) == [("whoosh", 0.0)], (
        "tiếng lấp chỗ sát nhau vẫn lọt vào bản mix — plan không được nối vào vòng lặp"
    )
    assert _placements_thuc_te(["whoosh", "impact"], [1.0, 3.0]) == [
        ("whoosh", 0.0), ("impact", 1.0),
    ], "tiếng nhấn bị chặn oan trên đường render thật"


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
