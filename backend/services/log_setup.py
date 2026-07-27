"""
log_setup.py — Ép stdout/stderr về UTF-8 trước khi bất kỳ dòng log tiếng Việt nào chạy.

VÌ SAO CẦN MODULE NÀY
---------------------
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
"""
from __future__ import annotations

import logging
import sys

_DEFAULT_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def force_utf8_streams() -> None:
    """Cấu hình lại stdout/stderr sang UTF-8. Im lặng bỏ qua nếu stream không hỗ trợ."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            # stream đã bị thay bằng object khác (pytest capture, uvicorn --no-use-colors...)
            # hoặc không phải TextIOWrapper → không có gì để sửa, kệ nó.
            pass


def setup_logging(level: int = logging.INFO, fmt: str = _DEFAULT_FORMAT) -> None:
    """force_utf8_streams() + basicConfig. An toàn khi gọi nhiều lần."""
    force_utf8_streams()
    logging.basicConfig(level=level, format=fmt)
