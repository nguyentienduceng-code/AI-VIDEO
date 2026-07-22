"""Test audio synthesis naturalness comparing plain neural TTS vs prosody engine."""
import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import asyncio
import os
from services.tts_service import _synthesize_plain, _synthesize_with_prosody

async def main():
    text = "Thế giới bạn đang sống là thực, hay chỉ là một ma trận được lập trình? Cuốn sách Luật Tâm Thức sẽ giải mã những bí ẩn lớn nhất về vũ trụ và chính bạn."
    out_plain = "test_plain.mp3"
    out_prosody = "test_prosody.mp3"
    
    print("Synthesizing PLAIN neural TTS...")
    dur1, wbs1 = await _synthesize_plain(text, out_plain, "vi-VN-NamMinhNeural", "+0%", "+0Hz")
    print(f"Plain done: duration={dur1:.2f}s, words={len(wbs1)}")
    
    print("Synthesizing PROSODY engine...")
    dur2, wbs2 = await _synthesize_with_prosody(text, out_prosody, "vi-VN-NamMinhNeural", "+0%", "+0Hz")
    print(f"Prosody done: duration={dur2:.2f}s, words={len(wbs2)}")
    
    print("\nFile sizes:")
    print(f"  Plain:   {os.path.getsize(out_plain)} bytes")
    print(f"  Prosody: {os.path.getsize(out_prosody)} bytes")

if __name__ == "__main__":
    asyncio.run(main())
