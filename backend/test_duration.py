import asyncio
import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
from services import gemini_service

async def main():
    topic = "Bí ẩn dưới đáy đại dương"
    
    # Test 1: Duration scaling (30s vs 120s vs 180s)
    print("=" * 60)
    print("TEST 1: Duration Scaling + Auto Scene Count")
    print("=" * 60)
    
    for dur in ["30s", "120s", "180s"]:
        cfg = gemini_service.DURATION_CONFIG.get(dur, {})
        print(f"\n--- {dur} (target words: {cfg.get('words','?')}, suggested scenes: {cfg.get('suggested_scenes','?')}) ---")
        
        result = await gemini_service.generate_script(
            topic=topic,
            num_scenes=cfg.get("suggested_scenes", 5),
            mode="storyteller",
            art_style="Cinematic",
            target_duration=dur,
            narration_tone="viral",
        )
        
        if isinstance(result, dict) and "scenes" in result:
            scenes = result["scenes"]
        else:
            scenes = result
            
        total_words = 0
        for i, scene in enumerate(scenes):
            text = scene.get("text", "") if isinstance(scene, dict) else ""
            emotion = scene.get("emotion", "?") if isinstance(scene, dict) else "?"
            transition = scene.get("transition", "?") if isinstance(scene, dict) else "?"
            words = len(text.split())
            total_words += words
            print(f"  [Cảnh {i+1}] emotion={emotion}, transition={transition}, words={words}")
            print(f"    {text[:80]}{'...' if len(text) > 80 else ''}")
        
        print(f"  => Tổng: {total_words} từ | {len(scenes)} cảnh")

    # Test 2: Narration Tone comparison
    print("\n" + "=" * 60)
    print("TEST 2: Narration Tone Comparison (viral vs emotional)")
    print("=" * 60)
    
    for tone in ["viral", "emotional"]:
        print(f"\n--- Tone: {tone} ---")
        result = await gemini_service.generate_script(
            topic="Tại sao mèo sợ nước",
            num_scenes=4,
            mode="storyteller",
            art_style="Cinematic",
            target_duration="30s",
            narration_tone=tone,
        )
        
        if isinstance(result, dict) and "scenes" in result:
            scenes = result["scenes"]
        else:
            scenes = result
            
        for i, scene in enumerate(scenes):
            text = scene.get("text", "") if isinstance(scene, dict) else ""
            emotion = scene.get("emotion", "?") if isinstance(scene, dict) else "?"
            print(f"  [Cảnh {i+1}] emotion={emotion}: {text[:100]}{'...' if len(text) > 100 else ''}")
    
    print("\n✅ All tests completed!")

if __name__ == "__main__":
    asyncio.run(main())
