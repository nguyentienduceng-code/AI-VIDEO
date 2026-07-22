import asyncio
import edge_tts

async def test():
    communicate = edge_tts.Communicate("xin chao", "vi-VN-HoaiMyNeural", rate="+10%")
    try:
        await communicate.save("test.mp3")
        print("success")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(test())
