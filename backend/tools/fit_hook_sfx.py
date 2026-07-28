"""
fit_hook_sfx.py — Nạp một file âm thanh tải về thành tiếng trục quay hợp lệ cho Hook Máy Xèng.

    python tools/fit_hook_sfx.py "C:\\path\\mubeenstudio-money-counting-machine-sfx-406495.mp3" --name money_counter

Làm gì:
1. Đọc mọi định dạng (mp3/wav/ogg/m4a) qua FFmpeg, đưa về 44.1kHz mono.
2. TỰ TÌM đoạn 1.18 giây "kêu nhất" thay vì cắt mù từ giây 0 — file tải trên mạng
   thường có 0.2-0.5 giây im lặng đầu file.
3. Cắt đúng độ dài pha quay, vào/ra mềm để không kêu "pắc" ở chỗ cắt.
4. Chuẩn hoá đỉnh về 0.5 cho ngang bằng các tiếng có sẵn (không lấn giọng đọc).
5. Ghi ra assets/sfx/reel_<name>.wav.

Sau khi chạy, khai báo thêm 1 dòng trong:
  - backend/services/video_service.py  → HOOK_REEL_SOUNDS
  - frontend/src/constants.js          → HOOK_REEL_SOUNDS
"""
import argparse
import os
import subprocess
import sys
import tempfile

import numpy as np
import soundfile as sf

SR = 44100
TARGET_DUR = 2.18          # khớp reel_spin.wav mặc định (pha quay 2.0s + đuôi 0.18s)
                           # = hook_engine.SLOT_DURATION + 0.18
TARGET_PEAK = 0.5
SFX_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "sfx")


def _atempo_chain(factor: float) -> str:
    """atempo chỉ nhận 0.5-2.0 mỗi tầng → xâu nhiều tầng cho hệ số lớn."""
    stages = []
    remain = factor
    while remain > 2.0:
        stages.append(2.0)
        remain /= 2.0
    while remain < 0.5:
        stages.append(0.5)
        remain /= 0.5
    stages.append(remain)
    return ",".join(f"atempo={s:.6f}" for s in stages)


def _decode(path: str, tempo: float = 1.0) -> np.ndarray:
    """
    Giải mã file bất kỳ về mảng mono 44.1kHz bằng FFmpeg đi kèm imageio_ffmpeg.
    `tempo` > 1 nén thời gian (atempo GIỮ NGUYÊN cao độ, chỉ chạy nhanh hơn).
    """
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    fd, wav = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        cmd = [ff, "-y", "-i", path, "-ac", "1", "-ar", str(SR)]
        if abs(tempo - 1.0) > 1e-3:
            cmd += ["-filter:a", _atempo_chain(tempo)]
        cmd += ["-f", "wav", wav]
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        data, _ = sf.read(wav, dtype="float32", always_2d=False)
        return np.asarray(data, dtype=np.float64)
    finally:
        if os.path.exists(wav):
            os.remove(wav)


def _loudest_window(x: np.ndarray, dur: float) -> np.ndarray:
    """Cửa sổ `dur` giây có năng lượng cao nhất — bỏ qua im lặng đầu/cuối file."""
    n = int(dur * SR)
    if len(x) <= n:
        return x
    # Tổng tích luỹ của bình phương → năng lượng mọi cửa sổ trong 1 lượt
    energy = np.concatenate([[0.0], np.cumsum(x.astype(np.float64) ** 2)])
    sums = energy[n:] - energy[:-n]
    start = int(np.argmax(sums))
    return x[start:start + n]


def main():
    # Chạy trực tiếp bằng python.exe thì stdout là cp1252 và MỌI dòng in có dấu tiếng
    # Việt sẽ ném UnicodeEncodeError — công cụ chết trước cả khi đụng tới file âm thanh.
    # Xem services/log_setup.py.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from services.log_setup import force_utf8_streams
        force_utf8_streams()
    except Exception:
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="File âm thanh tải về")
    ap.add_argument("--name", required=True, help="Mã ngắn, VD: money_counter")
    ap.add_argument("--duration", type=float, default=TARGET_DUR)
    ap.add_argument("--peak", type=float, default=TARGET_PEAK)
    ap.add_argument("--from-start", action="store_true",
                    help="Cắt từ đầu file thay vì tự tìm đoạn kêu nhất")
    ap.add_argument("--compress", action="store_true",
                    help="NÉN THỜI GIAN cả file về đúng độ dài (giữ nguyên cao độ) thay vì "
                         "cắt lấy một đoạn. Dùng khi file có cấu trúc 'chạy rồi tự dừng' — "
                         "cắt đoạn giữa sẽ vứt mất chính cái kết đó.")
    ap.add_argument("--out",
                    help="Tên file ra trong assets/sfx/ (mặc định 'reel_<name>.wav'). "
                         "Công cụ này ban đầu chỉ dùng cho tiếng trục quay Máy Xèng nên "
                         "tiền tố 'reel_' bị gắn cứng; giờ nó nạp tiếng cho MỌI hiệu ứng "
                         "nên tên phải đặt được. VD: --out ambient_mystic.wav")
    args = ap.parse_args()

    if not os.path.isfile(args.input):
        sys.exit(f"Không thấy file: {args.input}")

    probe = _decode(args.input)
    src_dur = len(probe) / SR
    print(f"  Nguồn: {os.path.basename(args.input)} — {src_dur:.2f}s")

    n = int(args.duration * SR)

    if args.compress and src_dur > args.duration:
        tempo = src_dur / args.duration
        x = _decode(args.input, tempo=tempo)
        print(f"  Nén thời gian x{tempo:.2f} (giữ nguyên cao độ) → {len(x)/SR:.2f}s")
        y = x[:n]
    else:
        x = probe
        if args.from_start or len(x) <= n:
            y = x[:n]
        else:
            y = _loudest_window(x, args.duration)
            print(f"  Đã chọn đoạn kêu nhất dài {len(y)/SR:.2f}s")

    if len(y) < n:   # file ngắn hơn yêu cầu → đệm im lặng phía sau
        y = np.pad(y, (0, n - len(y)))

    # Vào 8ms / ra 80ms cho mềm
    a = min(int(0.008 * SR), len(y))
    b = min(int(0.080 * SR), len(y))
    y[:a] *= np.linspace(0, 1, a)
    y[-b:] *= np.linspace(1, 0, b)

    peak = float(np.max(np.abs(y)))
    if peak <= 0:
        sys.exit("File chỉ có im lặng.")
    y = (y / peak * args.peak).astype(np.float32)

    os.makedirs(SFX_DIR, exist_ok=True)
    out = os.path.join(SFX_DIR, args.out or f"reel_{args.name}.wav")
    sf.write(out, y, SR)
    print(f"  Đã ghi: {out} — {len(y)/SR:.3f}s, đỉnh {np.max(np.abs(y)):.2f}")
    print(f"\n  Còn 2 bước: khai báo '{args.name}' trong HOOK_REEL_SOUNDS ở")
    print("    backend/services/video_service.py  và  frontend/src/constants.js")


if __name__ == "__main__":
    main()
