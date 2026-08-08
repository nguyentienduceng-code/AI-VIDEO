"""
scene_balancer.py — Chia lại ranh giới cảnh cho đều nhịp, KHÔNG viết lại một chữ nào.

VẤN ĐỀ
------
Gemini chia cảnh theo ý nghĩa nội dung, không theo đồng hồ. Kết quả thường gặp: cảnh 3
gánh một câu 11 giây (một ảnh đứng yên 11 giây — người xem bỏ đi), trong khi cảnh 7 chỉ
có "Và rồi mọi thứ sụp đổ." dài 1.4 giây (ảnh chớp qua chưa kịp nhìn). Tổng thời lượng
có thể vẫn đúng mục tiêu, nên mọi cảnh báo dựa trên TỔNG số từ đều không thấy gì bất
thường — vấn đề nằm ở PHÂN BỔ.

CÁCH GIẢI
---------
Gộp toàn bộ lời thoại thành một dãy câu, rồi chia dãy đó thành K nhóm liên tiếp sao cho
các nhóm gần với nhịp lý tưởng nhất. Đây là bài toán linear partition, giải đúng bằng
quy hoạch động — KHÔNG phải heuristic tham lam, và không cần gọi LLM: cùng đầu vào luôn
cho cùng đầu ra, chạy trong vài mili giây, không tốn quota.

Vì chỉ DI CHUYỂN ranh giới chứ không sửa chữ, nội dung và giọng văn giữ nguyên tuyệt đối.

RÀNG BUỘC MỀM, KHÔNG CỨNG
-------------------------
Một câu đơn lẻ dài 11 giây thì không ranh giới nào cứu được — ràng buộc cứng sẽ làm bài
toán vô nghiệm và hàm phải ném lỗi giữa lúc user đang chờ. Nên trần/sàn được cài dưới
dạng PHẠT trong hàm chi phí: luôn có lời giải, và lời giải tự động dồn phần vi phạm vào
đúng chỗ không thể tránh, thay vì rải đều ra mọi cảnh.
"""
from __future__ import annotations

import logging
import math
import re

logger = logging.getLogger(__name__)

# Nhịp xem — phải khớp SHOT_MIN_S/SHOT_MAX_S trong ScriptEditor.jsx.
MIN_SHOT_S = 2.5
MAX_SHOT_S = 6.5
IDEAL_SHOT_S = 4.5

# Hệ số phạt khi vượt trần/dưới sàn. Đủ lớn để lệch nhịp bị ưu tiên sửa trước, nhưng
# không vô hạn — vô hạn thì bài toán vô nghiệm ở kịch bản có câu dài bất khả phân.
_PENALTY = 25.0

MAX_SCENES = 75  # khớp gemini_service.MAX_SCENES (Podcast / Long-form)

# Khi một cảnh gốc bị tách làm nhiều cảnh, tất cả đều thừa kế CÙNG một image_prompt —
# và ba ảnh sinh từ cùng một mô tả thì nhìn như nhau, người xem tưởng video bị đứng
# hình. Thêm góc máy khác nhau vào các phần sau để cùng một bối cảnh được nhìn từ nhiều
# hướng: rẻ hơn nhiều so với nhờ LLM viết prompt mới, và giữ nguyên nội dung mô tả.
# Phần ĐẦU TIÊN luôn giữ prompt gốc y nguyên — đó là khung hình đạo diễn đã chọn.
_SHOT_VARIANTS = (
    "wide establishing shot",
    "close-up detail",
    "low angle shot",
    "over-the-shoulder view",
    "high angle shot",
)

# Tách câu: sau dấu kết câu + khoảng trắng, hoặc xuống dòng. Giữ nguyên dấu câu.
_SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+|\n+")

# Tách mệnh đề — CHỈ dùng cho câu đơn dài hơn cả trần một cảnh, khi không còn ranh giới
# câu nào để cắt. Cắt sau dấu phẩy/chấm phẩy/hai chấm/gạch ngang, tức đúng những chỗ
# người đọc vốn đã ngắt hơi.
#
# ĐÁNH ĐỔI phải biết: mỗi cảnh là một lần gọi TTS riêng, nên cắt giữa câu tạo một nhịp
# ngắt trong giọng đọc mà bản gốc không có. Ở dấu phẩy thì nhịp đó nghe tự nhiên, nhưng
# vẫn là thay đổi có thể nghe thấy — vì vậy chỉ động tới câu đã vượt trần, nơi lựa chọn
# duy nhất còn lại là để một ảnh đứng yên hơn 6.5 giây.
_CLAUSE_RE = re.compile(r"(?<=[,;:–—])\s+")


class _Unit:
    """Một câu — đơn vị nhỏ nhất mà ranh giới cảnh được phép cắt vào."""

    __slots__ = ("text", "source_idx", "seconds", "hard_start", "atomic")

    def __init__(self, text: str, source_idx: int, seconds: float,
                 hard_start: bool = False, atomic: bool = False):
        self.text = text
        self.source_idx = source_idx      # cảnh gốc, để giữ lại image_prompt/emotion
        self.seconds = seconds
        self.hard_start = hard_start      # buộc mở đầu một cảnh mới
        self.atomic = atomic              # cả cảnh là một khối, không được trộn


def _is_untouchable(scene: dict) -> bool:
    """Cảnh không được phép gộp/tách với cảnh khác.

    - override_asset: user đã tự tay gắn ảnh/video cho ĐÚNG đoạn lời này; gộp sang cảnh
      khác là làm hỏng chủ ý rõ ràng của họ.
    - quote_card: không có giọng đọc, chữ hiển thị là chính nội dung — trộn vào cảnh kể
      chuyện thì mất luôn ý nghĩa của loại cảnh này.
    """
    return bool(scene.get("override_asset")) or scene.get("scene_type") == "quote_card"


def _split_units(scenes: list[dict], voice: str | None, rate: str | None) -> list[_Unit]:
    from services import duration_model

    units: list[_Unit] = []
    for idx, scene in enumerate(scenes):
        text = (scene.get("text") or "").strip()
        pause_s = (scene.get("pause_after_ms") or 0) / 1000.0

        if _is_untouchable(scene) or not text:
            units.append(_Unit(
                text=text,
                source_idx=idx,
                seconds=duration_model.estimate_duration(text, voice, rate) + pause_s,
                hard_start=True,
                atomic=True,
            ))
            continue

        sentences = [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]
        if not sentences:
            sentences = [text]

        # Câu nào dài hơn cả một cảnh thì cắt tiếp tại mệnh đề, nếu không nó sẽ một
        # mình chiếm trọn một cảnh vượt trần và không thuật toán nào cứu được.
        pieces: list[str] = []
        for sentence in sentences:
            pieces.extend(_split_long_sentence(sentence, voice, rate))

        for i, piece in enumerate(pieces):
            # pause_after_ms là khoảng lặng CUỐI cảnh, chỉ thuộc về mảnh cuối cùng.
            extra = pause_s if i == len(pieces) - 1 else 0.0
            units.append(_Unit(
                text=piece,
                source_idx=idx,
                seconds=duration_model.estimate_duration(piece, voice, rate) + extra,
                hard_start=(i == 0 and idx > 0 and _is_untouchable(scenes[idx - 1])),
            ))
    return units


def _split_long_sentence(sentence: str, voice: str | None, rate: str | None) -> list[str]:
    """Cắt một câu quá dài tại ranh giới mệnh đề. Trả về [sentence] nếu không cắt được.

    Gom tham lam chứ không tối ưu: các mảnh sau đó vẫn đi qua quy hoạch động chung ở
    _partition, nên chỉ cần chúng đủ nhỏ để thuật toán còn chỗ xoay xở.
    """
    from services import duration_model

    if duration_model.estimate_duration(sentence, voice, rate) <= MAX_SHOT_S:
        return [sentence]

    clauses = [c.strip() for c in _CLAUSE_RE.split(sentence) if c.strip()]
    if len(clauses) < 2:
        return [sentence]  # câu dài nhưng liền một mạch — đành chịu

    pieces, current, current_s = [], [], 0.0
    for clause in clauses:
        clause_s = duration_model.estimate_duration(clause, voice, rate)
        if current and current_s + clause_s > MAX_SHOT_S:
            pieces.append(" ".join(current))
            current, current_s = [clause], clause_s
        else:
            current.append(clause)
            current_s += clause_s
    if current:
        pieces.append(" ".join(current))
    return pieces


def _segment_cost(seconds: float) -> float:
    """Chi phí của một cảnh có thời lượng cho trước."""
    cost = (seconds - IDEAL_SHOT_S) ** 2
    if seconds > MAX_SHOT_S:
        cost += _PENALTY * (seconds - MAX_SHOT_S) ** 2
    elif seconds < MIN_SHOT_S:
        cost += _PENALTY * (MIN_SHOT_S - seconds) ** 2
    return cost


def _partition(units: list[_Unit]) -> list[tuple[int, int]]:
    """Chia dãy câu thành các nhóm liên tiếp tối ưu. Trả về danh sách (start, end).

    Quy hoạch động: dp[k][j] = chi phí nhỏ nhất khi chia j câu đầu thành đúng k nhóm.
    Số nhóm K KHÔNG cố định trước — bảng dp tính một lần cho mọi K rồi chọn K có tổng
    chi phí thấp nhất, nên số cảnh tự rơi ra từ nội dung thay vì bị áp đặt.
    """
    n = len(units)
    if n == 0:
        return []

    prefix = [0.0] * (n + 1)
    for i, u in enumerate(units):
        prefix[i + 1] = prefix[i] + u.seconds

    # hard[j] = True nếu câu j buộc mở đầu nhóm → không nhóm nào được chứa nó ở giữa.
    hard = [u.hard_start or u.atomic for u in units]
    # Câu ngay SAU một câu atomic cũng phải mở nhóm mới.
    for i, u in enumerate(units):
        if u.atomic and i + 1 < n:
            hard[i + 1] = True

    # next_hard[i] = vị trí hard đầu tiên > i, để kiểm tra đoạn hợp lệ trong O(1).
    next_hard = [n] * (n + 1)
    for i in range(n - 1, -1, -1):
        next_hard[i] = i if hard[i] else next_hard[i + 1]

    def seg_ok(i: int, j: int) -> bool:
        """Đoạn [i, j) hợp lệ nếu không nuốt một ranh giới cứng nào vào giữa."""
        return next_hard[i + 1] >= j

    k_max = min(n, MAX_SCENES)
    INF = float("inf")
    dp = [[INF] * (n + 1) for _ in range(k_max + 1)]
    back = [[-1] * (n + 1) for _ in range(k_max + 1)]
    dp[0][0] = 0.0

    for k in range(1, k_max + 1):
        for j in range(k, n + 1):
            best, best_i = INF, -1
            for i in range(k - 1, j):
                if dp[k - 1][i] == INF or not seg_ok(i, j):
                    continue
                cost = dp[k - 1][i] + _segment_cost(prefix[j] - prefix[i])
                if cost < best:
                    best, best_i = cost, i
            dp[k][j] = best
            back[k][j] = best_i

    best_k = min(range(1, k_max + 1), key=lambda k: dp[k][n])
    if dp[best_k][n] == INF:
        # Không thể xảy ra về mặt toán học (K=n luôn hợp lệ), nhưng nếu có thì trả về
        # nguyên trạng còn hơn ném lỗi giữa lúc user đang chờ.
        logger.warning("[SceneBalancer] Không tìm được cách chia hợp lệ, giữ nguyên.")
        return [(i, i + 1) for i in range(n)]

    groups, j, k = [], n, best_k
    while k > 0:
        i = back[k][j]
        groups.append((i, j))
        j, k = i, k - 1
    groups.reverse()
    return groups


def _dominant_source(units: list[_Unit]) -> int:
    """Cảnh gốc đóng góp NHIỀU THỜI LƯỢNG nhất vào nhóm này.

    Theo thời lượng chứ không theo số câu: một câu dài 6 giây quyết định hình ảnh của
    cảnh nhiều hơn ba câu vụn 1 giây.
    """
    weight: dict[int, float] = {}
    for u in units:
        weight[u.source_idx] = weight.get(u.source_idx, 0.0) + u.seconds
    return max(weight, key=weight.get)


def _build_scene(units: list[_Unit], source_scenes: list[dict], number: int) -> dict:
    """Dựng một cảnh mới từ nhóm câu, thừa kế thuộc tính của cảnh gốc CHI PHỐI.

    "Chi phối" = cảnh gốc đóng góp nhiều thời lượng nhất vào nhóm này (xem _dominant_source).
    """
    dominant_idx = _dominant_source(units)
    nguon_khac_nhau = {u.source_idx for u in units}

    scene = dict(source_scenes[dominant_idx])
    scene["scene"] = number
    scene["text"] = " ".join(u.text for u in units).strip()
    # pause_after_ms là khoảng lặng cuối cảnh → lấy của cảnh gốc chứa câu CUỐI nhóm.
    scene["pause_after_ms"] = source_scenes[units[-1].source_idx].get("pause_after_ms", 0) or 0

    if len(nguon_khac_nhau) > 1:
        # Đã trộn lời của nhiều cảnh: các trường mô tả riêng cho đoạn chữ cũ không còn
        # đúng nữa. Giữ lại sẽ khiến phụ đề hiện một đằng, giọng đọc một nẻo.
        scene.pop("subtitle_text", None)
        scene.pop("highlight_text", None)
    return scene


def rebalance_scenes(
    scenes: list[dict],
    voice: str | None = None,
    rate: str | None = None,
) -> dict:
    """Chia lại ranh giới cảnh cho đều nhịp. Trả về {"scenes", "report"}.

    KHÔNG sửa đổi `scenes` đầu vào — trả về danh sách mới để giao diện dựng preview
    trước/sau rồi mới hỏi user có áp dụng không.
    """
    if not scenes:
        return {"scenes": [], "report": {"changed": False, "groups": [], "before": {}, "after": {}}}

    units = _split_units(scenes, voice, rate)
    groups = _partition(units)

    new_scenes, group_report = [], []
    seen_dominant: dict[int, int] = {}   # cảnh gốc → đã sinh ra bao nhiêu cảnh mới
    for n, (i, j) in enumerate(groups, start=1):
        chunk = units[i:j]
        scene = _build_scene(chunk, scenes, n)

        # Cảnh gốc này đã đóng góp prompt cho một cảnh trước đó → đổi góc máy để hai
        # ảnh không ra giống hệt nhau.
        dominant = _dominant_source(chunk)
        lan_thu = seen_dominant.get(dominant, 0)
        seen_dominant[dominant] = lan_thu + 1
        if lan_thu > 0 and scene.get("image_prompt"):
            variant = _SHOT_VARIANTS[(lan_thu - 1) % len(_SHOT_VARIANTS)]
            scene["image_prompt"] = f"{scene['image_prompt'].rstrip('. ')}, {variant}"

        new_scenes.append(scene)
        sources = sorted({u.source_idx + 1 for u in chunk})  # 1-based cho user đọc
        seconds = sum(u.seconds for u in chunk)
        group_report.append({
            "scene": n,
            "seconds": round(seconds, 1),
            "from_scenes": sources,
            "action": ("keep" if len(sources) == 1 and _count_groups_of(groups, units, sources[0] - 1) == 1
                       else "merge" if len(sources) > 1 else "split"),
            "too_long": seconds > MAX_SHOT_S,
            "too_short": seconds < MIN_SHOT_S,
        })

    before = _stats([_scene_seconds(s, voice, rate) for s in scenes])
    after = _stats([g["seconds"] for g in group_report])
    return {
        "scenes": new_scenes,
        "report": {
            "changed": len(new_scenes) != len(scenes) or any(g["action"] != "keep" for g in group_report),
            "groups": group_report,
            "before": before,
            "after": after,
        },
    }


def _count_groups_of(groups, units, source_idx: int) -> int:
    """Số cảnh MỚI mà một cảnh gốc bị trải ra — >1 nghĩa là cảnh đó đã bị tách."""
    return sum(
        1 for (i, j) in groups
        if any(u.source_idx == source_idx for u in units[i:j])
    )


def _scene_seconds(scene: dict, voice: str | None, rate: str | None) -> float:
    from services import duration_model

    return duration_model.estimate_duration(
        scene.get("text") or "", voice, rate, scene.get("pause_after_ms") or 0
    )


def _stats(durations: list[float]) -> dict:
    """Số liệu tóm tắt để UI nói được 'trước/sau' bằng con số, không chỉ bằng cảm giác."""
    if not durations:
        return {"scenes": 0, "total": 0.0, "longest": 0.0, "shortest": 0.0, "off_pace": 0}
    return {
        "scenes": len(durations),
        "total": round(sum(durations), 1),
        "longest": round(max(durations), 1),
        "shortest": round(min(durations), 1),
        # Số cảnh nằm ngoài nhịp xem tốt — con số quan trọng nhất, vì đây chính là thứ
        # người xem cảm nhận được (ảnh đứng ì hoặc chớp qua).
        "off_pace": sum(1 for d in durations if d > MAX_SHOT_S or d < MIN_SHOT_S),
        "std": round(math.sqrt(sum((d - sum(durations) / len(durations)) ** 2 for d in durations) / len(durations)), 2),
    }
