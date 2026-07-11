import React, { useState, useRef, useCallback } from 'react';
import {
  Wand2, Smartphone, Monitor, Square, AlertTriangle,
  ChevronDown, ChevronUp, Trash2, Plus, GripVertical,
  Upload, X, Eye, Download, RotateCcw, Key, Play,
  Sparkles, PenLine, Film, Check
} from 'lucide-react';

// ─── CONSTANTS ───
const API_BASE = 'http://localhost:8000';

const MODE_MAP = {
  storyteller: 'storyteller',
  img2vid: 'photo_narration',
  slideshow: 'photo_slideshow',
  script: 'script_video',
  quiz: 'quiz_listicle',
};

const MODES = [
  { id: 'storyteller', icon: '✨', title: 'AI Storyteller', desc: 'Nhập chủ đề → AI viết kịch bản,\nsinh ảnh, render video tự động' },
  { id: 'img2vid', icon: '🖼️', title: 'Ảnh → Video', desc: 'Upload ảnh → AI viết lời bình\nvà kể chuyện cho từng ảnh' },
  { id: 'slideshow', icon: '🎞️', title: 'Slideshow', desc: 'Upload ảnh → Video cinematic\nvới nhạc nền, hiệu ứng' },
  { id: 'script', icon: '📝', title: 'Script → Video', desc: 'Paste script viết sẵn → AI chia\ncảnh, sinh ảnh, đọc lời' },
  { id: 'quiz', icon: '❓', title: 'Quiz / Listicle', desc: 'Chủ đề → AI sinh video dạng\n"Top N" hoặc hỏi-đáp' },
];

const STYLES = [
  { value: 'Anime illustration, vibrant colors, Studio Ghibli inspired', label: 'Anime (Hoạt hình)' },
  { value: 'Photorealistic, cinematic lighting, 8K UHD', label: 'Realistic (Thực tế)' },
  { value: '3D render, Pixar style, soft lighting, highly detailed', label: '3D Render' },
  { value: 'Cinematic, dramatic lighting, widescreen composition', label: 'Cinematic (Điện ảnh)' },
  { value: 'Watercolor painting, soft brush strokes, artistic', label: 'Watercolor (Màu nước)' },
  { value: 'Cyberpunk 2077 style, neon lights, futuristic city, sci-fi', label: 'Cyberpunk 2077 (Tương lai)' },
  { value: 'Dark Fantasy, gothic, moody lighting, mysterious, highly detailed', label: 'Dark Fantasy (Huyền bí)' },
  { value: 'Vintage 35mm film, grainy, retro aesthetic, warm nostalgic colors', label: 'Vintage Film (Phim cũ)' },
  { value: 'Comic book panel, manga style, heavy shadows, halftone patterns, dramatic angles', label: 'Comic/Manga (Truyện tranh)' },
  { value: 'Hand-drawn Japanese animation, pastel tones, beautiful scenery, nostalgic', label: 'Japanese Animation (Tươi sáng)' },
];

const VOICES = [
  { value: 'vi-VN-NamMinhNeural', label: 'Nam - Nam Minh' },
  { value: 'vi-VN-HoaiMyNeural', label: 'Nữ - Hoài My' },
  { value: 'vi-VN-AnNiNeural', label: 'Nữ - An Ni (Trẻ trung)' },
  { value: 'vi-VN-PhuongMyNeural', label: 'Nữ - Phương My (Tin tức)' },
  { value: 'minion', label: 'Minion (Nhí nhảnh)' },
  { value: 'minion_pro', label: 'Minion Pro (Hỗn loạn, Cuốn hút)' },
];

// ─── MAIN APP ───
export default function App() {
  // Workflow step: 'config' → 'editor' → 'rendering' → 'done'
  const [step, setStep] = useState('config');

  // Config states
  const [activeMode, setActiveMode] = useState('storyteller');
  const [topic, setTopic] = useState('');
  const [scriptText, setScriptText] = useState('');
  const [ratio, setRatio] = useState('9:16');
  const [numScenes, setNumScenes] = useState(6);
  const [voice, setVoice] = useState('vi-VN-NamMinhNeural');
  const [style, setStyle] = useState(STYLES[0].value);
  const [bgm, setBgm] = useState('none');
  const [apiKey, setApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);

  // V3 features
  const [useVeo, setUseVeo] = useState(false);
  const [useAnimatedCaptions, setUseAnimatedCaptions] = useState(true);
  const [ctaText, setCtaText] = useState('');

  // V4 features (Phase 2 UI upgrades)
  const [speechRate, setSpeechRate] = useState('+0%');
  const [speechPitch, setSpeechPitch] = useState('+0Hz');
  const [bgmVolume, setBgmVolume] = useState(15); // 0 to 100
  const [negativePrompt, setNegativePrompt] = useState('');

  // Upload states
  const [uploadSessionId, setUploadSessionId] = useState(null);
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [uploadLoading, setUploadLoading] = useState(false);
  const fileInputRef = useRef(null);

  // Script editor states
  const [scenes, setScenes] = useState([]);
  const [scriptLoading, setScriptLoading] = useState(false);

  // Render states
  const [status, setStatus] = useState('idle');
  const [progress, setProgress] = useState(0);
  const [jobMessage, setJobMessage] = useState('');
  const [progressLog, setProgressLog] = useState([]);
  const [videoUrl, setVideoUrl] = useState(null);
  const [srtUrl, setSrtUrl] = useState(null);

  // Error
  const [errorMsg, setErrorMsg] = useState('');

  // Slider
  const minScenes = 4, maxScenes = 20;
  const sliderPercent = ((numScenes - minScenes) / (maxScenes - minScenes)) * 100;

  // ─── Needs upload? ───
  const needsUpload = activeMode === 'img2vid' || activeMode === 'slideshow';
  const needsScript = activeMode === 'script';
  const needsTopic = !needsUpload && !needsScript;

  // ─── UPLOAD HANDLER ───
  const handleUpload = async (e) => {
    const files = Array.from(e.target.files);
    if (!files.length) return;

    setUploadLoading(true);
    setErrorMsg('');
    const formData = new FormData();
    files.forEach(f => formData.append('images', f));

    try {
      const res = await fetch(`${API_BASE}/api/upload-images`, { method: 'POST', body: formData });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Upload lỗi');
      }
      const data = await res.json();
      setUploadSessionId(data.session_id);
      setUploadedFiles(files.map(f => f.name));
      setNumScenes(files.length);
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setUploadLoading(false);
    }
  };

  // ─── STEP 1: GENERATE SCRIPT ───
  const handleGenerateScript = async () => {
    if (needsTopic && !topic.trim()) {
      setErrorMsg('Vui lòng nhập chủ đề video!');
      return;
    }
    if (needsScript && !scriptText.trim()) {
      setErrorMsg('Vui lòng nhập nội dung kịch bản!');
      return;
    }
    if (needsUpload && !uploadSessionId) {
      setErrorMsg('Vui lòng upload ảnh trước!');
      return;
    }

    setErrorMsg('');
    setScriptLoading(true);

    try {
      const payload = {
        topic,
        mode: MODE_MAP[activeMode],
        num_scenes: numScenes,
        art_style: style,
        script_text: scriptText || undefined,
        upload_session_id: uploadSessionId || undefined,
        gemini_api_key: apiKey || undefined,
      };

      const res = await fetch(`${API_BASE}/api/generate-script`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Lỗi sinh kịch bản');
      }

      const data = await res.json();
      setScenes(data.scenes || []);
      setStep('editor');
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setScriptLoading(false);
    }
  };

  // ─── STEP 2: RENDER VIDEO ───
  const handleRenderVideo = async () => {
    if (!scenes.length) {
      setErrorMsg('Chưa có cảnh nào để render!');
      return;
    }

    setErrorMsg('');
    setStep('rendering');
    setStatus('loading');
    setProgress(0);
    setJobMessage('Đang khởi tạo...');
    setProgressLog([]);
    setVideoUrl(null);
    setSrtUrl(null);

    try {
      const payload = {
        scenes,
        mode: MODE_MAP[activeMode],
        aspect_ratio: ratio,
        voice,
        bgm_track: bgm === 'none' ? null : bgm,
        upload_session_id: uploadSessionId || undefined,
        speech_rate: speechRate,
        speech_pitch: speechPitch,
        bgm_volume: bgmVolume / 100, // convert percentage to float
        negative_prompt: negativePrompt || undefined,
        gemini_api_key: apiKey || undefined,
        use_veo: useVeo,
        cta_text: ctaText || undefined,
        use_animated_captions: useAnimatedCaptions,
      };

      const res = await fetch(`${API_BASE}/api/render-video`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Lỗi server');
      }

      const data = await res.json();
      const jobId = data.job_id;

      // WebSocket progress
      const ws = new WebSocket(`ws://localhost:8000/api/ws/job-status/${jobId}`);

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.progress !== undefined) setProgress(msg.progress);
        if (msg.message) {
          setJobMessage(msg.message);
          setProgressLog(prev => {
            const last = prev[prev.length - 1];
            if (last === msg.message) return prev;
            return [...prev, msg.message];
          });
        }

        if (msg.status === 'done') {
          ws.close();
          setStatus('done');
          setStep('done');
          if (msg.video_url) setVideoUrl(`${API_BASE}${msg.video_url}`);
          if (msg.srt_url) setSrtUrl(`${API_BASE}${msg.srt_url}`);
        } else if (msg.status === 'error') {
          ws.close();
          setStatus('error');
          setStep('rendering');
          setErrorMsg(msg.error || msg.message || 'Có lỗi xảy ra');
        }
      };

      ws.onerror = () => {
        setStatus('error');
        setErrorMsg('Mất kết nối WebSocket với máy chủ!');
      };

    } catch (err) {
      setStatus('error');
      setErrorMsg(err.message);
    }
  };

  // ─── SCENE EDITOR HELPERS ───
  const updateScene = (index, field, value) => {
    setScenes(prev => prev.map((s, i) => i === index ? { ...s, [field]: value } : s));
  };
  const removeScene = (index) => {
    setScenes(prev => prev.filter((_, i) => i !== index).map((s, i) => ({ ...s, scene: i + 1 })));
  };
  const addScene = () => {
    setScenes(prev => [...prev, { scene: prev.length + 1, text: '', image_prompt: '' }]);
  };
  const moveScene = (from, to) => {
    if (to < 0 || to >= scenes.length) return;
    setScenes(prev => {
      const arr = [...prev];
      const [item] = arr.splice(from, 1);
      arr.splice(to, 0, item);
      return arr.map((s, i) => ({ ...s, scene: i + 1 }));
    });
  };

  // ─── RESET ───
  const handleReset = () => {
    setStep('config');
    setScenes([]);
    setStatus('idle');
    setProgress(0);
    setJobMessage('');
    setProgressLog([]);
    setVideoUrl(null);
    setSrtUrl(null);
    setErrorMsg('');
    setUploadSessionId(null);
    setUploadedFiles([]);
  };

  // ═══════════════════════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════════════════════
  return (
    <div className="app-container">

      {/* ─── HEADER ─── */}
      <div className="app-header">
        <div className="app-logo">
          <Film size={24} /> AI Video Studio
        </div>
        <div className="header-steps">
          <div className={`header-step ${step === 'config' ? 'active' : ''} ${step !== 'config' ? 'completed' : ''}`}>
            <div className="header-step-num">1</div> Cài đặt
          </div>
          <div className="header-step-arrow">→</div>
          <div className={`header-step ${step === 'editor' ? 'active' : ''} ${['rendering', 'done'].includes(step) ? 'completed' : ''}`}>
            <div className="header-step-num">2</div> Kịch bản
          </div>
          <div className="header-step-arrow">→</div>
          <div className={`header-step ${step === 'rendering' || step === 'done' ? 'active' : ''}`}>
            <div className="header-step-num">3</div> Render
          </div>
        </div>
      </div>

      {/* ─── MODE CARDS ─── */}
      {step === 'config' && (
        <div className="top-modes">
          {MODES.map(mode => (
            <div
              key={mode.id}
              className={`mode-card ${activeMode === mode.id ? 'active' : ''}`}
              onClick={() => { setActiveMode(mode.id); setErrorMsg(''); }}
            >
              <div className="mode-icon">{mode.icon}</div>
              <div className="mode-title">{mode.title}</div>
              <div className="mode-desc" style={{ whiteSpace: 'pre-line' }}>{mode.desc}</div>
            </div>
          ))}
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════ */}
      {/* STEP 1: CONFIG */}
      {/* ═══════════════════════════════════════════════════════ */}
      {step === 'config' && (
        <div className="main-grid">
          <div className="control-panel">
            {/* ── Content Input ── */}
            <div>
              <div className="step-header">
                <div className="step-badge step-1">1</div>
                <span className="step-title">
                  {needsUpload ? 'Upload Ảnh' : needsScript ? 'Nhập Kịch bản' : 'Ý Tưởng / Chủ Đề'}
                </span>
              </div>

              {/* Topic input (storyteller, quiz) */}
              {needsTopic && (
                <>
                  <label className="field-label">CHỦ ĐỀ VIDEO</label>
                  <textarea
                    className="form-textarea"
                    value={topic}
                    onChange={e => setTopic(e.target.value)}
                    placeholder="VD: 5 sự thật thú vị về vũ trụ mà bạn chưa biết..."
                    rows={4}
                  />
                </>
              )}

              {/* Script input (script mode) */}
              {needsScript && (
                <>
                  <label className="field-label">KỊCH BẢN CỦA BẠN</label>
                  <textarea
                    className="form-textarea"
                    value={scriptText}
                    onChange={e => setScriptText(e.target.value)}
                    placeholder="Paste toàn bộ script vào đây. AI sẽ tự chia thành các cảnh và sinh hình ảnh phù hợp..."
                    rows={6}
                    style={{ minHeight: 160 }}
                  />
                </>
              )}

              {/* Image upload (img2vid, slideshow) */}
              {needsUpload && (
                <div className="upload-zone">
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept="image/jpeg,image/png,image/webp"
                    onChange={handleUpload}
                    style={{ display: 'none' }}
                  />
                  {uploadedFiles.length === 0 ? (
                    <div
                      className="upload-placeholder"
                      onClick={() => fileInputRef.current?.click()}
                    >
                      <Upload size={32} />
                      <p>Nhấn để chọn ảnh (JPG, PNG, WebP)</p>
                      <span>Tối đa 20 ảnh, mỗi ảnh ≤ 10MB</span>
                    </div>
                  ) : (
                    <div className="upload-done">
                      <Check size={20} style={{ color: 'var(--green)' }} />
                      <span>Đã upload {uploadedFiles.length} ảnh</span>
                      <button
                        className="btn-icon"
                        onClick={() => { setUploadedFiles([]); setUploadSessionId(null); }}
                      >
                        <X size={16} />
                      </button>
                    </div>
                  )}
                  {uploadLoading && <div className="upload-loading">Đang upload...</div>}
                </div>
              )}
            </div>

            <div className="divider" />

            {/* ── Settings ── */}
            <div>
              <div className="step-header">
                <div className="step-badge step-2">2</div>
                <span className="step-title">Cài đặt</span>
              </div>

              {/* Ratio */}
              <div style={{ marginBottom: 24 }}>
                <label className="field-label">TỈ LỆ KHUNG HÌNH</label>
                <div className="ratio-group">
                  {[
                    { v: '9:16', icon: <Smartphone size={14} />, label: '9:16 Dọc' },
                    { v: '16:9', icon: <Monitor size={14} />, label: '16:9 Ngang' },
                    { v: '1:1', icon: <Square size={14} />, label: '1:1 Vuông' },
                  ].map(r => (
                    <button key={r.v} className={`ratio-btn ${ratio === r.v ? 'active' : ''}`} onClick={() => setRatio(r.v)}>
                      {r.icon} {r.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Scenes slider */}
              {!needsUpload && (
                <div style={{ marginBottom: 24 }}>
                  <div className="slider-header">
                    <label className="field-label" style={{ marginBottom: 0 }}>SỐ CẢNH:</label>
                    <span className="slider-value">{numScenes}</span>
                  </div>
                  <div className="slider-container">
                    <div style={{ position: 'relative', height: 24, display: 'flex', alignItems: 'center' }}>
                      <input type="range" min={minScenes} max={maxScenes} value={numScenes}
                        onChange={e => setNumScenes(Number(e.target.value))}
                        style={{ position: 'absolute', width: '100%', opacity: 0, zIndex: 10, cursor: 'pointer', height: '100%' }}
                      />
                      <div style={{ width: '100%', height: 4, background: 'rgba(255,255,255,0.1)', borderRadius: 2, position: 'relative' }}>
                        <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${sliderPercent}%`, background: 'var(--amber)', borderRadius: 2 }} />
                        <div style={{ position: 'absolute', left: `${sliderPercent}%`, top: '50%', transform: 'translate(-50%, -50%)', width: 16, height: 16, background: 'var(--amber)', borderRadius: '50%', boxShadow: '0 0 0 4px rgba(245, 158, 11, 0.2)' }} />
                      </div>
                    </div>
                    <div className="slider-labels"><span>{minScenes}</span><span>{maxScenes}</span></div>
                    <div className="slider-hint">~{numScenes * 5}-{numScenes * 10}s</div>
                  </div>
                </div>
              )}

              {/* Voice + Style */}
              <div className="settings-grid">
                <div>
                  <label className="field-label">GIỌNG ĐỌC</label>
                  <select className="form-select" value={voice} onChange={e => setVoice(e.target.value)}>
                    {VOICES.map(v => <option key={v.value} value={v.value}>{v.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="field-label">PHONG CÁCH ẢNH</label>
                  <select className="form-select" value={style} onChange={e => setStyle(e.target.value)}>
                    {STYLES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                  </select>
                </div>
              </div>

              {/* BGM */}
              <div style={{ marginBottom: 20 }}>
                <label className="field-label">♬ NHẠC NỀN</label>
                <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
                  <select className="form-select" value={bgm} onChange={e => setBgm(e.target.value)} style={{ flex: 1 }}>
                    <option value="none">Không dùng nhạc nền</option>
                    <option value="chill_lofi">Chill Lo-Fi</option>
                    <option value="epic_cinematic">Epic Cinematic</option>
                    <option value="soft_piano">Soft Piano</option>
                    <option value="upbeat_pop">Upbeat Pop</option>
                  </select>
                  {bgm !== 'none' && (
                    <div style={{ width: 120, display: 'flex', flexDirection: 'column', gap: 4 }}>
                      <span style={{ fontSize: 11, color: '#aaa' }}>ÂM LƯỢNG ({bgmVolume}%)</span>
                      <input type="range" min="0" max="100" value={bgmVolume} onChange={e => setBgmVolume(Number(e.target.value))} />
                    </div>
                  )}
                </div>
              </div>

              {/* Advanced audio & image */}
              <div className="settings-grid" style={{ marginBottom: 20 }}>
                <div>
                  <label className="field-label">TỐC ĐỘ GIỌNG ĐỌC</label>
                  <select className="form-select" value={speechRate} onChange={e => setSpeechRate(e.target.value)}>
                    <option value="-20%">Rất chậm (-20%)</option>
                    <option value="-10%">Chậm (-10%)</option>
                    <option value="+0%">Bình thường</option>
                    <option value="+10%">Nhanh (+10%)</option>
                    <option value="+20%">Rất nhanh (+20%)</option>
                  </select>
                </div>
                <div>
                  <label className="field-label">CAO ĐỘ (PITCH)</label>
                  <select className="form-select" value={speechPitch} onChange={e => setSpeechPitch(e.target.value)}>
                    <option value="-20Hz">Rất trầm (-20Hz)</option>
                    <option value="-10Hz">Trầm (-10Hz)</option>
                    <option value="+0Hz">Bình thường</option>
                    <option value="+10Hz">Cao (+10Hz)</option>
                    <option value="+20Hz">Rất cao (+20Hz)</option>
                  </select>
                </div>
              </div>
              
              <div style={{ marginBottom: 20 }}>
                <label className="field-label">TỪ KHÓA LOẠI TRỪ (NEGATIVE PROMPT)</label>
                <input 
                  type="text" 
                  className="form-input" 
                  style={{ width: '100%', boxSizing: 'border-box' }} 
                  value={negativePrompt} 
                  onChange={e => setNegativePrompt(e.target.value)} 
                  placeholder="VD: text, watermark, ugly, low resolution..." 
                />
              </div>

              {/* Advanced */}
              <div className="advanced-box">
                <div className="advanced-title">⚡ Tùy chọn nâng cao</div>
                <label className="checkbox-row">
                  <input type="checkbox" checked={useVeo} onChange={e => setUseVeo(e.target.checked)} />
                  <span>Dùng <b>Veo 3</b> biến ảnh → video clip động (~3 phút/cảnh)</span>
                </label>
                <label className="checkbox-row">
                  <input type="checkbox" checked={useAnimatedCaptions} onChange={e => setUseAnimatedCaptions(e.target.checked)} />
                  <span>Phụ đề động kiểu TikTok</span>
                </label>
                <div style={{ marginTop: 8 }}>
                  <label className="field-label">CTA CUỐI VIDEO (Tùy chọn)</label>
                  <input type="text" className="form-input" value={ctaText} onChange={e => setCtaText(e.target.value)} placeholder="VD: Inbox ngay để nhận ưu đãi!" />
                </div>
              </div>

              {/* API Key */}
              <div className="api-key-box" style={{ marginTop: 16 }}>
                <div className="api-key-header" onClick={() => setShowApiKey(!showApiKey)}>
                  <Key size={14} /> Gemini API Key (tùy chọn)
                  {showApiKey ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                </div>
                {showApiKey && (
                  <input type="password" className="form-input" value={apiKey} onChange={e => setApiKey(e.target.value)}
                    placeholder="Nhập API Key nếu không dùng key trong .env" style={{ marginTop: 8 }}
                  />
                )}
              </div>
            </div>

            {/* Generate Script button */}
            <div style={{ marginTop: 'auto', paddingTop: 20 }}>
              <button className="btn-generate" onClick={handleGenerateScript} disabled={scriptLoading}>
                {scriptLoading ? (
                  <span className="btn-loading"><div className="spinner" /> Đang sinh kịch bản...</span>
                ) : (
                  <><Sparkles size={18} /> Sinh Kịch Bản (Bước 1)</>
                )}
              </button>
              {errorMsg && (
                <div className="error-box" style={{ marginTop: 16 }}>
                  <AlertTriangle size={16} /> {errorMsg}
                </div>
              )}
            </div>
          </div>

          {/* ── Right: Preview placeholder ── */}
          <div className="preview-panel" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ textAlign: 'center', color: 'rgba(255,255,255,0.35)', padding: 40 }}>
              <Sparkles size={48} style={{ opacity: 0.4, marginBottom: 16 }} />
              <h3 style={{ marginBottom: 8, fontWeight: 600 }}>Bước 1: Sinh Kịch Bản</h3>
              <p style={{ fontSize: 14, lineHeight: 1.6 }}>
                Nhập ý tưởng bên trái và nhấn <b>"Sinh Kịch Bản"</b>.<br />
                AI sẽ viết kịch bản để bạn xem và chỉnh sửa<br />
                trước khi render video.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════ */}
      {/* STEP 2: SCRIPT EDITOR */}
      {/* ═══════════════════════════════════════════════════════ */}
      {step === 'editor' && (
        <div className="editor-layout">
          <div className="editor-toolbar">
            <button className="btn-outline" onClick={() => setStep('config')}>
              <RotateCcw size={14} /> Quay lại cài đặt
            </button>
            <div className="editor-toolbar-info">
              <PenLine size={14} /> {scenes.length} cảnh — Chỉnh sửa lời thoại & mô tả ảnh bên dưới
            </div>
            <button className="btn-generate" style={{ width: 'auto', padding: '10px 24px', marginTop: 0 }} onClick={handleRenderVideo}>
              <Play size={16} /> Render Video (Bước 2)
            </button>
          </div>

          {errorMsg && (
            <div className="error-box" style={{ marginBottom: 16 }}>
              <AlertTriangle size={16} /> {errorMsg}
            </div>
          )}

          <div className="scene-list">
            {scenes.map((scene, idx) => (
              <div key={idx} className="scene-card">
                <div className="scene-header">
                  <div className="scene-number">Cảnh {idx + 1}</div>
                  <div className="scene-actions">
                    <button className="btn-icon" onClick={() => moveScene(idx, idx - 1)} disabled={idx === 0} title="Di chuyển lên">
                      <ChevronUp size={14} />
                    </button>
                    <button className="btn-icon" onClick={() => moveScene(idx, idx + 1)} disabled={idx === scenes.length - 1} title="Di chuyển xuống">
                      <ChevronDown size={14} />
                    </button>
                    <button className="btn-icon btn-danger" onClick={() => removeScene(idx)} title="Xóa cảnh" disabled={scenes.length <= 1}>
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
                <div className="scene-fields">
                  <div className="scene-field">
                    <label className="field-label">LỜI THOẠI (TIẾNG VIỆT)</label>
                    <textarea
                      className="form-textarea scene-textarea"
                      value={scene.text}
                      onChange={e => updateScene(idx, 'text', e.target.value)}
                      placeholder="Lời thoại sẽ được đọc bằng TTS..."
                      rows={3}
                    />
                  </div>
                  <div className="scene-field">
                    <label className="field-label">MÔ TẢ HÌNH ẢNH (TIẾNG ANH)</label>
                    <textarea
                      className="form-textarea scene-textarea"
                      value={scene.image_prompt}
                      onChange={e => updateScene(idx, 'image_prompt', e.target.value)}
                      placeholder="Image prompt for AI image generation..."
                      rows={2}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>

          <button className="btn-add-scene" onClick={addScene}>
            <Plus size={16} /> Thêm cảnh mới
          </button>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════ */}
      {/* STEP 3: RENDERING */}
      {/* ═══════════════════════════════════════════════════════ */}
      {step === 'rendering' && (
        <div className="render-panel">
          <div className="render-center">
            <div style={{ fontSize: 56, marginBottom: 20 }}>🎬</div>
            <h2 style={{ marginBottom: 8 }}>Đang sản xuất video</h2>
            <p className="render-message">{jobMessage}</p>

            <div className="progress-bar-container">
              <div className="progress-bar-fill" style={{ width: `${progress}%` }} />
            </div>
            <div className="progress-percent">{progress}%</div>

            {/* Progress log */}
            <div className="progress-log">
              {progressLog.map((msg, i) => (
                <div key={i} className="progress-log-item">
                  <Check size={12} style={{ color: 'var(--green)', flexShrink: 0 }} />
                  <span>{msg}</span>
                </div>
              ))}
            </div>
          </div>

          {errorMsg && (
            <div style={{ padding: '0 40px 24px' }}>
              <div className="error-box">
                <AlertTriangle size={16} /> {errorMsg}
              </div>
              <button className="btn-outline" style={{ marginTop: 12 }} onClick={() => { setStep('editor'); setErrorMsg(''); setStatus('idle'); }}>
                <RotateCcw size={14} /> Quay lại chỉnh sửa
              </button>
            </div>
          )}
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════ */}
      {/* STEP 4: DONE */}
      {/* ═══════════════════════════════════════════════════════ */}
      {step === 'done' && videoUrl && (
        <div className="done-panel">
          <div className="done-video-wrap">
            <video src={videoUrl} controls autoPlay style={{ width: '100%', height: '100%', objectFit: 'contain', borderRadius: 12 }} />
          </div>
          <div className="done-actions">
            <a href={videoUrl} download className="btn-generate" style={{ flex: 1, textAlign: 'center', textDecoration: 'none' }}>
              <Download size={18} /> Tải Video MP4
            </a>
            {srtUrl && (
              <a href={srtUrl} download className="btn-outline" style={{ textDecoration: 'none' }}>
                <Download size={14} /> Tải Phụ đề (.srt)
              </a>
            )}
            <button className="btn-outline" onClick={handleReset}>
              <RotateCcw size={14} /> Tạo Video Mới
            </button>
            <button className="btn-outline" onClick={() => setStep('editor')}>
              <PenLine size={14} /> Chỉnh sửa & Render lại
            </button>
          </div>
        </div>
      )}

    </div>
  );
}
