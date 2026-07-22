import asyncio
import sys
sys.path.append('C:/dev/AI-VIDEO-MAKER/backend')
from services import tts_service, image_router

async def test():
    try:
        a, b = await asyncio.gather(
            tts_service.synthesize_speech('Xin chào', 'C:/dev/AI-VIDEO-MAKER/test2.mp3'),
            image_router.generate_image_with_fallback('cat', 'C:/dev/AI-VIDEO-MAKER/test2.png', google_api_key=None)
        )
        print('Done')
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(test())
