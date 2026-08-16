import React from 'react';
import {
  ChevronUp, ChevronDown, ChevronRight,
  Trash2, Film, Volume2, Music, Upload, X,
  Headphones, Pause, Square, Settings, AlertTriangle,
} from 'lucide-react';
import { useShallow } from 'zustand/react/shallow';
import { useAppStore } from '../store';
import { API_BASE, TRANSITIONS, SFX_OPTIONS } from '../constants';

// Nhịp xem: một ảnh đứng yên quá 6.5 giây là ì, dưới 2.5 giây là chớp qua chưa kịp nhìn.
const SHOT_MIN_S = 2.5;
const SHOT_MAX_S = 6.5;

// Thời lượng dự kiến của một cảnh (cùng công thức với duration_model.estimate_duration).
const countWords = (text) => {
  const BREAK_TAG_RE = /<break[^>]*>/gi;
  const cleaned = (text || '').replace(BREAK_TAG_RE, ' ').trim();
  return cleaned ? cleaned.split(/\s+/).length : 0;
};
const breakSeconds = (text) => {
  const BREAK_TIME_RE = /<break[^>]*time\s*=\s*"([\d.]+)\s*(ms|s)"[^>]*>/gi;
  let total = 0;
  for (const [, value, unit] of (text || '').matchAll(BREAK_TIME_RE)) {
    const v = parseFloat(value);
    if (!Number.isNaN(v)) total += unit.toLowerCase() === 'ms' ? v / 1000 : v;
  }
  return total;
};
const estimateSceneSeconds = (scene, wps) => {
  const words = countWords(scene?.text);
  const speech = words > 0 ? words / (wps || 3.0) : 0;
  return speech + breakSeconds(scene?.text) + (scene?.pause_after_ms || 0) / 1000;
};

// Tốc độ đọc dự phòng
const FALLBACK_WPS = 3.0;

// Nhãn thời lượng cạnh mỗi cảnh
function SceneTiming({ seconds }) {
  if (!seconds) return null;
  const tooLong = seconds > SHOT_MAX_S;
  const tooShort = seconds < SHOT_MIN_S;
  const color = tooLong ? 'var(--red, #ef4444)' : tooShort ? 'var(--amber, #f59e0b)' : 'var(--text-dim, #94a3b8)';
  const title = tooLong
    ? `Cảnh dài ~${seconds.toFixed(1)}s. Một ảnh đứng yên quá ${SHOT_MAX_S}s khiến nhịp video ì.`
    : tooShort
      ? `Cảnh chỉ ~${seconds.toFixed(1)}s. Ảnh chớp qua nhanh hơn ${SHOT_MIN_S}s thì người xem chưa kịp nhìn.`
      : `Ước lượng ~${seconds.toFixed(1)}s — nhịp tốt.`;
  return (
    <span style={{ color, fontSize: 11, fontWeight: 600 }} title={title}>
      ~{seconds.toFixed(1)}s
    </span>
  );
}

// Nhãn nguồn hình
const SOURCE_LABEL = {
  ai_image: 'ảnh AI',
  stock_video: 'video thật Pexels',
  veo: 'video AI Veo',
  override: 'hình bạn tự tải lên',
};

function CacheDot({ state, kindLabel, source, probing }) {
  if (probing || state === undefined) {
    return <span style={{ opacity: 0.4 }} title="Đang kiểm tra bộ nhớ đệm...">⚪ {kindLabel}</span>;
  }
  const via = source ? ` (${SOURCE_LABEL[source] || source})` : '';
  return state
    ? <span style={{ color: 'var(--green)' }} title={`${kindLabel}${via}: đã có sẵn trong bộ nhớ đệm.`}>🟢 {kindLabel}</span>
    : <span style={{ color: 'var(--red)' }} title={`${kindLabel}${via}: chưa có — cảnh này sẽ phải tạo mới.`}>🔴 {kindLabel}</span>;
}

const BREAK_SNIPPET = '<break time="1s"/>';

/**
 * SceneCard — renders a single scene accordion.
 *
 * Props:
 *   scene, idx
 *   collapsed, expandedAdvanced, previewIdx, uploadingIdx, customSfxList, cacheStatus, probing
 *   sceneSeconds (array, for SceneTiming label)
 *   textareaRefs (ref from parent, to support insertBreak cursor positioning)
 *   onToggleCollapse, onToggleAdvanced
 *   onUpdate(idx, field, value)
 *   onRemove(idx)
 *   onMoveUp(idx), onMoveDown(idx)
 *   onPreview(idx), onStopPreview()
 *   onInsertBreak(idx, textareaRef)
 *   onUploadOverride(idx, file), onClearOverride(idx)
 *   totalScenes (for disabled checks)
 *   globalSfxVolume, globalBgmVolume, globalUseSinglePassNarration, globalUseSfx
 */
export default function SceneCard({
  scene, idx,
  collapsed, expandedAdvanced,
  previewIdx, uploadingIdx, customSfxList,
  cacheStatus, probing,
  sceneSeconds,
  textareaRefs,
  onToggleCollapse,
  onToggleAdvanced,
  onUpdate,
  onRemove,
  onMoveUp, onMoveDown,
  onPreview, onStopPreview,
  onInsertBreak,
  onUploadOverride, onClearOverride,
  onUploadSfx,
  totalScenes,
  globalSfxVolume, globalBgmVolume,
  globalUseSinglePassNarration,
  globalUseSfx,
}) {
  const status = cacheStatus?.[idx];
  const hasOverride = Boolean(scene.override_asset);
  const bgmOverridden = scene.bgm_volume !== undefined && scene.bgm_volume !== null;
  const sceneSec = sceneSeconds?.[idx];

  return (
    <div key={idx} className="scene-card">
      {/* ── Header ── */}
      <div className="scene-header">
        <div
          className="scene-number"
          style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}
          onClick={() => onToggleCollapse(idx)}
        >
          {collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />} Cảnh {idx + 1}
        </div>
        <div style={{ display: 'flex', gap: 12, fontSize: 11, alignItems: 'center', marginLeft: 12, flex: 1 }}>
          <CacheDot state={status?.audio_cached} kindLabel="Giọng" probing={probing} />
          <CacheDot state={status?.image_cached} kindLabel="Hình" source={status?.image_source} probing={probing} />
          <SceneTiming seconds={sceneSec} />
          {collapsed && (
            <span style={{ marginLeft: 12, opacity: 0.6, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '300px' }}>
              {scene.text}
            </span>
          )}
        </div>
        <div className="scene-actions">
          <button className="btn-icon" onClick={() => onMoveUp(idx)} disabled={idx === 0} title="Di chuyển lên"><ChevronUp size={14} /></button>
          <button className="btn-icon" onClick={() => onMoveDown(idx)} disabled={idx === totalScenes - 1} title="Di chuyển xuống"><ChevronDown size={14} /></button>
          <button className="btn-icon btn-danger" onClick={() => onRemove(idx)} title="Xóa cảnh" disabled={totalScenes <= 1}><Trash2 size={14} /></button>
        </div>
      </div>

      {!collapsed && (
      <div className="scene-fields">
        {/* ── Script field ── */}
        <div className="scene-field">
          <label className="field-label" style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span>LỜI THOẠI (TIẾNG VIỆT)</span>
            <button
              type="button"
              className="btn-icon"
              onClick={() => onPreview(idx)}
              disabled={!scene.text?.trim()}
              title="Nghe thử giọng đọc của riêng cảnh này (có cả nhịp nghỉ)."
              style={{ padding: '2px 8px', fontSize: 11, fontWeight: 600, color: previewIdx === idx ? 'var(--amber)' : undefined }}
            >
              {previewIdx === idx
                ? <><Square size={11} style={{ verticalAlign: 'text-bottom' }} /> Dừng</>
                : <><Headphones size={11} style={{ verticalAlign: 'text-bottom' }} /> Nghe thử</>}
            </button>
            <button
              type="button"
              className="btn-icon"
              onClick={() => {
                const el = textareaRefs?.current?.[idx];
                onInsertBreak(idx, el);
              }}
              title={`Chèn ${BREAK_SNIPPET} tại vị trí con trỏ — ép giọng đọc dừng hẳn 1 giây.`}
              style={{ padding: '2px 8px', fontSize: 11, fontWeight: 600 }}
            >
              <Pause size={11} style={{ verticalAlign: 'text-bottom' }} /> Chèn nhịp nghỉ
            </button>
            {scene.text?.includes('<break') && (
              <span style={{ fontSize: 11, color: 'var(--amber)', fontWeight: 400 }}>
                ⏸ Có ngắt nghỉ cảm xúc
                {globalUseSinglePassNarration && ' — bị bỏ qua khi bật "Đọc liền mạch cả bài"'}
              </span>
            )}
          </label>
          <textarea
            ref={el => {
              if (textareaRefs?.current) textareaRefs.current[idx] = el;
            }}
            className="form-textarea scene-textarea"
            value={scene.text}
            onChange={e => onUpdate(idx, 'text', e.target.value)}
            placeholder="Lời thoại sẽ được đọc bằng TTS..."
            rows={3}
          />
        </div>

        {/* ── Image prompt field ── */}
        <div className="scene-field">
          <label className="field-label" style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span>MÔ TẢ HÌNH ẢNH (TIẾNG ANH)</span>
            <label
              className="btn-icon"
              style={{ padding: '2px 8px', fontSize: 11, fontWeight: 600, cursor: 'pointer' }}
              title="Dùng ảnh/video của bạn thay cho hình AI sinh cho riêng cảnh này."
            >
              <Upload size={11} style={{ verticalAlign: 'text-bottom' }} />
              {uploadingIdx === idx ? ' Đang tải...' : ' Tải ảnh/video của tôi'}
              <input
                type="file"
                accept=".png,.jpg,.jpeg,.webp,.bmp,.mp4,.mov,.webm"
                style={{ display: 'none' }}
                disabled={uploadingIdx === idx}
                onChange={e => { onUploadOverride(idx, e.target.files?.[0]); e.target.value = ''; }}
              />
            </label>
          </label>

          {hasOverride ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', border: '1px solid var(--green)', borderRadius: 8, marginBottom: 8 }}>
              {scene.override_kind === 'video' ? (
                <video src={`${API_BASE}/api/scene-asset/${scene.override_asset}`} style={{ width: 54, height: 54, objectFit: 'cover', borderRadius: 6 }} muted />
              ) : (
                <img src={`${API_BASE}/api/scene-asset/${scene.override_asset}`} alt="" style={{ width: 54, height: 54, objectFit: 'cover', borderRadius: 6 }} />
              )}
              <span style={{ flex: 1, fontSize: 12, color: 'var(--green)' }}>
                Đang dùng {scene.override_kind === 'video' ? 'video' : 'ảnh'} của bạn — mô tả bên dưới sẽ bị bỏ qua ở cảnh này.
              </span>
              <button className="btn-icon btn-danger" onClick={() => onClearOverride(idx)} title="Gỡ, trả cảnh về cho AI sinh hình"><X size={14} /></button>
            </div>
          ) : null}

          <textarea
            className="form-textarea scene-textarea"
            value={scene.image_prompt}
            onChange={e => onUpdate(idx, 'image_prompt', e.target.value)}
            placeholder="Image prompt for AI image generation..."
            rows={2}
            disabled={hasOverride}
            style={hasOverride ? { opacity: 0.5 } : undefined}
          />
        </div>

        {/* ── Source quote warning ── */}
        {hasOverride ? null : (() => {
          const hasClaim = /\d{2,}|\b[A-ZĐ][a-zà-ỹ]+\s[A-ZĐ]/.test(scene.text || "");
          const warning = (hasClaim && !scene.source_quote)
            ? "Cảnh có chứa số liệu hoặc tên riêng nhưng chưa có nguồn gốc (source_quote). Vui lòng kiểm tra lại."
            : null;
          return warning ? (
            <div style={{ background: 'var(--surface-hover)', borderLeft: '3px solid var(--amber)', padding: '8px 12px', fontSize: 12, color: 'var(--amber)', marginTop: 8, borderRadius: '0 4px 4px 0' }}>
              <AlertTriangle size={14} style={{ verticalAlign: 'middle', marginRight: 6 }} />
              {warning}
            </div>
          ) : null;
        })()}

        {/* ── Advanced toggle button ── */}
        <div style={{ marginTop: 12 }}>
          <button
            className="btn-outline"
            style={{ width: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 6, fontSize: 12, padding: '8px 0', background: 'rgba(255,255,255,0.02)', border: '1px dashed rgba(255,255,255,0.1)' }}
            onClick={() => onToggleAdvanced(idx)}
          >
            <Settings size={14} /> {expandedAdvanced ? 'Ẩn Cài đặt nâng cao' : 'Cài đặt Nâng cao (Nguồn hình, Chuyển cảnh, SFX...)'}
          </button>
        </div>

        {/* ── Advanced settings panel ── */}
        {expandedAdvanced && (
          <div className="advanced-scene-settings" style={{ animation: 'fadeIn 0.2s', marginTop: 12 }}>
            <div className="scene-field" style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: 160 }}>
                <label className="field-label"><Film size={12} style={{ verticalAlign: 'middle' }} /> NGUỒN HÌNH (RIÊNG CẢNH NÀY)</label>
                <select
                  className="form-select form-select-sm"
                  value={scene.visual_source || 'auto'}
                  onChange={e => onUpdate(idx, 'visual_source', e.target.value)}
                  disabled={hasOverride}
                >
                  <option value="auto">Tự động (Theo gợi ý Xen kẽ / Cài đặt chung)</option>
                  <option value="ai_image">🖼️ Ảnh AI (AI Image)</option>
                  <option value="stock_video">🎬 Video thật (Pexels Stock)</option>
                </select>
              </div>
            </div>

            <div className="scene-field" style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 12, padding: '10px 12px', background: 'var(--surface)', borderRadius: 6, border: '1px solid var(--border)' }}>
              <div style={{ flex: 1, minWidth: 140 }}>
                <label className="field-label">LOẠI CẢNH (TYPE)</label>
                <select
                  className="form-select form-select-sm"
                  value={scene.scene_type || 'narration'}
                  onChange={e => onUpdate(idx, 'scene_type', e.target.value)}
                >
                  <option value="narration">Kể chuyện (Voice)</option>
                  <option value="quote_card">Quote Card (Không Voice)</option>
                </select>
              </div>
              <div style={{ flex: 1, minWidth: 120 }}>
                <label className="field-label">NHỊP NGHỈ (ms)</label>
                <input
                  type="number"
                  className="form-input form-input-sm"
                  value={scene.pause_after_ms || 0}
                  onChange={e => onUpdate(idx, 'pause_after_ms', parseInt(e.target.value) || 0)}
                  min={0} max={3000} step={100}
                />
              </div>
              <div style={{ flex: 2, minWidth: 200 }}>
                <label className="field-label">NGUỒN TRÍCH DẪN (Chống bịa)</label>
                <input
                  type="text"
                  className="form-input form-input-sm"
                  value={scene.source_quote || ''}
                  onChange={e => onUpdate(idx, 'source_quote', e.target.value)}
                  placeholder="Nguyên văn tài liệu gốc..."
                />
              </div>
            </div>

            <div className="scene-field" style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 12 }}>
              {/* Transition */}
              <div style={{ flex: 1, minWidth: 160 }}>
                <label className="field-label"><Film size={12} style={{ verticalAlign: 'middle' }} /> CHUYỂN CẢNH (sang cảnh sau)</label>
                <select
                  className="form-select form-select-sm"
                  value={scene.transition || 'crossfade'}
                  onChange={e => onUpdate(idx, 'transition', e.target.value)}
                >
                  {TRANSITIONS.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
              </div>

              {/* SFX */}
              <div style={{ flex: 1, minWidth: 200 }}>
                <label className="field-label"><Volume2 size={12} style={{ verticalAlign: 'middle' }} /> TIẾNG ĐỘNG (SFX) CẢNH NÀY</label>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center', width: '100%' }}>
                  <select
                    className="form-select form-select-sm"
                    value={scene.sfx || ''}
                    onChange={e => {
                      const val = e.target.value;
                      onUpdate(idx, 'sfx', val);
                      if (val) {
                        const audio = new Audio(`${API_BASE}/api/preview/sfx/${val}`);
                        const vol = scene.sfxVolume !== undefined ? scene.sfxVolume : 100;
                        audio.volume = (globalSfxVolume / 100) * (vol / 100);
                        audio.play().catch(() => {});
                      }
                    }}
                    style={{ flex: 1, minWidth: 0 }}
                  >
                    <optgroup label="SFX Mặc định">
                      {SFX_OPTIONS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                    </optgroup>
                    {customSfxList.length > 0 && (
                      <optgroup label="SFX Tự Tải Lên">
                        {customSfxList.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                      </optgroup>
                    )}
                  </select>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4, width: 80, flexShrink: 0 }}>
                    <span style={{ fontSize: 10, color: 'gray' }}>Vol</span>
                    <input
                      type="range"
                      className="vol-slider"
                      min="0"
                      max="200"
                      value={scene.sfxVolume !== undefined ? scene.sfxVolume : 100}
                      onChange={e => {
                        const vol = Number(e.target.value);
                        onUpdate(idx, 'sfxVolume', vol);
                        if (scene.sfx) {
                          const audio = new Audio(`${API_BASE}/api/preview/sfx/${scene.sfx}`);
                          audio.volume = (globalSfxVolume / 100) * (vol / 100);
                          audio.play().catch(() => {});
                        }
                      }}
                      style={{ flex: 1, minWidth: 0 }}
                      title={`Âm lượng SFX: ${scene.sfxVolume !== undefined ? scene.sfxVolume : 100}%`}
                    />
                  </div>
                  <label className="btn btn-sm btn-outline-secondary" style={{ padding: '2px 6px', fontSize: 11, display: 'flex', alignItems: 'center', gap: 2, cursor: 'pointer' }} title="Tải SFX của riêng bạn">
                    <span>+</span>
                    <input type="file" accept=".wav,.mp3" style={{ display: 'none' }} onChange={e => { onUploadSfx && onUploadSfx(e); e.target.value = ''; }} />
                  </label>
                </div>
              </div>

              {/* BGM per-scene */}
              <div style={{ flex: 1, minWidth: 200 }}>
                <label className="field-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Music size={12} style={{ verticalAlign: 'middle' }} />
                  <span>NHẠC NỀN CẢNH NÀY</span>
                  <input
                    type="checkbox"
                    checked={bgmOverridden}
                    title="Chỉnh riêng âm lượng nhạc nền cho cảnh này."
                    onChange={e => onUpdate(idx, 'bgm_volume', e.target.checked ? globalBgmVolume / 100 : undefined)}
                  />
                </label>
                {bgmOverridden ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <input
                      type="range" min="0" max="100" step="5"
                      className="form-range"
                      style={{ flex: 1 }}
                      value={Math.round(scene.bgm_volume * 100)}
                      onChange={e => onUpdate(idx, 'bgm_volume', Number(e.target.value) / 100)}
                    />
                    <span style={{ fontSize: 12, minWidth: 34, textAlign: 'right' }}>{Math.round(scene.bgm_volume * 100)}%</span>
                  </div>
                ) : (
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', paddingTop: 6 }}>
                    Theo mức chung ({globalBgmVolume}%)
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
      )}
    </div>
  );
}
