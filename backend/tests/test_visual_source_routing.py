"""
Test cho PHÉP CHỌN NGUỒN HÌNH (ảnh AI vs video stock) và thứ tự tầng dự phòng sinh ảnh.

Chạy:  python tests/test_visual_source_routing.py   (từ thư mục backend/, không cần pytest)
       pytest tests/test_visual_source_routing.py

VÌ SAO CÓ FILE NÀY: triệu chứng người dùng báo — "đa số video đều lấy từ Pexels, Gemini
sinh ảnh khá ít" — không đến từ một lỗi crash nào, mà từ HAI phép suy luận âm thầm:

  1. `_pick_visual_source` dò chữ "realistic"/"photoreal" trong `art_style`. Nhưng
     `STYLES[1]` trên giao diện là "Realistic (Thực tế)" = "Photorealistic, cinematic
     lighting, 8K UHD" — lựa chọn tự nhiên nhất cho chủ đề đời thực. Chọn nó là TOÀN BỘ
     video chuyển sang Pexels, trong khi người dùng tưởng mình chọn PHONG CÁCH VẼ.
     (Đây là thế hệ bẫy THỨ HAI: bản trước đó dò chính chuỗi đó trong `image_prompt` do
     Gemini sinh — xem docstring `_pick_visual_source`.)
  2. `generate_image_with_fallback` đặt Pexels photo TRƯỚC Pollinations FLUX. Hàm này được
     gọi chính xác vì người dùng muốn ẢNH AI, nhưng hết quota Gemini là nó trả về ảnh
     STOCK TĨNH — đổi nguồn hình sau lưng người dùng.

Cả hai đều là lỗi CÂM: video vẫn render xong, vẫn đẹp, chỉ là không phải thứ người dùng
chọn — và không log nào nói ra.
"""
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import _pick_visual_source, _wants_stock_footage


class Req:
    """Bản tối giản của RenderVideoRequest cho phép chọn nguồn hình."""

    def __init__(self, **kw):
        self.visual_source = kw.get("visual_source", "auto")
        self.prefer_stock_video = kw.get("prefer_stock_video", False)
        self.art_style = kw.get("art_style", "Anime illustration, vibrant colors")


# Chuỗi art_style THẬT của giao diện (frontend/src/constants.js › STYLES).
STYLE_REALISTIC = "Photorealistic, cinematic lighting, 8K UHD"
STYLE_ANIME = "Anime illustration, vibrant colors, Studio Ghibli inspired"
STYLE_DOC = "Vintage 35mm film, grainy, retro aesthetic, warm nostalgic colors"


# ---------------------------------------------------------------------------
# 1. art_style KHÔNG được quyết định nguồn hình
# ---------------------------------------------------------------------------
def test_chon_phong_cach_realistic_khong_con_bien_ca_video_thanh_stock():
    """Đây chính là triệu chứng người dùng báo."""
    req = Req(visual_source="auto", prefer_stock_video=False, art_style=STYLE_REALISTIC)
    assert _pick_visual_source(req, {}, 0) == "ai_image"
    assert _wants_stock_footage(req) is False


def test_moi_phong_cach_deu_cho_cung_mot_nguon_khi_auto():
    """`art_style` trả lời 'vẽ theo kiểu gì', KHÔNG phải 'lấy hình từ đâu'."""
    nguon = {
        _pick_visual_source(Req(art_style=s), {}, 0)
        for s in (STYLE_REALISTIC, STYLE_ANIME, STYLE_DOC, "", "documentary footage")
    }
    assert nguon == {"ai_image"}, f"art_style vẫn còn ảnh hưởng nguồn hình: {nguon}"


def test_cong_tac_tuong_minh_van_hoat_dong_day_du():
    """Bỏ bẫy không được làm mất quyền chọn stock của người dùng."""
    assert _pick_visual_source(Req(prefer_stock_video=True), {}, 0) == "stock_video"
    assert _pick_visual_source(Req(visual_source="stock_video"), {}, 0) == "stock_video"
    assert _pick_visual_source(Req(visual_source="ai_image", prefer_stock_video=True), {}, 0) == "ai_image"
    # Cấu hình riêng của TỪNG CẢNH thắng cấu hình cấp video.
    assert _pick_visual_source(Req(visual_source="ai_image"), {"visual_source": "stock_video"}, 3) == "stock_video"


def test_che_do_xen_ke_giu_nguyen_luat_theo_cam_xuc():
    req = Req(visual_source="mixed")
    # Cảnh mở màn luôn là ảnh AI: hook cần kiểm soát bố cục 100%.
    assert _pick_visual_source(req, {"emotion": "calm"}, 0) == "ai_image"
    assert _pick_visual_source(req, {"emotion": "calm"}, 2) == "stock_video"
    assert _pick_visual_source(req, {"emotion": "hook"}, 2) == "ai_image"


def test_tang_sinh_kich_ban_va_tang_render_dung_cung_mot_luat():
    """Lệch nhau là kịch bản viết image_prompt kiểu này mà render lại lấy hình kiểu khác."""
    for kw in (
        {"art_style": STYLE_REALISTIC},
        {"prefer_stock_video": True},
        {"visual_source": "stock_video"},
        {"visual_source": "ai_image", "art_style": STYLE_REALISTIC},
    ):
        req = Req(**kw)
        muon_stock = _wants_stock_footage(req)
        # Ở chế độ "mixed" hai tầng cố ý khác nhau (xem docstring _wants_stock_footage),
        # nên chỉ đối chiếu các chế độ còn lại.
        if req.visual_source != "mixed":
            canh_dau_bo_qua = _pick_visual_source(req, {}, 1) == "stock_video"
            assert muon_stock == canh_dau_bo_qua, kw


# ---------------------------------------------------------------------------
# 2. Thứ tự tầng dự phòng sinh ảnh
# ---------------------------------------------------------------------------
def test_pollinations_dung_truoc_pexels_photo():
    """Dự phòng cho ẢNH AI phải là ảnh AI khác, không phải ảnh stock tĩnh.

    Kiểm bằng vị trí xuất hiện trong mã nguồn: hàm này là một chuỗi try/except tuần tự,
    nên thứ tự dòng CHÍNH LÀ thứ tự tầng. Bản cũ có Pexels trước Pollinations.
    """
    from services import image_router

    src = inspect.getsource(image_router.generate_image_with_fallback)
    vi_tri_gemini = src.index("generate_image_google")
    vi_tri_pollinations = src.index("_generate_pollinations")
    vi_tri_pexels = src.index("fetch_pexels_photo")
    vi_tri_gradient = src.index("_create_artistic_gradient_image")

    assert vi_tri_gemini < vi_tri_pollinations < vi_tri_pexels < vi_tri_gradient, (
        "Thứ tự tầng phải là: Gemini → Pollinations FLUX → Pexels photo → gradient"
    )


def test_pexels_photo_khong_nhan_nguyen_prompt_dai_lam_tu_khoa():
    """LỖI CŨ: truyền cả "Extreme close-up shot of ... 8k, Unreal Engine 5" cho Pexels.

    Đúng loại truy vấn rác mà `stock_query_from_prompt` sinh ra để tránh.
    """
    from services import image_router

    src = inspect.getsource(image_router.generate_image_with_fallback)
    doan_pexels = src[src.index("fetch_pexels_photo") - 400: src.index("fetch_pexels_photo") + 200]
    assert "stock_query_from_prompt" in doan_pexels


def test_moi_tang_deu_ghi_lai_nguon_that():
    """Không ghi thì không ai biết ảnh đến từ đâu — xem _summarize_visual_sources."""
    from services import image_router

    src = inspect.getsource(image_router.generate_image_with_fallback)
    for ma in ("gemini_image", "pollinations_flux", "pexels_photo", "gradient_offline", "cache:image"):
        assert f'_ghi("{ma}")' in src, f"tầng {ma} không ghi nguồn"


# ---------------------------------------------------------------------------
# 3. Ghi .env — hai lỗi lộ ra khi thêm giao diện Quản lý Key API
# ---------------------------------------------------------------------------
def test_key_moi_duoc_ghi_kem_chu_thich_dung_cua_no():
    """LỖI CŨ: mọi key mới đều bị dán comment "# Thư mục lưu toàn bộ dữ liệu sinh ra..."

    Comment đó viết cho CUSTOM_ASSETS_DIR. Không hỏng gì khi chạy, nhưng biến file cấu
    hình — thứ người dùng phải tự đọc khi gỡ lỗi — thành file nói dối về nội dung của nó.
    """
    import tempfile

    import config

    goc = config.ENV_FILE
    d = tempfile.mkdtemp()
    config.ENV_FILE = os.path.join(d, ".env")
    try:
        with open(config.ENV_FILE, "w", encoding="utf-8") as f:
            f.write("GEMINI_API_KEY=g1\n")
        config.write_env_value("PIXABAY_API_KEY", "pb-123")
        noi_dung = open(config.ENV_FILE, encoding="utf-8").read()
        assert "PIXABAY_API_KEY=pb-123" in noi_dung
        assert "Thư mục lưu toàn bộ dữ liệu" not in noi_dung
        assert "pixabay.com/api/docs" in noi_dung, "phải là chú thích của chính Pixabay"
    finally:
        config.ENV_FILE = goc


def test_gia_tri_rong_thi_XOA_dong_thay_vi_ghi_key_bang_rong():
    """LỖI CŨ: hạ từ nhiều key Gemini xuống 2 làm .env mọc 9 dòng `GEMINI_API_KEY_i=` trắng.

    Mỗi dòng lại kèm một comment sai. Toàn bộ code đọc env đều dùng `os.getenv(...) or
    <mặc định>`, nên rỗng và không tồn tại là một — xoá mới là hành vi đúng.
    """
    import tempfile

    import config

    goc = config.ENV_FILE
    d = tempfile.mkdtemp()
    config.ENV_FILE = os.path.join(d, ".env")
    try:
        with open(config.ENV_FILE, "w", encoding="utf-8") as f:
            f.write("GEMINI_API_KEY=g1\nGEMINI_API_KEY_1=g2\nGEMINI_API_KEY_2=g3\nPORT=8000\n")
        config.write_env_value("GEMINI_API_KEY_1", "")
        config.write_env_value("GEMINI_API_KEY_2", "")
        config.write_env_value("GEMINI_API_KEY_7", "")  # chưa từng tồn tại → không sao
        noi_dung = open(config.ENV_FILE, encoding="utf-8").read()

        assert "GEMINI_API_KEY_1" not in noi_dung
        assert "GEMINI_API_KEY_2" not in noi_dung
        assert "GEMINI_API_KEY=g1" in noi_dung, "key chính không được mất"
        assert "PORT=8000" in noi_dung, "dòng khác không được mất"
        # Và không để lại dòng trống chồng nhau sau khi xoá.
        assert "\n\n\n" not in noi_dung
    finally:
        config.ENV_FILE = goc


def test_chu_thich_mo_coi_bi_don_theo_khi_xoa_key():
    import tempfile

    import config

    goc = config.ENV_FILE
    d = tempfile.mkdtemp()
    config.ENV_FILE = os.path.join(d, ".env")
    try:
        with open(config.ENV_FILE, "w", encoding="utf-8") as f:
            f.write("GEMINI_API_KEY=g1\n")
        config.write_env_value("PIXABAY_API_KEY", "pb")
        config.write_env_value("PIXABAY_API_KEY", "")
        noi_dung = open(config.ENV_FILE, encoding="utf-8").read()
        assert "PIXABAY" not in noi_dung, "xoá key phải xoá cả chú thích của nó"
    finally:
        config.ENV_FILE = goc


if __name__ == "__main__":
    ok = fail = 0
    for ten, fn in sorted(list(globals().items())):
        if ten.startswith("test_") and callable(fn):
            try:
                fn()
                ok += 1
                print(f"  PASS  {ten}")
            except AssertionError as e:
                fail += 1
                print(f"  FAIL  {ten}: {e}")
    print(f"\n{ok} pass, {fail} fail")
    sys.exit(1 if fail else 0)
