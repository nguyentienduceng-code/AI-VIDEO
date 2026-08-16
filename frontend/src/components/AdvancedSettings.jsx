import React, { useState, useEffect } from 'react';
import { Play, ChevronDown, ChevronRight } from 'lucide-react';
import { useShallow } from 'zustand/react/shallow';
import { useAppStore } from '../store';
import { SUBTITLE_STYLES, COLOR_GRADINGS, VISUAL_SOURCES, HOOK_SFX_OPTIONS, OUTRO_ONLY_EFFECTS, API_BASE } from '../constants';

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
    usePatternInterrupt: s.usePatternInterrupt, setUsePatternInterrupt: s.setUsePatternInterrupt,
    autoRetryLowQuality: s.autoRetryLowQuality, setAutoRetryLowQuality: s.setAutoRetryLowQuality,
    hookEffect: s.hookEffect, setHookEffect: s.setHookEffect,
    hookReelSfx: s.hookReelSfx, setHookReelSfx: s.setHookReelSfx,
    hookText: s.hookText, setHookText: s.setHookText,
    hookQuote: s.hookQuote, setHookQuote: s.setHookQuote,
    visualSource: s.visualSource, setVisualSource: s.setVisualSource,
    preferStockVideo: s.preferStockVideo, setPreferStockVideo: s.setPreferStockVideo,
    colorGrading: s.colorGrading, setColorGrading: s.setColorGrading,
    subtitleStyle: s.subtitleStyle, setSubtitleStyle: s.setSubtitleStyle,
    speechRate: s.speechRate, setSpeechRate: s.setSpeechRate,
    speechPitch: s.speechPitch, setSpeechPitch: s.setSpeechPitch,
    sfxVolume: s.sfxVolume, setSfxVolume: s.setSfxVolume,
    hookSfxVolume: s.hookSfxVolume, setHookSfxVolume: s.setHookSfxVolume,
    watermarkText: s.watermarkText, setWatermarkText: s.setWatermarkText,
    watermarkLogo: s.watermarkLogo, setWatermarkLogo: s.setWatermarkLogo,
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

  const [bgmGroups, setBgmGroups] = useState({
    "🧘‍♀️ Thiền định & Chữa lành (Ambient)": [],
    "🕵️‍♂️ Kịch tính & Huyền bí (Cinematic)": [],
    "☕ Thư giãn & Kể chuyện (Chill & Lo-Fi)": [],
    "🎉 Năng động & Tích cực (Upbeat)": [],
    "🎧 Hip-hop & Đường phố (Rap/Trap)": [],
    "🤡 Vui nhộn (Funny)": [],
    "📁 Khác (Nhạc chưa phân loại)": []
  });
  useEffect(() => {
    fetch(`${API_BASE}/api/bgm-list`)
      .then(r => r.json())
      .then(d => {
        const groups = {
          "🧘‍♀️ Thiền định & Chữa lành (Ambient)": [],
          "🕵️‍♂️ Kịch tính & Huyền bí (Cinematic)": [],
          "☕ Thư giãn & Kể chuyện (Chill & Lo-Fi)": [],
          "🎉 Năng động & Tích cực (Upbeat)": [],
          "🎧 Hip-hop & Đường phố (Rap/Trap)": [],
          "🤡 Vui nhộn (Funny)": [],
          "📁 Khác (Nhạc chưa phân loại)": []
        };
        const hardcoded = {
          "moment_of_peace": "🧘‍♀️ Thiền định & Chữa lành (Ambient)",
          "new_age_nature": "🧘‍♀️ Thiền định & Chữa lành (Ambient)",
          "deep_abstract_ambient": "🧘‍♀️ Thiền định & Chữa lành (Ambient)",
          "ghost_piano_yeti_music_main_version": "🕵️‍♂️ Kịch tính & Huyền bí (Cinematic)",
          "black_light_all_good_folks_main": "🕵️‍♂️ Kịch tính & Huyền bí (Cinematic)",
          "running_night": "🕵️‍♂️ Kịch tính & Huyền bí (Cinematic)",
          "fluffy_clouds_fugu_vibes_main_version": "☕ Thư giãn & Kể chuyện (Chill & Lo-Fi)",
          "lofi_jazzy_love": "☕ Thư giãn & Kể chuyện (Chill & Lo-Fi)",
          "livin_easy_oliver_massa_main": "☕ Thư giãn & Kể chuyện (Chill & Lo-Fi)",
          "Back_When": "☕ Thư giãn & Kể chuyện (Chill & Lo-Fi)",
          "let_good_times_roll_ra_main_version": "🎉 Năng động & Tích cực (Upbeat)",
          "afro_pop": "🎉 Năng động & Tích cực (Upbeat)",
          "music_promotion": "🎉 Năng động & Tích cực (Upbeat)",
          "hype_drill": "🎧 Hip-hop & Đường phố (Rap/Trap)",
          "no_sleep_hiphop": "🎧 Hip-hop & Đường phố (Rap/Trap)",
          "rap_beat": "🎧 Hip-hop & Đường phố (Rap/Trap)",
          "type_beat": "🎧 Hip-hop & Đường phố (Rap/Trap)",
          "comedy_cartoon": "🤡 Vui nhộn (Funny)"
        };
        (d.tracks || []).forEach(t => {
           const id = t.id.replace(/\.[^/.]+$/, "");
           let group = "📁 Khác (Nhạc chưa phân loại)";
           if (hardcoded[id]) {
             group = hardcoded[id];
           } else {
             const lowerId = id.toLowerCase();
             if (lowerId.match(/ambient|chant|peace|nature|smooth|calm/)) group = "🧘‍♀️ Thiền định & Chữa lành (Ambient)";
             else if (lowerId.match(/cinematic|epic|ghost|dark|suspens/)) group = "🕵️‍♂️ Kịch tính & Huyền bí (Cinematic)";
             else if (lowerId.match(/chill|lofi|lo.fi|acoustic|sad|relax/)) group = "☕ Thư giãn & Kể chuyện (Chill & Lo-Fi)";
             else if (lowerId.match(/funny|comedy|cartoon/)) group = "🤡 Vui nhộn (Funny)";
             else if (lowerId.match(/upbeat|pop|bass|happy|energetic/)) group = "🎉 Năng động & Tích cực (Upbeat)";
             else if (lowerId.match(/rap|hip.*hop|trap|drill|beat/)) group = "🎧 Hip-hop & Đường phố (Rap/Trap)";
           }
           groups[group].push({ value: id, label: t.name });
        });
        setBgmGroups(groups);
      }).catch(() => {});
  }, []);

  const [openOutro, setOpenOutro] = useState(true);
  const [openSystem, setOpenSystem] = useState(true);

  const BGMOptions = (
    <>
      {Object.entries(bgmGroups).map(([label, tracks]) => {
        if (tracks.length === 0) return null;
        return (
          <optgroup key={label} label={label}>
            {tracks.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
          </optgroup>
        );
      })}
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
      
      <div className="advanced-inputs-grid" style={{ marginTop: 20 }}>
        
        {/* --- SECTION: HÌNH ẢNH & THỊ GIÁC --- */}
        <SectionHeader title="HÌNH ẢNH & THỊ GIÁC" isOpen={openImage} onToggle={() => setOpenImage(!openImage)} />
        <div className={`accordion-wrapper ${openImage ? 'open' : ''}`}>
          <div className="accordion-inner">
        <div className="toggles-grid" style={{ marginBottom: 15, gridColumn: '1 / -1' }}>
          <ToggleRow label={<span>Dùng <b>Veo 3</b> biến ảnh → video clip động</span>} checked={ctx.useVeo} onChange={ctx.setUseVeo} tooltip="Sử dụng Google Veo 3.1 để tạo chuyển động từ ảnh tĩnh (tốn thêm thời gian render)" />
          <ToggleRow label="Nối cảnh mượt (Frame Chaining)" checked={ctx.useFrameChaining} onChange={ctx.setUseFrameChaining} tooltip="Ghép nối khung hình đầu cuối giữa các cảnh để chuyển cảnh siêu mượt" />
          <ToggleRow label="Hiệu ứng Ken Burns (Ảnh tĩnh)" checked={ctx.useKenBurns} onChange={ctx.setUseKenBurns} tooltip="Tự động zoom/pan nhẹ trên ảnh tĩnh nếu không dùng Veo" />
        </div>
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
          {/* `prefer_stock_video` KHÔNG có công tắc riêng trên giao diện — chỉ preset bật
              được nó (2 preset mặc định: Review sách, Du lịch). Nên trước đây người dùng nạp
              preset là toàn bộ video chuyển sang footage tải về mà không có dấu hiệu nào, và
              cũng KHÔNG có cách nào tắt ngoài việc nạp preset khác. Dòng dưới hiện ra đúng
              lúc đó, kèm nút tắt. */}
          {ctx.preferStockVideo && ctx.visualSource === 'auto' && (
            <span style={{ fontSize: 11, color: '#f59e0b', marginTop: 4, display: 'block', lineHeight: 1.5 }}>
              ⚠️ Preset đang bật <b>ưu tiên video thật</b>, nên "Tự động" = video Pexels cho mọi cảnh.{' '}
              <button
                type="button"
                onClick={() => ctx.setPreferStockVideo(false)}
                style={{ background: 'none', border: 'none', padding: 0, color: '#3b82f6', cursor: 'pointer', fontSize: 11, textDecoration: 'underline' }}
              >
                Tắt để dùng ảnh AI
              </button>
            </span>
          )}
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
          <label className="toggle-label" style={{ marginTop: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <input 
              type="checkbox" 
              checked={ctx.watermarkLogo} 
              onChange={e => ctx.setWatermarkLogo(e.target.checked)} 
            />
            <span style={{ fontSize: '0.9rem' }}>Chèn Logo NTD (Ảnh NTD Logo)</span>
          </label>
        </div>

        </div>
        </div>

        {/* --- SECTION: GIỌNG ĐỌC & SFX CƠ BẢN --- */}
        <SectionHeader title="GIỌNG ĐỌC & SFX CƠ BẢN" isOpen={openVoice} onToggle={() => setOpenVoice(!openVoice)} />
        <div className={`accordion-wrapper ${openVoice ? 'open' : ''}`}>
          <div className="accordion-inner">
        <div className="toggles-grid" style={{ marginBottom: 15, gridColumn: '1 / -1' }}>
          <ToggleRow label={<span>🎙️ Đọc <b>liền mạch cả bài</b> (1 lần gọi)</span>} checked={ctx.useSinglePassNarration} onChange={ctx.setUseSinglePassNarration} tooltip="Đọc toàn bộ kịch bản trong MỘT lần gọi thay vì từng cảnh riêng lẻ: ngữ điệu, cao độ và nhịp thở liên tục suốt video, không còn 'vào giọng' lại ở mỗi cảnh. Mốc cắt cảnh sẽ tự bám theo giọng đọc. ĐÁNH ĐỔI: bỏ qua cảm xúc và tốc độ đọc riêng mà AI gán cho từng cảnh. Không dùng được với giọng Minion / OmniVoice." />
          <ToggleRow label="Lấy hơi tự nhiên (Breathing)" checked={ctx.useBreathing} onChange={ctx.setUseBreathing} tooltip="Tự động chèn tiếng lấy hơi (breathing) vào các khoảng nghỉ để nghe như người thật" />
          <ToggleRow label="Tiếng động phụ hoạ (SFX các cảnh)" checked={ctx.useSfx} onChange={ctx.setUseSfx} tooltip="Cho phép phát các hiệu ứng âm thanh (SFX) mà bạn đã cấu hình riêng cho từng cảnh ở bước Kịch bản. Nếu tắt, toàn bộ SFX chuyển cảnh sẽ bị loại bỏ." />
          <ToggleRow label="Đồng bộ theo nhịp nhạc (Beat Sync)" checked={ctx.useBeatSync} onChange={ctx.setUseBeatSync} tooltip="Chuyển cảnh hoặc giật zoom tự động khớp với điểm nhấn của nhạc nền" />
          <ToggleRow label="Tự động giảm nhạc nền khi đọc (Audio Ducking)" checked={ctx.useAudioDucking} onChange={ctx.setUseAudioDucking} tooltip="Tự động giảm âm lượng nhạc nền (BGM) xuống nhỏ hơn khi có giọng đọc (để làm rõ lời thoại), và tăng lại khi có khoảng lặng." />
        </div>
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

        </div>
        </div>

        {/* --- SECTION: MỞ ĐẦU VIDEO (INTRO & HOOK) --- */}
        <SectionHeader title="MỞ ĐẦU VIDEO (INTRO & HOOK)" isOpen={openHook} onToggle={() => setOpenHook(!openHook)} />
        <div className={`accordion-wrapper ${openHook ? 'open' : ''}`}>
          <div className="accordion-inner">
        <div className="toggles-grid" style={{ marginBottom: 15, gridColumn: '1 / -1' }}>
          <ToggleRow label={<span>Cú đấm mở màn (<b>Hook Zoom Boost</b>)</span>} checked={ctx.hookZoomBoost} onChange={ctx.setHookZoomBoost} tooltip="Cảnh đầu zoom mạnh (1.0→1.35) + tự thêm tiếng Riser dâng trào để giữ chân người xem trong 3 giây đầu" />
          <ToggleRow label="⚡ Pattern Interrupt (Chống lướt)" checked={ctx.usePatternInterrupt} onChange={ctx.setUsePatternInterrupt} tooltip="Tạo các cú giật nhẹ (flash trắng ngắn hoặc zoom nhẹ) cứ mỗi 2.5-3.5s để giữ mắt người xem. Tự động vô hiệu ở tone Storytelling/Emotional để tránh phá hỏng không khí." />
        </div>
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
            <option value="typewriter_quote">⌨️ Gõ chữ (A2 Typewriter)</option>
            <option value="camera_shutter">📸 Nháy máy ảnh (Camera Shutter)</option>
            <option value="cyber_glitch">⚡ Nhiễu sóng (Cyber Glitch)</option>
            <option value="vintage_film_burn">🎞️ Cháy phim (Vintage Film Burn)</option>
            <option value="smash_cut_blackout">💥 Đóng sập đen (Smash Cut)</option>
            <option value="cinematic_letterbox">🎬 Viền đen điện ảnh (21:9 Letterbox)</option>
            <option value="paper_rip_split">✂️ Xé giấy/Cắt đôi (Split Reveal)</option>

            {/* ── 6 Hook Nghệ Thuật Mới ── */}
            <option value="double_exposure">👻 Ảnh ma (Double Exposure)</option>
            <option value="light_paint_ingress">🔦 Vẽ bằng ánh sáng (Light Paint)</option>
            <option value="memory_resurface">💫 Bề mặt ký ức (Memory Resurface)</option>
            <option value="forbidden_uncover">🔓 Lật mở bí mật (Forbidden Uncover)</option>
            <option value="ink_bleed">🖋️ Nhập nhòe mực (Ink Bleed)</option>
            <option value="scene_assembly">🧩 Lắp ráp hiện thực (Scene Assembly)</option>
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

        </div>
        </div>

        {/* --- SECTION: KẾT THÚC VIDEO (OUTRO) --- */}
        <SectionHeader title="KẾT THÚC VIDEO (OUTRO)" isOpen={openOutro} onToggle={() => setOpenOutro(!openOutro)} />
        <div className={`accordion-wrapper ${openOutro ? 'open' : ''}`}>
          <div className="accordion-inner">
        <div className="input-group">
          <label className="field-label">HIỆU ỨNG OUTRO KẾT THÚC</label>
          <select className="form-select form-select-sm" value={ctx.outroEffect} onChange={e => ctx.setOutroEffect(e.target.value)}>
            <option value="none">🚫 Không dùng Outro</option>
            {/* carousel_quote CỐ Ý không có ở đây: chạy lại màn "Máy Xèng" quay bìa giả
                hợp lý ở đầu video (tạo hồi hộp) nhưng vô nghĩa ở cuối (khán giả đã biết
                đáp án từ đầu) — outro cần gây ấn tượng nhanh, không lặp lại một màn chờ
                4.5 giây. Backend vẫn xử lý được giá trị này (preset/project cũ đã lưu),
                chỉ ẩn khỏi lựa chọn mới. */}
            <option value="typewriter_quote">⌨️ Gõ chữ (Typewriter)</option>
            <option value="camera_shutter">📸 Nháy máy ảnh (Camera Shutter)</option>
            <option value="cyber_glitch">⚡ Nhiễu sóng (Cyber Glitch)</option>
            <option value="vintage_film_burn">🎞️ Cháy phim (Vintage Film Burn)</option>
            {OUTRO_ONLY_EFFECTS.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
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
        </div>
        </div>

        {/* --- SECTION: TỐI ƯU & HỆ THỐNG --- */}
        <SectionHeader title="TỐI ƯU & HỆ THỐNG" isOpen={openSystem} onToggle={() => setOpenSystem(!openSystem)} />
        <div className={`accordion-wrapper ${openSystem ? 'open' : ''}`}>
          <div className="accordion-inner">
        <div className="toggles-grid" style={{ marginBottom: 15, gridColumn: '1 / -1' }}>
          <ToggleRow
            label="✍️ Tự viết lại kịch bản nếu điểm thấp"
            checked={ctx.autoRetryLowQuality}
            onChange={ctx.setAutoRetryLowQuality}
            tooltip="Nếu lớp biên tập AI chấm kịch bản dưới 60/100, hệ thống viết lại ĐÚNG 1 lượt kèm các góp ý cụ thể, và chỉ nhận bản mới khi nó điểm cao hơn. Tốn thêm 1-2 lượt quota mỗi khi kích hoạt. Không áp dụng cho mode Kịch bản → Video (lời thoại của bạn luôn giữ nguyên văn)."
          />
        </div>
        </div>
        </div>
      </div>
    </div>
  );
}
