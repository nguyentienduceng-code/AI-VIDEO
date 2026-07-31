"""
Test cho tầng CHỌN & TÌM NGUỒN HÌNH: từ khoá tìm footage, bậc thang truy vấn,
chuẩn hoá ứng viên Pixabay, và bản tổng kết nguồn hình.

Chạy:  python tests/test_stock_sourcing.py   (từ thư mục backend/, không cần pytest)
       pytest tests/test_stock_sourcing.py

VÌ SAO CÓ FILE NÀY: chất lượng footage phụ thuộc gần như hoàn toàn vào MỘT chuỗi — câu
truy vấn gửi kho stock — mà chuỗi đó lại được sinh bằng heuristic không có test nào canh.
Đo trên 14 `image_prompt` Gemini thật thì thuật toán cũ (lọc stopword rồi lấy 3 từ ĐẦU)
làm MẤT chủ thể ở 4 trường hợp, vì tiếng Anh đặt danh từ chính ở CUỐI cụm danh từ:

    "a vintage closed leather book lying on a dark wooden table"
        → "vintage closed leather"   (không còn chữ "book")
    "close up of hands digging into soft soil under an old tree"
        → "hands digging into"       (kết bằng giới từ, mất "soil")

Đây là loại lỗi CÂM điển hình của dự án này: video vẫn render xong, vẫn có hình, chỉ là
hình "hơi đúng mà không đúng chủ đề" — không thể phát hiện bằng cách chạy app, chỉ phát
hiện được bằng cách ngồi xem lại từng cảnh.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.gemini_service import build_stock_queries, stock_query_from_prompt
from services.image_router import _pixabay_to_candidate, _score_stock_candidate
from main import VISUAL_SOURCE_LABELS, _summarize_visual_sources


# ---------------------------------------------------------------------------
# 1. Từ khoá PHẢI giữ được danh từ chính
# ---------------------------------------------------------------------------
# Mỗi dòng: (image_prompt thật do Gemini sinh, danh từ chính BẮT BUỘC còn trong query)
CAC_CA_THAT = [
    ("a vintage closed leather book lying on a dark wooden table near a warm lantern", "book"),
    ("hands cleaning delicate crystal glasses in a rustic sunlit shop", "glasses"),
    ("empty dusty street in an old middle eastern market under harsh sunlight", "street"),
    ("close up of hands digging into soft soil under an old sycamore tree", "soil"),
    ("Extreme close-up shot of a stressed Asian man in his 30s holding a paper bank passbook", "man"),
    ("ancient giant pyramids silhouettes under a dark dramatic twilight sky", "pyramids"),
    ("a young man standing on a wooden dock looking at the ocean in morning light", "man"),
    ("endless sand dunes stretching to the horizon under a clear sky", "dunes"),
    ("Low-angle drone shot of a glass skyscraper at dusk, teal and orange grading, 8k", "skyscraper"),
    ("car headlights on a rainy night street", "headlights"),
    ("a hand writing a letter by candlelight", "letter"),
    ("Wide establishing shot of stacks of cash on a desk, 8k photorealistic", "cash"),
]


def test_tu_khoa_luon_giu_danh_tu_chinh():
    """4/12 ca này từng mất hẳn chủ thể với thuật toán 'lấy 3 từ đầu'."""
    for prompt, danh_tu in CAC_CA_THAT:
        q = stock_query_from_prompt(prompt)
        assert danh_tu in q.split(), f"{prompt[:52]!r} → {q!r}, mất {danh_tu!r}"


def test_tu_khoa_khong_bao_gio_ket_bang_gioi_tu():
    """'hands digging into' là truy vấn vô nghĩa với kho stock."""
    gioi_tu = {"in", "on", "at", "into", "to", "of", "with", "under", "near", "by", "from"}
    for prompt, _ in CAC_CA_THAT:
        q = stock_query_from_prompt(prompt)
        assert q.split()[-1] not in gioi_tu, f"{q!r} kết bằng giới từ"


def test_tu_khoa_khong_chua_thuat_ngu_may_quay_hay_render():
    rac = {"8k", "photorealistic", "cinematic", "shot", "close-up", "drone", "low-angle",
           "establishing", "wide", "teal", "orange", "stock", "footage"}
    for prompt, _ in CAC_CA_THAT:
        for tu in stock_query_from_prompt(prompt).split():
            assert tu not in rac, f"{prompt[:40]!r} → còn từ rác {tu!r}"


def test_tu_khoa_gon_va_khong_rong():
    for prompt, _ in CAC_CA_THAT:
        q = stock_query_from_prompt(prompt)
        assert 1 <= len(q.split()) <= 3, f"{q!r} dài/ngắn bất thường"
    # Prompt rỗng hoặc toàn jargon vẫn phải trả một truy vấn dùng được.
    assert stock_query_from_prompt("") == "nature"
    assert stock_query_from_prompt("8k photorealistic cinematic shot") == "nature"


def test_khong_bao_gio_gui_chinh_khai_niem_video_stock_lam_tu_khoa():
    """'stock footage style' lọt lưới thì query gửi Pexels là chính khái niệm 'video stock'.

    Đo trên kịch bản thật: Gemini hay chốt image_prompt bằng đuôi đó ở tone storytelling.

    Ghi chú về `with`: prompt này để "a flock of sheep" làm tân ngữ của "with", nên luật
    head-final trả về "walking flock sheep" chứ không phải "young shepherd". Đã đo cả hai
    cách trên 7 prompt có chữ "with": coi "with" là ranh giới bối cảnh thì 3/4 ca còn lại
    tệ hơn hẳn ("a man with a laptop in a cafe" → chỉ còn "man", "an old fisherman with a
    wooden boat" → "old fisherman", mất chiếc thuyền). Nên chỉ khẳng định điều THẬT SỰ quan
    trọng: truy vấn phải sạch rác và phải nêu một chủ thể có thật.
    """
    kw = stock_query_from_prompt(
        "A young shepherd walking with a flock of sheep across green hills, stock footage style"
    )
    assert "stock" not in kw and "footage" not in kw and "style" not in kw
    assert {"sheep", "flock", "shepherd"} & set(kw.split()), kw

    kw2 = stock_query_from_prompt(
        "A vintage hardbound book lying on warm sand next to an hourglass, "
        "cinematic lighting, photorealistic, 8k"
    )
    assert "book" in kw2.split(), kw2
    for rac in ("8k", "photorealistic", "cinematic"):
        assert rac not in kw2


def test_bo_tien_to_goc_may_truoc_khi_trich():
    """Prompt chế độ ảnh AI BẮT BUỘC mở đầu bằng góc máy, nếu không gỡ thì chủ thể bị lệch."""
    q = stock_query_from_prompt("Extreme close-up shot of a lion roaring in the savanna")
    assert "lion" in q.split()
    assert "extreme" not in q and "shot" not in q


# ---------------------------------------------------------------------------
# 2. Bậc thang truy vấn
# ---------------------------------------------------------------------------
def test_bac_thang_di_tu_cu_the_den_rong_dan():
    """Pexels trả 0 kết quả từng làm cảnh đó rơi thẳng về ảnh AI tĩnh, dù chỉ cần bỏ
    một tính từ là tìm thấy — video thành nửa footage thật nửa ảnh tĩnh."""
    thang = build_stock_queries(
        "a vintage closed leather book lying on a dark wooden table"
    )
    assert thang[0] == "closed leather book"
    assert thang[-1] == "book", "bậc cuối phải là danh từ chính trơ trọi"
    # Rộng dần, không có bậc nào dài hơn bậc trước.
    do_dai = [len(q.split()) for q in thang]
    assert do_dai == sorted(do_dai, reverse=True), do_dai
    assert len(thang) == len(set(thang)), "không được có bậc trùng nhau"


def test_bac_thang_khong_trung_khi_tu_khoa_ngan():
    thang = build_stock_queries("car headlights on a rainy night street")
    assert thang == ["car headlights", "headlights"]


# ---------------------------------------------------------------------------
# 3. Ứng viên Pixabay phải dùng được với luật chấm điểm sẵn có
# ---------------------------------------------------------------------------
def test_chuan_hoa_hit_pixabay_ve_dang_kieu_pexels():
    """Pixabay KHÔNG trả width/height ở cấp hit và API video của họ KHÔNG có tham số
    `orientation` — nên phải tự suy kích thước, nếu không clip 16:9 sẽ lọt vào video dọc."""
    hit = {
        "id": 12345,
        "duration": 14,
        "videos": {
            "large": {"url": "https://x/large.mp4", "width": 1080, "height": 1920},
            "small": {"url": "https://x/small.mp4", "width": 540, "height": 960},
            "tiny": {},  # Pixabay có lúc trả biến thể rỗng
        },
    }
    c = _pixabay_to_candidate(hit)
    assert c["width"] == 1080 and c["height"] == 1920
    assert c["duration"] == 14
    assert len(c["video_files"]) == 2, "biến thể rỗng phải bị bỏ"
    # id có tiền tố nhà cung cấp: id Pixabay và Pexels là hai không gian số riêng biệt,
    # trộn thẳng vào cùng used_ids sẽ có lúc trùng số một cách vô nghĩa.
    assert c["id"] == "pixabay-12345"

    # Và phải chấm điểm được bằng đúng hàm dùng cho Pexels.
    diem = _score_stock_candidate(c, target_ratio=1080 / 1920, target_h=1920, needed_dur=5.0)
    assert diem == 0.0, f"clip dọc 1080x1920 đủ dài phải không bị phạt, nhận {diem}"


def test_clip_ngang_bi_phat_nang_hon_clip_doc_khi_lam_video_doc():
    ngang = _pixabay_to_candidate({
        "id": 1, "duration": 20,
        "videos": {"large": {"url": "u", "width": 1920, "height": 1080}},
    })
    doc = _pixabay_to_candidate({
        "id": 2, "duration": 20,
        "videos": {"large": {"url": "u", "width": 1080, "height": 1920}},
    })
    r, h = 1080 / 1920, 1920
    assert _score_stock_candidate(ngang, r, h, 5.0) > _score_stock_candidate(doc, r, h, 5.0)


# ---------------------------------------------------------------------------
# 3.5. Cửa chặn "match mờ" — Pexels gần như không bao giờ trả 0 kết quả
# ---------------------------------------------------------------------------
# Nhãn thật lấy từ slug URL Pexels trong lần đo trực tiếp (per_page=6, orientation=portrait).
POOL_RAC = [  # "zoroastrian fire altar" → 3094 kết quả, khớp 0/6
    {"_label": "day-of-the-dead-celebration"},
    {"_label": "woman-holding-a-candle-in-church"},
    {"_label": "priest-praying-in-orthodox-church"},
]
POOL_TOT = [  # "closed leather book" → khớp 3/6
    {"_label": "holy-bible-on-wooden-surface"},
    {"_label": "islam"},
    {"_label": "reading-a-book-with-a-coffee"},
]


def test_phat_hien_duoc_ket_qua_match_mo():
    """Bậc thang truy vấn MỘT MÌNH là chưa đủ: truy vấn vô vọng vẫn 'thành công'.

    Pexels match mờ nên "zoroastrian fire altar" trả về 3094 clip — toàn bộ là lễ hội
    Halloween, nến nhà thờ, linh mục cầu nguyện. Không có cửa chặn này thì cảnh đó nhận
    một clip sai hẳn chủ đề mà pipeline coi như thành công.
    """
    from services.image_router import _pool_is_relevant

    assert not _pool_is_relevant(POOL_RAC, "zoroastrian fire altar")
    assert _pool_is_relevant(POOL_TOT, "closed leather book")


def test_cua_chan_khop_ca_so_nhieu_so_it():
    """'sand dunes' phải khớp slug 'walking-on-a-sand-dune-in-the-desert'."""
    from services.image_router import _pool_is_relevant

    pool = [{"_label": "walking-on-a-sand-dune-in-the-desert"}]
    assert _pool_is_relevant(pool, "endless sand dunes")
    pool2 = [{"_label": "vertical-video-of-wine-glasses"}]
    assert _pool_is_relevant(pool2, "delicate crystal glasses")


def test_cua_chan_khong_bao_gio_loai_oan_khi_thieu_du_lieu():
    """Không kết luận được thì phải CHO QUA — chặn sẽ loại oan cả một nhà cung cấp.

    Trường hợp thật có thể xảy ra: API đổi tên trường mô tả, `_label` thành rỗng hết. Lúc
    đó cửa chặn phải im lặng nhường đường, không được biến thành "không nguồn nào dùng được".
    """
    from services.image_router import _pool_is_relevant

    assert _pool_is_relevant([{"_label": ""}, {}], "closed leather book") is True
    # Truy vấn không có từ nào đủ dài để đối chiếu → cho qua.
    assert _pool_is_relevant([{"_label": "abc"}], "a of") is True


def test_loai_rieng_khi_match_mo_de_caller_biet_nen_dung_anh_ai():
    """Khái niệm trừu tượng (biểu đồ lượng tử) VỐN không có trong kho footage.

    Lúc đó ảnh AI mới là câu trả lời đúng — nên lỗi phải có LOẠI RIÊNG, không lẫn với
    lỗi mạng/khoá sai.
    """
    from services.image_router import StockIrrelevantError, _select_and_download

    try:
        _select_and_download(
            POOL_RAC, "Pexels", "quantum entanglement diagram", "/tmp/x.mp4",
            "9:16", 4.0, set(), {},
        )
    except StockIrrelevantError as e:
        assert "không cái nào liên quan" in str(e)
    else:
        raise AssertionError("phải ném StockIrrelevantError")


# ---------------------------------------------------------------------------
# 4. Tổng kết nguồn hình — điều kiện tiên quyết để tối ưu
# ---------------------------------------------------------------------------
def test_tom_tat_dem_dung_tung_nguon():
    """Không có bản tổng kết này thì 'đa số video lấy từ Pexels' chỉ là cảm giác."""
    scenes = [
        {"visual_source_used": "Pexels"},
        {"visual_source_used": "Pexels"},
        {"visual_source_used": "gemini_image"},
        {"visual_source_used": "pollinations_flux"},
    ]
    tom_tat = _summarize_visual_sources(scenes)
    assert "2 video Pexels" in tom_tat
    assert "1 ảnh Gemini" in tom_tat
    assert "1 ảnh Pollinations" in tom_tat


def test_tom_tat_gop_moi_dang_cache_thanh_mot_nhom():
    scenes = [
        {"visual_source_used": "cache:Pexels"},
        {"visual_source_used": "cache:file_mp4"},
        {"visual_source_used": "cache:image"},
        {"visual_source_used": "gemini_image"},
    ]
    tom_tat = _summarize_visual_sources(scenes)
    assert "3 dùng lại từ cache" in tom_tat
    assert "1 ảnh Gemini" in tom_tat


def test_canh_thieu_thong_tin_khong_bi_bo_qua_im_lang():
    """Cảnh không rõ nguồn phải HIỆN ra, vì nó nghĩa là có nhánh nào chưa gắn cờ."""
    assert "không rõ" in _summarize_visual_sources([{}, {}])


def test_moi_nhan_nguon_deu_co_ten_tieng_viet():
    """Nhãn thiếu thì tổng kết in ra tên biến nội bộ — vô nghĩa với người dùng."""
    from services import image_router

    ma_nguon = {"Pexels", "Pixabay", "gemini_image", "pexels_photo", "pollinations_flux",
                "gradient_offline", "placeholder", "veo", "user_override", "user_photo",
                "user_cover", "unknown"}
    assert ma_nguon <= set(VISUAL_SOURCE_LABELS)
    # Và các chuỗi đó phải thật sự tồn tại trong image_router (chống lệch tên khi refactor).
    src = open(image_router.__file__, encoding="utf-8").read()
    for ma in ("gemini_image", "pexels_photo", "pollinations_flux", "gradient_offline"):
        assert f'_ghi("{ma}")' in src, f"{ma} không còn được ghi trong image_router"


if __name__ == "__main__":
    ok = fail = 0
    for ten, fn in sorted(list(globals().items())):
        if ten.startswith("test_") and callable(fn):
            try:
                fn()
                ok += 1
                print(f"  PASS  {ten}")
            except AssertionError as e:
                fail += 1
                print(f"  FAIL  {ten}: {e}")
    print(f"\n{ok} pass, {fail} fail")
    sys.exit(1 if fail else 0)
