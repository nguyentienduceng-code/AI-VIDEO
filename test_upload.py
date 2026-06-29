"""Test upload images endpoint."""
import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import requests
from PIL import Image
import io
import os

# Create 3 test images
test_images = []
for i in range(3):
    img = Image.new('RGB', (800, 600), color=(50 + i*60, 100, 200 - i*50))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    test_images.append(('images', (f'test_{i+1}.png', buf, 'image/png')))

# Upload
resp = requests.post('http://127.0.0.1:8000/api/upload-images', files=test_images)
print(f"Status: {resp.status_code}")
data = resp.json()
print(f"Response: {data}")

if resp.status_code == 200:
    session_id = data['session_id']
    print(f"✅ Upload OK — session_id: {session_id}, count: {data['count']}")
    
    # Verify files exist
    upload_dir = os.path.join(os.path.dirname(__file__), 'backend', 'assets', 'uploads', session_id)
    if os.path.isdir(upload_dir):
        files = os.listdir(upload_dir)
        print(f"✅ Files on disk: {files}")
    else:
        print(f"❌ Upload dir not found: {upload_dir}")
else:
    print(f"❌ Upload failed: {data}")
