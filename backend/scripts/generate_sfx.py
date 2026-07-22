import os
import numpy as np
from scipy.io import wavfile

SFX_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "sfx")
os.makedirs(SFX_DIR, exist_ok=True)

def generate_pop(filename="pop.wav"):
    sample_rate = 44100
    duration = 0.1
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    freqs = np.linspace(800, 100, len(t))
    audio = np.sin(2 * np.pi * freqs * t)
    envelope = np.exp(-t * 50)
    audio = audio * envelope
    audio = np.int16(audio / np.max(np.abs(audio)) * 32767)
    wavfile.write(os.path.join(SFX_DIR, filename), sample_rate, audio)
    print(f"Generated {filename}")

def generate_whoosh(filename="whoosh.wav"):
    sample_rate = 44100
    duration = 0.5
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    noise = np.random.normal(0, 1, len(t))
    envelope = np.sin(np.pi * (t / duration)) ** 2
    window_size = 50
    filtered_noise = np.convolve(noise, np.ones(window_size)/window_size, mode='same')
    audio = filtered_noise * envelope
    audio = np.int16(audio / np.max(np.abs(audio)) * 32767)
    wavfile.write(os.path.join(SFX_DIR, filename), sample_rate, audio)
    print(f"Generated {filename}")

def generate_ding(filename="ding.wav"):
    sample_rate = 44100
    duration = 1.0
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    audio = np.sin(2 * np.pi * 800 * t) + 0.5 * np.sin(2 * np.pi * 1600 * t)
    envelope = np.exp(-t * 5)
    audio = audio * envelope
    audio = np.int16(audio / np.max(np.abs(audio)) * 32767)
    wavfile.write(os.path.join(SFX_DIR, filename), sample_rate, audio)
    print(f"Generated {filename}")

def generate_riser(filename="riser.wav"):
    sample_rate = 44100
    duration = 3.0
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    freqs = np.linspace(50, 800, len(t))
    audio = np.sin(2 * np.pi * freqs * t)
    envelope = (t / duration) ** 2
    audio = audio * envelope
    audio = np.int16(audio / np.max(np.abs(audio)) * 32767)
    wavfile.write(os.path.join(SFX_DIR, filename), sample_rate, audio)
    wavfile.write(os.path.join(SFX_DIR, filename), sample_rate, audio)
    print(f"Generated {filename}")

def generate_bell(filename="bell.wav"):
    sample_rate = 44100
    duration = 2.0
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    # Bell sound with multiple harmonics
    audio = (1.0 * np.sin(2 * np.pi * 500 * t) * np.exp(-t * 2) +
             0.5 * np.sin(2 * np.pi * 1000 * t) * np.exp(-t * 4) +
             0.2 * np.sin(2 * np.pi * 1500 * t) * np.exp(-t * 6))
    audio = np.int16(audio / np.max(np.abs(audio)) * 32767)
    wavfile.write(os.path.join(SFX_DIR, filename), sample_rate, audio)
    print(f"Generated {filename}")

def generate_suspense(filename="suspense.wav"):
    sample_rate = 44100
    duration = 4.0
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    # Low frequency drone
    audio = np.sin(2 * np.pi * 60 * t) + 0.5 * np.sin(2 * np.pi * 62 * t)
    envelope = np.minimum(t, 1.0) * np.exp(-t * 0.2)
    audio = audio * envelope
    audio = np.int16(audio / np.max(np.abs(audio)) * 32767)
    wavfile.write(os.path.join(SFX_DIR, filename), sample_rate, audio)
    print(f"Generated {filename}")

def generate_impact(filename="impact.wav"):
    sample_rate = 44100
    duration = 1.0
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    noise = np.random.normal(0, 1, len(t))
    low_freq = np.sin(2 * np.pi * np.linspace(150, 20, len(t)) * t)
    audio = (noise * 0.5 + low_freq) * np.exp(-t * 10)
    audio = np.int16(audio / np.max(np.abs(audio)) * 32767)
    wavfile.write(os.path.join(SFX_DIR, filename), sample_rate, audio)
    print(f"Generated {filename}")

def generate_laugh(filename="laugh.wav"):
    # Simple placeholder for a laugh (just some bouncy noise)
    sample_rate = 44100
    duration = 1.5
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    noise = np.random.normal(0, 1, len(t))
    # Bounce envelope
    envelope = np.abs(np.sin(2 * np.pi * 4 * t)) * np.exp(-t * 2)
    audio = noise * envelope
    # Bandpass around human voice freq (placeholder)
    audio = np.int16(audio / np.max(np.abs(audio)) * 32767)
    wavfile.write(os.path.join(SFX_DIR, filename), sample_rate, audio)
    print(f"Generated {filename}")

if __name__ == "__main__":
    generate_pop()
    generate_whoosh()
    generate_ding()
    generate_riser()
    generate_bell()
    generate_suspense()
    generate_impact()
    generate_laugh()
    print("Done generating SFX!")
