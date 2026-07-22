import asyncio
import edge_tts

async def test():
    # +12Hz is pitch in edge_tts, or +15Hz, let's try +50Hz for minion
    communicate = edge_tts.Communicate("xin chao, minh la minion", "vi-VN-HoaiMyNeural", rate="+30%", pitch="+400Hz")
    await communicate.save("test_minion.mp3")
    print("success")

asyncio.run(test())
