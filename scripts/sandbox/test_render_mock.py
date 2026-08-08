import asyncio
import os
import sys

# Ensure backend path is added
sys.path.append("C:/dev/AI-VIDEO-MAKER/backend")
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv("C:/dev/AI-VIDEO-MAKER/backend/.env")

from services import gemini_service, tts_service, image_router, video_service
from services.motion_effects import build_scene_timeline, apply_ken_burns, pick_pan_direction
from services.audio_mix_service import master_audio_and_export

async def main():
    print("=== MOCK PIPELINE TEST ===")
    
    # 1. Mock Scenes
    scenes = [
        {
            "scene": 1,
            "text": "Xin chào bạn, hôm nay chúng ta sẽ tìm hiểu về vũ trụ.",
            "image_prompt": "A spectacular galaxy in deep space, hyperrealistic photography, 8k",
            "sfx": "whoosh",
            "emotion": "hook",
            "transition": "crossfade"
        },
        {
            "scene": 2,
            "text": "Trái đất của chúng ta chỉ là một hạt cát nhỏ bé trong vũ trụ bao la.",
            "image_prompt": "A beautiful view of Earth from space, cinematic lighting, 8k",
            "sfx": "bell",
            "emotion": "calm",
            "transition": "fade_black"
        }
    ]
    
    # Setup test workspace
    workspace = "C:/dev/AI-VIDEO-MAKER/test_workspace_mock"
    os.makedirs(workspace, exist_ok=True)
    os.makedirs(os.path.join(workspace, "audio"), exist_ok=True)
    os.makedirs(os.path.join(workspace, "images"), exist_ok=True)
    
    # Generate Voice and Images
    for i, s in enumerate(scenes):
        print(f"\n--- Scene {i+1} ---")
        text = s.get("text", "")
        print(f"Text: {text}")
        
        # Voice (using OmniVoice to check if it works!)
        audio_path = f"{workspace}/audio/scene_{i+1}.mp3"
        print("Synthesizing speech via OmniVoice...")
        try:
            # Using omnivoice_male_podcast_vi
            dur, wbs = await tts_service.synthesize_speech(
                text=text,
                output_path=audio_path,
                voice="omnivoice_male_podcast_vi",
                emotion=s.get("emotion", "")
            )
            print(f"Voice Duration: {dur}s, boundaries: {len(wbs)}")
            s["audio_path"] = audio_path
            s["word_boundaries"] = wbs
            s["computed_duration"] = dur
        except Exception as e:
            print(f"Voice synthesis failed: {e}")
            s["audio_path"] = ""
            s["word_boundaries"] = []
            s["computed_duration"] = 3.0
            
        # Image
        img_path = f"{workspace}/images/scene_{i+1}.png"
        print("Generating image...")
        try:
            # We don't pass Google API Key so it falls back to Pollinations Flux
            await image_router.generate_image_with_fallback(
                image_prompt=s.get("image_prompt"),
                output_path=img_path,
                aspect_ratio="16:9",
                google_api_key=None
            )
            print(f"Image generated: {img_path}")
            s["image_path"] = img_path
        except Exception as e:
            print(f"Image generation failed: {e}")
            s["image_path"] = ""

    # Build timeline
    scenes = build_scene_timeline(scenes, overlap_dur=0.4)
    
    scene_assets = []
    for i, s in enumerate(scenes):
        if not s.get("image_path"): 
            print(f"Scene {i+1} is missing image! Skip.")
            continue
        
        img_path = s["image_path"]
        duration = s.get("computed_duration", 3.0)
        default_effect = s.get("visual_effect", "") or pick_pan_direction(i)
        
        # Apply Ken Burns if it's an image
        if not img_path.lower().endswith((".mp4", ".mov")):
            out_mp4 = img_path + f"_{i}.mp4"
            print(f"Applying Ken Burns to scene {i+1}...")
            try:
                await asyncio.to_thread(
                    apply_ken_burns,
                    image_path=img_path,
                    output_path=out_mp4,
                    duration=duration,
                    fps=30,
                    pan_direction=default_effect,
                    resolution=(1920, 1080) # Horizontal 16:9
                )
                img_path = out_mp4
            except Exception as e:
                print(f"Ken Burns failed: {e}")
                
        scene_assets.append({
            "image_path": img_path,
            "audio_path": s.get("audio_path"),
            "text": s.get("text", ""),
            "duration": duration,
            "sfx": s.get("sfx", ""),
            "visual_effect": default_effect,
            "word_boundaries": s.get("word_boundaries", []),
            "transition": s.get("transition", "crossfade"),
            "start_time": s.get("start_time", 0.0)
        })

    # Render video
    print("\n--- Rendering video ---")
    raw_video = f"{workspace}/final_raw.mp4"
    final_output = f"{workspace}/final_output.mp4"
    output_ass = f"{workspace}/final_output.ass"
    
    if os.path.exists(raw_video): os.remove(raw_video)
    if os.path.exists(final_output): os.remove(final_output)
    if os.path.exists(output_ass): os.remove(output_ass)
        
    try:
        await asyncio.to_thread(
            video_service.render_final_video,
            scene_assets, raw_video,
            aspect_ratio="16:9",
            bgm_path=None,
            mode="storyteller"
        )
        print("Raw video rendered successfully.")
        
        # Generate subtitles (.ass)
        await asyncio.to_thread(
            video_service.generate_ass_file,
            scene_assets, output_ass, "storyteller", subtitle_style="karaoke_bold"
        )
        print("Subtitles generated successfully.")
        
        # Mastering
        print("Mastering Audio and burning subtitles...")
        await asyncio.to_thread(
            master_audio_and_export,
            input_video_path=raw_video,
            output_path=final_output,
            bgm_path=None,
            ass_subtitle_path=output_ass,
            use_gpu=False
        )
        print(f"=== SUCCESS ===\nFinal video saved at: {final_output}")
    except Exception as e:
        print(f"=== FAILURE ===\nRender failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
