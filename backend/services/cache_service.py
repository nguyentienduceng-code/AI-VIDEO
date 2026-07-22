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
import shutil
import time
from typing import Any, Optional

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "cache")
MEDIA_CACHE_DIR = os.path.join(CACHE_DIR, "media")
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(MEDIA_CACHE_DIR, exist_ok=True)

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
            print(f"Cache save error: {e}")

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
                        print(f"[Cache] HIT: {prefix} → {os.path.basename(final_output)}")
                        return True
                    except Exception as e:
                        print(f"[Cache] Copy error: {e}")
                        return False
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
            print(f"[Cache] SAVED: {prefix} → {os.path.basename(cache_path)} ({os.path.getsize(cache_path) / 1024:.0f}KB)")
        except Exception as e:
            print(f"[Cache] Save error: {e}")
        
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
                    print(f"[Cache] CLEANUP: Xóa {os.path.basename(fpath)} ({fsize / 1024 / 1024:.1f}MB, {age / 86400:.0f} ngày tuổi)")
        except Exception as e:
            print(f"[Cache] Cleanup error: {e}")

    def get_cache_stats(self) -> dict:
        """Thống kê dung lượng và số file cache (dành cho API /api/cache-stats)."""
        total_size = 0
        file_count = 0
        for dirpath, _, filenames in os.walk(MEDIA_CACHE_DIR):
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                if os.path.isfile(fpath):
                    total_size += os.path.getsize(fpath)
                    file_count += 1
        return {
            "media_files": file_count,
            "total_size_mb": round(total_size / 1024 / 1024, 1),
            "max_size_gb": MAX_CACHE_SIZE_GB,
            "cache_dir": MEDIA_CACHE_DIR,
        }


cache = CacheService()
