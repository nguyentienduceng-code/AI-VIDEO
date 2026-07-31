import argparse
import os
import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.abspath("backend"))

import subprocess
import whisper
from backend.services.tts_service import register_custom_voice, VOICES_PREVIEW_DIR

import imageio_ffmpeg


def main():
    parser = argparse.ArgumentParser(
        description="Cài một file ghi âm thành giọng Clone OmniVoice (chuyển WAV 24kHz + tự transcript qua Whisper)."
    )
    parser.add_argument("input_audio", help="Đường dẫn file ghi âm nguồn (.wav/.ogg/.m4a/.mp3/...)")
    parser.add_argument("voice_id", help='ID giọng, vd: omnivoice_custom_ten_giong (bắt buộc tiền tố "omnivoice_custom_" để UI nhận diện)')
    parser.add_argument("voice_name", help='Tên hiển thị trên UI, vd: "Nam Tiến Đức (OmniVoice Clone)"')
    parser.add_argument("--lang", default="vi", help="Mã ngôn ngữ cho Whisper transcribe (mặc định: vi)")
    args = parser.parse_args()

    if not os.path.isfile(args.input_audio):
        sys.exit(f"Không tìm thấy file: {args.input_audio}")

    voice_id = args.voice_id
    voice_name = args.voice_name

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    os.makedirs(VOICES_PREVIEW_DIR, exist_ok=True)
    wav_path = os.path.join(VOICES_PREVIEW_DIR, f"{voice_id}_ref.wav")
    mp3_path = os.path.join(VOICES_PREVIEW_DIR, f"{voice_id}.mp3")

    print("Converting to 24000Hz WAV...")
    subprocess.run([ffmpeg_exe, "-y", "-i", args.input_audio, "-ar", "24000", "-ac", "1", wav_path],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("Converting to MP3 for UI preview...")
    subprocess.run([ffmpeg_exe, "-y", "-i", args.input_audio, mp3_path],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("Transcribing WAV...")
    import soundfile as sf
    import numpy as np
    model = whisper.load_model("base")
    audio, sr = sf.read(wav_path)
    if audio.dtype != np.float32:
        audio = audio.astype(np.float32)

    result = model.transcribe(audio, language=args.lang, fp16=False)
    ref_text = result["text"].strip()
    print(f"Transcript: {ref_text}")

    print("Registering voice in database...")
    register_custom_voice(voice_id, voice_name, ref_text)

    print(f"Success! Voice {voice_name} installed with ID: {voice_id}")


if __name__ == "__main__":
    main()
