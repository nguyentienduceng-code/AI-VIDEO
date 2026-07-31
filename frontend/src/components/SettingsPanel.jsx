import React, { useState } from 'react';
import { AlertTriangle, Sparkles, Settings2, Zap, HardDrive } from 'lucide-react';
import { useShallow } from 'zustand/react/shallow';
import { API_BASE, MODE_MAP } from '../constants';
import { useAppStore, needsUpload as needsUploadFor, needsScript as needsScriptFor, needsTopic as needsTopicFor } from '../store';
import InputSection from './InputSection';
import ConfigSection from './ConfigSection';
import AdvancedSettings from './AdvancedSettings';
import StorageSettings from './StorageSettings';
import ApiKeySettings from './ApiKeySettings';

export default function SettingsPanel() {
  const ctx = useAppStore(useShallow((s) => ({
    activeMode: s.activeMode,
    numScenes: s.numScenes,
    setScenes: s.setScenes,
    setStep: s.setStep,
    topic: s.topic,
    scriptText: s.scriptText,
    uploadSessionId: s.uploadSessionId,
    setErrorMsg: s.setErrorMsg,
    errorMsg: s.errorMsg,
    scriptLoading: s.scriptLoading,
    setScriptLoading: s.setScriptLoading,
    style: s.style,
    targetDuration: s.targetDuration,
    narrationTone: s.narrationTone,
    contentNiche: s.contentNiche,
    apiKey: s.apiKey,
    characterDescription: s.characterDescription,
    setEstimatedDurationS: s.setEstimatedDurationS,
    voice: s.voice,
    speechRate: s.speechRate,
    preferStockVideo: s.preferStockVideo,
    visualSource: s.visualSource,
    hookQuote: s.hookQuote,
    setHookQuote: s.setHookQuote,
    autoRetryLowQuality: s.autoRetryLowQuality,
    setScriptNotice: s.setScriptNotice,
    bgm: s.bgm,
    setBgm: s.setBgm,
    hookText: s.hookText,
    setHookText: s.setHookText,
    hookVariants: s.hookVariants,
    setHookVariants: s.setHookVariants,
    scriptReview: s.scriptReview,
    setScriptReview: s.setScriptReview,
    ctaText: s.ctaText,
    setCtaText: s.setCtaText,
  })));
  const needsUpload = needsUploadFor(ctx.activeMode);
  const needsScript = needsScriptFor(ctx.activeMode);
  const needsTopic = needsTopicFor(ctx.activeMode);
  const [activeTab, setActiveTab] = useState('basic');

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

    if (needsTopic && !ctx.topic.trim()) return ctx.setErrorMsg('Vui lòng nhập chủ đề video!');
    if (needsScript && !ctx.scriptText.trim()) return ctx.setErrorMsg('Vui lòng nhập nội dung kịch bản!');
    if (needsUpload && !ctx.uploadSessionId) return ctx.setErrorMsg('Vui lòng upload ảnh trước!');
    ctx.setErrorMsg('');
    ctx.setScriptLoading(true);
    try {
      const payload = {
        topic: ctx.topic, mode: MODE_MAP[ctx.activeMode], num_scenes: ctx.numScenes, art_style: ctx.style,
        target_duration: ctx.targetDuration, narration_tone: ctx.narrationTone,
        content_niche: ctx.contentNiche || undefined,
        script_text: ctx.scriptText || undefined, upload_session_id: ctx.uploadSessionId || undefined,
        gemini_api_key: ctx.apiKey || undefined, character_description: ctx.characterDescription || undefined,
        // Giọng + tốc độ để backend ước lượng thời lượng bằng ĐÚNG giọng sẽ đọc, khi
        // cân lại nhịp các cảnh (mode Script → Video).
        voice: ctx.voice, speech_rate: ctx.speechRate,
        // Nguồn hình phải gửi NGAY TỪ BƯỚC SINH KỊCH BẢN, không chờ tới lúc render:
        // image_prompt cho footage stock và cho ảnh AI là hai kiểu viết khác hẳn nhau
        // (backend: IMAGE_PROMPT_RULES_STOCK vs _AI). Gửi muộn thì kịch bản đã mang sẵn
        // "8k, Unreal Engine" và tìm Pexels ra video sai chủ đề.
        prefer_stock_video: ctx.preferStockVideo,
        visual_source: ctx.visualSource,
        auto_retry_low_quality: ctx.autoRetryLowQuality,
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
      // Backend đã tự cân lại nhịp: nói cho user biết vì số cảnh có thể khác con số họ
      // chọn — im lặng đổi thì trông như lỗi.
      if (data.rebalance) {
        const { before, after } = data.rebalance;
        ctx.setScriptNotice(
          `Đã tự cân lại nhịp: ${before.scenes} → ${after.scenes} cảnh, ` +
          `cảnh dài nhất ${before.longest}s → ${after.longest}s. Lời thoại giữ nguyên từng chữ.`,
        );
      } else {
        ctx.setScriptNotice('');
      }
      if (data.estimated_duration_s !== undefined) {
        ctx.setEstimatedDurationS(data.estimated_duration_s);
      }
      if (data.recommended_bgm && ctx.bgm === 'auto') {
        ctx.setBgm(data.recommended_bgm);
      }
      // Auto-điền tiêu đề Hook giật gân do AI sinh (trước đây bị vứt bỏ) nếu user chưa tự nhập
      if (data.hook_text && !ctx.hookText?.trim()) {
        ctx.setHookText(data.hook_text);
      }
      // Câu quote đắt nhất cho các hiệu ứng mở màn dạng quote (carousel_quote,
      // typewriter_quote, blackout_question). Backend trước đây KHÔNG sinh trường này dù
      // hiệu ứng đã chờ nó sẵn, nên ai muốn dùng đều phải tự gõ câu quote.
      if (data.hook_quote && !ctx.hookQuote?.trim()) {
        ctx.setHookQuote(data.hook_quote);
      }
      // Lưu hook_variants cho A/B Hook Selector (B3)
      if (data.hook_variants && data.hook_variants.length > 0) {
        ctx.setHookVariants(data.hook_variants);
      } else {
        ctx.setHookVariants([]);
      }
      // Lưu kết quả Script Review (B2)
      if (data.review) {
        ctx.setScriptReview(data.review);
        // Nói rõ khi backend đã tự viết lại kịch bản: người dùng bấm 1 lần mà nhận về bản
        // thứ hai thì phải được biết, nếu không họ tưởng AI ngẫu nhiên ra kết quả khác.
        if (data.review.regenerated) {
          ctx.setScriptNotice(
            `Bản đầu bị chấm ${data.review.previous_score}/100 nên hệ thống đã tự viết lại: ` +
            `giờ ${data.review.quality_score}/100. Tắt ở Cài đặt nâng cao nếu muốn tiết kiệm quota.`,
          );
        }
      } else {
        ctx.setScriptReview(null);
      }
      // Tương tự với CTA: mode Script → Video giờ đọc được dòng "CTA:" trong kịch bản dán vào
      if (data.cta_text && !ctx.ctaText?.trim()) {
        ctx.setCtaText(data.cta_text);
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
      {/* Cột trái: Cấu hình (Dạng Tab) */}
      <div className="settings-col settings-left-col panel-box" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        <div className="settings-tabs">
          <button className={`tab-btn ${activeTab === 'basic' ? 'active' : ''}`} onClick={() => setActiveTab('basic')}>
            <Settings2 size={16} /> Cơ bản
          </button>
          <button className={`tab-btn ${activeTab === 'advanced' ? 'active' : ''}`} onClick={() => setActiveTab('advanced')}>
            <Zap size={16} /> Nâng cao
          </button>
          <button className={`tab-btn ${activeTab === 'system' ? 'active' : ''}`} onClick={() => setActiveTab('system')}>
            <HardDrive size={16} /> Hệ thống
          </button>
        </div>
        
        <div className="tab-content" style={{ flex: 1 }}>
          {activeTab === 'basic' && <ConfigSection />}
          {activeTab === 'advanced' && <AdvancedSettings />}
          {activeTab === 'system' && (
            <>
              <ApiKeySettings />
              <StorageSettings />
            </>
          )}
        </div>
      </div>

      {/* Cột phải: Input và nút Generate */}
      <div className="settings-col panel-box" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        <InputSection />
        
        <div style={{ marginTop: 'auto', paddingTop: '20px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
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
