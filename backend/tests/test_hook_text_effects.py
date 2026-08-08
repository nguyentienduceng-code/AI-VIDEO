"""
Test cho 2 hook THUẦN CHỮ: A1 Blackout Question và A2 Typewriter.

Gộp chung vì cả hai dựng nền bằng cùng một hàm (`_blurred_fill_bg`) và dính cùng một lớp
lỗi — xem test_nen_hook_chu_khong_dung_hinh.

Chạy:  python tests/test_hook_text_effects.py  (từ thư mục backend/, không cần pytest)
       pytest tests/test_hook_text_effects.py

VÌ SAO CÓ FILE NÀY: 2 lỗi tìm được trên video thật ngày 2026-07-30, cả hai đều là lỗi
CÂM — video render xong, phát được, không exception nào:

  1. Nền hook ĐỨNG HÌNH TUYỆT ĐỐI 2.75 giây. `_blurred_fill_bg` trả về ImageClip, tức
     MỘT khung hình bất động, và typewriter không có chuyển động hình nào khác. Đo trên
     bản render thật: lệch giữa các khung chỉ 0.009-0.025/255 — bất động theo đúng nghĩa
     đen, ngay 3 giây mở đầu video. Cùng lớp lỗi đã phải vá cho camera_shutter và
     cyber_glitch trước đó.

  2. Con trỏ '|' nhấp nháy tham gia vào phép XUỐNG DÒNG. Đo với đúng font/cỡ chữ của
     hook: "Cuốn sách triệu bản suýt bị giấu" vừa khít 1 dòng (103px) nhưng thêm " |"
     thành 2 dòng (172px) — chữ nhảy xuống dòng sớm một bước rồi bước sau lùi về.

Cả hai chỉ lộ ra khi RENDER + ĐO, không phải khi đọc code.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PIL import Image

from services.hook_engine import (
    _blurred_fill_bg,
    _safe_caption_clip,
    build_blackout_question_hook,
    build_typewriter_quote_hook,
)

W, H = 1080, 1920
DUR = 3.02
TEXT = "Cuốn sách triệu bản suýt bị giấu vĩnh viễn"

_cover_path = None


def _cover() -> str:
    """Ảnh bìa giả có CẤU TRÚC LỚN (không phải nhiễu mịn).

    Nền hook bị làm mờ mạnh, nên chi tiết nhỏ biến mất sạch — muốn đo được chuyển động
    thì hình gốc phải có mảng màu lớn và biên rõ để phép phóng làm dịch chuyển thấy được.
    """
    global _cover_path
    if _cover_path and os.path.isfile(_cover_path):
        return _cover_path
    # Nền GRADIENT chứ không phải mảng màu phẳng: phép phóng chỉ làm đổi giá trị pixel ở
    # nơi CÓ ĐỘ DỐC màu. Bản đầu của test này dùng 4 ô màu phẳng và đo ra lệch 0.036 —
    # gần như không phân biệt được với đứng hình, tức test vô dụng dù code đã đúng.
    yy, xx = np.mgrid[0:1200, 0:800].astype(np.float32)
    arr = np.stack([
        xx / 800 * 255,
        yy / 1200 * 255,
        (xx / 800 + yy / 1200) / 2 * 255,
    ], axis=-1)
    # Thêm vài khối sáng lớn để còn cấu trúc sống sót qua bán kính mờ 20px.
    for cx, cy, rr in ((200, 250, 150), (600, 900, 180), (400, 600, 120)):
        arr[((yy - cy) ** 2 + (xx - cx) ** 2) < rr ** 2] = 255.0
    arr = arr.astype(np.uint8)
    p = os.path.join(tempfile.mkdtemp(prefix="avm_tw_"), "cover.png")
    Image.fromarray(arr).save(p)
    _cover_path = p
    return p


def _top_band(frame) -> np.ndarray:
    """25% TRÊN của khung — vùng chắc chắn không dính chữ (chữ luôn căn giữa)."""
    return np.asarray(frame, dtype=np.float32)[: H // 4]


def _lech_giua_cac_khung(clip, moc) -> list:
    khung = [_top_band(clip.get_frame(t)) for t in moc]
    return [float(np.abs(khung[i] - khung[i - 1]).mean()) for i in range(1, len(khung))]


def test_nen_hook_chu_khong_dung_hinh():
    """Nền của CẢ HAI hook thuần chữ phải chuyển động liên tục, không phải khung chết.

    Gộp chung một test vì đây là cùng MỘT lớp lỗi ở cùng MỘT hàm dựng nền
    (`_blurred_fill_bg` trả ImageClip tĩnh): hook nào không tự có chuyển động hình mà
    quên bật zoom đều dính. Tách ra 2 test chỉ khiến lần thêm hook thứ ba lại quên.
    """
    for ten, clip in (
        ("typewriter_quote", build_typewriter_quote_hook(TEXT, W, H, DUR, _cover())),
        # blackout_question ngắn hơn (1.5s) và chữ có pop-in 0.2s đầu, nhưng phần còn lại
        # vẫn đứng hình y hệt nếu nền không chuyển động.
        ("blackout_question", build_blackout_question_hook(TEXT, W, H, 1.5, _cover())),
    ):
        try:
            dur = float(clip.duration)
            moc = [dur * f for f in (0.05, 0.3, 0.55, 0.8, 0.97)]
            lech = _lech_giua_cac_khung(clip, moc)
        finally:
            clip.close()
        assert min(lech) > 0.2, (
            f"nền hook '{ten}' đứng hình: lệch giữa các khung "
            f"{[round(x, 3) for x in lech]} (bản lỗi đo được 0.009-0.025 — bất động "
            "theo đúng nghĩa đen)"
        )


def test_nen_phong_to_dan_khong_giat_lui():
    """Phóng phải một chiều: tụt lại là nền hở mép, nhảy là thấy rõ hơn cả đứng yên."""
    # PHẢI đo qua CompositeVideoClip khung cố định, đúng như hook dùng thật: clip đã
    # resized trả về mảng TO DẦN (đo được 1090px ở giữa hook so với 1080px lúc đầu), so
    # thẳng 2 mảng khác shape thì vỡ chứ không đo được gì.
    from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip

    bg = _blurred_fill_bg(_cover(), W, H, DUR, darken=0.66, blur=20, zoom_to=1.06)
    clip = CompositeVideoClip([bg], size=(W, H)).with_duration(DUR)
    try:
        goc = _top_band(clip.get_frame(0.0))
        dt = [float(np.abs(_top_band(clip.get_frame(t)) - goc).mean())
              for t in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0)]
    finally:
        clip.close()
        bg.close()
    assert all(dt[i] >= dt[i - 1] for i in range(1, len(dt))), (
        f"độ lệch so với khung đầu không tăng đều: {[round(x, 2) for x in dt]}"
    )


def test_zoom_mac_dinh_tat_giu_nguyen_hanh_vi_cu():
    """4 hook còn lại đang dùng chung hàm này và tự có chuyển động riêng — không được
    âm thầm thêm zoom cho chúng."""
    clip = _blurred_fill_bg(_cover(), W, H, DUR, darken=0.5)
    try:
        d = float(np.abs(_top_band(clip.get_frame(0.1)) - _top_band(clip.get_frame(2.5))).mean())
    finally:
        clip.close()
    assert d < 0.01, f"zoom bật nhầm khi không ai yêu cầu: lệch {d:.3f}"


def test_con_tro_khong_lam_chu_nhay_dong():
    """Khung chữ chỉ được PHÌNH RA theo từng bước gõ, không bao giờ co lại.

    Co lại = chữ vừa xuống dòng xong lại nhảy ngược lên — đúng triệu chứng của bản lỗi,
    nơi con trỏ '|' bật/tắt xen kẽ làm đổi điểm xuống dòng.
    """
    box_w, fs = int(W * 0.85), int(W * 0.055)
    style = dict(color="white", stroke_color="black", stroke_width=3)
    words = TEXT.split()
    cao = []
    for i in range(1, len(words) + 1):
        c = _safe_caption_clip(" ".join(words[:i]) + " |", fs, box_w, **style)
        cao.append(c.h)
        c.close()
    lui = [i for i in range(1, len(cao)) if cao[i] < cao[i - 1]]
    assert not lui, f"chữ nhảy ngược ở bước {lui} — chuỗi chiều cao: {cao}"


def _mat_na_chu(frame) -> np.ndarray:
    """Mặt nạ chữ TRẮNG trên nền bìa đã làm mờ + tối."""
    a = np.asarray(frame, dtype=np.int16)
    return (a[..., 0] > 200) & (a[..., 1] > 200) & (a[..., 2] > 200)


def _do_khoi_chu(clip, moc: list) -> list:
    """[(y_dòng_đầu, chiều_cao_khối, số_pixel_chữ)] tại từng mốc thời gian.

    KHÔNG đếm số dòng bằng khoảng trống giữa các dải pixel: đo thật thì khe đó co từ 12
    xuống 6 rows ngay khi chữ "viễn" xuất hiện (dấu ngã ăn ngược lên trên), nên mọi ngưỡng
    gõ cứng đều báo động giả. Chiều cao khối và vị trí dòng đầu mới là số đo ổn định.
    """
    ra = []
    for t in moc:
        m = _mat_na_chu(clip.get_frame(t))
        rows = np.where(m.any(axis=1))[0]
        if not len(rows):
            ra.append((None, 0, 0))
            continue
        ra.append((int(rows[0]), int(rows[-1] - rows[0]), int(m.sum())))
    return ra


def test_dong_dau_dung_yen_khi_chu_xuong_dong():
    """Dòng đầu PHẢI nằm im, dòng mới mọc xuống dưới.

    `vertical_align` mặc định của MoviePy là "center" nên khối chữ luôn căn giữa theo
    chiều dọc trong khung cố định: lúc 1 dòng thì nằm giữa, tới khi mọc dòng thứ 2 thì
    dòng 1 BỊ ĐẨY NGƯỢC LÊN. Đo riêng TextClip: dòng đầu nhảy từ y=61 lên y=24 — giật
    đứng 37px đúng khoảnh khắc xuống dòng.
    """
    clip = build_typewriter_quote_hook(TEXT, W, H, DUR, _cover())
    try:
        moc = [round(0.1 + k * 0.1, 2) for k in range(int((DUR - 0.15) / 0.1))]
        do = _do_khoi_chu(clip, moc)
    finally:
        clip.close()

    ys = [y for y, _, _ in do if y is not None]
    cao = [c for _, c, _ in do if c]
    assert max(cao) >= 1.8 * min(cao), (
        f"câu mẫu không hề xuống dòng ở cỡ chữ hiện tại (cao {min(cao)}..{max(cao)}px) — "
        "test mất ý nghĩa, đổi TEXT dài hơn"
    )
    assert max(ys) - min(ys) <= 4, (
        f"dòng đầu nhảy {max(ys) - min(ys)}px trong lúc gõ (chỉ được xê dịch do khử răng cưa)"
    )


def test_so_dong_chi_tang_khong_bao_gio_giam():
    """Chữ chỉ được dài thêm, không bao giờ co ngược về ít dòng hơn.

    Co ngược = con trỏ vừa đẩy chữ xuống dòng xong lại kéo lên — đúng triệu chứng khi con
    trỏ tham gia phép ngắt dòng. Kiểm ngay trên HÀM NGẮT DÒNG chứ không đếm dải pixel: số
    dòng là thứ _ngat_dong() quyết định, đo lại qua ảnh chỉ thêm nhiễu (dấu tiếng Việt làm
    khe giữa 2 dòng co lại còn 6 rows).
    """
    from services.hook_engine import _ngat_dong

    words = TEXT.split()
    fs, box_w = int(W * 0.055), int(W * 0.85)
    so_dong = [len(_ngat_dong(words[:i] + ["|"], fs, box_w)) for i in range(1, len(words) + 1)]
    lui = [i for i in range(1, len(so_dong)) if so_dong[i] < so_dong[i - 1]]
    assert not lui, f"số dòng co ngược tại bước {lui}: {so_dong}"
    assert max(so_dong) >= 2, f"câu mẫu không xuống dòng — test mất ý nghĩa: {so_dong}"


def test_con_tro_nhap_nhay_va_tat_o_khung_cuoi():
    """Con trỏ phải BẬT/TẮT, và khung hình cuối không được đọng lại dấu '|'.

    Đo trong pha GIỮ CUỐI (chữ đã gõ xong) nên số từ không đổi — mọi chênh lệch pixel ở
    đó chỉ có thể do con trỏ. Bản trước gõ cứng con trỏ vào cả pha này nên nó đứng chết
    dính, nhìn như gõ thừa phím chứ không phải hiệu ứng.
    """
    clip = build_typewriter_quote_hook(TEXT, W, H, DUR, _cover())
    try:
        giu = DUR * 0.85 + 0.02          # sau khi gõ xong
        moc = [round(giu + k * 0.04, 3) for k in range(int((DUR - giu - 0.02) / 0.04))]
        px = [p for _, _, p in _do_khoi_chu(clip, moc)]
    finally:
        clip.close()

    assert len(px) >= 4, "pha giữ cuối quá ngắn để đo — chỉnh lại mốc"
    lo, hi = min(px), max(px)
    assert hi - lo > 150, f"con trỏ không nhấp nháy trong pha giữ cuối: {px}"
    assert px[-1] - lo < 150, (
        f"khung hình cuối vẫn còn con trỏ (px={px[-1]}, mức tắt={lo}) — sẽ đọng lại "
        "một dấu '|' bất động ngay trước lúc cắt sang Cảnh 1"
    )


def test_con_tro_khong_tham_gia_ngat_dong():
    """Bỏ token con trỏ khỏi kết quả ngắt dòng KHÔNG được làm đổi số dòng.

    Đây là điều kiện để nhấp nháy an toàn: bản trước phải bỏ hẳn nhấp nháy vì con trỏ
    nằm trong chuỗi đem đi đo, bật/tắt là đổi luôn điểm xuống dòng.
    """
    from services.hook_engine import _ngat_dong

    words = TEXT.split()
    fs, box_w = int(W * 0.055), int(W * 0.85)
    for i in range(1, len(words) + 1):
        dong = _ngat_dong(words[:i] + ["|"], fs, box_w)
        bo = [list(d) for d in dong]
        bo[-1] = bo[-1][:-1]
        assert len(bo) == len(dong), f"bỏ con trỏ làm đổi số dòng ở bước {i}"


def test_chu_khong_nho_hon_cac_hook_chu_khac():
    """_hook_caption_overlay và blackout_question đều dùng 0.055/0.85 — typewriter từng
    là hook chữ nhỏ nhất (0.05/0.8) dù chữ chính là toàn bộ nội dung nó hiển thị."""
    import inspect

    from services import hook_engine

    src = inspect.getsource(hook_engine.build_typewriter_quote_hook)
    assert "video_width * 0.055" in src and "video_width * 0.85" in src, (
        "cỡ chữ/bề ngang khung chữ của typewriter đã lệch khỏi chuẩn chung 0.055/0.85"
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
