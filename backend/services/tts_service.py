"""
tts_service.py
---------------
NÂNG CẤP V2:
1. Giữ nguyên fix nợ kỹ thuật #1 (async/await trực tiếp).
2. Thêm `rate` parameter: điều chỉnh tốc độ đọc (ví dụ "-10%" cho chậm,
   "+10%" cho nhanh). Hữu ích cho quiz mode (nhanh) vs storyteller (chậm).
3. Thêm `get_available_voices()`: trả về danh sách giọng đọc tiếng Việt
   có sẵn để frontend hiển thị.
"""

from __future__ import annotations

import edge_tts
from mutagen.mp3 import MP3  # để đo chính xác độ dài audio (giây)

DEFAULT_VOICE = "vi-VN-HoaiMyNeural"  # giọng nữ tiếng Việt mặc định
DEFAULT_RATE = "+0%"  # tốc độ đọc mặc định (không đổi)

# Danh sách giọng đọc tiếng Việt hỗ trợ bởi Edge-TTS
VIETNAMESE_VOICES = [
    {"id": "vi-VN-HoaiMyNeural", "name": "Hoài My", "gender": "Nữ"},
    {"id": "vi-VN-NamMinhNeural", "name": "Nam Minh", "gender": "Nam"},
]


async def synthesize_speech(
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
) -> float:
    """
    Chuyển văn bản -> giọng nói, lưu file mp3 tại output_path.
    Trả về độ dài audio (giây) để video_service.py căn thời gian hiển thị ảnh.

    Parameters:
        text: Nội dung cần đọc
        output_path: Đường dẫn file mp3 xuất ra
        voice: ID giọng đọc Edge-TTS
        rate: Tốc độ đọc (VD: "-10%", "+0%", "+15%")

    QUAN TRỌNG: hàm này PHẢI được gọi bằng `await synthesize_speech(...)`
    từ một hàm `async def` khác. Không gọi run_until_complete ở đây hay
    ở bất kỳ đâu khác trong codebase.
    """
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(output_path)

    audio = MP3(output_path)
    duration_seconds = audio.info.length
    return duration_seconds


def get_available_voices():
    """Trả về danh sách giọng đọc tiếng Việt để frontend hiển thị."""
    return VIETNAMESE_VOICES
