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
import json
import os
import shutil
import subprocess
import tempfile
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

# ── Custom Voice Cloning Registry (Phase 3) ──────────────────────────
from config import CUSTOM_VOICES_FILE, SFX_DIR, VOICES_PREVIEW_DIR  # noqa: F401


def _load_custom_voices() -> list:
    if not os.path.exists(CUSTOM_VOICES_FILE):
        return []
    try:
        with open(CUSTOM_VOICES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_custom_voices(voices: list):
    with open(CUSTOM_VOICES_FILE, "w", encoding="utf-8") as f:
        json.dump(voices, f, ensure_ascii=False, indent=2)


def get_custom_voice(voice_id: str) -> dict | None:
    for v in _load_custom_voices():
        if v.get("id") == voice_id:
            return v
    return None


def register_custom_voice(voice_id: str, name: str, ref_text: str) -> dict:
    voices = _load_custom_voices()
    entry = {"id": voice_id, "name": name, "ref_text": ref_text}
    voices = [v for v in voices if v.get("id") != voice_id]
    voices.append(entry)
    _save_custom_voices(voices)
    return entry


def remove_custom_voice(voice_id: str) -> bool:
    voices = _load_custom_voices()
    remaining = [v for v in voices if v.get("id") != voice_id]
    if len(remaining) == len(voices):
        return False
    _save_custom_voices(remaining)
    for suffix in (f"{voice_id}_ref.wav", f"{voice_id}.mp3"):
        p = os.path.join(VOICES_PREVIEW_DIR, suffix)
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass
    return True

import random
import re
import logging

logger = logging.getLogger(__name__)


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
    # edge-tts >= 7.x mặc định boundary="SentenceBoundary" — phải chỉ định WordBoundary
    # tường minh, nếu không sẽ KHÔNG có word boundaries → phụ đề karaoke mất hiệu ứng nhảy chữ.
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
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
        shutil.copy(files[0], output_path)
        return True

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
        logger.warning(f"[Prosody] ffmpeg concat lỗi ({e}). Fallback nối byte thô.")
        try:
            with open(output_path, "wb") as out:
                for f in files:
                    with open(f, "rb") as inp:
                        out.write(inp.read())
            return True
        except Exception as e2:
            logger.error(f"[Prosody] Nối byte cũng lỗi: {e2}")
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
    NÂNG CẤP V3.2 Engine (Full-Context Seamless Prosody):
    Gửi toàn bộ văn bản cảnh trong 1 lần gọi duy nhất đến Microsoft Neural TTS.
    Loại bỏ hoàn toàn việc ngắt câu ghép nối file MP3 thủ công (vốn gây ra khoảng lặng khựng ~100ms giữa các câu).
    Giữ trọn vẹn nhịp thở tự nhiên, điệu đọc truyền cảm và độ khớp 100% của phụ đề Karaoke.
    """
    return await _synthesize_plain(text, output_path, voice, rate, pitch)


async def _synthesize_plain(
    text: str, output_path: str, voice: str, rate: str, pitch: str
) -> tuple[float, list]:
    """Synthesize toàn bộ text bằng 1 lần gọi plain text (phương pháp cũ)."""
    # boundary="WordBoundary" bắt buộc từ edge-tts 7.x (mặc định là SentenceBoundary)
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
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

    shutil.move(temp_path, output_path)

    return duration_seconds, word_boundaries


# ══════════════════════════════════════════════════════════════════════
# V4.0: Single-Pass Narration — đọc liền mạch TOÀN kịch bản trong 1 lần gọi
# ══════════════════════════════════════════════════════════════════════

class NarrationSplitError(RuntimeError):
    """Không map được word boundaries về từng cảnh → caller phải fallback per-scene."""


def _prepare_scene_texts(scene_texts: list[str]) -> tuple[str, list[tuple[int, int]]]:
    """
    Chuẩn hoá + nối text tất cả các cảnh thành MỘT chuỗi đọc liền.
    Trả về (chuỗi đầy đủ, danh sách (char_start, char_end) của từng cảnh).

    Mỗi cảnh được đảm bảo kết thúc bằng dấu câu để Microsoft Neural TTS tự xuống
    giọng và lấy hơi đúng chỗ — đây chính là thứ tạo ra nhịp tự nhiên mà cách gọi
    từng cảnh riêng lẻ không bao giờ có (mỗi lần gọi là một lần "vào giọng" mới).
    """
    parts: list[str] = []
    ranges: list[tuple[int, int]] = []
    cursor = 0
    for raw in scene_texts:
        t = _normalize_text(raw or "").strip()
        if t and t[-1] not in ".!?…:;,":
            t += "."
        if not t:
            t = "."
        start = cursor
        parts.append(t)
        cursor += len(t)
        ranges.append((start, cursor))
        cursor += 1  # khoảng trắng nối giữa 2 cảnh
    return " ".join(parts), ranges


def split_word_boundaries_by_scene(
    word_boundaries: list, full_text: str, scene_ranges: list[tuple[int, int]]
) -> list[list]:
    """
    Chia danh sách word_boundaries TOÀN CỤC về từng cảnh.

    Không đếm từ theo `.split()` vì cách tách từ của Edge-TTS không trùng khớp
    (dấu câu, số, từ ghép) — lệch 1 từ là lệch dồn toàn bộ các cảnh sau. Thay vào đó
    dò vị trí ký tự thật của từng từ trong chuỗi gốc rồi quy ra cảnh theo khoảng ký tự.
    """
    lower = full_text.lower()
    buckets: list[list] = [[] for _ in scene_ranges]
    cursor = 0

    def _scene_of(pos: int) -> int:
        for idx, (s, e) in enumerate(scene_ranges):
            if s <= pos < e:
                return idx
        # Rơi vào khoảng trắng nối giữa 2 cảnh → tính cho cảnh gần nhất phía trước.
        for idx in range(len(scene_ranges) - 1, -1, -1):
            if scene_ranges[idx][0] <= pos:
                return idx
        return 0

    for wb in word_boundaries:
        w = (wb.get("text") or "").strip()
        if not w:
            continue
        # Chỉ dò trong cửa sổ ngắn phía trước con trỏ: nếu tìm toàn chuỗi, một từ lặp lại
        # ở cuối bài có thể kéo con trỏ nhảy vọt và phá toàn bộ ánh xạ.
        window_end = min(len(lower), cursor + len(w) + 40)
        idx = lower.find(w.lower(), cursor, window_end)
        if idx == -1:
            idx = cursor
            cursor = min(len(lower), cursor + len(w) + 1)
        else:
            cursor = idx + len(w)
        buckets[_scene_of(idx)].append(wb)

    return buckets


async def synthesize_script_single_pass(
    scene_texts: list[str],
    output_path: str,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
    pitch: str = "+0Hz",
) -> tuple[float, list[list], float]:
    """
    V4.0 — Gọi Edge-TTS ĐÚNG MỘT LẦN cho toàn bộ kịch bản.

    Trả về (tổng thời lượng, word_boundaries đã chia theo cảnh (mốc TUYỆT ĐỐI), tổng dur).

    ĐÁNH ĐỔI CÓ CHỦ Ý: chế độ này BỎ QUA `emotion` và `speech_rate_modifier` riêng của
    từng cảnh, vì cả bài chỉ có một lần gọi nên không thể đổi rate/pitch giữa chừng.
    Đổi lại: cao độ, nhịp thở và ngữ điệu liên tục suốt video thay vì reset ở mỗi cảnh.

    Raise NarrationSplitError nếu có cảnh CÓ CHỮ nhưng không nhận được từ nào —
    dấu hiệu ánh xạ hỏng, caller phải quay về chế độ đọc từng cảnh.
    """
    from services.cache_service import cache as _tts_cache

    full_text, ranges = _prepare_scene_texts(scene_texts)

    cache_params = dict(mode="single_pass", text=full_text, voice=voice, rate=rate, pitch=pitch)
    cached = _tts_cache.get("tts_meta", **cache_params)
    if cached and _tts_cache.get_media("tts", output_path, **cache_params):
        logger.info("[Narration] Cache HIT — tái dùng bản đọc liền mạch.")
        return cached["duration"], cached["scene_wbs"], cached["duration"]

    if voice.startswith("omnivoice_") or voice.startswith("minion"):
        raise NarrationSplitError(
            f"Giọng '{voice}' không hỗ trợ đọc liền mạch (cần word boundaries của Edge-TTS)."
        )

    logger.info(f"[Narration] Đọc liền mạch {len(scene_texts)} cảnh trong 1 lần gọi ({len(full_text)} ký tự)...")
    duration, wbs = await _synthesize_plain(full_text, output_path, voice, rate, pitch)

    scene_wbs = split_word_boundaries_by_scene(wbs, full_text, ranges)

    for i, (bucket, raw) in enumerate(zip(scene_wbs, scene_texts)):
        if not bucket and (raw or "").strip():
            raise NarrationSplitError(f"Cảnh {i+1} có lời thoại nhưng không nhận được từ nào.")

    try:
        _tts_cache.set_media("tts", output_path, **cache_params)
        _tts_cache.set("tts_meta", {"duration": duration, "scene_wbs": scene_wbs}, **cache_params)
    except Exception as e:
        logger.warning(f"[Narration] Lưu cache lỗi (không nghiêm trọng): {e}")

    return duration, scene_wbs, duration


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
            logger.info(f"[OmniVoice] Loading model on {device}... This may take a while.")
            _omnivoice_model = OmniVoice.from_pretrained(
                "k2-fsa/OmniVoice",
                device_map=device,
                dtype=torch.float16 if torch.cuda.is_available() else torch.float32
            )
            logger.info("[OmniVoice] Model loaded successfully.")
        except Exception as e:
            logger.error(f"[OmniVoice] Failed to load model: {e}")
            raise e
    return _omnivoice_model

async def _synthesize_gtts_fallback(text: str, output_path: str) -> tuple[float, list]:
    """Fallback 3: gTTS (Google TTS)"""
    try:
        from gtts import gTTS
        tts = gTTS(text, lang='vi')
        temp_path = output_path + ".gtts.tmp"
        tts.save(temp_path)
        audio = MP3(temp_path)
        duration = audio.info.length
        shutil.move(temp_path, output_path)
        wbs = _estimate_word_boundaries(text, duration)
        return max(1.0, duration), wbs
    except Exception as e:
        logger.warning(f"[gTTS Fallback] Error: {e}. Using Offline Windows SAPI5 Fallback.")
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
        logger.error(f"[Offline TTS Fallback] Error: {e}")

    # Fallback cuối cùng: Sinh tệp âm thanh im lặng (Silence) 3.0s để không bao giờ làm chết pipeline
    _generate_silence_audio(output_path, duration_sec=3.0)
    return 3.0, _estimate_word_boundaries(text, 3.0)

# ══════════════════════════════════════════════════════════════════════
# OmniVoice Prosody Helpers (V3.3)
# ══════════════════════════════════════════════════════════════════════

OMNIVOICE_SR = 24000
# Trần ký tự mỗi mẩu gửi cho OmniVoice. 200 chứ không phải 90: mô hình xử lý tốt câu
# dài, cắt vụn chỉ làm mất ngữ điệu vắt qua ranh giới mẩu.
_TTS_MAX_CHUNK_CHARS = 200
# Ngưỡng coi là "im lặng" khi gọt hai đầu mỗi mẩu.
_TTS_TRIM_TOP_DB = 40
# Khoảng lặng TRẢ LẠI sau khi gọt, theo dấu câu đã cắt ra (giây). Gọt xong mà nối
# thẳng thì các vế dính sát nhau, nghe hụt hơi và vội — còn khó chịu hơn cả tiếng
# khựng ban đầu. Mục tiêu là thay khoảng lặng NGẪU NHIÊN của model bằng khoảng lặng
# CÓ KIỂM SOÁT, chứ không phải xoá sạch mọi nhịp nghỉ.
_TTS_PAUSE_AFTER = {",": 0.12, ";": 0.18, ":": 0.18}
_TTS_SENTENCE_PAUSE = 0.25   # giữa hai câu
_TTS_ELLIPSIS_PAUSE = 0.35   # mẩu kết thúc bằng "..." — nhịp lặng cố ý, xem prompt Gemini


def _split_sentence_for_tts(sentence: str, max_chars: int = _TTS_MAX_CHUNK_CHARS):
    """
    Cắt câu dài thành các mẩu cho OmniVoice, ưu tiên RANH GIỚI NGỮ NGHĨA (dấu , ; :).
    Trả về [(văn bản, dấu kết thúc)] — dấu kết thúc dùng để tính khoảng lặng chèn lại.

    LỖI CŨ: cắt cứng theo 90 ký tự bất kể nội dung. Ranh giới rơi vào giữa vế câu
    ("...tôi đã đi" | "tới đó và thấy...") nên ngữ điệu bị bẻ gãy đúng chỗ không có
    dấu câu nào — tai nghe ra ngay là một cú vấp.

    Câu KHÔNG có dấu ngắt nào mà vẫn quá dài thì mới cắt theo ranh giới từ (lưới an
    toàn cũ, giữ nguyên: không bao giờ được đứt giữa một từ).
    """
    s = (sentence or "").strip()
    if not s:
        return []
    if len(s) <= max_chars:
        return [(s, "")]

    # Tách theo dấu ngắt vế, GIỮ dấu lại để biết cần nghỉ bao lâu
    clauses = []
    for part in re.findall(r"[^,;:]+[,;:]?", s):
        part = part.strip()
        if not part:
            continue
        if part[-1] in ",;:":
            clauses.append((part[:-1].strip(), part[-1]))
        else:
            clauses.append((part, ""))

    # Gộp các vế ngắn cho tới sát trần ký tự (đừng cắt vụn hơn mức cần thiết)
    merged, buf, buf_trail = [], "", ""
    for text, trail in clauses:
        cand = f"{buf}{buf_trail} {text}".strip() if buf else text
        if buf and len(cand) > max_chars:
            merged.append((buf, buf_trail))
            buf, buf_trail = text, trail
        else:
            buf, buf_trail = cand, trail
    if buf:
        merged.append((buf, buf_trail))

    # Vế đơn vẫn quá dài → lưới an toàn: cắt theo từ
    out = []
    for text, trail in merged:
        if len(text) <= max_chars:
            out.append((text, trail))
            continue
        cur = ""
        for word in text.split():
            if cur and len(cur) + 1 + len(word) > max_chars:
                out.append((cur, ""))
                cur = word
            else:
                cur = f"{cur} {word}".strip()
        if cur:
            out.append((cur, trail))
    return out


def _trim_tts_silence(seg):
    """
    Gọt khoảng lặng hai đầu một mẩu audio. Trả lại chính `seg` nếu không gọt được
    (thiếu librosa, hoặc mẩu gần như im lặng hoàn toàn).

    KHÔNG được ném exception: hàm này nằm trong đường sinh giọng clone, lỗi ở đây sẽ
    đẩy cả job rơi về Edge-TTS và mất sạch giọng đã clone.
    """
    try:
        import librosa
    except Exception as e:      # librosa nặng (numba/llvmlite), có thể chưa cài
        logger.warning(f"[OmniVoice] Không có librosa, bỏ qua bước gọt lặng: {e}")
        return seg
    try:
        trimmed, _ = librosa.effects.trim(seg, top_db=_TTS_TRIM_TOP_DB)
        # Mẩu im gần hết → giữ bản gốc, đừng trả về mảng rỗng làm mất chữ
        if trimmed.size < int(0.02 * OMNIVOICE_SR):
            return seg
        return trimmed
    except Exception as e:
        logger.warning(f"[OmniVoice] Gọt lặng thất bại, dùng nguyên bản: {e}")
        return seg


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


# Singleton model whisper cho Forced Alignment — load 1 lần, tránh tải lại ~150MB mỗi cảnh.
_whisper_model = None


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        import stable_whisper
        logger.info("[ForcedAlign] Loading stable-whisper 'base' model (1 lần duy nhất)...")
        _whisper_model = stable_whisper.load_model("base")
    return _whisper_model


def _forced_align_word_boundaries(wav_path: str, text: str) -> list:
    """
    Sử dụng Forced Alignment (stable-ts/whisper) để trích xuất word boundaries
    chính xác từ file WAV. Fallback về _estimate nếu thư viện chưa cài.
    """
    try:
        model = _get_whisper_model()
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
            logger.info(f"[OmniVoice] Forced Alignment thành công: {len(wbs)} words")
            return wbs
    except ImportError:
        logger.warning("[OmniVoice] stable-whisper chưa cài. Dùng nội suy word boundaries.")
    except Exception as e:
        logger.warning(f"[OmniVoice] Forced Alignment lỗi ({e}). Dùng nội suy word boundaries.")
    
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
    import numpy as np
    
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

    # --- Emotion qua TEMPO thay vì đổi instruct token ---
    # LÝ DO: pipeline dùng Voice Cloning (ref_audio) nên instruct KHÔNG ảnh hưởng audio
    # sau khi ref đã tạo. Trước đây emotion còn "bake" vào file ref dùng chung → cảnh đầu
    # quyết định timbre cả video. Giờ: ref = identity thuần (không emotion), cảm xúc thể
    # hiện qua tempo delta (%) — phủ đủ 6/6 emotion Gemini sinh ra, giữ timbre ổn định.
    EMOTION_TEMPO_DELTA = {
        "hook": +4, "excited": +6, "calm": 0,
        "dramatic": -5, "suspense": -6, "closing": -3,
    }
    emotion_tempo = EMOTION_TEMPO_DELTA.get(emotion, 0)

    # Giọng clone cá nhân: lấy ref_text riêng từ registry
    custom_voice = get_custom_voice(instruct) if instruct.startswith("omnivoice_custom_") else None

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
        if custom_voice:
            cv_name = custom_voice.get("name", "").lower()
            if "nữ" in cv_name or "female" in cv_name or "gái" in cv_name:
                clean_tokens = ["female", "young adult", "moderate pitch"]
            else:
                clean_tokens = ["male", "young adult", "moderate pitch"]
        else:
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
        preview_dir = VOICES_PREVIEW_DIR
        os.makedirs(preview_dir, exist_ok=True)
        ref_wav_path = os.path.join(preview_dir, f"{instruct}_ref.wav")
        ref_text = "Chào bạn, đây là giọng đọc tham khảo để đồng bộ video."

        if custom_voice:
            # Giọng clone cá nhân: file mẫu do user upload (bắt buộc tồn tại) + transcript riêng
            ref_text = custom_voice.get("ref_text") or ref_text
            if not os.path.exists(ref_wav_path) or os.path.getsize(ref_wav_path) < 1000:
                raise RuntimeError(f"Thiếu file mẫu giọng clone: {ref_wav_path}. Hãy upload lại mẫu giọng.")
        elif not os.path.exists(ref_wav_path) or os.path.getsize(ref_wav_path) < 1000:
            # Nếu chưa có giọng mẫu, tạo 1 bản zero-shot (identity thuần, KHÔNG kèm emotion) và lưu lại
            logger.info(f"[OmniVoice] Tạo giọng mẫu Zero-shot cho {instruct}...")
            ref_audio_arr = model.generate(text=ref_text, instruct=mapped_instruct)
            sf.write(ref_wav_path, ref_audio_arr[0], 24000)
            
        audio_chunks = []
        last_sentence_idx = total_sentences - 1
        for idx, sentence in enumerate(sentences):
            # Prosody: điều chỉnh instruct theo ngữ cảnh câu
            sentence_instruct = _get_omnivoice_sentence_instruct(
                sentence, idx, total_sentences, mapped_instruct
            )

            sub_chunks = _split_sentence_for_tts(sentence)
            last_chunk_idx = len(sub_chunks) - 1

            for j, (sub, trail) in enumerate(sub_chunks):
                if not sub.strip():
                    continue
                # Dùng Voice Cloning thay vì Zero-shot để đảm bảo 100% đồng nhất giọng.
                # `instruct` BẮT BUỘC phải truyền kèm dù đã có ref_audio: thiếu nó thì
                # model mất mốc phong cách nền và trôi dần về giọng mặc định, giọng clone
                # bị lai tạp. sentence_instruct trước đây được tính ra rồi BỎ KHÔNG DÙNG.
                arr = model.generate(
                    text=sub,
                    instruct=sentence_instruct,
                    ref_audio=ref_wav_path,
                    ref_text=ref_text,
                )
                seg = np.asarray(arr[0], dtype=np.float32)
                audio_chunks.append(_trim_tts_silence(seg))

                # Chèn lại nhịp nghỉ có kiểm soát (xem _TTS_PAUSE_AFTER)
                is_very_last = (idx == last_sentence_idx) and (j == last_chunk_idx)
                if is_very_last:
                    continue
                gap = _TTS_PAUSE_AFTER.get(trail, 0.0)
                if j == last_chunk_idx:                       # hết câu
                    gap = max(gap, _TTS_SENTENCE_PAUSE)
                if sub.rstrip().endswith(("...", "…")):       # nhịp lặng cố ý
                    gap = max(gap, _TTS_ELLIPSIS_PAUSE)
                if gap > 0:
                    audio_chunks.append(np.zeros(int(gap * OMNIVOICE_SR), dtype=np.float32))

        if not audio_chunks:
            logger.warning(f"[OmniVoice] Không sinh được audio nào cho text: '{clean_text}'. Trả về im lặng 1s.")
            final_audio = np.zeros(24000, dtype=np.float32)
        elif len(audio_chunks) == 1:
            final_audio = audio_chunks[0]
        else:
            final_audio = np.concatenate(audio_chunks, axis=0)

        return final_audio

    try:
        audio = await asyncio.to_thread(_run_omnivoice_with_prosody)
        wav_path = output_path.replace(".mp3", ".wav") if output_path.endswith(".mp3") else output_path
        sf.write(wav_path, audio, 24000)
        
        # --- Time-Stretching (Rate + Emotion Tempo) ---
        rate_match = re.match(r'([+-]?\d+)%', rate)
        if rate_match or emotion_tempo:
            percent = (int(rate_match.group(1)) if rate_match else 0) + emotion_tempo
            if percent != 0:
                atempo = max(0.5, min(2.0, 1.0 + (percent / 100.0)))
                stretched_wav_path = wav_path.replace(".wav", "_stretched.wav")
                try:
                    import imageio_ffmpeg
                    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                    cmd = [ffmpeg_exe, "-y", "-i", wav_path, "-filter:a", f"atempo={atempo}", stretched_wav_path]
                    await asyncio.to_thread(subprocess.run, cmd, check=True, capture_output=True, timeout=120)
                    os.replace(stretched_wav_path, wav_path)
                except Exception as stretch_err:
                    logger.warning(f"[OmniVoice] Time-stretching failed: {stretch_err}")

        # Update duration after stretching
        info = sf.info(wav_path)
        duration = info.duration

        if output_path != wav_path:
            shutil.copy(wav_path, output_path)
        
        # V3.3: Forced Alignment cho word boundaries chính xác
        wbs = await asyncio.to_thread(_forced_align_word_boundaries, wav_path, clean_text)
        
        return max(1.0, duration), wbs
    except Exception as e:
        fallback_msg = f"⚠️ OmniVoice không khả dụng ({type(e).__name__}). Tự động dùng giọng Edge-TTS thay thế."
        logger.warning(f"[OmniVoice] {fallback_msg}")
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
            logger.warning(f"[OmniVoice Fallback] Edge-TTS failed: {fallback_e}. Chuyển sang gTTS.")
            return await _synthesize_gtts_fallback(clean_text, output_path)

# ══════════════════════════════════════════════════════════════════════
# Vi chỉnh nhịp đọc — thẻ <break time="1s"/>
# ══════════════════════════════════════════════════════════════════════
# Edge-TTS KHÔNG nhận SSML: thư viện tự bọc text vào khung SSML của nó và escape mọi
# dấu '<'. Gửi thẻ break vào thẳng thì máy đọc nguyên văn "break time bằng một giây".
# Vì thế trước đây pipeline chỉ thay thẻ bằng "..." — mà "..." chỉ tạo được khoảng
# lặng vài chục ms, không đủ để "ngưng đọng cảm xúc".
#
# Cách làm ở đây: CẮT text tại thẻ, đọc từng đoạn rời, rồi khâu lại bằng FFmpeg với
# đúng khoảng im lặng ở giữa. Nhờ vậy thẻ break hoạt động với MỌI giọng (Edge, Minion,
# OmniVoice, gTTS) vì nó nằm ngoài tầng TTS.

import re as _re

BREAK_TAG_RE = _re.compile(
    r"""<\s*break\s+time\s*=\s*["']?\s*(\d+(?:[.,]\d+)?)\s*(ms|s)\s*["']?\s*/?\s*>""",
    _re.IGNORECASE,
)

# Trần 5s: dài hơn thì khán giả video ngắn tưởng file lỗi và vuốt qua.
MAX_BREAK_SECONDS = 5.0
_SILENCE_SAMPLE_RATE = 24000


def has_break_tags(text: str) -> bool:
    return bool(BREAK_TAG_RE.search(text or ""))


def strip_break_tags(text: str) -> str:
    """Bỏ thẻ break, dùng cho phụ đề/hiển thị (khán giả không được thấy thẻ)."""
    cleaned = BREAK_TAG_RE.sub(" ", text or "")
    return _re.sub(r"\s{2,}", " ", cleaned).strip()


def split_by_breaks(text: str) -> list[tuple[str, float]]:
    """
    Cắt text thành [(đoạn_chữ, số_giây_nghỉ_sau_đoạn), ...].

    Hai thẻ dính nhau thì cộng dồn thời gian nghỉ; thẻ đứng ngay ĐẦU cảnh bị bỏ qua
    (khoảng lặng mở màn đã thuộc về chuyển cảnh trước đó). Cả hai cách xử lý đều nhằm
    tránh sinh ra đoạn chữ rỗng — Edge-TTS trả file 0 byte cho chuỗi rỗng.
    """
    parts: list[tuple[str, float]] = []
    cursor = 0
    for m in BREAK_TAG_RE.finditer(text or ""):
        value = float(m.group(1).replace(",", "."))
        seconds = value / 1000.0 if m.group(2).lower() == "ms" else value
        seconds = max(0.0, min(MAX_BREAK_SECONDS, seconds))
        chunk = (text[cursor:m.start()] or "").strip()
        if chunk:
            parts.append((chunk, seconds))
        elif parts:
            # Thẻ dính ngay sau thẻ trước → cộng dồn thời gian nghỉ.
            prev_text, prev_pause = parts[-1]
            parts[-1] = (prev_text, min(MAX_BREAK_SECONDS, prev_pause + seconds))
        cursor = m.end()
    tail = (text[cursor:] or "").strip()
    if tail:
        parts.append((tail, 0.0))
    return parts


def _resolve_written_path(requested: str) -> str | None:
    """
    Đường dẫn file THẬT SỰ được ghi ra.

    Cần thiết vì OmniVoice/gTTS có thể ghi .wav trong khi caller xin .mp3 (hoặc ngược
    lại) — đúng cái bẫy mà `wav_alt` trong main.py đang đỡ.
    """
    base, ext = os.path.splitext(requested)
    for candidate in (requested, base + ".wav", base + ".mp3"):
        if os.path.isfile(candidate) and os.path.getsize(candidate) > 0:
            return candidate
    return None


def _concat_audio_with_pauses(
    segments: list[tuple[str, float]], output_path: str
) -> None:
    """
    Nối các file audio, chèn im lặng giữa chúng, ghi đè lên output_path.

    Dùng FFmpeg chứ không phải MoviePy: các đoạn có thể khác định dạng (mp3 của
    Edge-TTS, wav của OmniVoice) và khác số kênh; `aresample`+`aformat` ép tất cả về
    cùng chuẩn trước khi concat, việc mà concatenate_audioclips không tự làm — lệch
    số kênh là nó ném lỗi giữa chừng.
    """

    import imageio_ffmpeg

    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-hide_banner", "-nostats"]
    labels: list[str] = []
    filters: list[str] = []
    idx = 0
    for seg_path, pause in segments:
        cmd += ["-i", seg_path]
        filters.append(
            f"[{idx}:a]aresample={_SILENCE_SAMPLE_RATE},"
            f"aformat=sample_fmts=s16:channel_layouts=mono[a{idx}]"
        )
        labels.append(f"[a{idx}]")
        idx += 1
        if pause > 0:
            cmd += [
                "-f", "lavfi", "-t", f"{pause:.3f}",
                "-i", f"anullsrc=r={_SILENCE_SAMPLE_RATE}:cl=mono",
            ]
            filters.append(
                f"[{idx}:a]aformat=sample_fmts=s16:channel_layouts=mono[a{idx}]"
            )
            labels.append(f"[a{idx}]")
            idx += 1

    filters.append(f"{''.join(labels)}concat=n={len(labels)}:v=0:a=1[out]")
    tmp_out = output_path + ".breaks.tmp" + (os.path.splitext(output_path)[1] or ".mp3")
    cmd += ["-filter_complex", ";".join(filters), "-map", "[out]", tmp_out]

    subprocess.run(cmd, check=True, capture_output=True, text=True, errors="replace", timeout=300)
    os.replace(tmp_out, output_path)


async def _synthesize_with_breaks(
    text: str, output_path: str, warning_callback, **kwargs
) -> tuple[float, list]:
    """Đọc từng đoạn giữa các thẻ break rồi khâu lại kèm khoảng lặng."""

    segments = split_by_breaks(text)
    if len(segments) <= 1:
        return await _synthesize_speech_internal(
            strip_break_tags(text), output_path, warning_callback=warning_callback, **kwargs
        )

    tmp_dir = tempfile.mkdtemp(prefix="tts_breaks_")
    produced: list[tuple[str, float]] = []
    total_dur = 0.0
    merged_wbs: list = []
    try:
        for i, (chunk, pause) in enumerate(segments):
            seg_target = os.path.join(tmp_dir, f"seg_{i}{os.path.splitext(output_path)[1] or '.mp3'}")
            dur, wbs = await _synthesize_speech_internal(
                chunk, seg_target, warning_callback=warning_callback, **kwargs
            )
            written = _resolve_written_path(seg_target)
            if not written:
                raise RuntimeError(f"Đoạn {i + 1} không sinh được audio.")
            for wb in wbs or []:
                shifted = dict(wb)
                shifted["offset"] = shifted.get("offset", 0.0) + total_dur
                merged_wbs.append(shifted)
            produced.append((written, pause))
            total_dur += dur + pause

        _concat_audio_with_pauses(produced, output_path)
        return total_dur, merged_wbs
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


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
    Có TTS Cache: cùng (text, voice, rate, pitch, emotion, breathing) → tái dùng audio cũ,
    render lại video không tốn thời gian sinh giọng.
    """
    from services.cache_service import cache as _tts_cache

    cache_params = dict(
        text=text, voice=voice, rate=rate, pitch=pitch,
        emotion=emotion or "", breathing=bool(use_breathing),
    )
    cached_meta = _tts_cache.get("tts_meta", **cache_params)
    if cached_meta and _tts_cache.get_media("tts", output_path, **cache_params):
        logger.info(f"[TTS Cache] HIT — tái dùng giọng đọc đã sinh ({voice}).")
        return cached_meta.get("duration", 3.0), cached_meta.get("word_boundaries", [])

    if has_break_tags(text):
        # Vi chỉnh nhịp đọc: cắt tại thẻ, đọc rời, khâu lại kèm khoảng lặng thật.
        # Hỏng ở bất kỳ đoạn nào cũng KHÔNG được giết cảnh — quay về đọc liền một mạch
        # với thẻ bị gỡ bỏ, mất nhịp nghỉ còn hơn mất tiếng.
        try:
            dur, wbs = await _synthesize_with_breaks(
                text, output_path, warning_callback,
                voice=voice, rate=rate, pitch=pitch, mode=mode, emotion=emotion,
            )
        except Exception as break_err:
            logger.warning(f"[TTS Break] Ghép nhịp nghỉ thất bại ({break_err}). Đọc liền mạch.")
            dur, wbs = await _synthesize_speech_internal(
                strip_break_tags(text), output_path, voice, rate, pitch, mode, emotion, warning_callback
            )
    else:
        dur, wbs = await _synthesize_speech_internal(text, output_path, voice, rate, pitch, mode, emotion, warning_callback)

    if use_breathing and os.path.exists(output_path):
        breath_path = os.path.join(SFX_DIR, "breath.wav")
        if os.path.exists(breath_path):
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
                
                shutil.move(temp_out, output_path)
                
                # Shift word boundaries
                breath_dur = breath_clip.duration
                dur += breath_dur
                for wb in wbs:
                    wb["offset"] += breath_dur
                    
            except Exception as e:
                logger.warning(f"[Breathing] Error applying breathing effect: {e}")

    # Lưu cache (file audio + metadata duration/word_boundaries) cho lần render sau
    try:
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            _tts_cache.set_media("tts", output_path, **cache_params)
            _tts_cache.set("tts_meta", {"duration": dur, "word_boundaries": wbs}, **cache_params)
    except Exception as cache_err:
        logger.warning(f"[TTS Cache] Save error (non-fatal): {cache_err}")

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
        logger.warning(f"Voice {voice} không tồn tại. Fallback về vi-VN-HoaiMyNeural.")
        voice = "vi-VN-HoaiMyNeural"

    # Chuẩn hóa text
    text = _normalize_text(text)

    # Xử lý giọng ảo (Minion) & Disable Prosody Engine mặc định để giữ độ mượt mà toàn cục (full-context TTS)
    use_prosody = False
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
            logger.warning(f"Edge-TTS error (attempt {attempt+1}/3): {e}")
            if os.path.exists(output_path):
                os.remove(output_path)
            tmp = output_path + ".tmp"
            if os.path.exists(tmp):
                os.remove(tmp)
            await asyncio.sleep(2)

    # Fallback gTTS & Offline SAPI5
    logger.warning(f"Edge-TTS failed completely: {last_error}. Chuyển sang gTTS Fallback.")
    return await _synthesize_gtts_fallback(text, output_path)


def get_available_voices():
    """Danh sách giọng: built-in + giọng clone cá nhân của user."""
    voices = list(VIETNAMESE_VOICES)
    for cv in _load_custom_voices():
        voices.append({
            "id": cv["id"],
            "name": f"🎤 {cv.get('name', cv['id'])} (Clone)",
            "gender": "Clone",
        })
    return voices


# ══════════════════════════════════════════════════════════════════════
# TTS Health & Warmup (Phase 1)
# ══════════════════════════════════════════════════════════════════════

def get_tts_health() -> dict:
    """Trạng thái hạ tầng TTS — cho UI hiển thị GPU voice sẵn sàng hay chưa."""
    import importlib.util
    health = {
        "omnivoice_repo": os.path.isdir(os.getenv("OMNIVOICE_PATH", r"C:\dev\OmniVoice")),
        "omnivoice_model_loaded": _omnivoice_model is not None,
        "stable_whisper_installed": importlib.util.find_spec("stable_whisper") is not None,
        "whisper_align_loaded": _whisper_model is not None,
        "custom_voices": len(_load_custom_voices()),
        "cuda": False,
        "gpu_name": None,
    }
    try:
        import torch
        health["cuda"] = torch.cuda.is_available()
        if health["cuda"]:
            health["gpu_name"] = torch.cuda.get_device_name(0)
    except Exception:
        pass
    return health


async def warmup_omnivoice():
    """
    Load trước OmniVoice + whisper-align trong background lúc khởi động server,
    để cảnh đầu tiên không phải chịu trễ load model (30-60s).
    Gọi từ startup event của FastAPI; lỗi chỉ log, không làm chết server.
    """
    try:
        await asyncio.to_thread(_get_omnivoice_model)
        logger.info("[Warmup] OmniVoice model sẵn sàng.")
    except Exception as e:
        logger.warning(f"[Warmup] OmniVoice không khả dụng ({type(e).__name__}: {e}). Sẽ dùng Edge-TTS.")
    try:
        await asyncio.to_thread(_get_whisper_model)
        logger.info("[Warmup] Whisper alignment model sẵn sàng.")
    except Exception as e:
        logger.warning(f"[Warmup] stable-whisper không khả dụng: {e}")
