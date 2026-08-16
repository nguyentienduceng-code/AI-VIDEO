"""
Test cho nguồn chữ của phần đuôi video — resolve_outro_text().

Chạy:  python tests/test_outro_text.py    (từ thư mục backend/, không cần pytest)
       pytest tests/test_outro_text.py

VÌ SAO CÓ FILE NÀY: `cta_text` (câu kêu gọi hành động Gemini sinh riêng cho đuôi video)
từng là FIELD CHẾT — có trong `RenderVideoRequest`, frontend gửi lên đều đặn, nhưng
KHÔNG nơi nào đọc. Outro vì thế rơi thẳng về `hook_text`, tức đem CÂU MỞ ĐẦU ra làm lời
chốt, thứ người xem vừa nghe ở giây đầu tiên.

Đây là bug "khai báo nhưng không nối dây" — dòng bug tái diễn của dự án này, luôn nằm ở
CHỖ NỐI giữa hai tầng chứ không phải trong logic một hàm. Test hợp đồng sẵn có
(test_render_contract.py) đối chiếu ba tập hợp tên field, nhưng một field có mặt đủ
trong cả ba tập vẫn có thể chẳng ai đọc tới — nên ở đây có thêm một test chạy THẬT qua
`render_final_video` và bắt lấy chuỗi mà clip outro nhận được.

Phép chọn này còn được gõ lại ở BA nơi (main.py lúc tính tổng thời lượng, video_service
lúc dựng clip, /api/timing-profile để UI hiện trước con số) và chỉ được giữ khớp bằng
một dòng comment dặn "PHẢI khớp từng chữ". Với 2 hiệu ứng outro có thời lượng ĐỘNG theo
độ dài chữ, lệch nguồn chữ là lệch luôn thời lượng: UI hiện một đằng, video ra một nẻo.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PIL import Image

from services.video_service import resolve_outro_text

CTA = "Lưu video để khám phá thêm bí mật văn học!"
HOOK = "Cuốn sách triệu bản suýt bị giấu vĩnh viễn"
USER = "Đọc và nhận xét"


def test_uu_tien_chu_user_go_tay():
    assert resolve_outro_text(USER, CTA, HOOK) == USER


def test_khong_go_tay_thi_lay_cta_gemini():
    """Đây chính là hành vi đã hỏng: trước khi vá, nhánh này trả về hook_text."""
    assert resolve_outro_text("", CTA, HOOK) == CTA
    assert resolve_outro_text(None, CTA, HOOK) == CTA


def test_khong_co_cta_moi_roi_ve_hook():
    assert resolve_outro_text("", "", HOOK) == HOOK
    assert resolve_outro_text(None, None, HOOK) == HOOK


def test_chuoi_toan_khoang_trang_coi_nhu_rong():
    """Ô nhập để trống trên UI có thể gửi lên vài dấu cách — không được coi là "có chữ",
    nếu không thì outro hiện một khoảng trắng và nuốt mất cả CTA lẫn hook."""
    assert resolve_outro_text("   ", CTA, HOOK) == CTA
    assert resolve_outro_text("\n\t ", "", HOOK) == HOOK


def test_tat_ca_rong_tra_chuoi_rong():
    """build_cta_card_hook tự ẩn dòng chữ khi rỗng — phải trả "" chứ không phải None."""
    assert resolve_outro_text("", "", "") == ""
    assert resolve_outro_text(None, None, None) == ""


def test_cta_text_co_trong_ca_hai_danh_sach_cau_noi():
    """Thiếu ở một trong hai danh sách là field lại chết y như cũ, không một dòng lỗi."""
    from main import RENDER_PASSTHROUGH_FIELDS, RenderVideoRequest
    from services.video_service import RENDER_KWARG_KEYS

    assert "cta_text" in RenderVideoRequest.model_fields
    assert "cta_text" in RENDER_PASSTHROUGH_FIELDS, "main.py không chuyển cta_text sang render"
    assert "cta_text" in RENDER_KWARG_KEYS, "render_final_video coi cta_text là key lạ"


def test_ba_noi_deu_goi_chung_mot_ham():
    """Chống việc ai đó gõ lại phép chọn `outro_text or hook_text` ngay tại chỗ.

    Bản cũ giữ ba nơi khớp nhau bằng một dòng comment dặn dò — không có gì cưỡng chế.
    """
    import inspect

    import main
    from services import video_service
    from services import pipeline_orchestrator

    src_main = inspect.getsource(main)
    src_vs = inspect.getsource(video_service)
    src_orch = inspect.getsource(pipeline_orchestrator)

    assert (src_main + src_orch).count("resolve_outro_text(") >= 3, (
        "main/orchestrator phải gọi resolve_outro_text ở cả 2 chỗ (tính tổng thời lượng + "
        "/api/timing-profile), cộng dòng import"
    )
    for xau in ("req.outro_text or req.hook_text", 'kwargs.get("outro_text") or hook_text'):
        assert xau not in src_main and xau not in src_vs and xau not in src_orch, (
            f"phép chọn nguồn chữ outro bị gõ lại tại chỗ: {xau!r}"
        )


def test_noi_day_cta_toi_clip_outro():
    """Chạy ĐÚNG vòng lặp render_final_video và bắt lấy chuỗi clip outro thật sự nhận.

    Không có test này thì cta_text có thể nằm đủ trong mọi danh sách mà vẫn không ai đọc
    — đúng trạng thái nó đã ở suốt nhiều bản render.
    """
    from services import hook_engine
    import services.video_service as vs

    class _Stop(BaseException):
        """Kế thừa BaseException CÓ CHỦ Ý, không phải Exception.

        Nhánh Outro Engine bọc trong `except Exception` và chỉ ghi log rồi render tiếp,
        nên một Exception thường bị NUỐT: test vẫn đúng kết quả nhưng phải trả tiền cho
        trọn một lần render (đo được 13s/lượt thay vì ~1s).
        """

    tmp = tempfile.mkdtemp(prefix="avm_cta_")
    img = os.path.join(tmp, "f.png")
    Image.fromarray(np.full((192, 108, 3), 128, np.uint8)).save(img)

    def _chay(outro_text, cta_text, hook_text):
        assets = [{"image_path": img, "duration": 2.0, "start_time": 0.0,
                   "sfx": "", "audio_path": "", "text": "x"}]
        bat = {}

        def _spy(cover, text, w, h, dur, *a, **k):
            bat["text"] = text
            raise _Stop()

        goc = hook_engine.build_cta_card_hook
        hook_engine.build_cta_card_hook = _spy
        try:
            vs.render_final_video(
                assets, os.path.join(tmp, "out.mp4"),
                use_sfx=False, progress_logger=None,
                hook_effect="none", outro_effect="cta_card",
                outro_text=outro_text, cta_text=cta_text, hook_text=hook_text,
            )
        except _Stop:
            pass
        finally:
            hook_engine.build_cta_card_hook = goc
        return bat.get("text", "<KHÔNG GỌI TỚI CLIP OUTRO>")

    assert _chay(USER, CTA, HOOK) == USER, "chữ user gõ tay bị bỏ qua"
    assert _chay("", CTA, HOOK) == CTA, (
        "cta_text KHÔNG tới được clip outro — vẫn là field chết"
    )
    assert _chay("", "", HOOK) == HOOK, "mất luôn dự phòng cuối cùng"


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
