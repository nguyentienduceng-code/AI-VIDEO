"""Test generate-video endpoint — storyteller mode with 6 scenes."""
import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import requests
import time

# 1. Submit job
payload = {
    "mode": "storyteller",
    "topic": "5 lý do nên học lập trình Python năm 2026",
    "num_scenes": 6,
    "aspect_ratio": "9:16",
    "art_style": "Cinematic",
    "voice": "vi-VN-HoaiMyNeural",
    "speech_rate": "+0%",
}

print("📤 Submitting job...")
resp = requests.post('http://127.0.0.1:8000/api/generate-video', json=payload)
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
for i in range(120):  # max 10 minutes
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
        if job.get('scenes'):
            print(f"   Scenes: {len(job['scenes'])} cảnh")
            for s in job['scenes']:
                print(f"     Cảnh {s['scene']}: {s['text'][:60]}...")
        break
    
    if status == 'error':
        print(f"\n❌ ERROR: {job.get('error')}")
        break
else:
    print("\n⏰ Timeout after 10 minutes")
