export const API_BASE = 'http://localhost:8000';

export const MODE_MAP = {
  storyteller: 'storyteller',
  img2vid: 'photo_narration',
  slideshow: 'photo_slideshow',
  script: 'script_video',
  quiz: 'quiz_listicle',
  manual: 'manual',
};

export const MODES = [
  { id: 'storyteller', icon: '✨', title: 'AI Storyteller', desc: 'Nhập chủ đề → AI viết kịch bản,\nsinh ảnh, render video tự động' },
  { id: 'img2vid', icon: '🖼️', title: 'Ảnh → Video', desc: 'Upload ảnh → AI viết lời bình\nvà kể chuyện cho từng ảnh' },
  { id: 'slideshow', icon: '🎞️', title: 'Slideshow', desc: 'Upload ảnh → Video cinematic\nvới nhạc nền, hiệu ứng' },
  { id: 'script', icon: '📝', title: 'Script → Video', desc: 'Paste script viết sẵn → AI chia\ncảnh, sinh ảnh, đọc lời' },
  { id: 'quiz', icon: '❓', title: 'Quiz / Listicle', desc: 'Chủ đề → AI sinh video dạng\n"Top N" hoặc hỏi-đáp' },
];

export const STYLES = [
  { value: 'Anime illustration, vibrant colors, Studio Ghibli inspired', label: 'Anime (Hoạt hình)' },
  { value: 'Photorealistic, cinematic lighting, 8K UHD', label: 'Realistic (Thực tế)' },
  { value: '3D render, Pixar style, soft lighting, highly detailed', label: '3D Render' },
  { value: 'Cinematic, dramatic lighting, widescreen composition', label: 'Cinematic (Điện ảnh)' },
  { value: 'Watercolor painting, soft brush strokes, artistic', label: 'Watercolor (Màu nước)' },
  { value: 'Cyberpunk 2077 style, neon lights, futuristic city, sci-fi', label: 'Cyberpunk 2077 (Tương lai)' },
  { value: 'Dark Fantasy, gothic, moody lighting, mysterious, highly detailed', label: 'Dark Fantasy (Huyền bí)' },
  { value: 'Vintage 35mm film, grainy, retro aesthetic, warm nostalgic colors', label: 'Vintage Film (Phim cũ)' },
  { value: 'Comic book panel, manga style, heavy shadows, halftone patterns, dramatic angles', label: 'Comic/Manga (Truyện tranh)' },
  { value: 'Hand-drawn Japanese animation, pastel tones, beautiful scenery, nostalgic', label: 'Japanese Animation (Tươi sáng)' },
];

export const VOICES = [
  { value: 'vi-VN-NamMinhNeural', label: 'Nam - Nam Minh (Cơ bản)' },
  { value: 'vi-VN-NamMinhNeural_deep', label: 'Nam - Nam Minh (Giọng Nam Trầm)' },
  { value: 'vi-VN-HoaiMyNeural', label: 'Nữ - Hoài My (Cơ bản)' },
  { value: 'omnivoice_female_storyteller_vi', label: 'OmniVoice - Nữ (Cuốn hút/Năng lượng)' },
  { value: 'omnivoice_male_podcast_vi', label: 'OmniVoice - Nam (Podcast/Trầm ấm)' },
  { value: 'omnivoice_male_elderly_vi', label: 'OmniVoice - Nam (Cụ già/Kể chuyện)' },
  { value: 'omnivoice_male_middle_aged_low_vi', label: 'OmniVoice - Nam (Trung niên/Trầm êm)' },
  { value: 'omnivoice_female_whisper_vi', label: 'OmniVoice - Nữ (Thì thầm/Tâm sự)' },
  { value: 'omnivoice_female_child_vi', label: 'OmniVoice - Nữ (Trẻ em/Hoạt hình)' },
  { value: 'minion_pro', label: 'Đặc biệt - Minion Pro (Nhấn nhá)' },
];

// Niche nội dung — kích hoạt palette hiệu ứng + bản vẽ cấu trúc cảnh riêng (backend NICHE_BLUEPRINTS)
export const NICHE_OPTIONS = [
  { value: '', label: '— Tự do (theo tone) —' },
  { value: 'book', label: '📚 Review Sách/Phim' },
  { value: 'finance', label: '💰 Tài chính/Làm giàu' },
  { value: 'history', label: '🏛️ Lịch sử/Bí ẩn' },
  { value: 'psychology', label: '🧠 Tâm lý/Self-help' },
  { value: 'truecrime', label: '🔪 True Crime/Vụ án' },
  { value: 'travel', label: '🌍 Du lịch/Khám phá' },
];

export const NARRATION_TONES = [
  { value: 'viral', label: '🔥 Viral Hook', desc: 'Gây sốc, cuốn hút, FOMO' },
  { value: 'storytelling', label: '📖 Kể chuyện', desc: 'Trầm lắng, cliffhanger, style review sách/phim' },
  { value: 'educational', label: '📚 Giáo dục', desc: 'Rõ ràng, logic, dẫn chứng' },
  { value: 'emotional', label: '💔 Cảm xúc', desc: 'Storytelling sâu sắc' },
  { value: 'humorous', label: '😂 Hài hước', desc: 'Dí dỏm, bất ngờ' },
];

export const DURATION_OPTIONS = [
  { value: '15s',  label: '15s',  scenes: 4 },
  { value: '30s',  label: '30s',  scenes: 5 },
  { value: '60s',  label: '60s',  scenes: 7 },
  { value: '90s',  label: '90s',  scenes: 9 },
  { value: '120s', label: '2 min', scenes: 12 },
  { value: '180s', label: '3 min', scenes: 16 },
  { value: '240s', label: '4 min', scenes: 18 },
  { value: '300s', label: '5 min', scenes: 20 },
];

export const SUBTITLE_STYLES = [
  { value: 'karaoke_bold', label: 'Karaoke Nhịp điệu (Viền đen)' },
  { value: 'hormozi_bold', label: 'Hormozi (Đa sắc, nảy chữ)' },
  { value: 'cinematic_box', label: 'Điện ảnh (Nền mờ)' },
  { value: 'minimal_white', label: 'Tối giản (Chữ trắng, bóng mờ)' },
];

// Chuyển cảnh — đồng bộ với backend video_service.VALID_TRANSITIONS
export const TRANSITIONS = [
  { value: 'crossfade', label: '🌫️ Hòa tan (Crossfade)' },
  { value: 'fade_black', label: '⬛ Mờ đen (Fade Black)' },
  { value: 'fade_white', label: '⚡ Chớp trắng (Flash)' },
  { value: 'zoom_through', label: '🔍 Lao xuyên (Zoom Through)' },
  { value: 'zoom_punch', label: '🥊 Giật zoom (Zoom Punch)' },
  { value: 'slide_left', label: '⬅️ Trượt trái (Slide)' },
  { value: 'slide_right', label: '➡️ Trượt phải (Slide)' },
  { value: 'slide_up', label: '⬆️ Trượt lên (Slide)' },
  { value: 'slide_down', label: '⬇️ Trượt xuống (Slide)' },
  { value: 'wipe_right', label: '🧹 Gạt ngang (Wipe)' },
  { value: 'wipe_down', label: '🧹 Gạt dọc (Wipe)' },
  { value: 'whip_pan', label: '💨 Quét nhanh (Whip Pan)' },
  { value: 'page_flip', label: '📖 Lật trang sách' },
  { value: 'droplet', label: '💧 Giọt nước lan' },
];

// Hiệu ứng âm thanh per-scene — khớp file trong assets/sfx/
export const SFX_OPTIONS = [
  { value: '', label: '🔇 Không tiếng' },
  { value: 'whoosh', label: '💨 Vèo (Whoosh)' },
  { value: 'swoosh_soft', label: '🍃 Vèo nhẹ (Swoosh Soft)' },
  { value: 'pop', label: '🫧 Bụp (Pop)' },
  { value: 'tick', label: '👆 Tíc (Click)' },
  { value: 'ding', label: '🔔 Ding' },
  { value: 'bell', label: '🛎️ Chuông (Bell)' },
  { value: 'shimmer', label: '✨ Lấp lánh (Shimmer)' },
  { value: 'riser', label: '📈 Riser (dâng trào)' },
  { value: 'bass_drop', label: '🔊 Trầm rơi (Bass Drop)' },
  { value: 'impact', label: '💥 Va đập (Impact)' },
  { value: 'suspense', label: '😱 Hồi hộp (Suspense)' },
  { value: 'heartbeat', label: '🫀 Nhịp tim (Heartbeat)' },
  { value: 'laugh', label: '😂 Cười (Laugh)' },
];

export const COLOR_GRADINGS = [
  { value: 'warm_cinematic', label: '🎬 Điện ảnh Ấm (Teal & Orange)' },
  { value: 'cool_matrix', label: '🌌 Tương lai (Cyan / Cool Matrix)' },
  { value: 'vintage_film', label: '🎞️ Phim cũ (Vintage 35mm Retro)' },
  { value: 'vivid_pop', label: '🔥 Rực rỡ (Vivid Pop Viral)' },
  { value: 'noir_dramatic', label: '🖤 Trắng đen (Noir Dramatic)' },
  { value: 'none', label: '⚪ Gốc (Không dùng lọc màu)' },
];
