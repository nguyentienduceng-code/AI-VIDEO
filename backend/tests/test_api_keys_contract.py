"""
Test hợp đồng cho endpoint quản lý API Key: GET/POST /api/api-keys-config.

Chạy:  python tests/test_api_keys_contract.py   (từ thư mục backend/, không cần pytest)
       pytest tests/test_api_keys_contract.py

VÌ SAO VIẾT LẠI THEO KIỂU STANDALONE: bản đầu dùng fixture `tmp_path`/`monkeypatch` của
pytest, nhưng venv của dự án KHÔNG cài pytest (`python -m pytest` → No module named pytest)
và 16 file test còn lại đều chạy bằng `python tests/<file>.py`. Nghĩa là file test này chưa
từng chạy một lần nào — đúng loại "lưới an toàn tưởng có mà không có" mà dự án đã dính nhiều
lần. Giữ tương thích pytest, nhưng phải chạy được không cần nó.

AN TOÀN: endpoint này GHI THẬT vào backend/.env. Test luôn trỏ `config.ENV_FILE` sang file
tạm và tự kiểm tra lại trước khi POST — ghi trượt vào .env thật là mất sạch API key của
người dùng.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)

ENV_THAT = config.ENV_FILE


class EnvTam:
    """Chuyển config.ENV_FILE sang file tạm, và luôn nạp lại môi trường thật khi xong."""

    def __init__(self, noi_dung: str = "GEMINI_API_KEY=cu\n"):
        self.noi_dung = noi_dung

    def __enter__(self) -> str:
        self.duong_dan = os.path.join(tempfile.mkdtemp(), ".env")
        with open(self.duong_dan, "w", encoding="utf-8") as f:
            f.write(self.noi_dung)
        config.ENV_FILE = self.duong_dan
        assert config.ENV_FILE != ENV_THAT, "CHẶN: test sắp ghi vào .env thật!"
        return self.duong_dan

    def __exit__(self, *exc):
        config.ENV_FILE = ENV_THAT
        # Endpoint có ghi vào os.environ → dọn sạch rồi nạp lại .env thật, để các test sau
        # (và chính phiên chạy này) không nhìn thấy key giả.
        for k in list(os.environ):
            if k.startswith(("GEMINI_API_KEY", "PEXELS_API_KEY", "PIXABAY_API_KEY", "FAL_KEY")):
                os.environ.pop(k, None)
        from dotenv import load_dotenv

        load_dotenv(ENV_THAT, override=True)
        from services.key_manager import fal_keys, gemini_keys

        gemini_keys.__init__("GEMINI_API_KEY")
        fal_keys.__init__("FAL_KEY")
        return False


def test_get_tra_ve_du_truong_va_trang_thai():
    r = client.get("/api/api-keys-config")
    assert r.status_code == 200
    d = r.json()
    for truong in ("gemini_api_keys", "pexels_api_key", "pixabay_api_key", "fal_key", "status"):
        assert truong in d, truong
    assert isinstance(d["gemini_api_keys"], list)
    for nha in ("gemini", "pexels", "pixabay", "fal"):
        assert nha in d["status"], nha
        assert isinstance(d["status"][nha], bool)


def test_post_ghi_dung_ten_bien_vao_env():
    with EnvTam() as env:
        r = client.post("/api/api-keys-config", json={
            "gemini_api_keys": ["key_a", "key_b"],
            "pexels_api_key": "px_1",
            "pixabay_api_key": "pb_2",
            "fal_key": "fal_3",
        })
        assert r.status_code == 200 and r.json()["status"] == "ok"
        noi_dung = open(env, encoding="utf-8").read()
        # Key thứ nhất là key CHÍNH, các key sau đánh số từ 1.
        assert "GEMINI_API_KEY=key_a" in noi_dung
        assert "GEMINI_API_KEY_1=key_b" in noi_dung
        assert "PEXELS_API_KEY=px_1" in noi_dung
        assert "PIXABAY_API_KEY=pb_2" in noi_dung
        assert "FAL_KEY=fal_3" in noi_dung


def test_post_don_sach_key_du_phong_cu_khong_de_lai_rac():
    """Hạ từ 4 key xuống 1 phải XOÁ hẳn các slot cũ, không để lại `GEMINI_API_KEY_2=` trắng.

    LỖI CŨ: vòng dọn ghi giá trị rỗng, mà `write_env_value` lúc đó lại append dòng — .env
    mọc ra 9 dòng trắng, mỗi dòng kèm một comment sai về "thư mục lưu dữ liệu".
    """
    with EnvTam("GEMINI_API_KEY=a\nGEMINI_API_KEY_1=b\nGEMINI_API_KEY_2=c\nGEMINI_API_KEY_3=d\nPORT=8000\n") as env:
        r = client.post("/api/api-keys-config", json={"gemini_api_keys": ["chi_mot_key"]})
        assert r.status_code == 200
        noi_dung = open(env, encoding="utf-8").read()
        assert "GEMINI_API_KEY=chi_mot_key" in noi_dung
        for i in (1, 2, 3):
            assert f"GEMINI_API_KEY_{i}" not in noi_dung, f"còn sót slot {i}"
        assert "PORT=8000" in noi_dung, "dòng không liên quan không được mất"
        assert "Thư mục lưu toàn bộ dữ liệu" not in noi_dung


def test_post_khong_dung_toi_truong_khong_gui_len():
    """Gửi riêng Pixabay không được xoá mất key Gemini/Pexels đang có."""
    with EnvTam("GEMINI_API_KEY=giu_nguyen\nPEXELS_API_KEY=cung_giu\n") as env:
        r = client.post("/api/api-keys-config", json={"pixabay_api_key": "chi_pixabay"})
        assert r.status_code == 200
        noi_dung = open(env, encoding="utf-8").read()
        assert "GEMINI_API_KEY=giu_nguyen" in noi_dung
        assert "PEXELS_API_KEY=cung_giu" in noi_dung
        assert "PIXABAY_API_KEY=chi_pixabay" in noi_dung


def test_key_manager_nap_lai_ngay_sau_khi_luu():
    """Lưu key mới mà KeyManager không nạp lại thì phải khởi động lại backend mới ăn."""
    with EnvTam():
        client.post("/api/api-keys-config", json={"gemini_api_keys": ["moi_1", "moi_2", "moi_3"]})
        from services.key_manager import gemini_keys

        assert len(gemini_keys.keys) == 3, gemini_keys.keys
        assert gemini_keys.get_current_key() == "moi_1"
        # Xoay vòng phải đi qua đủ 3 key (cơ chế chống 429).
        assert {gemini_keys.rotate() for _ in range(3)} == {"moi_1", "moi_2", "moi_3"}


def test_env_that_khong_he_bi_cham_toi():
    """Chốt chặn cuối: sau tất cả test trên, .env thật phải còn nguyên."""
    assert config.ENV_FILE == ENV_THAT
    assert os.path.isfile(ENV_THAT)
    noi_dung = open(ENV_THAT, encoding="utf-8").read()
    for rac in ("key_a", "key_b", "px_1", "pb_2", "fal_3", "chi_mot_key", "moi_1"):
        assert rac not in noi_dung, f".env thật đã bị test ghi vào: {rac!r}"


if __name__ == "__main__":
    ok = fail = 0
    # Chạy theo THỨ TỰ khai báo, không sắp xếp: test chốt chặn .env phải chạy CUỐI.
    ten_test = [
        "test_get_tra_ve_du_truong_va_trang_thai",
        "test_post_ghi_dung_ten_bien_vao_env",
        "test_post_don_sach_key_du_phong_cu_khong_de_lai_rac",
        "test_post_khong_dung_toi_truong_khong_gui_len",
        "test_key_manager_nap_lai_ngay_sau_khi_luu",
        "test_env_that_khong_he_bi_cham_toi",
    ]
    for ten in ten_test:
        try:
            globals()[ten]()
            ok += 1
            print(f"  PASS  {ten}")
        except AssertionError as e:
            fail += 1
            print(f"  FAIL  {ten}: {e}")
    print(f"\n{ok} pass, {fail} fail")
    sys.exit(1 if fail else 0)
