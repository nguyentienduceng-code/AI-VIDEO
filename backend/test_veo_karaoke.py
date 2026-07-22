import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import generate_script, _run_render_pipeline, GenerateScriptRequest, RenderVideoRequest

async def test():
    # 1. Test generate_script
    print("--- 1. Testing generate_script ---")
    script_req = GenerateScriptRequest(
        topic="Sự thật thú vị về lỗ đen",
        mode="quiz_listicle",
        num_scenes=2, # Giữ số lượng ít để test nhanh
    )
    
    scenes_response = await generate_script(script_req)
    
    # generate_script now returns a dict with "scenes"
    if isinstance(scenes_response, dict) and "scenes" in scenes_response:
        scenes = scenes_response["scenes"]
    else:
        print("Error: Invalid response from generate_script")
        return
        
    print(f"Generated {len(scenes)} scenes:")
    for s in scenes:
        print(f" - {s.get('text', '')[:30]}...")
        
    # 2. Test render_video
    print("\n--- 2. Testing _run_render_pipeline (Cinematic Box + Watermark) ---")
    render_req = RenderVideoRequest(
        scenes=scenes,
        mode="storyteller",
        use_veo=False, # Tắt Veo để test nhanh (tránh tốn quota API)
        voice="vi-VN-HoaiMyNeural",
        speech_rate="+0%",
        subtitle_style="cinematic_box",
        watermark_text="@tester_watermark",
        use_gpu_encode=True
    )
    
    job_id = "test_pipeline_cinematic"
    print(f"Running render pipeline for job: {job_id}...")
    await _run_render_pipeline(job_id, render_req)
    print("Pipeline completed. Check assets/output for test_pipeline_cinematic.mp4 and .ass")

if __name__ == "__main__":
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(test())
