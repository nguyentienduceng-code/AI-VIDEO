import asyncio
import os
import sys

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(r"C:\dev\AI-VIDEO-MAKER\backend")

from services.tts_service import synthesize_speech

PREVIEW_DIR = r"C:\dev\AI-VIDEO-MAKER\backend\assets\voices_preview"
os.makedirs(PREVIEW_DIR, exist_ok=True)

VOICES = [
    {"id": "vi-VN-AnNiNeural", "text": "Chào mừng bạn đến với hệ thống tạo video tự động bằng AI."},
    {"id": "vi-VN-PhuongMyNeural", "text": "Chào mừng bạn đến với hệ thống tạo video tự động bằng AI."},
    {"id": "minion", "text": "Chào mừng bạn đến với hệ thống tạo video tự động bằng AI."},
    {"id": "minion_pro", "text": "Chào mừng bạn đến với hệ thống tạo video tự động bằng AI."},
    {"id": "omnivoice_male_vi", "text": "Chào mừng bạn đến với hệ thống tạo video tự động bằng AI. Đây là giọng đọc nam chuẩn."},
    {"id": "omnivoice_female_vi", "text": "Chào mừng bạn đến với hệ thống tạo video tự động bằng AI. Đây là giọng đọc nữ chuẩn."},
    {"id": "omnivoice_female_whisper_vi", "text": "Chào mừng bạn đến với hệ thống tạo video tự động. Hãy nghe kể một câu chuyện thật nhẹ nhàng."},
    {"id": "omnivoice_female_child_vi", "text": "Chào mừng bạn đến với hệ thống tạo video tự động bằng AI. Giọng của em bé nè!"},
    {"id": "omnivoice_female_high_vi", "text": "Chào mừng bạn đến với hệ thống tạo video! Giọng đọc thật là hào hứng!"},
    {"id": "omnivoice_male_low_vi", "text": "Chào mừng bạn đến với hệ thống tạo video tự động. Đây là bản tin tài chính."},
    {"id": "omnivoice_male_elderly_vi", "text": "Chào mừng bạn đến với hệ thống tạo video. Ngày xửa ngày xưa, có một ngôi làng nhỏ."},
    {"id": "omnivoice_male_middle_aged_low_vi", "text": "Xin chào, tôi là một người đàn ông trung niên với chất giọng cực kỳ trầm ấm và từ tốn."},
    {"id": "omnivoice_male_motivational_vi", "text": "Đừng bao giờ từ bỏ ước mơ của bạn! Hãy đứng lên và hành động ngay hôm nay!"},
    {"id": "omnivoice_male_podcast_vi", "text": "Chào mừng các bạn đã quay trở lại với series podcast phát triển bản thân."},
    {"id": "omnivoice_male_whisper_vi", "text": "Chào bạn, hôm nay của bạn thế nào? Hãy thả lỏng và lắng nghe nhé."},
]

async def main():
    for voice_info in VOICES:
        voice_id = voice_info["id"]
        text = voice_info["text"]
        out_path = os.path.join(PREVIEW_DIR, f"{voice_id}.mp3")
        if not os.path.exists(out_path):
            print(f"Generating preview for {voice_id}...")
            try:
                await synthesize_speech(text=text, output_path=out_path, voice=voice_id)
                print(f"Success: {out_path}")
            except Exception as e:
                print(f"Error for {voice_id}: {e}")
        else:
            print(f"Exists: {out_path}")

if __name__ == "__main__":
    asyncio.run(main())
