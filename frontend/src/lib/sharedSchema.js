/**
 * Shared schema giữa AI Video Maker và BookTok App.
 *
 * ĐỐI TÁC: BookTok App giữ bản TypeScript ở src/lib/shared-schema.ts (xem comment ở đó).
 * Hai file phải LUÔN đồng bộ — bất kỳ thay đổi nào ở một phía phải phản ánh ngay phía kia.
 *
 * Schema v3 (2026-08-15):
 * - content_niche: mapped từ BookTok niche_category → AI-VM content_niche
 * - hook_effect: mapped từ BookTok hook_type (Việt) → AI-VM hook_effect (EN)
 * - emotion_core: mapped từ BookTok Literary emotion → AI-VM core emotion
 *
 * Luật validation:
 * - 'text' BẮT BUỘC cho mỗi scene (AI Video Maker dùng 'text' làm TTS narration).
 *   ⚠️  'text' PHẢI giữ nguyên nội dung bình thường — KHÔNG viết HOA toàn bộ.
 *   Nếu gặp scene có 'text' viết HOA toàn bộ (ví dụ "KẾT SẮT BẢN THẢO") → TTS
 *   sẽ đọc từng chữ cái một, rất giòn và rời rạc. Chỉ 'highlight_text' được viết HOA.
 * - 'image_prompt' HOẶC 'search_keyword' phải có (nếu không, scene vừa không có ảnh AI
 *   vừa không tìm được stock video trên Pexels).
 * - 'duration_s' ngoài [1, 60] là bất thường — đánh dấu để user xem lại.
 *   (Mở rộng từ 30→60 để hỗ trợ Podcast / Long-form 10m–15m.)
 *
 * Trước đây processJsonFile() chỉ JSON.parse + setScenes thẳng — không validate gì. Hậu
 * quả thật: BookTok export 30+ scenes (dạng {scenes: [...], imagePrompts: [...]} với
 * image_prompt nằm NGOÀI scene) → AI Video Maker nhận, không thấy image_prompt ở scene
 * → render thành ảnh trống đen, không lỗi nào để truy.
 *
 * ⚠️  QUY TẮC TTS:
 * - 'text' / 'narration' → GIỌNG ĐỌC (TTS) — phải viết bình thường, không HOA
 * - 'highlight_text'          → TEXT HIỂN THỊ trên màn hình — VIẾT HOA được
 * - KHÔNG BAO GIỜ gán highlight_text vào text/narration cho TTS
 */

// ── Mapping Tables — Đồng bộ BookTok ↔ AI Video Maker ────────────────────────────
// ── 1. Niche: BookTok → AI Video Maker content_niche ────────────────────────────
export const NICHE_TO_CONTENT_NICHE = {
    // BookTok NICHE_PROMPTS key → AI-VM content_niche
    'selfhelp':   'psychology',
    'fiction':    'book',
    'philosophy': 'history',
    'spiritual':   'poetry_literature',
    'business':    'finance',
    'thriller':    'truecrime',
    'raw_truth':   'truecrime',
    // BookTok UI label (NICHE_TO_PROMPT_ID) → AI-VM content_niche
    'Kỷ Luật & Phát Triển': 'psychology',
    'Tâm Lý Học & Hành Vi': 'psychology',
    'Quyền Lực & Thao Túng': 'history',
    'Tâm Linh & Chữa Lành': 'poetry_literature',
    'Kinh Doanh & Đầu Tư': 'finance',
    'Triết Học & Khoa Học': 'history',
    'Tiểu Thuyết & Văn Học': 'book',
    'Trinh Thám & Kinh Dị': 'truecrime',
    'Sự Thật Trần Trụi': 'truecrime',
    'Khác': 'psychology',
};

// ── 2. Emotion: BookTok Literary → AI Video Maker Core ──────────────────────────
export const EMOTION_MAPPING = {
    'thyme':          'calm',
    'epic':           'dramatic',
    'lyrical':        'calm',
    'meditative':     'calm',
    'suspense_deep':  'suspense',
    'piercing':       'dramatic',
};

// ── 3. Hook: BookTok hook_type (Việt) → AI Video Maker hook_effect (EN) ────────
export const HOOK_TYPE_MAP = {
    'Gõ chữ':          'word_by_word',
    'Máy đánh chữ':    'typewriter_quote',
    'Đánh chữ':        'typewriter_quote',
    'Màn đen':         'blackout_question',
    'Đen thui':         'blackout_question',
    'Bìa xèng':        'carousel_quote',
    'Bìa xè':          'carousel_quote',
    'Máy xèng':        'carousel_quote',
    'Slot Machine':     'carousel_quote',
    'Xèng':            'carousel_quote',
    'Rung mạnh':       'full_shake',
    'Rung':             'full_shake',
    'Shake':            'full_shake',
    'Nứt':             'full_shake',
    // EN fallback
    carousel_quote:     'carousel_quote',
    typewriter_quote:  'typewriter_quote',
    blackout_question:  'blackout_question',
    word_by_word:      'word_by_word',
    full_shake:         'full_shake',
};

// ── Legacy alias (Giai đoạn 1-2) ─────────────────────────────────────────────
export const NICHE_TO_EMOTION = NICHE_TO_CONTENT_NICHE;  // alias

// ── Core constants ──────────────────────────────────────────────────────────────
export const CORE_EMOTIONS = ['hook', 'calm', 'dramatic', 'excited', 'suspense', 'closing', ''];
export const CORE_TRANSITIONS = [
    'crossfade', 'droplet', 'fade_black', 'fade_white',
    'page_flip', 'slide_left', 'slide_right', 'slide_up',
    'whip_pan', 'wipe_down', 'wipe_right',
    'zoom_punch', 'zoom_through', ''
];

// ── NICHE_PERCENT_BLUEPRINTS (JS port của gemini_service.py) ──────────────────
// Tuples: [start_pct, end_pct, emotion, sfx, transition, speech_rate_modifier, visual_effect]
// Dùng để resolve emotion cho từng scene khi import JSON từ BookTok.
const NICHE_PERCENT_BLUEPRINTS = {
    "book": [
        [0.00, 0.06, "hook",     "",         "fade_black", "+5%", "zoom_in"],
        [0.06, 0.20, "calm",     "",         "crossfade",  "0%",  "none"],
        [0.20, 0.42, "calm",     "",         "page_flip",  "0%",  "none"],
        [0.42, 0.50, "suspense", "suspense", "fade_black", "-3%", "zoom_in"],
        [0.50, 0.75, "dramatic", "",         "crossfade",  "0%",  "none"],
        [0.75, 0.83, "dramatic", "riser",    "zoom_punch", "-3%", "zoom_in"],
        [0.83, 0.92, "calm",     "shimmer",  "droplet",    "-5%", "none"],
        [0.92, 1.01, "closing",  "ding",     "fade_black", "-5%", "none"],
    ],
    "finance": [
        [0.00, 0.15, "hook",     "riser",    "whip_pan",   "+15%", "zoom_in"],
        [0.15, 0.30, "dramatic", "",         "slide_left", "+5%",  "none"],
        [0.30, 0.50, "calm",     "tick",     "slide_right","0%",  "none"],
        [0.50, 0.70, "excited",  "bass_drop","zoom_punch", "-3%",  "zoom_in"],
        [0.70, 0.90, "dramatic", "impact",   "fade_white", "0%",  "none"],
        [0.90, 1.01, "closing",  "ding",     "fade_black", "+5%",  "none"],
    ],
    "history": [
        [0.00, 0.10, "hook",     "suspense", "fade_black", "+5%",  "zoom_in"],
        [0.10, 0.25, "calm",     "",         "crossfade",  "0%",   "none"],
        [0.25, 0.65, "suspense", "heartbeat","crossfade",  "-3%",  "none"],
        [0.65, 0.75, "dramatic", "suspense", "wipe_down",  "-3%",  "none"],
        [0.75, 0.85, "dramatic", "impact",   "zoom_punch", "-3%",  "zoom_in"],
        [0.85, 1.01, "closing",  "",         "droplet",    "-5%",  "none"],
    ],
    "psychology": [
        [0.00, 0.15, "hook",     "",         "crossfade",  "0%",   "zoom_in"],
        [0.15, 0.30, "calm",     "",         "crossfade",  "-5%",  "none"],
        [0.30, 0.70, "calm",     "",         "crossfade",  "-5%",  "none"],
        [0.70, 0.85, "dramatic", "shimmer",  "droplet",    "-8%",  "zoom_in"],
        [0.85, 1.01, "closing",  "",         "fade_black", "-8%",  "none"],
    ],
    "truecrime": [
        [0.00, 0.15, "hook",     "heartbeat","fade_black", "+5%",  "zoom_in"],
        [0.15, 0.35, "suspense", "",         "crossfade",  "0%",   "none"],
        [0.35, 0.65, "suspense", "suspense", "fade_black", "0%",   "none"],
        [0.65, 0.80, "dramatic", "bass_drop","whip_pan",   "+5%",  "zoom_in"],
        [0.80, 0.90, "dramatic", "impact",   "zoom_punch", "-3%",  "zoom_in"],
        [0.90, 1.01, "closing",  "",         "droplet",    "-5%",  "none"],
    ],
    "travel": [
        [0.00, 0.20, "hook",     "swoosh_soft","slide_up", "+10%", "zoom_in"],
        [0.20, 0.40, "excited",  "",          "wipe_right","0%",   "none"],
        [0.40, 0.60, "excited",  "pop",       "zoom_through","0%",  "zoom_in"],
        [0.60, 0.80, "calm",     "shimmer",   "crossfade",  "-3%",  "none"],
        [0.80, 1.01, "closing",  "ding",      "fade_black", "+5%",  "none"],
    ],
    "art_masterpiece": [
        [0.00, 0.15, "hook",     "",         "fade_black", "+5%",  "zoom_in"],
        [0.15, 0.35, "calm",     "",         "crossfade",  "0%",   "none"],
        [0.35, 0.55, "calm",     "",         "page_flip",  "0%",   "none"],
        [0.55, 0.70, "dramatic", "shimmer",  "zoom_punch", "-3%",  "zoom_in"],
        [0.70, 0.85, "dramatic", "impact",   "droplet",    "-5%",  "none"],
        [0.85, 1.01, "closing",  "",         "fade_black", "-5%",  "none"],
    ],
    "poetry_literature": [
        [0.00, 0.15, "hook",     "",         "crossfade",  "0%",   "zoom_in"],
        [0.15, 0.40, "calm",     "",         "droplet",    "-5%",  "none"],
        [0.40, 0.60, "calm",     "",         "fade_black", "-5%",  "none"],
        [0.60, 0.75, "dramatic", "shimmer",  "droplet",    "-8%",  "zoom_in"],
        [0.75, 0.90, "calm",     "",         "crossfade",  "-5%",  "none"],
        [0.90, 1.01, "closing",  "",         "fade_black", "-5%",  "none"],
    ],
    "architecture_wonders": [
        [0.00, 0.15, "hook",     "swoosh_soft","fade_black","+10%","zoom_in"],
        [0.15, 0.35, "dramatic", "",          "slide_up",  "+5%",  "none"],
        [0.35, 0.55, "dramatic", "heartbeat", "wipe_down", "0%",   "none"],
        [0.55, 0.75, "calm",     "",          "crossfade", "-3%",  "none"],
        [0.75, 0.90, "dramatic", "impact",   "zoom_punch", "-5%", "zoom_in"],
        [0.90, 1.01, "closing",  "",          "fade_black", "-5%", "none"],
    ],
};

// TONE_PERCENT_PALETTES fallback khi không có niche
const TONE_PERCENT_PALETTES = {
    "viral": [
        [0.00, 0.10, "hook",     "",         "crossfade",  "0%",   "zoom_in"],
        [0.10, 0.35, "dramatic", "riser",    "whip_pan",   "+5%",  "none"],
        [0.35, 0.60, "calm",     "",         "crossfade",  "0%",   "none"],
        [0.60, 0.80, "dramatic", "bass_drop","zoom_punch", "-3%",  "zoom_in"],
        [0.80, 0.90, "calm",     "shimmer",  "droplet",    "-5%",  "none"],
        [0.90, 1.01, "closing",  "ding",     "fade_black", "-5%",  "none"],
    ],
    "calm": [
        [0.00, 0.15, "hook",     "",         "crossfade",  "0%",   "zoom_in"],
        [0.15, 0.40, "calm",     "",         "crossfade",  "-5%",  "none"],
        [0.40, 0.65, "calm",     "",         "droplet",    "-5%",  "none"],
        [0.65, 0.80, "dramatic", "shimmer",  "droplet",    "-8%",  "zoom_in"],
        [0.80, 1.01, "closing",  "",         "fade_black", "-5%",  "none"],
    ],
    "suspenseful": [
        [0.00, 0.10, "hook",     "suspense", "fade_black", "+5%",  "zoom_in"],
        [0.10, 0.30, "suspense", "",         "crossfade",  "0%",   "none"],
        [0.30, 0.60, "suspense", "heartbeat","fade_black", "-3%",  "none"],
        [0.60, 0.80, "dramatic", "bass_drop","whip_pan",   "+5%",  "zoom_in"],
        [0.80, 1.01, "closing",  "",         "droplet",    "-5%",  "none"],
    ],
};

/**
 * JS port của gemini_service.resolve_blueprint().
 * Resolve blueprint cho mỗi scene dựa trên content_niche (thể loại) và vị trí.
 *
 * @param {string} niche - content_niche (book, finance, psychology, v.v.)
 * @param {string} tone - narration_tone (viral, calm, suspenseful)
 * @param {number} totalScenes - tổng số scene
 * @returns {Array<{emotion: string, sfx: string, transition: string, speech_rate_modifier: string, visual_effect: string}>}
 */
export function resolveBlueprint(niche, tone, totalScenes) {
    const bp = NICHE_PERCENT_BLUEPRINTS[niche] || TONE_PERCENT_PALETTES[tone] || TONE_PERCENT_PALETTES["viral"];
    const out = [];
    const total = Math.max(totalScenes - 1, 1);
    for (let i = 0; i < totalScenes; i++) {
        const p = i / total;
        // Find matching band
        let band = bp[bp.length - 1]; // fallback to last band
        for (const b of bp) {
            if (p >= b[0] && p < b[1]) {
                band = b;
                break;
            }
        }
        out.push({
            emotion:              band[2],
            sfx:                  band[3],
            transition:           band[4],
            speech_rate_modifier: band[5],
            visual_effect:        band[6],
        });
    }
    return out;
}

// AI Video Maker dùng 'text' làm narration (TTS đọc scene.text), KHÔNG phải 'narration'.
export const REQUIRED_SCENE_FIELDS = ['text'];
export const OPTIONAL_SCENE_FIELDS = [
    'image_prompt',
    'search_keyword',
    'duration_s',
    'highlight_text',
    'transition',
    'emotion',
    'emotion_core',    // ← MỚI: Literary emotion mapped sang core
    'scene_type',
    'voice_effect',
    'pause_s',
    'pause_after_ms',
    'visual_note',
    'speech_rate_modifier',
    'pacing_recommendation',
    'subtitle_text',
    'chapter_index',
    'chapter_title',
];

// Literary Metadata
export const LITERARY_FIELDS = [
    'for_readers_who_like',
    'reading_conditions',
    'similar_books',
    'what_stays',
    'emotional_tone',
    'pacing_recommendation',
    'moment_to_build',
    'visual_mood',
    'sound_recommendation',
    'pacing_notes',
];

export function normalizeScene(scene, idx = 0) {
    const block = scene.block || (scene.emotion === 'hook' ? 'HOOK' : 'SCENE');
    const narration = scene.narration || scene.text || scene.vo || '';

    // ── Map emotion: Literary → Core ──────────────────────────────────────────────
    const emotion = scene.emotion || '';
    let emotion_core = scene.emotion_core || '';
    if (!emotion_core && emotion && EMOTION_MAPPING[emotion]) {
        emotion_core = EMOTION_MAPPING[emotion];
    }

    return {
        scene: scene.scene ?? idx + 1,
        block,
        narration,
        text: scene.text ?? narration,
        highlight_text: scene.highlight_text || scene.highlight || '',
        image_prompt: scene.image_prompt || '',
        search_keyword: scene.search_keyword || '',
        duration_s: scene.duration_s ?? 3.5,
        transition: scene.transition ?? 'crossfade',
        emotion,
        emotion_core,  // ← MỚI: mapped Literary → Core
        sfx: scene.sfx ?? '',
        speech_rate_modifier: scene.speech_rate_modifier ?? '',
        scene_type: scene.scene_type || '',
        voice_effect: scene.voice_effect || '',
        pause_after_ms: scene.pause_after_ms ?? null,
        pause_s: scene.pause_s || (scene.pause_after_ms ? scene.pause_after_ms / 1000 : ''),
        visual_note: scene.visual_note || '',
        pacing_recommendation: scene.pacing_recommendation || '',
        subtitle_text: scene.subtitle_text ?? '',
        chapter_index: scene.chapter_index ?? null,
        chapter_title: scene.chapter_title ?? '',
        niche_category: scene.niche_category || '',
    };
}

export function validateScene(scene, idx) {
    const warnings = [];
    for (const field of REQUIRED_SCENE_FIELDS) {
        if (!scene[field]) {
            warnings.push(`Scene ${idx + 1}: thiếu trường bắt buộc "${field}"`);
        }
    }
    if (!scene.image_prompt && !scene.search_keyword) {
        warnings.push(`Scene ${idx + 1}: cần "image_prompt" hoặc "search_keyword"`);
    }
    if (scene.duration_s && (scene.duration_s < 1 || scene.duration_s > 60)) {
        warnings.push(`Scene ${idx + 1}: duration_s=${scene.duration_s} ngoài khoảng [1, 60]`);
    }
    return warnings;
}

export function validateImportPayload(payload) {
    const warnings = [];
    if (!payload || typeof payload !== 'object') {
        return ['Payload không phải JSON object hợp lệ.'];
    }
    if (!payload.scenes || !Array.isArray(payload.scenes)) {
        warnings.push('Payload thiếu mảng "scenes" ở cấp ngoài cùng.');
        return warnings;
    }
    if (payload.scenes.length === 0) {
        warnings.push('Mảng scenes rỗng.');
    }
    if (payload.source === 'booktok-app') {
        const v = payload.source_version || 1;
        if (v >= 3) {
            warnings.push(`ℹ️ Schema v${v} — có content_niche + hook_effect + emotion_core để AI Video Maker resolve đúng.`);
        } else {
            warnings.push(`ℹ️ Phát hiện JSON từ BookTok App (schema v${v}) — đã áp dụng schema chuẩn.`);
        }
    }
    payload.scenes.forEach((scene, idx) => {
        warnings.push(...validateScene(scene, idx));
    });
    return warnings;
}

export function normalizeImportPayload(payload) {
    const sourceScenes = Array.isArray(payload) ? payload : (payload.scenes || []);

    // ── 1. Map niche_category → content_niche ────────────────────────────────────
    const niche_category = payload.niche_category || '';
    let content_niche = payload.content_niche || '';
    if (!content_niche && niche_category && NICHE_TO_CONTENT_NICHE[niche_category]) {
        content_niche = NICHE_TO_CONTENT_NICHE[niche_category];
    }

    // ── 2. Map hook_type → hook_effect ─────────────────────────────────────────
    const rawHookType = payload.hook_effect || payload.hook_type || '';
    let hook_effect = payload.hook_effect || '';
    if (!hook_effect && rawHookType) {
        // Dùng map từng từ hoặc fallback về raw
        hook_effect = HOOK_TYPE_MAP[rawHookType] || rawHookType;
    }

    // ── 3. Resolve blueprint cho từng scene (như backend resolve_blueprint) ─────────
    // Khi import từ BookTok: scenes đã có emotion Literary (thyme, epic…) nhưng
    // render engine cần emotion CORE (dramatic, calm…). Gọi resolveBlueprint()
    // để ghi đè emotion/transition/sfx theo content_niche + vị trí.
    const resolvedBlueprint = resolveBlueprint(content_niche || '', payload.narration_tone || 'viral', sourceScenes.length);

    // ── 4. Enrich scenes với content_niche và resolved blueprint ───────────────────
    const enrichedScenes = sourceScenes.map((s, idx) => ({
        ...s,
        niche_category,
        content_niche,
        // Override bằng resolved blueprint (nếu scene chưa có giá trị riêng)
        _resolved: resolvedBlueprint[idx] || {},
    }));
    const scenes = enrichedScenes.map((s, idx) => {
        const norm = normalizeScene(s, idx);
        const bp = s._resolved || {};
        // Nếu emotion là Literary (không nằm trong CORE) → ghi đè bằng resolved
        const isLiterary = norm.emotion && !CORE_EMOTIONS.includes(norm.emotion);
        if (isLiterary) {
            norm.emotion = bp.emotion || norm.emotion_core || norm.emotion;
        }
        // Ghi đè transition/sfx nếu scene không có giá trị cụ thể
        if (!norm.transition || norm.transition === 'crossfade') {
            norm.transition = bp.transition || norm.transition;
        }
        if (!norm.sfx) {
            norm.sfx = bp.sfx || '';
        }
        if (!norm.speech_rate_modifier) {
            norm.speech_rate_modifier = bp.speech_rate_modifier || '0%';
        }
        // Đánh dấu là đã resolved để UI hiển thị đúng
        norm._blueprint_resolved = true;
        return norm;
    });

    const totalDuration = scenes.reduce((sum, s) => sum + (Number(s.duration_s) || 3.5), 0);

    // Literary metadata passthrough
    const literary = payload.literary || {};

    // ── 5. Resolve emotion cho UI display ──────────────────────────────────────
    let emotion = payload.emotion || literary.emotional_tone || '';
    if (!emotion && niche_category && NICHE_TO_CONTENT_NICHE[niche_category]) {
        emotion = NICHE_TO_CONTENT_NICHE[niche_category];
    }

    return {
        scenes,
        estimated_duration_s: payload.estimated_duration_s ?? Math.round(totalDuration * 10) / 10,
        hook_text: payload.hook_text,
        hook_quote: payload.hook_quote,
        hook_effect,  // ← MỚI: hook_effect mapped sang EN
        cta_text: payload.cta_text,
        outro_text: payload.outro_text,
        recommended_bgm: payload.recommended_bgm,
        title_recommendations: payload.title_recommendations,
        recommended_hashtags: payload.recommended_hashtags,
        caption_suggestion: payload.caption_suggestion,
        pinned_comment: payload.pinned_comment,
        sentiment: payload.sentiment || emotion,
        niche_category,
        content_niche,  // ← MỚI: dùng cho resolve_blueprint() ở backend
        chapters_summary: payload.chapters_summary || [],
        literary,
        for_readers_who_like: literary.for_readers_who_like || [],
        reading_conditions: literary.reading_conditions || [],
        similar_books: literary.similar_books || [],
        what_stays: literary.what_stays || '',
        emotional_tone: literary.emotional_tone || '',
        pacing_recommendation: literary.pacing_recommendation || '',
        visual_mood: literary.visual_mood || '',
        sound_recommendation: literary.sound_recommendation || '',
    };
}
