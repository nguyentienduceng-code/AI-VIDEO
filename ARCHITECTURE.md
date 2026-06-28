# KIẾN TRÚC & CƠ CHẾ HOẠT ĐỘNG: AI VIDEO STUDIO

Tài liệu này mô tả chi tiết cơ cấu, luồng hoạt động và các thành phần kỹ thuật của hệ thống sinh video tự động AI Video Maker, phục vụ cho việc kiểm soát, bảo trì và phát triển tính năng về sau.

---

## 1. Tổng quan Hệ thống (System Overview)

Hệ thống được thiết kế theo kiến trúc Client-Server:
- **Frontend (React + Vite):** Giao diện người dùng đơn trang (SPA) cho phép nhập ý tưởng kịch bản, cấu hình API Key và xem trực tiếp trạng thái tiến trình xử lý cũng như kết quả video.
- **Backend (FastAPI - Python):** Xử lý logic lõi, điều phối các luồng gọi API bên ngoài (LLM, TTS) và tiến hành render video tự động thông qua công cụ MoviePy.
- **Communication:** Giao tiếp qua REST API tại endpoint `/api/generate-video` với định dạng dữ liệu trao đổi là JSON.

---

## 2. Luồng xử lý cốt lõi (Main Workflow)

Quy trình từ ý tưởng thành video hoàn chỉnh diễn ra hoàn toàn tự động qua 4 bước:

### Bước 1: Tiếp nhận yêu cầu (Frontend → Backend)
- Người dùng nhập *Chủ đề (Topic)* và tuỳ chọn *Gemini API Key* vào giao diện.
- Payload được gửi qua HTTP POST tới `http://localhost:8000/api/generate-video`.

### Bước 2: Sinh Kịch bản & Phân cảnh (Gemini Service)
- Dịch vụ `gemini_service.py` gọi **Gemini 1.5 Pro**.
- Hệ thống phân tích chủ đề và trả về 1 mảng JSON chứa 4 phân cảnh.
- Mỗi phân cảnh gồm: số thứ tự cảnh (`scene`), lời thoại (`text`) và mô tả hình ảnh tiếng Anh (`image_prompt`).

### Bước 3: Tạo Âm thanh & Hình ảnh (TTS Service)
- Dịch vụ `tts_service.py` dùng thư viện **Edge-TTS** (Microsoft) để tổng hợp giọng nói Tiếng Việt (mặc định nữ: `vi-VN-HoaiMyNeural`). 
- Đồng thời, tải hoặc sinh hình ảnh tương ứng (hiện tại dùng placeholder ngẫu nhiên, cấu trúc đã mở sẵn để cắm API sinh ảnh chuyên dụng như Imagen 3).

### Bước 4: Render Video (Video Service)
- Dịch vụ `video_service.py` sử dụng thư viện **MoviePy**.
- Cắt/ghép (concatenate) các chuỗi Audio và Hình ảnh đã sinh; tự động căn chỉnh thời lượng hiển thị hình ảnh khớp chính xác với độ dài đoạn audio tương ứng.
- Xuất file `.mp4` (codec libx264/aac) ở định dạng khung hình dọc (Tiktok/Reels) về thư mục `assets/output`.

---

## 3. Cấu trúc mã nguồn (Directory Structure)

```text
AI-VIDEO-MAKER/
├── frontend/                     # UI Application (React + Vite)
│   ├── src/App.jsx               # Logic tương tác, gọi API và hiển thị
│   ├── src/index.css             # Định dạng, hiệu ứng UI
│   └── vite.config.js
├── backend/                      # API Server (FastAPI)
│   ├── main.py                   # Điểm đầu vào, khai báo Endpoint và CORS
│   ├── services/
│   │   ├── gemini_service.py     # Prompt kỹ thuật sư cho LLM
│   │   ├── tts_service.py        # Logic chuyển văn bản thành giọng nói async
│   │   └── video_service.py      # Logic ghép media bằng MoviePy
│   ├── assets/                   # Nơi lưu trữ tài nguyên máy tạo ra
│   │   ├── audio/                # Chứa file .mp3 từng phân cảnh
│   │   ├── images/               # Chứa file .jpg/.png từng phân cảnh
│   │   └── output/               # Chứa file final_video.mp4 
│   └── .env                      # Lưu GEMINI_API_KEY, TTS_VOICE
├── start.bat                     # Script khởi chạy đồng thời FE/BE
└── stop.bat                      # Script tắt sạch các tiến trình ngầm
```

---

## 4. Định hướng phát triển và mở rộng (Future Roadmap)

Tài liệu cung cấp sẵn các "điểm neo" (hook points) để nhà phát triển mở rộng trong tương lai:

1. **Image Generation API:** Thay thế logic placeholder tại `main.py` bằng thư viện gọi API Google Imagen 3, Midjourney hoặc DALL-E thông qua trường `image_prompt`.
2. **Hiệu ứng chữ (Subtitles):** Thêm module sinh file `.srt` từ text hoặc chèn TextClip trong `video_service.py` để tạo phụ đề động (karaoke effect) giúp video hấp dẫn hơn.
3. **Chuyển cảnh (Transitions):** Bổ sung các hiệu ứng chuyển cảnh mượt mà (Fade in/Fade out, Slide) giữa các phân đoạn hình ảnh trong quá trình render.
4. **Tối ưu Pipeline & Scale:** Sử dụng cơ chế hàng đợi (Celery/Redis) hoặc WebSockets để frontend có thể nhận real-time status thay vì HTTP Request chặn (blocking) nếu thời gian render video quá lớn/dài.

---

## 5. Nợ kỹ thuật & Rủi ro hệ thống (Technical Debt & Limitations)

Hiện tại hệ thống đang ở giai đoạn MVP (Minimum Viable Product). Dưới đây là các rủi ro hệ thống và khoản nợ kỹ thuật cần ưu tiên xử lý để đảm bảo ứng dụng đạt chuẩn Production:

1. **Lỗi Event Loop (FastAPI vs Edge-TTS):** `tts_service.py` đang dùng `asyncio.get_event_loop().run_until_complete()` bên trong môi trường FastAPI vốn đã chạy sẵn một event loop, có thể gây lỗi `RuntimeError: This event loop is already running`. *Khắc phục: Dùng endpoint `async def` và gọi `await` trực tiếp.*
2. **Thư viện Gemini bị Deprecated:** Thư viện `google.generativeai` đang bị Google ngừng hỗ trợ (End-of-life). *Khắc phục: Cần migrate sang package mới `google.genai` và dùng **Structured Outputs** (Pydantic Schema) để đảm bảo LLM trả về chuẩn JSON 100%, tránh parse lỗi.*
3. **Nguy cơ Timeout (Kiến trúc HTTP):** Render video bằng `MoviePy` rất nặng. Việc bắt HTTP Request chờ (blocking) có thể gây lỗi 504 Gateway Timeout. *Khắc phục: Áp dụng Hàng đợi (Queue) hoặc WebSocket như đề cập ở phần Định hướng.*
4. **Tràn bộ nhớ do Quản lý File:** Các tài nguyên sinh ra (ảnh, âm thanh, video) lưu trong thư mục `assets/` không được xóa đi sau mỗi chu kỳ chạy, dẫn tới rác bộ nhớ ổ cứng. *Khắc phục: Cần thiết lập cơ chế Cleanup (xóa file temp) tự động sau khi video render xong.*
5. **Đứt gãy Audio-Video (MoviePy):** Việc nối thẳng các clip mà không có crossfade hoặc xử lý audio tĩnh khiến luồng chuyển động hình ảnh trở nên thô và giật cục. *Khắc phục: Áp dụng hiệu ứng âm thanh/hình ảnh khi chuyển đổi (Transition/Crossfade).*
