"""
Test hợp đồng giữa component React và store Zustand.

Chạy:  python tests/test_frontend_store_contract.py    (từ thư mục backend/)

VÌ SAO CÓ FILE NÀY (và vì sao nó nằm ở backend): mỗi component lấy state qua một khối
`useAppStore(useShallow((s) => ({ ... })))`. Đọc `ctx.X` mà quên khai báo X trong khối
đó thì JavaScript KHÔNG báo lỗi — nó trả undefined. Undefined chạy tiếp vào phép tính
thành NaN, JSON.stringify biến NaN thành null, và máy chủ từ chối cả request.

Đã xảy ra thật: `hook_sfx_volume: ctx.hookSfxVolume / 100` trong khi selector thiếu
`hookSfxVolume` → mọi lần bấm Render đều trả 422, không một dòng lỗi nào ở phía trình
duyệt chỉ ra nguyên nhân.

Dự án chưa có bộ chạy test JavaScript, nên kiểm tra bằng cách đọc mã nguồn — thô sơ
nhưng bắt đúng lớp lỗi cần bắt, và chạy chung với các test còn lại.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.normpath(os.path.join(_BACKEND, "..", "frontend", "src"))

_SELECTOR_RE = re.compile(r"useAppStore\(\s*useShallow\(", re.DOTALL)
_KEY_RE = re.compile(r"(\w+)\s*:\s*s\.\w+")
_CTX_USE_RE = re.compile(r"\bctx\.(\w+)")

# Truy cập lồng nhau kiểu ctx.scenes[0].text — chỉ phần đầu mới là key của store.
_STORE_FILE = os.path.join(_SRC, "store.js")


def _components() -> list[str]:
    folder = os.path.join(_SRC, "components")
    return [os.path.join(folder, f) for f in sorted(os.listdir(folder)) if f.endswith(".jsx")]


def _selector_keys(source: str) -> set[str] | None:
    """Các key mà component tự khai báo trong khối useShallow. None nếu không có khối nào."""
    m = _SELECTOR_RE.search(source)
    if not m:
        return None
    # Cắt từ đầu khối tới dấu đóng `})))` đầu tiên — đủ chính xác cho cách viết trong dự án.
    start = m.end()
    end = source.find("})))", start)
    if end == -1:
        return None
    return set(_KEY_RE.findall(source[start:end]))


def test_moi_ctx_duoc_doc_deu_co_trong_selector():
    """Đây là test đã bắt được bug hookSfxVolume."""
    loi = []
    for path in _components():
        with open(path, encoding="utf-8") as f:
            source = f.read()
        keys = _selector_keys(source)
        if keys is None:
            continue
        used = set(_CTX_USE_RE.findall(source))
        thieu = sorted(used - keys)
        if thieu:
            loi.append(f"{os.path.basename(path)}: đọc ctx.{{{', '.join(thieu)}}} nhưng selector không có")

    assert not loi, "\n    " + "\n    ".join(loi)


def test_moi_key_trong_selector_deu_ton_tai_trong_store():
    """Gõ sai tên khi khai báo selector cũng cho undefined y hệt, chỉ khác chỗ gõ sai."""
    with open(_STORE_FILE, encoding="utf-8") as f:
        store_src = f.read()

    # State: các key trong INITIAL_STATE. Hành động: các hàm/giá trị trả về ở cuối store.
    state_keys = set(re.findall(r"^\s{2}(\w+)\s*:", store_src, re.MULTILINE))
    setters = {f"set{k[0].upper()}{k[1:]}" for k in state_keys}
    extra = set(re.findall(r"^\s*(?:const|let)\s+(\w+)\s*=", store_src, re.MULTILINE))
    known = state_keys | setters | extra

    loi = []
    for path in _components():
        with open(path, encoding="utf-8") as f:
            keys = _selector_keys(f.read())
        if not keys:
            continue
        la = sorted(k for k in keys if k not in known)
        if la:
            loi.append(f"{os.path.basename(path)}: selector khai báo {la} — store không có")

    assert not loi, "\n    " + "\n    ".join(loi)


def test_payload_render_khong_gui_gia_tri_tinh_tu_undefined():
    """Bất kỳ `ctx.X / số` nào trong payload đều phải có X trong selector — phép chia
    trên undefined cho NaN, và NaN đi qua JSON thành null, làm hỏng cả request."""
    path = os.path.join(_SRC, "components", "ScriptEditor.jsx")
    with open(path, encoding="utf-8") as f:
        source = f.read()
    keys = _selector_keys(source) or set()

    chia = set(re.findall(r"ctx\.(\w+)\s*/\s*\d", source))
    thieu = sorted(chia - keys)

    assert not thieu, f"phép chia trên giá trị không có trong selector: {thieu}"


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
