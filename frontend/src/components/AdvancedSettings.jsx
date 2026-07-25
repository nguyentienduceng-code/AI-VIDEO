import React from 'react';
import { useAppContext } from '../AppContext';
import { SUBTITLE_STYLES, COLOR_GRADINGS } from '../constants';

export default function AdvancedSettings() {
  const ctx = useAppContext();

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
    <div className="advanced-box panel-box">
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
          label="Tự thêm SFX mở màn (Hook)"
          checked={ctx.useSfx}
          onChange={ctx.setUseSfx}
          tooltip="Tự chèn tiếng Riser dâng trào ở cảnh mở màn (khi bật Hook Zoom Boost). Lưu ý: SFX bạn chọn RIÊNG cho từng cảnh trong phần Kịch bản LUÔN phát, không phụ thuộc nút này."
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
        <ToggleRow
          label={<span>🎬 Dùng <b>video nền thật</b> (Pexels stock)</span>}
          checked={ctx.preferStockVideo}
          onChange={ctx.setPreferStockVideo}
          tooltip="Thay ảnh AI tĩnh bằng video stock chuyển động thật từ Pexels cho MỌI cảnh (không cần Veo/billing). Hợp nhất với chủ đề đời thực; cảnh nào không tìm được video sẽ tự dùng ảnh AI."
        />
      </div>

      <div className="advanced-inputs-grid" style={{ marginTop: 20 }}>
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
          <label className="field-label">HIỆU ỨNG HOOK ĐẦU VIDEO</label>
          <select className="form-select form-select-sm" value={ctx.hookEffect} onChange={e => ctx.setHookEffect(e.target.value)}>
            <option value="word_by_word">Từng từ đập vào (Word-by-word)</option>
            <option value="full_shake">Rung lắc cả câu (Full shake)</option>
            <option value="carousel_quote">Slot Machine & Bìa sách (Carousel Quote)</option>
          </select>
        </div>
        <div className="input-group" style={{ gridColumn: '1 / -1' }}>
          <label className="field-label">TIÊU ĐỀ HOOK CHỮ (Áp dụng Từng từ/Rung lắc)</label>
          <input 
            type="text" 
            className="form-input form-input-sm" 
            value={ctx.hookText} 
            onChange={e => ctx.setHookText(e.target.value)} 
            placeholder="VD: BÍ MẬT ĐỘNG TRỜI VỀ ROCKEFELLER!..." 
          />
        </div>
        <div className="input-group" style={{ gridColumn: '1 / -1' }}>
          <label className="field-label">TRÍCH DẪN HOOK BÌA SÁCH (Quote - Áp dụng Carousel)</label>
          <input 
            type="text" 
            className="form-input form-input-sm" 
            value={ctx.hookQuote} 
            onChange={e => ctx.setHookQuote(e.target.value)} 
            placeholder="VD: GIÁ TRỊ NẰM Ở SỰ LỰA CHỌN..." 
          />
        </div>
        <div className="input-group">
          <label className="field-label">TỐC ĐỘ ĐỌC (EDGE-TTS)</label>
          <select className="form-select form-select-sm" value={ctx.speechRate} onChange={e => ctx.setSpeechRate(e.target.value)}>
            <option value="-10%">Chậm (-10%)</option>
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
        <div className="input-group">
          <label className="field-label">ÂM LƯỢNG SFX ({ctx.sfxVolume}%)</label>
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
      </div>
    </div>
  );
}
