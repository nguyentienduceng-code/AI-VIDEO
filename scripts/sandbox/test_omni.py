import sys
import asyncio
sys.path.append('C:/dev/AI-VIDEO-MAKER/backend')
from services.tts_service import _synthesize_omnivoice

async def test_omni():
    print("Synthesizing OmniVoice...")
    dur, wbs = await _synthesize_omnivoice("Xin chào bạn, tôi là OmniVoice", "C:/dev/AI-VIDEO-MAKER/backend/assets/cache/test_omni.mp3", "omnivoice_male_podcast_vi")
    print(f"Duration: {dur}")

asyncio.run(test_omni())
