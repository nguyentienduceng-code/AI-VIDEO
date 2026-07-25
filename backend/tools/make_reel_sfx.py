"""
make_reel_sfx.py — Tổng hợp tiếng trục quay (reel_spin) + tiếng chốt (ding) cho Hook Máy Xèng.

Chạy lại khi muốn tinh chỉnh:  python tools/make_reel_sfx.py

THIẾT KẾ (khác hẳn bản 8-bit cũ):
- Bản cũ là chuỗi sóng vuông arcade dài 3.5 giây, trong khi hình chỉ quay 1.0 giây →
  vừa chói vừa còn kêu 2.5 giây sau khi trục đã dừng, đè lên câu dẫn đầu video.
- Bản mới dài đúng bằng pha quay, và mỗi tiếng "tách" rơi ĐÚNG lúc một bìa sách lướt
  qua tâm màn hình (tính ngược từ chính hàm ease-out của hook_engine), nên tai nghe
  khớp với mắt nhìn. Âm sắc là gỗ/nhựa gõ nhẹ (sine tắt dần + chút noise), không phải
  sóng vuông, nên êm và không lấn giọng đọc.
"""
import os
import numpy as np
import soundfile as sf

SR = 44100
SFX_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "sfx")

# Phải khớp hook_engine.build_carousel_hook
SLOT_DUR = 1.0
NUM_FAKES = 4
SUBDIVISIONS = 8   # gõ 1 tiếng mỗi nửa khoảng bìa → nhịp dày vừa phải


def _tick(freq: float, dur: float, decay: float, noise_amt: float = 0.18) -> np.ndarray:
    """Một tiếng gõ: 2 sine tắt dần (cơ bản + bồi) trộn chút noise cho có 'chất gỗ'."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    env = np.exp(-t / decay)
    body = np.sin(2 * np.pi * freq * t) + 0.45 * np.sin(2 * np.pi * freq * 2.02 * t)
    noise = np.random.default_rng(int(freq)).normal(0, 1, n) * np.exp(-t / (decay * 0.35))
    sig = (body + noise_amt * noise) * env
    # Vào tiếng mềm 1ms để không bị 'click' số
    attack = min(int(0.001 * SR), n)
    sig[:attack] *= np.linspace(0, 1, attack)
    return sig


def _one_pole_lowpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    """Lọc thông thấp 1 cực — cắt phần chói trên 6kHz để tiếng không gắt."""
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc = (1 - a) * v + a * acc
        y[i] = acc
    return y


def build_reel_spin() -> np.ndarray:
    """Chuỗi tiếng gõ giảm dần theo ĐÚNG đường ease-out bậc 3 của hình."""
    total = SLOT_DUR + 0.18                      # dư 0.18s cho đuôi tiếng cuối tắt hẳn
    out = np.zeros(int(total * SR), dtype=np.float64)

    for k in range(1, SUBDIVISIONS + 1):
        # hook_engine: scroll(p) = (1-(1-p)^3) * NUM_FAKES * gap.
        # Bìa thứ k/SUBDIVISIONS lướt qua tâm khi scroll = k/SUBDIVISIONS của tổng quãng.
        frac = k / SUBDIVISIONS
        p = 1.0 - (1.0 - frac) ** (1.0 / 3.0)
        t0 = p * SLOT_DUR

        # Càng chậm lại thì tiếng càng trầm và dài hơn một chút (cảm giác nặng dần)
        freq = 1550 - 420 * frac
        decay = 0.014 + 0.020 * frac
        amp = 0.62 - 0.16 * frac
        tick = _tick(freq, dur=0.16, decay=decay) * amp

        s = int(t0 * SR)
        e = min(s + len(tick), len(out))
        out[s:e] += tick[: e - s]

    # Lớp "gió" rất khẽ bên dưới, tắt dần theo đà quay
    t = np.arange(len(out)) / SR
    air = np.random.default_rng(7).normal(0, 1, len(out))
    air = _one_pole_lowpass(air, 900) * 0.09 * np.clip(1.0 - t / SLOT_DUR, 0, 1) ** 2
    out += air

    out = _one_pole_lowpass(out, 6000)

    # Fade-out cuối 60ms để nối liền sang tiếng chốt
    fade = int(0.06 * SR)
    out[-fade:] *= np.linspace(1, 0, fade)

    peak = np.max(np.abs(out))
    return (out / peak * 0.5).astype(np.float32)   # đỉnh 0.5: nhẹ, không lấn giọng


def build_ding() -> np.ndarray:
    """Tiếng chốt: chuông nhỏ trong trẻo, ngắn (0.9s) thay cho bản 1.5s cũ."""
    dur = 0.9
    n = int(dur * SR)
    t = np.arange(n) / SR
    # Bộ bồi âm kiểu chuông (tỉ lệ không nguyên → nghe 'kim loại' chứ không 'đàn')
    partials = [(1.0, 1.00, 0.55), (2.76, 0.42, 0.38), (5.40, 0.18, 0.24), (8.93, 0.09, 0.16)]
    base = 1180.0
    sig = np.zeros(n)
    for ratio, amp, tau in partials:
        sig += amp * np.sin(2 * np.pi * base * ratio * t) * np.exp(-t / tau)

    attack = int(0.002 * SR)
    sig[:attack] *= np.linspace(0, 1, attack)
    sig = _one_pole_lowpass(sig, 9000)
    fade = int(0.08 * SR)
    sig[-fade:] *= np.linspace(1, 0, fade)

    peak = np.max(np.abs(sig))
    return (sig / peak * 0.45).astype(np.float32)


def main():
    os.makedirs(SFX_DIR, exist_ok=True)
    for name, data in (("reel_spin", build_reel_spin()), ("ding", build_ding())):
        path = os.path.join(SFX_DIR, f"{name}.wav")
        # Giữ bản cũ lại phòng khi muốn quay về
        if os.path.exists(path):
            backup = os.path.join(SFX_DIR, f"{name}_v1_arcade.wav")
            if not os.path.exists(backup):
                os.replace(path, backup)
                print(f"  đã lưu bản cũ -> {os.path.basename(backup)}")
        sf.write(path, data, SR)
        print(f"  {name}.wav: {len(data)/SR:.3f}s, đỉnh {np.max(np.abs(data)):.2f}")


if __name__ == "__main__":
    main()
