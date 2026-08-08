import React, { useState, useEffect } from 'react';
import { Bookmark, Save, Trash2 } from 'lucide-react';
import { useShallow } from 'zustand/react/shallow';
import { useAppStore } from '../store';
import { API_BASE } from '../constants';
import { toast } from '../lib/toast.jsx';

export default function PresetManager() {
  const ctx = useAppStore(useShallow((s) => ({
    applyPreset: s.applyPreset,
    ratio: s.ratio,
    voice: s.voice,
    style: s.style,
    bgm: s.bgm,
    targetDuration: s.targetDuration,
    narrationTone: s.narrationTone,
    speechRate: s.speechRate,
    speechPitch: s.speechPitch,
    bgmVolume: s.bgmVolume,
    hookSfxVolume: s.hookSfxVolume,   // payload lưu preset đọc giá trị này
    subtitleStyle: s.subtitleStyle,
    colorGrading: s.colorGrading,
    preferStockVideo: s.preferStockVideo,
    visualSource: s.visualSource,
    useSinglePassNarration: s.useSinglePassNarration,
    hookReelSfx: s.hookReelSfx,
    useSfx: s.useSfx,
    useKenBurns: s.useKenBurns,
    hookZoomBoost: s.hookZoomBoost,
    useBreathing: s.useBreathing,
    useFrameChaining: s.useFrameChaining,
    useBeatSync: s.useBeatSync,
    hookEffect: s.hookEffect,
    // Thiếu 6 dòng này thì payload lưu preset gửi lên `undefined` cho từng khoá, Pydantic
    // lặng lẽ thay bằng giá trị mặc định — người dùng lưu preset xong nạp lại thấy Outro
    // và nhạc mở màn biến mất, không có lỗi nào.
    introBgm: s.introBgm,
    introBgmDuration: s.introBgmDuration,
    useAudioDucking: s.useAudioDucking,
    outroEffect: s.outroEffect,
    outroReelSfx: s.outroReelSfx,
    outroSfxVolume: s.outroSfxVolume,
    // Chỉ logo, KHÔNG kèm watermarkText: chữ đóng dấu là nội dung riêng từng video.
    watermarkLogo: s.watermarkLogo,
  })));
  const [presets, setPresets] = useState([]);
  const [selectedPresetId, setSelectedPresetId] = useState('');
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [newPresetName, setNewPresetName] = useState('');
  const [loading, setLoading] = useState(false);

  const fetchPresets = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/presets`);
      if (res.ok) {
        const data = await res.json();
        setPresets(data.presets || []);
      }
    } catch (e) {
      toast("Không tải được presets: " + e.message, { type: 'error' });
    }
  };

  useEffect(() => {
    fetchPresets();
  }, []);

  const handleSelectPreset = (presetId) => {
    setSelectedPresetId(presetId);
    if (!presetId) return;
    const found = presets.find(p => p.id === presetId);
    if (found) {
      ctx.applyPreset(found);
    }
  };

  const handleSavePreset = async () => {
    if (!newPresetName.trim()) return toast("Vui lòng nhập tên cho Preset!", { type: 'warning' });
    setLoading(true);
    try {
      const payload = {
        name: newPresetName.trim(),
        aspect_ratio: ctx.ratio,
        voice: ctx.voice,
        art_style: ctx.style,
        bgm_track: ctx.bgm === 'none' ? null : ctx.bgm,
        intro_bgm_track: ctx.introBgm === 'none' ? null : ctx.introBgm,
        intro_bgm_duration: ctx.introBgmDuration,
        target_duration: ctx.targetDuration,
        narration_tone: ctx.narrationTone,
        speech_rate: ctx.speechRate,
        speech_pitch: ctx.speechPitch,
        bgm_volume: ctx.bgmVolume,
        subtitle_style: ctx.subtitleStyle,
        color_grading: ctx.colorGrading,
        prefer_stock_video: ctx.preferStockVideo,
        visual_source: ctx.visualSource,
        use_single_pass_narration: ctx.useSinglePassNarration,
        hook_reel_sfx: ctx.hookReelSfx,
        // Lưu nguyên con số trên thanh trượt (thang %, giống bgm_volume/sfx_volume).
        // KHÔNG chia 100 ở đây: việc đổi sang hệ số chỉ xảy ra ở payload render
        // (ScriptEditor.jsx). Xem chú thích đơn vị tại PresetRequest trong main.py.
        hook_sfx_volume: ctx.hookSfxVolume,
        use_sfx: ctx.useSfx,
        sfx_volume: ctx.sfxVolume,
        use_audio_ducking: ctx.useAudioDucking,
        use_ken_burns: ctx.useKenBurns,
        hook_zoom_boost: ctx.hookZoomBoost,
        use_breathing: ctx.useBreathing,
        use_frame_chaining: ctx.useFrameChaining,
        use_beat_sync: ctx.useBeatSync,
        hook_effect: ctx.hookEffect,
        outro_effect: ctx.outroEffect,
        outro_reel_sfx: ctx.outroReelSfx,
        outro_sfx_volume: ctx.outroSfxVolume,
        // Store giữ BOOLEAN (một ô tick), backend giữ TÊN FILE logo. Quy đổi đúng ở
        // ranh giới này — cùng quy ước với payload render trong ScriptEditor.jsx.
        watermark_logo: ctx.watermarkLogo ? 'logo_ntd' : null
      };

      const res = await fetch(`${API_BASE}/api/presets`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        const data = await res.json();
        await fetchPresets();
        if (data.preset) {
          setSelectedPresetId(data.preset.id);
        }
        setShowSaveModal(false);
        setNewPresetName('');
      } else {
        toast("Lỗi khi lưu Preset!", { type: 'error' });
      }
    } catch (e) {
      toast("Lỗi kết nối: " + e.message, { type: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleDeletePreset = async () => {
    if (!selectedPresetId) return;
    const found = presets.find(p => p.id === selectedPresetId);
    if (!found || found.is_default) {
      return toast("Không thể xóa Preset mặc định!", { type: 'warning' });
    }

    if (!window.confirm(`Bạn có chắc muốn xóa Preset "${found.name}"?`)) return;

    try {
      const res = await fetch(`${API_BASE}/api/presets/${selectedPresetId}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        setSelectedPresetId('');
        await fetchPresets();
      } else {
        toast("Lỗi khi xóa Preset!", { type: 'error' });
      }
    } catch (e) {
      toast("Lỗi kết nối: " + e.message, { type: 'error' });
    }
  };

  const selectedPresetObj = presets.find(p => p.id === selectedPresetId);

  return (
    <div className="preset-container" style={{ marginBottom: 15, padding: '12px 16px', background: 'rgba(255,255,255,0.03)', borderRadius: 8, border: '1px solid rgba(255,255,255,0.08)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 260 }}>
          <Bookmark size={18} style={{ color: '#FFD700' }} />
          <span style={{ fontSize: '0.9rem', fontWeight: 600, whiteSpace: 'nowrap' }}>Preset Mẫu:</span>
          <select 
            className="form-select form-select-sm" 
            value={selectedPresetId} 
            onChange={e => handleSelectPreset(e.target.value)}
            style={{ flex: 1 }}
          >
            <option value="">-- Chọn Preset lưu sẵn --</option>
            {(() => {
              const groups = {};
              presets.forEach(p => {
                const niche = p.content_niche || 'Khác';
                const nicheName = niche === 'book' ? '📚 Sách & Kể chuyện' : 
                                  niche === 'finance' ? '💰 Tài chính & Kinh doanh' :
                                  niche === 'history' ? '🏛️ Lịch sử & Khám phá' :
                                  niche === 'psychology' ? '🧠 Tâm lý & Đời sống' :
                                  niche === 'truecrime' ? '🔪 Vụ án & Kỳ bí' :
                                  niche === 'travel' ? '🌍 Du lịch & Phong cảnh' : 
                                  niche === 'Khác' ? '✨ Khác' : niche;
                if (!groups[nicheName]) groups[nicheName] = [];
                groups[nicheName].push(p);
              });
              
              return Object.entries(groups).map(([groupName, items]) => (
                <optgroup key={groupName} label={groupName}>
                  {items.map(p => (
                    <option key={p.id} value={p.id}>
                      {p.name.replace(/^[\u2700-\u27BF]|[\uE000-\uF8FF]|\uD83C[\uDC00-\uDFFF]|\uD83D[\uDC00-\uDFFF]|[\u2011-\u26FF]|\uD83E[\uDD10-\uDDFF]\s?/, '')} {p.is_default ? '(Mặc định)' : ''}
                    </option>
                  ))}
                </optgroup>
              ));
            })()}
          </select>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button 
            type="button" 
            className="btn btn-sm btn-outline-warning" 
            onClick={() => setShowSaveModal(true)}
            style={{ display: 'flex', alignItems: 'center', gap: 4 }}
          >
            <Save size={14} /> Lưu Preset hiện tại
          </button>

          {selectedPresetObj && !selectedPresetObj.is_default && (
            <button 
              type="button" 
              className="btn btn-sm btn-outline-danger" 
              onClick={handleDeletePreset}
              title="Xóa Preset này"
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>

      {showSaveModal && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px dashed rgba(255,255,255,0.1)', display: 'flex', gap: 8, alignItems: 'center' }}>
          <input 
            type="text" 
            className="form-input form-input-sm" 
            placeholder="Nhập tên Preset (VD: Shorts Game, Review Sách)..." 
            value={newPresetName} 
            onChange={e => setNewPresetName(e.target.value)}
            style={{ flex: 1 }}
          />
          <button 
            type="button" 
            className="btn btn-sm btn-primary" 
            onClick={handleSavePreset}
            disabled={loading}
          >
            {loading ? 'Đang lưu...' : 'Xác nhận Lưu'}
          </button>
          <button 
            type="button" 
            className="btn btn-sm btn-secondary" 
            onClick={() => setShowSaveModal(false)}
          >
            Hủy
          </button>
        </div>
      )}
    </div>
  );
}
