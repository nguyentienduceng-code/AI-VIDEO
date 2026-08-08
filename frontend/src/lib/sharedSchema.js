/**
 * Shared schema giữa AI Video Maker và BookTok App.
 *
 * ĐỐI TÁC: BookTok App giữ bản TypeScript ở src/lib/shared-schema.ts (xem comment ở đó).
 * Hai file phải LUÔN đồng bộ — bất kỳ thay đổi nào ở một phía phải phản ánh ngay phía kia.
 *
 * Luật validation:
 * - 'narration' BẮT BUỘC cho mỗi scene (không có thì TTS không chạy được).
 * - 'image_prompt' HOẶC 'search_keyword' phải có (nếu không, scene vừa không có ảnh AI
 *   vừa không tìm được stock video trên Pexels).
 * - 'duration_s' ngoài [1, 60] là bất thường — đánh dấu để user xem lại.
 *   (Mở rộng từ 30→60 để hỗ trợ Podcast / Long-form 10m–15m.)
 *
 * Trước đây processJsonFile() chỉ JSON.parse + setScenes thẳng — không validate gì. Hậu
 * quả thật: BookTok export 30+ scenes (dạng {scenes: [...], imagePrompts: [...]} với
 * image_prompt nằm NGOÀI scene) → AI Video Maker nhận, không thấy image_prompt ở scene
 * → render thành ảnh trống đen, không lỗi nào để truy.
 */

export const REQUIRED_SCENE_FIELDS = ['narration'];
export const OPTIONAL_SCENE_FIELDS = [
  'image_prompt',
  'search_keyword',
  'duration_s',
  'highlight_text',
  'transition',
  'emotion',
];

export function normalizeScene(scene, idx = 0) {
  const block = scene.block || (scene.emotion === 'hook' ? 'HOOK' : 'SCENE');
  // Fallback chain: narration (AI Video Maker) > text (BookTok/AI) > vo (legacy).
  // Nếu chỉ check narration, vứt luôn nội dung scene AI sinh ra chỉ có 'text'.
  const narration = scene.narration || scene.text || scene.vo || '';
  // Lưu ý: AI Video Maker UI cũ đọc scene.text ở nhiều nơi (input Lời thoại,
  // TTS preview, v.v.). Trước đây hàm chỉ trả narration — JSON nhập có 'text'
  // (từ BookTok) bị mất trắng khi render. Thêm 'text' = narration để cả hai
  // convention đều hoạt động. Tương thích ngược khi đã có sẵn 'text'.
  return {
    scene: scene.scene ?? idx + 1,
    block,
    narration,
    text: scene.text ?? narration, // ← KEY FIX: mirror để UI input không trống
    highlight_text: scene.highlight_text || scene.highlight || '',
    image_prompt: scene.image_prompt || '',
    search_keyword: scene.search_keyword || '',
    duration_s: scene.duration_s ?? 3.5,
    transition: scene.transition ?? 'crossfade',
    emotion: scene.emotion ?? '',
    sfx: scene.sfx ?? '',
    speech_rate_modifier: scene.speech_rate_modifier ?? '',
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
    warnings.push(`Scene ${idx + 1}: duration_s=${scene.duration_s} ngoài [1, 60]`);
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
  // Cảnh báo nguồn: BookTok và Gemini-AI có format JSON hơi khác nhau.
  if (payload.source === 'booktok-app') {
    warnings.push('ℹ️ Phát hiện JSON từ BookTok App — đã áp dụng schema chuẩn.');
  }
  payload.scenes.forEach((scene, idx) => {
    warnings.push(...validateScene(scene, idx));
  });
  return warnings;
}

export function normalizeImportPayload(payload) {
  const sourceScenes = Array.isArray(payload) ? payload : (payload.scenes || []);
  const scenes = sourceScenes.map((s, idx) => normalizeScene(s, idx));
  const totalDuration = scenes.reduce((sum, s) => sum + (Number(s.duration_s) || 3.5), 0);
  return {
    scenes,
    estimated_duration_s: payload.estimated_duration_s ?? Math.round(totalDuration * 10) / 10,
    hook_text: payload.hook_text,
    hook_quote: payload.hook_quote,
    cta_text: payload.cta_text,
    outro_text: payload.outro_text,
    recommended_bgm: payload.recommended_bgm,
    title_recommendations: payload.title_recommendations,
    recommended_hashtags: payload.recommended_hashtags,
    caption_suggestion: payload.caption_suggestion,
    pinned_comment: payload.pinned_comment,
    sentiment: payload.sentiment,
    niche_category: payload.niche_category,
  };
}
