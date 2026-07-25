# AI Image Keywords — Prompt cinematic cho ảnh AI

Dùng khi nguồn hình là **Ảnh AI** (Imagen 3 / gemini-flash-image / Pollinations FLUX):
chủ đề giả tưởng, anime, siêu thực, nhân vật hư cấu — những thứ KHÔNG có trên kho video stock.

> ⚠️ TUYỆT ĐỐI KHÔNG dùng kiểu prompt này khi nguồn là video stock (Pexels) — xem `stock-footage-guide.md`.

## Công thức prompt

`[Subject/Action] + [Environment/Background] + [Lighting & Atmosphere] + [Camera Angle & Lens] + [Render Style & Quality]`

Ví dụ đầy đủ:
`A cute yellow robot exploring a neon cyberpunk market, rain-soaked streets with glowing signs, moody volumetric lighting, low-angle wide shot on 35mm lens, Unreal Engine 5 render, cinematic color grading, 8k.`

## Kho keyword (dùng luân phiên để tránh lặp)

**Chất lượng siêu thực:** hyper-realistic, photorealistic, ultra-detailed, 8k resolution,
award-winning photography, National Geographic style, raw photo.

**Ánh sáng:** cinematic lighting, dramatic shadows, volumetric lighting, golden hour,
neon glow, moody atmosphere, ray tracing, studio lighting, rim light, chiaroscuro.

**Góc máy & ống kính:** extreme close-up, wide-angle shot, aerial view, drone shot,
macro photography, shot on 35mm lens, depth of field, bokeh, over-the-shoulder, dutch angle.

**Kết xuất/phong cách:** Unreal Engine 5 render, Octane render, cinematic color grading,
teal and orange lut, film grain, anamorphic lens flare.

**Phong cách nghệ thuật (khi cần):** Studio Ghibli anime, Pixar 3D, cyberpunk 2077,
dark fantasy gothic, watercolor painting, comic book manga, vintage 35mm film.

## Character Consistency (giữ nhân vật nhất quán)

Nếu video có 1 nhân vật xuyên suốt: mô tả LẶP LẠI ngoại hình ở MỌI cảnh
(VD: `a girl with short black hair, green bomber jacket, round glasses`) và dùng chung
1 tông màu ánh sáng (`cinematic teal and orange lighting`). App hỗ trợ truyền
`character_description` + `sync_characters` để tự chèn.

## Negative prompt (tránh lỗi ảnh)

Gợi ý cho app (`negative_prompt`): `blurry, low quality, distorted, deformed, bad anatomy,
extra limbs, poorly drawn face`. Cinematic thêm: `flat lighting, amateur, phone camera, cartoon`.
