"""
image_upload_service.py
------------------------
Dịch vụ nhận, validate và xử lý ảnh upload từ người dùng.
Hỗ trợ các mode: photo_narration, photo_slideshow.

- Nhận file multipart upload
- Validate: type (jpg/png/webp), size (max 10MB/ảnh)
- Resize nếu quá lớn (max 3840px cạnh dài nhất)
- Lưu vào assets/uploads/{session_id}/
- Trả về list đường dẫn ảnh đã xử lý
"""

from __future__ import annotations

import os
import uuid
import shutil
from typing import List, Tuple

from PIL import Image
from fastapi import UploadFile

# Giới hạn
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB per file
MAX_TOTAL_FILES = 20
MAX_DIMENSION = 3840  # Resize nếu cạnh dài nhất vượt quá
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOADS_DIR = os.path.join(BASE_DIR, "assets", "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)


async def process_uploaded_images(
    files: List[UploadFile],
    session_id: str | None = None,
) -> Tuple[str, List[str]]:
    """
    Xử lý batch upload ảnh.

    Returns:
        (session_id, list_of_image_paths) — session_id dùng để reference
        khi gọi generate-video sau đó.
    """
    if not files:
        raise ValueError("Không có file nào được upload.")
    if len(files) > MAX_TOTAL_FILES:
        raise ValueError(f"Tối đa {MAX_TOTAL_FILES} ảnh mỗi lần upload.")

    sid = session_id or str(uuid.uuid4())
    session_dir = os.path.join(UPLOADS_DIR, sid)
    os.makedirs(session_dir, exist_ok=True)

    saved_paths: List[str] = []

    for i, file in enumerate(files):
        # --- Validate extension ---
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(
                f"File '{file.filename}' không được hỗ trợ. "
                f"Chỉ chấp nhận: {', '.join(ALLOWED_EXTENSIONS)}"
            )

        # --- Validate content type ---
        if file.content_type and file.content_type not in ALLOWED_TYPES:
            raise ValueError(
                f"File '{file.filename}' có content-type không hợp lệ: {file.content_type}"
            )

        # --- Read & validate size ---
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise ValueError(
                f"File '{file.filename}' vượt quá giới hạn {MAX_FILE_SIZE // (1024*1024)}MB."
            )

        # --- Save raw file first ---
        out_name = f"img_{i+1:03d}{ext}"
        raw_path = os.path.join(session_dir, out_name)
        with open(raw_path, "wb") as f:
            f.write(content)

        # --- Resize if necessary (keep aspect ratio) ---
        try:
            img = Image.open(raw_path)
            w, h = img.size
            if max(w, h) > MAX_DIMENSION:
                ratio = MAX_DIMENSION / max(w, h)
                new_size = (int(w * ratio), int(h * ratio))
                img = img.resize(new_size, Image.LANCZOS)

            # Convert RGBA to RGB (MoviePy prefers RGB)
            if img.mode == "RGBA":
                bg = Image.new("RGB", img.size, (0, 0, 0))
                bg.paste(img, mask=img.split()[3])
                img = bg

            # Save as PNG for consistency
            final_path = os.path.join(session_dir, f"img_{i+1:03d}.png")
            img.save(final_path, "PNG", quality=95)
            img.close()

            # Remove raw file if it was different format
            if raw_path != final_path and os.path.exists(raw_path):
                os.remove(raw_path)

            saved_paths.append(final_path)

        except Exception as e:
            raise ValueError(f"Không thể xử lý ảnh '{file.filename}': {e}")

    return sid, saved_paths


def get_upload_paths(session_id: str) -> List[str]:
    """Lấy lại danh sách đường dẫn ảnh đã upload theo session_id."""
    session_dir = os.path.join(UPLOADS_DIR, session_id)
    if not os.path.isdir(session_dir):
        return []

    paths = []
    for fname in sorted(os.listdir(session_dir)):
        if fname.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            paths.append(os.path.join(session_dir, fname))
    return paths


def cleanup_upload(session_id: str):
    """Xóa toàn bộ ảnh upload của 1 session."""
    session_dir = os.path.join(UPLOADS_DIR, session_id)
    shutil.rmtree(session_dir, ignore_errors=True)
