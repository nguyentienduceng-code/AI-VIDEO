"""
tts_service.py
---------------
NÂNG CẤP V3.1 — Sentence-Level Prosody Engine (Robust):
1. Tách câu → gộp câu quá ngắn (<5 từ) với câu kế tiếp để tránh Edge-TTS reject.
2. Ghép nối từng câu với rate/pitch riêng (sentence-by-sentence concat).
3. Nếu câu nào thất bại → gộp vào câu tiếp theo và thử lại.
4. Fallback cuối cùng: gửi toàn bộ text 1 lần (plain text mode).
5. Giữ nguyên Word Boundaries, Minion voices, Emotion Profiles, fallback gTTS.
"""

from __future__ import annotations

import asyncio
import os
import edge_tts
from mutagen.mp3 import MP3

DEFAULT_VOICE = "vi-VN-HoaiMyNeural"
DEFAULT_RATE = "+5%"

VIETNAMESE_VOICES = [
    {"id": "vi-VN-HoaiMyNeural", "name": "Hoài My", "gender": "Nữ"},
    {"id": "vi-VN-NamMinhNeural", "name": "Nam Minh", "gender": "Nam"},
    {"id": "vi-VN-AnNiNeural", "name": "An Ni (Trẻ trung)", "gender": "Nữ"},
    {"id": "vi-VN-PhuongMyNeural", "name": "Phương My (Tin tức)", "gender": "Nữ"},
    {"id": "minion", "name": "Minion (Nhí nhảnh)", "gender": "Ảo"},
    {"id": "minion_pro", "name": "Minion Pro (Hỗn loạn, Cuốn hút)", "gender": "Ảo"},
]

import random
import re


def _minion_pro_transform(text: str) -> str:
    """Biến đổi văn bản thành kiểu nói nhí nhảnh, lúng búng của Minion."""
    gibberish = ["Bello!", "Pô-pa-yê!", "Ba-na-na!", "Tu-la-li-lu!", "Pa-ra tu!", "Hí hí!", "He he he!", "Báp-pôi!"]
    sentences = re.split(r'(?<=[.!?]) +', text.strip())
    transformed = []
    for s in sentences:
        if not s:
            continue
        s = s.replace('.', '?')
        words = s.split()
        if not words:
            continue
        for i, w in enumerate(words):
            if len(w) > 2 and w[0].lower() in ['b', 'p', 'm', 'n'] and random.random() < 0.2:
                words[i] = f"{w[0]}-{w}"
        new_s = ""
        for i, w in enumerate(words):
            new_s += w + " "
            if random.random() < 0.1 and i < len(words) - 1:
                new_s += ", "
        if random.random() < 0.4:
            new_s = random.choice(gibberish) + " " + new_s
        elif random.random() < 0.4:
            new_s = new_s.strip() + " " + random.choice(gibberish)
        transformed.append(new_s.strip())
    return " ".join(transformed)


# ── Emotion Profiles V2 (Kích hoạt pitch_delta ±3-5Hz để thêm diễn cảm giữa các cảnh) ──
# Biên độ nhỏ (±3-5Hz) đủ để tạo cảm xúc mà không làm "biến giọng" khó chịu.
EMOTION_PROFILES = {
    "hook":      {"rate_delta": "+5%",   "pitch_delta": "+3Hz"},
    "calm":      {"rate_delta": "+0%",   "pitch_delta": "-2Hz"},
    "dramatic":  {"rate_delta": "-3%",   "pitch_delta": "-3Hz"},
    "excited":   {"rate_delta": "+5%",   "pitch_delta": "+5Hz"},
    "suspense":  {"rate_delta": "-3%",   "pitch_delta": "-4Hz"},
    "closing":   {"rate_delta": "-2%",   "pitch_delta": "-2Hz"},
}


def _apply_emotion_to_rate_pitch(rate: str, pitch: str, emotion: str) -> tuple:
    """Cộng dồn delta từ emotion profile vào rate/pitch base."""
    profile = EMOTION_PROFILES.get(emotion)
    if not profile:
        return rate, pitch
    rate_match = re.match(r'([+-]?\d+)%', rate)
    base_rate = int(rate_match.group(1)) if rate_match else 0
    delta_rate_match = re.match(r'([+-]?\d+)%', profile["rate_delta"])
    delta_rate = int(delta_rate_match.group(1)) if delta_rate_match else 0
    pitch_match = re.match(r'([+-]?\d+)Hz', pitch)
    base_pitch = int(pitch_match.group(1)) if pitch_match else 0
    delta_pitch_match = re.match(r'([+-]?\d+)Hz', profile["pitch_delta"])
    delta_pitch = int(delta_pitch_match.group(1)) if delta_pitch_match else 0
    return f"{base_rate + delta_rate:+d}%", f"{base_pitch + delta_pitch:+d}Hz"


# ══════════════════════════════════════════════════════════════════════
# V3.1: Sentence-Level Prosody Engine
# ══════════════════════════════════════════════════════════════════════

def _strip_emoji(text: str) -> str:
    """Xóa triệt để 100% Emoji & Icons Unicode khỏi chuỗi."""
    # Dải chính: Supplementary Multilingual Plane (hầu hết emoji hiện đại)
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    # Dải phụ: Miscellaneous Symbols, Dingbats, Misc Technical, Arrows, etc.
    text = re.sub(r'[\u2600-\u27ff\u2300-\u23ff\u2B50-\u2B55\u2B06\u2934\u2935\u200d\ufe0f\u00a9\u00ae\u203c\u2049\u2122\u2139\u2194-\u21aa\u231a-\u231b\u25aa-\u25fe\u2702-\u27b0\u3030\u303d\u3297\u3299]', '', text)
    return text


def _normalize_text(text: str) -> str:
    """Chuẩn hóa văn bản: xóa markdown, dịch viết tắt, lọc 100% emoji/icons."""
    text = text.replace("**", "").replace("*", "").replace("#", "").replace(" - ", ", ")
    acronyms = {
        "VNĐ": "Việt Nam Đồng", "CHDV": "căn hộ dịch vụ",
        "App": "ứng dụng", "AI": "ây ai"
    }
    for k, v in acronyms.items():
        text = text.replace(k, v)
    if "<break" in text:
        text = re.sub(r'<break[^>]*>', '', text).strip()
    # Thay dấu gạch dài (—) bằng dấu phẩy để giữ nhịp ngắt khi đọc
    text = text.replace('—', ',')
    text = text.replace('–', ',')
    # Xóa 100% Emoji & Icons Unicode để TTS không đọc thành chữ
    text = _strip_emoji(text)
    # Chỉ giữ lại ký tự hợp lệ cho TTS
    text = re.sub(r'[^\w\s.,!?:;"\'\-\(\)%/$&+]', '', text)
    # Dọn khoảng trắng thừa và khoảng trắng trước dấu câu
    text = re.sub(r'  +', ' ', text)
    text = re.sub(r'\s+([.,!?:;])', r'\1', text)
    return text.strip()


def _estimate_word_boundaries(text: str, duration: float) -> list:
    """Nội suy word_boundaries dựa trên thời lượng audio cho các TTS không hỗ trợ SSML."""
    words = text.split()
    if not words:
        return []
    total_chars = sum(len(w) for w in words)
    if total_chars == 0:
        return []
    
    wbs = []
    current_time = 0.0
    for w in words:
        w_dur = (len(w) / total_chars) * duration
        wbs.append({
            "offset": current_time,
            "duration": w_dur,
            "text": w
        })
        current_time += w_dur
    return wbs



def _split_and_merge_sentences(text: str, min_words: int = 5) -> list[str]:
    """
    Tách câu theo dấu . ! ? rồi gộp các câu quá ngắn (<min_words từ)
    với câu kế tiếp để tránh Edge-TTS reject.
    """
    raw = re.split(r'(?<=[.!?])\s+', text.strip())
    sentences = [s.strip() for s in raw if s.strip()]

    if len(sentences) <= 1:
        return sentences

    # Gộp câu ngắn với câu kế tiếp
    merged = []
    buffer = ""
    for s in sentences:
        if buffer:
            buffer = buffer + " " + s
            if len(buffer.split()) >= min_words:
                merged.append(buffer)
                buffer = ""
        elif len(s.split()) < min_words:
            buffer = s
        else:
            merged.append(s)

    if buffer:
        if merged:
            merged[-1] = merged[-1] + " " + buffer
        else:
            merged.append(buffer)

    return merged


def _get_sentence_prosody(sentence: str, index: int, total: int, base_rate: int, base_pitch: int) -> dict:
    """
    Gán micro-prosody cho từng câu dựa trên dấu câu + vị trí.
    Trả về rate/pitch riêng cho câu đó.
    """
    word_count = len(sentence.split())
    rate_delta = 0
    pitch_delta = 0

    # Câu mở đầu cảnh → hào hứng hơn
    if index == 0:
        rate_delta += 5
        pitch_delta += 2

    # Phân tích dấu câu cuối
    stripped = sentence.rstrip()
    if stripped.endswith("..."):
        rate_delta -= 8
        pitch_delta -= 2
    elif stripped.endswith("?"):
        pitch_delta += 4
    elif stripped.endswith("!"):
        rate_delta += 5
        pitch_delta += 3
    elif word_count > 15:
        rate_delta -= 3

    return {
        "rate": f"{base_rate + rate_delta:+d}%",
        "pitch": f"{base_pitch + pitch_delta:+d}Hz",
    }


def _parse_rate_pitch(rate: str, pitch: str) -> tuple[int, int]:
    """Parse '+5%' → 5, '+0Hz' → 0."""
    rate_match = re.match(r'([+-]?\d+)%', rate)
    base_rate = int(rate_match.group(1)) if rate_match else 0
    pitch_match = re.match(r'([+-]?\d+)Hz', pitch)
    base_pitch = int(pitch_match.group(1)) if pitch_match else 0
    return base_rate, base_pitch


async def _synth_one_sentence(text: str, voice: str, rate: str, pitch: str) -> tuple[bytes, list]:
    """
    Sinh giọng nói cho 1 câu. Trả về (audio_bytes, word_boundaries).
    Raise exception nếu thất bại.
    """
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    audio_data = bytearray()
    word_boundaries = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data.extend(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            word_boundaries.append({
                "offset": chunk["offset"] / 10000000.0,
                "duration": chunk["duration"] / 10000000.0,
                "text": chunk["text"]
            })
    return bytes(audio_data), word_boundaries


def _concat_audio_files(files: list[str], output_path: str) -> bool:
    """
    Ghép nhiều file MP3 thành 1 bằng ffmpeg concat demuxer (-c copy).
    An toàn hơn nối byte thô: tránh lệch timing / tiếng "pop" ở điểm nối câu.
    Fallback nối byte nếu ffmpeg không khả dụng.
    """
    if not files:
        return False
    if len(files) == 1:
        import shutil
        shutil.copy(files[0], output_path)
        return True

    import tempfile
    import subprocess
    list_path = None
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as lf:
            list_path = lf.name
            for f in files:
                safe = f.replace("\\", "/").replace("'", "'\\''")
                lf.write(f"file '{safe}'\n")
        cmd = [ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", output_path]
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        return True
    except Exception as e:
        print(f"[Prosody] ffmpeg concat lỗi ({e}). Fallback nối byte thô.")
        try:
            with open(output_path, "wb") as out:
                for f in files:
                    with open(f, "rb") as inp:
                        out.write(inp.read())
            return True
        except Exception as e2:
            print(f"[Prosody] Nối byte cũng lỗi: {e2}")
            return False
    finally:
        if list_path and os.path.exists(list_path):
            try:
                os.remove(list_path)
            except OSError:
                pass


async def _synthesize_with_prosody(
    text: str, output_path: str, voice: str, rate: str, pitch: str
) -> tuple[float, list]:
    """
    V3.1 Core: Tách câu → sinh giọng nói từng câu với rate/pitch riêng → ghép nối.
    Nếu câu nào lỗi → gộp vào câu kế tiếp. Nếu toàn bộ lỗi → fallback plain text.
    Các đoạn được ghi ra file tạm rồi ghép bằng ffmpeg (không nối byte thô).
    """
    import tempfile

    sentences = _split_and_merge_sentences(text)

    # Nếu chỉ 1 câu hoặc text quá ngắn → dùng plain text
    if len(sentences) <= 1:
        return await _synthesize_plain(text, output_path, voice, rate, pitch)

    base_rate, base_pitch = _parse_rate_pitch(rate, pitch)
    total = len(sentences)

    chunk_files: list[str] = []
    all_wbs = []
    cumulative_offset = 0.0
    failed_buffer = ""  # Câu thất bại sẽ được gộp vào đây

    def _write_chunk(audio_bytes: bytes) -> str:
        fd, tmp = tempfile.mkstemp(suffix=".mp3")
        with os.fdopen(fd, "wb") as f:
            f.write(audio_bytes)
        return tmp

    try:
        for i in range(total):
            sentence = sentences[i]

            # Nếu có câu thất bại trước đó, gộp vào câu hiện tại
            if failed_buffer:
                sentence = failed_buffer + " " + sentence
                failed_buffer = ""

            prosody = _get_sentence_prosody(sentence, i, total, base_rate, base_pitch)

            try:
                audio_bytes, wbs = await _synth_one_sentence(
                    sentence, voice, prosody["rate"], prosody["pitch"]
                )

                # Điều chỉnh offset của word boundaries
                for wb in wbs:
                    wb["offset"] += cumulative_offset
                    all_wbs.append(wb)

                tmp = _write_chunk(audio_bytes)
                chunk_files.append(tmp)

                # Đo duration của chunk này
                try:
                    chunk_dur = MP3(tmp).info.length
                except Exception:
                    chunk_dur = len(audio_bytes) / 16000.0  # ước lượng

                cumulative_offset += chunk_dur

                # Delay nhỏ giữa các API call (tránh rate limit)
                if i < total - 1:
                    await asyncio.sleep(0.3)

            except Exception as e:
                print(f"Prosody Engine: Sentence {i} failed ({e}), buffering for merge...")
                failed_buffer = sentence
                continue

        # Nếu câu cuối cùng cũng fail → fallback plain text cho phần còn lại
        if failed_buffer:
            print(f"Prosody Engine: Remaining buffer '{failed_buffer[:30]}...' — falling back to plain text append")
            try:
                fb_audio, fb_wbs = await _synth_one_sentence(failed_buffer, voice, rate, pitch)
                for wb in fb_wbs:
                    wb["offset"] += cumulative_offset
                    all_wbs.append(wb)
                chunk_files.append(_write_chunk(fb_audio))
            except Exception:
                print("Prosody Engine: Final buffer also failed, skipping.")

        if not chunk_files:
            # Toàn bộ thất bại → fallback plain text đầy đủ
            print("Prosody Engine: All sentences failed. Full fallback to plain text.")
            return await _synthesize_plain(text, output_path, voice, rate, pitch)

        if not _concat_audio_files(chunk_files, output_path):
            return await _synthesize_plain(text, output_path, voice, rate, pitch)
    finally:
        for f in chunk_files:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except OSError:
                    pass

    try:
        audio = MP3(output_path)
        duration = audio.info.length
    except Exception:
        duration = cumulative_offset

    return duration, all_wbs


async def _synthesize_plain(
    text: str, output_path: str, voice: str, rate: str, pitch: str
) -> tuple[float, list]:
    """Synthesize toàn bộ text bằng 1 lần gọi plain text (phương pháp cũ)."""
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    word_boundaries = []
    audio_data = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data.extend(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            word_boundaries.append({
                # Bù trừ độ trễ padding của MP3 encoder khi decode bằng FFmpeg (khoảng 50ms)
                "offset": (chunk["offset"] / 10000000.0) + 0.05,
                "duration": chunk["duration"] / 10000000.0,
                "text": chunk["text"]
            })

    temp_path = output_path + ".tmp"
    with open(temp_path, "wb") as f:
        f.write(audio_data)

    try:
        from moviepy.audio.io.AudioFileClip import AudioFileClip
        clip = AudioFileClip(temp_path)
        duration_seconds = clip.duration
        clip.close()
    except Exception:
        audio = MP3(temp_path)
        duration_seconds = audio.info.length

    import shutil
    shutil.move(temp_path, output_path)

    return duration_seconds, word_boundaries


# ══════════════════════════════════════════════════════════════════════
# OmniVoice Engine (V3.2)
# ══════════════════════════════════════════════════════════════════════

_omnivoice_model = None

def _get_omnivoice_model():
    global _omnivoice_model
    if _omnivoice_model is None:
        import sys
        # Đường dẫn cài đặt OmniVoice có thể override qua env OMNIVOICE_PATH (không hard-code máy).
        omnivoice_path = os.getenv("OMNIVOICE_PATH", r"C:\dev\OmniVoice")
        if omnivoice_path not in sys.path:
            sys.path.append(omnivoice_path)
        try:
            from omnivoice import OmniVoice
            import torch
            device = "cuda:0" if torch.cuda.is_available() else "cpu"
            print(f"[OmniVoice] Loading model on {device}... This may take a while.")
            _omnivoice_model = OmniVoice.from_pretrained(
                "k2-fsa/OmniVoice",
                device_map=device,
                dtype=torch.float16 if torch.cuda.is_available() else torch.float32
            )
            print("[OmniVoice] Model loaded successfully.")
        except Exception as e:
            print(f"[OmniVoice] Failed to load model: {e}")
            raise e
    return _omnivoice_model

async def _synthesize_gtts_fallback(text: str, output_path: str) -> tuple[float, list]:
    """Fallback 3: gTTS (Google TTS)"""
    try:
        from gtts import gTTS
        from mutagen.mp3 import MP3
        tts = gTTS(text, lang='vi')
        temp_path = output_path + ".gtts.tmp"
        tts.save(temp_path)
        audio = MP3(temp_path)
        duration = audio.info.length
        import shutil
        shutil.move(temp_path, output_path)
        wbs = _estimate_word_boundaries(text, duration)
        return max(1.0, duration), wbs
    except Exception as e:
        print(f"[gTTS Fallback] Error: {e}. Using Offline Windows SAPI5 Fallback.")
        return await _synthesize_offline_fallback(text, output_path)

def _generate_silence_audio(output_path: str, duration_sec: float = 3.0):
    """Tạo tệp audio im lặng chuẩn 24kHz phòng khi mạng bị ngắt hoàn toàn."""
    import soundfile as sf
    import numpy as np
    num_samples = int(24000 * duration_sec)
    silence = np.zeros(num_samples, dtype=np.float32)
    sf.write(output_path, silence, 24000)

async def _synthesize_offline_fallback(text: str, output_path: str) -> tuple[float, list]:
    """Fallback 4: PyTTSx3 (Windows SAPI5 Offline TTS - KHÔNG CẦN INTERNET)"""
    def _run_pyttsx3():
        import pyttsx3
        engine = pyttsx3.init()
        engine.save_to_file(text, output_path)
        engine.runAndWait()
        
    try:
        await asyncio.to_thread(_run_pyttsx3)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            from moviepy.audio.io.AudioFileClip import AudioFileClip
            clip = AudioFileClip(output_path)
            dur = clip.duration
            clip.close()
            wbs = _estimate_word_boundaries(text, dur)
            return max(1.0, dur), wbs
    except Exception as e:
        print(f"[Offline TTS Fallback] Error: {e}")

    # Fallback cuối cùng: Sinh tệp âm thanh im lặng (Silence) 3.0s để không bao giờ làm chết pipeline
    _generate_silence_audio(output_path, duration_sec=3.0)
    return 3.0, _estimate_word_boundaries(text, 3.0)

# ══════════════════════════════════════════════════════════════════════
# OmniVoice Prosody Helpers (V3.3)
# ══════════════════════════════════════════════════════════════════════

def _get_omnivoice_sentence_instruct(sentence: str, index: int, total: int, base_instruct: str) -> str:
    """
    Gán micro-prosody cho OmniVoice dựa trên ngữ cảnh câu.
    OmniVoice không dùng rate/pitch như Edge-TTS mà dùng instruct text.
    """
    stripped = sentence.rstrip()
    
    # Câu mở đầu cảnh → thêm "energetic" nếu chưa có whisper
    if index == 0 and "whisper" not in base_instruct.lower():
        return base_instruct  # Giữ nguyên instruct gốc cho câu đầu (đã tự nhiên hào hứng)
    
    # Câu kết thúc bằng "..." → giọng chậm lại, nhẹ nhàng
    if stripped.endswith("..."):
        if "whisper" not in base_instruct.lower():
            return base_instruct.rstrip(", ") + ", low pitch"
        return base_instruct
    
    # Câu cảm thán "!" → giữ nguyên hoặc tăng nhẹ
    if stripped.endswith("!"):
        return base_instruct
    
    # Câu hỏi "?" → giữ nguyên
    if stripped.endswith("?"):
        return base_instruct
    
    # Câu thường → giữ nguyên
    return base_instruct


def _forced_align_word_boundaries(wav_path: str, text: str) -> list:
    """
    Sử dụng Forced Alignment (stable-ts/whisper) để trích xuất word boundaries
    chính xác từ file WAV. Fallback về _estimate nếu thư viện chưa cài.
    """
    try:
        import stable_whisper
        model = stable_whisper.load_model("base")
        result = model.align(wav_path, text, language="vi")
        wbs = []
        for segment in result.segments:
            for word in segment.words:
                wbs.append({
                    "offset": word.start,
                    "duration": word.end - word.start,
                    "text": word.word.strip()
                })
        if wbs:
            print(f"[OmniVoice] Forced Alignment thành công: {len(wbs)} words")
            return wbs
    except ImportError:
        print("[OmniVoice] stable-whisper chưa cài. Dùng nội suy word boundaries.")
    except Exception as e:
        print(f"[OmniVoice] Forced Alignment lỗi ({e}). Dùng nội suy word boundaries.")
    
    # Fallback: nội suy
    import soundfile as sf
    try:
        info = sf.info(wav_path)
        duration = info.duration
    except Exception:
        duration = 3.0
    return _estimate_word_boundaries(text, duration)


async def _synthesize_omnivoice(text: str, output_path: str, instruct: str = "male, young adult, moderate pitch", rate: str = "+0%", emotion: str = "", warning_callback=None) -> tuple[float, list]:
    """
    V3.3: Tạo giọng đọc từ OmniVoice với Prosody Engine + Forced Alignment.
    - Emotion Mapping: Dịch cảm xúc từ Gemini sang Instruct Token.
    - Time-Stretching: Xử lý rate modifier bằng FFmpeg atempo.
    """
    import soundfile as sf
    import asyncio
    import os
    import numpy as np
    import re
    
    clean_text = _normalize_text(text)
    if not clean_text:
        clean_text = "..."

    OMNIVOICE_MAPPING = {
        "omnivoice_female_storyteller_vi": "female, young adult, energetic, moderate pitch",
        "omnivoice_male_podcast_vi": "male, young adult, moderate pitch",
        "omnivoice_male_elderly_vi": "male, elderly, low pitch",
        "omnivoice_male_middle_aged_low_vi": "male, middle-aged, low pitch",
        "omnivoice_female_whisper_vi": "female, young adult, whisper",
        "omnivoice_female_child_vi": "female, child, high pitch",
    }
    
    mapped_instruct = OMNIVOICE_MAPPING.get(instruct, instruct)
    
    # --- Emotion Mapping ---
    if emotion == "excited":
        mapped_instruct = mapped_instruct.replace("moderate pitch", "").replace("low pitch", "")
        mapped_instruct += ", high pitch"
    elif emotion in ["dramatic", "suspense"]:
        mapped_instruct = mapped_instruct.replace("moderate pitch", "").replace("high pitch", "")
        mapped_instruct += ", whisper, low pitch"
    elif emotion == "calm":
        mapped_instruct = mapped_instruct.replace("high pitch", "").replace("low pitch", "")
        mapped_instruct += ", moderate pitch"
    
    # Whitelist các từ khóa hợp lệ được chấp nhận bởi mô hình OmniVoice
    VALID_OMNIVOICE_TOKENS = {
        "american accent", "australian accent", "british accent", "canadian accent", "child", "chinese accent",
        "elderly", "female", "high pitch", "indian accent", "japanese accent", "korean accent", "low pitch",
        "male", "middle-aged", "moderate pitch", "portuguese accent", "russian accent", "teenager",
        "very high pitch", "very low pitch", "whisper", "young adult"
    }
    raw_tokens = [t.strip() for t in mapped_instruct.split(",")]
    clean_tokens = [t for t in raw_tokens if t.lower() in VALID_OMNIVOICE_TOKENS]
    if not clean_tokens:
        clean_tokens = ["male", "young adult", "moderate pitch"]
    mapped_instruct = ", ".join(clean_tokens)

    def _run_omnivoice_with_prosody():
        import torch
        # Đặt cố định seed để OmniVoice giữ đúng 1 chất giọng (timbre) xuyên suốt tất cả cảnh
        torch.manual_seed(42)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(42)

        model = _get_omnivoice_model()
        
        # Prosody V3.3: Tách câu bằng engine đã có sẵn thay vì regex thô
        sentences = _split_and_merge_sentences(clean_text, min_words=5)
        if not sentences:
            sentences = [clean_text]
        total_sentences = len(sentences)
            
        # Đường dẫn cache giọng mẫu (Reference Audio) để Cloning
        preview_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "voices_preview")
        os.makedirs(preview_dir, exist_ok=True)
        ref_wav_path = os.path.join(preview_dir, f"{instruct}_ref.wav")
        ref_text = "Chào bạn, đây là giọng đọc tham khảo để đồng bộ video."
        
        # Nếu chưa có giọng mẫu, tạo 1 bản zero-shot và lưu lại
        if not os.path.exists(ref_wav_path) or os.path.getsize(ref_wav_path) < 1000:
            print(f"[OmniVoice] Tạo giọng mẫu Zero-shot cho {instruct}...")
            ref_audio_arr = model.generate(text=ref_text, instruct=mapped_instruct)
            sf.write(ref_wav_path, ref_audio_arr[0], 24000)
            
        audio_chunks = []
        for idx, sentence in enumerate(sentences):
            # Prosody: điều chỉnh instruct theo ngữ cảnh câu
            sentence_instruct = _get_omnivoice_sentence_instruct(
                sentence, idx, total_sentences, mapped_instruct
            )
            
            # Chunk nhỏ hơn cho câu dài (90 ký tự thay vì 180 nếu > 15 từ)
            max_chunk = 90 if len(sentence.split()) > 15 else 180
            sub_chunks = [sentence[i:i+max_chunk] for i in range(0, len(sentence), max_chunk)]
            
            for sub in sub_chunks:
                if not sub.strip():
                    continue
                # Dùng Voice Cloning thay vì Zero-shot để đảm bảo 100% đồng nhất giọng
                arr = model.generate(text=sub, ref_audio=ref_wav_path, ref_text=ref_text)
                audio_chunks.append(arr[0])
                
        if len(audio_chunks) == 1:
            final_audio = audio_chunks[0]
        else:
            final_audio = np.concatenate(audio_chunks, axis=0)
            
        return final_audio

    try:
        audio = await asyncio.to_thread(_run_omnivoice_with_prosody)
        wav_path = output_path.replace(".mp3", ".wav") if output_path.endswith(".mp3") else output_path
        sf.write(wav_path, audio, 24000)
        
        # --- Time-Stretching (Rate Modification) ---
        rate_match = re.match(r'([+-]?\d+)%', rate)
        if rate_match:
            percent = int(rate_match.group(1))
            if percent != 0:
                atempo = max(0.5, min(2.0, 1.0 + (percent / 100.0)))
                stretched_wav_path = wav_path.replace(".wav", "_stretched.wav")
                try:
                    import subprocess
                    import imageio_ffmpeg
                    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                    cmd = [ffmpeg_exe, "-y", "-i", wav_path, "-filter:a", f"atempo={atempo}", stretched_wav_path]
                    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
                    os.replace(stretched_wav_path, wav_path)
                except Exception as stretch_err:
                    print(f"[OmniVoice] Time-stretching failed: {stretch_err}")

        # Update duration after stretching
        info = sf.info(wav_path)
        duration = info.duration

        if output_path != wav_path:
            import shutil
            shutil.copy(wav_path, output_path)
        
        # V3.3: Forced Alignment cho word boundaries chính xác
        wbs = await asyncio.to_thread(_forced_align_word_boundaries, wav_path, clean_text)
        
        return max(1.0, duration), wbs
    except Exception as e:
        fallback_msg = f"⚠️ OmniVoice không khả dụng ({type(e).__name__}). Tự động dùng giọng Edge-TTS thay thế."
        print(f"[OmniVoice] {fallback_msg}")
        # Broadcast cảnh báo cho user qua WebSocket (nếu có callback)
        if warning_callback:
            try:
                await warning_callback(fallback_msg)
            except Exception:
                pass
        fallback_voice = "vi-VN-NamMinhNeural" if "male" in instruct.lower() else "vi-VN-HoaiMyNeural"
        try:
            return await _synthesize_plain(clean_text, output_path, fallback_voice, "+0%", "+0Hz")
        except Exception as fallback_e:
            print(f"[OmniVoice Fallback] Edge-TTS failed: {fallback_e}. Chuyển sang gTTS.")
            return await _synthesize_gtts_fallback(clean_text, output_path)

# ══════════════════════════════════════════════════════════════════════
# Main synthesize function
# ══════════════════════════════════════════════════════════════════════

async def synthesize_speech(
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
    pitch: str = "+0Hz",
    mode: str = "storyteller",
    emotion: str = "",
    warning_callback=None,
    use_breathing: bool = False,
) -> tuple[float, list]:
    """
    V3.1: Chuyển văn bản → giọng nói với Sentence-Level Prosody + Multilayer Fallback.
    Hỗ trợ chèn tiếng lấy hơi (Breathing) để tạo cảm giác tự nhiên.
    """
    dur, wbs = await _synthesize_speech_internal(text, output_path, voice, rate, pitch, mode, emotion, warning_callback)
    
    if use_breathing and os.path.exists(output_path):
        breath_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "sfx", "breath.wav")
        if os.path.exists(breath_path):
            import tempfile
            from moviepy.audio.io.AudioFileClip import AudioFileClip
            from moviepy.audio.AudioClip import concatenate_audioclips
            
            try:
                breath_clip = AudioFileClip(breath_path)
                speech_clip = AudioFileClip(output_path)
                
                final_clip = concatenate_audioclips([breath_clip, speech_clip])
                
                # Cần ghi đè lại output_path
                _fd, temp_out = tempfile.mkstemp(suffix=".wav")
                os.close(_fd)
                # moviepy 2.1.2 không hỗ trợ `await final_clip.write_audiofile_async`, ta chạy đồng bộ trên thread
                def _write():
                    final_clip.write_audiofile(temp_out, fps=24000, logger=None)
                    breath_clip.close()
                    speech_clip.close()
                    final_clip.close()
                await asyncio.to_thread(_write)
                
                import shutil
                shutil.move(temp_out, output_path)
                
                # Shift word boundaries
                breath_dur = breath_clip.duration
                dur += breath_dur
                for wb in wbs:
                    wb["offset"] += breath_dur
                    
            except Exception as e:
                print(f"[Breathing] Error applying breathing effect: {e}")
                
    return dur, wbs

async def _synthesize_speech_internal(
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
    pitch: str = "+0Hz",
    mode: str = "storyteller",
    emotion: str = "",
    warning_callback=None,
) -> tuple[float, list]:
    # ── Xử lý OmniVoice ──
    if voice.startswith("omnivoice_"):
        return await _synthesize_omnivoice(text, output_path, voice, rate=rate, emotion=emotion, warning_callback=warning_callback)

    if voice == "vi-VN-NamMinhNeural_deep":
        voice = "vi-VN-NamMinhNeural"
        pitch = "-20Hz"

    if voice not in [v["id"] for v in VIETNAMESE_VOICES] and not voice.startswith("minion"):
        print(f"Voice {voice} không tồn tại. Fallback về vi-VN-HoaiMyNeural.")
        voice = "vi-VN-HoaiMyNeural"

    # Chuẩn hóa text
    text = _normalize_text(text)

    # Xử lý giọng ảo (Minion) — bypass prosody engine
    use_prosody = True
    if voice == "minion":
        voice = "vi-VN-HoaiMyNeural"
        rate = "+30%"
        pitch = "+400Hz"
        use_prosody = False
    elif voice == "minion_pro":
        voice = "vi-VN-HoaiMyNeural"
        rate = "+45%"
        pitch = f"+{random.randint(350, 450)}Hz"
        text = _minion_pro_transform(text)
        use_prosody = False
    elif emotion:
        rate, pitch = _apply_emotion_to_rate_pitch(rate, pitch, emotion)

    # Retry logic Edge-TTS (dùng trực tiếp Neural TTS full-context để giữ trọn vẹn nhịp thở và diễn cảm tự nhiên)
    import os
    last_error = None
    for attempt in range(3):
        try:
            # Sentence-Level Prosody Engine V3.1: gán micro-prosody (rate/pitch) riêng cho
            # từng câu theo dấu câu + vị trí. Giọng ảo (minion) bỏ qua để giữ hiệu ứng gốc.
            # _synthesize_with_prosody tự fallback về plain khi text 1 câu hoặc câu lỗi.
            if use_prosody:
                return await _synthesize_with_prosody(text, output_path, voice, rate, pitch)
            return await _synthesize_plain(text, output_path, voice, rate, pitch)
        except Exception as e:
            last_error = e
            print(f"Edge-TTS error (attempt {attempt+1}/3): {e}")
            if os.path.exists(output_path):
                os.remove(output_path)
            tmp = output_path + ".tmp"
            if os.path.exists(tmp):
                os.remove(tmp)
            await asyncio.sleep(2)

    # Fallback gTTS & Offline SAPI5
    print(f"Edge-TTS failed completely: {last_error}. Chuyển sang gTTS Fallback.")
    return await _synthesize_gtts_fallback(text, output_path)


def get_available_voices():
    return VIETNAMESE_VOICES
