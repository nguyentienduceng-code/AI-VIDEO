"""
Tạo bell_chime.wav và heartbeat_dramatic.wav cho Literary Mode.
Dùng wave module (built-in) — không cần FFmpeg.
"""
import math
import struct
import wave
import os

SAMPLE_RATE = 44100

def create_bell_chime(output_path: str, duration_ms: int = 800):
    """Tạo bell_chime.wav - chime nhẹ nhàng với harmonics."""
    import numpy as np

    n_samples = int(SAMPLE_RATE * duration_ms / 1000)
    t = np.linspace(0, duration_ms / 1000, n_samples, False)

    # Fundamental + harmonics (bell-like)
    freq = 880  # A5
    signal = (
        0.6 * np.sin(2 * np.pi * freq * t) +
        0.25 * np.sin(2 * np.pi * freq * 2 * t) +   # octave
        0.10 * np.sin(2 * np.pi * freq * 3 * t) +  # fifth
        0.05 * np.sin(2 * np.pi * freq * 4.2 * t)   # inharmonic
    )

    # Envelope: quick attack, slow decay
    attack = int(0.01 * n_samples)
    decay = np.linspace(1.0, 0.001, n_samples - attack)
    envelope = np.concatenate([np.linspace(0, 1, attack), decay])

    signal = signal * envelope
    signal = (signal * 16384).astype(np.int16)

    with wave.open(output_path, 'w') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(signal.tobytes())

    print(f"Created: {output_path}")


def create_heartbeat_dramatic(output_path: str, bpm: int = 72, beats: int = 3):
    """Tạo heartbeat_dramatic.wav - heartbeat rõ ràng hơn, có reverb tail."""
    import numpy as np

    beat_interval = 60.0 / bpm
    total_duration = beat_interval * beats
    n_samples = int(SAMPLE_RATE * total_duration)
    signal = np.zeros(n_samples)

    for i in range(beats):
        start = int(i * beat_interval * SAMPLE_RATE)

        # Lub-dub pattern
        lub_start = start
        lub_dur = int(0.07 * SAMPLE_RATE)
        lub_env = np.hanning(lub_dur * 2)[:lub_dur]
        lub_t = np.linspace(0, 0.07, lub_dur, False)
        lub = np.sin(2 * np.pi * 40 * lub_t) * lub_env * 0.8

        dub_start = start + int(0.15 * SAMPLE_RATE)
        dub_dur = int(0.06 * SAMPLE_RATE)
        dub_env = np.hanning(dub_dur * 2)[:dub_dur]
        dub_t = np.linspace(0, 0.06, dub_dur, False)
        dub = np.sin(2 * np.pi * 35 * dub_t) * dub_env * 0.5

        # Place
        end_lub = min(lub_start + lub_dur, n_samples)
        end_dub = min(dub_start + dub_dur, n_samples)
        signal[lub_start:end_lub] += lub[:end_lub - lub_start]
        signal[dub_start:end_dub] += dub[:end_dub - dub_start]

        # Reverb tail
        reverb_start = start + int(0.1 * SAMPLE_RATE)
        reverb_dur = int(0.4 * SAMPLE_RATE)
        reverb_env = np.exp(-np.linspace(0, 8, reverb_dur))
        reverb_t = np.linspace(0, 0.4, reverb_dur, False)
        reverb = np.sin(2 * np.pi * 30 * reverb_t) * reverb_env * 0.15
        end_rev = min(reverb_start + reverb_dur, n_samples)
        signal[reverb_start:end_rev] += reverb[:end_rev - reverb_start]

    signal = (signal * 16384).astype(np.int16)

    with wave.open(output_path, 'w') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(signal.tobytes())

    print(f"Created: {output_path}")


if __name__ == "__main__":
    sfx_dir = os.path.join(os.path.dirname(__file__), "..", "assets", "sfx")
    sfx_dir = os.path.abspath(sfx_dir)
    os.makedirs(sfx_dir, exist_ok=True)

    create_bell_chime(os.path.join(sfx_dir, "bell_chime.wav"))
    create_heartbeat_dramatic(os.path.join(sfx_dir, "heartbeat_dramatic.wav"))
    print("Done!")
