import React from 'react';
import { Smartphone, Monitor, Square, Play } from 'lucide-react';
import { useAppContext } from '../AppContext';
import { STYLES, VOICES, NARRATION_TONES, DURATION_OPTIONS } from '../constants';
import PresetManager from './PresetManager';

export default function ConfigSection() {
  const ctx = useAppContext();
  const minScenes = 4, maxScenes = 20;
  const sliderPercent = ((ctx.numScenes - minScenes) / (maxScenes - minScenes)) * 100;

  return (
    <div className="panel-box">
      <PresetManager />

      <div className="step-header">
        <div className="step-badge step-1">1</div>
        <span className="step-title">Cài đặt Cơ bản</span>
      </div>
      
      <div className="input-group">
        <label className="field-label">TỈ LỆ KHUNG HÌNH</label>
        <div className="ratio-group">
          {[
            { v: '9:16', icon: <Smartphone size={14} />, label: '9:16 Dọc' }, 
            { v: '16:9', icon: <Monitor size={14} />, label: '16:9 Ngang' }, 
            { v: '1:1', icon: <Square size={14} />, label: '1:1 Vuông' }
          ].map(r => (
            <button key={r.v} className={`ratio-btn ${ctx.ratio === r.v ? 'active' : ''}`} onClick={() => ctx.setRatio(r.v)}>
              {r.icon} {r.label}
            </button>
          ))}
        </div>
      </div>
      
      {!ctx.needsUpload && (
        <>
          <div className="input-group">
            <div className="slider-header">
              <label className="field-label" style={{ marginBottom: 0 }}>SỐ CẢNH:</label>
              <span className="slider-value">{ctx.numScenes}</span>
            </div>
            <div className="slider-container">
              <div className="slider-track-wrap">
                <input 
                  type="range" 
                  min={minScenes} 
                  max={maxScenes} 
                  value={ctx.numScenes} 
                  onChange={e => ctx.setNumScenes(Number(e.target.value))} 
                  className="range-input" 
                />
                <div className="slider-track-bg">
                  <div className="slider-track-fill" style={{ width: `${sliderPercent}%` }} />
                  <div className="slider-thumb" style={{ left: `${sliderPercent}%` }} />
                </div>
              </div>
            </div>
          </div>
          
          <div className="input-group">
            <label className="field-label">THỜI LƯỢNG DỰ KIẾN</label>
            <div className="ratio-group" style={{ flexWrap: 'wrap' }}>
              {DURATION_OPTIONS.map(d => (
                <button 
                  key={d.value} 
                  className={`ratio-btn ${ctx.targetDuration === d.value ? 'active' : ''}`}
                  onClick={() => { ctx.setTargetDuration(d.value); ctx.setNumScenes(d.scenes); }}
                >
                  {d.label}
                </button>
              ))}
            </div>
          </div>

          <div className="input-group">
            <label className="field-label">PHONG CÁCH KỂ CHUYỆN</label>
            <div className="ratio-group" style={{ flexWrap: 'wrap' }}>
              {NARRATION_TONES.map(t => (
                <button 
                  key={t.value}
                  className={`ratio-btn ${ctx.narrationTone === t.value ? 'active' : ''}`}
                  onClick={() => ctx.setNarrationTone(t.value)}
                  title={t.desc}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
        </>
      )}

      <div className="settings-grid">
        <div className="input-group">
          <label className="field-label">GIỌNG ĐỌC</label>
          <div style={{ display: 'flex', gap: 8 }}>
            <select className="form-select" value={ctx.voice} onChange={e => ctx.setVoice(e.target.value)} style={{ flex: 1 }}>
              {VOICES.map(v => <option key={v.value} value={v.value}>{v.label}</option>)}
            </select>
            <button className="btn-icon" onClick={() => ctx.playPreview('voice', ctx.voice)}><Play size={18} /></button>
          </div>
        </div>
        <div className="input-group">
          <label className="field-label">PHONG CÁCH ẢNH</label>
          <select className="form-select" value={ctx.style} onChange={e => ctx.setStyle(e.target.value)}>
            {STYLES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </div>
      </div>
      
      <div className="input-group">
        <label className="field-label">♬ NHẠC NỀN</label>
        <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
          <select className="form-select" value={ctx.bgm} onChange={e => ctx.setBgm(e.target.value)} style={{ flex: 1 }}>
            <option value="auto">✨ Tự động chọn bằng AI</option>
            <option value="none">Không dùng nhạc nền</option>
            <option value="afro_pop">Afro Pop</option>
            <option value="black_light_all_good_folks_main">Black Light (All Good Folks)</option>
            <option value="comedy_cartoon">Comedy Cartoon</option>
            <option value="deep_abstract_ambient">Deep Abstract Ambient</option>
            <option value="fluffy_clouds_fugu_vibes_main_version">Fluffy Clouds (Fugu Vibes)</option>
            <option value="hype_drill">Hype Drill</option>
            <option value="lofi_jazzy_love">Lo-Fi Jazzy Love</option>
            <option value="moment_of_peace">Moment Of Peace</option>
            <option value="music_promotion">Music Promotion</option>
            <option value="new_age_nature">New Age Nature</option>
            <option value="no_sleep_hiphop">No Sleep Hip-Hop</option>
            <option value="rap_beat">Rap Beat</option>
            <option value="running_night">Running Night</option>
            <option value="type_beat">Type Beat</option>
          </select>
          {ctx.bgm !== 'none' && <button className="btn-icon" onClick={() => ctx.playPreview('bgm', ctx.bgm)}><Play size={18} /></button>}
          {ctx.bgm !== 'none' && <input type="range" className="vol-slider" min="0" max="100" value={ctx.bgmVolume} onChange={e => ctx.setBgmVolume(Number(e.target.value))} style={{ width: 80 }} />}
        </div>
      </div>
    </div>
  );
}
