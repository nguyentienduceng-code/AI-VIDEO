export const API_BASE = 'http://localhost:8000';
// BookTok AI App server — dùng để nạp kịch bản JSON đã export.
export const BOOKTOK_API_BASE = 'http://localhost:3005';

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
  { value: 'Oil painting, textured canvas brushstrokes, Renaissance style, chiaroscuro lighting', label: 'Sơn dầu Cổ điển (Nghệ thuật)' },
  { value: 'Traditional Asian ink wash painting, Shan Shui watercolor, misty paper texture', label: 'Tranh Thủy mặc (Thơ ca)' },
  { value: 'Architectural render, cinematic wide angle, dramatic twilight lighting, 8k detail', label: 'Kiến trúc Điện ảnh (Công trình)' },
  { value: 'Architectural blueprint sketch, technical drawing lines, blue background', label: 'Bản vẽ Phác thảo (Blueprint)' },
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
  { value: 'art_masterpiece', label: '🎨 Tranh & Nghệ thuật' },
  { value: 'poetry_literature', label: '📜 Thơ ca & Văn học' },
  { value: 'architecture_wonders', label: '🏛️ Công trình & Kỳ quan' },
  { value: 'finance', label: '💰 Tài chính/Làm giàu' },
  { value: 'history', label: '📜 Lịch sử/Bí ẩn' },
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

// `scenes` PHẢI khớp DURATION_CONFIG[...]['suggested_scenes'] của backend
// (gemini_service.py). Số cũ cho ~24 từ/cảnh ≈ 8.5 giây/cảnh — video ì như slideshow.
// Số mới nhắm ~12 từ/cảnh ≈ 4 giây/cảnh, đúng nhịp short.
export const DURATION_OPTIONS = [
  { value: '15s',  label: '15s',  scenes: 4 },
  { value: '30s',  label: '30s',  scenes: 6 },
  { value: '60s',  label: '60s',  scenes: 12 },
  { value: '90s',  label: '90s',  scenes: 19 },
  { value: '120s', label: '2 min', scenes: 25 },
  { value: '180s', label: '3 min', scenes: 30 },
  { value: '240s', label: '4 min', scenes: 35 },
  { value: '300s', label: '5 min', scenes: 40 },
  { value: '480s', label: '8 min', scenes: 45 },
  { value: '600s', label: '10m Podcast', scenes: 60 },
  { value: '900s', label: '15m Podcast', scenes: 75 },
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
  { value: 'bell_chime', label: '🔔 Chuông ngân (Bell Chime)' },
  { value: 'shimmer', label: '✨ Lấp lánh (Shimmer)' },
  { value: 'riser', label: '📈 Riser (dâng trào)' },
  { value: 'bass_drop', label: '🔊 Trầm rơi (Bass Drop)' },
  { value: 'impact', label: '💥 Va đập (Impact)' },
  { value: 'suspense', label: '😱 Hồi hộp (Suspense)' },
  { value: 'heartbeat', label: '🫀 Nhịp tim (Heartbeat)' },
  { value: 'heartbeat_dramatic', label: '💓 Tim dồn dập (Dramatic Heartbeat)' },
  { value: 'laugh', label: '😂 Cười (Laugh)' },
  { value: 'breath', label: '😮‍💨 Hơi thở (Breath)' },
  { value: 'deep_breath', label: '😮‍💨 Hít sâu (Deep Breath)' },
  { value: 'cash_register', label: '💰 Máy tính tiền (Cash Register)' },
  { value: 'tape_rewind', label: '⏪ Tua băng (Tape Rewind)' },
  { value: 'typewriter_clack', label: '⌨️ Lạch cạch (Typewriter Clack)' },
  { value: 'whip_whoosh', label: '🌪️ Vút (Whip Whoosh)' },
  { value: 'ui_click', label: '🖱️ Click (UI Click)' },
  { value: 'braam_horn', label: '📯 Còi (Braam Horn)' },
  { value: 'camera_fast', label: '📸 Tách (Camera Fast)' },
  { value: 'page_turn', label: '📄 Lật trang (Page Turn)' },
  { value: 'clock_tick', label: '⏱️ Tích tắc (Clock Tick)' },
];

// Tiếng trục quay Hook Máy Xèng — đồng bộ với backend video_service.HOOK_REEL_SOUNDS.
// Thêm tiếng mới: chạy `python tools/fit_hook_sfx.py <file> --name <id>` rồi khai báo
// 1 dòng ở đây và 1 dòng trong video_service.py.
export const HOOK_REEL_SOUNDS = [
  { value: 'tick_wood', label: '🪵 Gõ mộc (khớp từng bìa lướt qua)' },
  { value: 'money_counter', label: '💵 Máy đếm tiền' },
  { value: 'arcade_8bit', label: '🕹️ Arcade 8-bit (bản cũ)' },
];

export const HOOK_SFX_OPTIONS = {
  carousel_quote: HOOK_REEL_SOUNDS,
  typewriter_quote: [
    { value: 'typewriter_fast', label: '⌨️ Lạch cạch (Fast Typewriter)' },
  ],
  blackout_question: [
    { value: 'typewriter_fast', label: '⌨️ Lạch cạch (Fast Typewriter)' },
  ],
  camera_shutter: [
    { value: 'camera_shutter', label: '📸 Tách máy ảnh (Camera Shutter)' },
  ],
  cyber_glitch: [
    { value: 'digital_glitch', label: '⚡ Xẹt điện/Glitch (Digital Whoosh)' },
  ],
  vintage_film_burn: [
    { value: 'film_projector', label: '🎞️ Lạch cạch máy chiếu (Film Projector)' },
  ],
  // Chỉ dùng cho Outro — xem OUTRO_ONLY_EFFECTS bên dưới và build_cta_card_hook (backend).
  cta_card: [
    { value: 'cta_chime', label: '🔔 Chuông reo (Chime)' },
    { value: 'cta_pop', label: '🫧 Bụp vui tươi (Pop)' },
  ],
  smash_cut_blackout: [
    { value: 'impact_boom', label: '💥 Đóng sập (Smash Boom)' },
  ],
  cinematic_letterbox: [
    { value: 'cinematic_swell', label: '📈 Dâng trào (Cinematic Swell)' },
  ],
  paper_rip_split: [
    { value: 'impact_boom', label: '💥 Nổ/Va đập (Impact Boom)' },
  ],
  // 6 HOOK NGHỆ THUẬT MỚI:
  double_exposure: [
    { value: 'cinematic_swell', label: '📈 Dâng trào (Cinematic Swell)' },
    { value: 'ambient_mystic', label: '🌌 Tĩnh mịch (Mystic Ambient)' },
  ],
  light_paint_ingress: [
    { value: 'cinematic_swell', label: '📈 Dâng trào (Cinematic Swell)' },
    { value: 'ambient_mystic', label: '🌌 Tĩnh mịch (Mystic Ambient)' },
  ],
  memory_resurface: [
    { value: 'ambient_mystic', label: '🌌 Tĩnh mịch (Mystic Ambient)' },
    { value: 'cinematic_swell', label: '📈 Dâng trào (Cinematic Swell)' },
  ],
  forbidden_uncover: [
    { value: 'impact_boom', label: '💥 Nổ/Va đập (Impact Boom)' },
    { value: 'cinematic_swell', label: '📈 Dâng trào (Cinematic Swell)' },
  ],
  ink_bleed: [
    { value: 'ambient_mystic', label: '🌌 Tĩnh mịch (Mystic Ambient)' },
    { value: 'cinematic_swell', label: '📈 Dâng trào (Cinematic Swell)' },
  ],
  scene_assembly: [
    { value: 'cinematic_swell', label: '📈 Dâng trào (Cinematic Swell)' },
    { value: 'ambient_mystic', label: '🌌 Tĩnh mịch (Mystic Ambient)' },
  ],
  // Hook mới:
  smart_quote_animation: [
    { value: 'ambient_mystic', label: '🌌 Ambient kỳ ảo' },
    { value: 'cinematic_swell', label: '📈 Dâng trào cinematic' },
  ],
  none: [],
};

// Hiệu ứng CHỈ dành cho Outro, không hiện trong dropdown Hook mở đầu — vì lý do
// tương ứng với build_cta_card_hook (hook_engine.py): thẻ CTA (Thích/Theo dõi/Chia
// sẻ) chỉ có ý nghĩa ở CUỐI video, đưa lên đầu clip sẽ vô nghĩa (chưa xem gì đã kêu
// gọi theo dõi).
export const OUTRO_ONLY_EFFECTS = [
  { value: 'cta_card', label: '💚 Thẻ kêu gọi hành động (CTA Card)' },
];


// Nguồn hình cho từng cảnh — đồng bộ với backend main.VALID_VISUAL_SOURCES
//
// Nhãn của 'auto' TRƯỚC ĐÂY là "(theo Phong cách ảnh)" — và backend đúng là làm vậy: nó dò
// chữ "realistic"/"photoreal" trong art_style. Nghĩa là chọn phong cách "Realistic (Thực
// tế)" — lựa chọn hoàn toàn tự nhiên cho chủ đề đời thực — sẽ chuyển TOÀN BỘ video sang
// video tải về, dù người dùng chỉ đang chọn kiểu vẽ cho ảnh AI. Bẫy đó đã gỡ ở backend
// (xem main._pick_visual_source), nhãn phải nói đúng sự thật mới.
export const VISUAL_SOURCES = [
  { value: 'mixed', label: '🎭 Xen kẽ thông minh (Gợi ý: Video thật & Ảnh AI)' },
  { value: 'auto', label: '⚙️ Tự động (Theo cài đặt nâng cao / Ưu tiên video)' },
  { value: 'ai_image', label: '🖼️ Chỉ ảnh AI (100% Ảnh sinh bởi AI)' },
  { value: 'stock_video', label: '🎬 Chỉ video thật (100% Pexels Stock)' },
];

export const COLOR_GRADINGS = [
  { value: 'warm_cinematic', label: '🎬 Điện ảnh Ấm (Teal & Orange)' },
  { value: 'cool_matrix', label: '🌌 Tương lai (Cyan / Cool Matrix)' },
  { value: 'vintage_film', label: '🎞️ Phim cũ (Vintage 35mm Retro)' },
  { value: 'vivid_pop', label: '🔥 Rực rỡ (Vivid Pop Viral)' },
  { value: 'noir_dramatic', label: '🖤 Trắng đen (Noir Dramatic)' },
  { value: 'none', label: '⚪ Gốc (Không dùng lọc màu)' },
];
