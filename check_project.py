import sys, json, os
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Check latest project deeply
fp = r"D:\AI VIDEO\projects\19cd9a3c-7aea-4f7b-84cb-76780611b0d3.json"
d = json.load(open(fp, 'r', encoding='utf-8'))

req = d.get('req', {})
print("=== req keys:", list(req.keys()))
print("Voice in req:", req.get('voice'))
print("Title:", d.get('title'))
print("Mode:", d.get('mode'))
print("Status:", d.get('status'))
print()

scenes = d.get('scenes', [])
for i, s in enumerate(scenes[:3]):
    print(f"--- Scene {i} keys: {list(s.keys())}")
    print(f"    narration: {str(s.get('narration',''))[:100]}")
    print(f"    narration_audio: {s.get('narration_audio','(none)')}")
    print(f"    voice: {s.get('voice','(none)')}")
    # Check for warning/error in scene
    for k in s.keys():
        if 'warn' in k.lower() or 'error' in k.lower() or 'fallback' in k.lower():
            print(f"    {k}: {str(s[k])[:200]}")
    print()

# Check output directory for latest video
output_dir = r"D:\AI VIDEO\output"
if os.path.exists(output_dir):
    vids = [(f, os.path.getmtime(os.path.join(output_dir, f))) for f in os.listdir(output_dir) if f.endswith(('.mp4','.mkv'))]
    vids.sort(key=lambda x: x[1], reverse=True)
    print("=== Latest videos ===")
    for v, t in vids[:5]:
        import datetime
        print(f"  {v} ({os.path.getsize(os.path.join(output_dir, v))//1024} KB) - {datetime.datetime.fromtimestamp(t)}")

# Check audio directory for latest audio files
audio_dir = r"D:\AI VIDEO\audio"
if os.path.exists(audio_dir):
    auds = [(f, os.path.getmtime(os.path.join(audio_dir, f))) for f in os.listdir(audio_dir) if f.endswith(('.mp3','.wav'))]
    auds.sort(key=lambda x: x[1], reverse=True)
    print("\n=== Latest audio files ===")
    for a, t in auds[:10]:
        import datetime
        print(f"  {a} ({os.path.getsize(os.path.join(audio_dir, a))//1024} KB) - {datetime.datetime.fromtimestamp(t)}")
