"""
Test bắt TÊN TOÀN CỤC KHÔNG TỒN TẠI trong mã nguồn backend.

Chạy:  python tests/test_ten_toan_cuc.py    (từ thư mục backend/)
       pytest tests/test_ten_toan_cuc.py

VÌ SAO CÓ FILE NÀY — bug thật, tốn nhiều lần render để lần ra:

    watermark_logo=os.path.join(BASE_DIR, "assets", "watermarks", f"{req.watermark_logo}.png")
                   if req.watermark_logo else None,

`BASE_DIR` chưa bao giờ được import vào main.py. Nhưng vì nó nằm ở nhánh THẬT của một
biểu thức điều kiện, Python chỉ tra tên đó khi `req.watermark_logo` khác None — tức
CHỈ khi user tick "Chèn Logo NTD". Hệ quả:

  * `import main` chạy trơn — không ImportError, không SyntaxError;
  * mọi test hiện có đi qua sạch, vì không test nào bật logo;
  * job chỉ chết đúng lúc user bật logo, và chết ở bước dựng master_kwargs — SAU khi
    đã sinh xong toàn bộ ảnh Gemini + TTS, phần đắt nhất và lâu nhất của pipeline;
  * người dùng chỉ thấy "Lỗi: name 'BASE_DIR' is not defined" nên hiểu thành
    "tính năng chèn logo không hoạt động".

Bất kỳ nhánh code ÍT ĐI QUA nào cũng có thể chứa cùng loại lỗi này. Test dưới đây
không dò riêng BASE_DIR mà quét CẢ LỚP lỗi: mọi tên được ĐỌC như biến toàn cục nhưng
không hề được gán / import / khai báo ở cấp module, và cũng không phải builtin.

Dùng `symtable` chứ không tự đi AST: symtable là chính bộ phân tích phạm vi của
CPython, nên nó tự xử lý đúng tham số hàm, biến comprehension, closure, global/nonlocal
— những thứ mà một vòng lặp `ast.walk` tìm Name sẽ báo động giả hàng loạt.
"""
import builtins
import os
import symtable
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Các module chịu kiểm tra: mã chạy thật của backend. Thêm file mới vào đây khi nó
# trở thành đường chạy chính.
_MODULES = [
    "main.py",
    os.path.join("services", "audio_mix_service.py"),
    os.path.join("services", "render_worker.py"),
    os.path.join("services", "ffmpeg_assembler.py"),
    os.path.join("services", "video_service.py"),
    os.path.join("services", "image_router.py"),
    "config.py",
]

# Tên được phép "không thấy khai báo": builtins + tên do công cụ/typing chèn.
_CHO_PHEP = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__package__", "reveal_type"}


def _ten_cap_module(bang: symtable.SymbolTable) -> set:
    """Tên được GÁN hoặc IMPORT ở cấp module — tức thực sự tồn tại khi chạy."""
    ten = set()
    for sym in bang.get_symbols():
        if sym.is_assigned() or sym.is_imported() or sym.is_parameter():
            ten.add(sym.get_name())
    # def/class ở cấp module cũng là gán, symtable đã tính; lấy thêm cho chắc.
    for con in bang.get_children():
        ten.add(con.get_name())
    return ten


def _ten_toan_cuc_duoc_doc(bang: symtable.SymbolTable, ket_qua: set) -> None:
    """Đệ quy mọi phạm vi, thu các tên được ĐỌC mà phạm vi hiện tại coi là toàn cục."""
    for sym in bang.get_symbols():
        if sym.is_referenced() and sym.is_global() and not sym.is_assigned():
            ket_qua.add(sym.get_name())
    for con in bang.get_children():
        _ten_toan_cuc_duoc_doc(con, ket_qua)


def _kiem_tra_mot_file(duong_dan_tuong_doi: str) -> list:
    """Trả về danh sách tên toàn cục bị đọc nhưng không tồn tại."""
    duong_dan = os.path.join(BACKEND_DIR, duong_dan_tuong_doi)
    with open(duong_dan, encoding="utf-8") as f:
        src = f.read()

    bang = symtable.symtable(src, duong_dan_tuong_doi, "exec")
    co_san = _ten_cap_module(bang) | _CHO_PHEP

    duoc_doc = set()
    _ten_toan_cuc_duoc_doc(bang, duoc_doc)
    return sorted(duoc_doc - co_san)


def test_khong_co_ten_toan_cuc_khong_ton_tai():
    """Mọi tên dùng như biến toàn cục phải được gán hoặc import ở cấp module.

    Đây là loại lỗi mà Python KHÔNG bắt lúc import: nó chỉ nổ khi luồng chạy chạm đúng
    dòng đó. Với các nhánh chỉ bật khi user tick một tuỳ chọn hiếm dùng, "chạm đúng
    dòng đó" có thể là hàng tháng sau khi commit.
    """
    loi = {}
    for mod in _MODULES:
        thieu = _kiem_tra_mot_file(mod)
        if thieu:
            loi[mod] = thieu

    assert not loi, "Tên toàn cục không tồn tại (sẽ NameError khi chạy tới dòng đó):\n" + "\n".join(
        f"  {mod}: {', '.join(ten)}" for mod, ten in loi.items()
    )


def test_watermark_logo_path_tra_ve_file_that():
    """Bật logo phải ra đúng đường dẫn file có thật, không phải None và không NameError.

    Đây là kiểm chứng TRỰC TIẾP cho bug BASE_DIR: gọi đúng hàm mà main.py dùng, với
    đúng chuỗi mà frontend gửi ("logo_ntd" — xem ScriptEditor.jsx).
    """
    from main import _watermark_logo_path

    assert _watermark_logo_path(None) is None
    assert _watermark_logo_path("") is None

    duong_dan = _watermark_logo_path("logo_ntd")
    assert duong_dan is not None, (
        "logo_ntd không giải ra được đường dẫn nào — kiểm tra "
        "backend/assets/watermarks/logo_ntd.png có tồn tại không."
    )
    assert os.path.isfile(duong_dan), duong_dan
    assert duong_dan.endswith(os.path.join("assets", "watermarks", "logo_ntd.png"))


def test_watermark_logo_path_chan_path_traversal():
    """`watermark_logo` là chuỗi từ client, phải không leo ra khỏi thư mục watermarks."""
    from main import _watermark_logo_path

    for xau in ("../../config", r"..\..\config", "sub/logo_ntd", "/etc/passwd"):
        assert _watermark_logo_path(xau) is None, f"không chặn: {xau!r}"


if __name__ == "__main__":
    # Chạy trực tiếp bằng python.exe thì stdout là cp1252 và mọi dòng có dấu sẽ vỡ.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    that_bai = 0
    for ten, fn in sorted(globals().items()):
        if ten.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {ten}")
            except AssertionError as e:
                that_bai += 1
                print(f"FAIL  {ten}\n      {e}")
    sys.exit(1 if that_bai else 0)
