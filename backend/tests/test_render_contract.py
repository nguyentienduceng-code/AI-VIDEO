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


# Trường NỘI DUNG — chữ nghĩa/tài nguyên riêng của TỪNG video. Preset lưu KIỂU DÁNG nên
# tuyệt đối không được chứa chúng: nạp preset cũ mà chữ của video cũ hiện ra là sai hẳn
# kỳ vọng người dùng. Thêm field chữ mới thì thêm tên vào đây.
_TRUONG_NOI_DUNG = {
    "scenes", "mode", "topic", "hook_text", "hook_quote", "outro_text",
    "watermark_text", "cta_text", "negative_prompt", "character_description",
    "gemini_api_key", "upload_session_id", "cover_image_session_id",
}

# Trường chỉ có ý nghĩa lúc render, không phải lựa chọn thẩm mỹ để lưu lại.
_TRUONG_CHI_RENDER = {
    "aspect_ratio", "cover_image_position", "use_veo", "use_veo_ambient_audio",
    "use_fixed_seed", "use_gpu_encode", "use_fast_assembly",
}

# Preset có quyền đặt tên riêng cho những thứ KHÔNG phải ánh xạ 1-1 sang render.
_PRESET_RIENG = {"name", "art_style", "voice", "target_duration", "narration_tone"}

_REQ_ATTR_RE = re.compile(r"\breq\.([a-zA-Z_][a-zA-Z0-9_]*)")


def test_preset_khong_chua_truong_noi_dung():
    """Preset lưu KIỂU DÁNG, không lưu NỘI DUNG.

    outro_text từng lọt vào PresetRequest một mình — thành ngoại lệ duy nhất phá quy tắc
    mà hook_text/hook_quote/topic/watermark_text/cta_text đều tuân theo, và cũng chưa bao
    giờ được frontend gửi hay khôi phục nên chỉ là một field chết.
    """
    from main import PresetRequest

    lot = sorted(set(PresetRequest.model_fields) & _TRUONG_NOI_DUNG)
    assert not lot, (
        f"PresetRequest chứa trường nội dung: {lot}. Preset chỉ lưu kiểu dáng — "
        "nạp lại preset mà chữ của video cũ hiện ra là sai kỳ vọng người dùng."
    )


def test_preset_va_render_goi_cung_mot_ten_cho_cung_mot_thu():
    """Mọi tuỳ chọn kiểu dáng phải mang ĐÚNG MỘT tên ở cả hai model.

    LỖI CŨ: nhạc nền chính là `bgm_track` ở cả hai, nhưng nhạc mở màn là
    `intro_bgm_track` bên render và `intro_bgm` bên preset. Lệch tên kiểu này không gây
    lỗi ngay — nó chỉ chờ tới lúc ai đó gán thẳng preset sang payload render và giá trị
    im lặng rơi về mặc định.
    """
    from main import PresetRequest

    pf = set(PresetRequest.model_fields)
    rf = set(RenderVideoRequest.model_fields)

    la_mat = sorted(pf - rf - _PRESET_RIENG)
    assert not la_mat, (
        f"PresetRequest có {la_mat} nhưng RenderVideoRequest không có tên tương ứng — "
        "hoặc gõ sai tên, hoặc hai bên đang gọi cùng một thứ bằng hai tên khác nhau."
    )

    thieu = sorted(rf - pf - _TRUONG_NOI_DUNG - _TRUONG_CHI_RENDER)
    assert not thieu, (
        f"RenderVideoRequest có tuỳ chọn kiểu dáng {thieu} mà preset không lưu được — "
        "người dùng chỉnh xong lưu preset, nạp lại thì mất."
    )


def _pipeline_source(main_py_source: str) -> str:
    """Thân hàm _run_render_pipeline — nơi DUY NHẤT nhận RenderVideoRequest.

    Phải cắt đúng hàm này: gần như MỌI endpoint trong main.py đều đặt tên tham số là
    `req`, nhưng của các model khác (GenerateScriptRequest, PresetRequest...). Quét cả
    file sẽ báo động giả hàng loạt và test bị vô hiệu hoá vì không ai tin nó nữa.
    """
    start = main_py_source.index("async def _run_render_pipeline")
    rest = main_py_source[start:]
    # Hàm kết thúc ở định nghĩa top-level kế tiếp (không thụt đầu dòng).
    end = re.search(r"\n(?=(?:async def |def |@app\.|class ))", rest)
    return rest[: end.start()] if end else rest


def test_moi_field_req_doc_deu_ton_tai_trong_model():
    """
    Mọi `req.<field>` trong main.py phải có thật trong RenderVideoRequest.

    ĐÂY LÀ LƯỚI CHO MỘT SỰ CỐ THẬT: bản Outro/Dynamic-BGM thêm `req.intro_bgm_track` vào
    pipeline nhưng QUÊN khai báo field ở model. Pydantic mặc định BỎ IM LẶNG khoá lạ, nên
    frontend gửi đúng tên vẫn bị vứt, rồi MỌI job render chết bằng AttributeError — ở vị
    trí ngoài khối try nên lỗi thoát khỏi BackgroundTask và job đứng ở "pending" vĩnh
    viễn, giao diện không hiện lỗi gì.

    Không lớp nào trong bốn cổng chất lượng bắt được: cú pháp hợp lệ, ruff không kiểm tra
    thuộc tính Pydantic, và nhánh lỗi chỉ nổ lúc chạy thật.
    """
    main_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
    with open(main_py, encoding="utf-8") as f:
        source = f.read()

    fields = set(RenderVideoRequest.model_fields)
    duoc_doc = set(_REQ_ATTR_RE.findall(_pipeline_source(source)))
    thieu = sorted(a for a in duoc_doc if a not in fields and not a.startswith("model_"))

    assert not thieu, (
        "main.py đọc req.{" + ", ".join(thieu) + "} nhưng RenderVideoRequest không khai báo. "
        "Pydantic bỏ im lặng khoá lạ → AttributeError giữa job render."
    )


# ── Hợp đồng thứ HAI: master_kwargs → master_audio_and_export ────────────────────
# Đây là một ĐƯỜNG DỮ LIỆU HOÀN TOÀN KHÁC với render_kwargs ở trên, và cho tới giờ chưa
# có test nào bao phủ. Nó đã sinh ra đúng một loại bug BA lần:
#   - narration_tone + use_pattern_interrupt: có trong model và passthrough nhưng không
#     được nhét vào master_kwargs → khoá an toàn "tắt Pattern Interrupt ở tone trầm"
#     chưa bao giờ chạy thật, và toggle của user bị bỏ qua hoàn toàn;
#   - hook_duration: render_worker đọc nhưng main.py quên set → cú chớp Pattern Interrupt
#     rơi vào giữa hook.
# Mọi lần đều im lặng tuyệt đối: master_kwargs.get(...) chỉ trả về giá trị mặc định.

_RE_MASTER_GET = re.compile(r'master_kwargs\.get\(\s*["\']([a-zA-Z_][a-zA-Z0-9_]*)["\']')


def _nguon(mod_path: str) -> str:
    with open(mod_path, encoding="utf-8") as f:
        return f.read()


def _khoa_master_kwargs_trong_main() -> set:
    """Các khoá của literal `master_kwargs = dict(...)` trong main.py."""
    src = _nguon(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py"))
    i = src.index("master_kwargs = dict(")
    j = src.index("\n        )", i)
    return set(re.findall(r"^\s{12}([a-zA-Z_][a-zA-Z0-9_]*)\s*=", src[i:j], re.M))


# Khoá render_worker đọc với giá trị mặc định mà main.py CỐ Ý không set: chúng không phải
# lựa chọn của người dùng (không có trong RenderVideoRequest, không có ô nào trên UI), chỉ
# là hằng số nội bộ của bước master. Thêm tên vào đây là một QUYẾT ĐỊNH có ý thức — đó
# chính là điều test này muốn ép.
_MASTER_MAC_DINH_CO_Y = {"add_vignette", "progress_bar"}


def test_render_worker_khong_doc_khoa_master_kwargs_khong_ai_set():
    """Mọi `master_kwargs.get("X")` trong render_worker phải có X trong dict ở main.py.

    Ngoại lệ duy nhất là _MASTER_MAC_DINH_CO_Y. Nếu một khoá vừa nằm trong ngoại lệ vừa
    là field của RenderVideoRequest thì đó KHÔNG còn là hằng số nội bộ nữa mà là lựa chọn
    của user đang bị nuốt — bắt luôn ở đây.
    """
    from services import render_worker

    doc = set(_RE_MASTER_GET.findall(inspect.getsource(render_worker)))
    set_o_main = _khoa_master_kwargs_trong_main()

    thieu = sorted(doc - set_o_main - _MASTER_MAC_DINH_CO_Y)
    assert not thieu, (
        f"render_worker đọc master_kwargs[{', '.join(thieu)}] nhưng main.py không bao giờ "
        "set — giá trị luôn rơi về mặc định, không một dòng lỗi nào. Nếu đó là hằng số "
        "nội bộ có chủ ý, thêm tên vào _MASTER_MAC_DINH_CO_Y."
    )

    lua_chon_bi_nuot = sorted(
        (_MASTER_MAC_DINH_CO_Y - set_o_main) & set(RenderVideoRequest.model_fields)
    )
    assert not lua_chon_bi_nuot, (
        f"{lua_chon_bi_nuot} vừa là field người dùng đặt được, vừa nằm trong danh sách "
        "'mặc định có chủ ý' — lựa chọn của user đang bị nuốt im lặng."
    )


def test_hai_duong_master_truyen_cung_bo_tham_so_hieu_ung():
    """Đường worker và nhánh inline phải truyền CÙNG các tham số hiệu ứng.

    Hai nhánh này gọi cùng một hàm nhưng dựng tham số ở hai chỗ tách rời; lệch nhau
    nghĩa là bật/tắt FastAssembly lại ra hai video khác nhau.
    """
    src = _nguon(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py"))
    i = src.index("master_audio_and_export,")
    inline = src[i:src.index("\n                )", i)]

    o_main = _khoa_master_kwargs_trong_main()
    for ten in ("narration_tone", "use_pattern_interrupt", "hook_duration",
                "bgm_volume_segments", "use_audio_ducking"):
        assert ten in o_main, f"master_kwargs (đường worker) thiếu {ten}"
        assert f"{ten}=" in inline, f"nhánh inline gọi master_audio_and_export thiếu {ten}"


def test_master_audio_and_export_nhan_moi_khoa_duoc_truyen():
    """Gõ sai tên khoá ở main.py thì hàm đích không có tham số đó → TypeError giữa job."""
    from services.audio_mix_service import master_audio_and_export

    nhan = set(inspect.signature(master_audio_and_export).parameters)
    # Khoá chỉ dành cho render_worker (nó tự dịch sang tham số khác), không phải cho hàm đích.
    _CHI_WORKER = {"subtitle_style", "hook_effect", "use_gpu", "progress_bar", "add_vignette"}
    la = sorted(_khoa_master_kwargs_trong_main() - nhan - _CHI_WORKER)
    assert not la, (
        f"master_kwargs chứa khoá mà master_audio_and_export không nhận: {la}"
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
