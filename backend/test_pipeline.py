import asyncio
import os
import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()

from services import gemini_service, tts_service, image_router, video_service

async def main():
    print("=== PIPELINE BACKTEST ===")
    
    # 1. Generate Script
    print("1. Generating script...")
    scenes = await gemini_service.generate_script(
        topic="Sự thật thú vị về loài mèo",
        num_scenes=3,
        mode="storyteller",
        target_duration="15s",
        narration_tone="humorous"
    )
    
    if isinstance(scenes, dict) and "scenes" in scenes:
        scenes = scenes["scenes"]
        
    print(f"Generated {len(scenes)} scenes.")
    
    # Setup test workspace
    os.makedirs("test_workspace", exist_ok=True)
    
    # Sinh audio và tải ảnh
    for i, s in enumerate(scenes):
        print(f"\n--- Scene {i+1} ---")
        text = s.get("text", "")
        print(f"Text: {text}")
        
        # 2. TTS
        audio_path = f"test_workspace/scene_{i}.mp3"
        print("Synthesizing speech...")
        dur, wbs = await tts_service.synthesize_speech(
            text=text,
            output_path=audio_path,
            emotion=s.get("emotion", ""),
            voice="vi-VN-NamMinhNeural"
        )
        print(f"Audio dur: {dur}")
        s["audio_path"] = audio_path
        s["word_boundaries"] = wbs
        s["computed_duration"] = dur # Tạm thời lấy duration của audio
        
        # 3. Image
        img_path = f"test_workspace/scene_{i}.jpg"
        print("Generating image...")
        try:
            await image_router.generate_image_with_fallback(s.get("image_prompt", "A cat"), img_path, "16:9", seed=12345)
            s["image_path"] = img_path
        except Exception as e:
            print(f"Failed to generate image: {e}")
            s["image_path"] = ""

    # Tính toán timeline
    from services.motion_effects import build_scene_timeline, pick_pan_direction
    scenes = build_scene_timeline(scenes)
    
    scene_assets = []
    from services.motion_effects import apply_ken_burns
    for i, s in enumerate(scenes):
        if not s.get("image_path"): continue
        img_path = s["image_path"]
        duration = s.get("computed_duration", 3.0)
        default_effect = s.get("visual_effect", "") or pick_pan_direction(i)
        
        # Apply Ken Burns
        out_mp4 = img_path + f"_{i}.mp4"
        await asyncio.to_thread(
            apply_ken_burns,
            image_path=img_path, output_path=out_mp4, duration=duration, fps=30, pan_direction=default_effect
        )
        img_path = out_mp4
        
        scene_assets.append({
            "image_path": img_path,
            "audio_path": s.get("audio_path"),
            "text": s.get("text", ""),
            "duration": duration,
            "start_time": s.get("start_time", 0.0),
            "sfx": s.get("sfx", ""),
            "visual_effect": default_effect,
            "word_boundaries": s.get("word_boundaries", []),
            "transition": s.get("transition", "crossfade")
        })

    # 4. Render Video
    print("\n4. Rendering raw video...")
    output_path = "test_workspace/final_raw.mp4"
    final_output = "test_workspace/final_output.mp4"
    if os.path.exists(output_path): os.remove(output_path)
    if os.path.exists(final_output): os.remove(final_output)
        
    try:
        raw_video = video_service.render_final_video(
            scene_assets=scene_assets,
            output_path=output_path,
            aspect_ratio="16:9",
            mode="storyteller"
        )
        print(f"Raw video rendered at: {raw_video}")
        
        print("\n5. Mastering Audio...")
        from services.audio_mix_service import master_audio_and_export
        master_audio_and_export(
            input_video_path=raw_video,
            output_path=final_output,
            bgm_path=None,
            use_gpu=False
        )
        print(f"✅ Final Video rendered successfully at: {final_output}")
    except Exception as e:
        print(f"❌ Video rendering failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
