import asyncio
import sys

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append('C:/dev/AI-VIDEO-MAKER/backend')
from services.tts_service import synthesize_speech

async def test():
    try:
        dur = await synthesize_speech("Lập trình Python rất thú vị nhé các bạn", "test_minion_pro.mp3", voice="minion_pro")
        print(f"Success! Duration: {dur}")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(test())
