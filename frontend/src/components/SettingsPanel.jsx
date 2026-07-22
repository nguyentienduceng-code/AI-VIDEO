import React from 'react';
import { AlertTriangle, Sparkles } from 'lucide-react';
import { API_BASE, MODE_MAP } from '../constants';
import { useAppContext } from '../AppContext';
import InputSection from './InputSection';
import ConfigSection from './ConfigSection';
import AdvancedSettings from './AdvancedSettings';

export default function SettingsPanel() {
  const ctx = useAppContext();

  const handleGenerateScript = async () => {
    if (ctx.activeMode === 'manual') {
      const emptyScenes = Array.from({ length: ctx.numScenes }, (_, i) => ({
        scene: i + 1,
        text: '',
        image_prompt: ''
      }));
      ctx.setScenes(emptyScenes);
      ctx.setStep('editor');
      return;
    }

    if (ctx.needsTopic && !ctx.topic.trim()) return ctx.setErrorMsg('Vui lòng nhập chủ đề video!');
    if (ctx.needsScript && !ctx.scriptText.trim()) return ctx.setErrorMsg('Vui lòng nhập nội dung kịch bản!');
    if (ctx.needsUpload && !ctx.uploadSessionId) return ctx.setErrorMsg('Vui lòng upload ảnh trước!');
    ctx.setErrorMsg('');
    ctx.setScriptLoading(true);
    try {
      const payload = {
        topic: ctx.topic, mode: MODE_MAP[ctx.activeMode], num_scenes: ctx.numScenes, art_style: ctx.style,
        target_duration: ctx.targetDuration, narration_tone: ctx.narrationTone,
        script_text: ctx.scriptText || undefined, upload_session_id: ctx.uploadSessionId || undefined,
        gemini_api_key: ctx.apiKey || undefined, character_description: ctx.characterDescription || undefined,
      };
      const res = await fetch(`${API_BASE}/api/generate-script`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Lỗi sinh kịch bản');
      }
      const data = await res.json();
      ctx.setScenes(data.scenes || []);
      if (data.recommended_bgm && ctx.bgm === 'auto') {
        ctx.setBgm(data.recommended_bgm);
      }
      ctx.setStep('editor');
    } catch (err) {
      ctx.setErrorMsg(err.message);
    } finally {
      ctx.setScriptLoading(false);
    }
  };

  const handleManualBypass = () => {
    const emptyScenes = Array.from({ length: ctx.numScenes }, (_, i) => ({
      scene: i + 1,
      text: '',
      image_prompt: ''
    }));
    ctx.setScenes(emptyScenes);
    ctx.setStep('editor');
  };

  return (
    <div className="settings-two-column">
      {/* Cột trái: Cấu hình */}
      <div className="settings-col">
        <ConfigSection />
        <AdvancedSettings />
      </div>

      {/* Cột phải: Input và nút Generate */}
      <div className="settings-col">
        <InputSection />
        
        <div style={{ marginTop: '20px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <button className="btn-generate" onClick={handleGenerateScript} disabled={ctx.scriptLoading}>
            {ctx.scriptLoading ? <span className="btn-loading"><div className="spinner" /> Đang xử lý...</span> : <><Sparkles size={18} /> Sinh Kịch Bản Bằng AI (Bước 2)</>}
          </button>
          
          <button 
            className="btn-outline" 
            onClick={handleManualBypass} 
            disabled={ctx.scriptLoading}
            style={{ width: '100%', padding: '12px', borderRadius: '12px', border: '1px solid var(--border)', background: 'transparent', color: 'var(--text-secondary)', cursor: 'pointer', fontWeight: 500 }}
          >
            ✏️ Tự Nhập Kịch Bản Bằng Tay
          </button>

          {ctx.errorMsg && (
            <div className="error-box" style={{ marginTop: 6 }}>
              <AlertTriangle size={16} /> 
              <span>
                {ctx.errorMsg}
                <br/>
                <span style={{ fontSize: 12, opacity: 0.8 }}>
                  Gợi ý: Nếu AI đang quá tải, bạn có thể bấm "Tự Nhập Kịch Bản Bằng Tay" ở trên.
                </span>
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
