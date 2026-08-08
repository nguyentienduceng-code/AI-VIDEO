import asyncio
import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
import os

# Thêm thư mục backend vào sys.path để import được services
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from services.tts_service import synthesize_speech

async def test():
    text = "Chào mừng bạn đến với phần mềm **Quản Lý CHDV**! Với App này, doanh thu 100 VNĐ sẽ được tính toán chính xác."
    print("Testing TTS with text:", text)
    duration = await synthesize_speech(
        text=text,
        output_path="test_v2.mp3",
        mode="storyteller"
    )
    print("Success! Audio duration:", duration)

if __name__ == "__main__":
    asyncio.run(test())
