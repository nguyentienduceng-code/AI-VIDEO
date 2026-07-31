import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Smartphone, Monitor, Square, Play, Mic, Music, Loader, Sparkles, Pencil, Wrench } from 'lucide-react';
import { useShallow } from 'zustand/react/shallow';
import { useAppStore, needsUpload as needsUploadFor } from '../store';
import { STYLES, VOICES, NARRATION_TONES, DURATION_OPTIONS, NICHE_OPTIONS, API_BASE } from '../constants';
import PresetManager from './PresetManager';

export default function ConfigSection() {
  const ctx = useAppStore(useShallow((s) => ({
    activeMode: s.activeMode,
    ratio: s.ratio, setRatio: s.setRatio,
    numScenes: s.numScenes, setNumScenes: s.setNumScenes,
    targetDuration: s.targetDuration, setTargetDuration: s.setTargetDuration,
    narrationTone: s.narrationTone, setNarrationTone: s.setNarrationTone,
    contentNiche: s.contentNiche, setContentNiche: s.setContentNiche,
    voice: s.voice, setVoice: s.setVoice,
    style: s.style, setStyle: s.setStyle,
    bgm: s.bgm, setBgm: s.setBgm,
    introBgm: s.introBgm, setIntroBgm: s.setIntroBgm,
    introBgmDuration: s.introBgmDuration, setIntroBgmDuration: s.setIntroBgmDuration,
    bgmVolume: s.bgmVolume, setBgmVolume: s.setBgmVolume,
    playPreview: s.playPreview,
    playMixPreview: s.playMixPreview,
    stopAllAudio: s.stopAllAudio,
  })));
  const needsUpload = needsUploadFor(ctx.activeMode);
  // Trần 30 (khớp MAX_SCENES của backend): trần 20 cũ khiến video từ 3 phút trở lên
  // buộc mỗi cảnh phải gánh 25-40 từ, tức 8-13 giây/cảnh.
  const minScenes = 4, maxScenes = 30;
  const sliderPercent = ((ctx.numScenes - minScenes) / (maxScenes - minScenes)) * 100;

  // ── Voice Cloning: danh sách giọng clone cá nhân + upload mẫu ──
  const [customVoices, setCustomVoices] = useState([]);
  const [cloneBusy, setCloneBusy] = useState(false);
  const [clonePreviewBusy, setClonePreviewBusy] = useState(false);
  const cloneInputRef = useRef(null);
  const clonePreviewAudioRef = useRef(null);
  const clonePreviewUrlRef = useRef(null);

  const loadCustomVoices = useCallback(() => {
    fetch(`${API_BASE}/api/voices`)
      .then(r => r.json())
      .then(d => setCustomVoices((d.voices || []).filter(v => v.id?.startsWith('omnivoice_custom_'))))
      .catch(() => {});
  }, []);

  useEffect(() => { loadCustomVoices(); }, [loadCustomVoices]);

  // Giọng AI (clone cá nhân hoặc preset OmniVoice) sinh ra bằng GPU, không nghe thử
  // được qua /api/preview/voice/{id} như giọng Edge-TTS: file .mp3 mẫu ở đó là bản ghi
  // âm GỐC user tải lên, không phải giọng AI đã tổng hợp. Muốn biết bản clone đọc ra
  // sao thì phải thật sự cho nó đọc một câu.
  const isAiVoice = (ctx.voice || '').startsWith('omnivoice_');
  const selectedClone = customVoices.find(v => v.id === ctx.voice);

  const stopClonePreview = useCallback(() => {
    if (clonePreviewAudioRef.current) {
      clonePreviewAudioRef.current.pause();
      clonePreviewAudioRef.current = null;
    }
    if (clonePreviewUrlRef.current) {
      URL.revokeObjectURL(clonePreviewUrlRef.current);   // không thu hồi thì blob rò rỉ trong tab
      clonePreviewUrlRef.current = null;
    }
  }, []);

  useEffect(() => stopClonePreview, [stopClonePreview]);

  const CLONE_PREVIEW_TEXT =
    'Xin chào, đây là giọng đọc AI được nhân bản từ mẫu ghi âm của bạn. ' +
    'Bạn thấy chất lượng và ngữ điệu thế nào?';

  const previewCloneVoice = async () => {
    stopClonePreview();
    ctx.stopAllAudio();
    setClonePreviewBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/preview-scene-voice`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: CLONE_PREVIEW_TEXT, voice: ctx.voice }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Không nghe thử được giọng AI.');
      }
      // Backend báo về đây khi OmniVoice hỏng và đã đọc bằng giọng tiêu chuẩn thay thế
      // — không hiện ra thì user tưởng bản clone nghe y hệt giọng mặc định.
      const warn = res.headers.get('X-TTS-Warning');
      const url = URL.createObjectURL(await res.blob());
      clonePreviewUrlRef.current = url;
      const audio = new Audio(url);
      clonePreviewAudioRef.current = audio;
      audio.addEventListener('ended', stopClonePreview);
      await audio.play();
      if (warn) alert(decodeURIComponent(warn));
    } catch (err) {
      stopClonePreview();
      alert('Lỗi nghe thử giọng AI: ' + err.message);
    } finally {
      setClonePreviewBusy(false);
    }
  };

  // Chạy lại toàn bộ khâu xử lý mẫu cho giọng đã tạo từ trước khi có bộ lọc: lọc nhiễu,
  // chuẩn hoá độ to, cắt về 10 giây, chép lại lời mẫu. Giọng cũ không có cách nào khác
  // để hưởng các bản vá này ngoài việc xoá đi tải lên lại — mà file gốc thì user
  // thường đã không còn giữ.
  const [repairing, setRepairing] = useState(false);

  const repairCloneVoice = async () => {
    if (!selectedClone) return;
    if (!window.confirm(
      `Sửa lại giọng "${selectedClone.raw_name}"?\n\n` +
      'Hệ thống sẽ lọc nhiễu, chuẩn hoá độ to, cắt mẫu về 10 giây và chép lại lời mẫu ' +
      'từ chính file ghi âm. Dùng khi giọng được tạo từ lâu hoặc đọc ra nghe chưa chuẩn.'
    )) return;
    setRepairing(true);
    try {
      const res = await fetch(`${API_BASE}/api/voice-clone/${selectedClone.id}/repair`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Sửa thất bại');
      loadCustomVoices();
      alert(
        `✅ ${data.message}\n\n` +
        `Lời mẫu mới:\n"${data.after.ref_text}"\n\n` +
        'Hãy bấm ✨ nghe thử. Nếu lời mẫu trên có chữ sai so với file bạn thu, ' +
        'bấm ✏️ sửa lại cho đúng — càng khớp thì giọng đọc càng chuẩn.'
      );
    } catch (err) {
      alert('Lỗi sửa giọng clone: ' + err.message);
    } finally {
      setRepairing(false);
    }
  };

  // Sửa tên hiển thị + văn bản đọc mẫu. Transcript sai (whisper hay nhầm dấu tiếng Việt)
  // làm giọng clone phát âm lệch, nên đây là thứ đáng sửa nhất sau khi nghe thử.
  const editCloneVoice = async () => {
    if (!selectedClone) return;
    const newName = window.prompt('Tên hiển thị của giọng clone:', selectedClone.raw_name || '');
    if (newName === null) return;
    const newTranscript = window.prompt(
      'Văn bản đọc mẫu (transcript) — phải khớp ĐÚNG lời trong file ghi âm bạn đã tải lên.\n' +
      'Để TRỐNG rồi bấm OK: hệ thống nghe lại file và tự chép lời (dùng khi giọng đọc ra vô nghĩa).',
      selectedClone.ref_text || ''
    );
    if (newTranscript === null) return;

    const put = (body) => fetch(`${API_BASE}/api/voice-clone/${selectedClone.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    try {
      const body = newTranscript.trim()
        ? { name: newName, transcript: newTranscript.trim() }
        : { name: newName, retranscribe: true };   // để trống = nhờ máy chép lại
      let res = await put(body);
      let data = await res.json();
      if (res.status === 409) {
        const dungBanChep = window.confirm(
          data.detail + '\n\n[OK] = dùng lời hệ thống chép được (khuyên dùng)\n[Cancel] = giữ nguyên lời bạn nhập'
        );
        res = await put(dungBanChep
          ? { name: newName, retranscribe: true }
          : { name: newName, transcript: newTranscript.trim(), force_transcript: true });
        data = await res.json();
      }
      if (!res.ok) throw new Error(data.detail || 'Cập nhật thất bại');
      loadCustomVoices();
      alert(`✅ ${data.message}` + (data.voice?.ref_text ? `\n\nLời mẫu hiện tại:\n"${data.voice.ref_text}"` : ''));
    } catch (err) {
      alert('Lỗi cập nhật giọng clone: ' + err.message);
    }
  };

  const handleCloneUpload = async (e) => {
    const f = e.target.files?.[0];
    const defaultName = f.name.replace(/\.[^.]+$/, '');
    const cloneName = window.prompt("Nhập tên cho giọng Clone (Khuyên dùng tiền tố 'Nam - ' hoặc 'Nữ - ' để dễ phân loại):", defaultName);
    if (!cloneName) {
      if (cloneInputRef.current) cloneInputRef.current.value = '';
      return;
    }
    
    // Transcript phải khớp ĐÚNG lời trong file — backend đối chiếu bằng whisper và từ
    // chối nếu lệch. Bỏ trống là an toàn nhất: hệ thống tự chép lời từ chính file đó.
    const transcript = window.prompt(
      'Văn bản đọc mẫu — nhập ĐÚNG từng chữ mà bạn nói trong file ghi âm.\n' +
      '(Để trống thì hệ thống tự chép lời. Nhập sai lời sẽ làm giọng AI đọc ra tiếng Việt vô nghĩa.)',
      ''
    );
    if (transcript === null) {
      if (cloneInputRef.current) cloneInputRef.current.value = '';
      return;
    }

    setCloneBusy(true);
    try {
      const fd = new FormData();
      fd.append('file', f);
      fd.append('name', cloneName.trim());
      if (transcript.trim()) fd.append('transcript', transcript.trim());
      const res = await fetch(`${API_BASE}/api/voice-clone`, { method: 'POST', body: fd });
      const data = await res.json();
      // 409 = transcript lệch nội dung file. Cho user chọn: dùng bản máy chép lại (an
      // toàn), hay giữ nguyên bản mình nhập (nếu họ chắc chắn whisper nghe sai).
      if (res.status === 409) {
        const dungBanChep = window.confirm(
          data.detail + '\n\n[OK] = dùng lời hệ thống chép được (khuyên dùng)\n[Cancel] = giữ nguyên lời bạn nhập'
        );
        const fd2 = new FormData();
        fd2.append('file', f);
        fd2.append('name', cloneName.trim());
        if (dungBanChep) {
          // không gửi transcript → backend tự chép lời từ file
        } else {
          fd2.append('transcript', transcript.trim());
          fd2.append('force_transcript', 'true');
        }
        const res2 = await fetch(`${API_BASE}/api/voice-clone`, { method: 'POST', body: fd2 });
        const data2 = await res2.json();
        if (!res2.ok) throw new Error(data2.detail || 'Upload thất bại');
        Object.assign(data, data2);
      } else if (!res.ok) {
        throw new Error(data.detail || 'Upload thất bại');
      }
      loadCustomVoices();
      ctx.setVoice(data.voice_id);
      alert(
        `✅ Đã tạo giọng clone "${data.name}" (${data.gender})!\n\n` +
        `Mẫu sau khi lọc nhiễu & gọt lặng: ${data.speech_seconds}s tiếng nói.\n` +
        `Transcript nhận dạng: "${data.ref_text}"\n\n` +
        `Giọng đã được chọn sẵn. Bấm nút ✨ để nghe thử giọng AI đọc thật, ` +
        `và nút ✏️ nếu cần sửa lại transcript cho khớp lời trong file.`
      );
    } catch (err) {
      alert('Lỗi tạo giọng clone: ' + err.message);
    } finally {
      setCloneBusy(false);
      if (cloneInputRef.current) cloneInputRef.current.value = '';
    }
  };

  const builtInMale = VOICES.filter(v => v.label.includes('Nam -') || v.label.includes('Nam ('));
  const builtInFemale = VOICES.filter(v => v.label.includes('Nữ -') || v.label.includes('Nữ ('));
  const builtInOther = VOICES.filter(v => !builtInMale.includes(v) && !builtInFemale.includes(v));

  // Xếp nhóm theo trường `gender` do backend trả về, KHÔNG dò chữ trong tên nữa: đó
  // cũng chính là giới tính backend dùng để chọn giọng đọc thay thế khi OmniVoice hỏng,
  // nên nhóm hiện trên màn hình và giọng nghe được lúc lỗi luôn khớp nhau.
  const customMale = customVoices.filter(v => v.gender === 'Nam');
  const customFemale = customVoices.filter(v => v.gender === 'Nữ');
  const customOther = customVoices.filter(v => !customMale.includes(v) && !customFemale.includes(v));

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

  return (
    <div className="config-section-inner">
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
      
      {!needsUpload && (
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

          <div className="input-group">
            <label className="field-label">THỂ LOẠI NỘI DUNG (NICHE) — hiệu ứng & cấu trúc tự khớp</label>
            <select
              className="form-select form-select-sm"
              value={ctx.contentNiche}
              onChange={e => ctx.setContentNiche(e.target.value)}
              title="Chọn thể loại để AI dùng bản vẽ cấu trúc + hiệu ứng chuyển cảnh/SFX đúng chất (mini-twist giữa bài, cao trào ~80%...). Để trống nếu muốn tự do theo tone."
            >
              {NICHE_OPTIONS.map(n => <option key={n.value} value={n.value}>{n.label}</option>)}
            </select>
          </div>
        </>
      )}

      <div className="settings-grid">
        <div className="input-group">
          <label className="field-label">GIỌNG ĐỌC</label>
          <div style={{ display: 'flex', gap: 8 }}>
            <select className="form-select" value={ctx.voice} onChange={e => ctx.setVoice(e.target.value)} style={{ flex: 1 }}>
              <optgroup label="👨 Giọng Nam (Có sẵn)">
                {builtInMale.map(v => <option key={v.value} value={v.value}>{v.label}</option>)}
              </optgroup>
              <optgroup label="👩 Giọng Nữ (Có sẵn)">
                {builtInFemale.map(v => <option key={v.value} value={v.value}>{v.label}</option>)}
              </optgroup>
              {builtInOther.length > 0 && (
                <optgroup label="👽 Giọng Đặc biệt">
                  {builtInOther.map(v => <option key={v.value} value={v.value}>{v.label}</option>)}
                </optgroup>
              )}
              {customMale.length > 0 && (
                <optgroup label="🎤 Clone Nam (Cá nhân)">
                  {customMale.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
                </optgroup>
              )}
              {customFemale.length > 0 && (
                <optgroup label="🎤 Clone Nữ (Cá nhân)">
                  {customFemale.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
                </optgroup>
              )}
              {customOther.length > 0 && (
                <optgroup label="🎤 Clone Khác (Cá nhân)">
                  {customOther.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
                </optgroup>
              )}
            </select>
            <button className="btn-icon" onClick={() => ctx.playPreview('voice', ctx.voice)} title="Nghe thử"><Play size={18} /></button>
            {isAiVoice && (
              <button
                className="btn-icon"
                onClick={previewCloneVoice}
                disabled={clonePreviewBusy}
                title="Nghe thử AI Clone: cho giọng AI đọc thật một câu tiếng Việt để kiểm tra chất lượng (nút ▶ bên cạnh chỉ phát lại file ghi âm gốc bạn đã tải lên)"
              >
                {clonePreviewBusy ? <Loader size={18} className="animate-spin" /> : <Sparkles size={18} />}
              </button>
            )}
            {selectedClone && (
              <button
                className="btn-icon"
                onClick={editCloneVoice}
                title="Sửa tên hiển thị & văn bản đọc mẫu của giọng clone này"
              >
                <Pencil size={18} />
              </button>
            )}
            {selectedClone && (
              <button
                className="btn-icon"
                onClick={repairCloneVoice}
                disabled={repairing}
                title="Sửa lại mẫu giọng: lọc nhiễu, chuẩn hoá độ to, cắt về 10 giây và chép lại lời mẫu. Dùng cho giọng tạo từ lâu hoặc đọc ra nghe chưa chuẩn."
              >
                {repairing ? <Loader size={18} className="animate-spin" /> : <Wrench size={18} />}
              </button>
            )}
            <button
              className="btn-icon"
              onClick={() => cloneInputRef.current?.click()}
              disabled={cloneBusy}
              title="Clone giọng của bạn: upload đoạn ghi âm nói rõ ràng 5-10 giây (wav/mp3/m4a)"
            >
              {cloneBusy ? <Loader size={18} className="animate-spin" /> : <Mic size={18} />}
            </button>
            <input
              ref={cloneInputRef}
              type="file"
              accept=".wav,.mp3,.m4a,.ogg,.flac,audio/*"
              style={{ display: 'none' }}
              onChange={handleCloneUpload}
            />
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
        <label className="field-label">♬ NHẠC NỀN CHÍNH (MAIN BGM)</label>
        <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
          <select className="form-select" value={ctx.bgm} onChange={e => ctx.setBgm(e.target.value)} style={{ flex: 1 }}>
            <option value="auto">✨ Tự động chọn bằng AI</option>
            <option value="none">Không dùng nhạc nền</option>
            {BGMOptions}
          </select>
          {ctx.bgm !== 'none' && (
            <div style={{ display: 'flex', gap: 4 }}>
              <button className="btn-icon" onClick={() => ctx.playPreview('bgm', ctx.bgm)} title="Nghe thử nhạc nền độc lập">
                <Play size={18} />
              </button>
              <button 
                className="btn-icon" 
                style={{ color: '#FF69B4', background: 'rgba(255,105,180,0.1)' }}
                onClick={() => ctx.playMixPreview(ctx.voice, ctx.bgm)} 
                title="Nghe lồng tiếng (Mix Voice + BGM) để test âm lượng nền"
              >
                <div style={{ display: 'flex', alignItems: 'center' }}>
                  <Mic size={14} style={{ marginRight: -4 }} />
                  <Music size={14} />
                </div>
              </button>
            </div>
          )}
          {ctx.bgm !== 'none' && <input type="range" className="vol-slider" min="0" max="100" value={ctx.bgmVolume} onChange={e => ctx.setBgmVolume(Number(e.target.value))} style={{ width: 80 }} />}
        </div>
      </div>
    </div>
  );
}
