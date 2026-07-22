import asyncio
from services.gemini_service import generate_script
import time

async def test():
    t0 = time.time()
    try:
        res = await generate_script(topic="Giới thiệu sách", num_scenes=6, mode="storyteller")
        print(f"Success! Time: {time.time()-t0:.2f}s")
        print(res)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())
