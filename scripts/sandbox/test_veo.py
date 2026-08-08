import asyncio
import sys
import os
from dotenv import load_dotenv

sys.path.append('C:/dev/AI-VIDEO-MAKER/backend')
load_dotenv('C:/dev/AI-VIDEO-MAKER/backend/.env')

from services import veo_service

async def test():
    try:
        await veo_service.text_to_video('A cute cat walking', 'test_veo.mp4')
        print('Veo success!')
    except Exception as e:
        print('Veo error:', e)

asyncio.run(test())
