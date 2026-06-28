"""
tts_service.py
---------------
FIX NỢ KỸ THUẬT #1 (Event Loop):
- Code cũ dùng `asyncio.get_event_loop().run_until_complete(...)` bên trong
  một ứng dụng FastAPI đã có event loop chạy sẵn -> RuntimeError.
- Code mới: hàm này tự thân đã là `async def`, và gọi trực tiếp
  `await communicate.save(...)` của edge-tts. Endpoint phía main.py cũng
  phải là `async def` và `await` hàm này, KHÔNG được bọc thêm
  run_until_complete ở bất kỳ đâu nữa.
"""

from __future__ import annotations

import edge_tts
from mutagen.mp3 import MP3  # để đo chính xác độ dài audio (giây)

DEFAULT_VOICE = "vi-VN-HoaiMyNeural"  # giọng nữ tiếng Việt mặc định


async def synthesize_speech(text: str, output_path: str, voice: str = DEFAULT_VOICE) -> float:
    """
    Chuyển văn bản -> giọng nói, lưu file mp3 tại output_path.
    Trả về độ dài audio (giây) để video_service.py căn thời gian hiển thị ảnh.

    QUAN TRỌNG: hàm này PHẢI được gọi bằng `await synthesize_speech(...)`
    từ một hàm `async def` khác. Không gọi run_until_complete ở đây hay
    ở bất kỳ đâu khác trong codebase.
    """
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

    audio = MP3(output_path)
    duration_seconds = audio.info.length
    return duration_seconds
