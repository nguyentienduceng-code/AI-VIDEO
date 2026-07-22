"""Test generate-video endpoint — storyteller mode with 6 scenes."""
import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import requests
import time
import sys

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# 1. Generate Script
script_payload = {
    "mode": "storyteller",
    "topic": "5 lý do nên học lập trình Python năm 2026",
    "num_scenes": 6,
    "art_style": "Cinematic"
}

print("📤 Generating script...")
resp_script = requests.post('http://127.0.0.1:8000/api/generate-script', json=script_payload)
print(f"Script Status: {resp_script.status_code}")
if resp_script.status_code != 200:
    print(f"❌ Script Generation Failed: {resp_script.text}")
    exit(1)

script_data = resp_script.json()
scenes = script_data.get('scenes', script_data) if isinstance(script_data, dict) else script_data

if not scenes:
    print("❌ No scenes generated.")
    exit(1)

# 2. Submit render job
render_payload = {
    "mode": "storyteller",
    "scenes": scenes,
    "aspect_ratio": "9:16",
    "voice": "minion_pro",
    "speech_rate": "+0%",
    "use_veo": False
}

print("📤 Submitting render job...")
resp = requests.post('http://127.0.0.1:8000/api/render-video', json=render_payload)
print(f"Status: {resp.status_code}")
data = resp.json()
print(f"Response: {data}")

if resp.status_code != 200:
    print(f"❌ Failed: {data}")
    exit(1)

job_id = data['job_id']
print(f"✅ Job created: {job_id}")

# 2. Poll status
print("\n⏳ Polling job status...")
for i in range(180):  # max 15 minutes
    time.sleep(5)
    resp = requests.get(f'http://127.0.0.1:8000/api/job-status/{job_id}')
    job = resp.json()
    status = job['status']
    progress = job['progress']
    message = job['message']
    print(f"  [{i*5:>3}s] {status} — {progress}% — {message}")
    
    if status == 'done':
        print(f"\n✅ VIDEO DONE!")
        print(f"   Video URL: {job.get('video_url')}")
        print(f"   SRT URL: {job.get('srt_url')}")
        scenes = job.get('scenes', [])
        if scenes:
            print(f"   Scenes: {len(scenes)} cảnh")
            for i, s in enumerate(scenes):
                print(f"     Cảnh {i+1}: {s.get('text', '')[:60]}...")
            
        print("\n")
        break
    
    if status == 'error':
        print(f"\n❌ ERROR: {job.get('error')}")
        break
else:
    print("\n⏰ Timeout after 10 minutes")
