import React, { useState, useEffect } from 'react';
import { AlertTriangle, RotateCcw, Check, Download, PenLine, Clock } from 'lucide-react';
import { useAppContext } from '../AppContext';

export default function RenderProgress() {
  const ctx = useAppContext();
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    let interval;
    if (ctx.step === 'rendering' && !ctx.errorMsg) {
      interval = setInterval(() => {
        setElapsed(prev => prev + 1);
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [ctx.step, ctx.errorMsg]);

  const formatTime = (secs) => {
    const m = Math.floor(secs / 60).toString().padStart(2, '0');
    const s = (secs % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  };

  if (ctx.step === 'done') {
    return (
      <div className="done-panel">
        <div className="done-video-wrap">
          <video src={ctx.videoUrl} controls autoPlay style={{ width: '100%', height: '100%', objectFit: 'contain', borderRadius: 12 }} />
        </div>
        <div className="done-actions">
          <a href={ctx.videoUrl} download className="btn-generate" style={{ flex: 1, textAlign: 'center', textDecoration: 'none' }}>
            <Download size={18} /> Tải Video MP4
          </a>
          {ctx.srtUrl && (
            <a href={ctx.srtUrl} download className="btn-outline" style={{ textDecoration: 'none' }}>
              <Download size={14} /> Tải Phụ đề (.srt)
            </a>
          )}
          <button className="btn-outline" onClick={ctx.handleReset}>
            <RotateCcw size={14} /> Tạo Video Mới
          </button>
          <button className="btn-outline" onClick={() => ctx.setStep('editor')}>
            <PenLine size={14} /> Chỉnh sửa & Render lại
          </button>
        </div>
        <div style={{ textAlign: 'center', marginTop: 16, color: 'var(--text-muted)', fontSize: '0.9rem' }}>
          <Clock size={14} style={{verticalAlign: 'text-bottom', marginRight: 4}} />
          Thời gian hoàn thành: <strong>{formatTime(elapsed)}</strong>
        </div>
      </div>
    );
  }

  return (
    <div className="render-panel">
      <div className="render-center">
        <div style={{ fontSize: 56, marginBottom: 20 }}>🎬</div>
        <h2 style={{ marginBottom: 8 }}>Đang sản xuất video</h2>
        <p className="render-message">{ctx.jobMessage}</p>

        <div className="progress-bar-container">
          <div className="progress-bar-fill" style={{ width: `${ctx.progress}%` }} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
          <div className="progress-percent" style={{ marginTop: 0 }}>{ctx.progress}%</div>
          <div style={{ fontSize: '1.1rem', color: 'var(--text-muted)', fontWeight: 500 }}>
            <Clock size={16} style={{verticalAlign: 'text-bottom', marginRight: 6}} />
            {formatTime(elapsed)}
          </div>
        </div>

        <div className="progress-log">
          {ctx.progressLog.map((msg, i) => (
            <div key={i} className="progress-log-item">
              <Check size={12} style={{ color: 'var(--green)', flexShrink: 0 }} />
              <span>{msg}</span>
            </div>
          ))}
        </div>
      </div>

      {ctx.errorMsg && (
        <div style={{ padding: '0 40px 24px' }}>
          <div className="error-box">
            <AlertTriangle size={16} /> {ctx.errorMsg}
          </div>
          <button className="btn-outline" style={{ marginTop: 12 }} onClick={() => { ctx.setStep('editor'); ctx.setErrorMsg(''); ctx.setStatus('idle'); }}>
            <RotateCcw size={14} /> Quay lại chỉnh sửa
          </button>
        </div>
      )}
    </div>
  );
}
