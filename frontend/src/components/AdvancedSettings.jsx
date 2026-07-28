import React, { useState } from 'react';
import { Play, ChevronDown, ChevronRight } from 'lucide-react';
import { useShallow } from 'zustand/react/shallow';
import { useAppStore } from '../store';
import { SUBTITLE_STYLES, COLOR_GRADINGS, VISUAL_SOURCES, HOOK_SFX_OPTIONS } from '../constants';

const SectionHeader = ({ title, isOpen, onToggle }) => (
  <div 
    style={{ 
      gridColumn: '1 / -1', 
      background: 'rgba(255, 255, 255, 0.03)', 
      border: '1px solid rgba(255, 255, 255, 0.05)',
      borderRadius: '8px',
      padding: '10px 14px', 
      color: '#e2e8f0', 
      fontSize: 12, 
      fontWeight: 'bold', 
      letterSpacing: 0.5, 
      marginTop: 8, 
      cursor: 'pointer', 
      display: 'flex', 
      alignItems: 'center',
      transition: 'background 0.2s',
      userSelect: 'none'
    }}
    onClick={onToggle}
    onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255, 255, 255, 0.08)'}
    onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(255, 255, 255, 0.03)'}
  >
    {isOpen ? <ChevronDown size={16} style={{ marginRight: 8, color: '#a855f7' }} /> : <ChevronRight size={16} style={{ marginRight: 8, color: '#a855f7' }} />}
    {title}
  </div>
);

export default function AdvancedSettings() {
  const ctx = useAppStore(useShallow((s) => ({
    useVeo: s.useVeo, setUseVeo: s.setUseVeo,
    useFrameChaining: s.useFrameChaining, setUseFrameChaining: s.setUseFrameChaining,
    useBeatSync: s.useBeatSync, setUseBeatSync: s.setUseBeatSync,
    useKenBurns: s.useKenBurns, setUseKenBurns: s.setUseKenBurns,
    useSfx: s.useSfx, setUseSfx: s.setUseSfx,
    useSinglePassNarration: s.useSinglePassNarration, setUseSinglePassNarration: s.setUseSinglePassNarration,
    useBreathing: s.useBreathing, setUseBreathing: s.setUseBreathing,
    hookZoomBoost: s.hookZoomBoost, setHookZoomBoost: s.setHookZoomBoost,
    hookEffect: s.hookEffect, setHookEffect: s.setHookEffect,
    hookReelSfx: s.hookReelSfx, setHookReelSfx: s.setHookReelSfx,
    hookText: s.hookText, setHookText: s.setHookText,
    hookQuote: s.hookQuote, setHookQuote: s.setHookQuote,
    visualSource: s.visualSource, setVisualSource: s.setVisualSource,
    colorGrading: s.colorGrading, setColorGrading: s.setColorGrading,
    subtitleStyle: s.subtitleStyle, setSubtitleStyle: s.setSubtitleStyle,
    speechRate: s.speechRate, setSpeechRate: s.setSpeechRate,
    speechPitch: s.speechPitch, setSpeechPitch: s.setSpeechPitch,
    sfxVolume: s.sfxVolume, setSfxVolume: s.setSfxVolume,
    hookSfxVolume: s.hookSfxVolume, setHookSfxVolume: s.setHookSfxVolume,
    watermarkText: s.watermarkText, setWatermarkText: s.setWatermarkText,
    introBgm: s.introBgm, setIntroBgm: s.setIntroBgm,
    introBgmDuration: s.introBgmDuration, setIntroBgmDuration: s.setIntroBgmDuration,
    // Outro + Ducking: THIẾU những dòng này thì ctx.setOutroEffect là undefined và bấm
    // vào dropdown ném TypeError, còn nút Ducking thành uncontrolled — bật/tắt không có
    // tác dụng gì. Cùng loại lỗi với hookSfxVolume; tests/test_frontend_store_contract.py
    // đối chiếu selector với mọi khoá được đọc trong file này nên quên là test đỏ ngay.
    useAudioDucking: s.useAudioDucking, setUseAudioDucking: s.setUseAudioDucking,
    outroEffect: s.outroEffect, setOutroEffect: s.setOutroEffect,
    outroText: s.outroText, setOutroText: s.setOutroText,
    outroReelSfx: s.outroReelSfx, setOutroReelSfx: s.setOutroReelSfx,
    outroSfxVolume: s.outroSfxVolume, setOutroSfxVolume: s.setOutroSfxVolume,
    playPreview: s.playPreview,
  })));

  const [openImage, setOpenImage] = useState(true);
  const [openVoice, setOpenVoice] = useState(true);
  const [openHook, setOpenHook] = useState(true);
  const [openOutro, setOpenOutro] = useState(true);



  const BGMOptions = (
    <>
      <optgroup label="🧘‍♀️ Thiền định & Chữa lành (Ambient)">
        <option value="moment_of_peace">Moment Of Peace</option>
        <option value="new_age_nature">New Age Nature</option>
        <option value="deep_abstract_ambient">Deep Abstract Ambient</option>
      </optgroup>

      <optgroup label="🕵️‍♂️ Kịch tính & Huyền bí (Cinematic)">
        <option value="ghost_piano_yeti_music_main_version">Ghost Piano (Yeti Music)</option>
        <option value="black_light_all_good_folks_main">Black Light (All Good Folks)</option>
        <option value="running_night">Running Night</option>
      </optgroup>

      <optgroup label="☕ Thư giãn & Kể chuyện (Chill & Lo-Fi)">
        <option value="fluffy_clouds_fugu_vibes_main_version">Fluffy Clouds (Fugu Vibes)</option>
        <option value="lofi_jazzy_love">Lo-Fi Jazzy Love</option>
        <option value="livin_easy_oliver_massa_main">Livin Easy (Oliver Massa)</option>
        <option value="Back_When">Back When</option>
      </optgroup>

      <optgroup label="🎉 Năng động & Tích cực (Upbeat)">
        <option value="let_good_times_roll_ra_main_version">Let Good Times Roll</option>
        <option value="afro_pop">Afro Pop</option>
        <option value="music_promotion">Music Promotion</option>
      </optgroup>

      <optgroup label="🎧 Hip-hop & Đường phố (Rap/Trap)">
        <option value="hype_drill">Hype Drill</option>
        <option value="no_sleep_hiphop">No Sleep Hip-Hop</option>
        <option value="rap_beat">Rap Beat</option>
        <option value="type_beat">Type Beat</option>
      </optgroup>

      <optgroup label="🤡 Vui nhộn (Funny)">
        <option value="comedy_cartoon">Comedy Cartoon</option>
      </optgroup>
    </>
  );

  // Helper component for Toggle Switch
  const ToggleRow = ({ label, checked, onChange, tooltip }) => (
    <div className="toggle-row" title={tooltip}>
      <span className="toggle-label">{label}</span>
      <label className="switch">
        <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} />
        <span className="slider round"></span>
      </label>
    </div>
  );

  return (
    <div className="advanced-box">
      <div className="advanced-title">⚡ Tùy chọn nâng cao</div>
      
      <div className="toggles-grid">
        <ToggleRow 
          label={<span>Dùng <b>Veo 3</b> biến ảnh → video clip động</span>} 
          checked={ctx.useVeo} 
          onChange={ctx.setUseVeo} 
          tooltip="Sử dụng Google Veo 3.1 để tạo chuyển động từ ảnh tĩnh (tốn thêm thời gian render)"
        />
        <ToggleRow 
          label="Nối cảnh mượt (Frame Chaining)" 
          checked={ctx.useFrameChaining} 
          onChange={ctx.setUseFrameChaining} 
          tooltip="Ghép nối khung hình đầu cuối giữa các cảnh để chuyển cảnh siêu mượt"
        />
        <ToggleRow 
          label="Đồng bộ theo nhịp nhạc (Beat Sync)" 
          checked={ctx.useBeatSync} 
          onChange={ctx.setUseBeatSync} 
          tooltip="Chuyển cảnh hoặc giật zoom tự động khớp với điểm nhấn của nhạc nền"
        />
        <ToggleRow 
          label="Hiệu ứng Ken Burns (Ảnh tĩnh)" 
          checked={ctx.useKenBurns} 
          onChange={ctx.setUseKenBurns} 
          tooltip="Tự động zoom/pan nhẹ trên ảnh tĩnh nếu không dùng Veo"
        />
        <ToggleRow
          label="Tiếng động phụ hoạ (SFX các cảnh)"
          checked={ctx.useSfx}
          onChange={ctx.setUseSfx}
          tooltip="Cho phép phát các hiệu ứng âm thanh (SFX) mà bạn đã cấu hình riêng cho từng cảnh ở bước Kịch bản. Nếu tắt, toàn bộ SFX chuyển cảnh sẽ bị loại bỏ."
        />
        <ToggleRow
          label="Tự động giảm nhạc nền khi đọc (Audio Ducking)"
          checked={ctx.useAudioDucking}
          onChange={ctx.setUseAudioDucking}
          tooltip="Tự động giảm âm lượng nhạc nền (BGM) xuống nhỏ hơn khi có giọng đọc (để làm rõ lời thoại), và tăng lại khi có khoảng lặng."
        />
        <ToggleRow
          label={<span>🎙️ Đọc <b>liền mạch cả bài</b> (1 lần gọi)</span>}
          checked={ctx.useSinglePassNarration}
          onChange={ctx.setUseSinglePassNarration}
          tooltip="Đọc toàn bộ kịch bản trong MỘT lần gọi thay vì từng cảnh riêng lẻ: ngữ điệu, cao độ và nhịp thở liên tục suốt video, không còn 'vào giọng' lại ở mỗi cảnh. Mốc cắt cảnh sẽ tự bám theo giọng đọc. ĐÁNH ĐỔI: bỏ qua cảm xúc và tốc độ đọc riêng mà AI gán cho từng cảnh. Không dùng được với giọng Minion / OmniVoice."
        />
        <ToggleRow
          label="Lấy hơi tự nhiên (Breathing)"
          checked={ctx.useBreathing}
          onChange={ctx.setUseBreathing}
          tooltip="Tự động chèn tiếng lấy hơi (breathing) vào các khoảng nghỉ để nghe như người thật"
        />
        <ToggleRow
          label={<span>Cú đấm mở màn (<b>Hook Zoom Boost</b>)</span>}
          checked={ctx.hookZoomBoost}
          onChange={ctx.setHookZoomBoost}
          tooltip="Cảnh đầu zoom mạnh (1.0→1.35) + tự thêm tiếng Riser dâng trào để giữ chân người xem trong 3 giây đầu"
        />
      </div>

      <div className="advanced-inputs-grid" style={{ marginTop: 20 }}>
        
        {/* --- SECTION: HÌNH ẢNH & THỊ GIÁC --- */}
        <SectionHeader title="HÌNH ẢNH & THỊ GIÁC" isOpen={openImage} onToggle={() => setOpenImage(!openImage)} />
        {openImage && (<>
        <div className="input-group">
          <label className="field-label">NGUỒN HÌNH ẢNH</label>
          <select
            className="form-select form-select-sm"
            value={ctx.visualSource}
            onChange={e => ctx.setVisualSource(e.target.value)}
            title="Quyết định mỗi cảnh dùng ảnh AI hay video thật tải từ Pexels. 'Xen kẽ thông minh' để cảnh trầm/kết dùng video thật, cảnh hook/cao trào dùng ảnh AI (giữ quyền kiểm soát bố cục). Cảnh nào không tìm được video stock sẽ tự rơi về ảnh AI."
          >
            {VISUAL_SOURCES.map(vs => (
              <option key={vs.value} value={vs.value}>{vs.label}</option>
            ))}
          </select>
        </div>
        
        <div className="input-group">
          <label className="field-label">BỘ LỌC MÀU (COLOR GRADING)</label>
          <select className="form-select form-select-sm" value={ctx.colorGrading} onChange={e => ctx.setColorGrading(e.target.value)}>
            {COLOR_GRADINGS.map(cg => (
              <option key={cg.value} value={cg.value}>{cg.label}</option>
            ))}
          </select>
        </div>
        
        <div className="input-group">
          <label className="field-label">KIỂU PHỤ ĐỀ</label>
          <select className="form-select form-select-sm" value={ctx.subtitleStyle} onChange={e => ctx.setSubtitleStyle(e.target.value)}>
            {SUBTITLE_STYLES.map(style => (
              <option key={style.value} value={style.value}>{style.label}</option>
            ))}
          </select>
        </div>

        <div className="input-group">
          <label className="field-label">ĐÓNG DẤU (WATERMARK)</label>
          <input 
            type="text" 
            className="form-input form-input-sm" 
            value={ctx.watermarkText} 
            onChange={e => ctx.setWatermarkText(e.target.value)} 
            placeholder="VD: @username" 
          />
        </div>

        </>)}

        {/* --- SECTION: GIỌNG ĐỌC & SFX CƠ BẢN --- */}
        <SectionHeader title="GIỌNG ĐỌC & SFX CƠ BẢN" isOpen={openVoice} onToggle={() => setOpenVoice(!openVoice)} />
        {openVoice && (<>
        <div className="input-group">
          <label className="field-label">TỐC ĐỘ ĐỌC (EDGE-TTS / OMNIVOICE)</label>
          <select className="form-select form-select-sm" value={ctx.speechRate} onChange={e => ctx.setSpeechRate(e.target.value)}>
            <option value="-20%">Rất chậm (-20%)</option>
            <option value="-15%">Chậm thong thả (-15%)</option>
            <option value="-10%">Chậm vừa (-10%)</option>
            <option value="+0%">Bình thường (0%)</option>
            <option value="+10%">Nhanh (+10%)</option>
            <option value="+15%">Rất nhanh (+15%)</option>
            <option value="+20%">Siêu dồn dập (+20%)</option>
          </select>
        </div>

        <div className="input-group">
          <label className="field-label">ĐỘ CAO GIỌNG (PITCH)</label>
          <select className="form-select form-select-sm" value={ctx.speechPitch} onChange={e => ctx.setSpeechPitch(e.target.value)}>
            <option value="+5Hz">Cao (+5Hz)</option>
            <option value="+0Hz">Bình thường (0Hz)</option>
            <option value="-5Hz">Trầm hơn (-5Hz)</option>
            <option value="-10Hz">Rất trầm (-10Hz)</option>
          </select>
        </div>

        <div className="input-group" style={{ gridColumn: '1 / -1' }}>
          <label className="field-label">ÂM LƯỢNG SFX TỪNG CẢNH ({ctx.sfxVolume}%)</label>
          <input 
            type="range" 
            min="0" 
            max="100" 
            step="5"
            className="form-range" 
            value={ctx.sfxVolume} 
            onChange={e => ctx.setSfxVolume(Number(e.target.value))} 
            disabled={!ctx.useSfx}
          />
        </div>

        </>)}

        {/* --- SECTION: MỞ ĐẦU VIDEO (INTRO & HOOK) --- */}
        <SectionHeader title="MỞ ĐẦU VIDEO (INTRO & HOOK)" isOpen={openHook} onToggle={() => setOpenHook(!openHook)} />
        {openHook && (<>
        <div className="input-group" style={{ gridColumn: '1 / -1' }}>
          <label className="field-label">♬ NHẠC MỞ ĐẦU (INTRO BGM - Tùy chọn)</label>
          <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
            <select className="form-select form-select-sm" value={ctx.introBgm} onChange={e => ctx.setIntroBgm(e.target.value)} style={{ flex: 1 }}>
              <option value="none">Không dùng nhạc mở đầu riêng</option>
              {BGMOptions}
            </select>
            {ctx.introBgm !== 'none' && (
              <select className="form-select form-select-sm" value={ctx.introBgmDuration} onChange={e => ctx.setIntroBgmDuration(Number(e.target.value))} style={{ width: 120 }}>
                <option value={0}>Hết cảnh 1</option>
                <option value={3}>3 giây</option>
                <option value={5}>5 giây</option>
                <option value={10}>10 giây</option>
              </select>
            )}
            {ctx.introBgm !== 'none' && (
              <button className="btn-icon" onClick={() => ctx.playPreview('bgm', ctx.introBgm)} title="Nghe thử Intro BGM">
                <Play size={18} />
              </button>
            )}
          </div>
        </div>

        <div className="input-group">
          <label className="field-label">HIỆU ỨNG HOOK ĐẦU VIDEO</label>
          <select className="form-select form-select-sm" value={ctx.hookEffect} onChange={e => ctx.setHookEffect(e.target.value)}>
            <option value="carousel_quote">🎰 Slot Machine & Bìa sách</option>
            <option value="blackout_question">⬛ Màn đen câu hỏi (A1 Blackout)</option>
            <option value="typewriter_quote">⌨️ Gõ chữ (A2 Typewriter)</option>
            <option value="breathing_vignette">🕯️ Thu phóng mờ (C3 Vignette)</option>
            <option value="camera_shutter">📸 Nháy máy ảnh (Camera Shutter)</option>
            <option value="cyber_glitch">⚡ Nhiễu sóng (Cyber Glitch)</option>
            <option value="vintage_film_burn">🎞️ Cháy phim (Vintage Film Burn)</option>
            <option value="none">🚫 Không dùng Hook</option>
          </select>
        </div>

        <div className="input-group" style={{ opacity: ctx.hookEffect !== 'none' ? 1 : 0.4, pointerEvents: ctx.hookEffect !== 'none' ? 'auto' : 'none' }}>
          <label className="field-label">ÂM THANH HIỆU ỨNG (HOOK SFX)</label>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', width: '100%' }}>
            <select
              className="form-select form-select-sm"
              value={ctx.hookReelSfx}
              onChange={e => ctx.setHookReelSfx(e.target.value)}
              style={{ flex: 1, minWidth: 0 }}
            >
              {(HOOK_SFX_OPTIONS[ctx.hookEffect] || []).map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4, width: 80, flexShrink: 0 }}>
              <span style={{ fontSize: 10, color: 'gray' }}>Vol</span>
              <input
                type="range"
                className="vol-slider"
                min="0"
                max="200"
                value={ctx.hookSfxVolume}
                onChange={e => ctx.setHookSfxVolume(Number(e.target.value))}
                style={{ flex: 1, minWidth: 0 }}
                title={`Âm lượng Hook SFX: ${ctx.hookSfxVolume}% (200% là cực đại)`}
              />
            </div>
            <button className="btn-icon" onClick={() => ctx.playPreview('hook_sfx', ctx.hookReelSfx)} title="Nghe thử âm thanh này" disabled={ctx.hookEffect === 'none' || !ctx.hookReelSfx}>
              <Play size={18} />
            </button>
          </div>
        </div>

        <div className="input-group">
          <label className="field-label">TIÊU ĐỀ HOOK CHỮ (MÀN ĐEN / GÕ CHỮ)</label>
          <input
            type="text"
            className="form-input form-input-sm"
            value={ctx.hookText}
            onChange={e => ctx.setHookText(e.target.value)}
            placeholder="VD: BÍ MẬT ĐỘNG TRỜI VỀ ROCKEFELLER!..."
          />
        </div>

        <div className="input-group">
          <label className="field-label">TRÍCH DẪN HOOK BÌA SÁCH (Quote - Áp dụng Carousel)</label>
          <input 
            type="text" 
            className="form-input form-input-sm" 
            value={ctx.hookQuote} 
            onChange={e => ctx.setHookQuote(e.target.value)} 
            placeholder="VD: GIÁ TRỊ NẰM Ở SỰ LỰA CHỌN..." 
          />
        </div>

        </>)}

        {/* --- SECTION: KẾT THÚC VIDEO (OUTRO) --- */}
        <SectionHeader title="KẾT THÚC VIDEO (OUTRO)" isOpen={openOutro} onToggle={() => setOpenOutro(!openOutro)} />
        {openOutro && (<>
        <div className="input-group">
          <label className="field-label">HIỆU ỨNG OUTRO KẾT THÚC</label>
          <select className="form-select form-select-sm" value={ctx.outroEffect} onChange={e => ctx.setOutroEffect(e.target.value)}>
            <option value="none">🚫 Không dùng Outro</option>
            <option value="carousel_quote">🎰 Slot Machine & Bìa sách</option>
            <option value="blackout_question">⬛ Màn đen (Blackout)</option>
            <option value="typewriter_quote">⌨️ Gõ chữ (Typewriter)</option>
            <option value="breathing_vignette">🕯️ Thu phóng mờ (Vignette)</option>
            <option value="camera_shutter">📸 Nháy máy ảnh (Camera Shutter)</option>
            <option value="cyber_glitch">⚡ Nhiễu sóng (Cyber Glitch)</option>
            <option value="vintage_film_burn">🎞️ Cháy phim (Vintage Film Burn)</option>
          </select>
        </div>

        <div className="input-group" style={{ opacity: ctx.outroEffect !== 'none' ? 1 : 0.4, pointerEvents: ctx.outroEffect !== 'none' ? 'auto' : 'none' }}>
          <label className="field-label">ÂM THANH OUTRO (OUTRO SFX)</label>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', width: '100%' }}>
            <select
              className="form-select form-select-sm"
              value={ctx.outroReelSfx}
              onChange={e => ctx.setOutroReelSfx(e.target.value)}
              style={{ flex: 1, minWidth: 0 }}
            >
              {(HOOK_SFX_OPTIONS[ctx.outroEffect] || []).map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4, width: 80, flexShrink: 0 }}>
              <span style={{ fontSize: 10, color: 'gray' }}>Vol</span>
              <input
                type="range"
                className="vol-slider"
                min="0"
                max="200"
                value={ctx.outroSfxVolume}
                onChange={e => ctx.setOutroSfxVolume(Number(e.target.value))}
                style={{ flex: 1, minWidth: 0 }}
                title={`Âm lượng Outro SFX: ${ctx.outroSfxVolume}%`}
              />
            </div>
            <button className="btn-icon" onClick={() => ctx.playPreview('hook_sfx', ctx.outroReelSfx)} title="Nghe thử âm thanh này" disabled={ctx.outroEffect === 'none' || !ctx.outroReelSfx}>
              <Play size={18} />
            </button>
          </div>
        </div>
        <div className="input-group">
          <label className="field-label">TIÊU ĐỀ/CHỮ OUTRO</label>
          <input 
            type="text" 
            className="form-input form-input-sm" 
            value={ctx.outroText || ""} 
            onChange={e => ctx.setOutroText(e.target.value)} 
            placeholder="Nhập câu kết..." 
          />
        </div>
        </>)}
      </div>
    </div>
  );
}
