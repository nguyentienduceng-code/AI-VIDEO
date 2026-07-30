"""
video_service.py
-----------------
NÂNG CẤP V2:
1. Đa tỉ lệ khung hình: 9:16 (TikTok/Reels), 16:9 (YouTube), 1:1 (Instagram).
2. BGM mixing: overlay nhạc nền dưới giọng đọc (volume ~15%).
3. Slideshow mode: ảnh + BGM, không TTS, Ken Burns mạnh, crossfade dài.
4. Quiz mode: text overlay lớn hơn, màu nhấn khác.
5. Giữ nguyên tất cả fix nợ kỹ thuật V1 (MoviePy v2, crossfade, subtitle burn-in).
"""

from __future__ import annotations

import logging
import os
import random
import re
from typing import List, Optional, TypedDict
import datetime as dt

from moviepy import (
    VideoFileClip,
    ImageClip,
    CompositeVideoClip,
)

logger = logging.getLogger(__name__)

# ── Kích thước khung hình theo aspect ratio ──────────────────────────
ASPECT_RATIO_SIZES = {
    "9:16": (1080, 1920),   # TikTok/Reels (dọc)
    "16:9": (1920, 1080),   # YouTube (ngang)
    "1:1":  (1080, 1080),   # Instagram (vuông)
}

FPS = 30
CROSSFADE_DURATION = 0.4       # giây — crossfade mượt giữa 2 cảnh (tăng từ 0.2 lên 0.4 cho tự nhiên hơn)
SLIDESHOW_CROSSFADE = 0.8      # giây — crossfade dài hơn cho slideshow
AUDIO_FADEOUT_DURATION = 0.05  # giây để fade-out cuối mỗi cảnh, chống "pop".
                               # Giảm từ 0.12 xuống 0.05 để không bị "cắn" vào chữ cuối gây "khựng".
SLIDESHOW_SCENE_DURATION = 5.0 # giây — mỗi ảnh hiển thị bao lâu trong slideshow
# = hook_engine.SLOT_DURATION (2.0s quay) + 2.5s pha Quote. Kéo pha quay dài thêm 1.0s
# thì hằng số này phải tăng đúng 1.0s, nếu không pha Quote bị cắt cụt mất 1 giây.
HOOK_CAROUSEL_DURATION = 4.5   # giây — độ dài clip hook carousel_quote chèn đầu video
# Giọng đọc vào SAU khi trục quay chốt xong. Trục quay chạy 0→2.0s, tiếng "chốt" (ding)
# nổ ở 2.0s; 2.35s là lúc phần đanh nhất của tiếng chốt đã tắt.
# LÝ DO: trước đây giọng đọc bắt đầu ngay 0.0s nên câu dẫn đầu video bị tiếng máy xèng
# đè lên toàn bộ — nghe lùng bùng đúng đoạn quan trọng nhất để giữ chân người xem.
# Phần hình KHÔNG bị đẩy lùi: hook vẫn là lớp phủ 4.5s, chỉ mốc vào tiếng dời đi.
HOOK_NARRATION_LEAD = 2.35

# ── NGUỒN CHÂN LÝ DUY NHẤT cho thời lượng + độ dời narration của MỌI hook ──────
# Trước đây mỗi hook mới thêm vào (blackout_question, typewriter_quote,
# breathing_vignette) phải tự khai báo lại thời lượng ở main.py (điều kiện dời
# start_time) VÀ ở video_service (dựng clip + FastAssembly) — 2 chỗ tách rời, không
# gì ép chúng khớp nhau. Hệ quả thực tế: main.py chỉ dời start_time cho
# "carousel_quote", 3 hook mới không hề dời giọng đọc; và FastAssembly hard-code
# hook_duration=HOOK_CAROUSEL_DURATION cho MỌI loại hook bất kể loại nào đang chạy.
# Từ giờ: thêm hook mới CHỈ cần thêm 1 dòng ở dict này — main.py và video_service
# đều tra cứu từ đây, không thể "quên sửa 1 trong N chỗ" được nữa.
HOOK_EFFECTS = {
    "carousel_quote":    {"duration": HOOK_CAROUSEL_DURATION, "narration_lead": HOOK_NARRATION_LEAD},
    "blackout_question": {"duration": 1.5, "narration_lead": 1.5},
    "typewriter_quote":  {"duration": 2.5, "narration_lead": 2.5},
    # outro_duration: đo riêng cho outro, luôn NGẮN HƠN bản hook (xem resolve_outro_timing).
    # Hook cần đủ dài để GIỮ CHÂN người xem trước khi vào nội dung; outro thì ngược lại —
    # người xem đã sẵn sàng lướt đi, càng vòng vo càng mất người. Chỉ effect có pha
    # "build-up" thấy rõ (loang sáng) mới cần khoá riêng; camera_shutter/cyber_glitch/
    # vintage_film_burn vốn đã gọn (2.0-2.5s) nên giữ nguyên.
    "breathing_vignette": {"duration": 3.0, "narration_lead": 3.0, "outro_duration": 2.0},
    "camera_shutter":    {"duration": 2.0, "narration_lead": 2.0},
    "cyber_glitch":      {"duration": 2.0, "narration_lead": 2.0},
    "vintage_film_burn": {"duration": 2.5, "narration_lead": 2.5},
    # CHỈ DÙNG CHO OUTRO (dropdown Hook không hiện lựa chọn này) — xem chú thích ở
    # build_cta_card_hook trong hook_engine.py. narration_lead vô nghĩa với outro
    # (resolve_outro_timing() chỉ đọc "duration") nhưng vẫn khai báo cho khớp shape.
    "cta_card":          {"duration": 2.4, "narration_lead": 2.4},
}

# ── Thời lượng ĐỘNG cho hook có chữ, theo độ dài hook_quote ──────────────────
# Chỉ áp dụng cho blackout_question/typewriter_quote: đây là 2 loại hook mà TOÀN BỘ
# nội dung hiển thị chỉ là dòng chữ đó — chữ dài mà giữ cứng 1.5-2.5s thì đọc không
# kịp, chữ ngắn (hoặc rỗng — dù rỗng đã bị chặn ở main.py, vẫn giữ sàn ở đây cho an
# toàn) thì ngâm video vô ích.
# KHÔNG áp dụng carousel_quote: thời lượng của nó khoá chặt với nhịp trục quay Máy
# Xèng + độ dài file SFX reel (xem hook_engine.SLOT_DURATION và bảng "4 chỗ phải
# khớp" ở đầu hook_engine.py) — đổi động sẽ làm lệch hình/tiếng ngay.
# KHÔNG áp dụng breathing_vignette: hiệu ứng này không có chữ, chỉ có ảnh bìa.
DYNAMIC_DURATION_HOOKS = {"blackout_question", "typewriter_quote"}
HOOK_MIN_DURATION = 1.2   # giây — sàn: chữ rất ngắn vẫn cần đủ thời gian để mắt kịp đọc
HOOK_MAX_DURATION = 4.0   # giây — trần: chữ rất dài cũng không kéo hook dài vô hạn
HOOK_SEC_PER_CHAR = 0.06  # giây/ký tự — xấp xỉ tốc độ đọc phụ đề thông thường

# Bản RÚT GỌN của 3 hằng số trên, dùng khi 2 hook động này chạy ở OUTRO (is_outro=True).
# Ở outro, typewriter_quote hiện TRỌN câu ngay (instant=True, xem hook_engine.py) thay vì
# gõ dần — nghĩa là 100% thời lượng là thời gian ĐỌC, không cần cộng thêm thời gian "gõ"
# như công thức hook gốc. Rút cả sàn/trần/tốc độ để outro không lê thê.
HOOK_MIN_DURATION_OUTRO = 1.0
HOOK_MAX_DURATION_OUTRO = 3.0
HOOK_SEC_PER_CHAR_OUTRO = 0.045


def resolve_hook_timing(hook_type: str, hook_quote: str, is_outro: bool = False) -> dict | None:
    """
    Trả về {"duration", "narration_lead"} cho 1 hook_type — NGUỒN CHÂN LÝ DUY NHẤT,
    dùng ở cả main.py (dời start_time) lẫn video_service (dựng clip + FastAssembly)
    để 2 nơi không bao giờ lệch nhau (xem lịch sử bug ở comment HOOK_EFFECTS trên).

    `is_outro=True`: dùng công thức rút gọn (HOOK_*_OUTRO) cho 2 hook có thời lượng
    động — xem chú thích ở các hằng số đó. Không ảnh hưởng gì khi gọi cho hook mở đầu.

    Trả None nếu hook_type không tồn tại (vd "none" hoặc giá trị rác) — caller tự
    hiểu là "không có hook" và bỏ qua toàn bộ narration lead / clip overlay.
    """
    base = HOOK_EFFECTS.get(hook_type)
    if base is None:
        return None
    if hook_type not in DYNAMIC_DURATION_HOOKS:
        return dict(base)

    text_len = len((hook_quote or "").strip())
    if is_outro:
        duration = max(HOOK_MIN_DURATION_OUTRO, min(HOOK_MAX_DURATION_OUTRO, text_len * HOOK_SEC_PER_CHAR_OUTRO + 0.3))
    else:
        duration = max(HOOK_MIN_DURATION, min(HOOK_MAX_DURATION, text_len * HOOK_SEC_PER_CHAR + 0.5))
    # narration_lead == duration: 2 hook này chỉ có 1 pha duy nhất (hiện chữ rồi cắt
    # thẳng sang Cảnh 1), không có pha "im lặng riêng" như carousel_quote (trục quay
    # xong mới tới pha Quote) nên không cần tách 2 giá trị khác nhau.
    return {"duration": duration, "narration_lead": duration}


def resolve_outro_text(outro_text: str = "", cta_text: str = "", hook_text: str = "") -> str:
    """
    Chữ hiển thị ở phần đuôi video — NGUỒN CHÂN LÝ DUY NHẤT, đối xứng với
    resolve_outro_timing().

    Thứ tự ưu tiên: user gõ tay > CTA do Gemini sinh > câu hook mở đầu.

    VÌ SAO PHẢI CÓ HÀM RIÊNG: cùng một phép chọn này trước đây được gõ lại BA lần ở ba
    nơi (`main.py` lúc tính tổng thời lượng, `video_service` lúc dựng clip outro, và
    endpoint `/api/timing-profile` để UI hiện trước con số). Chính comment cũ ở main.py
    đã phải dặn "PHẢI khớp từng chữ với cách video_service chọn nguồn chữ" — tức là
    đang dựa vào việc người sửa nhớ sửa đủ ba chỗ. Với 2 hiệu ứng outro có thời lượng
    ĐỘNG theo độ dài chữ (blackout_question/typewriter_quote), lệch nguồn chữ là lệch
    luôn thời lượng: UI hiện một đằng, video ra một nẻo.

    VÌ SAO cta_text ĐỨNG TRƯỚC hook_text: `cta_text` là câu kêu gọi hành động Gemini
    sinh riêng cho đuôi video (xem prompt ở gemini_service.py). Trước đây nó là FIELD
    CHẾT — có trong model, frontend gửi lên, nhưng không nơi nào đọc — nên outro rơi
    thẳng về `hook_text`, tức đem CÂU MỞ ĐẦU ra làm lời chốt. Người xem đã nghe câu đó
    ở giây đầu tiên rồi.

    Trả "" khi cả ba đều rỗng; `build_cta_card_hook` tự ẩn dòng chữ khi không có gì.
    """
    for ung_vien in (outro_text, cta_text, hook_text):
        if ung_vien and str(ung_vien).strip():
            return str(ung_vien).strip()
    return ""


def resolve_outro_timing(outro_type: str, outro_text: str = "") -> dict | None:
    """
    Thời lượng phần đuôi video — NGUỒN CHÂN LÝ DUY NHẤT, đối xứng với resolve_hook_timing.

    VÌ SAO PHẢI CÓ: Outro Engine làm video DÀI THÊM (`final_duration += outro_duration`),
    nhưng main.py tính `video_total_duration` chỉ từ scene_assets nên không hề biết. Con số
    đó đi thẳng vào thanh tiến trình FFmpeg (`color=...:d={total_duration}`), nên thanh vàng
    chạy hết 100% RỒI BIẾN MẤT trước khi outro kết thúc — người xem thấy nó hụt mất mấy giây
    cuối. Đây đúng là loại lệch mà resolve_hook_timing() đã được tạo ra để dập cho đầu video;
    đuôi video cần bản đối xứng, thay vì để video_service tự cộng thầm.

    OUTRO KHÔNG DÙNG Y NGUYÊN THỜI LƯỢNG HOOK: hook cần đủ dài để giữ chân người xem
    TRƯỚC KHI vào nội dung; outro thì ngược lại, người xem đã sẵn sàng lướt đi. 2 hook
    động (blackout_question/typewriter_quote) dùng công thức rút gọn riêng qua
    `is_outro=True`; các hiệu ứng tĩnh tra khoá "outro_duration" nếu có khai báo trong
    HOOK_EFFECTS (không có thì dùng lại "duration" như cũ).

    Trả None khi không có outro, để caller bỏ qua toàn bộ nhánh này.
    """
    if not outro_type or outro_type == "none":
        return None
    # carousel_quote KHÔNG lấy theo HOOK_EFFECTS: clip máy xèng có độ dài cố định riêng.
    if outro_type == "carousel_quote":
        return {"duration": HOOK_CAROUSEL_DURATION}
    if outro_type in DYNAMIC_DURATION_HOOKS:
        base = resolve_hook_timing(outro_type, outro_text, is_outro=True)
        return {"duration": base["duration"]} if base else None
    base = HOOK_EFFECTS.get(outro_type)
    if base is None:
        return None
    return {"duration": base.get("outro_duration", base["duration"])}


# ── Thư viện tiếng trục quay cho Hook Máy Xèng ──────────────────────
# Thêm tiếng mới: chạy `python tools/fit_hook_sfx.py <file tải về> --name <id>`,
# công cụ đó tự cắt/chuẩn hoá rồi ghi vào assets/sfx/reel_<id>.wav; sau đó khai báo
# thêm 1 dòng ở đây và 1 dòng trong frontend/src/constants.js (HOOK_REEL_SOUNDS).
HOOK_REEL_SOUNDS = {
    "tick_wood":     "reel_spin.wav",             # mặc định — tiếng gõ khớp từng bìa lướt qua
    "arcade_8bit":   "reel_spin_v1_arcade.wav",   # bản 8-bit cũ
    "money_counter": "reel_money_counter.wav",    # tiếng máy đếm tiền (user tự nạp)
    "impact_boom":   "impact_boom.mp3",          # 3.1s — cú đánh ở 0-1s rồi tắt dần, đuôi tự nhiên
    "typewriter_fast": "typewriter_fast.mp3",    # 8.1s — vòng lặp gõ, đã cắt theo độ dài chữ
    # Ba tiếng dưới đây dùng bản .wav ĐÃ CẮT, không dùng .mp3 gốc. Bản gốc vẫn nằm cạnh
    # làm master để cắt lại được (cắt từ .wav đã cắt thì mất chất lượng vĩnh viễn).
    # Cắt bằng: python tools/fit_hook_sfx.py assets/sfx/<x>.mp3 --name <x> --duration <n> --out <x>.wav
    "cinematic_swell": "cinematic_swell.wav",    # 6.0s → 4.0s: bỏ 2.2s im lặng đầu file
    "ambient_mystic": "ambient_mystic.wav",      # 19.7s → 4.0s: vốn là NHẠC NỀN, không phải điểm nhấn
    "camera_shutter": "camera_shutter.wav",      # 4.4s → 3.0s: giữ trọn cụm click, không cắt giữa chừng
    "digital_glitch": "digital_glitch.mp3",      # 2.0s — vừa khít cửa sổ
    "film_projector": "film_projector.mp3",      # 2.2s — vừa khít cửa sổ
    "cta_chime": "bell.wav",                     # 2.0s — tiếng chuông reo cho card CTA
    "cta_pop":   "pop.wav",                      # 1.97s — tiếng bụp vui tươi, thay thế
}

# Tiếng "ding" chốt cuối trục quay carousel_quote từng CỐ ĐỊNH "ding.wav" bất kể
# reel_key người dùng chọn — chọn reel "arcade_8bit" (8-bit retro) vẫn nghe đúng tiếng
# chuông ding "sang trọng" mặc định, lệch hẳn chất âm với tiếng quay 8-bit vừa nghe.
# ding_v1_arcade.wav đã có sẵn trong kho (đo mean_volume -12.5dB, lệch ding.wav gốc
# đúng 0.8dB — dùng chung hệ số cân bằng "_ding", không cần thêm khoá riêng).
DING_VARIANTS = {"arcade_8bit": "ding_v1_arcade.wav"}
DEFAULT_DING = "ding.wav"
DEFAULT_HOOK_REEL = "tick_wood"

# Hiệu ứng nào được phép dùng tiếng nào — PHẢI khớp HOOK_SFX_OPTIONS bên
# frontend/src/constants.js (tests/test_hook_sfx.py đối chiếu hai bên).
#
# VÌ SAO CẦN DANH SÁCH TRẮNG: các nhánh hiệu ứng đọc thẳng
# `HOOK_REEL_SOUNDS.get(reel_key, <tên file gõ tay>)`. Fallback chỉ nổ khi reel_key
# KHÔNG phải khoá hợp lệ — nhưng ca hỏng thật lại là reel_key HỢP LỆ mà SAI hiệu ứng:
# `hook_reel_sfx` mặc định của model là "tick_wood", nên một request chọn
# hook_effect="camera_shutter" mà không đụng tới ô âm thanh sẽ phát TIẾNG MÁY XÈNG cho
# cú bấm máy ảnh. Giao diện có chặn (resolveValidHookSfx) nhưng backend thì không, và
# preset cũ / gọi API trực tiếp đi thẳng qua.
HOOK_EFFECT_SOUNDS = {
    "carousel_quote":    ("tick_wood", "money_counter", "arcade_8bit"),
    "blackout_question": ("impact_boom",),
    "typewriter_quote":  ("typewriter_fast",),
    "breathing_vignette": ("cinematic_swell", "ambient_mystic"),
    "camera_shutter":    ("camera_shutter",),
    "cyber_glitch":      ("digital_glitch",),
    "vintage_film_burn": ("film_projector",),
    "cta_card":          ("cta_chime", "cta_pop"),
}

# Tiếng mở màn/kết thúc là ĐIỂM NHẤN, không phải nền nhạc. Nó được ngân thêm chừng này
# giây qua mốc kết thúc hiệu ứng (đuôi vang tự nhiên — cắt cụt một cú impact nghe rất
# giả), nhưng không hơn.
#
# LỖI CŨ: chỉ typewriter được cắt, phần còn lại thả tự do. Đo trên chính kho tiếng của
# dự án: impact_boom 3.1s trên cửa sổ 1.5s, camera_shutter 4.4s trên 2.0s,
# cinematic_swell 6.0s trên 3.0s, và ambient_mystic 19.7s trên 3.0s — tức gần 17 GIÂY
# tiếng nền đè lên lời thoại mở đầu, đúng đoạn quan trọng nhất để giữ chân người xem.
HOOK_SFX_TAIL = 1.0


def resolve_effect_sfx(effect: str, reel_key: str) -> str | None:
    """
    Đường dẫn tiếng động HỢP LỆ cho `effect`, hoặc None nếu không phát gì.

    Khoá lạ hoặc khoá của hiệu ứng khác đều bị kéo về lựa chọn đầu tiên của chính hiệu
    ứng đang chạy, thay vì rơi vào một tên file gõ tay. Trả None khi user chọn "none",
    khi hiệu ứng không có tiếng, hoặc khi file không tồn tại.
    """
    allowed = HOOK_EFFECT_SOUNDS.get(effect)
    if not allowed or not reel_key or reel_key == "none":
        return None
    key = reel_key if reel_key in allowed else allowed[0]
    path = os.path.join(SFX_DIR, HOOK_REEL_SOUNDS[key])
    return path if os.path.isfile(path) else None


def hook_sfx_max_dur(effect_duration: float) -> float:
    """Trần độ dài cho một tiếng điểm nhấn của hiệu ứng dài `effect_duration` giây."""
    return max(0.5, float(effect_duration) + HOOK_SFX_TAIL)


# Hệ số cân bằng ĐO ĐƯỢC, đưa mọi tiếng hiệu ứng về cùng một mức nghe.
#
# LỖI CŨ: mỗi nhánh hiệu ứng nhân một hằng số gõ tay khác nhau (×3.0 cho impact, ×0.6
# cho typewriter, ×1.5 cho tick...) TRÊN những file vốn đã chênh nhau 27.7 dB RMS —
# arcade_8bit là bản nén rất "nóng" (−4.3 dB) trong khi film_projector chỉ −32.0 dB.
# Cộng dồn hai tầng lệch, đỉnh sau khi nhân trải từ 0.25 tới 2.56, tức tiếng to nhất
# gấp 10 LẦN tiếng nhỏ nhất. Đo trên bản render thật: hook camera_shutter −25.3 dB
# trong khi hook carousel −17.7 dB, chênh 7.6 dB giữa hai hiệu ứng lẽ ra ngang nhau.
#
# Cách tính: chuẩn RMS về −22 dB, cộng một khoản lệch theo TÍNH CHẤT tiếng (cú đánh
# mạnh hơn, tiếng nền nhẹ hơn), rồi chặn đỉnh 0.85 để còn biên cho limiter ở bước trộn.
# Kết quả: chênh lệch còn 8.8 dB — phần dư là bản chất, tiếng xung ngắn không thể đạt
# cùng RMS mà không méo.
#
# Đo lại sau khi thay file tiếng: xem tests/test_hook_sfx.py::test_am_luong_can_bang.
HOOK_SFX_GAIN = {
    "tick_wood":        1.44,
    "arcade_8bit":      0.13,   # bản nén rất nóng, phải kéo xuống mạnh
    "money_counter":    1.57,
    "impact_boom":      0.56,   # đã +3 dB cho chất "cú đánh"
    "typewriter_fast":  0.85,
    "cinematic_swell":  1.29,   # −2 dB: là nền dâng, không phải điểm nhấn
    "ambient_mystic":   0.36,   # −4 dB: nền tĩnh mịch, nhẹ nhất
    "camera_shutter":   1.70,
    "digital_glitch":   1.05,
    "film_projector":   3.18,   # file gốc rất nhỏ (−32 dB)
    # Đo bằng ffmpeg volumedetect: pop.wav mean −22.4 dB (gần như đúng chuẩn, gain≈1),
    # bell.wav mean −14.1 dB (nóng hơn chuẩn 7.9 dB, phải kéo xuống ~0.40 để về −22 dB).
    "cta_pop":          1.05,
    "cta_chime":        0.40,
    # Tiếng PHỤ TRỢ — file cố định, không phải lựa chọn của người dùng. Phải có khoá
    # riêng: nếu truyền reel_key cho chúng thì chúng mượn hệ số của tiếng khác, và một
    # lựa chọn như arcade_8bit (hệ số 0.13) sẽ làm tắt ngóm tiếng ding/tick đi kèm.
    "_ding":            0.47,
    "_tick":            0.95,
    "_whoosh":          0.72,
}

# Trần cuối cùng sau khi nhân mức người dùng chỉnh. Người dùng kéo thanh trượt lên 200%
# vẫn không được phép làm SFX lấn hẳn giọng đọc.
HOOK_SFX_CEILING = 1.6


def hook_sfx_level(reel_key: str, user_volume: float) -> float:
    """Âm lượng cuối của một tiếng hiệu ứng = cân bằng đo được × mức người dùng chỉnh."""
    return min(HOOK_SFX_CEILING, float(user_volume) * HOOK_SFX_GAIN.get(reel_key, 1.0))
SFX_MIX_GAIN = 0.6             # hệ số giảm âm lượng SFX chung (tránh SFX thô/to lấn giọng đọc)

# Cân bằng âm lượng cho 13 SFX PER-SCENE (whoosh/pop/tick/ding/bell/shimmer/riser/
# bass_drop/impact/suspense/heartbeat/laugh/swoosh_soft) — CÙNG MỘT LỚP LỖI với
# HOOK_SFX_GAIN phía trên nhưng chưa từng được vá cho nhóm SFX này: mọi tiếng đều
# nhân đúng một công thức phẳng `sfx_volume * SFX_MIX_GAIN * scene_vol_ratio`
# (xem chỗ dùng bên dưới) bất kể độ to gốc của file chênh nhau bao nhiêu.
#
# Đo bằng `ffmpeg volumedetect` trên chính kho assets/sfx: mean_volume trải từ
# −42.0 dB (shimmer.wav) tới −8.3 dB (suspense.wav) — chênh 33.7 dB, tức chọn
# "Lấp lánh" cho một cảnh gần như câm trong khi chọn "Hồi hộp" cho cảnh khác chói
# hẳn lên, cùng một thanh trượt âm lượng. Nặng hơn cả lỗi 27.7 dB đã vá cho
# HOOK_SFX_GAIN.
#
# Cách tính: chuẩn RMS về -22 dB (cùng chuẩn với HOOK_SFX_GAIN), CHẶN TRẦN 3.5×.
# shimmer.wav là ngoại lệ duy nhất chạm trần: mean −42 dB cần gain 10× mới về đúng
# -22 dB, nhưng max_volume của nó chỉ −4.5 dB (file gần như toàn im lặng, một cú
# lấp lánh ngắn) — khuếch đại 10× (+20 dB) sẽ biến một hiệu ứng vốn dĩ TINH TẾ
# thành một tiếng chói tai ở đúng khung hình nó vang lên, đổi hẳn TÍNH CHẤT âm
# thanh chứ không chỉ độ to. Trần 3.5× (khớp tiền lệ film_projector trong
# HOOK_SFX_GAIN) đưa shimmer lên -31.1 dB — vẫn êm hơn phần còn lại một cách CÓ
# CHỦ Ý, không phải sai sót.
#
# Đo lại sau khi thêm/đổi file: tests/test_audio_mix.py::test_scene_sfx_can_bang_am_luong.
SCENE_SFX_GAIN = {
    "whoosh":      0.72,
    "swoosh_soft": 1.02,
    "pop":         1.05,
    "tick":        1.74,
    "ding":        0.37,
    "bell":        0.40,
    "shimmer":     3.50,   # CHẶN TRẦN — xem giải thích ở trên, KHÔNG phải 10.0 tính thẳng từ RMS
    "riser":       0.65,
    "bass_drop":   0.69,
    "impact":      1.84,
    "suspense":    0.21,
    "heartbeat":   0.60,
    "laugh":       0.72,
    "breath":      1.61,   # đo mean -26.2dB, max -9.6dB — không sát trần như shimmer, dùng thẳng gain RMS
}

# Gemini gán tên SFX theo NHỊP KỂ CHUYỆN (VD "sfx 'tick' khi liệt kê" — xem
# TONE_EFFECT_PALETTES/NICHE_BLUEPRINTS ở gemini_service.py), nên nhiều cảnh liên
# tiếp cùng nhịp rất hay trùng tên. Vì mỗi tên chỉ có ĐÚNG MỘT file .wav cố định,
# video cắt nhanh (cảnh 2-4s) phát nguyên văn cùng một file lặp lại sát nhau nghe
# như một nhịp trống đơn điệu, khó chịu. Dưới ngưỡng này (giây) thì bỏ lần lặp thứ
# 2 trở đi của CÙNG một tên, chờ tên khác hoặc khoảng cách đủ xa mới phát lại.
SCENE_SFX_REPEAT_MIN_GAP = 1.8

# Biến tấu ngẫu nhiên nhỏ mỗi lần phát (cao độ + âm lượng) để những lần KHÔNG bị
# chặn ở trên (tên khác nhau, hoặc đủ xa) cũng không nghe y hệt nhau — tai người
# rất nhạy với âm thanh lặp lại tuyệt đối giống nhau, lệch vài % đã đủ phá cảm giác
# máy móc mà không ảnh hưởng bảng cân bằng SCENE_SFX_GAIN ở trên.
SCENE_SFX_PITCH_JITTER = 0.06   # ±6% cao độ (kéo theo ±6% độ dài — kiểu tăng/giảm tốc băng cối)
SCENE_SFX_GAIN_JITTER = 0.08    # ±8% âm lượng (~±0.7dB)

# Không phải SFX nào cũng đáng chịu chung một luật. Chia theo VAI TRÒ trong nhịp kể:
#
# - LẤP CHỖ (dưới đây): tiếng chuyển cảnh / đếm nhịp. Gemini rải chúng dày nhất và
#   bản thân chúng gần như không mang thông tin — ĐÂY mới là nhóm gây nhàm tai khi dồn.
# - NHẤN (mọi tên còn lại: impact/bass_drop/riser/suspense/heartbeat/laugh/...): hiếm và
#   được đặt CÓ CHỦ ĐÍCH ở cao trào. Bỏ một tiếng impact ở đúng cú twist gây hại nhiều
#   hơn hẳn việc để nó vang gần một tiếng whoosh, nên nhóm này MIỄN cooldown bên dưới
#   (vẫn chịu luật trùng tên SCENE_SFX_REPEAT_MIN_GAP phía trên).
#
# Tên KHÔNG nằm trong tập này (SFX user tự tải lên) mặc định xếp vào nhóm NHẤN: không
# phân loại được thì không tự ý vứt của người dùng.
SCENE_SFX_FILLER = frozenset({"whoosh", "swoosh_soft", "pop", "tick"})

# Cooldown RIÊNG cho nhóm lấp chỗ, đo từ tiếng lấp chỗ gần nhất ĐƯỢC PHÁT THẬT (không
# phải từ cảnh gần nhất được GÁN). Quá sát thì BỎ HẲN — không đổi sang một tiếng lấp
# chỗ khác: đổi tên chỉ xoay âm sắc mà giữ nguyên MẬT ĐỘ, đúng thứ cần giảm.
#
# Đo trên 32 kịch bản Gemini thật đã cache (296 cảnh): chỉ 33% số cảnh được gán SFX và
# khoảng cách nhỏ nhất giữa 2 SFX liên tiếp là 3.67s — nên ở kịch bản do AI sinh, luật
# này gần như không bao giờ chạm tới. Nó tồn tại cho trường hợp user tự thêm SFX cho
# từng cảnh trong ScriptEditor, lúc đó mật độ mới thật sự tăng.
SCENE_SFX_FILLER_MIN_GAP = 3.0


def plan_scene_sfx(entries, exists=None):
    """
    Quyết định TRƯỚC cảnh nào được phát SFX per-scene.

    Tách hẳn khỏi vòng lặp render để test được mà không phải dựng cả một job — luật
    chọn/bỏ SFX trước đây nằm lẫn trong thân `render_final_video` nên không bộ test nào
    chạm tới được, và một lần thay luật đã lọt qua trọn bộ test mà không ai hay.

    entries: [(ten_sfx, moc_bat_dau_giay)] theo ĐÚNG thứ tự cảnh. Tên rỗng = cảnh không
             có SFX (vẫn phải truyền vào để chỉ số trả về khớp chỉ số cảnh).
    exists : callable(ten) -> bool. Dùng để một file THIẾU (tên gõ sai, SFX user đã xoá)
             không chiếm mất suất cooldown của một tiếng hợp lệ phía sau.

    Trả về set chỉ số cảnh ĐƯỢC PHÁT.
    """
    allowed = set()
    prev_name = None
    prev_start = None          # cảnh CÓ GÁN SFX gần nhất, kể cả khi bị chặn — cho luật trùng tên
    prev_filler_start = None   # tiếng lấp chỗ gần nhất PHÁT THẬT — cho cooldown lấp chỗ
    for i, (name, start) in enumerate(entries):
        if not name:
            continue
        # Tầng 1 — trùng TÊN quá sát (áp cho mọi nhóm). Mốc so sánh là cảnh được gán gần
        # nhất chứ không phải cảnh phát gần nhất: một chuỗi 3 cảnh 'tick' cách nhau 1s
        # phải bị chặn từ cảnh thứ 2 trở đi, chứ không để cảnh thứ 3 "đủ xa" cảnh thứ 1.
        gap = (start - prev_start) if prev_start is not None else None
        blocked = (
            name == prev_name
            and gap is not None
            and gap < SCENE_SFX_REPEAT_MIN_GAP
        )
        # Tầng 2 — cooldown nhóm lấp chỗ. Nhóm nhấn không đi qua nhánh này.
        if not blocked and name in SCENE_SFX_FILLER and prev_filler_start is not None:
            blocked = (start - prev_filler_start) < SCENE_SFX_FILLER_MIN_GAP
        prev_name, prev_start = name, start
        if blocked:
            continue
        if exists is not None and not exists(name):
            continue
        allowed.add(i)
        if name in SCENE_SFX_FILLER:
            prev_filler_start = start
    return allowed


def scene_sfx_jitter(output_path: str, index: int, sfx_name: str):
    """
    Biến tấu cao độ + âm lượng cho MỘT lần phát SFX — xem SCENE_SFX_PITCH_JITTER/GAIN_JITTER.

    Gieo hạt từ (tên file đích + chỉ số cảnh + tên SFX) thay vì dùng `random` toàn cục:
    render lại CÙNG một dự án phải cho ra CÙNG một bản mix. Không có tính tái lập thì
    không thể đem hai lần render ra so để tìm hồi quy — chính là cách đã bắt được bug
    Pattern Interrupt cháy trắng trước đây.

    Trả về (hệ_số_gain, tỷ_lệ_cao_độ).
    """
    rng = random.Random(f"{os.path.basename(output_path)}|{index}|{sfx_name}")
    return (
        rng.uniform(1.0 - SCENE_SFX_GAIN_JITTER, 1.0 + SCENE_SFX_GAIN_JITTER),
        rng.uniform(1.0 - SCENE_SFX_PITCH_JITTER, 1.0 + SCENE_SFX_PITCH_JITTER),
    )

# QUAN TRỌNG: font PHẢI có glyph tiếng Việt đầy đủ, đặc biệt ư/Ư (U+01B0/01AF)
# và ơ/Ơ (U+01A1/01A0).
# CẢNH BÁO: "Arial Black" (ariblk.ttf) KHÔNG có các glyph này — đã kiểm chứng bằng
# fontTools trên chính máy này. Khi thiếu glyph, libass thay thế từng ký tự bằng font
# khác nên chữ "trước" hiện thành "trƯớc": sai giữa từ, thấy rõ ở mọi phụ đề.
# Segoe UI Black (seguibl.ttf) cùng độ dày mà phủ đủ tiếng Việt.
SUBTITLE_FONT_NAME = "Segoe UI Black"
SUBTITLE_FONT_PATH = "C:/Windows/Fonts/seguibl.ttf"

# ── Thư mục BGM / SFX ───────────────────────────────────────────────
# Cả hai là tài nguyên ĐI KÈM MÃ NGUỒN: chúng ở lại backend/assets kể cả khi user
# chuyển kho dữ liệu sang ổ D (xem config.py).
from config import BASE_DIR, BGM_DIR, SFX_DIR, TEMP_DIR  # noqa: F401


class SceneAsset(TypedDict):
    image_path: str
    audio_path: str        # có thể rỗng "" cho slideshow mode
    text: str              # có thể rỗng "" cho slideshow mode
    duration: float        # độ dài audio (giây), hoặc SLIDESHOW_SCENE_DURATION
    sfx: str               # Tên hiệu ứng âm thanh (whoosh, pop...)
    visual_effect: str     # zoom_in, zoom_out, pan_left, pan_right
    highlight_text: str    # B-Roll Text


# ─────────────────────────────────────────────────────────────────────
# Transition Engine — đa dạng hoá chuyển cảnh
# ─────────────────────────────────────────────────────────────────────
# Danh sách transition hợp lệ (đồng bộ với frontend constants.TRANSITIONS)
VALID_TRANSITIONS = {
    "crossfade", "fade_black", "fade_white", "zoom_through",
    "slide_left", "slide_right", "slide_up", "slide_down", "whip_pan",
    "page_flip", "droplet", "zoom_punch", "wipe_right", "wipe_down",
}


def _apply_transition(scene, transition, add_crossfade_in, crossfade_dur, video_width, video_height):
    """
    Áp hiệu ứng chuyển cảnh cho ENTRANCE của 1 scene (blend/slide/reveal chồng lên cảnh
    trước trong vùng overlap). Luôn CrossFadeOut ở cuối để cảnh sau có nền blend.

    Mọi hiệu ứng "fancy" (slide/page_flip/droplet) được bọc try/except → nếu MoviePy lỗi
    thì tự động fallback crossfade, KHÔNG bao giờ làm hỏng render.
    """
    from moviepy.video.fx import CrossFadeIn, CrossFadeOut, FadeIn, FadeOut
    cf = crossfade_dur

    # Cảnh đầu tiên: không có entrance transition, chỉ fade out cuối để nối cảnh sau
    if not add_crossfade_in:
        return scene.with_effects([CrossFadeOut(cf)])

    try:
        if transition == "fade_black":
            return scene.with_effects([FadeIn(cf), FadeOut(cf)])

        if transition == "fade_white":
            from moviepy import ColorClip
            flash = (
                ColorClip((video_width, video_height), color=(255, 255, 255))
                .with_duration(cf)
                .with_effects([CrossFadeOut(cf)])
            )
            scene = scene.with_effects([CrossFadeIn(cf * 0.5), CrossFadeOut(cf)])
            return CompositeVideoClip([scene, flash], size=(video_width, video_height)).with_duration(scene.duration)

        if transition == "zoom_through":
            return scene.with_effects([CrossFadeIn(cf * 0.8), CrossFadeOut(cf * 0.8)])

        if transition == "zoom_punch":
            # Giật zoom vào: cảnh phóng to 1.4 rồi thu về 1.0 khi xuất hiện (đấm thị giác)
            def _punch(t, d=cf):
                p = min(t / d, 1.0) if d > 0 else 1.0
                ease = 1 - (1 - p) ** 3
                return 1.4 - 0.4 * ease

            scene = scene.resized(_punch).with_position("center")
            scene = scene.with_effects([CrossFadeIn(cf * 0.5), CrossFadeOut(cf)])
            return CompositeVideoClip([scene], size=(video_width, video_height)).with_duration(scene.duration)

        if transition in ("slide_left", "slide_right", "slide_up", "slide_down", "whip_pan", "page_flip"):
            slide_dur = cf * (0.5 if transition == "whip_pan" else 1.0)

            def _pos(t, tr=transition, d=slide_dur):
                p = min(t / d, 1.0) if d > 0 else 1.0
                ease = 1 - (1 - p) ** 3  # ease-out cubic cho cảm giác "đẩy" mượt
                if tr in ("slide_left", "whip_pan", "page_flip"):
                    return (int(video_width * (1 - ease)), 0)      # vào từ phải
                if tr == "slide_right":
                    return (int(-video_width * (1 - ease)), 0)     # vào từ trái
                if tr == "slide_up":
                    return (0, int(video_height * (1 - ease)))     # vào từ dưới
                if tr == "slide_down":
                    return (0, int(-video_height * (1 - ease)))    # vào từ trên
                return (0, 0)

            scene = scene.with_position(_pos)

            if transition == "page_flip":
                # Ép ngang nhẹ lúc "lật" rồi bung ra → cảm giác lật trang sách
                def _scale(t, d=slide_dur):
                    p = min(t / d, 1.0) if d > 0 else 1.0
                    return 0.82 + 0.18 * p

                scene = scene.resized(_scale)

            scene = scene.with_effects([CrossFadeOut(cf)])
            return CompositeVideoClip([scene], size=(video_width, video_height)).with_duration(scene.duration)

        if transition in ("droplet", "wipe_right", "wipe_down"):
            # Mặt nạ reveal: droplet=tròn lan từ tâm; wipe_right=lộ trái→phải; wipe_down=trên→dưới
            import numpy as np
            from moviepy import VideoClip
            w, h = video_width, video_height
            if transition == "droplet":
                max_r = ((w ** 2 + h ** 2) ** 0.5) / 2.0
                yy, xx = np.ogrid[:h, :w]
                dist = np.sqrt((xx - w / 2.0) ** 2 + (yy - h / 2.0) ** 2)

                def _mask_frame(t, d=cf):
                    p = min(t / d, 1.0) if d > 0 else 1.0
                    ease = 1 - (1 - p) ** 2
                    return (dist <= ease * max_r).astype(float)
            else:
                col_idx = np.arange(w).reshape(1, w)
                row_idx = np.arange(h).reshape(h, 1)

                def _mask_frame(t, d=cf, tr=transition):
                    p = min(t / d, 1.0) if d > 0 else 1.0
                    ease = 1 - (1 - p) ** 2
                    if tr == "wipe_right":
                        m = (col_idx <= ease * w).astype(float)
                        return np.broadcast_to(m, (h, w)).copy()
                    m = (row_idx <= ease * h).astype(float)
                    return np.broadcast_to(m, (h, w)).copy()

            mask = VideoClip(_mask_frame, is_mask=True).with_duration(scene.duration)
            return scene.with_mask(mask).with_effects([CrossFadeOut(cf)])
    except Exception as e:
        logger.warning(f"[Transition] '{transition}' lỗi ({e}), fallback crossfade.")

    # Mặc định: crossfade
    return scene.with_effects([CrossFadeIn(cf), CrossFadeOut(cf)])


# ─────────────────────────────────────────────────────────────────────
# Chuẩn hoá khung hình — thay viền đen bằng nền mờ lấp đầy
# ─────────────────────────────────────────────────────────────────────
# Lệch tỉ lệ dưới ngưỡng này thì CROP cho lấp đầy khung (mất rìa không đáng kể,
# đẹp hơn mọi loại nền). Vượt ngưỡng mới cần nền mờ.
CROP_FILL_TOLERANCE = 0.18


def _blurred_fill_bg_from_frame(frame, w: int, h: int, duration: float, darken: float = 0.45):
    """
    Nền LẤP ĐẦY khung từ chính khung hình đầu tiên của media: phóng to + làm mờ + tối đi.

    LÝ DO: trước đây media lệch tỉ lệ được fit vào giữa trên nền ColorClip ĐEN. Video stock
    Pexels rất hay trả clip 1080x1350 / 16:9 nên khung 9:16 lòi 2 dải đen dày — thứ giết
    cảm giác "video xịn" nhanh nhất. Nền mờ lấp đầy là cách các editor thật vẫn dùng.
    Nhận sẵn mảng frame thay vì đường dẫn để không phải decode lại file lần hai.
    """
    try:
        from PIL import Image, ImageFilter
        import numpy as np

        img = Image.fromarray(frame).convert("RGB")
        scale = max(w / img.width, h / img.height)
        nw, nh = int(img.width * scale) + 2, int(img.height * scale) + 2
        img = img.resize((nw, nh)).filter(ImageFilter.GaussianBlur(35))
        left, top = (nw - w) // 2, (nh - h) // 2
        img = img.crop((left, top, left + w, top + h))
        arr = (np.array(img).astype(np.float32) * darken).astype(np.uint8)
        return ImageClip(arr).with_duration(duration)
    except Exception as e:
        logger.warning(f"[BlurredFill] Lỗi tạo nền mờ ({e}). Dùng nền tối trơn.")
        from moviepy import ColorClip
        return ColorClip((w, h), color=(12, 12, 18)).with_duration(duration)


# ─────────────────────────────────────────────────────────────────────
# Build 1 scene clip
# ─────────────────────────────────────────────────────────────────────
def _build_scene_clip(
    asset: SceneAsset,
    add_crossfade_in: bool,
    video_width: int,
    video_height: int,
    crossfade_dur: float = CROSSFADE_DURATION,
    show_subtitle: bool = True,
    subtitle_font_size: int = 52,
    subtitle_color: str = "white",
    transition: str = "crossfade",
    # None = cảnh này KHÔNG hiện chữ nhấn (bị luật chống lặp loại); số = giây thứ mấy của
    # cảnh thì chữ bắt đầu hiện. Xem motion_effects.plan_scene_highlights().
    highlight_start: float | None = 0.0,
) -> CompositeVideoClip:
    """Ghép 1 ảnh + 1 audio + phụ đề burn-in thành 1 clip hoàn chỉnh."""
    duration = asset["duration"]

    # ── Media clip (Video/Image) ──
    is_video = asset["image_path"].lower().endswith((".mp4", ".mov"))
    if is_video:
        media_clip = VideoFileClip(asset["image_path"])
        # Loop video nếu ngắn hơn duration
        if media_clip.duration < duration:
            import math
            from moviepy import concatenate_videoclips
            loops = math.ceil(duration / media_clip.duration)
            media_clip = concatenate_videoclips([media_clip] * loops)
        media_clip = media_clip.subclipped(0, duration)
        media_ratio = media_clip.w / media_clip.h
    else:
        media_clip = (
            ImageClip(asset["image_path"])
            .with_duration(duration)
        )
        media_ratio = media_clip.w / media_clip.h

    # Chuẩn hoá về đúng khung: lệch ít → crop lấp đầy; lệch nhiều → nền mờ lấp đầy
    # (KHÔNG dùng viền đen nữa, xem _blurred_fill_bg_from_frame).
    target_ratio = video_width / video_height
    if abs(target_ratio - media_ratio) <= CROP_FILL_TOLERANCE:
        scale_fill = max(video_width / media_clip.w, video_height / media_clip.h)
        # BỎ QUA resize khi media đã ĐÚNG khung sẵn.
        # LÝ DO: từ khi normalize_stock_clip/apply_ken_burns xuất ra đúng 1080x1920,
        # scale_fill = 1.0 — nhưng MoviePy vẫn chạy PIL resize đủ 2 triệu điểm ảnh MỖI
        # KHUNG chỉ để trả lại đúng ảnh cũ. Đo thực tế: 165 fps → 60 fps, tức mất 2.75 lần
        # tốc độ cho một phép biến đổi không đổi gì cả.
        already_exact = (
            abs(scale_fill - 1.0) < 0.005
            and media_clip.w == video_width
            and media_clip.h == video_height
        )
        if not already_exact:
            media_clip = media_clip.resized(scale_fill)
        media_clip = media_clip.with_position("center")
    else:
        try:
            first_frame = media_clip.get_frame(0)
        except Exception as e:
            logger.warning(f"[BlurredFill] Không đọc được frame đầu ({e}).")
            first_frame = None

        if first_frame is not None:
            bg = _blurred_fill_bg_from_frame(first_frame, video_width, video_height, duration)
        else:
            from moviepy import ColorClip
            bg = ColorClip((video_width, video_height), color=(12, 12, 18)).with_duration(duration)

        scale_fit = min(video_width / media_clip.w, video_height / media_clip.h)
        fg = media_clip.resized(scale_fit).with_position("center")
        media_clip = CompositeVideoClip([bg, fg], size=(video_width, video_height)).with_duration(duration)

    layers = [media_clip]
    
    # ── B-Roll Text (Highlight Text) ──
    highlight_text = asset.get("highlight_text", "")
    if highlight_text and highlight_start is not None:
        from moviepy.video.VideoClip import TextClip
        from moviepy.video.fx.CrossFadeIn import CrossFadeIn
        from moviepy.video.fx.CrossFadeOut import CrossFadeOut
        from services.motion_effects import fit_highlight_fontsize

        # Chỉ hiện chớp nhoáng 1.2s để làm điểm nhấn, không che mặt nhân vật quá lâu
        hl_dur = min(1.2, duration)
        hl_upper = highlight_text.upper()
        hl_font = "C:/Windows/Fonts/arialbd.ttf"
        # Co fontsize theo độ dài chuỗi: 120px cố định tràn khung với cụm 3-4 tiếng
        # Việt có dấu (VD "MIỆT MÀI KIẾM TIỀN"), CompositeVideoClip cắt cụt ở cả hai
        # mép vì TextClip(method="label") không tự wrap/co chữ (xem fit_highlight_fontsize).
        hl_fontsize = fit_highlight_fontsize(hl_upper, hl_font, int(video_width * 0.92))

        txt_clip = (
            TextClip(
                text=hl_upper,
                font=hl_font,
                font_size=hl_fontsize,
                color="yellow",
                stroke_color="black",
                stroke_width=4,
                method="label"
            )
            .with_position(("center", 0.25), relative=True)  # Đẩy lên 25% phía trên
            .with_duration(hl_dur)
            .with_effects([CrossFadeIn(0.2), CrossFadeOut(0.2)])
            # Neo vào ĐÚNG lúc cụm được đọc, không phải đầu cảnh. Kẹp để không tràn qua
            # mốc kết thúc cảnh — tràn thì chữ bị cắt cụt ngay lúc chuyển cảnh.
            .with_start(max(0.0, min(float(highlight_start), duration - hl_dur)))
        )
        layers.append(txt_clip)

    # ── Audio KHÔNG được gắn vào clip video ──
    # LÝ DO: Khi concatenate_videoclips dùng padding âm (crossfade), 
    # MoviePy sẽ mix audio của 2 clip chồng lấp → giọng đọc bị trùng.
    # Audio sẽ được xây dựng thành track riêng biệt trong render_final_video().

    scene = CompositeVideoClip(layers, size=(video_width, video_height))

    # ── Transition Engine (đa dạng: crossfade/slide/page_flip/droplet/...) ──
    scene = _apply_transition(
        scene, transition, add_crossfade_in, crossfade_dur, video_width, video_height
    )

    return scene


# BGM Mix and Mastering are now delegated to FFmpeg in audio_mix_service.py


def _mix_audio_tracks(placements, total_duration, sr: int = 44100, return_array: bool = False):
    """
    Trộn nhiều đoạn audio thành 1 AudioArrayClip bằng numpy.

    `return_array=True` trả thẳng (mảng numpy, sample_rate) thay vì bọc AudioArrayClip —
    dùng khi cần GHI RA FILE (track sidechain chỉ-giọng), khỏi phải render ngược clip
    về mảng một lần nữa. Xem write_voice_sidechain().

    Mỗi phần tử: (path, start_time, volume, fadeout), hoặc thêm max_dur (phần tử thứ 5),
    hoặc thêm cả pitch_ratio (phần tử thứ 6).
    `max_dur` (tuỳ chọn) CẮT CỨNG độ dài đoạn đó — dùng cho SFX mà người dùng tự nạp vào,
    để một file dài (VD tiếng máy đếm tiền 5 giây tải trên mạng) không thể tràn sang phần
    lời dẫn. Đây là chốt chặn ở tầng trộn, không phụ thuộc file nguồn dài bao nhiêu.
    `pitch_ratio` (tuỳ chọn, mặc định 1.0) biến tấu cao độ/tốc độ kiểu băng cối — dùng cho
    SFX per-scene để cùng 1 file không nghe y hệt nhau ở mỗi lần phát (SCENE_SFX_PITCH_JITTER).

    LÝ DO KHÔNG dùng CompositeAudioClip: MoviePy 2.1.2 có bug — frame_function dùng
    `if (part is not False)` mà `part` là mảng numpy khi ghi audio theo chunk, khiến nó gọi
    get_frame trên MỌI clip cho MỌI thời điểm (kể cả ngoài cửa sổ). SFX ngắn (vd tick.wav
    0.05s) bị đọc tại t=1.0s → lỗi "Accessing time t=... with clip duration=...".
    Trộn thủ công bằng numpy đọc mỗi file ĐÚNG độ dài của nó nên tuyệt đối an toàn.
    """
    import math
    import numpy as np
    import soundfile as sf
    from moviepy.audio.AudioClip import AudioArrayClip

    def _read(path):
        """Đọc audio ĐÚNG độ dài file bằng soundfile (WAV & MP3), resample về sr nếu lệch.
        soundfile không đọc chunk vượt biên như MoviePy nên an toàn với file ngắn (tick 0.05s)."""
        data, file_sr = sf.read(path, dtype="float32", always_2d=True)  # (n, ch)
        if file_sr != sr and len(data) > 0:
            import librosa
            data = librosa.resample(data.T, orig_sr=file_sr, target_sr=sr).T
        return np.ascontiguousarray(data, dtype=np.float32)

    total_samples = int(math.ceil(max(total_duration, 0.1) * sr)) + sr  # +1s đệm an toàn
    master = np.zeros((total_samples, 2), dtype=np.float32)
    used = False

    for item in placements:
        # Chấp nhận tuple 4 phần tử (cũ), 5 phần tử có max_dur, hoặc 6 phần tử có
        # thêm pitch_ratio (biến tấu cao độ per-scene SFX, xem SCENE_SFX_PITCH_JITTER).
        path, start, volume, fadeout = item[:4]
        max_dur = item[4] if len(item) > 4 else None
        pitch_ratio = item[5] if len(item) > 5 else 1.0
        try:
            arr = _read(path)
        except Exception:
            # Fallback: đọc qua MoviePy nếu soundfile không xử lý được định dạng
            try:
                from moviepy.audio.io.AudioFileClip import AudioFileClip
                clip = AudioFileClip(path)
                arr = np.asarray(clip.to_soundarray(fps=sr), dtype=np.float32)
                clip.close()
                if arr.ndim == 1:
                    arr = arr[:, None]
            except Exception as e2:
                logger.warning(f"[AudioMix] Bỏ qua {os.path.basename(path)}: {e2}")
                continue

        # Chuẩn hoá về stereo (n, 2)
        if arr.ndim == 1:
            arr = np.column_stack([arr, arr])
        elif arr.shape[1] == 1:
            arr = np.repeat(arr, 2, axis=1)
        elif arr.shape[1] > 2:
            arr = arr[:, :2]

        # Biến tấu cao độ kiểu tăng/giảm tốc băng cối: resample từ sr*pitch_ratio
        # về sr khiến buffer NGẮN/DÀI đi tương ứng — ratio>1 vừa cao giọng vừa nhanh
        # hơn (đã đo bằng FFT trên tín hiệu sin thuần: ratio=1.06 -> +60Hz đúng ~6%).
        # Chỉ áp khi lệch đáng kể để khỏi tốn resample cho mọi track giọng đọc/BGM
        # (pitch_ratio mặc định 1.0 ở mọi placement khác ngoài SFX per-scene).
        if abs(pitch_ratio - 1.0) > 1e-3 and len(arr) > 4:
            import librosa as _librosa
            arr = np.ascontiguousarray(
                _librosa.resample(arr.T, orig_sr=sr * pitch_ratio, target_sr=sr).T,
                dtype=np.float32,
            )

        # Cắt cứng theo max_dur + gọt mềm 40ms cuối để chỗ cắt không kêu "pắc"
        if max_dur and max_dur > 0:
            limit = int(max_dur * sr)
            if 0 < limit < len(arr):
                arr = arr[:limit].copy()
                soft = min(int(0.04 * sr), len(arr))
                if soft > 1:
                    arr[-soft:] *= np.linspace(1.0, 0.0, soft)[:, None]

        if volume != 1.0:
            arr = arr * float(volume)

        if fadeout and fadeout > 0:
            fs = int(fadeout * sr)
            if 0 < fs < len(arr):
                arr[-fs:] *= np.linspace(1.0, 0.0, fs)[:, None]

        s = int(start * sr)
        if s >= total_samples or len(arr) == 0:
            continue
        e = min(s + len(arr), total_samples)
        master[s:e] += arr[: e - s]
        used = True

    if not used:
        # Giữ đúng ARITY của giá trị trả về ở cả hai chế độ: caller dùng return_array
        # unpack thành 2 biến, trả None trần ở đây sẽ ném TypeError thay vì cho nó
        # kiểm tra "không có audio" một cách bình thường.
        return (None, sr) if return_array else None

    # CẮT về đúng thời lượng video.
    # `total_samples` cộng thêm 1 giây đệm để mọi SFX đặt sát cuối vẫn ghi được trọn vẹn,
    # NHƯNG nếu trả nguyên phần đệm đó thì track audio dài hơn hình 1 giây — MoviePy ghi
    # hình tới 21.1s còn container kéo tới 22.1s, thành ra mọi video đều thừa 1 giây câm
    # ở cuối. Đệm chỉ để tính toán an toàn, không được lọt ra ngoài.
    keep = int(math.ceil(max(total_duration, 0.1) * sr))
    master = master[:keep]

    # ── Chống vỡ tiếng (clipping) ──
    # LỖI CŨ: `if peak > 1.0: master /= peak` — chia CẢ track cho đỉnh toàn cục. Nhưng
    # master này chứa cả giọng đọc lẫn SFX, nên một đỉnh 2 giây đầu (vd user kéo Hook SFX
    # lên 200%: tick.wav chồng lấn nhiều lớp → peak ~2.5) sẽ kéo tụt âm lượng giọng đọc
    # của TOÀN BỘ video xuống 2.5 lần. Triệu chứng ngoài đời là "tự nhiên video bé tiếng"
    # mà không liên quan gì tới đoạn đang nghe — gần như không thể lần ra nguyên nhân.
    #
    # Thay bằng limiter mềm: dưới ngưỡng THRESH giữ NGUYÊN XI (giọng đọc không bị đụng
    # tới), chỉ phần vượt ngưỡng mới bị nén bằng tanh. tanh() < 1 với mọi đầu vào nên
    # kết quả luôn nằm trong (-1, 1) → không thể clip, mà cũng không có chỗ nào bị "vặn
    # nhỏ oan".
    if master.size:
        THRESH = 0.85          # dưới mức này: tuyến tính tuyệt đối
        CEILING = 0.99         # trần thật (~-0.1 dBFS), KHÔNG phải 1.0: tanh() của số
                               # lớn bị làm tròn thành đúng 1.0 trong float32, nên lấy
                               # trần 1.0 thì đỉnh chạm sát 0 dBFS và encoder vẫn có thể
                               # kêu rè. Chừa lại một chút biên an toàn.
        HEADROOM = CEILING - THRESH
        absm = np.abs(master)
        over = absm > THRESH
        if over.any():
            excess = absm[over] - THRESH
            master[over] = np.sign(master[over]) * (
                THRESH + HEADROOM * np.tanh(excess / HEADROOM)
            )
            n_over = int(over.sum())
            logger.info(
                f"[AudioMix] Limiter mềm: nén {n_over} mẫu vượt {THRESH} "
                f"(đỉnh gốc {float(absm.max()):.2f}) — giọng đọc giữ nguyên âm lượng."
            )

    if return_array:
        return master, sr
    return AudioArrayClip(master, fps=sr)


# Hậu tố cố định của track chỉ-giọng dùng làm tín hiệu điều khiển ducking.
# Quy ước đường dẫn (thay vì đổi giá trị trả về của render_final_video) để cả đường
# worker lẫn đường inline tự tìm được file mà không phải nối thêm một kênh truyền nữa.
VOICE_SIDECHAIN_SUFFIX = ".voice.wav"


def write_voice_sidechain(voice_placements, master_audio_path, total_duration, video_path) -> str | None:
    """
    Ghi một track CHỈ CÓ GIỌNG ĐỌC, làm tín hiệu điều khiển cho sidechain ducking.

    VÌ SAO CẦN: bước master trước đây lấy `[0:a]` — track audio của video thô — làm
    sidechain. Nhưng track đó đã được trộn sẵn giọng đọc + TOÀN BỘ SFX + tiếng hook.
    Hậu quả: mỗi tiếng whoosh, impact_boom, tiếng máy xèng đều dìm nhạc nền xuống y hệt
    giọng nói — nhạc bị nén xuống đúng vào khoảnh khắc lẽ ra phải hoành tráng nhất.
    SFX là NỘI DUNG, không phải tín hiệu điều khiển.

    Trả None nếu không có giọng (photo_slideshow) — caller tự hiểu là khỏi ducking.
    """
    placements = _all_placements(voice_placements, master_audio_path, total_duration)
    if not placements:
        return None
    try:
        import soundfile as sf

        master, sr = _mix_audio_tracks(placements, total_duration, return_array=True)
        if master is None or not getattr(master, "size", 0):
            return None
        out = video_path + VOICE_SIDECHAIN_SUFFIX
        sf.write(out, master, sr)
        return out
    except Exception as e:
        # Không có sidechain thì ducking rơi về dùng [0:a] như cũ — kém hơn, không chết.
        logger.warning("[AudioMix] Không ghi được track sidechain chỉ-giọng: %s", e)
        return None


def _all_placements(audio_placements, master_audio_path, total_duration):
    """
    Danh sách track audio đầy đủ = SFX/giọng từng cảnh + dải giọng liền mạch (nếu có).
    Tách ra hàm riêng để đường nhanh (FFmpeg) và đường chậm (MoviePy) dùng CHUNG một
    nguồn sự thật, không sợ hai nhánh trộn ra hai bản khác nhau.
    """
    out = list(audio_placements)
    if master_audio_path and os.path.exists(master_audio_path):
        out.append((master_audio_path, 0.0, 1.0, 0.0))
    return out


# ─────────────────────────────────────────────────────────────────────
# Main render function
# ─────────────────────────────────────────────────────────────────────
# Mọi tuỳ chọn đi qua **kwargs của render_final_video — DANH SÁCH ĐẦY ĐỦ, phải khớp
# đúng những `kwargs.get("...")` bên trong hàm.
#
# VÌ SAO CẦN: **kwargs im lặng ở CẢ HAI chiều. Thiếu một key thì hàm lặng lẽ dùng
# default (đúng lỗi hook_sfx_volume: model có, frontend gửi, nhưng main.py quên nhét
# vào render_kwargs → thanh trượt của user vô hiệu suốt nhiều bản render mà không một
# dòng lỗi nào). Gõ sai tên một key thì cũng y như vậy, không ai hay. Danh sách này
# cộng với cảnh báo bên dưới biến cả hai loại lỗi câm thành một dòng WARNING trong log,
# và cho test hợp đồng ở tests/test_render_contract.py một nguồn để đối chiếu.
RENDER_KWARG_KEYS = frozenset({
    "hook_effect",
    "hook_quote",
    "hook_reel_sfx",
    "hook_sfx_volume",
    "hook_text",
    "outro_effect",
    "outro_reel_sfx",
    "outro_sfx_volume",
    "outro_text",
    "cta_text",
    "use_fast_assembly",
    "use_gpu_encode",
})


def render_final_video(
    scene_assets: List[SceneAsset],
    output_path: str,
    aspect_ratio: str = "9:16",
    bgm_path: Optional[str] = None,
    mode: str = "storyteller",
    bgm_volume: float = 0.15,
    master_audio_path: Optional[str] = None,
    use_sfx: bool = True,
    sfx_volume: float = 0.5,
    progress_logger="bar",
    # Được gọi khi đường nhanh (FFmpeg) hỏng và phải quay về MoviePy. Tiêm TẠI CHỖ ở
    # tiến trình con giống progress_logger — hàm không pickle được nên không đi qua
    # spawn_render được. None = không ai muốn nghe (vd test).
    on_fallback=None,
    **kwargs
) -> str:
    """
    Ghép toàn bộ các scene thành 1 video .mp4 hoàn chỉnh.
    Hỗ trợ đa aspect ratio, BGM mixing, và mode-specific rendering.
    Trả về output_path.

    Các tuỳ chọn nhận qua **kwargs: xem RENDER_KWARG_KEYS ngay phía trên.
    """
    # Key lạ = gõ sai tên hoặc caller gửi thừa. Chỉ CẢNH BÁO chứ không ném lỗi: đang ở
    # giữa một job render dài, chết vì một tuỳ chọn phụ thì thiệt hơn nhiều so với việc
    # render tiếp và để lại dấu vết trong log.
    _unknown = set(kwargs) - RENDER_KWARG_KEYS
    if _unknown:
        logger.warning(
            f"[Render] Bỏ qua tham số không được hỗ trợ: {sorted(_unknown)}. "
            f"Gõ sai tên? Danh sách hợp lệ: {sorted(RENDER_KWARG_KEYS)}"
        )

    video_width, video_height = ASPECT_RATIO_SIZES.get(aspect_ratio, (1080, 1920))

    # ── Mode-specific settings ──
    is_slideshow = (mode == "photo_slideshow")
    crossfade_dur = SLIDESHOW_CROSSFADE if is_slideshow else CROSSFADE_DURATION
    show_subtitle = not is_slideshow  # Slideshow không có subtitle
    subtitle_font_size = 58 if mode == "quiz_listicle" else 52
    subtitle_color = "#FFD700" if mode == "quiz_listicle" else "white"

    clips = []
    audio_placements = []  # (path, start_time, volume, fadeout) — trộn bằng numpy sau vòng lặp
    # TẬP CON chỉ gồm giọng đọc, không SFX. Dùng làm tín hiệu điều khiển ducking ở bước
    # master — xem write_voice_sidechain() để biết vì sao không thể dùng track đã trộn.
    voice_placements = []
    speech_segments = []
    final_duration = 0.0

    # ── Hook Engine (Overlay clip carousel_quote lên đầu video) ──
    hook_duration = 0.0
    hook_clip_overlay = None
    hook_type = kwargs.get("hook_effect")
    # Định nghĩa VÔ ĐIỀU KIỆN (không phụ thuộc hook_type): khối FastAssembly bên dưới
    # cần đọc lại để tính hook_duration động qua resolve_hook_timing() dù hook_type là
    # gì — để trong nhánh `if` bên dưới sẽ NameError khi hook_type="none".
    #
    # hook_quote  = quote CHỈ dành cho carousel_quote (hiện cạnh bìa sách ở pha Reveal).
    # hook_text   = tiêu đề chữ cho blackout_question/typewriter_quote.
    # LỖI CŨ: build_blackout_question_hook/build_typewriter_quote_hook trước đây nhận
    # nhầm `hook_quote` — đúng ra phải là `hook_text`, khớp với field UI thật sự cho
    # user nhập (AdvancedSettings.jsx: ô "TIÊU ĐỀ HOOK CHỮ" ghi rõ áp dụng cho 2 hiệu
    # ứng này, ô "TRÍCH DẪN HOOK BÌA SÁCH" ghi rõ chỉ áp dụng Carousel). Hậu quả kép:
    # (1) user điền đúng ô theo nhãn UI nhưng hook vẫn trống vì code đọc sai field;
    # (2) hook_text đồng thời còn kích hoạt phụ đề ASS legacy (word_by_word/full_shake,
    # xem generate_ass_file) vì điều kiện loại trừ ở đó chỉ chặn "carousel_quote", nên
    # chọn blackout/typewriter mà có hook_text vẫn bị burn thêm 1 lớp phụ đề chồng lên
    # cảnh 1 — sửa luôn điều kiện đó bên dưới để loại trừ MỌI hook do Hook Engine quản.
    hook_quote = kwargs.get("hook_quote", "")
    hook_text = kwargs.get("hook_text", "") or ""
    hook_sfx_volume = kwargs.get("hook_sfx_volume", 1.0)
    # MỘT nguồn duy nhất cho cả chuỗi if/elif bên dưới. Không cần mặc định riêng từng
    # nhánh nữa: resolve_effect_sfx() đã tự kéo mọi khoá lạ/khoá của hiệu ứng khác về
    # lựa chọn đầu tiên của chính hiệu ứng đang chạy.
    reel_key = kwargs.get("hook_reel_sfx") or DEFAULT_HOOK_REEL
    if hook_type and hook_type != "none":
        try:
            from services.hook_engine import (
                build_carousel_hook, SLOT_DURATION,
                build_blackout_question_hook,
                build_typewriter_quote_hook,
                build_breathing_vignette_hook,
                build_camera_shutter_hook,
                build_cyber_glitch_hook,
                build_vintage_film_burn_hook
            )
            cover_img = scene_assets[0]["image_path"]

            if hook_type == "carousel_quote":
                hook_clip_overlay = build_carousel_hook(cover_img, hook_quote, video_width, video_height, HOOK_CAROUSEL_DURATION)
                
                # Audio cho carousel_quote
                sfx_dir = SFX_DIR
                reel = resolve_effect_sfx(hook_type, reel_key)
                ding = os.path.join(sfx_dir, DING_VARIANTS.get(reel_key, DEFAULT_DING))

                effective_volume = hook_sfx_volume
                if reel:
                    audio_placements.append((reel, 0.0, hook_sfx_level(reel_key, effective_volume), 0.0, HOOK_NARRATION_LEAD))
                if os.path.isfile(ding):
                    audio_placements.append((ding, SLOT_DURATION, hook_sfx_level("_ding", effective_volume), 0.0))
            
            elif hook_type == "blackout_question":
                hook_clip_overlay = build_blackout_question_hook(
                    hook_text, video_width, video_height, resolve_hook_timing(hook_type, hook_text)["duration"], cover_img
                )
                # LỖI CŨ: `options` không tồn tại ở đâu trong hàm này (biến đúng là
                # `kwargs`, dùng ở nhánh carousel_quote phía trên) — NameError 100% mỗi
                # khi chọn hiệu ứng này, bị try/except bên dưới nuốt lặng lẽ, hook mất
                # trắng không báo lỗi. Verify bằng cách chạy lại đúng dòng này độc lập.
                impact_sfx = resolve_effect_sfx(hook_type, reel_key)
                effective_volume = hook_sfx_volume
                if impact_sfx:
                    # Tăng mạnh âm thanh impact_boom. Chặn đuôi: file dài 3.1s trên cửa
                    # sổ 1.5s, thả tự do là cú nổ đè lên câu thoại đầu tiên.
                    audio_placements.append((
                        impact_sfx, 0.0, hook_sfx_level(reel_key, effective_volume), 0.0,
                        hook_sfx_max_dur(HOOK_EFFECTS[hook_type]["duration"]),
                    ))

            elif hook_type == "typewriter_quote":
                hook_dur = resolve_hook_timing(hook_type, hook_text)["duration"]
                hook_clip_overlay = build_typewriter_quote_hook(
                    hook_text, video_width, video_height, hook_dur, cover_img
                )
                
                typewriter_sfx = resolve_effect_sfx(hook_type, reel_key)
                effective_volume = hook_sfx_volume

                if typewriter_sfx:
                    # Cắt độ dài vừa khít với thời gian chữ chạy xong (85% của hook_dur)
                    audio_placements.append((typewriter_sfx, 0.0, hook_sfx_level(reel_key, effective_volume), 0.0, hook_dur * 0.85))
                
                # Thêm âm thanh gõ từng chữ (tick.wav) khớp với nhịp xuất hiện TextClip
                tick_sfx = os.path.join(SFX_DIR, "tick.wav")
                if os.path.isfile(tick_sfx):
                    words = hook_text.strip().split()
                    n_words = len(words)
                    steps = max(1, min(n_words, 24))
                    step_dur = (hook_dur * 0.85) / steps
                    
                    for i in range(steps):
                        # Giảm hệ số khuếch đại xuống 1.5 để volume UI tuyến tính hơn
                        audio_placements.append((tick_sfx, i * step_dur, hook_sfx_level("_tick", effective_volume), 0.0))

            elif hook_type == "breathing_vignette":
                hook_clip_overlay = build_breathing_vignette_hook(
                    cover_img, video_width, video_height, HOOK_EFFECTS[hook_type]["duration"],
                    quote_text=hook_text,
                )
                swell_sfx = resolve_effect_sfx(hook_type, reel_key)
                effective_volume = hook_sfx_volume
                if swell_sfx:
                    # Chặn đuôi RẤT quan trọng ở đây: ambient_mystic dài 19.7s trên cửa
                    # sổ 3.0s — gần 17 giây tiếng nền đè lên lời dẫn mở đầu.
                    audio_placements.append((
                        swell_sfx, 0.0, hook_sfx_level(reel_key, effective_volume), 0.0,
                        hook_sfx_max_dur(HOOK_EFFECTS[hook_type]["duration"]),
                    ))
                    
            elif hook_type == "camera_shutter":
                hook_clip_overlay = build_camera_shutter_hook(
                    cover_img, video_width, video_height, HOOK_EFFECTS[hook_type]["duration"],
                    quote_text=hook_text,
                )
                # LỖI CŨ: fallback là "tick.wav" — tiếng gõ của hook Máy Xèng, không liên
                # quan gì tới cú bấm máy ảnh. resolve_effect_sfx kéo mọi khoá sai về đúng
                # camera_shutter.mp3.
                shutter_sfx = resolve_effect_sfx(hook_type, reel_key)
                effective_volume = hook_sfx_volume
                if shutter_sfx:
                    audio_placements.append((
                        shutter_sfx, 0.0, hook_sfx_level(reel_key, effective_volume), 0.0,
                        hook_sfx_max_dur(HOOK_EFFECTS[hook_type]["duration"]),
                    ))
                    
            elif hook_type == "cyber_glitch":
                hook_clip_overlay = build_cyber_glitch_hook(
                    cover_img, video_width, video_height, HOOK_EFFECTS[hook_type]["duration"],
                    quote_text=hook_text,
                )
                # LỖI CŨ: fallback "whoosh.wav" — tiếng gió, không phải tiếng xẹt điện.
                glitch_sfx = resolve_effect_sfx(hook_type, reel_key)
                effective_volume = hook_sfx_volume
                if glitch_sfx:
                    audio_placements.append((
                        glitch_sfx, 0.0, hook_sfx_level(reel_key, effective_volume), 0.0,
                        hook_sfx_max_dur(HOOK_EFFECTS[hook_type]["duration"]),
                    ))
                    
            elif hook_type == "vintage_film_burn":
                hook_clip_overlay = build_vintage_film_burn_hook(
                    cover_img, video_width, video_height, HOOK_EFFECTS[hook_type]["duration"],
                    quote_text=hook_text,
                )
                # LỖI CŨ: fallback "suspense.wav" — nhạc hồi hộp, không phải tiếng máy chiếu.
                burn_sfx = resolve_effect_sfx(hook_type, reel_key)
                effective_volume = hook_sfx_volume
                if burn_sfx:
                    audio_placements.append((
                        burn_sfx, 0.0, hook_sfx_level(reel_key, effective_volume), 0.0,
                        hook_sfx_max_dur(HOOK_EFFECTS[hook_type]["duration"]),
                    ))
                
            if hook_clip_overlay:
                hook_clip_overlay = hook_clip_overlay.with_start(0.0).with_position("center")
                
        except Exception as e:
            # exc_info=True: trước đây chỉ log str(e), mất traceback — khi hook lỗi
            # (vd sai API MoviePy), video vẫn render xong NHƯNG không có hiệu ứng mở đầu
            # nào cả, và log cụt khiến không dò ra hàm/dòng nào gây lỗi.
            logger.error(f"Hook Engine Error ({hook_type}): {e}", exc_info=True)
            # KHÔNG để None trơn: main.py đã dời timeline theo resolve_hook_timing() từ
            # trước, nên bỏ trống lớp phủ = khán giả nhận đúng chừng ấy giây MÀN HÌNH ĐEN
            # ngay đầu video. Dựng lớp phủ tối giản lấp vào đúng cửa sổ đó.
            hook_clip_overlay = None
            try:
                from services.hook_engine import build_fallback_hook

                # KHÔNG dùng biến `cover_img`: nó được gán BÊN TRONG khối try, nên nếu lỗi
                # xảy ra trước dòng đó thì ở đây là UnboundLocalError — đúng loại bẫy mà
                # scripts/check_imports.py sinh ra để canh.
                _fb_cover = scene_assets[0]["image_path"] if scene_assets else None
                _fb_dur = (resolve_hook_timing(hook_type, hook_text) or {}).get("duration", 0.0)
                if _fb_dur > 0 and _fb_cover:
                    hook_clip_overlay = (
                        build_fallback_hook(_fb_cover, video_width, video_height, _fb_dur)
                        .with_start(0.0).with_position("center")
                    )
                    logger.warning(
                        "[Hook] '%s' hỏng — đã lấp %.2fs bằng lớp phủ tĩnh để tránh màn hình đen.",
                        hook_type, _fb_dur,
                    )
            except Exception as fb_err:
                logger.error("[Hook] Lớp phủ dự phòng cũng thất bại: %s", fb_err, exc_info=True)
            if on_fallback:
                try:
                    on_fallback(
                        f"⚠️ Hiệu ứng mở đầu '{hook_type}' gặp lỗi — đã thay bằng ảnh tĩnh "
                        f"để video không bị đen đầu. Xem backend/logs/render_worker.log."
                    )
                except Exception:
                    pass

    # Chốt TRƯỚC vòng lặp cảnh nào được phát SFX per-scene — xem plan_scene_sfx() và
    # SCENE_SFX_REPEAT_MIN_GAP / SCENE_SFX_FILLER_MIN_GAP ở nơi khai báo.
    _sfx_plan = plan_scene_sfx(
        [
            (str(a.get("sfx") or ""), a.get("start_time", 0.0) + hook_duration)
            for a in scene_assets
        ],
        exists=lambda n: os.path.isfile(os.path.join(SFX_DIR, f"{n}.wav")),
    )

    for _i, asset in enumerate(scene_assets):
        dur = asset.get("duration", 3.0)
        # KHÔNG mutate asset["start_time"] (gây cộng dồn nếu render lại + double-offset với
        # generate_ass_file). Chỉ dùng biến local; phụ đề tự cộng offset qua hook_effect.
        start_time = asset.get("start_time", 0.0) + hook_duration
        has_audio = bool(asset.get("audio_path"))
        
        # Audio ducking tracking
        if has_audio:
            speech_segments.append((start_time, start_time + dur))
            
        # ── Build Audio Track ──
        # QUAN TRỌNG: KHÔNG composite giọng đọc + SFX vào chung 1 clip. Composite chung khiến
        # MoviePy đọc SFX NGẮN (vd tick.wav 0.05s) vượt quá độ dài của nó khi giọng đọc dài hơn
        # → lỗi "Accessing time t=... with clip duration=...". Đặt mỗi thứ thành TRACK RIÊNG
        # trên timeline tổng; composite ngoài tôn trọng cửa sổ start/end nên không đọc quá.
        # Thu thập vị trí audio để TRỘN bằng numpy sau vòng lặp (xem _mix_audio_tracks).
        # Track giọng đọc (TTS) — fade-out nhẹ cuối để không cụt chữ.
        if has_audio and os.path.isfile(asset["audio_path"]):
            voice_entry = (asset["audio_path"], start_time, 1.0, AUDIO_FADEOUT_DURATION)
            audio_placements.append(voice_entry)
            voice_placements.append(voice_entry)

        # SFX chọn riêng cho từng cảnh giờ ĐÃ BỊ CHẶN bởi toggle global use_sfx
        # theo yêu cầu của user (không bật SFX thì tắt sạch tiếng xoẹt chuyển cảnh).
        sfx_name = str(asset.get("sfx") or "")
        if sfx_name and use_sfx and _i in _sfx_plan:
            # Đã qua plan_scene_sfx() phía trên: cảnh nằm trong _sfx_plan nghĩa là vừa
            # không bị chặn vừa CÓ file thật, không cần kiểm tra isfile lần nữa.
            sfx_path = os.path.join(SFX_DIR, f"{sfx_name}.wav")
            # Giảm âm lượng SFX chung để không thô/to lấn giọng đọc, kết hợp vol riêng của cảnh.
            # SCENE_SFX_GAIN cân bằng độ to GỐC giữa các file (xem chú thích ở khai báo) — SFX
            # tự người dùng tải lên (không có trong bảng) dùng mặc định 1.0, không có gì để
            # cân bằng theo vì chưa từng đo được RMS của chúng.
            scene_vol_ratio = asset.get("sfxVolume", 100) / 100.0
            gain = sfx_volume * SFX_MIX_GAIN * scene_vol_ratio * SCENE_SFX_GAIN.get(sfx_name, 1.0)
            # Biến tấu nhỏ mỗi lần phát, TÁI LẬP ĐƯỢC — xem scene_sfx_jitter().
            _gain_jitter, pitch_ratio = scene_sfx_jitter(output_path, _i, sfx_name)
            gain *= _gain_jitter
            audio_placements.append((
                sfx_path, start_time, gain, 0.0, None, pitch_ratio,
            ))

        final_duration = max(final_duration, start_time + dur)

    # ── Outro Engine ──
    outro_type = kwargs.get("outro_effect")
    outro_clip_overlay = None
    outro_duration = 0.0
    outro_start = final_duration

    if outro_type and outro_type != "none" and scene_assets:
        try:
            from services.hook_engine import (
                build_carousel_hook, SLOT_DURATION,
                build_blackout_question_hook,
                build_typewriter_quote_hook,
                build_breathing_vignette_hook,
                build_camera_shutter_hook,
                build_cyber_glitch_hook,
                build_vintage_film_burn_hook,
                build_cta_card_hook,
            )
            outro_cover_img = scene_assets[-1]["image_path"]
            outro_sfx_volume = kwargs.get("outro_sfx_volume", 1.0)
            outro_reel_key = kwargs.get("outro_reel_sfx", "none")
            
            # Ưu tiên user gõ tay > CTA Gemini sinh > câu hook. KHÔNG tự viết lại phép
            # chọn này ở đây: main.py và /api/timing-profile phải ra CÙNG một chuỗi, nếu
            # không thì 2 hiệu ứng outro có thời lượng động sẽ tính ra 2 con số khác nhau.
            outro_text = resolve_outro_text(
                kwargs.get("outro_text"), kwargs.get("cta_text"), hook_text
            )
            
            # Cùng một hàm mà main.py dùng để cộng outro vào tổng thời lượng — hai nơi
            # không thể lệch nhau. KHÔNG tính lại tay ở đây.
            outro_duration = (resolve_outro_timing(outro_type, outro_text) or {}).get("duration", 2.0)

            if outro_type == "carousel_quote":
                outro_clip_overlay = build_carousel_hook(outro_cover_img, outro_text, video_width, video_height, HOOK_CAROUSEL_DURATION)
                sfx_dir = SFX_DIR
                # Fallback tra NGƯỢC qua HOOK_REEL_SOUNDS, không gõ tay tên file: bản cũ
                # ghi "tick_wood.mp3" — một file KHÔNG TỒN TẠI ("tick_wood" là tên KHOÁ,
                # file thật của nó là reel_spin.wav. Vì có os.path.isfile() che nên khoá
                # lạ chỉ dẫn tới im lặng không tiếng, không lỗi nào.
                reel_sfx = resolve_effect_sfx(outro_type, outro_reel_key or DEFAULT_HOOK_REEL)
                whoosh_sfx = os.path.join(sfx_dir, "whoosh.wav")
                ding_sfx = os.path.join(sfx_dir, DING_VARIANTS.get(outro_reel_key, DEFAULT_DING))
                slot_dur = SLOT_DURATION
                # Mỗi tiếng chỉ được ngân tới hết cửa sổ outro (tính TỪ mốc nó bắt đầu),
                # cộng đuôi vang. Không chặn thì chúng chạy hết độ dài file và bị cắt cụt
                # thô ở mốc kết thúc video thay vì tắt mềm.
                if os.path.isfile(whoosh_sfx):
                    audio_placements.append((
                        whoosh_sfx, outro_start + 0.0, hook_sfx_level("_whoosh", outro_sfx_volume), 0.0,
                        hook_sfx_max_dur(outro_duration),
                    ))
                if reel_sfx:
                    audio_placements.append((
                        reel_sfx, outro_start + slot_dur, hook_sfx_level(outro_reel_key, outro_sfx_volume), 0.0,
                        hook_sfx_max_dur(outro_duration - slot_dur),
                    ))
                if os.path.isfile(ding_sfx):
                    audio_placements.append((
                        ding_sfx, outro_start + HOOK_CAROUSEL_DURATION - 0.5,
                        hook_sfx_level("_ding", outro_sfx_volume), 0.0,
                        hook_sfx_max_dur(0.5),
                    ))
            
            elif outro_type == "blackout_question":
                # LỖI CŨ: tham số thứ 5 là cover_image_path (ảnh nền mờ), nhưng chỗ này
                # truyền nhầm subtitle_font_size (một số nguyên, VD 75) — bên trong hàm
                # `if cover_image_path:` vẫn đúng (số khác 0 luôn truthy) nên KHÔNG lộ ra
                # bằng exception ở ĐÂY, mà nổ tận trong _blurred_fill_bg khi gọi
                # cover_path.endswith(...) trên một int, bị except ở đó nuốt gọn thành
                # WARNING rồi âm thầm rơi về nền đen phẳng — outro luôn mất ảnh bìa mờ
                # phía sau dù outro_cover_img (đã tính đúng ở trên) hoàn toàn hợp lệ.
                outro_clip_overlay = build_blackout_question_hook(
                    outro_text, video_width, video_height, outro_duration, outro_cover_img
                )
                impact_sfx = resolve_effect_sfx(outro_type, outro_reel_key)
                if impact_sfx:
                    audio_placements.append((impact_sfx, outro_start + 0.0, hook_sfx_level(outro_reel_key, outro_sfx_volume), 0.0, hook_sfx_max_dur(outro_duration)))
                    
            elif outro_type == "typewriter_quote":
                # instant=True: chữ hiện TRỌN NGAY, không gõ dần (xem chú thích ở
                # build_typewriter_quote_hook) — nên bỏ hẳn vòng lặp tick theo từng từ
                # bên dưới: không còn animation gõ để đồng bộ, tick vẫn nổ đều đặn trong
                # khi chữ đã đứng yên trên khung hình sẽ nghe rời rạc, vô nghĩa. LỖI CŨ
                # kèm theo: vòng lặp đó tính số từ theo `hook_text` (câu mở đầu) thay vì
                # `outro_text` (câu đang hiển thị) — bỏ luôn nhân tiện dọn theo.
                outro_clip_overlay = build_typewriter_quote_hook(
                    outro_text, video_width, video_height, outro_duration, outro_cover_img,
                    instant=True,
                )
                typewriter_sfx = resolve_effect_sfx(outro_type, outro_reel_key)
                if typewriter_sfx:
                    # Chỉ 1 tiếng gõ ngắn làm điểm nhấn lúc chữ xuất hiện, không kéo dài
                    # theo % thời lượng như bản hook (ở đó còn có pha gõ dần để ngân theo).
                    audio_placements.append((typewriter_sfx, outro_start + 0.0, hook_sfx_level(outro_reel_key, outro_sfx_volume), 0.0, hook_sfx_max_dur(0.6)))

            elif outro_type == "breathing_vignette":
                outro_clip_overlay = build_breathing_vignette_hook(
                    outro_cover_img, video_width, video_height, outro_duration,
                    quote_text=outro_text, quick_reveal=True,
                )
                swell_sfx = resolve_effect_sfx(outro_type, outro_reel_key)
                if swell_sfx:
                    audio_placements.append((swell_sfx, outro_start + 0.0, hook_sfx_level(outro_reel_key, outro_sfx_volume), 0.0, hook_sfx_max_dur(outro_duration)))
                    
            elif outro_type == "camera_shutter":
                outro_clip_overlay = build_camera_shutter_hook(
                    outro_cover_img, video_width, video_height, outro_duration,
                    quote_text=outro_text,
                )
                shutter_sfx = resolve_effect_sfx(outro_type, outro_reel_key)
                if shutter_sfx:
                    audio_placements.append((shutter_sfx, outro_start + 0.0, hook_sfx_level(outro_reel_key, outro_sfx_volume), 0.0, hook_sfx_max_dur(outro_duration)))
                    
            elif outro_type == "cyber_glitch":
                outro_clip_overlay = build_cyber_glitch_hook(
                    outro_cover_img, video_width, video_height, outro_duration,
                    quote_text=outro_text,
                )
                glitch_sfx = resolve_effect_sfx(outro_type, outro_reel_key)
                if glitch_sfx:
                    audio_placements.append((glitch_sfx, outro_start + 0.0, hook_sfx_level(outro_reel_key, outro_sfx_volume), 0.0, hook_sfx_max_dur(outro_duration)))
                    
            elif outro_type == "vintage_film_burn":
                outro_clip_overlay = build_vintage_film_burn_hook(
                    outro_cover_img, video_width, video_height, outro_duration,
                    quote_text=outro_text,
                )
                burn_sfx = resolve_effect_sfx(outro_type, outro_reel_key)
                if burn_sfx:
                    audio_placements.append((burn_sfx, outro_start + 0.0, hook_sfx_level(outro_reel_key, outro_sfx_volume), 0.0, hook_sfx_max_dur(outro_duration)))

            elif outro_type == "cta_card":
                # CHỈ dùng cho outro — không có nhánh hook_type tương ứng, xem chú
                # thích ở build_cta_card_hook (hook_engine.py).
                outro_clip_overlay = build_cta_card_hook(
                    outro_cover_img, outro_text, video_width, video_height, outro_duration,
                )
                cta_sfx = resolve_effect_sfx(outro_type, outro_reel_key)
                if cta_sfx:
                    audio_placements.append((cta_sfx, outro_start + 0.0, hook_sfx_level(outro_reel_key, outro_sfx_volume), 0.0, hook_sfx_max_dur(outro_duration)))

            if outro_clip_overlay:
                outro_clip_overlay = outro_clip_overlay.with_start(outro_start).with_position("center")
                final_duration += outro_duration
                
        except Exception as e:
            logger.error(f"Outro Engine Error ({outro_type}): {e}", exc_info=True)
            # KHÁC hook: outro nằm ở CUỐI video và độ dài của nó do chính khối này cộng
            # vào final_duration, nên đưa outro_duration về 0 là video kết thúc gọn ngay
            # sau cảnh cuối — không để lại khoảng trống nào. Đầu video thì không làm vậy
            # được: timeline đã bị main.py dời từ trước, phải lấp bằng lớp phủ tĩnh.
            #
            # Đánh đổi: main.py đã cộng outro_duration vào video_total_duration để vẽ
            # thanh tiến trình, nên thanh sẽ chạm 100% sớm vài giây. Chấp nhận được so
            # với việc treo một khung hình đứng im ở cuối.
            outro_clip_overlay = None
            outro_duration = 0.0
            if on_fallback:
                try:
                    on_fallback(
                        f"⚠️ Hiệu ứng kết thúc '{outro_type}' gặp lỗi — video sẽ kết thúc "
                        f"ngay sau cảnh cuối. Xem backend/logs/render_worker.log."
                    )
                except Exception:
                    pass

    # ══════════════════════════════════════════════════════════════════
    # ĐƯỜNG NHANH: dựng cả timeline bằng MỘT lệnh FFmpeg (xfade + NVENC).
    # Chỉ chạy được khi mọi cảnh đã là video đúng khung hình đích — điều mà
    # normalize_stock_clip/apply_ken_burns đã bảo đảm. Hỏng ở bất kỳ bước nào thì
    # rơi êm về MoviePy bên dưới, không làm chết render.
    # ══════════════════════════════════════════════════════════════════
    if kwargs.get("use_fast_assembly", True):
        try:
            from services import ffmpeg_assembler as fa
            ok, why = fa.can_assemble(scene_assets, video_width, video_height)
            if not ok:
                logger.info(f"[FastAssembly] Bỏ qua, dùng MoviePy: {why}")
            else:
                mixed = _mix_audio_tracks(_all_placements(audio_placements, master_audio_path,
                                                          final_duration), final_duration)
                audio_wav = None
                if mixed is not None:
                    audio_wav = output_path + ".mix.wav"
                    mixed.write_audiofile(audio_wav, fps=44100, logger=None)

                # Track chỉ-giọng cho ducking ở bước master. Ghi CẢ Ở ĐƯỜNG NHANH, nếu
                # không thì bật FastAssembly (mặc định) sẽ âm thầm mất sidechain và
                # ducking rơi về dùng track đã trộn lẫn SFX — đúng cái đang muốn tránh.
                write_voice_sidechain(
                    voice_placements, master_audio_path, final_duration, output_path
                )

                hook_mp4 = None
                if hook_clip_overlay is not None:
                    # Hook chỉ ~105 khung, để MoviePy dựng riêng ra file rồi FFmpeg phủ lên
                    hook_mp4 = output_path + ".hook.mp4"
                    hook_clip_overlay.write_videofile(
                        hook_mp4, fps=FPS, codec="libx264", preset="veryfast",
                        audio=False, logger=None,
                        temp_audiofile_path=TEMP_DIR,
                    )
                    
                outro_mp4 = None
                if outro_clip_overlay is not None:
                    outro_mp4 = output_path + ".outro.mp4"
                    outro_clip_overlay.write_videofile(
                        outro_mp4, fps=FPS, codec="libx264", preset="veryfast",
                        audio=False, logger=None,
                        temp_audiofile_path=TEMP_DIR,
                    )

                # LỖI CŨ #1: hardcode HOOK_CAROUSEL_DURATION (4.5s) ở đây bất kể hook_type
                # nào đang chạy — chọn blackout_question (1.5s thật) vẫn khiến FFmpeg giữ
                # khoảng trống 4.5s, thừa 3s đứng hình trước khi vào Cảnh 1.
                # LỖI CŨ #2: sau khi thêm thời lượng ĐỘNG cho blackout/typewriter
                # (resolve_hook_timing), tra thẳng HOOK_EFFECTS[...]["duration"] tĩnh ở đây
                # sẽ ra một con số KHÁC với con số đã dùng để dựng hook_clip_overlay phía
                # trên — hook thật dài X giây nhưng FFmpeg chỉ mở khung che hình đúng
                # HOOK_EFFECTS-tĩnh giây, lệch hình/tiếng ngay tại điểm nối. Phải gọi lại
                # ĐÚNG HÀM, ĐÚNG THAM SỐ như lúc dựng clip để 2 nơi luôn khớp nhau.
                # Dùng hook_text (không phải hook_quote): đây là field thật sự quyết định
                # thời lượng động của blackout_question/typewriter_quote (xem sửa ở trên).
                # carousel_quote/breathing_vignette bỏ qua tham số text này (thời lượng
                # tĩnh) nên truyền hook_text ở đây vô hại cho 2 loại đó.
                _timing = resolve_hook_timing(hook_type, hook_text) or {}
                fa.assemble(
                    scene_assets, output_path,
                    width=video_width, height=video_height, fps=FPS,
                    crossfade_dur=crossfade_dur, audio_path=audio_wav,
                    hook_video=hook_mp4,
                    hook_duration=_timing.get("duration", 0.0),
                    outro_video=outro_mp4,
                    outro_start=outro_start,
                    outro_duration=outro_duration,
                    use_gpu=kwargs.get("use_gpu_encode", True),
                )
                for tmp_f in (audio_wav, hook_mp4, outro_mp4):
                    if tmp_f and os.path.exists(tmp_f):
                        try:
                            os.remove(tmp_f)
                        except OSError:
                            pass
                if hook_clip_overlay is not None:
                    hook_clip_overlay.close()
                if outro_clip_overlay is not None:
                    outro_clip_overlay.close()
                return output_path
        except Exception as fast_err:
            # ERROR + traceback, KHÔNG phải warning. Đây không phải nhánh dự phòng đã
            # biết trước nguyên nhân (như Veo hết quota hay Pexels 403) — nó nghĩa là
            # đường render mặc định đang HỎNG. Job vẫn ra video nên không ai để ý, chỉ
            # là chậm gấp ~100 lần: 19 cảnh mất 30-45 phút thay vì 15-20 giây.
            # Chính vì trước đây chỉ là một dòng warning mà lỗi lệch index input sống sót
            # qua cả một bản bàn giao mà không ai phát hiện.
            logger.error(
                "[FastAssembly] Thất bại — đang quay về MoviePy (chậm hơn ~100 lần): %s",
                fast_err, exc_info=True,
            )
            if on_fallback:
                try:
                    on_fallback(
                        "⚠️ Đường render nhanh không dùng được, đang dựng bằng cách chậm — "
                        "video sẽ lâu hơn nhiều bình thường. Xem backend/logs/render_worker.log."
                    )
                except Exception:
                    pass  # báo được thì tốt, không báo được cũng không làm hỏng render

    # ── Đường chậm (MoviePy) — giữ nguyên làm lưới an toàn ──
    # CÙNG một kế hoạch chữ nhấn với đường nhanh (ffmpeg_assembler): hai đường ra hai kết
    # quả khác nhau thì bật/tắt FastAssembly lại đổi cả nội dung hiển thị.
    from services.motion_effects import plan_scene_highlights
    _hl_plan = plan_scene_highlights(scene_assets)

    for i, asset in enumerate(scene_assets):
        start_time = asset.get("start_time", 0.0) + hook_duration
        # Transition của scene[i] nghĩa là "chuyển cảnh SANG cảnh sau" (đúng như UI).
        # Biên i→i+1 hiển thị qua LỐI VÀO của cảnh i+1, nên lối vào của cảnh hiện tại
        # phải dùng transition của cảnh TRƯỚC nó (sửa off-by-one: trước đây cảnh 0 bị bỏ).
        entrance_transition = scene_assets[i - 1].get("transition", "crossfade") if i > 0 else "crossfade"

        c = _build_scene_clip(
            asset,
            add_crossfade_in=(i > 0),
            video_width=video_width,
            video_height=video_height,
            crossfade_dur=crossfade_dur,
            show_subtitle=show_subtitle,
            subtitle_font_size=subtitle_font_size,
            subtitle_color=subtitle_color,
            transition=entrance_transition,
            highlight_start=_hl_plan.get(i),
        )

        clips.append(c.with_start(start_time))

    final = CompositeVideoClip(clips, size=(video_width, video_height)).with_duration(final_duration)

    # Chế độ đọc liền mạch (Single-Pass Narration): cả bài chỉ có 1 dải giọng duy nhất,
    # đặt tại mốc 0.0 như một track nữa trên timeline.
    # TRƯỚC ĐÂY nhánh này gọi `final.with_audio(master_audio)` SAU khi đã trộn xong —
    # tức là THAY TRẮNG toàn bộ track vừa trộn, xoá sạch SFX từng cảnh lẫn tiếng Máy Xèng
    # mở màn. Giờ nó tham gia vào cùng một lần trộn nên mọi thứ cùng vang lên.
    write_voice_sidechain(voice_placements, master_audio_path, final_duration, output_path)
    slow_placements = _all_placements(audio_placements, master_audio_path, final_duration)
    if master_audio_path and os.path.exists(master_audio_path):
        speech_segments = [(0.0, final_duration)]

    # Trộn toàn bộ audio (giọng đọc + SFX) bằng numpy → 1 track duy nhất (an toàn, không bug)
    if slow_placements:
        final_audio = _mix_audio_tracks(slow_placements, final_duration)
        if final_audio is not None:
            final = final.with_audio(final_audio)

    # BGM mixing now happens via FFmpeg in audio_mix_service.py

    # ── OVERLAYS còn lại trong MoviePy ──
    # CHỈ hook carousel ở đây, vì nó là clip động thật sự.
    # Vignette và thanh tiến trình ĐÃ CHUYỂN sang bước FFmpeg cuối (audio_mix_service):
    # cả hai phủ lên TOÀN BỘ video nên MoviePy phải trộn chúng ở mọi khung hình bằng
    # Python — đo thực tế mất 1.93 lần tốc độ (6.83 fps → 3.54 fps). FFmpeg làm cùng việc
    # đó bằng C, trong chính lượt encode vốn đã phải chạy, nên gần như miễn phí.
    if hook_clip_overlay is not None or outro_clip_overlay is not None:
        overlays = [final]
        if hook_clip_overlay is not None:
            overlays.append(hook_clip_overlay)
        if outro_clip_overlay is not None:
            overlays.append(outro_clip_overlay)
        final = CompositeVideoClip(
            overlays, size=(video_width, video_height)
        ).with_duration(final_duration).with_audio(final.audio)

    final.write_videofile(
        output_path,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        threads=os.cpu_count() or 4,
        preset="veryfast",   # bản RAW trung gian — sẽ bị encode lại ở bước master,
                             # nên "medium" chỉ tốn CPU cho một file dùng một lần rồi bỏ
        logger=progress_logger,
        # Không có dòng này, MoviePy đổ file tạm audio vào CWD (backend/) và để lại
        # hàng chục MB rác mang tên "<job_id>.mp4.rawTEMP_MPY_wvf_snd.mp4".
        temp_audiofile_path=TEMP_DIR,
    )

    # Giải phóng tài nguyên ngay sau khi render xong (giảm áp lực RAM)
    def _close_clip_recursive(clip):
        if not clip: return
        if hasattr(clip, "clips"): # CompositeVideoClip/CompositeAudioClip
            for subclip in clip.clips:
                _close_clip_recursive(subclip)
        try: clip.close()
        except: pass

    for c in clips:
        _close_clip_recursive(c)
    _close_clip_recursive(final)

    return output_path


# ─────────────────────────────────────────────────────────────────────
# SRT generation
# ─────────────────────────────────────────────────────────────────────
def _strip_emoji_for_subtitle(text: str) -> str:
    """Xóa triệt để emoji/icons khỏi text phụ đề để tránh hiện ký tự lạ trong video."""
    # Dải chính: Supplementary Multilingual Plane (hầu hết emoji hiện đại)
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    # Dải phụ: Miscellaneous Symbols, Dingbats, Misc Technical, Arrows, etc.
    text = re.sub(r'[\u2600-\u27ff\u2300-\u23ff\u2B50-\u2B55\u2B06\u2934\u2935\u200d\ufe0f\u00a9\u00ae\u203c\u2049\u2122\u2139\u2194-\u21aa\u231a-\u231b\u25aa-\u25fe\u2702-\u27b0\u3030\u303d\u3297\u3299]', '', text)
    return text.strip()


def generate_ass_file(scene_assets: List[SceneAsset], output_path: str, mode: str = "storyteller", subtitle_style: str = "karaoke_bold", hook_text: str = None, hook_effect: str = "word_by_word", video_width: int = 1080, video_height: int = 1920) -> str:
    """
    Sinh file phụ đề .ass (Advanced SubStation Alpha).
    Hỗ trợ 2 phong cách:
    - karaoke_bold: Viền dày, hiệu ứng nảy (pop-in), màu vàng nổi bật, tự động in hoa.
    - cinematic_box: Chữ trắng trên nền hộp mờ (box/backdrop) kéo ngang, tĩnh, chữ thường.

    video_width/height: khung hình THẬT của video sẽ bị burn phụ đề lên.
    """
    # ── PlayRes PHẢI khớp khung hình thật ──
    # LỖI CŨ: PlayRes ghi cứng 1080x1920 dù người dùng chọn 16:9 (1920x1080) hay 1:1.
    # libass co giãn hệ toạ độ PlayRes sang khung thật, mà phép co giãn đó KHÔNG đồng
    # đều khi tỉ lệ lệch nhau: với video 16:9 chữ bị kéo ngang 1.78x và nén dọc 0.56x
    # → méo hẳn, sai cả vị trí lẫn cỡ. Đã bắt được trên sản phẩm thật trong assets/output.
    REF_W, REF_H = 1080, 1920   # khung tham chiếu mà toàn bộ cỡ chữ/viền/lề dưới đây được căn theo
    sw = video_width / REF_W    # lề trái/phải: theo chiều NGANG
    sh = video_height / REF_H   # cỡ chữ, viền, bóng, lề dọc: theo chiều DỌC (chuẩn của phụ đề)

    def _s(v, k=None):
        """Quy đổi một giá trị thiết kế sang khung hiện tại. Giữ nguyên số 0 (Outline=0
        của minimal_white là cố ý, không được làm tròn thành 1)."""
        if not v:
            return 0
        return max(1, int(round(v * (sh if k is None else k))))

    def _wrap_w(n: int) -> int:
        """Số ký tự mỗi dòng: theo chiều NGANG. Khung rộng hơn thì xuống dòng thưa hơn,
        nếu không video 16:9 sẽ hiện một cột chữ hẹp lọt thỏm giữa màn hình."""
        return max(8, int(round(n * sw)))

    ass_content = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {video_width}",
        f"PlayResY: {video_height}",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
    ]
    
    # ── ĐỊNH NGHĨA STYLE DỰA TRÊN USER SETTING ──
    if subtitle_style == "cinematic_box":
        font_name = SUBTITLE_FONT_NAME  # Font dày, hiện đại, phủ đủ tiếng Việt
        font_size = _s(55)
        primary_color = "&H00FFFFFF"     # White
        secondary_color = "&H00FFFFFF"
        outline_color = "&H00000000"     # No outline needed
        back_color = "&H99000000"        # Semi-transparent black (99 is alpha)
        # BorderStyle=3 (Opaque box), Outline=8 (Box padding/margin)
        style_line = f"Style: Default,{font_name},{font_size},{primary_color},{secondary_color},{outline_color},{back_color},-1,0,0,0,100,100,0,0,3,{_s(8)},0,2,{_s(60, sw)},{_s(60, sw)},{_s(250)},1"
    elif subtitle_style == "minimal_white":
        font_name = SUBTITLE_FONT_NAME
        font_size = _s(50)
        primary_color = "&H00FFFFFF"     # White
        secondary_color = "&H00FFFFFF"
        outline_color = "&H00000000"
        back_color = "&H66000000"        # Soft shadow (alpha 66)
        # BorderStyle=1 (Outline), Outline=0, Shadow=3
        style_line = f"Style: Default,{font_name},{font_size},{primary_color},{secondary_color},{outline_color},{back_color},0,0,0,0,100,100,0,0,1,0,{_s(3)},2,{_s(40, sw)},{_s(40, sw)},{_s(250)},1"
    else: # karaoke_bold & hormozi_bold (Default)
        # Font dày cho cảm giác Cinematic, phủ đủ tiếng Việt (xem SUBTITLE_FONT_NAME).
        font_name = SUBTITLE_FONT_NAME
        font_size = _s(65 if mode == "quiz_listicle" else 75)
        primary_color = "&H0000FFFF"     # Yellow highlight
        secondary_color = "&H00FFFFFF"   # White base
        outline_color = "&H00000000"     # Black outline
        back_color = "&H00000000"        # Black shadow
        # BorderStyle=1 (Outline), Outline=6, Shadow=4
        style_line = f"Style: Default,{font_name},{font_size},{primary_color},{secondary_color},{outline_color},{back_color},-1,0,0,0,100,100,0,0,1,{_s(6)},{_s(5)},2,{_s(40, sw)},{_s(40, sw)},{_s(500)},1"

    ass_content.append(style_line)

    # ── HOOK STYLE (cho Tiêu đề 3s đầu) ──
    # Chữ to, vàng, nằm ở top (MarginV=150)
    hook_style_line = f"Style: HookTitle,{SUBTITLE_FONT_NAME},{_s(75)},&H0000FFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,{_s(8)},{_s(5)},8,{_s(40, sw)},{_s(40, sw)},{_s(150)},1"
    ass_content.append(hook_style_line)
    
    ass_content.append("")
    ass_content.append("[Events]")
    ass_content.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")

    def format_ass_time(td):
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        centiseconds = int(td.microseconds / 10000)
        return f"{hours:01d}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"

    # Add hook_text (duration 3 seconds max)
    # LỖI CŨ: chỉ loại trừ "carousel_quote" — khi Hook Engine có thêm 3 loại mới
    # (blackout_question/typewriter_quote/breathing_vignette), cả 3 đều != "carousel_quote"
    # nên vẫn lọt qua đây và bị burn THÊM 1 lớp phụ đề word_by_word (nhánh else mặc định
    # bên dưới) chồng lên Cảnh 1 — ngay cả khi hook_text đã được dùng đúng chỗ của nó
    # (blackout/typewriter tự vẽ chữ trong chính clip overlay của chúng rồi). Loại trừ
    # TOÀN BỘ hook_effect do HOOK_EFFECTS quản lý; chỉ còn lọt qua các giá trị legacy
    # thật sự (word_by_word/full_shake — không còn hiện trong dropdown UI nhưng vẫn có
    # thể tồn tại trong preset/project cũ) hoặc giá trị lạ/không xác định.
    if hook_text and hook_text.strip() and hook_effect not in HOOK_EFFECTS:
        import textwrap
        wrapped_hook = "\\N".join(textwrap.wrap(hook_text.strip().upper(), width=_wrap_w(16)))
        
        if hook_effect == "full_shake":
            # Effect: fade in 200ms, fade out 500ms, start large and scale down (bounce)
            hook_ass = f"{{\\fad(200,500)\\fscx130\\fscy130\\t(0,200,\\fscx100\\fscy100)}}{wrapped_hook}"
            ass_content.append(f"Dialogue: 1,0:00:00.00,0:00:03.00,HookTitle,,0,0,0,,{hook_ass}")
        else: # word_by_word
            # Generate cumulative lines for word-by-word pop-in
            words = hook_text.strip().upper().split()
            word_dur = 0.25 # pop a new word every 0.25s
            
            # Since ASS requires manual positioning if we pop word by word, the easiest way 
            # to do word-by-word popping without changing position is to use \alpha
            # But standard ASS supports {\alpha&HFF&} for transparent text.
            # We can write the FULL string, but set the upcoming words to transparent!
            
            for i in range(len(words)):
                start_s = i * word_dur
                if start_s >= 2.5: break # don't start appearing too late
                end_s = 3.0
                
                start_td = dt.timedelta(seconds=start_s)
                end_td = dt.timedelta(seconds=end_s)
                
                # Cắt chuỗi làm 2 phần: phần đã hiện (từ 0 đến i), phần chưa hiện (từ i+1 trở đi)
                # Phần đã hiện thì giữ nguyên. Từ đang hiện thì nảy to. Phần chưa hiện thì ẩn (alpha FF).
                
                text_parts = []
                for j, w in enumerate(words):
                    if j < i:
                        text_parts.append(w)
                    elif j == i:
                        text_parts.append(f"{{\\fscx150\\fscy150\\t(0,100,\\fscx100\\fscy100)}}{w}{{\\fscx100\\fscy100}}")
                    else:
                        text_parts.append(f"{{\\alpha&HFF&}}{w}{{\\alpha}}")
                
                full_text = " ".join(text_parts)
                # Apply word wrapping (we should replace space with \N manually based on length, or just keep it simple)
                import textwrap
                # Tricky to textwrap when there are tags. Let's just do a simple replacement.
                # Since hook text is short, we can rely on standard spacing or manual break
                
                fad_tag = r"{\fad(100,500)}" if i == 0 else r"{\fad(0,500)}"
                full_text_formatted = full_text.replace(r"{\alpha}", r"{\alpha&H00&}")
                
                event_line = f"Dialogue: 1,{format_ass_time(start_td)},{format_ass_time(end_td)},HookTitle,,0,0,0,,{fad_tag}{full_text_formatted}"
                ass_content.append(event_line)

    # Hook carousel_quote giờ đã được chuyển thành OVERLAY, không đẩy lùi thời gian video nữa.
    # Do đó hook_offset luôn = 0.0 để lồng tiếng và phụ đề Cảnh 1 bắt đầu ngay từ 0.0s.
    hook_offset = 0.0

    cursor = 0.0
    for _idx, asset in enumerate(scene_assets):
        duration = asset["duration"]
        # Dùng đúng mốc thời gian tuyệt đối (start_time đã tính overlap crossfade trong
        # build_scene_timeline) để phụ đề khớp 100% với giọng đọc. Trước đây hàm này tự
        # cộng dồn `cursor += duration` KHÔNG trừ overlap → phụ đề lệch dần theo số cảnh.
        scene_start = asset.get("start_time")
        if scene_start is None:
            scene_start = cursor
        scene_start += hook_offset

        # Phụ đề phải TẮT trước khi cảnh sau bắt đầu.
        # LỖI CŨ: end = scene_start + duration, mà `duration` đã bao gồm phần chồng lấn
        # crossfade (start_{i+1} = start_i + dur_i - overlap). Hệ quả: ở MỌI chuyển cảnh có
        # đúng `overlap` giây mà HAI khối phụ đề cùng hiển thị, chồng đè lên nhau — với
        # style hộp mờ thì thành hai hộp đen chồng nhau, rất lộ.
        scene_end = scene_start + duration
        if _idx + 1 < len(scene_assets):
            next_start = scene_assets[_idx + 1].get("start_time")
            if next_start is not None:
                scene_end = min(scene_end, next_start + hook_offset)

        display_text = asset.get("subtitle_text") or asset.get("source_quote") or asset.get("text")
        if display_text and display_text.strip():
            start_td = dt.timedelta(seconds=scene_start)
            end_td = dt.timedelta(seconds=scene_end)

            start_str = format_ass_time(start_td)
            end_str = format_ass_time(end_td)
            
            # Xử lý Text & Effect
            pop_effect = r"{\fscx30\fscy30\t(0,100,\fscx150\fscy150)\t(100,250,\fscx100\fscy100)}"
            word_boundaries = asset.get("word_boundaries", [])
            
            if subtitle_style == "cinematic_box":
                # Tĩnh, không pop-in, không highlight từng từ
                import textwrap
                raw_text = _strip_emoji_for_subtitle(display_text).replace('\n', ' ')
                wrapped = "\\N".join(textwrap.wrap(raw_text, width=_wrap_w(32)))
                ass_text = wrapped
            elif subtitle_style == "minimal_white":
                # Tĩnh chữ trắng nhỏ, có hiệu ứng fade nhẹ 200ms
                import textwrap
                raw_text = _strip_emoji_for_subtitle(display_text).replace('\n', ' ')
                wrapped = "\\N".join(textwrap.wrap(raw_text, width=_wrap_w(35)))
                ass_text = f"{{\\fad(200,200)}}{wrapped}"
            else:
                # Karaoke & Hormozi Style (có highlight, pop-in)
                if word_boundaries:
                    def _chunk_word_boundaries(wbs, max_chars=14):
                        chunks = []
                        curr = []
                        curr_len = 0
                        for w in wbs:
                            if curr_len + len(w["text"]) > max_chars and curr:
                                chunks.append(curr)
                                curr = []
                                curr_len = 0
                            curr.append(w)
                            curr_len += len(w["text"]) + 1
                        if curr:
                            chunks.append(curr)
                        return chunks

                    chunks = _chunk_word_boundaries(word_boundaries, max_chars=14)
                    import random
                    hormozi_colors = ["&H0000FFFF", "&H000000FF", "&H0000FF00", "&H0000A5FF"] # Yellow, Red, Green, Orange
                    _VN_STOPWORDS = {
                        "CỦA", "VÀ", "LÀ", "CÓ", "CHO", "ĐỂ", "MỘT", "CÁC", "NHỮNG",
                        "TRONG", "KHÔNG", "ĐƯỢC", "NÀY", "ĐÓ", "VỚI", "TRÊN", "THEO",
                        "NHƯ", "HAY", "HOẶC", "NHƯNG", "TỪ", "ĐẾN", "VỀ", "BỞI",
                        "CŨNG", "ĐÃ", "SẼ", "ĐANG", "VẪN", "MÀ", "THÌ", "KHI",
                        "NẾU", "HƠN", "RẤT", "QUÁ", "BẠN", "TÔI", "ĐI", "LẠI",
                        "RA", "LÊN", "XUỐNG", "VÀO", "SAU", "TRƯỚC", "NÊN", "CHỈ",
                        "CÒN", "HAI", "BA", "BỐN", "NĂM",
                    }

                    for chunk in chunks:
                        # chunk_start = offset of first word, chunk_end = offset + duration of last word
                        chunk_start_td = dt.timedelta(seconds=scene_start + chunk[0]["offset"])
                        # Kẹp về scene_end để chunk cuối không tràn sang phụ đề cảnh sau
                        chunk_end_td = dt.timedelta(
                            seconds=min(
                                scene_start + chunk[-1]["offset"] + chunk[-1]["duration"],
                                scene_end,
                            )
                        )
                        chunk_start_str = format_ass_time(chunk_start_td)
                        chunk_end_str = format_ass_time(chunk_end_td)

                        ass_text = pop_effect
                        for i, wb in enumerate(chunk):
                            dur_cs = max(1, int(wb["duration"] * 100))
                            text = wb["text"].upper()
                            prefix = " " if i > 0 else ""
                            if text.startswith(" "):
                                prefix = " "
                                text = text.strip()

                            is_strong = (
                                len(text) > 2
                                and text not in _VN_STOPWORDS
                            ) or any(p in text for p in ['!', '?'])
                            
                            if is_strong:
                                color = random.choice(hormozi_colors) if subtitle_style == "hormozi_bold" else "&H0000FFFF"
                                ass_text += f"{prefix}{{\\K{dur_cs}\\c{color}\\fscx130\\fscy130\\t(0,{dur_cs*10},\\fscx100\\fscy100)}}{text}{{\\c&H0000FFFF\\fscx100\\fscy100}}"
                            else:
                                ass_text += f"{prefix}{{\\K{dur_cs}}}{text}"
                        
                        event_line = f"Dialogue: 0,{chunk_start_str},{chunk_end_str},Default,,0,0,0,,{ass_text}"
                        ass_content.append(event_line)
                else:
                    import textwrap
                    text_val = _strip_emoji_for_subtitle(display_text).replace('\n', ' ').upper()
                    wrapped = "\\N".join(textwrap.wrap(text_val, width=_wrap_w(28)))
                    ass_text = f"{pop_effect}{wrapped}"
                    event_line = f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{ass_text}"
                    ass_content.append(event_line)
            
            if subtitle_style in ("cinematic_box", "minimal_white"):
                event_line = f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{ass_text}"
                ass_content.append(event_line)
            
        cursor += duration

    with open(output_path, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(ass_content))

    return output_path



# ─────────────────────────────────────────────────────────────────────
# BGM listing helper
# ─────────────────────────────────────────────────────────────────────
def get_available_bgm() -> List[dict]:
    """Trả về danh sách nhạc nền có sẵn trong assets/bgm/."""
    if not os.path.isdir(BGM_DIR):
        return []

    bgm_list = []
    LABELS = {
        "chill_lofi": "Chill Lo-Fi",
        "epic_cinematic": "Epic Cinematic",
        "upbeat_pop": "Upbeat Pop",
        "soft_piano": "Soft Piano",
        "corporate_minimal": "Corporate Minimal",
        "livin_easy_oliver_massa_main": "Livin Easy (Oliver Massa)",
        "Back_When": "Back When",
    }

    for fname in sorted(os.listdir(BGM_DIR)):
        if fname.lower().endswith((".mp3", ".wav", ".ogg")):
            name_key = os.path.splitext(fname)[0]
            bgm_list.append({
                "id": fname,
                "name": LABELS.get(name_key, name_key.replace("_", " ").title()),
                "path": os.path.join(BGM_DIR, fname),
            })

    return bgm_list
