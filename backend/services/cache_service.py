"""
cache_service.py
----------------
NÂNG CẤP V2: Hỗ trợ cache cả JSON metadata VÀ binary media files (ảnh/video).

Tính năng mới:
  - get_media() / set_media(): Cache binary files (PNG, MP4) theo hash prompt.
  - Auto-cleanup: Xóa file cache cũ hơn 7 ngày khi tổng cache > MAX_CACHE_SIZE_GB.
  - Thread-safe: Dùng atomic write (tmp + rename) tránh file corruption.
"""

import os
import json
import hashlib
import logging
import shutil
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

from config import CACHE_DIR, MEDIA_CACHE_DIR  # thư mục do config tạo sẵn

MAX_CACHE_SIZE_GB = 5       # Giới hạn dung lượng cache tối đa
MAX_CACHE_AGE_DAYS = 7      # Xóa file cũ hơn 7 ngày khi vượt ngưỡng


class CacheService:
    # ──────────────────────────────────────────────────────────
    # JSON Cache (giữ nguyên logic cũ)
    # ──────────────────────────────────────────────────────────
    def _get_key(self, prefix: str, **kwargs) -> str:
        """Tạo cache key dạng tên file từ prefix + hash các kwargs."""
        sorted_items = sorted(kwargs.items())
        data_str = json.dumps(sorted_items, default=str)
        hash_val = hashlib.md5(data_str.encode('utf-8')).hexdigest()
        return f"{prefix}_{hash_val}.json"

    def get(self, prefix: str, **kwargs) -> Optional[Any]:
        filepath = os.path.join(CACHE_DIR, self._get_key(prefix, **kwargs))
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def set(self, prefix: str, value: Any, **kwargs):
        filepath = os.path.join(CACHE_DIR, self._get_key(prefix, **kwargs))
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(value, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Cache save error: {e}")

    # ──────────────────────────────────────────────────────────
    # Media Cache (MỚI — cache ảnh/video binary)
    # ──────────────────────────────────────────────────────────
    def _media_key(self, prefix: str, **kwargs) -> str:
        """
        Tạo cache key cho media file.
        Hash dựa trên các tham số quyết định nội dung output
        (prompt, aspect_ratio, art_style, negative_prompt, seed).
        """
        sorted_items = sorted(kwargs.items())
        data_str = json.dumps(sorted_items, default=str)
        hash_val = hashlib.md5(data_str.encode('utf-8')).hexdigest()
        return f"{prefix}_{hash_val}"

    def get_media(self, prefix: str, output_path: str, **kwargs) -> bool:
        """
        Kiểm tra cache và copy file media vào output_path nếu có.
        
        Args:
            prefix: Loại media ("imagen", "veo", "pexels_photo", ...)
            output_path: Đường dẫn đích mà pipeline mong đợi file sẽ nằm ở đó.
            **kwargs: Các tham số để tạo cache key (prompt, aspect_ratio, ...)
        
        Returns:
            True nếu cache hit (đã copy file), False nếu miss.
        """
        key = self._media_key(prefix, **kwargs)
        
        # Tìm file cache với bất kỳ extension nào
        for fname in os.listdir(MEDIA_CACHE_DIR):
            if fname.startswith(key + "."):
                cached_path = os.path.join(MEDIA_CACHE_DIR, fname)
                if os.path.isfile(cached_path) and os.path.getsize(cached_path) > 0:
                    try:
                        # Xác định extension từ file cache
                        cached_ext = os.path.splitext(fname)[1]
                        # Nếu output_path có extension khác, điều chỉnh
                        out_base, out_ext = os.path.splitext(output_path)
                        final_output = output_path
                        if cached_ext != out_ext and cached_ext:
                            final_output = out_base + cached_ext
                        
                        shutil.copy2(cached_path, final_output)
                        # Cập nhật access time để LRU cleanup hoạt động
                        os.utime(cached_path)
                        logger.info(f"[Cache] HIT: {prefix} → {os.path.basename(final_output)}")
                        return True
                    except Exception as e:
                        logger.warning(f"[Cache] Copy error: {e}")
                        return False
        return False

    def has_media(self, prefix: str, **kwargs) -> bool:
        """
        Cache có sẵn media này không — KHÔNG chép file ra.

        Dùng cho đèn báo trạng thái trên UI (🟢 đã có / 🔴 sẽ tạo mới): giao diện hỏi
        liên tục mỗi lần user gõ phím, nên tuyệt đối không được chạm vào file như
        get_media(). Cũng KHÔNG cập nhật access time — chỉ nhìn thì không tính là dùng.
        """
        key = self._media_key(prefix, **kwargs)
        try:
            for fname in os.listdir(MEDIA_CACHE_DIR):
                if fname.startswith(key + "."):
                    fpath = os.path.join(MEDIA_CACHE_DIR, fname)
                    if os.path.isfile(fpath) and os.path.getsize(fpath) > 0:
                        return True
        except OSError:
            pass
        return False

    def set_media(self, prefix: str, source_path: str, **kwargs):
        """
        Lưu file media vào cache.
        
        Args:
            prefix: Loại media ("imagen", "veo", ...)
            source_path: Đường dẫn file media vừa sinh xong.
            **kwargs: Các tham số tạo cache key.
        """
        if not os.path.isfile(source_path) or os.path.getsize(source_path) == 0:
            return
        
        key = self._media_key(prefix, **kwargs)
        ext = os.path.splitext(source_path)[1] or ".bin"
        cache_path = os.path.join(MEDIA_CACHE_DIR, f"{key}{ext}")
        
        try:
            # Atomic copy: ghi vào tmp rồi rename
            tmp_path = cache_path + ".tmp"
            shutil.copy2(source_path, tmp_path)
            os.replace(tmp_path, cache_path)
            logger.info(f"[Cache] SAVED: {prefix} → {os.path.basename(cache_path)} ({os.path.getsize(cache_path) / 1024:.0f}KB)")
        except Exception as e:
            logger.warning(f"[Cache] Save error: {e}")
        
        # Kiểm tra dung lượng cache, cleanup nếu cần
        self._auto_cleanup()

    def _auto_cleanup(self):
        """Xóa file cache cũ khi tổng dung lượng vượt MAX_CACHE_SIZE_GB."""
        try:
            total_size = 0
            files_info = []
            
            for dirpath, _, filenames in os.walk(MEDIA_CACHE_DIR):
                for fname in filenames:
                    fpath = os.path.join(dirpath, fname)
                    if os.path.isfile(fpath):
                        stat = os.stat(fpath)
                        total_size += stat.st_size
                        files_info.append((fpath, stat.st_mtime))
            
            max_bytes = MAX_CACHE_SIZE_GB * 1024 * 1024 * 1024
            if total_size <= max_bytes:
                return
            
            # Sắp xếp theo thời gian sửa đổi (cũ nhất trước)
            files_info.sort(key=lambda x: x[1])
            now = time.time()
            max_age_seconds = MAX_CACHE_AGE_DAYS * 86400
            
            for fpath, mtime in files_info:
                if total_size <= max_bytes * 0.8:  # Giảm xuống 80% ngưỡng
                    break
                age = now - mtime
                if age > max_age_seconds:
                    fsize = os.path.getsize(fpath)
                    os.remove(fpath)
                    total_size -= fsize
                    logger.info(f"[Cache] CLEANUP: Xóa {os.path.basename(fpath)} ({fsize / 1024 / 1024:.1f}MB, {age / 86400:.0f} ngày tuổi)")
        except Exception as e:
            logger.warning(f"[Cache] Cleanup error: {e}")

    # ──────────────────────────────────────────────────────────
    # Thống kê & dọn dẹp thủ công
    # ──────────────────────────────────────────────────────────
    # quota.json nằm CHUNG thư mục với cache JSON nhưng KHÔNG phải cache: nó đếm số lần
    # gọi API còn lại trong ngày. Xoá nó = quota tự reset về 0 và app tưởng còn nguyên
    # hạn mức, gọi tiếp cho tới khi Google trả 429.
    PROTECTED_JSON = {"quota.json"}

    def _scan(self, dirpath: str, only_json: bool = False) -> tuple[int, int]:
        """(số_file, tổng_byte) — không đệ quy vào thư mục con."""
        count = size = 0
        try:
            for fname in os.listdir(dirpath):
                if only_json and (not fname.endswith(".json") or fname in self.PROTECTED_JSON):
                    continue
                fpath = os.path.join(dirpath, fname)
                if os.path.isfile(fpath):
                    count += 1
                    size += os.path.getsize(fpath)
        except OSError:
            pass
        return count, size

    def get_cache_stats(self) -> dict:
        """Thống kê dung lượng và số file cache (dành cho API /api/cache-stats)."""
        media_count, media_size = self._scan(MEDIA_CACHE_DIR)
        json_count, json_size = self._scan(CACHE_DIR, only_json=True)
        return {
            "media_files": media_count,
            "media_size_mb": round(media_size / 1024 / 1024, 1),
            "script_files": json_count,
            "script_size_mb": round(json_size / 1024 / 1024, 1),
            "total_size_mb": round((media_size + json_size) / 1024 / 1024, 1),
            "max_size_gb": MAX_CACHE_SIZE_GB,
            "cache_dir": MEDIA_CACHE_DIR,
        }

    def clear(self, include_script_cache: bool = False) -> dict:
        """
        Xoá bộ nhớ đệm theo yêu cầu của người dùng.

        `include_script_cache=False` (mặc định) chỉ xoá media — ảnh và giọng đọc, tức
        toàn bộ phần chiếm dung lượng. Kịch bản Gemini đã sinh chỉ vài KB mỗi bản nhưng
        sinh lại thì TỐN QUOTA API, nên phải bật tường minh mới xoá.

        Xoá cache KHÔNG làm hỏng gì: lần render sau chỉ đơn giản là gọi AI tạo lại.
        """
        removed = freed = 0

        def _wipe(dirpath: str, only_json: bool = False):
            nonlocal removed, freed
            try:
                names = os.listdir(dirpath)
            except OSError:
                return
            for fname in names:
                if only_json and (not fname.endswith(".json") or fname in self.PROTECTED_JSON):
                    continue
                fpath = os.path.join(dirpath, fname)
                if not os.path.isfile(fpath):
                    continue
                try:
                    fsize = os.path.getsize(fpath)
                    os.remove(fpath)
                    removed += 1
                    freed += fsize
                except OSError as e:
                    # File đang bị một job render mở → bỏ qua, lần dọn sau sẽ tới lượt nó.
                    logger.warning(f"[Cache] Không xoá được {fname}: {e}")

        _wipe(MEDIA_CACHE_DIR)
        if include_script_cache:
            _wipe(CACHE_DIR, only_json=True)

        freed_mb = round(freed / 1024 / 1024, 1)
        logger.info(f"[Cache] CLEAR: xoá {removed} file, giải phóng {freed_mb}MB.")
        return {"removed_files": removed, "freed_mb": freed_mb}


cache = CacheService()
