import os
import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
import subprocess
import imageio_ffmpeg

SFX_DIR = r"C:\dev\AI-VIDEO-MAKER\backend\assets\sfx"

RECIPES = {
    "typewriter_clack": "anoisesrc=d=0.05:c=white,bandpass=f=2000,afade=t=out:st=0:d=0.05",
    "ui_click": "sine=f=1200:d=0.03,afade=t=out:st=0:d=0.03",
    "whip_whoosh": "anoisesrc=d=0.3:c=pink,lowpass=f=3000,afade=t=in:st=0:d=0.1,afade=t=out:st=0.1:d=0.2",
    "camera_fast": "anoisesrc=d=0.3:c=white,tremolo=f=10:d=1,afade=t=out:st=0.2:d=0.1",
    "tape_rewind": "anoisesrc=d=0.5:c=brown,flanger,afade=t=in:st=0:d=0.1,afade=t=out:st=0.4:d=0.1",
    "braam_horn": "sine=f=55:d=2.0,vibrato=f=2,afade=t=in:st=0:d=0.2,afade=t=out:st=1.0:d=1.0",
    "deep_breath": "anoisesrc=d=1.5:c=pink,bandpass=f=600:width_type=h:w=300,afade=t=in:st=0:d=0.7,afade=t=out:st=0.7:d=0.8",
    "clock_tick": "sine=f=1500:d=0.02,afade=t=out:st=0:d=0.02",
    "cash_register": "sine=f=3000:d=0.2,afade=t=in:st=0:d=0.01,afade=t=out:st=0.05:d=0.15",
    "page_turn": "anoisesrc=d=0.4:c=brown,bandpass=f=800,afade=t=in:st=0:d=0.1,afade=t=out:st=0.2:d=0.2"
}

def generate_sfx():
    print("🎬 Đang tổng hợp 10 SFX chuyên nghiệp bằng thuật toán FFmpeg...")
    os.makedirs(SFX_DIR, exist_ok=True)
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    
    for name, lavfi_expr in RECIPES.items():
        out_path = os.path.join(SFX_DIR, f"{name}.wav")
        cmd = [
            ffmpeg_exe, "-y", 
            "-f", "lavfi", 
            "-i", lavfi_expr,
            out_path
        ]
        print(f"Synthesizing: {name}.wav")
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError as e:
            print(f"Lỗi khi tổng hợp {name}: {e}")

if __name__ == "__main__":
    generate_sfx()
    print("✅ Hoàn tất tổng hợp.")
