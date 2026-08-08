import os
from typing import List
import itertools
from dotenv import load_dotenv

load_dotenv()

class KeyManager:
    """
    Quản lý xoay vòng (Rotation) API Keys để chống lại lỗi 429 Quota Exceeded.
    Hỗ trợ lấy danh sách keys từ biến môi trường (ví dụ: GEMINI_API_KEY_1, GEMINI_API_KEY_2,...)
    """
    def __init__(self, prefix: str = "GEMINI_API_KEY"):
        self.keys: List[str] = []
        
        # Lấy key chính
        main_key = os.getenv(prefix)
        if main_key:
            self.keys.append(main_key)
            
        # Lấy các key dự phòng có đánh số
        idx = 1
        while True:
            backup_key = os.getenv(f"{prefix}_{idx}")
            if not backup_key:
                break
            if backup_key not in self.keys:
                self.keys.append(backup_key)
            idx += 1
            
        if not self.keys:
            # Fallback nếu không cấu hình
            self.keys = [""]
            
        self.cycle = itertools.cycle(self.keys)
        self.current_key = next(self.cycle)
        
    def get_current_key(self) -> str:
        return self.current_key
        
    def get_key(self) -> str:
        return self.current_key
        
    def rotate(self) -> str:
        """Chuyển sang key tiếp theo và trả về key đó."""
        self.current_key = next(self.cycle)
        return self.current_key

# Global instances cho dễ sử dụng
gemini_keys = KeyManager("GEMINI_API_KEY")
fal_keys = KeyManager("FAL_KEY")
