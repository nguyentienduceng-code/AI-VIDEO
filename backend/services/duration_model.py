"""
duration_model.py — NGUỒN CHÂN LÝ DUY NHẤT cho câu hỏi "đoạn chữ này đọc mất bao lâu?"

VÌ SAO CẦN
----------
Trước file này, cùng một câu hỏi được trả lời bằng BA công thức khác nhau nằm ở ba nơi:

  main.py:_estimate_scene_duration   words * 0.38 + 0.7    → 2.6 từ/giây
  gemini_service                     words / 3.0           → 3.0 từ/giây
  ScriptEditor.jsx (cảnh báo UI)     12 từ/cảnh            → ngầm định 3.0

Chênh 2.6 với 3.0 là 15% — trên video 60 giây là lệch 9 giây. Hệ quả thực tế: thanh
cảnh báo trên UI báo "vừa đủ" trong khi bộ chọn clip stock đã tính ra con số khác hẳn,
và không con số nào khớp với thời lượng video ra lò.

VÌ SAO PHẢI TỰ HỌC
------------------
Tốc độ đọc thật phụ thuộc giọng (NamMinh khác HoaiMy), phụ thuộc kiểu chữ (số liệu và
tên riêng đọc chậm hơn văn xuôi), và phụ thuộc cả phiên bản Edge-TTS. Một hằng số gõ
tay không thể đúng cho mọi trường hợp — mà pipeline này thì SẴN có số đo thật: mỗi lần
synthesize_speech() chạy là một mẫu (số từ, thời lượng thật). Trước đây số đo đó chỉ
dùng dựng phụ đề rồi vứt. Giờ nó được ghi lại và kéo dần ước lượng về đúng thực tế của
chính giọng người dùng đang dùng.

CHUẨN HOÁ THEO RATE
-------------------
Mẫu đo được quy về mốc rate "+0%" trước khi ghi (đọc nhanh 20% thì wps cao hơn 20%),
nên MỌI mẫu của cùng một giọng đều dồn vào một hồ sơ duy nhất, hội tụ nhanh hơn nhiều
so với việc tách hồ sơ riêng cho từng cặp (giọng, tốc độ).

KHÔNG NHẦM VỚI motion_effects.build_scene_timeline() / build_timeline_from_narration()
----------------------------------------------------------------------------------------
Đây là 2 "nguồn sự thật" khác nhau cho 2 câu hỏi khác nhau, không phải bản trùng lặp:
  • duration_model (file này) trả lời "ước lượng bao lâu TRƯỚC KHI có audio thật" — dùng
    để lên kế hoạch (chọn clip stock, cảnh báo độ dài kịch bản trên UI...).
  • motion_effects.build_scene_timeline/build_timeline_from_narration trả lời "audio
    TTS đã sinh ra rồi, cảnh này thực sự dài bao nhiêu trên timeline" — dựa trên
    word_boundaries đo được thật, không phải ước lượng. Đây là con số CUỐI đi vào
    scene_assets["duration"] mà render thật sự dùng.
Không hợp nhất hai hàm này: một cái chạy TRƯỚC TTS (chỉ có chữ), một cái chạy SAU TTS
(đã có audio thật) — thời điểm gọi khác nhau nên không thể chỉ còn một hàm.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading

logger = logging.getLogger(__name__)

# Tốc độ khởi điểm khi chưa có mẫu nào — giữ đúng con số đã đo tay trên pipeline này
# (xem ghi chú lịch sử ở gemini_service.VIETNAMESE_WORDS_PER_SECOND).
BASE_WPS = 3.0

# Biên tin cậy: mẫu nằm ngoài khoảng này gần như chắc chắn là rác (TTS lỗi trả file
# rỗng, hoặc text toàn ký hiệu) — ghi vào chỉ làm hỏng hồ sơ.
_MIN_VALID_WPS = 1.2
_MAX_VALID_WPS = 7.0
_MIN_WORDS_FOR_SAMPLE = 4   # câu quá ngắn: tỉ lệ khoảng lặng đầu/cuối lấn át, đo không chuẩn

# Trung bình động: mỗi mẫu mới kéo hồ sơ đi 1/n, chặn ở 50 để hồ sơ không bao giờ
# "đông cứng" — Edge-TTS đổi giọng theo phiên bản thì vẫn trôi theo được.
_MAX_WEIGHT = 50

_BREAK_RE = re.compile(r'<break\s+time\s*=\s*"([\d.]+)\s*(ms|s)"\s*/?>', re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_RATE_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*%\s*$")

_lock = threading.Lock()
_profile_cache: dict | None = None


def _profile_path() -> str:
    # Import trong hàm: config.py nạp .env và dựng thư mục lúc import, không nên kéo
    # theo chỉ để đọc một đường dẫn ở thời điểm module này được nạp.
    from config import DATA_DIR

    return os.path.join(DATA_DIR, "timing_profile.json")


def _empty_profile() -> dict:
    return {"version": 1, "voices": {}, "global": {"wps": BASE_WPS, "samples": 0}}


def _load() -> dict:
    global _profile_cache
    if _profile_cache is not None:
        return _profile_cache
    try:
        with open(_profile_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "voices" in data:
            _profile_cache = data
            return _profile_cache
    except (OSError, json.JSONDecodeError):
        pass  # chưa có file, hoặc file hỏng → bắt đầu lại từ mặc định
    _profile_cache = _empty_profile()
    return _profile_cache


def _save(profile: dict) -> None:
    """Ghi nguyên tử: ghi file tạm rồi đổi tên, để một lần tắt máy giữa chừng không để
    lại file JSON cụt khiến lần khởi động sau mất sạch hồ sơ đã học."""
    path = _profile_path()
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError as e:
        # Không ghi được hồ sơ KHÔNG được phép làm hỏng job render đang chạy.
        logger.warning(f"[DurationModel] Không lưu được hồ sơ tốc độ đọc: {e}")


# ── Phân tích văn bản ────────────────────────────────────────────────────────
def parse_rate(rate: str | None) -> float:
    """"+15%" → 1.15. Giá trị lạ → 1.0 (coi như tốc độ chuẩn)."""
    if not rate:
        return 1.0
    m = _RATE_RE.match(str(rate))
    if not m:
        return 1.0
    percent = float(m.group(1))
    # Chặn ở -90%: rate âm sâu hơn sẽ cho hệ số ~0 và làm phép chia nổ tung.
    return max(0.1, 1.0 + percent / 100.0)


def break_seconds(text: str) -> float:
    """Tổng thời gian các thẻ <break time="..."/> — đây là khoảng lặng CÓ THẬT trong
    file audio, phải cộng vào thời lượng nhưng KHÔNG được tính là thời gian đọc chữ."""
    total = 0.0
    for value, unit in _BREAK_RE.findall(text or ""):
        try:
            v = float(value)
        except ValueError:
            continue
        total += v / 1000.0 if unit.lower() == "ms" else v
    return total


def count_words(text: str) -> int:
    """Đếm từ sau khi bỏ MỌI thẻ đánh dấu — thẻ là chỉ dẫn nhịp đọc, không ai đọc chúng
    thành tiếng, đếm vào sẽ thổi phồng ước lượng."""
    cleaned = _TAG_RE.sub(" ", text or "").strip()
    return len(cleaned.split()) if cleaned else 0


# ── Tra cứu & ước lượng ──────────────────────────────────────────────────────
def words_per_second(voice: str | None = None, rate: str | None = None) -> float:
    """Tốc độ đọc kỳ vọng (từ/giây) cho một giọng ở một tốc độ.

    Ưu tiên hồ sơ riêng của giọng đó; chưa đủ mẫu thì lùi về trung bình toàn cục; chưa
    có gì cả thì dùng BASE_WPS.
    """
    profile = _load()
    entry = profile["voices"].get(voice or "", {})
    if entry.get("samples", 0) >= 3:
        base = float(entry["wps"])
    elif profile["global"].get("samples", 0) >= 3:
        base = float(profile["global"]["wps"])
    else:
        base = BASE_WPS
    return max(0.5, base * parse_rate(rate))


def estimate_duration(
    text: str,
    voice: str | None = None,
    rate: str | None = None,
    pause_after_ms: float = 0.0,
) -> float:
    """Thời lượng dự kiến (giây) của một khối lời thoại, ĐÃ tính cả khoảng lặng.

    Đây là hàm mà mọi nơi phải gọi — main.py (chọn clip stock), gemini_service (ước
    lượng tổng), và API cho UI. Muốn đổi cách tính thì đổi ở đây, một lần.
    """
    words = count_words(text)
    if words == 0:
        return break_seconds(text) + (pause_after_ms or 0) / 1000.0
    speech = words / words_per_second(voice, rate)
    return speech + break_seconds(text) + (pause_after_ms or 0) / 1000.0


# ── Học từ số đo thật ────────────────────────────────────────────────────────
def record_observation(
    text: str,
    actual_duration: float,
    voice: str | None = None,
    rate: str | None = None,
) -> None:
    """Ghi nhận một lần TTS thật. Gọi ngay sau synthesize_speech().

    KHÔNG BAO GIỜ ném lỗi ra ngoài: đây là chức năng phụ trợ, hỏng hồ sơ tốc độ đọc thì
    ước lượng kém đi một chút, còn làm chết job render thì mất cả video.
    """
    try:
        words = count_words(text)
        speech_time = float(actual_duration) - break_seconds(text)
        if words < _MIN_WORDS_FOR_SAMPLE or speech_time <= 0.3:
            return

        # Quy về mốc rate +0% để mọi tốc độ dồn chung một hồ sơ.
        observed = (words / speech_time) / parse_rate(rate)
        if not (_MIN_VALID_WPS <= observed <= _MAX_VALID_WPS):
            logger.debug(f"[DurationModel] Bỏ mẫu bất thường: {observed:.2f} từ/giây")
            return

        with _lock:
            profile = _load()
            for bucket in (profile["voices"].setdefault(voice or "unknown", {"wps": BASE_WPS, "samples": 0}),
                           profile["global"]):
                n = min(int(bucket.get("samples", 0)) + 1, _MAX_WEIGHT)
                wps = float(bucket.get("wps", BASE_WPS))
                bucket["wps"] = round(wps + (observed - wps) / n, 4)
                bucket["samples"] = int(bucket.get("samples", 0)) + 1
            _save(profile)
    except Exception as e:
        logger.debug(f"[DurationModel] Bỏ qua lỗi khi ghi mẫu: {e}")


def profile_summary(voice: str | None = None, rate: str | None = None) -> dict:
    """Số liệu cho UI: tốc độ đang dùng + đã học được từ bao nhiêu mẫu."""
    profile = _load()
    entry = profile["voices"].get(voice or "", {})
    return {
        "words_per_second": round(words_per_second(voice, rate), 3),
        "base_words_per_second": round(words_per_second(voice, None), 3),
        "voice_samples": int(entry.get("samples", 0)),
        "global_samples": int(profile["global"].get("samples", 0)),
        "is_learned": int(entry.get("samples", 0)) >= 3 or int(profile["global"].get("samples", 0)) >= 3,
    }


def reset_cache() -> None:
    """Buộc đọc lại hồ sơ từ đĩa ở lần dùng kế tiếp (dùng trong test)."""
    global _profile_cache
    with _lock:
        _profile_cache = None
