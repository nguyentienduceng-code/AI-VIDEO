"""
Test cho duration_model — nguồn chân lý duy nhất về "đoạn chữ này đọc mất bao lâu".

Chạy:  python tests/test_duration_model.py     (từ thư mục backend/)
       pytest tests/test_duration_model.py

Trọng tâm: hồ sơ tự học phải HỘI TỤ về tốc độ thật, và phải MIỄN NHIỄM với mẫu rác —
một job TTS lỗi trả file 0.1 giây cho 30 từ mà lọt vào hồ sơ thì mọi ước lượng sau đó
đều sai, và không ai biết vì chẳng có lỗi nào được ném ra.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import duration_model as dm


def _isolate():
    """Ép hồ sơ ra file tạm để test không đụng vào dữ liệu đã học của người dùng."""
    tmp = tempfile.mkdtemp(prefix="avm_timing_")
    dm._profile_path = lambda: os.path.join(tmp, "timing_profile.json")
    dm.reset_cache()


# ── Phân tích văn bản ────────────────────────────────────────────────────────
def test_dem_tu_bo_qua_the_danh_dau():
    """Thẻ <break/> là chỉ dẫn nhịp đọc, không ai đọc thành tiếng."""
    assert dm.count_words('Xin chào <break time="1s"/> các bạn') == 4
    assert dm.count_words("") == 0
    assert dm.count_words(None) == 0


def test_cong_don_thoi_gian_cac_the_break():
    assert dm.break_seconds('a <break time="1s"/> b <break time="500ms"/> c') == 1.5
    assert dm.break_seconds("không có thẻ nào") == 0.0


def test_doc_he_so_toc_do():
    assert dm.parse_rate("+15%") == 1.15
    assert dm.parse_rate("-20%") == 0.8
    assert dm.parse_rate("+0%") == 1.0
    assert dm.parse_rate(None) == 1.0
    assert dm.parse_rate("rác") == 1.0, "giá trị lạ phải lùi về tốc độ chuẩn, không nổ"
    assert dm.parse_rate("-500%") > 0, "rate âm sâu không được tạo hệ số ≤ 0 (chia cho 0)"


# ── Ước lượng ────────────────────────────────────────────────────────────────
def test_uoc_luong_gom_ca_khoang_lang():
    """30 từ ở 3 từ/giây = 10 giây, cộng 1 giây thẻ break và 0.5 giây pause = 11.5."""
    _isolate()
    text = " ".join(["từ"] * 30) + ' <break time="1s"/>'

    got = dm.estimate_duration(text, pause_after_ms=500)

    assert abs(got - 11.5) < 0.01, f"ước lượng {got:.2f}s, mong đợi 11.5s"


def test_toc_do_doc_nhanh_thi_thoi_luong_ngan_lai():
    _isolate()
    text = " ".join(["từ"] * 30)

    cham = dm.estimate_duration(text, rate="+0%")
    nhanh = dm.estimate_duration(text, rate="+20%")

    assert abs(nhanh - cham / 1.2) < 0.01, "hệ số tốc độ không được áp đúng"


def test_van_ban_rong_khong_chia_cho_khong():
    _isolate()
    assert dm.estimate_duration("") == 0.0
    assert dm.estimate_duration('<break time="2s"/>') == 2.0


# ── Tự học ───────────────────────────────────────────────────────────────────
def test_hoi_tu_ve_toc_do_that():
    """Giọng thật đọc 2.5 từ/giây: sau một loạt mẫu, ước lượng phải bám sát 2.5 chứ
    không nằm lì ở mặc định 3.0."""
    _isolate()
    text = " ".join(["từ"] * 25)

    for _ in range(30):
        dm.record_observation(text, 10.0, voice="vi-VN-Test")  # 25 từ / 10s = 2.5 wps

    got = dm.words_per_second("vi-VN-Test")
    assert abs(got - 2.5) < 0.15, f"học ra {got:.2f} từ/giây, mong đợi ~2.5"


def test_quy_doi_ve_moc_rate_0():
    """Mẫu đo ở +25% phải được quy về mốc chuẩn trước khi ghi, nếu không hồ sơ sẽ bị
    kéo lệch mỗi khi user chỉnh thanh tốc độ."""
    _isolate()
    text = " ".join(["từ"] * 25)

    # Đọc nhanh 25% → 3.75 wps quan sát được, quy về mốc chuẩn vẫn là 3.0
    for _ in range(30):
        dm.record_observation(text, 25 / 3.75, voice="vi-VN-Test2", rate="+25%")

    assert abs(dm.words_per_second("vi-VN-Test2") - 3.0) < 0.15


def test_bo_qua_mau_rac():
    """TTS lỗi (30 từ trong 0.2 giây) hoặc câu quá ngắn không được làm hỏng hồ sơ."""
    _isolate()
    text = " ".join(["từ"] * 30)

    for _ in range(20):
        dm.record_observation(text, 0.2, voice="vi-VN-Test3")      # 150 wps — vô lý
        dm.record_observation(text, 300.0, voice="vi-VN-Test3")    # 0.1 wps — vô lý
        dm.record_observation("hai từ", 5.0, voice="vi-VN-Test3")  # quá ngắn để đo

    assert dm.words_per_second("vi-VN-Test3") == dm.BASE_WPS, "mẫu rác đã lọt vào hồ sơ"


def test_tru_thoi_gian_break_truoc_khi_tinh_toc_do():
    """25 từ + 5 giây khoảng lặng, tổng 15 giây → tốc độ thật là 2.5 wps chứ không
    phải 1.67. Không trừ thẻ break ra thì hồ sơ tưởng giọng đọc chậm hơn thực tế."""
    _isolate()
    text = " ".join(["từ"] * 25) + ' <break time="5s"/>'

    for _ in range(30):
        dm.record_observation(text, 15.0, voice="vi-VN-Test4")

    assert abs(dm.words_per_second("vi-VN-Test4") - 2.5) < 0.15


def test_ghi_mau_khong_bao_gio_nem_loi():
    """Chức năng phụ trợ: hỏng thì ước lượng kém đi, tuyệt đối không được giết job."""
    _isolate()
    dm.record_observation(None, None, voice=None)
    dm.record_observation("abc", float("nan"))
    dm.record_observation("abc", -5.0)


def test_ho_so_ben_vung_qua_lan_doc_lai():
    """Học xong phải nằm lại trên đĩa — mỗi lần khởi động lại backend mà mất sạch thì
    cơ chế tự học vô nghĩa."""
    _isolate()
    text = " ".join(["từ"] * 25)
    for _ in range(30):
        dm.record_observation(text, 10.0, voice="vi-VN-Test5")

    dm.reset_cache()  # buộc đọc lại từ đĩa

    assert abs(dm.words_per_second("vi-VN-Test5") - 2.5) < 0.15


def test_summary_bao_dung_trang_thai_da_hoc():
    _isolate()
    assert dm.profile_summary("vi-VN-Moi")["is_learned"] is False

    text = " ".join(["từ"] * 25)
    for _ in range(5):
        dm.record_observation(text, 10.0, voice="vi-VN-Moi")

    s = dm.profile_summary("vi-VN-Moi")
    assert s["is_learned"] is True
    assert s["voice_samples"] == 5


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
