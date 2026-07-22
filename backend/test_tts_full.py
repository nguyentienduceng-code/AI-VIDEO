import asyncio
from services.tts_service import synthesize_speech

async def test():
    full_text = "Bạn có bao giờ cảm thấy mình cứ loay hoay mãi không? Mệt mỏi với những suy nghĩ tiêu cực, rồi tự hỏi tại sao mọi chuyện lại khó khăn đến vậy?"
    try:
        dur, wbs = await synthesize_speech(full_text, "test_output.mp3", rate="+0%", pitch="+0Hz")
        print(f"Success: dur={dur}")
    except Exception as e:
        print(f"Failed completely: {e}")

if __name__ == "__main__":
    asyncio.run(test())
