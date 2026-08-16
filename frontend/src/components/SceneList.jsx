import React, { useRef, useCallback } from 'react';
import {
  ChevronUp, ChevronDown, ChevronRight,
  AlertTriangle, PenLine, RotateCcw, Clipboard,
  Plus, CheckCircle, Zap, Code, Headphones, Pause, X,
} from 'lucide-react';
import { validateImportPayload, normalizeImportPayload } from '../lib/sharedSchema';
import { toast } from '../lib/toast.jsx';
import SceneCard from './SceneCard';

// Constants (duplicated from ScriptEditor — consider moving to a shared constants file)
const FALLBACK_WPS = 3.0;
const SHOT_MIN_S = 2.5;
const SHOT_MAX_S = 6.5;
const SCENE_TRANSITION_OVERHEAD = 0.5;
const BREAK_SNIPPET = '<break time="1s"/>';
const CACHE_PROBE_DELAY_MS = 600;

const BREAK_TAG_RE = /<break[^>]*>/gi;
const BREAK_TIME_RE = /<break[^>]*time\s*=\s*"([\d.]+)\s*(ms|s)"[^>]*>/gi;

const countWords = (text) => {
  const cleaned = (text || '').replace(BREAK_TAG_RE, ' ').trim();
  return cleaned ? cleaned.split(/\s+/).length : 0;
};
const breakSeconds = (text) => {
  let total = 0;
  for (const [, value, unit] of (text || '').matchAll(BREAK_TIME_RE)) {
    const v = parseFloat(value);
    if (!Number.isNaN(v)) total += unit.toLowerCase() === 'ms' ? v / 1000 : v;
  }
  return total;
};
const estimateSceneSeconds = (scene, wps) => {
  const words = countWords(scene?.text);
  const speech = words > 0 ? words / (wps || FALLBACK_WPS) : 0;
  return speech + breakSeconds(scene?.text) + (scene?.pause_after_ms || 0) / 1000;
};

// Nhãn thời lượng
function SceneTiming({ seconds }) {
  if (!seconds) return null;
  const tooLong = seconds > SHOT_MAX_S;
  const tooShort = seconds < SHOT_MIN_S;
  const color = tooLong ? 'var(--red, #ef4444)' : tooShort ? 'var(--amber, #f59e0b)' : 'var(--text-dim, #94a3b8)';
  const title = tooLong
    ? `Cảnh dài ~${seconds.toFixed(1)}s.`
    : tooShort
      ? `Cảnh chỉ ~${seconds.toFixed(1)}s.`
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
    : <span style={{ color: 'var(--red)' }} title={`${kindLabel}${via}: chưa có.`}>🔴 {kindLabel}</span>;
}

/**
 * SceneList — renders the full scene list panel including warnings, review badges,
 * full-mode editor, resplit preview, and the scene card map.
 *
 * Props:
 *   cacheStatus, collapsedScenes, expandedAdvanced,
 *   previewIdx, uploadingIdx, customSfxList,
 *   sceneSeconds, timing, durationBudget, timeline,
 *   collapsedScenes (Set), expandedAdvanced (Set),
 *   balancing, balancePreview, resplitting, resplitPreview,
 *   fullMode, fullText, fullLoading, fullPlaying, fullAt, fullProgress, fullScope,
 *   resplitPreview, keepBoundaries,
 *   probing,
 *   // store context snapshot (already selected by parent via useShallow)
 *   ctx: {
 *     scenes, setScenes, errorMsg, setErrorMsg,
 *     scenes: s.scenes, voice, speechRate, speechPitch, useBreathing,
 *     ratio, style, negativePrompt, activeMode, visualSource, preferStockVideo, useVeo,
 *     useSinglePassNarration, sfxVolume, bgmVolume,
 *     hookEffect, hookQuote, hookText, hookVariants, scriptReview,
 *     setHookText, setHookQuote, setCtaText, setScriptNotice, setEstimatedDurationS,
 *     ctaText, hookVariants, scriptReview,
 *   }
 *   // callbacks
 *   onScenesChange, onToggleCollapse, onToggleAdvanced,
 *   onUpdate, onRemove, onMoveUp, onMoveDown,
 *   onPreview, onStopPreview, onInsertBreak,
 *   onUploadOverride, onClearOverride,
 *   onToggleCollapseAll, isAllCollapsed,
 *   onOpenFullMode, onCloseFullMode, coSuaChuaLuu,
 *   onFullTextChange, onFullPlay, onFullStop, fullAudioRef, fullUrlRef,
 *   onRequestResplit, onApplyResplit,
 *   onRequestRebalance, onApplyRebalance,
 *   onSetBalancePreview, onSetResplitPreview,
 *   onSetKeepBoundaries,
 *   onToggleAdvanced, // for scene cards
 * }
 */
export default function SceneList({
  cacheStatus,
  collapsedScenes,
  expandedAdvanced,
  previewIdx,
  uploadingIdx,
  customSfxList,
  sceneSeconds,
  timing,
  durationBudget,
  timeline,
  probing,
  balancing,
  balancePreview,
  resplitting,
  resplitPreview,
  fullMode,
  fullText,
  fullLoading,
  fullPlaying,
  fullAt,
  fullProgress,
  fullScope,
  keepBoundaries,
  ctx,
  onScenesChange,
  onToggleCollapse,
  onToggleAdvanced,
  onUpdate,
  onRemove,
  onMoveUp,
  onMoveDown,
  onPreview,
  onStopPreview,
  onInsertBreak,
  onUploadOverride,
  onClearOverride,
  onUploadSfx,
  onToggleCollapseAll,
  isAllCollapsed,
  onOpenFullMode,
  onCloseFullMode,
  coSuaChuaLuu,
  onFullTextChange,
  onFullPlay,
  onSetKeepBoundaries,
  onRequestResplit,
  onApplyResplit,
  onRequestRebalance,
  onApplyRebalance,
  onSetBalancePreview,
  onSetResplitPreview,
}) {
  const fileInputRef = useRef(null);
  const fullAudioRef = useRef(null);
  const fullUrlRef = useRef(null);
  const textareaRefs = useRef([]);

  const reusedCount = cacheStatus
    ? cacheStatus.filter(s => s.audio_cached && s.image_cached).length
    : null;

  const handleImportJson = () => {
    if (fileInputRef.current) fileInputRef.current.click();
  };

  const processJsonString = (jsonStr) => {
    try {
      jsonStr = jsonStr.replace(/^```json\s*/i, '').replace(/^```\s*/, '').replace(/```\s*$/i, '').trim();
      jsonStr = jsonStr.replace(/,\s*([\]}])/g, '$1');
      const data = JSON.parse(jsonStr);

      if (data.scenes && Array.isArray(data.scenes)) {
        const normalized = normalizeImportPayload(data);
        const warnings = validateImportPayload(data);
        if (warnings.length > 0) {
          const proceed = window.confirm(
            `Có ${warnings.length} cảnh báo:\n\n${warnings.slice(0, 8).join('\n')}` +
            (warnings.length > 8 ? `\n... và ${warnings.length - 8} cảnh báo khác.` : '') +
            `\n\nBấm OK để tiếp tục.`
          );
          if (!proceed) return;
        }
        onScenesChange(normalized.scenes);
        if (normalized.estimated_duration_s !== undefined) ctx.setEstimatedDurationS(normalized.estimated_duration_s);
        if (data.hook_text !== undefined) ctx.setHookText(data.hook_text);
        if (data.hook_quote !== undefined) ctx.setHookQuote(data.hook_quote);
        if (data.cta_text !== undefined) ctx.setCtaText(data.cta_text);
        if (data.recommended_bgm) ctx.setBgm(data.recommended_bgm);
        if (data.outro_text !== undefined) ctx.setOutroText(data.outro_text);
        toast(`Nhập JSON thành công! ${normalized.scenes.length} cảnh đã được dàn trang.`, { type: 'success' });
      } else if (Array.isArray(data)) {
        const normalized = normalizeImportPayload(data);
        const warnings = validateImportPayload({ scenes: normalized.scenes });
        if (warnings.length > 0) {
          const proceed = window.confirm(`Có ${warnings.length} cảnh báo. Tiếp tục?`);
          if (!proceed) return;
        }
        onScenesChange(normalized.scenes);
        toast(`Nhập mảng JSON thành công! ${normalized.scenes.length} cảnh.`, { type: 'success' });
      } else {
        toast('Lỗi: Cấu trúc JSON không hợp lệ.', { type: 'error' });
      }
    } catch (err) {
      toast('Lỗi parse JSON: ' + err.message, { type: 'error' });
    }
  };

  const handlePasteJson = async () => {
    try {
      let text = '';
      if (navigator.clipboard && navigator.clipboard.readText) {
        text = await navigator.clipboard.readText();
      } else {
        text = window.prompt('Dán JSON vào đây:') || '';
      }
      if (!text || !text.trim()) {
        toast('Clipboard trống hoặc bạn chưa dán nội dung.', { type: 'warning' });
        return;
      }
      processJsonString(text);
    } catch (err) {
      const text = window.prompt('Không đọc được clipboard. Dán JSON thủ công vào đây:');
      if (text && text.trim()) processJsonString(text);
    }
  };

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (ev) => processJsonString(ev.target.result);
      reader.readAsText(file);
      e.target.value = null;
    }
  };

  const scenesToText = (scenes) => scenes.map(s => (s.text || '').trim()).filter(Boolean).join('\n\n');

  const stopFullPreview = useCallback(() => {
    if (fullAudioRef.current) { fullAudioRef.current.pause(); fullAudioRef.current = null; }
    if (fullUrlRef.current) { URL.revokeObjectURL(fullUrlRef.current); fullUrlRef.current = null; }
    onFullPlay(false);
  }, [onFullPlay]);

  return (
    <>
      {/* ── Toolbar ── */}
      <div className="editor-toolbar">
        <button className="btn-outline" onClick={() => ctx.setStep('config')}><RotateCcw size={14} /> Quay lại cài đặt</button>
        <div className="editor-toolbar-info" style={{ flex: 1, display: 'flex', alignItems: 'center' }}>
          <div style={{ whiteSpace: 'nowrap' }}>
            <PenLine size={14} /> {ctx.scenes.length} cảnh
            {reusedCount !== null && (
              <span style={{ marginLeft: 10 }} title="Cảnh đã có đủ giọng đọc + hình trong bộ nhớ đệm sẽ được tái dùng.">
                — 🟢 <strong>{reusedCount}</strong> cảnh tái dùng, 🔴 <strong>{ctx.scenes.length - reusedCount}</strong> tạo mới
              </span>
            )}
          </div>

          {ctx.scenes.length > 0 && (
            <div
              style={{ marginLeft: 24, flex: 1, maxWidth: 400, display: 'flex', flexDirection: 'column', gap: 4 }}
              title={'Hook và Outro CỘNG THÊM vào tổng thời lượng, không lấy bớt từ lời thoại.'}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-secondary)' }}>
                <span>⏳ Tổng: <strong>~{timeline.total.toFixed(1)}s</strong></span>
                {ctx.introBgm && ctx.introBgm !== 'none' && (
                  <span title="Khoảng thời gian nhạc mở màn chiếm.">
                    🎵 Intro phủ: <strong>{(ctx.introBgmDuration > 0 ? ctx.introBgmDuration : timeline.introBgmAuto).toFixed(1)}s</strong>
                  </span>
                )}
              </div>

              <div style={{ position: 'relative', height: 8, background: 'var(--surface-hover)', borderRadius: 4, overflow: 'hidden', display: 'flex' }}>
                {timeline.hookLead > 0 && (
                  <div style={{ height: '100%', width: `${(timeline.hookLead / timeline.total) * 100}%`, background: 'var(--amber)' }} />
                )}
                {timeline.speech > 0 && (
                  <div style={{ height: '100%', width: `${(timeline.speech / timeline.total) * 100}%`, background: '#a855f7' }} />
                )}
                {timeline.outroDur > 0 && (
                  <div style={{ height: '100%', width: `${(timeline.outroDur / timeline.total) * 100}%`, background: '#3b82f6' }} />
                )}
                {ctx.introBgm && ctx.introBgm !== 'none' && (
                  <div style={{
                    position: 'absolute', left: 0, bottom: 0, height: 2,
                    width: `${(Math.min(ctx.introBgmDuration > 0 ? ctx.introBgmDuration : timeline.introBgmAuto, timeline.total) / timeline.total) * 100}%`,
                    background: 'var(--green)'
                  }} />
                )}
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, opacity: 0.7 }}>
                {timeline.hookLead > 0 && <span>Hook {timeline.hookLead.toFixed(1)}s</span>}
                {timeline.speech > 0 && <span style={{ textAlign: timeline.hookLead > 0 ? 'center' : 'left', flex: 1 }}>Lời thoại {timeline.speech.toFixed(1)}s</span>}
                {timeline.outroDur > 0 && <span>Outro {timeline.outroDur.toFixed(1)}s</span>}
              </div>
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            type="button"
            className="btn-outline"
            style={{ borderColor: 'var(--green, #22c55e)', color: 'var(--green, #22c55e)', padding: '10px 16px' }}
            onClick={fullMode ? onCloseFullMode : onOpenFullMode}
            disabled={!ctx.scenes.length}
            title="Xem và sửa toàn bộ lời thoại như một bài liền mạch"
          >
            <PenLine size={16} /> {fullMode ? 'Đóng chế độ toàn bài' : 'Sửa toàn bộ kịch bản'}
          </button>
          <input type="file" accept=".json" style={{ display: 'none' }} ref={fileInputRef} onChange={handleFileSelect} />
          <button
            type="button"
            className="btn-outline"
            style={{ borderColor: 'var(--purple, #a78bfa)', color: 'var(--purple, #a78bfa)', padding: '10px 16px' }}
            onClick={handlePasteJson}
            title="Dán JSON trực tiếp từ clipboard"
          >
            <Clipboard size={16} /> Dán JSON
          </button>
          <button type="button" className="btn-outline" style={{ borderColor: 'var(--amber)', color: 'var(--amber)', padding: '10px 16px' }} onClick={handleImportJson}>
            <Code size={16} /> Import JSON
          </button>
          <button type="button" className="btn-outline" style={{ padding: '10px 16px' }} onClick={onToggleCollapseAll} disabled={!ctx.scenes.length}>
            {isAllCollapsed ? <ChevronDown size={16} /> : <ChevronUp size={16} />} {isAllCollapsed ? 'Mở rộng tất cả' : 'Thu gọn tất cả'}
          </button>
        </div>
      </div>

      {ctx.errorMsg && <div className="error-box" style={{ marginBottom: 16 }}><AlertTriangle size={16} /> {ctx.errorMsg}</div>}

      {ctx.scriptNotice && (
        <div className="warning-box" style={{ marginBottom: 16, borderColor: 'var(--green, #22c55e)', color: 'var(--green, #22c55e)' }}>
          <span style={{ flex: 1 }}>{ctx.scriptNotice}</span>
          <button className="btn-icon" onClick={() => ctx.setScriptNotice('')} title="Đóng thông báo">
            <X size={14} />
          </button>
        </div>
      )}

      {/* ── AI Script Review Badge ── */}
      {ctx.scriptReview && (
        <div className="panel-box" style={{ marginBottom: 16, padding: '12px 16px', borderLeft: `4px solid ${ctx.scriptReview.passed ? 'var(--green)' : 'var(--red)'}` }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: ctx.scriptReview.review_notes?.length ? 8 : 0 }}>
            <div style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
              <CheckCircle size={16} color={ctx.scriptReview.passed ? 'var(--green)' : 'var(--red)'} />
              AI Script Review: Điểm {ctx.scriptReview.quality_score}/100
            </div>
            {!ctx.scriptReview.passed && (
              <span style={{ fontSize: 12, color: 'var(--red)', fontWeight: 600 }}>Cần chỉnh sửa</span>
            )}
          </div>
          {ctx.scriptReview.review_notes && ctx.scriptReview.review_notes.length > 0 && (
            <ul style={{ margin: 0, paddingLeft: 20, fontSize: 13, display: 'flex', flexDirection: 'column', gap: 4 }}>
              {ctx.scriptReview.review_notes.map((note, i) => (
                <li key={i} style={{ color: note.severity === 'error' ? 'var(--red)' : note.severity === 'warning' ? 'var(--amber)' : 'var(--text-secondary)' }}>
                  <strong>Cảnh {note.scene_index}:</strong> {note.message}. <em style={{ opacity: 0.8 }}>{note.suggestion}</em>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* ── A/B Hook Selector ── */}
      {ctx.hookVariants && ctx.hookVariants.length > 0 && (
        <div className="panel-box" style={{ marginBottom: 16, padding: '12px 16px' }}>
          <div style={{ fontWeight: 600, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Zap size={16} color="var(--amber)" /> A/B Hook Selector — Chọn câu mở đầu thu hút nhất
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {ctx.hookVariants.map((variant, i) => {
              const isSelected = ctx.hookText === variant || ctx.hookQuote === variant;
              return (
                <div
                  key={i}
                  onClick={() => { ctx.setHookText(variant); ctx.setHookQuote(variant); }}
                  style={{
                    flex: '1 1 30%', minWidth: 200, padding: 10, borderRadius: 6, cursor: 'pointer',
                    background: isSelected ? 'rgba(245, 158, 11, 0.1)' : 'var(--bg-primary)',
                    border: `1px solid ${isSelected ? 'var(--amber)' : 'var(--border)'}`,
                    transition: 'all 0.2s'
                  }}
                >
                  <div style={{ fontSize: 13, color: isSelected ? 'var(--amber)' : 'var(--text-primary)', lineHeight: 1.4 }}>"{variant}"</div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Duration warnings ── */}
      {(durationBudget.isOver || durationBudget.isUnder || durationBudget.tooLongScenes > 0) && (
        <div className="warning-box" style={{ marginBottom: 16 }}>
          <AlertTriangle size={16} />
          <span>
            Kịch bản đọc hết khoảng <strong>{Math.round(durationBudget.total)}s</strong>
            {durationBudget.targetS != null && <> so với mục tiêu {durationBudget.durationLabel}</>}
            {durationBudget.isOver && ' — dài hơn đáng kể, cân nhắc rút gọn lời thoại.'}
            {durationBudget.isUnder && ' — ngắn hơn nhiều, có thể thêm ý cho đủ nhịp.'}
            {durationBudget.tooLongScenes > 0 && (
              <> Có <strong>{durationBudget.tooLongScenes}</strong> cảnh vượt {SHOT_MAX_S}s — ảnh đứng yên quá lâu làm nhịp video ì.</>
            )}
            {!timing.isLearned && (
              <em style={{ opacity: 0.75 }}> Ước lượng theo tốc độ đọc mặc định {timing.wps} từ/giây.</em>
            )}
          </span>
          <button
            className="btn-outline"
            onClick={onRequestRebalance}
            disabled={balancing || !ctx.scenes.length || fullMode}
            style={{ marginLeft: 12, whiteSpace: 'nowrap', flexShrink: 0 }}
          >
            {balancing ? 'Đang tính...' : 'Chia lại nhịp'}
          </button>
        </div>
      )}

      {/* ── Balance preview ── */}
      {balancePreview && (
        <div className="warning-box" style={{ marginBottom: 16, display: 'block', borderColor: 'var(--green, #22c55e)' }}>
          {(() => {
            const { before, after, groups, changed } = balancePreview.report;
            if (!changed) {
              return (
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <span>Kịch bản đã chia đều rồi — không có gì cần đổi.</span>
                  <button className="btn-outline" onClick={() => onSetBalancePreview(null)}>Đóng</button>
                </div>
              );
            }
            return (
              <>
                <div style={{ fontWeight: 700, marginBottom: 8 }}>Đề xuất chia lại nhịp</div>
                <table style={{ fontSize: 12, marginBottom: 10, borderSpacing: '14px 2px' }}>
                  <tbody>
                    <tr style={{ opacity: 0.7 }}><td /><td>hiện tại</td><td>sau khi chia</td></tr>
                    <tr><td>Số cảnh</td><td>{before.scenes}</td><td><strong>{after.scenes}</strong></td></tr>
                    <tr><td>Cảnh dài nhất</td><td>{before.longest}s</td><td><strong>{after.longest}s</strong></td></tr>
                    <tr><td>Cảnh ngắn nhất</td><td>{before.shortest}s</td><td><strong>{after.shortest}s</strong></td></tr>
                    <tr><td>Số cảnh lệch nhịp</td><td>{before.off_pace}</td><td><strong>{after.off_pace}</strong></td></tr>
                  </tbody>
                </table>
                <div style={{ maxHeight: 180, overflowY: 'auto', fontSize: 12, marginBottom: 10 }}>
                  {groups.map((g) => (
                    <div key={g.scene} style={{ opacity: g.action === 'keep' ? 0.6 : 1 }}>
                      Cảnh {g.scene}: {g.seconds}s
                      {g.action === 'merge' && <> — gộp lời của cảnh {g.from_scenes.join(' + ')}</>}
                      {g.action === 'split' && <> — tách từ cảnh {g.from_scenes[0]}</>}
                      {g.too_long && <span style={{ color: 'var(--red, #ef4444)' }}> (vẫn dài)</span>}
                    </div>
                  ))}
                </div>
                <div style={{ fontSize: 12, opacity: 0.8, marginBottom: 10 }}>
                  Lời thoại giữ nguyên. Khi gộp hai cảnh, ảnh của cảnh bị gộp sẽ không còn được dùng.
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn-outline" onClick={onApplyRebalance} style={{ borderColor: 'var(--green, #22c55e)', color: 'var(--green, #22c55e)', fontWeight: 700 }}>Áp dụng</button>
                  <button className="btn-outline" onClick={() => onSetBalancePreview(null)}>Huỷ</button>
                </div>
              </>
            );
          })()}
        </div>
      )}

      {/* ── Full-mode editor ── */}
      {fullMode && (
        <div className="panel-box" style={{ marginBottom: 16, padding: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
            <strong style={{ flex: 1 }}>Toàn bộ lời thoại — sửa thoải mái, chia cảnh tính sau</strong>
            <button
              className="btn-outline"
              onClick={onFullPlay}
              disabled={fullLoading || !ctx.scenes.length}
              style={{ borderColor: 'var(--green, #22c55e)', color: 'var(--green, #22c55e)' }}
            >
              {fullLoading ? <>Đang sinh giọng…</> : fullPlaying ? <><Pause size={14} /> Dừng</> : <><Headphones size={14} /> Nghe thử cả bài</>}
            </button>
          </div>

          {fullProgress && (
            <div style={{ marginBottom: 10 }}>
              <div style={{ height: 6, background: 'var(--bg-dim, #1e293b)', borderRadius: 3, overflow: 'hidden' }}>
                <div style={{ width: `${fullProgress.percent}%`, height: '100%', background: 'var(--green, #22c55e)', transition: 'width .4s ease' }} />
              </div>
              <div style={{ fontSize: 12, opacity: 0.8, marginTop: 4 }}>{fullProgress.message}</div>
            </div>
          )}

          {fullScope && (
            <div style={{ fontSize: 12, marginBottom: 8, color: fullScope === 'per_scene' ? 'var(--green, #22c55e)' : 'var(--text-dim, #94a3b8)' }}>
              {fullScope === 'per_scene'
                ? 'Đã lưu đệm giọng đọc cho từng cảnh — render sẽ dùng lại ngay.'
                : 'Bản đọc này được lưu đệm cho CẢ BÀI.'}
            </div>
          )}

          <div style={{ fontSize: 12, opacity: 0.75, marginBottom: 8 }}>
            Mỗi đoạn cách nhau một <strong>dòng trống</strong> là một cảnh.
            Xoá dòng trống để <strong>gộp</strong>, thêm dòng trống để <strong>tách</strong>.
          </div>

          <textarea
            className="form-input"
            value={fullText}
            onChange={e => onFullTextChange(e.target.value)}
            spellCheck={false}
            style={{ width: '100%', minHeight: 320, lineHeight: 1.7, fontSize: 15, resize: 'vertical' }}
            placeholder="Toàn bộ lời thoại của video..."
          />

          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 10, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 12, opacity: 0.7 }}>
              {fullText.trim() ? fullText.trim().split(/\n\s*\n+/).length : 0} đoạn · {countWords(fullText)} từ
              {fullAt !== null && <> · đang đọc cảnh <strong>{fullAt + 1}</strong></>}
            </span>
            <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
              <input type="checkbox" checked={keepBoundaries} onChange={e => onSetKeepBoundaries(e.target.checked)} />
              Giữ đúng ranh giới tôi chia
            </label>
            <div style={{ flex: 1 }} />
            <button
              className="btn-outline"
              onClick={onRequestResplit}
              disabled={resplitting || !fullText.trim()}
              style={{ borderColor: 'var(--green, #22c55e)', color: 'var(--green, #22c55e)', fontWeight: 700 }}
            >
              {resplitting ? 'Đang chia…' : 'Chia lại thành cảnh →'}
            </button>
          </div>
        </div>
      )}

      {/* ── Resplit preview ── */}
      {resplitPreview && (
        <div className="warning-box" style={{ marginBottom: 16, display: 'block', borderColor: 'var(--green, #22c55e)' }}>
          {(() => {
            const r = resplitPreview.report;
            return (
              <>
                <div style={{ fontWeight: 700, marginBottom: 8 }}>
                  Đề xuất: {r.canh_goc} cảnh → <strong>{r.canh_ket_qua} cảnh</strong>
                  {r.da_can_nhip ? ' (đã cân nhịp)' : ' (giữ đúng ranh giới bạn chia)'}
                </div>
                {r.doan_viet_moi > 0 && (
                  <div style={{ fontSize: 12, color: 'var(--amber)', marginBottom: 8 }}>
                    {r.doan_viet_moi} đoạn bạn viết mới không dò được về cảnh cũ.
                  </div>
                )}
                <div style={{ maxHeight: 200, overflowY: 'auto', fontSize: 12, marginBottom: 10 }}>
                  {resplitPreview.scenes.map((s, i) => (
                    <div key={i} style={{ marginBottom: 4 }}>
                      <strong>Cảnh {i + 1}:</strong> {(s.text || '').slice(0, 90)}{(s.text || '').length > 90 ? '…' : ''}
                      <div style={{ opacity: 0.6, paddingLeft: 12 }}>
                        🖼 {(s.image_prompt || '(chưa có mô tả ảnh)').slice(0, 80)}
                      </div>
                    </div>
                  ))}
                </div>
                <div style={{ fontSize: 12, opacity: 0.8, marginBottom: 10 }}>
                  Lời thoại giữ đúng từng chữ bạn vừa sửa.
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn-outline" onClick={onApplyResplit} style={{ borderColor: 'var(--green, #22c55e)', color: 'var(--green, #22c55e)', fontWeight: 700 }}>Áp dụng</button>
                  <button className="btn-outline" onClick={() => onSetResplitPreview(null)}>Huỷ</button>
                </div>
              </>
            );
          })()}
        </div>
      )}

      {/* ── Scene list ── */}
      <div className="scene-list">
        {ctx.scenes.map((scene, idx) => (
          <SceneCard
            key={idx}
            scene={scene}
            idx={idx}
            collapsed={collapsedScenes.has(idx)}
            expandedAdvanced={expandedAdvanced.has(idx)}
            previewIdx={previewIdx}
            uploadingIdx={uploadingIdx}
            customSfxList={customSfxList}
            cacheStatus={cacheStatus}
            probing={probing}
            sceneSeconds={sceneSeconds}
            textareaRefs={textareaRefs}
            onToggleCollapse={onToggleCollapse}
            onToggleAdvanced={onToggleAdvanced}
            onUpdate={onUpdate}
            onRemove={onRemove}
            onMoveUp={onMoveUp}
            onMoveDown={onMoveDown}
            onPreview={onPreview}
            onStopPreview={onStopPreview}
            onInsertBreak={onInsertBreak}
            onUploadOverride={onUploadOverride}
            onClearOverride={onClearOverride}
            onUploadSfx={onUploadSfx}
            totalScenes={ctx.scenes.length}
            globalSfxVolume={ctx.sfxVolume}
            globalBgmVolume={ctx.bgmVolume}
            globalUseSinglePassNarration={ctx.useSinglePassNarration}
            globalUseSfx={ctx.useSfx}
          />
        ))}
      </div>
      <button className="btn-add-scene" onClick={() => onScenesChange(prev => [...prev, { scene: prev.length + 1, text: '', image_prompt: '' }])}>
        <Plus size={16} /> Thêm cảnh mới
      </button>
    </>
  );
}
