import React, { useState, useRef, useCallback } from 'react';
import axios from 'axios';
import {
  Film, Play, Loader2, CheckCircle, Sparkles, Mic, Video, Wand2, Key,
  ImagePlus, Music, Upload, X, FileText, Brain, Camera, SlidersHorizontal,
  MonitorPlay, Square, Smartphone
} from 'lucide-react';

const API_BASE = "http://127.0.0.1:8000";

const MODES = [
  {
    id: 'storyteller',
    icon: <Wand2 size={22} />,
    label: 'AI Storyteller',
    desc: 'Nhập chủ đề → AI viết kịch bản, sinh ảnh, render video tự động',
    color: '#f59e0b',
  },
  {
    id: 'photo_narration',
    icon: <Camera size={22} />,
    label: 'Ảnh → Video',
    desc: 'Upload ảnh của bạn → AI viết lời bình và kể chuyện cho từng ảnh',
    color: '#3b82f6',
  },
  {
    id: 'photo_slideshow',
    icon: <ImagePlus size={22} />,
    label: 'Slideshow',
    desc: 'Upload ảnh → Video cinematic với nhạc nền, hiệu ứng Ken Burns',
    color: '#8b5cf6',
  },
  {
    id: 'script_video',
    icon: <FileText size={22} />,
    label: 'Script → Video',
    desc: 'Paste script viết sẵn → AI chia cảnh, sinh ảnh, đọc lời cho bạn',
    color: '#10b981',
  },
  {
    id: 'quiz_listicle',
    icon: <Brain size={22} />,
    label: 'Quiz / Listicle',
    desc: 'Nhập chủ đề → AI sinh video dạng "Top N" hoặc hỏi-đáp',
    color: '#ec4899',
  },
];

const ART_STYLES = [
  { value: 'Cinematic', label: 'Cinematic (Điện ảnh)' },
  { value: 'Anime', label: 'Anime (Hoạt hình)' },
  { value: 'Realistic', label: 'Realistic (Chân thực)' },
  { value: '3D Render', label: '3D Render (Khối 3D)' },
  { value: 'Watercolor', label: 'Watercolor (Màu nước)' },
  { value: 'Comic Book', label: 'Comic Book (Truyện tranh)' },
];

const ASPECT_RATIOS = [
  { value: '9:16', label: '9:16 Dọc', desc: 'TikTok / Reels', icon: <Smartphone size={14} /> },
  { value: '16:9', label: '16:9 Ngang', desc: 'YouTube', icon: <MonitorPlay size={14} /> },
  { value: '1:1', label: '1:1 Vuông', desc: 'Instagram', icon: <Square size={14} /> },
];

export default function App() {
  // ── Mode & Input state ──
  const [mode, setMode] = useState('storyteller');
  const [topic, setTopic] = useState('');
  const [scriptText, setScriptText] = useState('');
  const [numScenes, setNumScenes] = useState(6);
  const [aspectRatio, setAspectRatio] = useState('9:16');

  // ── Advanced settings ──
  const [apiKey, setApiKey] = useState('');
  const [voice, setVoice] = useState('vi-VN-HoaiMyNeural');
  const [artStyle, setArtStyle] = useState('Cinematic');
  const [bgmTrack, setBgmTrack] = useState('');
  const [speechRate, setSpeechRate] = useState('+0%');
  const [showAdvanced, setShowAdvanced] = useState(false);

  // ── Image upload state ──
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [uploadPreviews, setUploadPreviews] = useState([]);
  const [uploadSessionId, setUploadSessionId] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef(null);

  // ── Job state ──
  const [status, setStatus] = useState('idle');
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState('');
  const [videoUrl, setVideoUrl] = useState(null);
  const [srtUrl, setSrtUrl] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [script, setScript] = useState([]);

  // ── BGM list ──
  const [bgmList, setBgmList] = useState([]);
  const [bgmLoaded, setBgmLoaded] = useState(false);

  const wsRef = useRef(null);
  const dragCountRef = useRef(0);
  const [isDragging, setIsDragging] = useState(false);

  // ── Load BGM list on first render ──
  React.useEffect(() => {
    if (!bgmLoaded) {
      axios.get(`${API_BASE}/api/bgm-list`).then(res => {
        setBgmList(res.data.tracks || []);
        setBgmLoaded(true);
      }).catch(() => setBgmLoaded(true));
    }
  }, [bgmLoaded]);

  // ── Modes that need photo upload ──
  const needsUpload = mode === 'photo_narration' || mode === 'photo_slideshow';
  const needsTopic = mode === 'storyteller' || mode === 'quiz_listicle';
  const needsScript = mode === 'script_video';
  const needsSceneCount = mode === 'storyteller' || mode === 'quiz_listicle' || mode === 'script_video';

  // ── Image upload handlers ──
  const handleFileSelect = useCallback((files) => {
    const newFiles = Array.from(files).filter(f => f.type.startsWith('image/'));
    if (newFiles.length === 0) return;

    const combined = [...uploadedFiles, ...newFiles].slice(0, 20);
    setUploadedFiles(combined);

    // Generate previews
    const newPreviews = [...uploadPreviews];
    newFiles.forEach(file => {
      const reader = new FileReader();
      reader.onload = (e) => {
        setUploadPreviews(prev => [...prev, { name: file.name, src: e.target.result }].slice(0, 20));
      };
      reader.readAsDataURL(file);
    });
  }, [uploadedFiles, uploadPreviews]);

  const removeImage = (index) => {
    setUploadedFiles(prev => prev.filter((_, i) => i !== index));
    setUploadPreviews(prev => prev.filter((_, i) => i !== index));
    setUploadSessionId(null);
  };

  const handleDragEnter = (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragCountRef.current++;
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragCountRef.current--;
    if (dragCountRef.current === 0) setIsDragging(false);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragCountRef.current = 0;
    setIsDragging(false);
    if (e.dataTransfer.files?.length > 0) {
      handleFileSelect(e.dataTransfer.files);
    }
  };

  // ── Upload images to server ──
  const uploadImagesToServer = async () => {
    if (uploadedFiles.length === 0) return null;
    if (uploadSessionId) return uploadSessionId; // already uploaded

    setIsUploading(true);
    try {
      const formData = new FormData();
      uploadedFiles.forEach(f => formData.append('images', f));
      const res = await axios.post(`${API_BASE}/api/upload-images`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const sid = res.data.session_id;
      setUploadSessionId(sid);
      setIsUploading(false);
      return sid;
    } catch (err) {
      setIsUploading(false);
      throw new Error(err.response?.data?.detail || 'Upload ảnh thất bại.');
    }
  };

  // ── Generate video ──
  const handleGenerate = async () => {
    setErrorMsg('');
    setVideoUrl(null);
    setSrtUrl(null);
    setScript([]);
    setStatus('pending');
    setProgress(0);

    try {
      // Upload images if needed
      let sessionId = uploadSessionId;
      if (needsUpload) {
        if (uploadedFiles.length === 0) {
          throw new Error('Vui lòng upload ít nhất 1 ảnh.');
        }
        sessionId = await uploadImagesToServer();
      }

      const payload = {
        mode,
        topic: topic || '',
        num_scenes: numScenes,
        aspect_ratio: aspectRatio,
        gemini_api_key: apiKey || null,
        voice,
        art_style: artStyle,
        bgm_track: bgmTrack || null,
        speech_rate: speechRate,
        script_text: needsScript ? scriptText : null,
        upload_session_id: needsUpload ? sessionId : null,
      };

      const res = await axios.post(`${API_BASE}/api/generate-video`, payload);
      startWebSocket(res.data.job_id);
    } catch (err) {
      setStatus('error');
      setErrorMsg(err.response?.data?.detail || err.message || 'Lỗi từ server.');
    }
  };

  const startWebSocket = (jobId) => {
    if (wsRef.current) wsRef.current.close();
    const ws = new WebSocket(`ws://127.0.0.1:8000/api/ws/job-status/${jobId}`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const job = JSON.parse(event.data);
      setStatus(job.status);
      setProgress(job.progress);
      setMessage(job.message);
      if (job.scenes?.length > 0) setScript(job.scenes);
      if (job.status === 'done') {
        ws.close();
        setVideoUrl(`${API_BASE}${job.video_url}`);
        if (job.srt_url) setSrtUrl(`${API_BASE}${job.srt_url}`);
      }
      if (job.status === 'error') {
        ws.close();
        setErrorMsg(job.error);
      }
    };

    ws.onerror = () => {
      ws.close();
      setStatus('error');
      setErrorMsg("Mất kết nối tới server (WebSocket lỗi).");
    };
  };

  const isProcessing = ['pending', 'generating_script', 'generating_assets', 'rendering'].includes(status);

  const canGenerate = () => {
    if (isProcessing) return false;
    if (needsTopic && !topic.trim()) return false;
    if (needsScript && !scriptText.trim()) return false;
    if (needsUpload && uploadedFiles.length === 0) return false;
    return true;
  };

  return (
    <div className="app-wrapper">

      {/* ── HEADER ── */}
      <header className="app-header">
        <div className="header-icon-wrap">
          <Film size={26} />
        </div>
        <div>
          <h1 className="header-title">AI Video Studio</h1>
          <p className="header-sub">Xưởng sản xuất Video Tự động — 5 chế độ · Đa nền tảng</p>
        </div>
        <div className="status-bar" style={{ marginLeft: 'auto' }}>
          <span className="status-chip chip-green"><span className="chip-dot" />Backend Online</span>
          <span className="status-chip chip-blue"><span className="chip-dot" />Gemini API</span>
        </div>
      </header>

      {/* ── MODE SELECTOR ── */}
      <div className="card mode-selector-card">
        <p className="workflow-title">Chọn chế độ sản xuất</p>
        <div className="mode-grid">
          {MODES.map(m => (
            <button
              key={m.id}
              className={`mode-card ${mode === m.id ? 'mode-active' : ''}`}
              onClick={() => {
                setMode(m.id);
                setErrorMsg('');
              }}
              style={{ '--mode-color': m.color }}
            >
              <div className="mode-icon">{m.icon}</div>
              <div className="mode-label">{m.label}</div>
              <div className="mode-desc">{m.desc}</div>
            </button>
          ))}
        </div>
      </div>

      {/* ── MAIN GRID ── */}
      <div className="main-grid">

        {/* LEFT — Control Panel */}
        <div className="card" style={{ alignSelf: 'start' }}>
          <div className="card-top-bar" />

          {/* ── Input Section (mode-dependent) ── */}
          <div className="section-label">
            <div className="step-badge">1</div>
            <span className="section-title">
              {needsUpload ? 'Upload ảnh của bạn' : needsScript ? 'Nhập kịch bản' : 'Nội dung Kịch bản'}
            </span>
          </div>

          {/* Topic input (storyteller, quiz, photo_narration optional) */}
          {(needsTopic || mode === 'photo_narration') && (
            <div className="form-group">
              <label className="form-label">
                {mode === 'photo_narration' ? 'Chủ đề gợi ý (tùy chọn)' : 'Ý tưởng / Chủ đề'}
              </label>
              <textarea
                className="form-textarea"
                value={topic}
                onChange={e => setTopic(e.target.value)}
                placeholder={
                  mode === 'quiz_listicle'
                    ? 'Ví dụ: Top 5 sự thật thú vị về vũ trụ...'
                    : mode === 'photo_narration'
                    ? 'Ví dụ: Kỷ niệm chuyến du lịch Đà Lạt 2024...'
                    : 'Ví dụ: Làm video 1 phút giới thiệu Căn hộ dịch vụ...'
                }
              />
            </div>
          )}

          {/* Script input */}
          {needsScript && (
            <div className="form-group">
              <label className="form-label">Nội dung kịch bản</label>
              <textarea
                className="form-textarea"
                style={{ height: 200 }}
                value={scriptText}
                onChange={e => setScriptText(e.target.value)}
                placeholder="Paste nội dung script bạn đã viết sẵn vào đây. AI sẽ tự chia cảnh, sinh ảnh minh họa và đọc lời cho bạn..."
              />
            </div>
          )}

          {/* Image upload zone */}
          {needsUpload && (
            <div className="form-group">
              <div
                className={`upload-zone ${isDragging ? 'upload-zone-active' : ''}`}
                onDragEnter={handleDragEnter}
                onDragLeave={handleDragLeave}
                onDragOver={handleDragOver}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  multiple
                  style={{ display: 'none' }}
                  onChange={(e) => handleFileSelect(e.target.files)}
                />
                <Upload size={28} className="upload-icon" />
                <p className="upload-text">Kéo thả ảnh vào đây hoặc click để chọn</p>
                <p className="upload-hint">JPG, PNG, WebP · Tối đa 20 ảnh · Mỗi ảnh ≤ 10MB</p>
              </div>

              {/* Image preview grid */}
              {uploadPreviews.length > 0 && (
                <div className="image-grid">
                  {uploadPreviews.map((img, i) => (
                    <div key={i} className="image-thumb">
                      <img src={img.src} alt={img.name} />
                      <button className="image-remove" onClick={(e) => { e.stopPropagation(); removeImage(i); }}>
                        <X size={12} />
                      </button>
                      <span className="image-index">{i + 1}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="divider" />

          {/* ── Settings Section ── */}
          <div className="section-label">
            <div className="step-badge" style={{ color: '#ec4899', borderColor: '#ec489940', background: '#ec489910' }}>2</div>
            <span className="section-title">Cài đặt</span>
          </div>

          {/* Aspect Ratio */}
          <div className="form-group">
            <label className="form-label">Tỉ lệ khung hình</label>
            <div className="aspect-ratio-group">
              {ASPECT_RATIOS.map(ar => (
                <button
                  key={ar.value}
                  className={`ar-btn ${aspectRatio === ar.value ? 'ar-active' : ''}`}
                  onClick={() => setAspectRatio(ar.value)}
                >
                  {ar.icon}
                  <span>{ar.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Scene count slider */}
          {needsSceneCount && (
            <div className="form-group">
              <label className="form-label">Số cảnh: <strong style={{ color: '#f59e0b' }}>{numScenes}</strong></label>
              <div className="slider-wrap">
                <span className="slider-label">4</span>
                <input
                  type="range"
                  min="4"
                  max="20"
                  value={numScenes}
                  onChange={e => setNumScenes(Number(e.target.value))}
                  className="scene-slider"
                />
                <span className="slider-label">20</span>
              </div>
              <p className="form-hint">
                {numScenes <= 6 ? '~30-60s (ngắn)' : numScenes <= 12 ? '~1-2 phút (trung bình)' : '~2-5 phút (dài)'}
              </p>
            </div>
          )}

          <div style={{ display: 'flex', gap: '16px', marginBottom: '16px' }}>
            <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
              <label className="form-label">Giọng đọc</label>
              <select className="form-input" value={voice} onChange={e => setVoice(e.target.value)} style={{ appearance: 'auto', backgroundColor: 'rgba(0,0,0,0.2)' }}>
                <option value="vi-VN-HoaiMyNeural">Nữ - Hoài My</option>
                <option value="vi-VN-NamMinhNeural">Nam - Nam Minh</option>
              </select>
            </div>
            <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
              <label className="form-label">Phong cách ảnh</label>
              <select className="form-input" value={artStyle} onChange={e => setArtStyle(e.target.value)} style={{ appearance: 'auto', backgroundColor: 'rgba(0,0,0,0.2)' }}>
                {ART_STYLES.map(s => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </div>
          </div>

          {/* BGM selector */}
          <div className="form-group">
            <label className="form-label"><Music size={12} style={{ verticalAlign: 'middle' }} /> Nhạc nền</label>
            <select className="form-input" value={bgmTrack} onChange={e => setBgmTrack(e.target.value)} style={{ appearance: 'auto', backgroundColor: 'rgba(0,0,0,0.2)' }}>
              <option value="">Không dùng nhạc nền</option>
              {bgmList.map(b => (
                <option key={b.id} value={b.id}>{b.name}</option>
              ))}
            </select>
          </div>

          {/* Advanced toggle */}
          <button className="advanced-toggle" onClick={() => setShowAdvanced(!showAdvanced)}>
            <SlidersHorizontal size={14} />
            {showAdvanced ? 'Ẩn nâng cao' : 'Hiện nâng cao'}
          </button>

          {showAdvanced && (
            <div className="advanced-section">
              <div className="form-group">
                <label className="form-label">Tốc độ đọc (TTS)</label>
                <select className="form-input" value={speechRate} onChange={e => setSpeechRate(e.target.value)} style={{ appearance: 'auto', backgroundColor: 'rgba(0,0,0,0.2)' }}>
                  <option value="-20%">Rất chậm (-20%)</option>
                  <option value="-10%">Chậm (-10%)</option>
                  <option value="+0%">Bình thường</option>
                  <option value="+10%">Nhanh (+10%)</option>
                  <option value="+20%">Rất nhanh (+20%)</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label"><Key size={12} style={{ verticalAlign: 'middle' }} /> Gemini API Key (Tùy chọn)</label>
                <input
                  type="password"
                  className="form-input"
                  value={apiKey}
                  onChange={e => setApiKey(e.target.value)}
                  placeholder="Lấy miễn phí tại aistudio.google.com"
                />
              </div>
            </div>
          )}

          <div style={{ marginTop: 24 }}>
            <button
              className="btn-generate"
              onClick={handleGenerate}
              disabled={!canGenerate()}
            >
              {isProcessing ? (
                <><Loader2 size={20} className="spin" /> Đang xử lý... {progress}%</>
              ) : isUploading ? (
                <><Loader2 size={20} className="spin" /> Đang upload ảnh...</>
              ) : (
                <><Play size={20} fill="currentColor" /> Sản Xuất Video Ngay</>
              )}
            </button>
          </div>

          {status === 'error' && (
            <div className="error-box">⚠ {errorMsg}</div>
          )}
        </div>

        {/* RIGHT — Preview Panel */}
        <div className="preview-panel">

          <div className="card preview-card">
            <div className="card-top-bar" style={{ background: 'linear-gradient(90deg, #3b82f6, #8b5cf6)' }} />

            {/* IDLE */}
            {status === 'idle' && (
              <div className="idle-state">
                <div className="idle-icon">
                  <Film size={32} opacity={0.3} />
                </div>
                <h3 className="idle-title">Chưa có Video</h3>
                <p className="idle-desc">Chọn chế độ, nhập nội dung và bấm <strong>Sản Xuất</strong> để bắt đầu.</p>
              </div>
            )}

            {/* LOADING */}
            {isProcessing && (
              <div className="loading-state">
                <div className="spinner-ring" />
                <h3 className="loading-title">{message || 'Đang xử lý...'}</h3>
                <div style={{ marginTop: 20, width: '100%', background: 'rgba(255,255,255,0.1)', height: 8, borderRadius: 4, overflow: 'hidden' }}>
                   <div style={{ width: `${progress}%`, background: 'linear-gradient(90deg, #3b82f6, #a855f7)', height: '100%', borderRadius: 4, transition: 'width 0.5s ease' }} />
                </div>
                <p style={{ marginTop: 12, fontSize: 13, color: '#aaa', fontWeight: 500 }}>Tiến trình: {progress}%</p>
              </div>
            )}

            {/* SUCCESS */}
            {status === 'done' && (
              <div className="success-state">
                <div className="success-badge">
                  <CheckCircle size={14} />
                  Kết xuất thành công
                </div>
                <div className="video-player-wrap" style={{ display: 'flex', flexDirection: 'column', gap: '10px', width: '100%', alignItems: 'center' }}>
                  {videoUrl && <video src={videoUrl} controls style={{ width: '100%', borderRadius: '8px', maxHeight: '400px' }} />}
                  <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', justifyContent: 'center' }}>
                    <a href={videoUrl} download className="download-btn">⬇️ Tải Video</a>
                    {srtUrl && <a href={srtUrl} download className="download-btn">⬇️ Tải Phụ đề (.srt)</a>}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Script preview */}
          {script.length > 0 && (
            <div className="card" style={{ padding: '20px 24px' }}>
              <div className="section-label" style={{ marginBottom: 14 }}>
                <div className="step-badge" style={{ color: '#10b981', borderColor: '#10b98140', background: '#10b98110' }}>
                  <Sparkles size={12} />
                </div>
                <span className="section-title" style={{ fontSize: '0.9rem' }}>Kịch bản được tạo ({script.length} cảnh)</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxHeight: 400, overflowY: 'auto' }}>
                {script.map((scene, i) => (
                  <div key={i} className="script-scene-card">
                    <div className="script-scene-num">Cảnh {scene.scene}</div>
                    <div className="script-scene-text">{scene.text}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
