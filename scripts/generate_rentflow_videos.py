import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import requests
import time
import json

# Define the marketing video campaigns for RentFlow
campaigns = [
    {
        "id": "campaign_1_pain_point",
        "payload": {
            "mode": "storyteller",
            "topic": "Nỗi khổ của chủ nhà trọ khi phải tính tiền điện nước cuối tháng bằng sổ tay và Excel. Giới thiệu giải pháp phần mềm RentFlow giúp tính tiền 100 phòng chỉ với 1 cú click.",
            "num_scenes": 5,
            "aspect_ratio": "9:16",
            "art_style": "Cinematic",
            "voice": "vi-VN-HoaiMyNeural",
            "speech_rate": "+10%"
        }
    },
    {
        "id": "campaign_2_professionalism",
        "payload": {
            "mode": "storyteller",
            "topic": "Kinh nghiệm kinh doanh căn hộ dịch vụ cao cấp. Cách nâng tầm chuyên nghiệp để thu hút khách VIP bằng cách dùng App quản lý riêng cho khách thuê (Tenant Portal) của RentFlow.",
            "num_scenes": 6,
            "aspect_ratio": "9:16",
            "art_style": "Photorealistic",
            "voice": "vi-VN-NamMinhNeural",
            "speech_rate": "+0%"
        }
    }
]

def generate_video(campaign):
    print(f"\n🚀 Khởi tạo chiến dịch: {campaign['id']}")
    print(f"📝 Chủ đề: {campaign['payload']['topic']}")
    
    try:
        # Step 1: Generate Script
        script_payload = {
            "mode": campaign['payload'].get('mode', 'storyteller'),
            "topic": campaign['payload'].get('topic', ''),
            "num_scenes": campaign['payload'].get('num_scenes', 4),
            "art_style": campaign['payload'].get('art_style', 'Cinematic')
        }
        print("⏳ Đang sinh kịch bản...")
        resp_script = requests.post('http://127.0.0.1:8000/api/generate-script', json=script_payload)
        
        if resp_script.status_code != 200:
            print(f"❌ Lỗi khi sinh kịch bản: {resp_script.text}")
            return False
            
        script_data = resp_script.json()
        scenes = script_data.get('scenes', script_data) if isinstance(script_data, dict) else script_data
        
        if not scenes:
            print("❌ Không tạo được kịch bản.")
            return False
            
        # Step 2: Render Video
        render_payload = dict(campaign['payload'])
        render_payload['scenes'] = scenes
        
        resp = requests.post('http://127.0.0.1:8000/api/render-video', json=render_payload)
        
        if resp.status_code != 200:
            print(f"❌ Lỗi khi gửi yêu cầu render: {resp.text}")
            return False
            
        data = resp.json()
        job_id = data.get('job_id')
        print(f"✅ Đã tạo Job ID: {job_id}")
        
        print("⏳ Đang theo dõi tiến trình xử lý video (vui lòng không tắt máy)...")
        for i in range(120):  # max 10 minutes
            time.sleep(5)
            status_resp = requests.get(f'http://127.0.0.1:8000/api/job-status/{job_id}')
            job = status_resp.json()
            status = job['status']
            progress = job['progress']
            message = job['message']
            print(f"  [{i*5:>3}s] {status.upper()} — {progress}% — {message}")
            
            if status == 'done':
                print(f"\n🎉 HOÀN THÀNH CHIẾN DỊCH {campaign['id']}!")
                print(f"👉 Đường dẫn Video: {job.get('video_url')}")
                return True
            
            if status == 'error':
                print(f"\n❌ LỖI RENDER: {job.get('error')}")
                return False
                
        print("\n⏰ Quá thời gian chờ (Timeout)")
        return False
        
    except requests.exceptions.ConnectionError:
        print("❌ LỖI KẾT NỐI: Backend AI-VIDEO-MAKER chưa chạy!")
        print("💡 Hãy chạy file 'start.bat' trong thư mục AI-VIDEO-MAKER trước khi chạy script này.")
        return False

if __name__ == "__main__":
    print("🎬 HỆ THỐNG RENDER VIDEO QUẢNG CÁO RENTFLOW TỰ ĐỘNG 🎬")
    print("=" * 60)
    
    for camp in campaigns:
        success = generate_video(camp)
        if not success:
            print(f"⚠️ Dừng tiến trình do chiến dịch {camp['id']} gặp lỗi.")
            break
        print("-" * 60)
    
    print("\n🏁 TẤT CẢ QUÁ TRÌNH HOÀN TẤT.")
