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
    {"id": "vi-VN-AnNiNeural", "name": "An Ni (Trẻ trung)", "gender": "Nữ"},
    {"id": "vi-VN-PhuongMyNeural", "name": "Phương My (Tin tức)", "gender": "Nữ"},
    {"id": "minion", "name": "Minion (Nhí nhảnh)", "gender": "Ảo"},
    {"id": "minion_pro", "name": "Minion Pro (Hỗn loạn, Cuốn hút)", "gender": "Ảo"},
]

import random
import re

def _minion_pro_transform(text: str) -> str:
    """Biến đổi văn bản thành kiểu nói nhí nhảnh, lúng búng của Minion."""
    gibberish = ["Bello!", "Pô-pa-yê!", "Ba-na-na!", "Tu-la-li-lu!", "Pa-ra tu!", "Hí hí!", "He he he!", "Báp-pôi!"]
    
    # 1. Tách thành các câu nhỏ
    sentences = re.split(r'(?<=[.!?]) +', text.strip())
    transformed = []
    
    for s in sentences:
        if not s: continue
        # Đổi dấu chấm thành dấu hỏi để tạo ngữ điệu lên giọng cuối câu
        s = s.replace('.', '?')
        
        words = s.split()
        if not words: continue
        
        # 2. Thêm nói lắp búng (stuttering) ngẫu nhiên vào các từ bắt đầu bằng b, p, m, n
        for i, w in enumerate(words):
            if len(w) > 2 and w[0].lower() in ['b', 'p', 'm', 'n'] and random.random() < 0.2:
                words[i] = f"{w[0]}-{w}"
        
        # 3. Lắp lại thành câu, chèn các từ gián đoạn (ngắt câu dồn dập)
        new_s = ""
        for i, w in enumerate(words):
            new_s += w + " "
            if random.random() < 0.1 and i < len(words) - 1:
                new_s += ", "
                
        # 4. Thêm gibberish / tiếng cười ngẫu nhiên vào đầu hoặc cuối câu
        if random.random() < 0.4:
            new_s = random.choice(gibberish) + " " + new_s
        elif random.random() < 0.4:
            new_s = new_s.strip() + " " + random.choice(gibberish)
            
        transformed.append(new_s.strip())
        
    return " ".join(transformed)


async def synthesize_speech(
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
    pitch: str = "+0Hz",
    mode: str = "storyteller"
) -> float:
    """
    Chuyển văn bản -> giọng nói, lưu file mp3 tại output_path.
    Trả về độ dài audio (giây) để video_service.py căn thời gian hiển thị ảnh.

    Parameters:
        text: Nội dung cần đọc
        output_path: Đường dẫn file mp3 xuất ra
        voice: ID giọng đọc Edge-TTS
        rate: Tốc độ đọc (VD: "-10%", "+0%", "+15%")
        pitch: Cao độ (VD: "-10Hz", "+20Hz")

    QUAN TRỌNG: hàm này PHẢI được gọi bằng `await synthesize_speech(...)`
    từ một hàm `async def` khác. Không gọi run_until_complete ở đây hay
    ở bất kỳ đâu khác trong codebase.
    """
    import time
    
    # Kể chuyện ma (suspense): thêm dấu ... dài để edge-tts ngắt nghỉ lâu hơn
    if mode == "storyteller" and ("ma" in text.lower() or "hồi hộp" in text.lower() or voice == "vi-VN-NamMinhNeural"):
        text = text.replace(".", "... ").replace(",", ",,, ")

    # Xử lý giọng ảo (Virtual Voices)
    if voice == "minion":
        voice = "vi-VN-HoaiMyNeural"
        rate = "+30%"
        pitch = "+400Hz" # Tăng cao độ (chipmunk)
    elif voice == "minion_pro":
        voice = "vi-VN-HoaiMyNeural"
        rate = "+45%"
        pitch = f"+{random.randint(350, 450)}Hz" # Dao động cao độ
        text = _minion_pro_transform(text)

    temp_path = output_path + ".tmp"
    last_error = None
    for attempt in range(3):
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
            await communicate.save(temp_path)
            
            # Đảm bảo file hợp lệ
            audio = MP3(temp_path)
            duration_seconds = audio.info.length
            
            import shutil
            shutil.move(temp_path, output_path)
            
            return duration_seconds
        except Exception as e:
            last_error = e
            print(f"Edge-TTS error (attempt {attempt+1}/3): {e}")
            import os
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if os.path.exists(output_path):
                os.remove(output_path)
            import asyncio
            await asyncio.sleep(2)
            
    # Fallback if TTS fails completely: Create a dummy audio file of 3 seconds
    print(f"TTS failed completely: {last_error}. Using fallback dummy audio.")
    try:
        from gtts import gTTS
        tts = gTTS(text, lang='vi')
        temp_path = output_path + ".gtts.tmp"
        tts.save(temp_path)
        audio = MP3(temp_path)
        duration = audio.info.length
        import shutil
        shutil.move(temp_path, output_path)
        return duration
    except Exception as gtts_e:
        print(f"gTTS fallback failed: {gtts_e}")
        import os
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)
        # Return 3 seconds dummy
        return 3.0


def get_available_voices():
    """Trả về danh sách giọng đọc tiếng Việt để frontend hiển thị."""
    return VIETNAMESE_VOICES
