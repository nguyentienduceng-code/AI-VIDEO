"""
Test hợp đồng giữa API (RenderVideoRequest) và tầng render (render_final_video).

Chạy:  python tests/test_render_contract.py    (từ thư mục backend/)
       pytest tests/test_render_contract.py

VÌ SAO CÓ FILE NÀY: render_final_video nhận tuỳ chọn qua **kwargs, mà **kwargs im
lặng ở cả hai chiều — thiếu key thì dùng default, thừa/sai tên key thì bỏ qua, không
lỗi nào cả. Bug thật đã xảy ra: hook_sfx_volume có trong model, frontend gửi lên đều
đặn, video_service đọc đúng tên, nhưng main.py quên nhét vào render_kwargs → thanh
trượt của user vô hiệu hoàn toàn qua nhiều bản render mà không ai biết.

Ba tập hợp phải luôn khớp nhau:
  RenderVideoRequest (model)  ⊇  RENDER_PASSTHROUGH_FIELDS (main.py)
  RENDER_PASSTHROUGH_FIELDS   →  tham số tường minh HOẶC RENDER_KWARG_KEYS
  RENDER_KWARG_KEYS           ==  các kwargs.get(...) thật trong mã nguồn
"""
import inspect
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import RENDER_PASSTHROUGH_FIELDS, RenderVideoRequest, build_render_kwargs
from services import video_service
from services.video_service import RENDER_KWARG_KEYS, render_final_video

_SIG = inspect.signature(render_final_video)
_EXPLICIT_PARAMS = {
    name for name, p in _SIG.parameters.items() if p.kind is not p.VAR_KEYWORD
}


def _request(**overrides) -> RenderVideoRequest:
    return RenderVideoRequest(topic="test", mode="storyteller", scenes=[], **overrides)


def test_moi_field_passthrough_deu_ton_tai_trong_model():
    """Gõ sai tên field ở RENDER_PASSTHROUGH_FIELDS phải bị bắt ngay, chứ không đợi
    tới lúc getattr ném AttributeError giữa một job render dài."""
    fields = set(RenderVideoRequest.model_fields)
    thieu = [f for f in RENDER_PASSTHROUGH_FIELDS if f not in fields]
    assert not thieu, f"RenderVideoRequest không có field: {thieu}"


def test_moi_field_passthrough_deu_toi_duoc_render():
    """Mỗi field chuyển thẳng qua phải hoặc là tham số tường minh của
    render_final_video, hoặc nằm trong danh sách kwargs được hàm đó thật sự đọc.
    Không thoả = giá trị bị **kwargs nuốt mất, đúng kịch bản bug hook_sfx_volume."""
    mo_coi = [
        f for f in RENDER_PASSTHROUGH_FIELDS
        if f not in _EXPLICIT_PARAMS and f not in RENDER_KWARG_KEYS
    ]
    assert not mo_coi, (
        f"những field này gửi đi nhưng render_final_video không bao giờ đọc: {mo_coi}"
    )


def test_moi_kwarg_render_doc_deu_co_nguoi_cung_cap():
    """Chiều ngược lại: tuỳ chọn mà render đọc nhưng API không bao giờ gửi = tuỳ chọn
    chết, vĩnh viễn chạy bằng giá trị mặc định."""
    khong_ai_gui = RENDER_KWARG_KEYS - set(RENDER_PASSTHROUGH_FIELDS)
    assert not khong_ai_gui, (
        f"render_final_video đọc nhưng main.py không gửi: {sorted(khong_ai_gui)}"
    )


def test_render_kwarg_keys_khop_ma_nguon_that():
    """RENDER_KWARG_KEYS phải phản ánh đúng các kwargs.get("...") trong video_service.
    Thêm một kwargs.get mới mà quên khai báo thì cảnh báo 'tham số không hỗ trợ' sẽ
    báo nhầm chính tuỳ chọn hợp lệ đó."""
    src = inspect.getsource(video_service)
    thuc_te = set(re.findall(r'kwargs\.get\(\s*"([a-z_]+)"', src))
    thuc_te |= set(re.findall(r'kwargs\[\s*"([a-z_]+)"\s*\]', src))

    assert thuc_te == set(RENDER_KWARG_KEYS), (
        f"lệch nhau — chỉ có trong mã nguồn: {sorted(thuc_te - set(RENDER_KWARG_KEYS))}, "
        f"chỉ có trong RENDER_KWARG_KEYS: {sorted(set(RENDER_KWARG_KEYS) - thuc_te)}"
    )


def test_build_render_kwargs_khong_sinh_key_la():
    """Mọi key dựng ra phải được render_final_video chấp nhận, nếu không nó sẽ rơi vào
    nhánh cảnh báo 'tham số không được hỗ trợ'."""
    kwargs = build_render_kwargs(_request(), "9:16", "storyteller", None)

    la = set(kwargs) - _EXPLICIT_PARAMS - set(RENDER_KWARG_KEYS)
    assert not la, f"key không ai đọc: {sorted(la)}"


def test_hook_sfx_volume_di_toi_noi_khong_bien_dang():
    """Chính bug cũ, đóng đinh lại: giá trị user kéo trên thanh trượt phải tới được
    render nguyên vẹn — không rơi về mặc định 1.0, không bị nhân/chia 100."""
    for value in (0.0, 0.3, 1.0, 2.0):
        kwargs = build_render_kwargs(_request(hook_sfx_volume=value), "9:16", "storyteller", None)
        assert kwargs["hook_sfx_volume"] == value, (
            f"gửi {value} nhưng render nhận {kwargs.get('hook_sfx_volume')}"
        )


def test_don_vi_hai_thang_do_khong_bi_lan():
    """RenderVideoRequest dùng HỆ SỐ (1.0), PresetRequest dùng PHẦN TRĂM (100).
    Nếu ai đó 'thống nhất' hai mặc định này thành một số, âm lượng sẽ lệch 100 lần."""
    from main import PresetRequest

    assert RenderVideoRequest.model_fields["hook_sfx_volume"].default == 1.0
    assert PresetRequest.model_fields["hook_sfx_volume"].default == 100


def test_bien_gia_tri_hop_le_duoc_chan_o_tang_api():
    """Client quên chia 100 (gửi 50) phải bị chặn ngay tại API, không lọt xuống mixer."""
    from pydantic import ValidationError

    for hop_le in (0, 1, 1.5, 2.0):
        _request(hook_sfx_volume=hop_le)

    for bat_hop_le in (-0.1, 2.5, 50, 100):
        try:
            _request(hook_sfx_volume=bat_hop_le)
            raise AssertionError(f"{bat_hop_le} lẽ ra phải bị từ chối")
        except ValidationError:
            pass


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
