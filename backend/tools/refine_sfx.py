import os
import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
import subprocess

SFX_DIR = r"C:\dev\AI-VIDEO-MAKER\backend\assets\sfx"

# Cấu hình xử lý cho từng loại âm thanh (CapCut Standard: ngắn, sắc, dứt khoát)
SFX_PROFILES = {
    "swoosh_soft.wav": {"duration": 0.6, "fade_out": 0.2, "volume": "-4dB", "speed": 1.5},
    "whoosh.wav": {"duration": 0.4, "fade_out": 0.1, "volume": "-4dB", "speed": 1.5},
    "pop.wav": {"duration": 0.15, "fade_out": 0.05, "volume": "-2dB", "speed": 1.0},
    "impact.wav": {"duration": 1.2, "fade_out": 0.5, "volume": "-6dB", "speed": 1.0},
    "bass_drop.wav": {"duration": 1.5, "fade_out": 0.5, "volume": "-8dB", "speed": 1.0},
    "riser.wav": {"duration": 2.5, "fade_out": 0.2, "volume": "-4dB", "speed": 1.0},
    "digital_glitch.mp3": {"duration": 0.4, "fade_out": 0.1, "volume": "-6dB", "speed": 1.0},
    "bell_chime.wav": {"duration": 1.0, "fade_out": 0.3, "volume": "-3dB", "speed": 1.0}
}

def process_sfx():
    print("🎬 Đang xử lý bộ SFX thành chuẩn CapCut...")
    
    for filename, profile in SFX_PROFILES.items():
        in_path = os.path.join(SFX_DIR, filename)
        if not os.path.exists(in_path):
            print(f"Bỏ qua {filename} (Không tồn tại)")
            continue
            
        out_filename = filename.replace(".wav", "_capcut.wav").replace(".mp3", "_capcut.wav")
        out_path = os.path.join(SFX_DIR, out_filename)
        
        speed = profile["speed"]
        vol = profile["volume"]
        dur = profile["duration"]
        fade = profile["fade_out"]
        fade_start = max(0.01, dur - fade)
        
        filter_chain = []
        if speed != 1.0:
            filter_chain.append(f"atempo={speed}")
        filter_chain.append(f"volume={vol}")
        filter_chain.append(f"afade=t=out:st={fade_start}:d={fade}")
        
        filters = ",".join(filter_chain)
        
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        
        cmd = [
            ffmpeg_exe, "-y", "-i", in_path,
            "-af", filters,
            "-t", str(dur),
            out_path
        ]
        
        print(f"Đang xử lý: {filename} -> {out_filename}")
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Ghi đè file gốc bằng file đã xử lý để dùng làm mặc định
            os.replace(out_path, in_path.replace(".mp3", ".wav")) 
            if filename.endswith(".mp3"):
                os.remove(in_path)
            
        except subprocess.CalledProcessError as e:
            print(f"Lỗi khi xử lý {filename}: {e}")

if __name__ == "__main__":
    process_sfx()
    print("✅ Đã hoàn tất sàng lọc và cắt đuôi SFX.")
