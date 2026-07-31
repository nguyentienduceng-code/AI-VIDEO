"""
Test cho việc sửa TOÀN BỘ kịch bản rồi chia lại thành cảnh (services/script_resplit.py).

Chạy:  python tests/test_script_resplit.py     (từ thư mục backend/)
       pytest tests/test_script_resplit.py

Điều đắt nhất cần bảo vệ ở đây là `image_prompt`: mỗi cái là công sức của một vòng gọi
LLM. Sửa một chữ trong lời thoại mà mất sạch mô tả ảnh thì vừa tốn quota sinh lại, vừa
làm video đổi hình xoành xoạch dù người dùng không hề đụng vào hình.

Bốn thao tác THẬT mà người dùng sẽ làm trên khối chữ, mỗi cái một test:
  sửa chữ trong đoạn · gộp hai cảnh (xoá dòng trống) · tách một cảnh (thêm dòng trống)
  · viết thêm đoạn hoàn toàn mới.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import script_resplit as sr


def _canh(n, text, prompt):
    return {"scene": n, "text": text, "image_prompt": prompt,
            "emotion": "calm", "subtitle_text": f"phụ đề cũ {n}"}


KICH_BAN_GOC = [
    _canh(1, "Chín mươi chín phần trăm người tích góp tiền chỉ vì sợ thiếu thốn.", "một chiếc ví rỗng"),
    _canh(2, "Bà Lynne Twist đã chứng kiến suốt bốn mươi năm rằng tiền luôn mang cảm xúc.", "chân dung người phụ nữ lớn tuổi"),
    _canh(3, "Tiêu tiền bằng sự biết ơn thì tài chính sẽ tự chữa lành.", "bàn tay trao nhau đồng xu"),
]


# ──────────────────────────────────────────────────────────────────────
# 1. Tách/ghép khối chữ
# ──────────────────────────────────────────────────────────────────────

def test_dong_trong_la_ranh_gioi_canh_xuong_dong_don_thi_khong():
    """
    Người ta xuống dòng đơn cho dễ đọc chứ không có ý tách cảnh. Cắt theo mọi lần xuống
    dòng sẽ băm kịch bản thành hàng chục cảnh vụn ngay khi user format lại cho dễ nhìn.
    """
    assert sr.tach_doan("Câu một.\nCâu hai vẫn cùng cảnh.") == ["Câu một. Câu hai vẫn cùng cảnh."]
    assert sr.tach_doan("Cảnh một.\n\nCảnh hai.") == ["Cảnh một.", "Cảnh hai."]
    # Nhiều dòng trống liên tiếp / khoảng trắng thừa vẫn chỉ là MỘT ranh giới
    assert sr.tach_doan("A.\n\n\n  \n\nB.") == ["A.", "B."]
    assert sr.tach_doan("   ") == []


def test_ghep_roi_tach_lai_tra_ve_dung_kich_ban_ban_dau():
    """Vòng khứ hồi phải khép kín, nếu không mở trình sửa ra là kịch bản đã méo."""
    khoi = sr.ghep_thanh_van_ban(KICH_BAN_GOC)
    assert sr.tach_doan(khoi) == [c["text"] for c in KICH_BAN_GOC]


# ──────────────────────────────────────────────────────────────────────
# 2. Bốn thao tác sửa thật của người dùng
# ──────────────────────────────────────────────────────────────────────

def test_sua_vai_chu_van_giu_nguyen_anh_cua_canh_do():
    """Sửa chữ là thao tác thường gặp nhất — không được làm mất mô tả ảnh."""
    khoi = sr.ghep_thanh_van_ban(KICH_BAN_GOC).replace("sợ thiếu thốn", "nỗi sợ thiếu thốn ám ảnh")
    ket = sr.resplit(khoi, KICH_BAN_GOC, rebalance=False)
    canh = ket["scenes"]
    assert len(canh) == 3
    assert canh[0]["image_prompt"] == "một chiếc ví rỗng"
    assert canh[1]["image_prompt"] == "chân dung người phụ nữ lớn tuổi"
    assert canh[2]["image_prompt"] == "bàn tay trao nhau đồng xu"
    assert "nỗi sợ thiếu thốn ám ảnh" in canh[0]["text"]
    assert ket["report"]["doan_viet_moi"] == 0


def test_xoa_dong_trong_de_gop_hai_canh():
    """Gộp cảnh 1+2 → cảnh mới thừa kế ảnh của MỘT trong hai, không được để trống."""
    khoi = f'{KICH_BAN_GOC[0]["text"]} {KICH_BAN_GOC[1]["text"]}\n\n{KICH_BAN_GOC[2]["text"]}'
    ket = sr.resplit(khoi, KICH_BAN_GOC, rebalance=False)
    canh = ket["scenes"]
    assert len(canh) == 2
    assert canh[0]["image_prompt"] in ("một chiếc ví rỗng", "chân dung người phụ nữ lớn tuổi")
    assert canh[1]["image_prompt"] == "bàn tay trao nhau đồng xu"


def test_them_dong_trong_de_tach_mot_canh():
    """Tách cảnh 2 làm đôi → CẢ HAI nửa cùng thừa kế ảnh của cảnh 2 gốc."""
    khoi = (f'{KICH_BAN_GOC[0]["text"]}\n\n'
            "Bà Lynne Twist đã chứng kiến suốt bốn mươi năm.\n\n"
            "Rằng tiền luôn mang theo cảm xúc của người tiêu nó.\n\n"
            f'{KICH_BAN_GOC[2]["text"]}')
    ket = sr.resplit(khoi, KICH_BAN_GOC, rebalance=False)
    canh = ket["scenes"]
    assert len(canh) == 4
    assert canh[1]["image_prompt"] == "chân dung người phụ nữ lớn tuổi"
    assert canh[2]["image_prompt"] == "chân dung người phụ nữ lớn tuổi"
    assert canh[3]["image_prompt"] == "bàn tay trao nhau đồng xu", "nửa sau không được kéo lệch cảnh 3"


def test_doan_viet_moi_hoan_toan_bam_theo_canh_lien_truoc():
    """
    Đoạn tự viết thêm không dò được về đâu. Thà thừa kế hình của bối cảnh đang diễn ra
    còn hơn trả về ô trống rồi bắt pipeline sinh ảnh mù.
    """
    khoi = (f'{KICH_BAN_GOC[0]["text"]}\n\n'
            "Một câu hoàn toàn mới về chủ đề chẳng liên quan gì tới các cảnh cũ cả.\n\n"
            f'{KICH_BAN_GOC[2]["text"]}')
    ket = sr.resplit(khoi, KICH_BAN_GOC, rebalance=False)
    canh, bao_cao = ket["scenes"], ket["report"]
    assert canh[1]["image_prompt"] == "một chiếc ví rỗng", "phải bám cảnh liền trước"
    assert bao_cao["doan_viet_moi"] == 1
    assert bao_cao["thua_ke"][1]["la_doan_moi"] is True
    assert bao_cao["thua_ke"][0]["la_doan_moi"] is False


def test_cau_hook_lap_lai_o_cuoi_khong_keo_ve_canh_dau():
    """
    Kịch bản viral rất hay nhắc lại câu hook ở đoạn kết. Dò toàn cục sẽ khiến đoạn CUỐI
    thừa kế hình của cảnh ĐẦU — hình nhảy ngược về đầu bài. Ràng buộc thứ tự tiến chặn
    đúng chuyện đó.
    """
    goc = KICH_BAN_GOC + [_canh(4, "Chín mươi chín phần trăm người tích góp tiền chỉ vì sợ thiếu thốn.", "cảnh kết vòng tròn")]
    ket = sr.resplit(sr.ghep_thanh_van_ban(goc), goc, rebalance=False)
    canh = ket["scenes"]
    assert canh[0]["image_prompt"] == "một chiếc ví rỗng"
    assert canh[3]["image_prompt"] == "cảnh kết vòng tròn", "câu lặp kéo đoạn cuối về cảnh đầu"


# ──────────────────────────────────────────────────────────────────────
# 3. Trường theo chữ & cân nhịp
# ──────────────────────────────────────────────────────────────────────

def test_bo_cac_truong_mo_ta_doan_chu_cu():
    """
    `subtitle_text`/`word_boundaries` mô tả ĐOẠN CHỮ CŨ. Lời đã đổi mà giữ lại thì phụ đề
    hiện một đằng, giọng đọc một nẻo — đúng loại lỗi không ai soi ra khi xem bản nháp.
    """
    goc = [dict(KICH_BAN_GOC[0], word_boundaries=[{"offset": 0, "duration": 1, "text": "cũ"}],
                computed_duration=5.0, start_time=2.0)]
    ket = sr.resplit("Lời thoại đã được viết lại hoàn toàn khác trước.", goc, rebalance=False)
    canh = ket["scenes"][0]
    for truong in ("subtitle_text", "word_boundaries", "computed_duration", "start_time"):
        assert truong not in canh, f"còn sót {truong} của đoạn chữ cũ"
    assert canh["image_prompt"] == "một chiếc ví rỗng", "ảnh thì PHẢI giữ"
    assert canh["emotion"] == "calm"


def test_can_nhip_tat_di_thi_giu_dung_ranh_gioi_nguoi_dung_chot():
    """Có người đã chuẩn bị sẵn đúng N tấm ảnh — thuật toán không được tự ý chia lại."""
    khoi = "Một câu rất ngắn.\n\n" + ("Câu này dài hơn nhiều. " * 8)
    giu = sr.resplit(khoi, KICH_BAN_GOC, rebalance=False)
    assert len(giu["scenes"]) == 2
    assert giu["report"]["da_can_nhip"] is False

    can = sr.resplit(khoi, KICH_BAN_GOC, rebalance=True)
    assert can["report"]["da_can_nhip"] is True
    assert len(can["scenes"]) >= 2, "cân nhịp phải tách được đoạn dài ra"
    assert "nhip" in can["report"]


def test_so_canh_va_bao_cao_khop_nhau():
    ket = sr.resplit(sr.ghep_thanh_van_ban(KICH_BAN_GOC), KICH_BAN_GOC, rebalance=True)
    assert ket["report"]["canh_ket_qua"] == len(ket["scenes"])
    assert ket["report"]["canh_goc"] == 3
    assert ket["report"]["doan_da_sua"] == 3
    # scene được đánh số lại liên tục từ 1
    assert [c["scene"] for c in ket["scenes"]] == list(range(1, len(ket["scenes"]) + 1))


def test_kich_ban_trong_thi_bao_loi_ro_rang():
    try:
        sr.resplit("   \n\n  ", KICH_BAN_GOC)
        assert False, "phải ném ValueError"
    except ValueError as e:
        assert "trống" in str(e).lower()


def test_khong_co_canh_goc_van_chia_duoc():
    """Dán một kịch bản mới toanh vào ô trống — không có gì để thừa kế, không được nổ."""
    ket = sr.resplit("Câu một ở đây.\n\nCâu hai ở đây.", [], rebalance=False)
    assert len(ket["scenes"]) == 2
    assert all(c.get("text") for c in ket["scenes"])
    assert ket["report"]["canh_goc"] == 0


def test_khong_dung_vao_danh_sach_canh_goc():
    """Hàm trả ĐỀ XUẤT — sửa vào bản gốc là user mất kịch bản khi bấm Huỷ."""
    import copy
    ban_sao = copy.deepcopy(KICH_BAN_GOC)
    sr.resplit(sr.ghep_thanh_van_ban(KICH_BAN_GOC) + "\n\nĐoạn mới thêm.", KICH_BAN_GOC)
    assert KICH_BAN_GOC == ban_sao, "đã sửa vào danh sách cảnh gốc"


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
