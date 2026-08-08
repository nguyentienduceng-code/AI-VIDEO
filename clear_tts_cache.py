import sys, os, json, glob
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, 'backend')
from config import CACHE_DIR

target_voice = "omnivoice_custom_nam_tien_duc"
tts_metas = glob.glob(os.path.join(CACHE_DIR, "tts_meta_*.json"))
print(f"Scanning {len(tts_metas)} TTS cache entries for voice '{target_voice}'...")

removed_meta = 0
removed_media = 0
for f in tts_metas:
    try:
        d = json.load(open(f, encoding='utf-8'))
    except Exception:
        continue
    
    # Check all keys for the voice name
    values_str = json.dumps(d)
    if target_voice in values_str:
        print(f"  FOUND in: {os.path.basename(f)} -> {d}")
        # Get the hash part
        hash_part = os.path.basename(f).replace("tts_meta_", "").replace(".json", "")
        # Remove meta
        os.remove(f)
        removed_meta += 1
        # Remove corresponding media
        media_path = os.path.join(CACHE_DIR, "media", f"tts_{hash_part}.mp3")
        if os.path.exists(media_path):
            os.remove(media_path)
            removed_media += 1
            print(f"  REMOVED media: {media_path}")

print(f"\nDone. Removed {removed_meta} meta + {removed_media} media files.")

# Also check the media folder directly for tts files with nam_tien_duc
media_dir = os.path.join(CACHE_DIR, "media")
if os.path.exists(media_dir):
    print(f"\nMedia cache directory has {len(os.listdir(media_dir))} files total.")
