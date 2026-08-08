"""
Test cho lịch hiện CHỮ NHẤN (highlight_text) — motion_effects.plan_scene_highlights().

Chạy:  python tests/test_scene_highlight.py   (từ thư mục backend/, không cần pytest)
       pytest tests/test_scene_highlight.py

VÌ SAO CÓ FILE NÀY: đo trên video thật a67a0fa9 (30 cảnh) ra hai lỗi CÂM — video render
xong, phát được, không exception nào:

  1. LẶP: 24/30 cảnh có chữ nhấn, trong đó 12 cặp LIỀN KỀ trùng y nguyên. "ĐỪNG CHỈ
     TRÍCH" nhấp lại 4 lần trong 20 giây (cảnh 14-17), cùng màu cùng vị trí, trong khi
     lời đọc bên dưới mỗi lần một khác.

  2. LỆCH GIỜ: chữ luôn vẽ ở 1.2s ĐẦU cảnh bất kể cụm đó được đọc lúc nào. Chỉ 7/24 cảnh
     thực sự nói cụm đang hiện, và ngay cả 7 cảnh đó cũng đọc muộn hơn 0.98-5.32 giây.
     Cảnh 1 đọc "Xin chào tất cả mọi người" mà màn hình hiện "THIỆN CHÍ" — mãi cảnh 2
     mới nói tới.

Trên đúng bộ dữ liệu đó, luật mới đưa 24 lần hiện xuống 12 (mỗi cụm đúng một lần) và neo
được 7 lần vào đúng mốc đọc.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.motion_effects import plan_scene_highlights


def _canh(hl: str = "", loi: str = "", dur: float = 5.0, wps: float = 0.4) -> dict:
    """Một cảnh giả với word_boundaries dựng đều đặn từ chuỗi lời đọc."""
    wb = [
        {"text": tu, "offset": round(0.5 + i * wps, 3), "duration": wps}
        for i, tu in enumerate(loi.split())
    ]
    return {"highlight_text": hl, "word_boundaries": wb, "duration": dur}


def test_cum_lap_o_canh_lien_ke_chi_hien_MOT_lan():
    scenes = [
        _canh("ĐỪNG CHỈ TRÍCH", "Cuốn sách được chia thành bốn phần"),
        _canh("ĐỪNG CHỈ TRÍCH", "nguyên tắc đầu tiên là đừng chỉ trích ai cả"),
        _canh("ĐỪNG CHỈ TRÍCH", "Carnegie kể chuyện về tội phạm"),
        _canh("ĐỪNG CHỈ TRÍCH", "gần như không ai tự nhận mình xấu"),
    ]
    kh = plan_scene_highlights(scenes)
    assert len(kh) == 1, f"cụm lặp 4 cảnh liền kề vẫn hiện {len(kh)} lần: {kh}"


def test_chon_dung_canh_THUC_SU_doc_cum_do():
    """Không phải cứ lấy cảnh ĐẦU của đoạn — phải lấy cảnh nói ra cụm ấy.

    Đây là điểm tinh tế nhất: ở dữ liệu thật, "ĐỪNG CHỈ TRÍCH" trải cảnh 14-17 nhưng chỉ
    cảnh 15 mới đọc nó. Chọn cảnh đầu đoạn là hiện chữ trước lời đúng một cảnh.
    """
    scenes = [
        _canh("ĐỪNG CHỈ TRÍCH", "Cuốn sách được chia thành bốn phần"),
        _canh("ĐỪNG CHỈ TRÍCH", "nguyên tắc đầu tiên là đừng chỉ trích ai cả"),
        _canh("ĐỪNG CHỈ TRÍCH", "Carnegie kể chuyện về tội phạm"),
    ]
    kh = plan_scene_highlights(scenes)
    assert set(kh) == {1}, f"chọn nhầm cảnh: {kh}"


def test_neo_vao_dung_moc_cum_duoc_doc():
    """"đừng chỉ trích" là từ thứ 5-7 → offset 0.5 + 5*0.4 = 2.5s."""
    scenes = [_canh("ĐỪNG CHỈ TRÍCH", "nguyên tắc đầu tiên là đừng chỉ trích ai cả")]
    kh = plan_scene_highlights(scenes)
    assert abs(kh[0] - 2.5) < 0.01, f"neo sai mốc: {kh}"


def test_khong_canh_nao_doc_thi_ve_canh_dau_moc_0():
    """"NĂM 1936" đọc thành "năm một nghìn chín trăm ba mươi sáu" — không khớp chuỗi.

    Không khớp được thì giữ hành vi cũ (đầu cảnh), chỉ khác là chỉ còn MỘT lần.
    """
    scenes = [
        _canh("NĂM 1936", "Bối cảnh lúc đó là nước Mỹ giữa Đại Suy thoái"),
        _canh("NĂM 1936", "và tuyệt vọng đi tìm một cách sống tử tế hơn"),
    ]
    kh = plan_scene_highlights(scenes)
    assert kh == {0: 0.0}, f"dự phòng sai: {kh}"


def test_cum_quay_lai_sau_KHONG_bi_gop():
    """Nhắc lại một cụm sau vài cảnh khác là CÓ CHỦ ĐÍCH, không phải lặp gây nhàm.

    Chỉ gom các cảnh LIỀN KỀ — gom cả những lần cách xa nhau sẽ nuốt mất chủ ý dàn dựng.
    """
    scenes = [
        _canh("THÀNH THẬT", "hãy thành thật với chính mình"),
        _canh("ĐỪNG TRANH CÃI", "đừng tranh cãi với bất kỳ ai"),
        _canh("THÀNH THẬT", "một lần nữa hãy thành thật"),
    ]
    kh = plan_scene_highlights(scenes)
    assert set(kh) == {0, 1, 2}, f"gộp nhầm cụm cách xa nhau: {kh}"


def test_khong_tran_qua_moc_ket_thuc_canh():
    """Cụm đọc ở cuối cảnh thì phải lùi lại, không để chữ bị cắt cụt lúc chuyển cảnh."""
    # 8 từ, từ cuối ở 0.5 + 7*0.4 = 3.3s; cảnh dài 4.0s; chữ hiện 1.2s → phải kẹp về 2.8s
    scenes = [_canh("RẤT QUAN TRỌNG", "điều này thật sự là rất quan trọng", dur=4.0)]
    kh = plan_scene_highlights(scenes)
    assert kh[0] <= 4.0 - 1.2 + 1e-6, f"chữ tràn qua cuối cảnh: bắt đầu {kh[0]}"


def test_canh_khong_co_chu_nhan_khong_lam_lech_chi_so():
    scenes = [_canh("", "không có chữ nhấn"), _canh("", "cũng không"),
              _canh("ĐIỂM NHẤN", "đây là điểm nhấn thật")]
    kh = plan_scene_highlights(scenes)
    assert set(kh) == {2}, f"chỉ số lệch: {kh}"


def test_bo_dau_cau_khi_so_khop():
    """word_boundaries giữ nguyên dấu câu ("trích,") — so thô sẽ không bao giờ khớp."""
    scenes = [_canh("CHỈ TRÍCH", "đừng chỉ trích, oán trách hay than phiền")]
    kh = plan_scene_highlights(scenes)
    assert kh and abs(kh[0] - 0.9) < 0.01, f"dấu câu làm hỏng phép khớp: {kh}"


def test_hai_duong_render_dung_chung_mot_ke_hoach():
    """FastAssembly và MoviePy phải ra CÙNG kết quả — bật/tắt cờ không được đổi nội dung."""
    import inspect

    from services import ffmpeg_assembler, video_service

    for mod in (ffmpeg_assembler, video_service):
        assert "plan_scene_highlights" in inspect.getsource(mod), (
            f"{mod.__name__} không dùng plan_scene_highlights — hai đường sẽ trôi lệch nhau"
        )


def test_noi_day_moc_hien_chu_vao_lenh_ffmpeg():
    """Mốc neo phải THẬT SỰ đi vào filtergraph, không chỉ nằm trong dict.

    Dòng bug tái diễn của dự án nằm ở CHỖ NỐI: một kế hoạch đúng tuyệt đối vẫn vô nghĩa
    nếu bước dựng lệnh không hỏi tới nó.
    """
    import tempfile

    from services import ffmpeg_assembler as fa

    class _Bat(Exception):
        def __init__(self, cmd):
            self.cmd = cmd

    d = tempfile.mkdtemp(prefix="avm_hl_")
    scenes = []
    for i, (hl, loi) in enumerate((
        ("ĐỪNG CHỈ TRÍCH", "mở đầu không hề nhắc tới"),
        ("ĐỪNG CHỈ TRÍCH", "nguyên tắc đầu tiên là đừng chỉ trích ai cả"),
    )):
        p = os.path.join(d, f"s{i}.mp4")
        with open(p, "wb") as f:
            f.write(b"\0" * 64)
        s = _canh(hl, loi, dur=6.0)
        s.update({"image_path": p, "start_time": i * 6.0})
        scenes.append(s)

    def _fake_run(cmd, *a, **kw):
        raise _Bat(cmd)

    goc_run, goc_nvenc = fa.subprocess.run, fa._has_nvenc
    fa.subprocess.run = _fake_run
    fa._has_nvenc = lambda: False
    try:
        fa.assemble(scenes, os.path.join(d, "out.mp4"), width=1080, height=1920)
    except _Bat as e:
        cmd = e.cmd
    finally:
        fa.subprocess.run, fa._has_nvenc = goc_run, goc_nvenc

    fg = cmd[cmd.index("-filter_complex") + 1]
    assert fg.count("drawtext") == 1, (
        f"chữ nhấn vẫn vẽ {fg.count('drawtext')} lần cho cụm lặp — kế hoạch không được nối vào"
    )
    # Cụm đọc ở từ thứ 5 → 0.5 + 5*0.4 = 2.5s. Cửa sổ enable phải bắt đầu từ đó.
    # Dấu phẩy trong filtergraph bị escape thành `\,` (nháy đơn KHÔNG bảo vệ dấu phẩy —
    # xem _esc_expr), nên phải so đúng dạng đã escape.
    assert r"between(t\,2.500\,3.700)" in fg, (
        f"cửa sổ hiện chữ không neo vào mốc đọc. filtergraph: ...{fg[fg.find('drawtext'):][:240]}"
    )
    assert "(t-2.500)" in fg, "alpha vẫn tính từ đầu cảnh thay vì từ lúc chữ hiện"


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
