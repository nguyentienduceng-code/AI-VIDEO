import asyncio
import os
import glob
import sys
sys.path.append(os.path.join(os.path.dirname(__file__)))
from services.gemini_service import generate_script_from_images
import time

async def test():
    upload_dir = r"C:\dev\AI-VIDEO-MAKER\backend\assets\uploads\ddf8f1ed-9b53-41be-87c2-afe820f52209"
    user_images = glob.glob(os.path.join(upload_dir, "*"))
    print(f"Images: {user_images}")
    if user_images:
        t0 = time.time()
        try:
            res = await generate_script_from_images(user_images)
            print(f"Success! Time: {time.time()-t0:.2f}s")
            print(res)
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())
