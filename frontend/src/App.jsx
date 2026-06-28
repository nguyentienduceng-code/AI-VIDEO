import React, { useState } from 'react';
import axios from 'axios';
import {
  Film, Play, Loader2, CheckCircle, Sparkles, Mic, Video, Wand2, Key
} from 'lucide-react';

export default function App() {
  const [topic, setTopic] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [voice, setVoice] = useState('vi-VN-HoaiMyNeural');
  const [artStyle, setArtStyle] = useState('Cinematic');
  const [status, setStatus] = useState('idle'); // idle | pending | generating_script | generating_assets | rendering | done | error
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState('');
  const [videoUrl, setVideoUrl] = useState(null);
  const [srtUrl, setSrtUrl] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [script, setScript] = useState([]);

  const pollingRef = React.useRef(null);
  const API_BASE = "http://127.0.0.1:8000";

  const handleGenerate = async () => {
    if (!topic.trim()) return;
    setErrorMsg('');
    setVideoUrl(null);
    setScript([]);
    setStatus('pending');
    setProgress(0);

    try {
      const res = await axios.post(`${API_BASE}/api/generate-video`, {
        topic,
        gemini_api_key: apiKey || null,
        voice,
        art_style: artStyle,
      });
      startPolling(res.data.job_id);
    } catch (err) {
      setStatus('error');
      setErrorMsg(err.response?.data?.detail || err.message || 'Lỗi từ server.');
    }
  };

  const startPolling = (jobId) => {
    if (pollingRef.current) clearInterval(pollingRef.current);

    pollingRef.current = setInterval(async () => {
      try {
        const res = await axios.get(`${API_BASE}/api/job-status/${jobId}`);
        const job = res.data;
        setStatus(job.status);
        setProgress(job.progress);
        setMessage(job.message);

        if (job.status === 'done') {
          clearInterval(pollingRef.current);
          setVideoUrl(`${API_BASE}${job.video_url}`);
          setSrtUrl(`${API_BASE}${job.srt_url}`);
          if (job.scenes) {
            setScript(job.scenes);
          }
        }

        if (job.status === 'error') {
          clearInterval(pollingRef.current);
          setErrorMsg(job.error);
        }
      } catch (err) {
        clearInterval(pollingRef.current);
        setStatus('error');
        setErrorMsg(err.message);
      }
    }, 1000);
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
          <p className="header-sub">Xưởng sản xuất Video Tự động — Cá nhân · Miễn phí</p>
        </div>

        {/* Status chips */}
        <div className="status-bar" style={{ marginLeft: 'auto' }}>
          <span className="status-chip chip-green">
            <span className="chip-dot" />
            Backend Online
          </span>
          <span className="status-chip chip-blue">
            <span className="chip-dot" />
            Gemini API
          </span>
        </div>
      </header>

      {/* ── WORKFLOW BANNER ── */}
      <div className="card workflow-card">
        <p className="workflow-title">Quy trình tự động hóa</p>
        <div className="workflow-steps">
          {[
            { icon: <Wand2 size={13} />, label: 'Gemini\nViết kịch bản', color: '#f59e0b' },
            { icon: <Mic size={13} />, label: 'Edge TTS\nGiọng đọc AI', color: '#3b82f6' },
            { icon: <Sparkles size={13} />, label: 'Imagen\nSinh hình ảnh', color: '#8b5cf6' },
            { icon: <Video size={13} />, label: 'MoviePy\nRender MP4', color: '#10b981' },
          ].map((s, i) => (
            <div className="wf-step" key={i}>
              <div className="wf-icon" style={{ color: s.color, borderColor: s.color + '40', background: s.color + '10' }}>
                {s.icon}
              </div>
              <span className="wf-label" style={{ whiteSpace: 'pre-line' }}>{s.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── MAIN GRID ── */}
      <div className="main-grid">

        {/* LEFT — Control Panel */}
        <div className="card" style={{ alignSelf: 'start' }}>
          <div className="card-top-bar" />

          <div className="section-label">
            <div className="step-badge">1</div>
            <span className="section-title">Nội dung Kịch bản</span>
          </div>

          <div className="form-group">
            <label className="form-label">Ý tưởng / Chủ đề</label>
            <textarea
              className="form-textarea"
              value={topic}
              onChange={e => setTopic(e.target.value)}
              placeholder="Ví dụ: Làm 1 video ngắn 30s giới thiệu Căn hộ dịch vụ tại Tân Bình, nhấn mạnh tiện ích full nội thất, giờ giấc tự do, giá tốt..."
            />
          </div>

          <div className="divider" />
          
          <div className="section-label">
            <div className="step-badge" style={{ color: '#ec4899', borderColor: '#ec489940', background: '#ec489910' }}>
              2
            </div>
            <span className="section-title">Tuỳ chỉnh Nâng cao</span>
          </div>

          <div style={{ display: 'flex', gap: '16px', marginBottom: '16px' }}>
            <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
              <label className="form-label">Giọng đọc (Voice)</label>
              <select className="form-input" value={voice} onChange={e => setVoice(e.target.value)} style={{ appearance: 'auto', backgroundColor: 'rgba(0,0,0,0.2)' }}>
                <option value="vi-VN-HoaiMyNeural">Nữ - Hoài My</option>
                <option value="vi-VN-NamMinhNeural">Nam - Nam Minh</option>
              </select>
            </div>
            <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
              <label className="form-label">Phong cách (Art Style)</label>
              <select className="form-input" value={artStyle} onChange={e => setArtStyle(e.target.value)} style={{ appearance: 'auto', backgroundColor: 'rgba(0,0,0,0.2)' }}>
                <option value="Cinematic">Cinematic (Điện ảnh)</option>
                <option value="Anime">Anime (Hoạt hình)</option>
                <option value="Realistic">Realistic (Chân thực)</option>
                <option value="3D Render">3D Render (Khối 3D)</option>
              </select>
            </div>
          </div>

          <div className="divider" />

          <div className="section-label" style={{ marginBottom: 12 }}>
            <div className="step-badge" style={{ color: '#a78bfa', borderColor: '#a78bfa40', background: '#a78bfa10' }}>
              <Key size={12} />
            </div>
            <span className="section-title">API Key</span>
          </div>

          <div className="form-group">
            <label className="form-label">Gemini API Key (Tùy chọn)</label>
            <input
              type="password"
              className="form-input"
              value={apiKey}
              onChange={e => setApiKey(e.target.value)}
              placeholder="Lấy miễn phí tại aistudio.google.com"
            />
          </div>

          <div style={{ marginTop: 24 }}>
            <button
              className="btn-generate"
              onClick={handleGenerate}
              disabled={['pending', 'generating_script', 'generating_assets', 'rendering'].includes(status) || !topic.trim()}
            >
              {['pending', 'generating_script', 'generating_assets', 'rendering'].includes(status) ? (
                <><Loader2 size={20} className="spin" /> Đang xử lý... {progress}%</>
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

          {/* Preview Card */}
          <div className="card preview-card">
            <div className="card-top-bar" style={{ background: 'linear-gradient(90deg, #3b82f6, #8b5cf6)' }} />

            {/* IDLE */}
            {status === 'idle' && (
              <div className="idle-state">
                <div className="idle-icon">
                  <Film size={32} opacity={0.3} />
                </div>
                <h3 className="idle-title">Chưa có Video</h3>
                <p className="idle-desc">Nhập ý tưởng bên trái và bấm <strong>Sản Xuất</strong> để hệ thống bắt đầu làm việc.</p>
              </div>
            )}

            {/* LOADING */}
            {['pending', 'generating_script', 'generating_assets', 'rendering'].includes(status) && (
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
                  <div style={{ display: 'flex', gap: '10px' }}>
                    <a href={videoUrl} download style={{ padding: '6px 12px', background: 'rgba(255,255,255,0.1)', borderRadius: '6px', color: '#fff', textDecoration: 'none', fontSize: '0.85rem' }}>⬇️ Tải Video</a>
                    <a href={srtUrl} download style={{ padding: '6px 12px', background: 'rgba(255,255,255,0.1)', borderRadius: '6px', color: '#fff', textDecoration: 'none', fontSize: '0.85rem' }}>⬇️ Tải Phụ đề (.srt)</a>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Script preview card (show if success) */}
          {status === 'done' && script.length > 0 && (
            <div className="card" style={{ padding: '20px 24px' }}>
              <div className="section-label" style={{ marginBottom: 14 }}>
                <div className="step-badge" style={{ color: '#10b981', borderColor: '#10b98140', background: '#10b98110' }}>
                  <Sparkles size={12} />
                </div>
                <span className="section-title" style={{ fontSize: '0.9rem' }}>Kịch bản được tạo</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {script.map((scene, i) => (
                  <div key={i} style={{
                    background: 'rgba(0,0,0,0.25)',
                    border: '1px solid rgba(255,255,255,0.06)',
                    borderRadius: 8,
                    padding: '10px 14px',
                  }}>
                    <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#f59e0b', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.6px' }}>
                      Cảnh {scene.scene}
                    </div>
                    <div style={{ fontSize: '0.9rem', color: '#cbd5e1', lineHeight: 1.5 }}>{scene.text}</div>
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
