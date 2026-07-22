import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv(os.path.join("C:/dev/AI-VIDEO-MAKER/backend", ".env"))
sys.path.append("C:/dev/AI-VIDEO-MAKER/backend")

from services import gemini_service

async def test_imagen():
    output_path = "C:/dev/AI-VIDEO-MAKER/test_imagen_output.png"
    if os.path.exists(output_path):
        os.remove(output_path)
        
    print("Testing Imagen 3.0 generation...")
    try:
        res = await gemini_service.generate_image("A futuristic city", output_path)
        print("Success! Saved to:", res)
        print("File exists:", os.path.exists(output_path))
        print("File size:", os.path.getsize(output_path))
    except Exception as e:
        print("Error generating image:", e)

asyncio.run(test_imagen())
