import React, { useState, useEffect } from 'react';
import { Bookmark, Save, Trash2 } from 'lucide-react';
import { useShallow } from 'zustand/react/shallow';
import { useAppStore } from '../store';
import { API_BASE } from '../constants';

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
      console.error("Failed to fetch presets:", e);
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
    if (!newPresetName.trim()) return alert("Vui lòng nhập tên cho Preset!");
    setLoading(true);
    try {
      const payload = {
        name: newPresetName.trim(),
        aspect_ratio: ctx.ratio,
        voice: ctx.voice,
        art_style: ctx.style,
        bgm_track: ctx.bgm === 'none' ? null : ctx.bgm,
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
        sfx_volume: 8,
        use_ken_burns: ctx.useKenBurns,
        hook_zoom_boost: ctx.hookZoomBoost,
        use_breathing: ctx.useBreathing,
        use_frame_chaining: ctx.useFrameChaining,
        use_beat_sync: ctx.useBeatSync,
        hook_effect: ctx.hookEffect
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
        alert("Lỗi khi lưu Preset!");
      }
    } catch (e) {
      alert("Lỗi kết nối: " + e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDeletePreset = async () => {
    if (!selectedPresetId) return;
    const found = presets.find(p => p.id === selectedPresetId);
    if (!found || found.is_default) {
      return alert("Không thể xóa Preset mặc định!");
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
        alert("Lỗi khi xóa Preset!");
      }
    } catch (e) {
      alert("Lỗi kết nối: " + e.message);
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
            {presets.map(p => (
              <option key={p.id} value={p.id}>
                {p.name} {p.is_default ? '(Mặc định)' : ''}
              </option>
            ))}
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
