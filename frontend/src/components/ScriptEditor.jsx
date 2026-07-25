import React from 'react';
import { RotateCcw, PenLine, Play, AlertTriangle, ChevronUp, ChevronDown, Trash2, Plus, Film, Volume2, Code } from 'lucide-react';
import { useAppContext } from '../AppContext';
import { API_BASE, MODE_MAP, TRANSITIONS, SFX_OPTIONS } from '../constants';

export default function ScriptEditor() {
  const ctx = useAppContext();

  const handleRenderVideo = async () => {
    if (!ctx.scenes.length) return ctx.setErrorMsg('Chưa có cảnh nào để render!');
    ctx.setErrorMsg('');
    ctx.setStep('rendering');
    ctx.setStatus('loading');
    ctx.setProgress(0);
    ctx.setJobMessage('Đang khởi tạo...');
    ctx.setProgressLog([]);
    ctx.setVideoUrl(null);
    ctx.setSrtUrl(null);

    try {
      const payload = {
        scenes: ctx.scenes, mode: MODE_MAP[ctx.activeMode], aspect_ratio: ctx.ratio, voice: ctx.voice,
        art_style: ctx.style,
        bgm_track: ctx.bgm === 'none' ? null : ctx.bgm, upload_session_id: ctx.uploadSessionId || undefined,
        speech_rate: ctx.speechRate, speech_pitch: ctx.speechPitch, bgm_volume: ctx.bgmVolume / 100,
        negative_prompt: ctx.negativePrompt || undefined, gemini_api_key: ctx.apiKey || undefined,
        use_veo: ctx.useVeo, cta_text: ctx.ctaText || undefined, use_animated_captions: ctx.useAnimatedCaptions,
        character_description: ctx.characterDescription || undefined, use_frame_chaining: ctx.useFrameChaining,
        use_ken_burns: ctx.useKenBurns, use_beat_sync: ctx.useBeatSync, use_veo_ambient_audio: ctx.useVeoAmbientAudio,
        use_gpu_encode: ctx.useGpuEncode, hook_zoom_boost: ctx.hookZoomBoost,
        use_sfx: ctx.useSfx, sfx_volume: ctx.sfxVolume / 100,
        subtitle_style: ctx.subtitleStyle, color_grading: ctx.colorGrading, watermark_text: ctx.watermarkText || undefined,
        cover_image_session_id: ctx.coverImageSessionId || undefined,
        cover_image_position: ctx.coverImagePosition,
        use_breathing: ctx.useBreathing, hook_effect: ctx.hookEffect, hook_quote: ctx.hookQuote,
        hook_text: ctx.hookText,
        prefer_stock_video: ctx.preferStockVideo,
      };

      const res = await fetch(`${API_BASE}/api/render-video`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Lỗi server');
      }

      const data = await res.json();
      const jobId = data.job_id;

      const ws = new WebSocket(`ws://localhost:8000/api/ws/job-status/${jobId}`);

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.progress !== undefined) ctx.setProgress(msg.progress);
        if (msg.message) {
          ctx.setJobMessage(msg.message);
          ctx.setProgressLog(prev => {
            const last = prev[prev.length - 1];
            if (last === msg.message) return prev;
            return [...prev, msg.message];
          });
        }
        if (msg.status === 'done') {
          ws.close();
          ctx.setStatus('done');
          ctx.setStep('done');
          if (msg.video_url) ctx.setVideoUrl(`${API_BASE}${msg.video_url}`);
          if (msg.srt_url) ctx.setSrtUrl(`${API_BASE}${msg.srt_url}`);
        } else if (msg.status === 'error') {
          ws.close();
          ctx.setStatus('error');
          ctx.setStep('rendering');
          ctx.setErrorMsg(msg.error || msg.message || 'Có lỗi xảy ra');
        }
      };

      ws.onerror = () => {
        ctx.setStatus('error');
        ctx.setErrorMsg('Mất kết nối WebSocket với máy chủ!');
      };
    } catch (err) {
      ctx.setStatus('error');
      ctx.setErrorMsg(err.message);
    }
  };

  const updateScene = (index, field, value) => {
    ctx.setScenes(prev => prev.map((s, i) => i === index ? { ...s, [field]: value } : s));
  };
  const removeScene = (index) => {
    ctx.setScenes(prev => prev.filter((_, i) => i !== index).map((s, i) => ({ ...s, scene: i + 1 })));
  };
  const addScene = () => {
    ctx.setScenes(prev => [...prev, { scene: prev.length + 1, text: '', image_prompt: '' }]);
  };
  const moveScene = (from, to) => {
    if (to < 0 || to >= ctx.scenes.length) return;
    ctx.setScenes(prev => {
      const arr = [...prev];
      const [item] = arr.splice(from, 1);
      arr.splice(to, 0, item);
      return arr.map((s, i) => ({ ...s, scene: i + 1 }));
    });
  };

  const handleImportJson = () => {
    const jsonStr = prompt('Dán mã JSON kịch bản (từ AI) vào đây:');
    if (!jsonStr) return;
    try {
      const data = JSON.parse(jsonStr);
      if (data.scenes && Array.isArray(data.scenes)) {
        ctx.setScenes(data.scenes);
        if (data.hook_text !== undefined) ctx.setHookText(data.hook_text);
        if (data.hook_quote !== undefined) ctx.setHookQuote(data.hook_quote);
        if (data.cta_text !== undefined) ctx.setCtaText(data.cta_text);
        if (data.recommended_bgm) ctx.setBgm(data.recommended_bgm);
        alert('Nhập JSON thành công! Cảnh đã được dàn trang.');
      } else if (Array.isArray(data)) {
        ctx.setScenes(data);
        alert('Nhập mảng JSON thành công! Cảnh đã được dàn trang.');
      } else {
        alert('Lỗi: Cấu trúc JSON không hợp lệ (không tìm thấy scenes).');
      }
    } catch (e) {
      alert('Lỗi parse JSON: ' + e.message);
    }
  };

  return (
    <div className="editor-layout">
      <div className="editor-toolbar">
        <button className="btn-outline" onClick={() => ctx.setStep('config')}><RotateCcw size={14} /> Quay lại cài đặt</button>
        <div className="editor-toolbar-info"><PenLine size={14} /> {ctx.scenes.length} cảnh — Chỉnh sửa lời thoại & mô tả ảnh bên dưới</div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn-outline" style={{ borderColor: 'var(--amber)', color: 'var(--amber)', padding: '10px 16px' }} onClick={handleImportJson}>
            <Code size={16} /> Import JSON
          </button>
          <button className="btn-generate" style={{ width: 'auto', padding: '10px 24px', marginTop: 0 }} onClick={handleRenderVideo}>
            <Play size={16} /> Render Video (Bước 2)
          </button>
        </div>
      </div>

      {ctx.errorMsg && <div className="error-box" style={{ marginBottom: 16 }}><AlertTriangle size={16} /> {ctx.errorMsg}</div>}

      <div className="scene-list">
        {ctx.scenes.map((scene, idx) => (
          <div key={idx} className="scene-card">
            <div className="scene-header">
              <div className="scene-number">Cảnh {idx + 1}</div>
              <div className="scene-actions">
                <button className="btn-icon" onClick={() => moveScene(idx, idx - 1)} disabled={idx === 0} title="Di chuyển lên"><ChevronUp size={14} /></button>
                <button className="btn-icon" onClick={() => moveScene(idx, idx + 1)} disabled={idx === ctx.scenes.length - 1} title="Di chuyển xuống"><ChevronDown size={14} /></button>
                <button className="btn-icon btn-danger" onClick={() => removeScene(idx)} title="Xóa cảnh" disabled={ctx.scenes.length <= 1}><Trash2 size={14} /></button>
              </div>
            </div>
            <div className="scene-fields">
              <div className="scene-field">
                <label className="field-label">LỜI THOẠI (TIẾNG VIỆT) {scene.text?.includes('<break') && <span style={{ fontSize: 11, color: 'var(--amber)', fontWeight: 400, marginLeft: 8 }}>⏸ Có ngắt nghỉ cảm xúc</span>}</label>
                <textarea className="form-textarea scene-textarea" value={scene.text} onChange={e => updateScene(idx, 'text', e.target.value)} placeholder="Lời thoại sẽ được đọc bằng TTS..." rows={3} />
              </div>
              <div className="scene-field">
                <label className="field-label">MÔ TẢ HÌNH ẢNH (TIẾNG ANH)</label>
                <textarea className="form-textarea scene-textarea" value={scene.image_prompt} onChange={e => updateScene(idx, 'image_prompt', e.target.value)} placeholder="Image prompt for AI image generation..." rows={2} />
              </div>
              <div className="scene-field" style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <div style={{ flex: 1, minWidth: 160 }}>
                  <label className="field-label"><Film size={12} style={{ verticalAlign: 'middle' }} /> CHUYỂN CẢNH (sang cảnh sau)</label>
                  <select
                    className="form-select form-select-sm"
                    value={scene.transition || 'crossfade'}
                    onChange={e => updateScene(idx, 'transition', e.target.value)}
                  >
                    {TRANSITIONS.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                  </select>
                </div>
                <div style={{ flex: 1, minWidth: 160 }}>
                  <label className="field-label"><Volume2 size={12} style={{ verticalAlign: 'middle' }} /> TIẾNG ĐỘNG (SFX) CẢNH NÀY</label>
                  <select
                    className="form-select form-select-sm"
                    value={scene.sfx || ''}
                    onChange={e => {
                      const val = e.target.value;
                      updateScene(idx, 'sfx', val);
                      if (val) {
                        const audio = new Audio(`${API_BASE}/api/preview/sfx/${val}`);
                        audio.volume = ctx.sfxVolume ? (ctx.sfxVolume / 100) : 0.5;
                        audio.play().catch(err => console.error("SFX preview error:", err));
                      }
                    }}
                  >
                    {SFX_OPTIONS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                  </select>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
      <button className="btn-add-scene" onClick={addScene}><Plus size={16} /> Thêm cảnh mới</button>
    </div>
  );
}
