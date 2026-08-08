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
import threading
import imageio_ffmpeg
_ffmpeg_dir = os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
if _ffmpeg_dir not in os.environ.get("PATH", ""):
    os.environ["PATH"] += os.pathsep + _ffmpeg_dir
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
from config import (  # noqa: F401
    CACHE_DIR,
    CUSTOM_VOICES_FILE,
    MEDIA_CACHE_DIR,
    SFX_DIR,
    VOICES_PREVIEW_DIR,
)

# Giọng Edge-TTS thay thế khi giọng clone/OmniVoice không dùng được, theo giới tính.
FALLBACK_VOICE_BY_GENDER = {
    "Nam": ("vi-VN-NamMinhNeural", "Nam Minh"),
    "Nữ": ("vi-VN-HoaiMyNeural", "Hoài My"),
}

# Giọng OmniVoice dựng sẵn: id → chuỗi instruct gửi cho model. Ở mức MODULE chứ không
# nằm trong thân hàm sinh giọng: đây cũng là nơi duy nhất ghi giới tính của từng preset,
# mà việc chọn giọng đọc thay thế lúc OmniVoice hỏng phải đọc được nó.
OMNIVOICE_MAPPING = {
    "omnivoice_female_storyteller_vi": "female, young adult, energetic, moderate pitch",
    "omnivoice_male_podcast_vi": "male, young adult, moderate pitch",
    "omnivoice_male_elderly_vi": "male, elderly, low pitch",
    "omnivoice_male_middle_aged_low_vi": "male, middle-aged, low pitch",
    "omnivoice_female_whisper_vi": "female, young adult, whisper",
    "omnivoice_female_child_vi": "female, child, high pitch",
}

# Dò giới tính từ tên hiển thị do user đặt. Nữ đứng TRƯỚC nam vì "female" chứa "male"
# và "Nữ" thường đi kèm chữ "nam" trong câu tiếng Việt ("giọng nữ Việt Nam").
_FEMALE_HINTS = ("nữ", "female", "chị ", "cô ", "bà ", "gái", "woman", "girl")
_MALE_HINTS = ("nam", "male", "anh ", "chú ", "ông ", "trai", "man", "boy")


def _gender_from_name(text: str) -> str | None:
    """Suy giới tính từ chuỗi tự do (tên giọng). None nếu không đoán được."""
    low = f" {(text or '').lower()} "
    for hint in _FEMALE_HINTS:
        if hint in low:
            return "Nữ"
    for hint in _MALE_HINTS:
        if hint in low:
            return "Nam"
    return None


def _gender_from_instruct(instruct: str) -> str | None:
    """
    Suy giới tính từ chuỗi instruct của OmniVoice — so khớp THEO TOKEN, không phải
    substring.

    LỖI CŨ: `"male" in instruct` trả True cho "female, young adult, whisper" (chữ
    "female" chứa "male"), nên MỌI giọng nữ preset đều rơi về giọng nam Nam Minh khi
    OmniVoice hỏng.
    """
    tokens = {t.strip().lower() for t in (instruct or "").replace("_", ", ").split(",")}
    if "female" in tokens:
        return "Nữ"
    if "male" in tokens:
        return "Nam"
    return None


# register/update/remove_custom_voice đều load→sửa→save không đồng bộ. Không khoá thì
# 2 request sửa giọng clone cùng lúc (VD lưu transcript đối chiếu trong
# ensure_clone_ref_text() trong khi user đang đổi tên giọng ở UI) là mất update của
# nhau — request ghi sau thắng, ghi đè lên bản đã load TRƯỚC lúc request kia lưu xong.
_custom_voices_lock = threading.Lock()


def _load_custom_voices() -> list:
    if not os.path.exists(CUSTOM_VOICES_FILE):
        return []
    try:
        with open(CUSTOM_VOICES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_custom_voices(voices: list):
    """Ghi atomic (tmp+replace) — ghi dở dang giữa chừng thì lần load sau vẫn còn
    bản JSON cũ nguyên vẹn, thay vì rơi vào `except Exception: return []` của
    _load_custom_voices() và mất trắng sổ giọng clone."""
    tmp_path = CUSTOM_VOICES_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(voices, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, CUSTOM_VOICES_FILE)


def get_custom_voice(voice_id: str) -> dict | None:
    for v in _load_custom_voices():
        if v.get("id") == voice_id:
            return v
    return None


def register_custom_voice(voice_id: str, name: str, ref_text: str, gender: str | None = None) -> dict:
    with _custom_voices_lock:
        voices = _load_custom_voices()
        entry = {
            "id": voice_id,
            "name": name,
            "ref_text": ref_text,
            # Ghi giới tính NGAY LÚC TẠO: khi OmniVoice hỏng giữa chừng, đây là thứ duy
            # nhất cho biết nên đọc thay bằng giọng nam hay giọng nữ. Suy từ tên là
            # phương án chót.
            "gender": _normalize_gender(gender) or _gender_from_name(name) or "Nữ",
        }
        voices = [v for v in voices if v.get("id") != voice_id]
        voices.append(entry)
        _save_custom_voices(voices)
        return entry


def update_custom_voice(voice_id: str, name: str | None = None,
                        ref_text: str | None = None, gender: str | None = None,
                        ref_text_match: float | None = None,
                        ref_text_source: str | None = None) -> dict | None:
    """
    Sửa thông tin một giọng clone. Trả về bản ghi mới, hoặc None nếu không tồn tại.
    Chỉ ghi đè các trường được truyền vào (None = giữ nguyên).
    """
    with _custom_voices_lock:
        voices = _load_custom_voices()
        updated = None
        for v in voices:
            if v.get("id") != voice_id:
                continue
            if name is not None and name.strip():
                v["name"] = name.strip()
            if ref_text is not None and ref_text.strip():
                v["ref_text"] = ref_text.strip()
                # Transcript đổi thì điểm đối chiếu cũ hết hiệu lực — trừ khi người gọi
                # đưa điểm mới kèm theo (chính là lúc nó vừa được đo lại).
                if ref_text_match is None:
                    v.pop("ref_text_match", None)
            if ref_text_match is not None:
                v["ref_text_match"] = round(float(ref_text_match), 3)
            if ref_text_source:
                v["ref_text_source"] = ref_text_source
            g = _normalize_gender(gender)
            if g:
                v["gender"] = g
            elif not v.get("gender"):
                v["gender"] = _gender_from_name(v.get("name", "")) or "Nữ"
            updated = v
            break
        if updated is None:
            return None
        _save_custom_voices(voices)
        return updated


def _normalize_gender(gender: str | None) -> str | None:
    """'male'/'nam'/'Nam' → 'Nam'; 'female'/'nữ' → 'Nữ'; rác → None."""
    if not gender:
        return None
    g = gender.strip().lower()
    if g in ("nữ", "nu", "female", "f", "woman"):
        return "Nữ"
    if g in ("nam", "male", "m", "man"):
        return "Nam"
    return None


# ── Đối chiếu transcript với file mẫu ────────────────────────────────
# VÌ SAO PHẢI CÓ: OmniVoice nhận (ref_audio, ref_text) làm CẶP — nó coi ref_text là lời
# thoại của ref_audio rồi "đọc tiếp" sang văn bản đích. Nếu hai thứ không khớp, mô hình
# mất hoàn toàn mốc căn chữ↔tiếng và sinh ra thứ nghe RẤT giống tiếng Việt nhưng vô
# nghĩa — đúng triệu chứng "đọc không hiểu tiếng Việt".
#
# Đã xảy ra thật: giọng `omnivoice_custom_nam_tien_duc` có ref_text ghi "Chào các bạn,
# tôi là Nam Tiến Đức... giúp tự động hóa hoàn toàn quy trình..." trong khi file mẫu
# thực sự đọc "Hãy yêu thương bản thân như cách đất trời nâng niu từng tia nắng...".
# Mọi video dựng bằng giọng đó đều đọc bậy, và KHÔNG có một dòng cảnh báo nào.
MIN_REF_TEXT_MATCH = 0.55


def _transcript_words(text: str) -> list[str]:
    """Chuẩn hoá về danh sách từ thường, bỏ dấu câu — giữ nguyên dấu tiếng Việt."""
    return re.sub(r"[^\w\s]", " ", (text or "").lower()).split()


def transcript_similarity(a: str, b: str) -> float:
    """
    Độ khớp 0..1 giữa hai đoạn lời thoại, so THEO TỪ chứ không theo ký tự.

    So theo ký tự sẽ chấm điểm cao một cách giả tạo cho hai câu tiếng Việt bất kỳ, vì
    chúng dùng chung rất nhiều nguyên âm và dấu. So theo từ mới phân biệt được
    "sai chính tả vài chữ" (whisper nghe nhầm — chấp nhận được) với "hai nội dung khác
    hẳn nhau" (cặp mẫu/transcript hỏng — phải chặn).
    """
    import difflib
    wa, wb = _transcript_words(a), _transcript_words(b)
    if not wa or not wb:
        return 0.0
    return difflib.SequenceMatcher(None, wa, wb).ratio()


def transcribe_vietnamese(wav_path: str) -> str:
    """
    Chép lời một file audio tiếng Việt bằng whisper. Trả chuỗi rỗng nếu không chạy được.

    `fp16=False` là BẮT BUỘC, không phải tuỳ chọn cho chạy nhanh: trên GPU này whisper
    chạy fp16 (mặc định khi có CUDA) cho ra logits toàn NaN rồi ném ValueError giữa
    chừng — đo được, lặp lại 100%. Hậu quả cũ: mọi lần tự chép lời file mẫu đều thất
    bại, bị nuốt trong except, và giọng clone rơi về ref_text mặc định "Chào bạn, đây là
    giọng đọc tham khảo..." — tức SAI hoàn toàn so với file ghi âm, đúng cái cặp lệch
    làm giọng đọc ra tiếng Việt vô nghĩa. fp32 trên GPU vẫn chỉ mất ~2 giây.
    """
    try:
        model = _get_whisper_model("small")
        result = model.transcribe(wav_path, language="vi", fp16=False)
        return " ".join(seg.text.strip() for seg in result.segments).strip()
    except Exception as e:
        logger.warning(f"[VoiceClone] Whisper chép lời thất bại: {e}")
        return ""


def ensure_clone_ref_text(voice_id: str, ref_wav_path: str) -> tuple[str, str | None]:
    """
    Trả về (ref_text ĐÁNG TIN của giọng clone, cảnh báo cho UI hoặc None).

    TỰ CHỮA: bản ghi cũ (tạo trước khi có bước đối chiếu) chưa có `ref_text_match`.
    Lần đầu dùng tới, hàm này chép lời file mẫu rồi so với transcript đang lưu:
      • khớp  → ghi lại điểm số, lần sau không phải chép lời nữa.
      • lệch  → THAY transcript bằng bản chép từ chính file mẫu, và báo cho user biết.

    Thà dùng bản chép máy có vài chữ sai còn hơn một transcript của đoạn ghi âm khác:
    sai vài chữ chỉ làm phát âm hơi lệch, còn sai cả đoạn thì giọng đọc ra vô nghĩa.
    """
    cv = get_custom_voice(voice_id)
    if not cv:
        return "", None
    stored = (cv.get("ref_text") or "").strip()
    if cv.get("ref_text_match") is not None:
        return stored, None          # đã đối chiếu rồi, không chép lời lại

    heard = transcribe_vietnamese(ref_wav_path)
    if not heard:
        return stored, None          # không chép lời được → giữ nguyên, đừng phá

    score = transcript_similarity(stored, heard) if stored else 0.0
    if stored and score >= MIN_REF_TEXT_MATCH:
        update_custom_voice(voice_id, ref_text_match=score)
        return stored, None

    update_custom_voice(voice_id, ref_text=heard, ref_text_match=1.0, ref_text_source="asr_auto")
    # Mọi audio đã sinh bằng transcript sai đều là rác — không xoá thì lần render sau
    # vẫn lấy nguyên bản đọc bậy từ cache và việc tự chữa coi như chưa từng xảy ra.
    purge_voice_cache(voice_id)
    invalidate_voice_prompt(voice_id)      # prompt cũ đã nướng sẵn ref_text sai bên trong
    canh_bao = (
        f"⚠️ Văn bản đọc mẫu của giọng '{cv.get('name', voice_id)}' KHÔNG khớp file ghi âm "
        f"(độ khớp {score:.0%}). File mẫu thực sự đọc: \"{heard[:110]}...\". "
        "Đã tự sửa lại theo file ghi âm — đây chính là nguyên nhân giọng đọc ra tiếng Việt vô nghĩa."
    )
    logger.warning(f"[VoiceClone] {canh_bao}")
    return heard, canh_bao


def chep_loi_theo_cau(wav_path: str) -> list[dict]:
    """
    Chép lời kèm mốc thời gian TỪNG CÂU: [{"start", "end", "text"}, ...].

    Dùng để cắt mẫu giọng đúng ranh giới câu. Cắt theo năng lượng (silencedetect) không
    ăn thua với người nói liên tục — đo trên mẫu thật: không tìm được quãng lặng nào
    trong cả 10 giây. Mốc câu của whisper thì luôn có, và kèm theo một món hời: transcript
    của phần GIỮ LẠI là ghép thẳng các câu đó, nên cặp (audio, ref_text) khớp tuyệt đối
    mà không phải chép lời lần hai.
    """
    try:
        model = _get_whisper_model("small")
        result = model.transcribe(wav_path, language="vi", fp16=False)
        return [
            {"start": float(s.start), "end": float(s.end), "text": s.text.strip()}
            for s in result.segments if s.text.strip()
        ]
    except Exception as e:
        logger.warning(f"[VoiceClone] Chép lời theo câu thất bại: {e}")
        return []


def chon_diem_cat_mau(cau: list[dict], toi_da: float, toi_thieu: float) -> tuple[float | None, str]:
    """
    Chọn mốc cắt mẫu giọng và transcript tương ứng, từ danh sách câu đã chép lời.

    Ưu tiên 1 — kết thúc đúng CUỐI MỘT CÂU trong khoảng cho phép. OmniVoice coi ref_text
    là phần mở đầu rồi đọc TIẾP; mẫu dừng giữa câu là mời mô hình nói nốt câu dở đó. Đã
    đo được thật: mẫu cắt cứng giữa câu làm bản đọc bắt đầu bằng một mẩu rác lấy từ chính
    file mẫu trước khi vào nội dung cần đọc.

    Ưu tiên 2 — không câu nào kết thúc kịp thì lấy trọn câu đầu dù hơi ngắn, còn hơn cắt
    giữa chừng. Trả (None, "") nếu không chép được lời — phía gọi cắt cứng như cũ.

    LƯU Ý về "câu": whisper cắt đoạn theo khoảng ~5 giây, KHÔNG theo ngữ pháp — đoạn của
    nó thường kết thúc lửng giữa mệnh đề ("...khi gia đình tố"). Nên phải ưu tiên đoạn
    nào thật sự kết thúc bằng dấu chấm/hỏi/than; ranh giới đoạn trần chỉ là lựa chọn thứ hai.
    """
    if not cau:
        return None, ""
    trong_khoang = [c for c in cau if toi_thieu <= c["end"] <= toi_da]
    if trong_khoang:
        # Đoạn kết thúc bằng dấu kết câu = câu trọn vẹn thật sự, mô hình không còn gì
        # để "nói nốt". Ưu tiên tuyệt đối, kể cả khi phải bỏ đi vài giây phía sau.
        tron_ven = [c for c in trong_khoang if c["text"].rstrip().endswith((".", "!", "?", "…"))]
        moc = (tron_ven or trong_khoang)[-1]
        giu = cau[: cau.index(moc) + 1]
    else:
        giu = cau[:1]
        if giu[0]["end"] > toi_da:
            return None, ""          # ngay câu đầu đã dài quá trần → đành cắt cứng
    return giu[-1]["end"], " ".join(c["text"] for c in giu).strip()


def get_clone_gender(voice_id: str) -> str:
    """
    Giới tính của một giọng clone, tra từ registry (voices_custom.json).
    Ưu tiên trường `gender` đã lưu; chưa có thì suy từ tên; bí quá thì mặc định "Nữ".
    """
    cv = get_custom_voice(voice_id)
    if not cv:
        return "Nữ"
    return _normalize_gender(cv.get("gender")) or _gender_from_name(cv.get("name", "")) or "Nữ"


def resolve_fallback_voice(voice: str) -> tuple[str, str, str]:
    """
    Giọng Edge-TTS thay thế khi OmniVoice không dùng được.

    Trả về (voice_id_edge, tên hiển thị, giới tính). Giọng clone cá nhân tra registry;
    giọng preset omnivoice_* đọc token trong instruct/tên preset.
    """
    if voice.startswith("omnivoice_custom_"):
        gender = get_clone_gender(voice)
    else:
        # Bảng preset là nguồn chuẩn; id preset và chuỗi instruct thô đều dò được nốt.
        instruct = OMNIVOICE_MAPPING.get(voice, voice)
        gender = _gender_from_instruct(instruct) or _gender_from_name(voice) or "Nữ"
    vid, vname = FALLBACK_VOICE_BY_GENDER[gender]
    return vid, vname, gender


def remove_custom_voice(voice_id: str) -> bool:
    with _custom_voices_lock:
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
    invalidate_voice_prompt(voice_id)
    purge_voice_cache(voice_id)
    return True

import random
import re
import logging
import threading
import time

logger = logging.getLogger(__name__)


# ── Sổ tra ngược cache giọng clone ───────────────────────────────────
# Khoá cache của cache_service là md5 của bộ tham số → KHÔNG thể suy ngược từ voice_id
# ra tên file. Muốn xoá sạch audio cũ khi user sửa/xoá một giọng clone thì phải ghi lại
# tên file ngay lúc lưu cache. Chỉ ghi cho giọng `omnivoice_custom_*`: giọng dựng sẵn
# không bao giờ đổi nội dung nên cache của chúng luôn hợp lệ.
_VOICE_CACHE_INDEX_FILE = os.path.join(CACHE_DIR, "tts_voice_cache_index.json")
_voice_index_lock = threading.Lock()


def _read_voice_cache_index() -> dict:
    try:
        with open(_VOICE_CACHE_INDEX_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_voice_cache_index(index: dict) -> None:
    tmp = _VOICE_CACHE_INDEX_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _VOICE_CACHE_INDEX_FILE)


def _index_voice_cache_entry(voice: str, meta_prefix: str, media_prefix: str, cache_params: dict) -> None:
    """
    Ghi nhận (tên file json meta, khoá file media) vừa lưu cho một giọng clone.

    `cache_params` truyền vào dạng DICT chứ không phải **kwargs: bộ tham số cache luôn
    có khoá "voice", trùng tên tham số đầu tiên của hàm này → TypeError ngay lần lưu
    cache đầu tiên (lỗi bị nuốt trong khối try, sổ tra ngược rỗng vĩnh viễn).
    """
    if not voice or not voice.startswith("omnivoice_custom_"):
        return
    try:
        from services.cache_service import cache as _c
        meta_name = _c._get_key(meta_prefix, **cache_params)
        media_key = _c._media_key(media_prefix, **cache_params)
        with _voice_index_lock:
            index = _read_voice_cache_index()
            entries = index.setdefault(voice, [])
            pair = [meta_name, media_key]
            if pair not in entries:
                entries.append(pair)
                _write_voice_cache_index(index)
    except Exception as e:      # sổ tra ngược hỏng KHÔNG được làm chết pipeline giọng
        logger.warning(f"[TTS Cache] Không ghi được sổ tra cache cho {voice}: {e}")


def purge_voice_cache(voice_id: str) -> int:
    """
    Xoá mọi file audio đã cache của một giọng clone (dùng khi sửa/xoá giọng).
    Trả về số file đã xoá. Không bao giờ ném exception.
    """
    removed = 0
    try:
        with _voice_index_lock:
            index = _read_voice_cache_index()
            entries = index.pop(voice_id, [])
            if entries:
                _write_voice_cache_index(index)
    except Exception as e:
        logger.warning(f"[TTS Cache] Đọc sổ tra cache lỗi: {e}")
        return 0

    from services.cache_service import _MEDIA_EXTS

    for entry in entries:
        try:
            meta_name, media_key = entry[0], entry[1]
        except Exception:
            continue
        candidates = [os.path.join(CACHE_DIR, meta_name)]
        candidates += [os.path.join(MEDIA_CACHE_DIR, media_key + ext) for ext in _MEDIA_EXTS]
        for path in candidates:
            try:
                if os.path.isfile(path):
                    os.remove(path)
                    removed += 1
            except OSError:
                pass
    if removed:
        logger.info(f"[TTS Cache] Đã xoá {removed} file cache của giọng {voice_id}.")
    return removed


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


def _probe_audio_duration(path: str) -> float | None:
    """Thời lượng THẬT của một file audio (giây), hoặc None nếu không đọc được."""
    if not path or not os.path.isfile(path):
        return None
    try:
        import soundfile as sf
        return float(sf.info(path).duration)
    except Exception:
        pass
    try:
        return float(MP3(path).info.length)
    except Exception:
        pass
    try:
        from moviepy.audio.io.AudioFileClip import AudioFileClip
        clip = AudioFileClip(path)
        dur = float(clip.duration)
        clip.close()
        return dur
    except Exception:
        return None


# Nhịp nghỉ chèn giữa hai cảnh khi phải ghép từng cảnh lại. Ngắn hơn khoảng lặng mà
# Edge-TTS tự tạo giữa hai câu trong một lần đọc liền, nhưng đủ để tai không thấy hai
# cảnh dính vào nhau như một câu duy nhất.
NARRATION_SCENE_GAP = 0.35


async def _synthesize_script_per_scene_concat(
    scene_texts: list[str],
    output_path: str,
    voice: str,
    rate: str,
    pitch: str,
    warning_callback=None,
    progress_callback=None,
) -> tuple[float, list[list]]:
    """
    Sinh giọng TỪNG CẢNH rồi khâu lại thành một dải audio duy nhất, kèm word boundaries
    quy về MỐC TUYỆT ĐỐI của cả bài — tức đúng hợp đồng mà `synthesize_script_single_pass`
    trả về, nên phía dựng timeline không cần biết bản đọc được sinh bằng cách nào.

    Dùng cho các giọng không đọc liền mạch được (OmniVoice/clone/minion): chúng không
    trả về word boundaries của Edge-TTS, và OmniVoice còn phải cắt nhỏ text theo trần
    ký tự nên không thể nuốt cả kịch bản trong một lần gọi.
    """
    tmp_dir = tempfile.mkdtemp(prefix="narration_scenes_")
    produced: list[tuple[str, float]] = []
    scene_wbs: list[list] = [[] for _ in scene_texts]
    cursor = 0.0
    try:
        for i, raw in enumerate(scene_texts):
            t = (raw or "").strip()
            if not _normalize_text(t):
                continue        # cảnh không lời → không chiếm giây nào trên dải giọng
            if progress_callback:
                # Báo TRƯỚC khi sinh, không phải sau: cảnh OmniVoice mất hàng chục giây,
                # báo sau thì suốt thời gian chờ màn hình vẫn đứng ở cảnh trước đó.
                try:
                    await progress_callback(i, len(scene_texts))
                except Exception:
                    pass
            seg_target = os.path.join(tmp_dir, f"scene_{i+1}.mp3")
            # Truyền text THÔ, không phải bản đã _normalize_text: khoá cache của
            # synthesize_speech tính trên chuỗi nhận vào, mà đường render từng cảnh cũng
            # truyền text thô. Chuẩn hoá ở đây = hai khoá khác nhau cho cùng một câu →
            # nghe thử xong render vẫn sinh lại từ đầu, mất trắng công chờ.
            dur, wbs = await synthesize_speech(
                t, seg_target, voice=voice, rate=rate, pitch=pitch,
                warning_callback=warning_callback,
            )
            written = _resolve_written_path(seg_target)
            if not written:
                raise NarrationSplitError(f"Cảnh {i+1} không sinh được audio để ghép nối.")

            # Đo lại từ FILE THẬT: OmniVoice trả về max(1.0, dur) và nhánh <break> cộng
            # dồn ước lượng — lệch vài trăm ms mỗi cảnh là timeline trôi dần về cuối bài.
            real_dur = _probe_audio_duration(written) or dur
            bucket = wbs or _estimate_word_boundaries(t, real_dur)
            scene_wbs[i] = [
                {**wb, "offset": float(wb.get("offset", 0.0)) + cursor} for wb in bucket
            ]
            produced.append((written, NARRATION_SCENE_GAP))
            cursor += real_dur + NARRATION_SCENE_GAP

        if not produced:
            raise NarrationSplitError("Kịch bản không có lời thoại nào để đọc.")

        # Đoạn cuối không cần khoảng lặng đuôi
        produced[-1] = (produced[-1][0], 0.0)
        cursor -= NARRATION_SCENE_GAP

        await asyncio.to_thread(_concat_audio_with_pauses, produced, output_path)
        total = _probe_audio_duration(output_path) or cursor
        logger.info(
            f"[Narration] Ghép {len(produced)} cảnh thành dải giọng {total:.1f}s (giọng {voice})."
        )
        return total, scene_wbs
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def narration_cache_scope(voice: str) -> str:
    """
    Bản đọc cả bài của giọng này nạp được cache tới đâu.

      "per_scene"      — sinh từng cảnh rồi ghép (OmniVoice/clone/minion): MỖI cảnh vào
                         cache riêng, nên render kiểu nào cũng tái dùng được.
      "full_narration" — Edge-TTS gọi một lần cho cả bài: chỉ có MỘT mục cache cho toàn
                         bộ dải giọng, chỉ tái dùng khi render bật "Đọc liền mạch".

    Có hàm này để giao diện đừng hứa nhầm. Trước đó nút nghe thử cả bài tô xanh TẤT CẢ
    đèn cache — với giọng Edge ở chế độ render từng cảnh thì đó là nói dối: người dùng
    tưởng render sẽ tức thì rồi ngồi chờ sinh lại từ đầu.
    """
    return "per_scene" if (voice.startswith("omnivoice_") or voice.startswith("minion")) else "full_narration"


async def synthesize_script_single_pass(
    scene_texts: list[str],
    output_path: str,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
    pitch: str = "+0Hz",
    warning_callback=None,
    progress_callback=None,
) -> tuple[float, list[list], float]:
    """
    V4.1 — Sinh MỘT dải giọng cho toàn bộ kịch bản.

    Trả về (tổng thời lượng, word_boundaries đã chia theo cảnh (mốc TUYỆT ĐỐI), tổng dur).

    Hai đường sinh, cùng một hợp đồng trả về:
      • Giọng Edge-TTS  → gọi ĐÚNG MỘT LẦN cho cả bài (đọc liền mạch thật sự).
      • Giọng OmniVoice/clone/minion → sinh từng cảnh rồi khâu lại (xem
        `_synthesize_script_per_scene_concat`).

    LỖI CŨ: nhánh thứ hai ném thẳng NarrationSplitError, nên chọn giọng clone + bật
    "đọc liền mạch" là mất luôn chế độ hình-bám-theo-giọng, dù việc ghép nối hoàn toàn
    làm được. Giờ chỉ báo cho user biết cách sinh khác đi, không chặn.

    ĐÁNH ĐỔI CÓ CHỦ Ý: chế độ này BỎ QUA `emotion` và `speech_rate_modifier` riêng của
    từng cảnh, vì cả bài chỉ có một lần gọi nên không thể đổi rate/pitch giữa chừng.
    Đổi lại: cao độ, nhịp thở và ngữ điệu liên tục suốt video thay vì reset ở mỗi cảnh.

    Raise NarrationSplitError nếu có cảnh CÓ CHỮ nhưng không nhận được từ nào —
    dấu hiệu ánh xạ hỏng, caller phải quay về chế độ đọc từng cảnh.
    """
    from services.cache_service import cache as _tts_cache

    full_text, ranges = _prepare_scene_texts(scene_texts)
    per_scene = narration_cache_scope(voice) == "per_scene"

    cache_params = dict(
        mode="per_scene_concat" if per_scene else "single_pass",
        text=full_text, voice=voice, rate=rate, pitch=pitch,
    )
    cached = _tts_cache.get("tts_meta", **cache_params)
    if cached and _tts_cache.get_media("tts", output_path, **cache_params):
        logger.info("[Narration] Cache HIT — tái dùng bản đọc liền mạch.")
        return cached["duration"], cached["scene_wbs"], cached["duration"]

    if per_scene:
        msg = (
            f"ℹ️ Giọng '{voice}' không đọc liền một mạch được — hệ thống sinh từng cảnh "
            "rồi ghép lại thành một dải giọng. Timeline vẫn bám theo giọng đọc."
        )
        logger.info(f"[Narration] {msg}")
        if warning_callback:
            try:
                await warning_callback(msg)
            except Exception:
                pass
        duration, scene_wbs = await _synthesize_script_per_scene_concat(
            scene_texts, output_path, voice, rate, pitch,
            warning_callback=warning_callback, progress_callback=progress_callback,
        )
    else:
        logger.info(f"[Narration] Đọc liền mạch {len(scene_texts)} cảnh trong 1 lần gọi ({len(full_text)} ký tự)...")
        duration, wbs = await _synthesize_plain(full_text, output_path, voice, rate, pitch)

        scene_wbs = split_word_boundaries_by_scene(wbs, full_text, ranges)

        for i, (bucket, raw) in enumerate(zip(scene_wbs, scene_texts)):
            if not bucket and (raw or "").strip():
                raise NarrationSplitError(f"Cảnh {i+1} có lời thoại nhưng không nhận được từ nào.")

    try:
        _tts_cache.set_media("tts", output_path, **cache_params)
        _tts_cache.set("tts_meta", {"duration": duration, "scene_wbs": scene_wbs}, **cache_params)
        _index_voice_cache_entry(voice, "tts_meta", "tts", cache_params)
    except Exception as e:
        logger.warning(f"[Narration] Lưu cache lỗi (không nghiêm trọng): {e}")

    return duration, scene_wbs, duration


# ══════════════════════════════════════════════════════════════════════
# OmniVoice Engine (V3.2)
# ══════════════════════════════════════════════════════════════════════

_omnivoice_model = None
# Lý do model KHÔNG nạp được (thiếu CUDA / thiếu repo / thiếu package). Nhớ lại lý do
# thay vì thử nạp lại mỗi cảnh: một video 20 cảnh trên máy không GPU trước đây phải
# nuốt trọn 20 lần import torch + dò checkpoint, mỗi lần vài chục giây, rồi vẫn rơi về
# Edge-TTS. Lỗi nạp model là tất định trong một tiến trình, thử lại không đổi kết quả.
_omnivoice_load_error: str | None = None
# Chỉ có 1 GPU cho cả process. Khoá này dùng CHUNG cho việc load model (tránh 2 request
# đầu tiên cùng lúc double-load, tốn gấp đôi VRAM trên card 6GB) LẪN việc gọi
# model.generate() (tránh 2 render song song đè seed/forward-pass của nhau — xem
# _run_omnivoice_with_prosody bên dưới).
_omnivoice_lock = threading.Lock()


def _get_omnivoice_model():
    global _omnivoice_model, _omnivoice_load_error
    if _omnivoice_model is None and _omnivoice_load_error:
        raise RuntimeError(_omnivoice_load_error)
    if _omnivoice_model is not None:
        return _omnivoice_model
    with _omnivoice_lock:
        # Double-check: request khác có thể đã nạp xong trong lúc ta chờ lock.
        if _omnivoice_model is None and _omnivoice_load_error:
            raise RuntimeError(_omnivoice_load_error)
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
                _omnivoice_load_error = f"{type(e).__name__}: {e}"
                logger.error(f"[OmniVoice] Failed to load model: {e}")
                raise e
        return _omnivoice_model


def reset_omnivoice_load_error() -> None:
    """Cho phép thử nạp lại model sau khi user đã cài đặt/sửa cấu hình (gọi từ /api/tts-health)."""
    global _omnivoice_load_error
    _omnivoice_load_error = None


# ── Bộ nhớ đệm "prompt giọng" (VoiceClonePrompt) ─────────────────────
# Mỗi lần gọi generate(ref_audio=...) OmniVoice phải: đọc file wav → resample → chạy
# audio tokenizer → tính RMS. Kết quả CHỈ phụ thuộc (file mẫu, ref_text), mà cả hai đều
# đứng yên suốt một video — nên với video 20 cảnh, 19 lần mã hoá sau là làm lại y hệt.
#
# `create_voice_clone_prompt()` tách đúng phần đó ra thành một đối tượng tái dùng được,
# và `.save()/.load()` cho phép giữ qua các lần khởi động lại. Ta đệm ở hai tầng:
#   • RAM   — trong một tiến trình, nhanh nhất, không chạm đĩa;
#   • file  — `{voice_id}_prompt.pt` cạnh file mẫu, sống qua restart backend.
#
# KHOÁ ĐỆM phải gồm cả dấu vân tay của file mẫu (mtime + kích thước) VÀ ref_text: prompt
# đã nướng sẵn ref_text vào trong (xem class VoiceClonePrompt), nên sửa transcript mà
# vẫn dùng prompt cũ là quay lại đúng lỗi cặp lệch vừa sửa xong.
_voice_prompt_cache: dict = {}
_voice_prompt_lock = threading.Lock()


def _voice_prompt_fingerprint(ref_wav_path: str, ref_text: str) -> str:
    try:
        st = os.stat(ref_wav_path)
        stamp = f"{int(st.st_mtime)}:{st.st_size}"
    except OSError:
        stamp = "0:0"
    import hashlib
    return hashlib.md5(f"{stamp}|{ref_text}".encode("utf-8")).hexdigest()[:16]


def _voice_prompt_path(voice_id: str) -> str:
    return os.path.join(VOICES_PREVIEW_DIR, f"{voice_id}_prompt.pt")


def get_voice_clone_prompt(model, voice_id: str, ref_wav_path: str, ref_text: str):
    """
    Prompt giọng đã mã hoá sẵn cho (file mẫu, ref_text) hiện tại.

    Trả về None nếu OmniVoice bản này không có `create_voice_clone_prompt` — khi đó phía
    gọi cứ truyền ref_audio như cũ. Mọi lỗi ở đây đều KHÔNG được ném ra: đệm hỏng thì
    chỉ chậm, còn ném thì mất cả giọng clone.
    """
    if not hasattr(model, "create_voice_clone_prompt"):
        return None
    van_tay = _voice_prompt_fingerprint(ref_wav_path, ref_text)
    khoa = (voice_id, van_tay)

    with _voice_prompt_lock:
        hit = _voice_prompt_cache.get(khoa)
    if hit is not None:
        return hit

    pt_path = _voice_prompt_path(voice_id)
    meta_path = pt_path + ".fingerprint"
    try:
        # Chỉ nạp file .pt khi dấu vân tay khớp — file mẫu đổi thì bản lưu là rác.
        if os.path.isfile(pt_path) and os.path.isfile(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                if f.read().strip() == van_tay:
                    from omnivoice import VoiceClonePrompt
                    prompt = VoiceClonePrompt.load(pt_path)
                    with _voice_prompt_lock:
                        _voice_prompt_cache[khoa] = prompt
                    logger.info(f"[OmniVoice] Dùng lại prompt giọng đã lưu của {voice_id}.")
                    return prompt
    except Exception as e:
        logger.warning(f"[OmniVoice] Không nạp được prompt giọng đã lưu ({e}). Mã hoá lại.")

    try:
        prompt = model.create_voice_clone_prompt(ref_audio=ref_wav_path, ref_text=ref_text)
    except Exception as e:
        logger.warning(f"[OmniVoice] Mã hoá prompt giọng thất bại ({e}). Dùng thẳng ref_audio.")
        return None

    with _voice_prompt_lock:
        _voice_prompt_cache[khoa] = prompt
    try:
        prompt.save(pt_path)
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(van_tay)
    except Exception as e:
        logger.warning(f"[OmniVoice] Không lưu được prompt giọng xuống đĩa ({e}).")
    return prompt


def invalidate_voice_prompt(voice_id: str) -> None:
    """
    Bỏ prompt đã đệm của một giọng (khi file mẫu hoặc transcript thay đổi).

    Dấu vân tay đã tự lo phần đúng/sai, hàm này chỉ dọn rác cho gọn — nhưng vẫn phải
    gọi khi XOÁ giọng, nếu không file .pt nằm lại trong voices_preview mãi mãi.
    """
    with _voice_prompt_lock:
        for khoa in [k for k in _voice_prompt_cache if k[0] == voice_id]:
            _voice_prompt_cache.pop(khoa, None)
    for p in (_voice_prompt_path(voice_id), _voice_prompt_path(voice_id) + ".fingerprint"):
        try:
            if os.path.isfile(p):
                os.remove(p)
        except OSError:
            pass

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
# Mã ngôn ngữ gửi kèm mọi lần gọi OmniVoice. Bỏ trống thì model chạy chế độ
# "language-agnostic" (`<|lang_start|>None<|lang_end|>` trong prompt) — chính README của
# OmniVoice nói rõ chỉ định ngôn ngữ cho kết quả tốt hơn. Tiếng Việt có 8482 giờ dữ liệu
# huấn luyện (docs/languages.md), thuộc nhóm tài nguyên cao, không có lý do gì để giấu.
OMNIVOICE_LANG = "vi"

# Số bước khuếch tán. ĐỪNG HẠ XUỐNG để chạy nhanh — đã đo trên chính giọng clone của dự
# án (GTX 1660 SUPER, cùng câu, cùng seed), chép lời sản phẩm bằng whisper:
#   32 bước — 93s, audio 11.2s: "...tích góp tiền chỉ vì sợ thiếu thốn. Bà Lin Twist đã
#             chứng kiến suốt 40 năm rằng tiền luôn mang cảm xúc."   ✔ sạch
#   16 bước — 47s, audio 16.1s: "Ăn thướn KHÔ CANH CANH cắt các những góp tiền..."
#             ✘ "khô canh" là mảnh của ref_text ("cánh đồng khô cằn") RÒ vào output
#   8  bước — 24s, audio 18.7s: "dần trểu tên nhìn chí vì sự xô thốn. Ư...... Ư......"  ✘
# Dấu hiệu nhận biết hỏng mà không cần nghe: audio DÀI RA dù cùng văn bản — mô hình
# không hội tụ nên phần tạp âm không bị bước xoá-khoảng-lặng nhận ra.
# README của OmniVoice có gợi ý "16 cho nhanh", nhưng đó là cho tiếng Anh/Trung; tiếng
# Việt có thanh điệu nên nhạy hơn nhiều. Chỉnh qua env chỉ để thử nghiệm.
OMNIVOICE_NUM_STEP = int(os.getenv("OMNIVOICE_NUM_STEP", "32"))

# Tốc độ sinh giọng THẬT của máy này, đo lấy chứ không đoán: RTF = giây xử lý / giây
# audio. README của OmniVoice quảng cáo RTF 0.025 (nhanh gấp 40 lần thời gian thực) —
# con số đó đo trên GPU trung tâm dữ liệu có Tensor Core. Đo trên GTX 1660 SUPER (Turing
# TU116, KHÔNG có Tensor Core, 6GB) được RTF ≈ 8, tức chậm hơn ~300 lần quảng cáo.
# Giữ số đo lại để báo trước cho user thay vì để họ ngồi nhìn thanh tiến trình.
_omnivoice_rtf: float | None = None
_omnivoice_rtf_lock = threading.Lock()
_omnivoice_rtf_da_doc = False
# Trên ngưỡng này thì đáng báo cho user biết trước (chậm hơn thời gian thực 3 lần).
OMNIVOICE_RTF_CANH_BAO = 3.0
# Ghi số đo xuống đĩa để lần khởi động sau đã biết máy này nhanh hay chậm. Không có nó,
# user bấm nghe thử lần đầu sau mỗi lần khởi động lại backend đều không nhận được ước
# tính thời gian — đúng lúc cần nhất, vì đó là lần chờ lâu nhất.
_RTF_FILE = os.path.join(CACHE_DIR, "omnivoice_rtf.json")


def _doc_rtf_da_luu() -> None:
    global _omnivoice_rtf, _omnivoice_rtf_da_doc
    if _omnivoice_rtf_da_doc:
        return
    _omnivoice_rtf_da_doc = True
    try:
        with open(_RTF_FILE, "r", encoding="utf-8") as f:
            gia_tri = float(json.load(f).get("rtf"))
        if 0 < gia_tri < 1000:
            _omnivoice_rtf = gia_tri
    except Exception:
        pass        # chưa có file / file hỏng → coi như chưa đo, đừng đoán bừa


def _ghi_nhan_rtf(giay_xu_ly: float, giay_audio: float) -> float | None:
    """Cập nhật RTF theo trung bình trượt. Trả về RTF mới, hoặc None nếu số liệu vô nghĩa."""
    global _omnivoice_rtf
    if giay_audio <= 0.1 or giay_xu_ly <= 0:
        return None
    rtf = giay_xu_ly / giay_audio
    with _omnivoice_rtf_lock:
        _doc_rtf_da_luu()
        # Trọng số 0.3 cho mẫu mới: đủ nhạy khi máy đổi tải, đủ mượt để một cảnh ngắn
        # bất thường không kéo lệch cả ước tính.
        _omnivoice_rtf = rtf if _omnivoice_rtf is None else 0.7 * _omnivoice_rtf + 0.3 * rtf
        moi = _omnivoice_rtf
    try:
        tmp = _RTF_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"rtf": round(moi, 3)}, f)
        os.replace(tmp, _RTF_FILE)
    except Exception:
        pass        # không ghi được thì chỉ mất ước tính, không được làm hỏng giọng
    return moi


def get_omnivoice_rtf() -> float | None:
    """RTF đã đo được (nhớ qua các lần khởi động). None nếu máy này chưa từng sinh giọng AI."""
    with _omnivoice_rtf_lock:
        _doc_rtf_da_luu()
        return _omnivoice_rtf


def uoc_tinh_thoi_gian_giong_ai(tong_giay_audio: float) -> str | None:
    """Câu mô tả thời gian chờ dự kiến, hoặc None nếu chưa có số đo."""
    rtf = get_omnivoice_rtf()
    if not rtf or rtf < OMNIVOICE_RTF_CANH_BAO:
        return None
    phut = tong_giay_audio * rtf / 60.0
    return (
        f"⏳ Giọng AI trên GPU máy này chạy chậm hơn thời gian thực khoảng {rtf:.0f} lần "
        f"— {tong_giay_audio:.0f} giây lời thoại cần khoảng {phut:.0f} phút xử lý. "
        "Mẹo: bấm \"Nghe thử cả bài\" một lượt rồi làm việc khác; bản đọc đó được lưu đệm "
        "theo từng cảnh nên lúc render không phải sinh lại giây nào."
    )



# ── Đọc số bằng chữ cho OmniVoice ────────────────────────────────────
# Edge-TTS tự đọc "99%" thành "chín mươi chín phần trăm"; OmniVoice thì KHÔNG: nó là
# model tổng hợp thuần, README ghi rõ phải tự chuẩn hoá số trước ("123" → "one hundred
# twenty-three"). Bộ chuẩn hoá kèm theo (`normalize_text=True`) chỉ phục vụ tiếng Trung
# và tiếng Anh; các ngôn ngữ khác rơi về `num2words` — gói này KHÔNG có trong dự án. Nên
# tiếng Việt phải tự lo, nếu không mọi con số trong kịch bản đều đọc sai hoặc bị nuốt.
_VI_DIGITS = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
_VI_SCALES = [(1_000_000_000, "tỷ"), (1_000_000, "triệu"), (1_000, "nghìn")]


def _vi_read_group(n: int, full: bool) -> str:
    """Đọc một nhóm 3 chữ số. `full` = có nhóm lớn hơn đứng trước (phải đọc đủ 'không trăm')."""
    tram, du = divmod(n, 100)
    chuc, dv = divmod(du, 10)
    out = []
    if tram or full:
        out += [_VI_DIGITS[tram], "trăm"]
    if chuc == 0:
        if dv and (tram or full):
            out += ["lẻ", _VI_DIGITS[dv]]
        elif dv:
            out.append(_VI_DIGITS[dv])
    elif chuc == 1:
        out.append("mười")
        if dv == 5:
            out.append("lăm")          # "mười lăm", KHÔNG phải "mười năm" (= 10 năm)
        elif dv:
            out.append(_VI_DIGITS[dv])
    else:
        out += [_VI_DIGITS[chuc], "mươi"]
        if dv == 1:
            out.append("mốt")          # "hai mươi mốt"
        elif dv == 5:
            out.append("lăm")
        elif dv:
            out.append(_VI_DIGITS[dv])
    return " ".join(out)


def vi_number_to_words(n: int) -> str:
    """Số nguyên → chữ tiếng Việt. Âm và số cực lớn đều xử lý được."""
    if n < 0:
        return "âm " + vi_number_to_words(-n)
    if n < 10:
        return _VI_DIGITS[n]
    parts, con_lai, da_doc = [], n, False
    for value, ten in _VI_SCALES:
        if con_lai >= value:
            nhom, con_lai = divmod(con_lai, value)
            parts.append(f"{vi_number_to_words(nhom) if nhom >= 1000 else _vi_read_group(nhom, False)} {ten}")
            da_doc = True
        elif da_doc and con_lai == 0:
            break
    if con_lai:
        parts.append(_vi_read_group(con_lai, da_doc))
    return " ".join(p for p in parts if p).strip()


_VI_SYMBOL_WORDS = [
    (re.compile(r"\s*%"), " phần trăm"),
    (re.compile(r"\s*\$"), " đô la"),
    (re.compile(r"\s+&\s+"), " và "),
    (re.compile(r"\s+\+\s+"), " cộng "),
]
_NUM_RE = re.compile(r"\d[\d.,]*")


def normalize_vi_numbers(text: str) -> str:
    """
    Đổi số và ký hiệu trong văn bản sang chữ đọc được.

    Xử lý cả dấu phân cách nghìn kiểu Việt Nam ("1.000.000") lẫn phần thập phân
    ("3,5" → "ba phẩy năm"). Nhập nhằng "1.000" là một nghìn hay một phẩy không không
    không được phân xử theo luật: nhóm 3 chữ số sau dấu chấm = phân cách nghìn.
    """
    def _doc_so(m: re.Match) -> str:
        raw = m.group(0).rstrip(".,")
        duoi = m.group(0)[len(raw):]          # dấu câu dính đuôi, phải trả lại
        nguyen, thap_phan = raw, ""
        for sep in (",", "."):
            if sep in raw:
                dau, _, sau = raw.rpartition(sep)
                # 3 chữ số sau dấu = phân cách nghìn, ngược lại là thập phân
                if len(sau) != 3 or not dau:
                    nguyen, thap_phan = dau or "0", sau
                break
        nguyen = re.sub(r"[.,]", "", nguyen) or "0"
        try:
            out = vi_number_to_words(int(nguyen))
        except ValueError:
            return m.group(0)
        if thap_phan:
            out += " phẩy " + " ".join(_VI_DIGITS[int(c)] for c in thap_phan if c.isdigit())
        return out + duoi

    text = _NUM_RE.sub(_doc_so, text or "")
    for pattern, word in _VI_SYMBOL_WORDS:
        text = pattern.sub(word, text)
    return re.sub(r"\s{2,}", " ", text).strip()


# ĐÃ XOÁ (chủ ý, đừng dựng lại): bộ cắt mẩu 200 ký tự + gọt lặng librosa + bảng khoảng
# nghỉ tự chế `_TTS_PAUSE_AFTER`. OmniVoice đã tự chia đoạn giữ ngữ cảnh, tự xoá khoảng
# lặng thừa và tự fade hai đầu; lớp thủ công chồng lên chỉ cắt mất phụ âm đầu mỗi mẩu và
# bẻ gãy ngữ điệu. Xem chú thích trong _synthesize_omnivoice.


_whisper_models = {}
_whisper_models_lock = threading.Lock()


def _get_whisper_model(size="base"):
    # transcribe_vietnamese() và chep_loi_theo_cau() mỗi cái chạy trong một
    # asyncio.to_thread riêng — 2 lệnh gọi đầu tiên cùng lúc (2 cảnh của 2 render khác
    # nhau) có thể cùng lọt qua check `size not in _whisper_models` trước khi cái nào
    # kịp ghi, nạp trùng model 2 lần, tốn thêm VRAM vốn đã chật trên GPU 6GB.
    if size in _whisper_models:
        return _whisper_models[size]
    with _whisper_models_lock:
        if size not in _whisper_models:
            import stable_whisper
            logger.info(f"[Whisper] Loading stable-whisper '{size}' model...")
            _whisper_models[size] = stable_whisper.load_model(size)
        return _whisper_models[size]


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
    
    # Đọc số bằng chữ TRƯỚC khi gửi: OmniVoice không có bộ chuẩn hoá cho tiếng Việt
    # (xem normalize_vi_numbers), nên "99%" và "40 năm" trong kịch bản sẽ bị đọc sai
    # hoặc nuốt mất. Edge-TTS tự làm được việc này nên chỉ áp ở nhánh OmniVoice.
    clean_text = normalize_vi_numbers(_normalize_text(text))
    if not clean_text:
        clean_text = "..."

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
        # Giọng clone: lấy giới tính đã lưu trong registry (cùng nguồn với giọng thay
        # thế khi hỏng), không đoán lại bằng một bộ luật khác ở đây.
        gender = get_clone_gender(instruct) if custom_voice else "Nam"
        clean_tokens = ["female" if gender == "Nữ" else "male", "young adult", "moderate pitch"]
    mapped_instruct = ", ".join(clean_tokens)

    def _run_omnivoice_with_prosody():
        import torch
        # Chỉ 1 GPU cho cả process: khoá quanh TOÀN BỘ seed+generate, không chỉ load
        # model. Thiếu khoá thì 2 cảnh của 2 render khác nhau chạy song song (mỗi cảnh
        # qua asyncio.to_thread riêng) sẽ đè torch.manual_seed(42) của nhau NGAY TRƯỚC
        # generate() của bên kia — voice timbre trôi giữa các cảnh trong cùng video.
        with _omnivoice_lock:
            # Đặt cố định seed để OmniVoice giữ đúng 1 chất giọng (timbre) xuyên suốt tất cả cảnh
            torch.manual_seed(42)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(42)

            model = _get_omnivoice_model()

            # Đường dẫn cache giọng mẫu (Reference Audio) để Cloning
            preview_dir = VOICES_PREVIEW_DIR
            os.makedirs(preview_dir, exist_ok=True)
            ref_wav_path = os.path.join(preview_dir, f"{instruct}_ref.wav")
            ref_text = "Chào bạn, đây là giọng đọc tham khảo để đồng bộ video."
            canh_bao = None

            if custom_voice:
                # Giọng clone cá nhân: file mẫu do user upload (bắt buộc tồn tại) + transcript riêng
                if not os.path.exists(ref_wav_path) or os.path.getsize(ref_wav_path) < 1000:
                    raise RuntimeError(f"Thiếu file mẫu giọng clone: {ref_wav_path}. Hãy upload lại mẫu giọng.")
                # CẶP (ref_audio, ref_text) phải khớp nhau, nếu không giọng đọc ra vô nghĩa.
                # Xem ensure_clone_ref_text — nó tự chép lời file mẫu và sửa nếu lệch.
                checked, canh_bao = ensure_clone_ref_text(instruct, ref_wav_path)
                ref_text = checked or ref_text
            elif not os.path.exists(ref_wav_path) or os.path.getsize(ref_wav_path) < 1000:
                # Nếu chưa có giọng mẫu, tạo 1 bản zero-shot (identity thuần, KHÔNG kèm emotion) và lưu lại
                logger.info(f"[OmniVoice] Tạo giọng mẫu Zero-shot cho {instruct}...")
                ref_audio_arr = model.generate(
                    text=ref_text, instruct=mapped_instruct, language=OMNIVOICE_LANG
                )
                sf.write(ref_wav_path, ref_audio_arr[0], 24000)

            # Số trong ref_text cũng phải là chữ: file mẫu đọc "một nghìn chín trăm bốn mươi
            # ba", nếu transcript ghi "1943" thì cặp chữ↔tiếng lệch ngay tại con số đó.
            ref_text = normalize_vi_numbers(ref_text)

            # MỘT lần gọi cho cả cảnh — KHÔNG tự cắt câu, KHÔNG tự gọt lặng nữa.
            # LỖI CŨ: pipeline tự tách câu, tự cắt mẩu 200 ký tự, gọi generate() cho từng
            # mẩu, gọt lặng bằng librosa rồi chèn lại khoảng nghỉ tự chế. Cả bốn việc đó
            # OmniVoice đã làm sẵn và làm đúng hơn:
            #   • tự chia đoạn khi audio ước tính vượt 30s (audio_chunk_duration=15s), giữ
            #     ngữ cảnh xuyên mẩu — cắt tay thì mỗi mẩu là một lần "vào giọng" mới;
            #   • postprocess_output=True đã xoá khoảng lặng giữa (>500ms) và hai đầu;
            #   • fade_duration/pad_duration=0.1s làm mềm hai đầu — librosa top_db=40 ăn
            #     đúng vào phần fade đó, cụt phụ âm đầu của MỌI mẩu.
            # File mẫu chỉ cần mã hoá MỘT lần cho cả video — xem get_voice_clone_prompt.
            prompt = get_voice_clone_prompt(model, instruct, ref_wav_path, ref_text)
            nguon_giong = (
                {"voice_clone_prompt": prompt} if prompt is not None
                else {"ref_audio": ref_wav_path, "ref_text": ref_text}
            )
            arr = model.generate(
                text=clean_text,
                instruct=mapped_instruct,
                language=OMNIVOICE_LANG,
                num_step=OMNIVOICE_NUM_STEP,
                **nguon_giong,
            )
            final_audio = np.asarray(arr[0], dtype=np.float32)
        if final_audio.size == 0:
            logger.warning(f"[OmniVoice] Không sinh được audio cho text: '{clean_text}'. Trả về im lặng 1s.")
            final_audio = np.zeros(OMNIVOICE_SR, dtype=np.float32)
        return final_audio, canh_bao

    try:
        _t_bat_dau = time.monotonic()
        audio, ref_warning = await asyncio.to_thread(_run_omnivoice_with_prosody)
        rtf = _ghi_nhan_rtf(time.monotonic() - _t_bat_dau, len(audio) / OMNIVOICE_SR)
        if rtf and rtf >= OMNIVOICE_RTF_CANH_BAO:
            logger.info(
                "[OmniVoice] Tốc độ thực đo được: RTF %.1f (%.0f giây xử lý cho mỗi giây audio).",
                rtf, rtf,
            )
        if ref_warning and warning_callback:
            try:
                await warning_callback(ref_warning)
            except Exception:
                pass
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
        # Giọng thay thế phải ĐÚNG GIỚI TÍNH với giọng người dùng đã chọn: tra registry
        # cho giọng clone, đọc token instruct cho giọng preset (xem resolve_fallback_voice).
        fallback_voice, fallback_name, gender = resolve_fallback_voice(instruct)
        display = (custom_voice or {}).get("name") or instruct
        fallback_msg = (
            f"⚠️ Giọng AI '{display}' không dùng được ({type(e).__name__}: {e}). "
            f"Đang đọc tạm bằng giọng tiêu chuẩn {fallback_name} ({gender})."
        )
        logger.warning(f"[OmniVoice] {fallback_msg}")
        # Broadcast cảnh báo cho user qua WebSocket (nếu có callback)
        if warning_callback:
            try:
                await warning_callback(fallback_msg)
            except Exception:
                pass
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

    # Breathing đã DI CHUYỂN sang video_service.render_final_video (1 lần ở đầu video).
    # Ở đây chỉ sinh giọng thuần, không can thiệp audio.
    # Lý do: breathe ghép vào MỖI scene gây tiếng thở lặp ~3-4s/lần — nghe như "quoẹt".
    # Fix: ghép 1 lần DUY NHẤT vào audio_placements[0] ở video_service.

    # Lưu cache (file audio + metadata duration/word_boundaries) cho lần render sau
    try:
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            _tts_cache.set_media("tts", output_path, **cache_params)
            _tts_cache.set("tts_meta", {"duration": dur, "word_boundaries": wbs}, **cache_params)
            _index_voice_cache_entry(voice, "tts_meta", "tts", cache_params)
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
            # gender THẬT (Nam/Nữ) chứ không phải nhãn "Clone": giao diện xếp nhóm theo
            # trường này, và nó cũng chính là thứ quyết định giọng đọc thay thế khi
            # OmniVoice hỏng — hai chỗ phải nhìn cùng một con số.
            # Tính TRỰC TIẾP từ `cv` đã có trong tay (cùng logic get_clone_gender), thay
            # vì gọi get_clone_gender(cv["id"]) → get_custom_voice() → _load_custom_voices()
            # đọc + parse lại NGUYÊN file JSON cho MỖI giọng clone trong vòng lặp này.
            "gender": _normalize_gender(cv.get("gender")) or _gender_from_name(cv.get("name", "")) or "Nữ",
            "is_clone": True,
            "raw_name": cv.get("name", cv["id"]),
            "ref_text": cv.get("ref_text", ""),
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
        "whisper_align_loaded": "base" in _whisper_models,
        "custom_voices": len(_load_custom_voices()),
        "cuda": False,
        "gpu_name": None,
        # Tốc độ THẬT đo được trên máy này, để UI nói con số cụ thể thay vì "có thể chậm".
        "omnivoice_rtf": get_omnivoice_rtf(),
        "omnivoice_num_step": OMNIVOICE_NUM_STEP,
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
        await asyncio.to_thread(_get_whisper_model, "base")
        logger.info("[Warmup] Whisper alignment model sẵn sàng.")
    except Exception as e:
        logger.warning(f"[Warmup] stable-whisper không khả dụng: {e}")
