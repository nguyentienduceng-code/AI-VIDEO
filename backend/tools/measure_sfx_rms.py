"""
Measure RMS + peak of Literary Mode SFX files.
Run: python tools/measure_sfx_rms.py
"""
import os
import sys
import math
import struct
import wave

def measure_wav(path):
    with wave.open(path, 'rb') as w:
        sw = w.getsampwidth()
        nch = w.getnchannels()
        sr = w.getframerate()
        # Use readframes(-1) instead of nframes to get all available data
        data = w.readframes(-1)
        n = len(data) // (sw * nch)
    fmt = {1: 'b', 2: 'h', 4: 'i'}[sw]
    samples = list(struct.unpack(f'<{n * nch}{fmt}', data))
    if nch == 2:
        samples = samples[::2]
    rms = math.sqrt(sum(s*s for s in samples) / len(samples))
    peak = max(abs(s) for s in samples)
    rms_db = 20 * math.log10(rms / 32768 + 1e-10)
    peak_db = 20 * math.log10(peak / 32768 + 1e-10)
    return rms, peak, rms_db, peak_db

SFX_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "sfx")
SFX_DIR = os.path.abspath(SFX_DIR)

LITERARY_SFX = [
    "bell_chime.wav",
    "heartbeat_dramatic.wav",
    # Also check existing files used in LITERARY_SFX_MAP
    "bell.wav",
    "shimmer.wav",
    "cinematic_swell.wav",
    "riser.wav",
    "heartbeat.wav",
    "suspense.wav",
    "breath.wav",
    "ambient_mystic.wav",
    "tick.wav",
    "impact.wav",
    "bass_drop.wav",
    "whoosh.wav",
]

TARGET_DB = -22.0  # Same target as SCENE_SFX_GAIN

print(f"{'File':<30} {'RMS dB':>8} {'Peak dB':>8} {'Target dB':>10} {'Suggested Gain':>14}")
print("-" * 75)

results = {}
for fname in LITERARY_SFX:
    path = os.path.join(SFX_DIR, fname)
    if not os.path.isfile(path):
        print(f"{fname:<30} {'NOT FOUND':>8}")
        continue
    rms, peak, rms_db, peak_db = measure_wav(path)
    # Gain to bring RMS to target
    suggested_gain = 10 ** ((TARGET_DB - rms_db) / 20)
    suggested_gain = min(suggested_gain, 3.5)  # cap at 3.5 like SCENE_SFX_GAIN
    results[fname] = {
        "rms_db": round(rms_db, 1),
        "peak_db": round(peak_db, 1),
        "suggested_gain": round(suggested_gain, 3),
    }
    print(f"{fname:<30} {rms_db:>8.1f} {peak_db:>8.1f} {TARGET_DB:>10.1f} {suggested_gain:>14.3f}")

print("\n=== Literary SFX MAP gain_boost suggestions ===")
LITERARY_MAP = {
    "fiction": {"primary": "bell", "secondary": "shimmer"},
    "philosophy": {"primary": "cinematic_swell", "secondary": "riser"},
    "thriller": {"primary": "heartbeat", "secondary": "suspense"},
    "spiritual": {"primary": "breath", "secondary": "ambient_mystic"},
    "poetry": {"primary": "tick", "secondary": "bell"},
    "raw_truth": {"primary": "impact", "secondary": "bass_drop"},
}
for genre, cfg in LITERARY_MAP.items():
    print(f"\n{genre}:")
    for key in ["primary", "secondary"]:
        name = cfg[key]
        wav = f"{name}.wav"
        mp3 = f"{name}.mp3"
        if wav in results:
            r = results[wav]
            print(f"  {key}: {name} -> RMS {r['rms_db']}dB -> suggested SCENE_SFX_GAIN={r['suggested_gain']}")
        elif mp3 in results:
            print(f"  {key}: {name} (mp3) -> check manually")
        else:
            print(f"  {key}: {name} -> NOT FOUND")
