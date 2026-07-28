"""
Test cho cache_service — kho ảnh/giọng đọc đã sinh, thứ quyết định render lại tốn
bao nhiêu quota API.

Chạy:  python tests/test_cache_service.py    (từ thư mục backend/)
       pytest tests/test_cache_service.py

Hai thứ được canh kỹ nhất ở đây, vì cả hai đều từng hỏng mà KHÔNG có lỗi nào bắn ra:

  1. Ngưỡng dung lượng phải thật sự được cưỡng chế. Bản cũ chỉ xoá file quá 7 ngày,
     nên cache vượt 5GB toàn file mới thì không xoá được byte nào — MAX_CACHE_SIZE_GB
     thành con số trang trí và ổ đĩa cứ thế đầy.

  2. Cái gì lưu vào phải tra lại được. Lưu ra một đuôi mà _find_cached không dò tới
     = cache miss vĩnh viễn: file vẫn chiếm ổ, AI vẫn bị gọi lại mỗi lần render.
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import cache_service as cs


def _fresh(max_gb: float = 5) -> tuple:
    """CacheService trỏ vào thư mục tạm rỗng — không đụng cache thật của người dùng.

    Dựng lại ĐÚNG hình dạng thật: media/ là thư mục CON của cache/. Cho hai biến cùng
    trỏ một chỗ sẽ làm clear() xoá nhầm quota.json và test báo lỗi oan.
    """
    tmp = tempfile.mkdtemp(prefix="avm_cache_")
    media = os.path.join(tmp, "media")
    os.makedirs(media, exist_ok=True)
    cs.CACHE_DIR = tmp
    cs.MEDIA_CACHE_DIR = media
    cs.MAX_CACHE_SIZE_GB = max_gb
    return cs.CacheService(), media


def _write(path: str, size: int, age_days: float = 0.0) -> str:
    with open(path, "wb") as f:
        f.write(b"\0" * size)
    if age_days:
        old = time.time() - age_days * 86400
        os.utime(path, (old, old))
    return path


# ── Tra cứu ──────────────────────────────────────────────────────────────────
def test_luu_roi_tra_lai_duoc():
    c, tmp = _fresh()
    src = _write(os.path.join(tmp, "src.png"), 2048)

    c.set_media("imagen", src, prompt="mèo")

    assert c.has_media("imagen", prompt="mèo"), "vừa lưu xong mà tra không thấy"


def test_khoa_khac_nhau_khong_dung_chung_file():
    """Hai prompt khác nhau phải ra hai khoá khác nhau — nếu không, cảnh này nhận
    nhầm hình của cảnh kia và người dùng chỉ phát hiện lúc xem lại bản render."""
    c, tmp = _fresh()
    c.set_media("imagen", _write(os.path.join(tmp, "a.png"), 1024), prompt="mèo")

    assert not c.has_media("imagen", prompt="chó")


def test_cung_prompt_khac_prefix_la_hai_kho_rieng():
    """Ảnh AI và video stock của cùng một prompt phải nằm hai ngăn khác nhau."""
    c, tmp = _fresh()
    c.set_media("imagen", _write(os.path.join(tmp, "a.png"), 1024), prompt="biển")

    assert not c.has_media("stock", prompt="biển")


def test_get_media_lay_theo_duoi_da_cache():
    """Pipeline xin .png nhưng cảnh đó đã được cache dưới dạng video .mp4 — phải trả
    về đúng file .mp4, vì đuôi của file cache mới là sự thật."""
    c, tmp = _fresh()
    c.set_media("stock", _write(os.path.join(tmp, "clip.mp4"), 4096), prompt="biển")

    out = os.path.join(tmp, "scene_1.png")
    assert c.get_media("stock", out, prompt="biển")
    assert os.path.isfile(os.path.join(tmp, "scene_1.mp4")), "phải ghi ra .mp4"


def test_tra_khoa_khong_ton_tai_khong_nem_loi():
    c, _ = _fresh()
    assert c.has_media("imagen", prompt="chưa từng có") is False
    assert c.get_media("imagen", "/tmp/khong-quan-trong.png", prompt="chưa từng có") is False


def test_file_rong_khong_tinh_la_cache_hit():
    """File 0 byte là dấu vết của một lần ghi đứt gánh, không phải cache dùng được."""
    c, tmp = _fresh()
    key = c._media_key("imagen", prompt="hỏng")
    _write(os.path.join(tmp, key + ".png"), 0)

    assert not c.has_media("imagen", prompt="hỏng")


def test_duoi_la_bi_tu_choi_thang_tay():
    """Lưu ra đuôi mà _find_cached không dò tới = file chiếm ổ vĩnh viễn mà không lần
    tra nào tìm thấy. Thà không lưu."""
    c, tmp = _fresh()
    src = _write(os.path.join(tmp, "la.bin"), 1024)

    c.set_media("imagen", src, prompt="x")

    assert not c.has_media("imagen", prompt="x")


def test_moi_duoi_trong_danh_sach_deu_tra_lai_duoc():
    """_MEDIA_EXTS là hợp đồng giữa set_media và _find_cached — lệch một đuôi là loại
    media đó mất cache im lặng."""
    for ext in cs._MEDIA_EXTS:
        c, tmp = _fresh()
        c.set_media("imagen", _write(os.path.join(tmp, "src" + ext), 512), prompt="p")
        assert c.has_media("imagen", prompt="p"), f"đuôi {ext} lưu được nhưng tra không thấy"


# ── Cưỡng chế ngưỡng dung lượng ──────────────────────────────────────────────
def _fill(tmp: str, n: int, size: int, age_days: float = 0.0):
    for i in range(n):
        _write(os.path.join(tmp, f"imagen_{i:04d}.png"), size, age_days)


def _total(tmp: str) -> int:
    return sum(os.path.getsize(os.path.join(tmp, f)) for f in os.listdir(tmp))


def test_duoi_nguong_thi_khong_dong_gi():
    c, tmp = _fresh(max_gb=1 / 1024)          # ngưỡng 1MB
    _fill(tmp, 4, 100 * 1024)                 # 400KB
    before = set(os.listdir(tmp))

    c._auto_cleanup()

    assert set(os.listdir(tmp)) == before


def test_vuot_nguong_voi_TOAN_FILE_MOI_van_phai_don():
    """ĐÂY LÀ LỖI CŨ: bản trước chỉ xoá file > 7 ngày, nên cache vượt ngưỡng mà toàn
    file mới thì không xoá nổi một byte — ổ đĩa đầy trong im lặng."""
    c, tmp = _fresh(max_gb=1 / 1024)          # ngưỡng 1MB
    _fill(tmp, 20, 100 * 1024, age_days=0)    # 2MB, tất cả vừa tạo

    c._auto_cleanup()

    assert _total(tmp) <= 1024 * 1024 * 0.8, "vượt ngưỡng mà không dọn xuống 80%"
    assert os.listdir(tmp), "dọn quá tay, xoá sạch cả cache"


def test_file_qua_han_bi_xoa_truoc_file_moi():
    """Pha 1 phải dùng hết file quá hạn trước khi pha 2 đụng tới file còn mới.

    Lượng file quá hạn ở đây dư sức đưa cache về dưới ngưỡng, nên KHÔNG file mới nào
    được phép mất. Lưu ý: dọn dừng ngay khi chạm ngưỡng, nên vẫn còn sót lại vài file
    quá hạn là đúng — xoá thêm chỉ tổ vứt đi những thứ còn dùng lại được.
    """
    c, tmp = _fresh(max_gb=1 / 1024)          # ngưỡng 1MB
    for i in range(8):
        _write(os.path.join(tmp, f"cu_{i}.png"), 100 * 1024, age_days=30)
    for i in range(4):
        _write(os.path.join(tmp, f"moi_{i}.png"), 100 * 1024, age_days=0)

    c._auto_cleanup()

    con_lai = set(os.listdir(tmp))
    con_moi = {f for f in con_lai if f.startswith("moi_")}
    assert len(con_moi) == 4, f"file mới bị xoá dù file quá hạn còn dư: {sorted(con_lai)}"
    assert len(con_lai) < 12, "vượt ngưỡng mà không xoá gì"


def test_don_theo_lru_cu_nhat_truoc():
    """Khi buộc phải đụng tới file chưa quá hạn, cái cũ nhất phải đi trước."""
    c, tmp = _fresh(max_gb=1 / 1024)
    for i in range(20):
        # i càng lớn càng mới
        _write(os.path.join(tmp, f"f_{i:02d}.png"), 100 * 1024, age_days=(20 - i) * 0.1)

    c._auto_cleanup()

    con_lai = sorted(os.listdir(tmp))
    assert con_lai, "xoá sạch"
    giu_cu_nhat = min(int(f.split("_")[1].split(".")[0]) for f in con_lai)
    assert giu_cu_nhat > 0, "file cũ nhất lẽ ra phải bị xoá đầu tiên"


# ── Xoá thủ công ─────────────────────────────────────────────────────────────
def test_clear_khong_dung_vao_quota_json():
    """quota.json nằm chung thư mục nhưng KHÔNG phải cache: xoá nó = app tưởng còn
    nguyên hạn mức và gọi API tiếp cho tới khi Google trả 429."""
    c, _ = _fresh()
    _write(os.path.join(cs.CACHE_DIR, "quota.json"), 128)
    _write(os.path.join(cs.CACHE_DIR, "gen_script_abc.json"), 128)

    c.clear(include_script_cache=True)

    assert os.path.isfile(os.path.join(cs.CACHE_DIR, "quota.json")), "đã xoá mất bộ đếm quota"
    assert not os.path.isfile(os.path.join(cs.CACHE_DIR, "gen_script_abc.json"))


def test_clear_mac_dinh_giu_lai_kich_ban_gemini():
    """Kịch bản chỉ vài KB nhưng sinh lại thì TỐN QUOTA — mặc định không đụng tới."""
    c, _ = _fresh()
    _write(os.path.join(cs.CACHE_DIR, "gen_script_abc.json"), 128)

    c.clear()

    assert os.path.isfile(os.path.join(cs.CACHE_DIR, "gen_script_abc.json"))


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
