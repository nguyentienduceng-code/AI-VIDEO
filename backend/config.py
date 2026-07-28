"""
config.py
---------
NGUỒN SỰ THẬT DUY NHẤT cho mọi đường dẫn file của backend.

VÌ SAO CÓ HAI GỐC THƯ MỤC, KHÔNG PHẢI MỘT:

  BUNDLED_ASSETS_DIR = backend/assets — tài nguyên ĐI KÈM MÃ NGUỒN, chỉ đọc:
      bgm/ (74MB nhạc nền), sfx/ (tiếng động), slot_covers/, fonts/, templates/.
      Những thứ này KHÔNG được đi theo ổ D. Nếu chuyển, `get_available_bgm()` trả
      danh sách rỗng, hook Máy Xèng mất tiếng trục quay, riser/whoosh im lặng —
      user chỉ thấy "video không có nhạc" mà không hiểu vì sao.

  DATA_DIR = nơi đổ MỌI THỨ DO CHẠY MÁY SINH RA, có thể trỏ sang ổ khác:
      images/ (688MB), output/ (299MB), cache/ (112MB), audio/, uploads/,
      veo_tmp/, projects/, render_status/, voices_preview/.
      Đây mới là phần làm đầy SSD hệ thống.

Mặc định DATA_DIR == BUNDLED_ASSETS_DIR (= backend/assets) nên khi CHƯA cấu hình gì,
hành vi giống hệt bản cũ, không cần di dời một byte nào.

Đổi chỗ lưu: đặt CUSTOM_ASSETS_DIR trong backend/.env (hoặc dùng UI Cấu hình Nâng cao),
ví dụ:  CUSTOM_ASSETS_DIR=D:\\AIVideoAssets
Biến môi trường chỉ đọc MỘT LẦN lúc import → phải khởi động lại backend sau khi đổi.
"""

from __future__ import annotations

import logging
import os
import shutil

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Alias "ffmpeg.exe" cho các thư viện bên thứ ba gọi bare "ffmpeg" qua subprocess
# ---------------------------------------------------------------------------
# imageio_ffmpeg đóng gói ffmpeg dưới tên PHIÊN BẢN (vd "ffmpeg-win-x86_64-v7.1.exe"),
# không phải "ffmpeg.exe". main.py có thêm thư mục đó vào PATH, nhưng đó KHÔNG đủ:
# Windows CreateProcess tìm đúng file tên "ffmpeg.exe" trên PATH, không tự khớp tên
# phiên bản. Hậu quả THẬT đã xảy ra: stable_whisper (dùng để tự transcribe mẫu giọng
# clone khi user không nhập transcript — xem /api/voice-clone) gọi thẳng
# subprocess.run(['ffmpeg', ...]) và luôn FileNotFoundError, bị nuốt lặng lẽ, rơi về
# ref_text mặc định chung chung — SAI với nội dung thật của mẫu giọng, làm giọng clone
# phát âm/ngữ điệu lệch. Tạo bản sao tên "ffmpeg.exe" cạnh file gốc (idempotent, chạy
# lại không lỗi) để mọi thư viện gọi bare "ffmpeg" đều tìm thấy.
def _ensure_ffmpeg_alias() -> None:
    try:
        import imageio_ffmpeg
        src = imageio_ffmpeg.get_ffmpeg_exe()
        alias = os.path.join(os.path.dirname(src), "ffmpeg.exe")
        if not os.path.exists(alias):
            shutil.copy2(src, alias)
            logger.info("[Config] Đã tạo alias %s cho stable_whisper/thư viện bên thứ ba.", alias)
    except Exception as e:  # không được để lỗi này chặn cả backend khởi động
        logger.warning("[Config] Không tạo được alias ffmpeg.exe: %s", e)


_ensure_ffmpeg_alias()

# config là module được nạp SỚM NHẤT ở cả tiến trình FastAPI lẫn process con của
# render (multiprocessing spawn). Nếu cấu hình sai, nó log cảnh báo tiếng Việt NGAY
# lúc import — tức trước khi _worker_main() kịp gọi setup_logging(). Ép UTF-8 tại đây
# để dòng cảnh báo đó không tự giết process con. Xem services/log_setup.py.
try:
    from services.log_setup import force_utf8_streams

    force_utf8_streams()
except Exception:  # pragma: no cover — chạy đơn lẻ, không có services/ trên sys.path
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, ".env")

# KHÔNG gọi load_dotenv() trần: nó dò file .env theo CWD. Render chạy trong process
# con (multiprocessing spawn trên Windows) — process con re-import toàn bộ module với
# CWD không chắc trùng backend/, và sẽ lặng lẽ đọc thiếu cấu hình, đổ file về chỗ khác
# với process cha. Đường dẫn tuyệt đối thì cả hai luôn đọc cùng một file.
load_dotenv(ENV_FILE)

# ---------------------------------------------------------------------------
# Gốc 1: tài nguyên đi kèm mã nguồn (chỉ đọc, KHÔNG di dời)
# ---------------------------------------------------------------------------
BUNDLED_ASSETS_DIR = os.path.join(BASE_DIR, "assets")

BGM_DIR = os.path.join(BUNDLED_ASSETS_DIR, "bgm")
SFX_DIR = os.path.join(BUNDLED_ASSETS_DIR, "sfx")
SLOT_COVERS_DIR = os.path.join(BUNDLED_ASSETS_DIR, "slot_covers")
FONTS_DIR = os.path.join(BUNDLED_ASSETS_DIR, "fonts")

# ---------------------------------------------------------------------------
# Gốc 2: dữ liệu do chạy máy sinh ra (di dời được)
# ---------------------------------------------------------------------------
ENV_KEY = "CUSTOM_ASSETS_DIR"

# Ký tự phá vỡ filtergraph của FFmpeg. Đường dẫn chứa chúng sẽ làm hỏng `ass='...'`,
# `drawtext=fontfile='...'` — lệnh render chết giữa chừng với "Invalid argument" mà
# không ai đoán ra là do tên thư mục. Chặn từ đầu rẻ hơn nhiều so với debug sau.
# (Windows vốn đã cấm : " < > | ? * trong tên, nên danh sách này là phần còn lại.)
FFMPEG_UNSAFE_CHARS = "'[],;\n\r"


def validate_storage_path(path: str) -> tuple[bool, str, list[str]]:
    """
    Kiểm tra một đường dẫn có dùng làm DATA_DIR được không.

    Trả về (hợp_lệ, thông_báo_lỗi, danh_sách_cảnh_báo). Cảnh báo KHÔNG chặn — chỉ để
    hiển thị lên UI cho user tự quyết.
    """
    warnings: list[str] = []
    path = (path or "").strip().strip('"')
    if not path:
        return False, "Đường dẫn trống.", warnings

    bad = [c for c in FFMPEG_UNSAFE_CHARS if c in path]
    if bad:
        shown = ", ".join(repr(c) for c in bad)
        return False, f"Đường dẫn chứa ký tự làm hỏng lệnh FFmpeg: {shown}", warnings

    if not os.path.isabs(path):
        return False, "Phải là đường dẫn tuyệt đối (ví dụ: D:\\AIVideoAssets).", warnings

    # Thử tạo + ghi thử. Ổ rời chưa cắm, thư mục chỉ-đọc, thiếu quyền — mọi thứ đều
    # lộ ra ở đây, lúc user còn đang nhìn màn hình, chứ không phải giữa lúc render.
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_probe")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
    except OSError as e:
        return False, f"Không ghi được vào thư mục này: {e}", warnings

    if not path.isascii():
        warnings.append(
            "Đường dẫn có ký tự tiếng Việt/Unicode. FFmpeg trên Windows thường vẫn chạy, "
            "nhưng dùng tên thư mục không dấu sẽ chắc chắn hơn."
        )
    if len(path) > 120:
        warnings.append(
            f"Đường dẫn dài {len(path)} ký tự. Windows giới hạn 260 ký tự cho cả đường dẫn — "
            "tên file cảnh + hậu tố render có thể vượt ngưỡng. Nên chọn đường dẫn ngắn."
        )
    if os.path.abspath(path).lower().startswith(BASE_DIR.lower()):
        warnings.append("Thư mục nằm trong mã nguồn — sẽ không giải phóng được ổ C.")
    return True, "", warnings


def _resolve_data_dir() -> tuple[str, bool, str]:
    """
    Chốt DATA_DIR lúc khởi động. Trả về (đường_dẫn, đang_dùng_tuỳ_chỉnh, lý_do_fallback).

    Cấu hình hỏng KHÔNG được làm chết backend: rơi về assets/ mặc định và ghi log to,
    vì mất chỗ lưu tạm còn cứu được, còn backend không bật lên nổi thì mất tất.
    """
    raw = (os.getenv(ENV_KEY) or "").strip().strip('"')
    if not raw:
        return BUNDLED_ASSETS_DIR, False, ""

    ok, err, _ = validate_storage_path(raw)
    if not ok:
        logger.error(
            "[Config] %s=%r không dùng được (%s). Tạm quay về %s.",
            ENV_KEY, raw, err, BUNDLED_ASSETS_DIR,
        )
        return BUNDLED_ASSETS_DIR, False, err
    return os.path.abspath(raw), True, ""


DATA_DIR, IS_CUSTOM_DATA_DIR, DATA_DIR_FALLBACK_REASON = _resolve_data_dir()

AUDIO_DIR = os.path.join(DATA_DIR, "audio")
IMAGES_DIR = os.path.join(DATA_DIR, "images")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
MEDIA_CACHE_DIR = os.path.join(CACHE_DIR, "media")
VEO_TMP_DIR = os.path.join(DATA_DIR, "veo_tmp")
PROJECTS_DIR = os.path.join(DATA_DIR, "projects")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
RENDER_STATUS_DIR = os.path.join(DATA_DIR, "render_status")
VOICES_PREVIEW_DIR = os.path.join(DATA_DIR, "voices_preview")
# Ảnh/video user tự tải lên để GHI ĐÈ một cảnh cụ thể. Tách khỏi uploads/ vì uploads/
# bị cleanup_upload() xoá theo session ngay sau khi render xong, còn file ghi đè phải
# sống qua nhiều lần render lại.
OVERRIDES_DIR = os.path.join(DATA_DIR, "overrides")
# Tiếng động do NGƯỜI DÙNG tự nạp. Tách hẳn khỏi SFX_DIR (tài nguyên đi kèm mã nguồn,
# chỉ đọc, được git theo dõi): ghi file upload vào đó sẽ làm mọi lần tải lên hiện trong
# `git status` — .gitignore có ngoại lệ `!backend/assets/sfx/*.wav` — và giữ dữ liệu
# người dùng nằm lại ổ C kể cả khi đã trỏ CUSTOM_ASSETS_DIR sang ổ khác.
CUSTOM_SFX_DIR = os.path.join(DATA_DIR, "custom_sfx")
# File tạm của MoviePy và các bản nghe thử. MoviePy 2.1.2 đặt temp_audiofile_path=""
# mặc định, tức là ghi "<tên>TEMP_MPY_wvf_snd.mp4" vào CWD — thư mục backend/ — và bỏ
# lại đó nếu encode chết giữa chừng. Trỏ vào đây để rác đi theo ổ dữ liệu và bị dọn tự động.
TEMP_DIR = os.path.join(DATA_DIR, "temp")

PRESETS_FILE = os.path.join(DATA_DIR, "presets.json")
CUSTOM_VOICES_FILE = os.path.join(DATA_DIR, "voices_custom.json")
QUOTA_FILE = os.path.join(CACHE_DIR, "quota.json")

_DATA_SUBDIRS = (
    AUDIO_DIR, IMAGES_DIR, OUTPUT_DIR, CACHE_DIR, MEDIA_CACHE_DIR, VEO_TMP_DIR,
    PROJECTS_DIR, UPLOADS_DIR, RENDER_STATUS_DIR, VOICES_PREVIEW_DIR, OVERRIDES_DIR,
    TEMP_DIR, CUSTOM_SFX_DIR,
)

for _d in _DATA_SUBDIRS:
    os.makedirs(_d, exist_ok=True)


# ---------------------------------------------------------------------------
# Di dời dữ liệu người dùng (chỉ phần NHỎ và KHÔNG tái tạo được)
# ---------------------------------------------------------------------------
# images/ audio/ output/ cache/ KHÔNG chép: hơn 1GB, và đều tự sinh lại được — chép
# chúng sẽ treo backend hàng phút lúc khởi động. Ngược lại presets.json và projects/
# là công sức user, mất là mất hẳn; chúng chỉ vài MB nên chép được ngay.
_MIGRATE_FILES = ("presets.json", "voices_custom.json")
_MIGRATE_DIRS = ("projects", "voices_preview")


def _migrate_user_data() -> None:
    if not IS_CUSTOM_DATA_DIR:
        return
    for name in _MIGRATE_FILES:
        src = os.path.join(BUNDLED_ASSETS_DIR, name)
        dst = os.path.join(DATA_DIR, name)
        if os.path.isfile(src) and not os.path.exists(dst):
            try:
                shutil.copy2(src, dst)
                logger.info("[Config] Đã chuyển %s sang kho dữ liệu mới.", name)
            except OSError as e:
                logger.warning("[Config] Không chuyển được %s: %s", name, e)
    for name in _MIGRATE_DIRS:
        src = os.path.join(BUNDLED_ASSETS_DIR, name)
        dst = os.path.join(DATA_DIR, name)
        if os.path.isdir(src) and not os.listdir(dst):
            try:
                shutil.copytree(src, dst, dirs_exist_ok=True)
                logger.info("[Config] Đã chuyển thư mục %s/ sang kho dữ liệu mới.", name)
            except OSError as e:
                logger.warning("[Config] Không chuyển được %s/: %s", name, e)


_migrate_user_data()


# ---------------------------------------------------------------------------
# Ghi cấu hình xuống .env
# ---------------------------------------------------------------------------
def write_env_value(key: str, value: str) -> None:
    """
    Đặt `key=value` trong backend/.env, GIỮ NGUYÊN mọi dòng khác (API key, comment).

    Ghi qua file tạm rồi os.replace: mất điện giữa chừng cũng không để lại .env cụt
    làm mất sạch API key của user.
    """
    if "\n" in value or "\r" in value:
        raise ValueError("Giá trị không được chứa ký tự xuống dòng.")

    lines: list[str] = []
    if os.path.isfile(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()

    replaced = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        if stripped.split("=", 1)[0].strip() == key:
            lines[i] = f"{key}={value}"
            replaced = True
            break
    if not replaced:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("# Thư mục lưu toàn bộ dữ liệu sinh ra (ảnh, video, cache).")
        lines.append(f"{key}={value}")

    tmp = ENV_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, ENV_FILE)


def _dir_size_mb(path: str) -> float:
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for fname in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, fname))
            except OSError:
                pass
    return round(total / 1024 / 1024, 1)


def get_storage_info(with_sizes: bool = False) -> dict:
    """Trạng thái kho lưu trữ cho endpoint /api/storage-config."""
    info = {
        "data_dir": DATA_DIR,
        "bundled_assets_dir": BUNDLED_ASSETS_DIR,
        "is_custom": IS_CUSTOM_DATA_DIR,
        "configured_value": (os.getenv(ENV_KEY) or "").strip(),
        "fallback_reason": DATA_DIR_FALLBACK_REASON,
        "env_file": ENV_FILE,
        "subdirs": {
            "audio": AUDIO_DIR, "images": IMAGES_DIR, "output": OUTPUT_DIR,
            "cache": CACHE_DIR, "veo_tmp": VEO_TMP_DIR, "projects": PROJECTS_DIR,
            "uploads": UPLOADS_DIR, "overrides": OVERRIDES_DIR,
        },
    }
    try:
        usage = shutil.disk_usage(DATA_DIR)
        info["disk_total_gb"] = round(usage.total / 1024 ** 3, 1)
        info["disk_free_gb"] = round(usage.free / 1024 ** 3, 1)
    except OSError:
        info["disk_total_gb"] = info["disk_free_gb"] = None
    if with_sizes:
        info["used_mb"] = _dir_size_mb(DATA_DIR)
    return info


logger.info(
    "[Config] Kho dữ liệu: %s (%s) | Tài nguyên gốc: %s",
    DATA_DIR, "tuỳ chỉnh" if IS_CUSTOM_DATA_DIR else "mặc định", BUNDLED_ASSETS_DIR,
)
