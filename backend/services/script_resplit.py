"""
script_resplit.py — Sửa TOÀN BỘ kịch bản như một bài liền, rồi chia lại thành cảnh.

VÌ SAO CẦN
----------
Trình sửa theo từng cảnh bắt người viết nhìn nội dung qua 20 ô rời rạc. Không ai kiểm
soát được mạch văn kiểu đó: câu cuối cảnh 3 và câu đầu cảnh 4 lặp ý nhau mà chẳng ai
thấy, vì hai ô cách nhau một màn hình cuộn. Sửa liền mạch trên MỘT khối chữ mới nhìn ra
được nhịp, chỗ thừa, chỗ hụt.

Nhưng chia cảnh lại là việc của đồng hồ, không phải của mắt: mỗi cảnh nên rơi vào khoảng
2.5-6.5 giây đọc. Đó đúng là việc `scene_balancer` đã làm tốt bằng quy hoạch động. Nên
module này KHÔNG tự chia — nó chỉ lo phần `scene_balancer` không lo được:

    văn bản đã sửa  →  gán lại vào các cảnh gốc  →  scene_balancer chia đều nhịp

CHỖ KHÓ DUY NHẤT: GIỮ LẠI ẢNH
-----------------------------
Mỗi cảnh mang theo `image_prompt`, `emotion`, `sfx`... — công sức của cả một vòng gọi
LLM. Nếu sau khi sửa chữ ta vứt hết đi rồi sinh lại thì vừa tốn quota vừa làm video đổi
hình xoành xoạch dù người dùng chỉ sửa một chữ.

Nên: đoạn văn mới được DÒ NGƯỢC về cảnh gốc có lời giống nó nhất (so theo TỪ, chịu được
sửa vài chữ), rồi thừa kế toàn bộ thuộc tính của cảnh đó. Đoạn hoàn toàn mới (người dùng
tự viết thêm) không dò được thì thừa kế cảnh liền trước — hình của bối cảnh đang diễn ra
vẫn hợp lý hơn là một ô trống.
"""
from __future__ import annotations

import difflib
import logging
import re

logger = logging.getLogger(__name__)

# Dưới ngưỡng này coi như hai đoạn không liên quan → không thừa kế bừa.
# 0.4 chứ không phải 0.55 như bên đối chiếu transcript: ở đây người dùng ĐANG CỐ Ý sửa
# chữ, nên phải rộng tay hơn nhiều. Sai sót ở đây cũng nhẹ hơn hẳn — cùng lắm là cảnh
# nhận nhầm mô tả ảnh của cảnh bên cạnh, không phải giọng đọc ra thứ vô nghĩa.
MIN_MATCH = 0.4

# Các trường mô tả ĐOẠN CHỮ CŨ. Lời đã đổi thì chúng không còn đúng nữa — giữ lại sẽ làm
# phụ đề hiện một đằng, giọng đọc một nẻo. (scene_balancer cũng bỏ chúng khi trộn cảnh.)
_TRUONG_THEO_CHU = ("subtitle_text", "highlight_text", "word_boundaries", "duration",
                    "computed_duration", "start_time")


def tach_doan(full_text: str) -> list[str]:
    """
    Cắt khối chữ thành các đoạn theo DÒNG TRỐNG.

    Dòng trống là ranh giới cảnh mà người dùng nhìn thấy và sửa được: xoá dòng trống =
    gộp hai cảnh, thêm dòng trống = tách cảnh. Xuống dòng đơn KHÔNG cắt — người ta hay
    xuống dòng cho dễ đọc chứ không có ý tách cảnh.
    """
    khoi = re.split(r"\n\s*\n+", (full_text or "").strip())
    return [re.sub(r"\s+", " ", k).strip() for k in khoi if k.strip()]


def ghep_thanh_van_ban(scenes: list[dict]) -> str:
    """Dựng khối chữ để sửa: mỗi cảnh một đoạn, ngăn nhau bằng dòng trống."""
    return "\n\n".join((s.get("text") or "").strip() for s in scenes if (s.get("text") or "").strip())


def _tu(text: str) -> list[str]:
    return re.sub(r"[^\w\s]", " ", (text or "").lower()).split()


def _do_giong(a: str, b: str) -> float:
    """Độ giống 0..1 giữa hai đoạn, so THEO TỪ (chịu được sửa vài chữ, đổi dấu câu)."""
    wa, wb = _tu(a), _tu(b)
    if not wa or not wb:
        return 0.0
    return difflib.SequenceMatcher(None, wa, wb).ratio()


def gan_doan_vao_canh_goc(doan_moi: list[str], scenes_goc: list[dict]) -> list[dict]:
    """
    Dựng cảnh tạm từ các đoạn đã sửa, thừa kế thuộc tính của cảnh gốc giống nhất.

    Dò theo THỨ TỰ TIẾN: cảnh gốc đã dùng cho đoạn i thì các đoạn sau chỉ dò từ đó trở
    đi. Không có ràng buộc này, một câu lặp lại ở cuối bài sẽ kéo đoạn cuối về thừa kế
    hình của cảnh đầu — kịch bản viral rất hay lặp lại câu hook ở đoạn kết, nên đây là
    tình huống thường gặp chứ không phải hiếm.
    """
    ket_qua: list[dict] = []
    con_tro = 0                      # cảnh gốc nhỏ nhất còn được phép dò tới
    nguon_truoc = 0                  # cảnh gốc mà đoạn liền trước đã thừa kế

    for doan in doan_moi:
        diem_tot_nhat, idx_tot_nhat = 0.0, -1
        for idx in range(con_tro, len(scenes_goc)):
            diem = _do_giong(doan, scenes_goc[idx].get("text", ""))
            if diem > diem_tot_nhat:
                diem_tot_nhat, idx_tot_nhat = diem, idx

        if idx_tot_nhat >= 0 and diem_tot_nhat >= MIN_MATCH:
            nguon = idx_tot_nhat
            con_tro = idx_tot_nhat          # cho phép nhiều đoạn cùng thừa kế 1 cảnh (tách cảnh)
        else:
            nguon = min(nguon_truoc, len(scenes_goc) - 1)   # đoạn viết mới → bám cảnh liền trước

        goc = scenes_goc[nguon] if scenes_goc else {}
        canh = {k: v for k, v in goc.items() if k not in _TRUONG_THEO_CHU}
        canh["text"] = doan
        canh["scene"] = len(ket_qua) + 1
        canh["_nguon_goc"] = nguon + 1          # 1-based, để UI nói "thừa kế ảnh của cảnh 3"
        canh["_do_khop"] = round(diem_tot_nhat, 2)
        ket_qua.append(canh)
        nguon_truoc = nguon

    return ket_qua


def resplit(
    full_text: str,
    scenes_goc: list[dict],
    voice: str | None = None,
    rate: str | None = None,
    rebalance: bool = True,
) -> dict:
    """
    Toàn bộ quy trình: chữ đã sửa → cảnh tạm (thừa kế ảnh) → cân nhịp.

    Trả về {"scenes", "report"}. CHỈ LÀ ĐỀ XUẤT — không ghi đè gì; giao diện dựng
    preview rồi để người dùng quyết định, y như /api/rebalance-scenes.

    `rebalance=False` cho người dùng tự chốt ranh giới bằng dòng trống mà không để thuật
    toán đụng vào — có người muốn đúng 12 cảnh cho 12 tấm ảnh đã chuẩn bị sẵn.
    """
    doan = tach_doan(full_text)
    if not doan:
        raise ValueError("Kịch bản trống — không có đoạn nào để chia.")

    tam = gan_doan_vao_canh_goc(doan, scenes_goc or [])

    # Số liệu thừa kế phải tính TRƯỚC khi cân nhịp: sau đó các cảnh bị gộp/tách, không
    # còn ánh xạ 1-1 với đoạn người dùng vừa sửa nữa.
    thua_ke = [
        {"scene": c["scene"], "tu_canh_goc": c["_nguon_goc"], "do_khop": c["_do_khop"],
         "la_doan_moi": c["_do_khop"] < MIN_MATCH}
        for c in tam
    ]
    for c in tam:
        c.pop("_nguon_goc", None)
        c.pop("_do_khop", None)

    report = {
        "doan_da_sua": len(doan),
        "canh_goc": len(scenes_goc or []),
        "thua_ke": thua_ke,
        "doan_viet_moi": sum(1 for t in thua_ke if t["la_doan_moi"]),
        "da_can_nhip": False,
    }

    if not rebalance:
        for n, c in enumerate(tam, start=1):
            c["scene"] = n
        report["canh_ket_qua"] = len(tam)
        return {"scenes": tam, "report": report}

    from services import scene_balancer
    ket = scene_balancer.rebalance_scenes(tam, voice, rate)
    report["da_can_nhip"] = True
    report["canh_ket_qua"] = len(ket["scenes"])
    report["nhip"] = ket["report"]
    return {"scenes": ket["scenes"], "report": report}
