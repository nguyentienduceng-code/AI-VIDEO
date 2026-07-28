"""
log_setup.py — Ép stdout/stderr về UTF-8 + ghi log ra file, trước khi bất kỳ dòng
log tiếng Việt nào chạy.

VÌ SAO CẦN ÉP UTF-8
-------------------
Trên Windows, khi stdout KHÔNG phải console thật (chạy như service, hoặc `python -m
uvicorn ... > server.log`, hoặc bị process manager bắt ống), Python mở nó bằng
encoding của locale — cp1252 — với errors='strict'. Mọi dòng log có dấu tiếng Việt
lập tức ném UnicodeEncodeError.

Đổi print() sang logger KHÔNG cứu được, đã đo tận nơi:
  1. logging bắt lỗi trong emit() rồi gọi handleError();
  2. handleError() in traceback ra stderr — traceback chứa CHÍNH dòng mã nguồn
     tiếng Việt vừa gây lỗi;
  3. stderr cũng là cp1252 → ném tiếp, và lần này lỗi THOÁT RA NGOÀI, giết luôn
     hàm đang chạy (đã thấy assemble() chết đúng kiểu này).

Nên phải chặn ở tầng stream, không phải tầng logging. errors='replace' là lưới an
toàn cuối: thà log ra '?' còn hơn sập job render.

Phải gọi ở CẢ tiến trình FastAPI lẫn tiến trình con của multiprocessing — Windows
dùng 'spawn' nên tiến trình con dựng TextIOWrapper mới, không thừa hưởng cấu hình
của tiến trình cha.

VÌ SAO CẦN GHI RA FILE
----------------------
`start.bat` chạy uvicorn trong một cửa sổ cmd. Đóng cửa sổ là mất sạch log — nên
khi job render chết ngầm giữa chừng thì KHÔNG còn dấu vết nào để truy. Ngày
2026-07-28 đã phải đi mò log PM2 cũ 17 ngày vì lý do này, và suýt kết luận sai.
Từ nay mọi dòng log được ghi song song vào `backend/logs/*.log`, xoay vòng 10MB × 5.

MỖI TIẾN TRÌNH MỘT FILE RIÊNG (quan trọng)
------------------------------------------
RotatingFileHandler KHÔNG an toàn đa tiến trình trên Windows: lúc xoay vòng nó
đổi tên `x.log` → `x.log.1`, mà Windows cấm đổi tên file đang được tiến trình
khác mở → PermissionError. Vì render chạy trong process con riêng
(`render_worker.py`), tiến trình đó phải ghi sang file khác qua tham số
`log_name`. Nếu sau này chạy NHIỀU worker song song thật sự, cần đổi sang
QueueHandler + một tiến trình ghi log duy nhất.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys

_DEFAULT_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"

# backend/logs — suy từ vị trí file này (backend/services/log_setup.py → backend/).
# CỐ Ý không import config để lấy đường dẫn: config.py đã import ngược module này
# (xem đầu config.py), thêm chiều ngược lại là vỡ import vòng lúc khởi động.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(_BACKEND_DIR, "logs")

_MAX_BYTES = 10 * 1024 * 1024  # 10MB mỗi file
_BACKUP_COUNT = 5              # giữ 5 file cũ → trần ~60MB mỗi loại log
_HANDLER_TAG = "_avm_log_name"  # đánh dấu handler của ta để gắn đúng một lần


def force_utf8_streams() -> None:
    """Cấu hình lại stdout/stderr sang UTF-8. Im lặng bỏ qua nếu stream không hỗ trợ."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            # stream đã bị thay bằng object khác (pytest capture, uvicorn --no-use-colors...)
            # hoặc không phải TextIOWrapper → không có gì để sửa, kệ nó.
            pass


def _attach_file_handler(log_name: str, level: int, fmt: str) -> str | None:
    """Gắn RotatingFileHandler vào root logger. Trả về đường dẫn file, None nếu hỏng.

    Idempotent: gọi lại với cùng `log_name` sẽ không gắn thêm handler thứ hai.
    """
    root = logging.getLogger()
    for handler in root.handlers:
        if getattr(handler, _HANDLER_TAG, None) == log_name:
            return getattr(handler, "baseFilename", None)

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        path = os.path.join(LOG_DIR, f"{log_name}.log")
        handler = logging.handlers.RotatingFileHandler(
            path,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",   # BẮT BUỘC: mặc định là cp1252, mọi log tiếng Việt sẽ ném lỗi
            delay=True,         # chưa tạo file cho tới dòng log đầu tiên
        )
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter(fmt))
        setattr(handler, _HANDLER_TAG, log_name)
        root.addHandler(handler)
        return path
    except OSError:
        # Thư mục chỉ đọc / hết đĩa / bị khoá — KHÔNG được làm chết app chỉ vì không
        # ghi được log. Rơi về console-only như hành vi cũ.
        return None


def setup_logging(
    level: int = logging.INFO,
    fmt: str = _DEFAULT_FORMAT,
    log_name: str = "backend",
) -> None:
    """force_utf8_streams() + basicConfig + ghi file. An toàn khi gọi nhiều lần.

    log_name: tên file log (không đuôi). Mỗi TIẾN TRÌNH phải dùng tên riêng — xem
    ghi chú đa tiến trình ở đầu module.
    """
    force_utf8_streams()
    logging.basicConfig(level=level, format=fmt)

    # basicConfig() không làm gì nếu root đã có handler (vd uvicorn tự cấu hình
    # trước). Khi đó root.level có thể là WARNING và file log sẽ mất hết dòng INFO —
    # đúng những dòng cần nhất để dựng lại diễn biến một job render đã chết.
    root = logging.getLogger()
    if root.level == logging.NOTSET or root.level > level:
        root.setLevel(level)

    _attach_file_handler(log_name, level, fmt)
