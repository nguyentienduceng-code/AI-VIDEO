import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import os
import torch
import soundfile as sf
import numpy as np

sys.path.append(r"C:\dev\OmniVoice")
from omnivoice import OmniVoice

device = "cuda:0" if torch.cuda.is_available() else "cpu"
model = OmniVoice.from_pretrained(
    "k2-fsa/OmniVoice",
    device_map=device,
    dtype=torch.float16 if torch.cuda.is_available() else torch.float32
)

ref_path = "test_omni_ref.wav"
instruct = "male, elderly, very low pitch"
ref_text = "Chào bạn, đây là giọng nói của một người đàn ông lớn tuổi, trầm ấm và từ tốn."

# 1. Generate reference audio using Voice Design (zero-shot)
print("Generating Reference Audio...")
torch.manual_seed(42)
audio = model.generate(text=ref_text, instruct=instruct)[0]
sf.write(ref_path, audio, 24000)

# 2. Use the generated reference to clone voice for Scene 1
print("Cloning Scene 1...")
scene1_text = "Mọi biến cố xảy ra không hề ngẫu nhiên."
audio1 = model.generate(text=scene1_text, ref_audio=ref_path, ref_text=ref_text)[0]
sf.write("test_scene1.wav", audio1, 24000)

# 3. Use the generated reference to clone voice for Scene 2
print("Cloning Scene 2...")
scene2_text = "Đã đến lúc thấu hiểu nghiệp quả và tự do thoát khỏi ma trận của tâm trí."
audio2 = model.generate(text=scene2_text, ref_audio=ref_path, ref_text=ref_text)[0]
sf.write("test_scene2.wav", audio2, 24000)

print("Done. Please check test_scene1.wav and test_scene2.wav for consistency.")
