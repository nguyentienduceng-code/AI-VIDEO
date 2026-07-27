import React, { useRef } from 'react';
import { Upload, X, Image } from 'lucide-react';
import { useShallow } from 'zustand/react/shallow';
import { useAppStore, needsUpload as needsUploadFor, needsScript as needsScriptFor, needsTopic as needsTopicFor } from '../store';
import { API_BASE } from '../constants';

export default function InputSection() {
  const ctx = useAppStore(useShallow((s) => ({
    activeMode: s.activeMode,
    topic: s.topic, setTopic: s.setTopic,
    scriptText: s.scriptText, setScriptText: s.setScriptText,
    characterDescription: s.characterDescription, setCharacterDescription: s.setCharacterDescription,
    uploadSessionId: s.uploadSessionId, setUploadSessionId: s.setUploadSessionId,
    uploadedFiles: s.uploadedFiles, setUploadedFiles: s.setUploadedFiles,
    uploadLoading: s.uploadLoading, setUploadLoading: s.setUploadLoading,
    coverImageSessionId: s.coverImageSessionId, setCoverImageSessionId: s.setCoverImageSessionId,
    coverImageName: s.coverImageName, setCoverImageName: s.setCoverImageName,
    coverImageLoading: s.coverImageLoading, setCoverImageLoading: s.setCoverImageLoading,
    coverImagePosition: s.coverImagePosition, setCoverImagePosition: s.setCoverImagePosition,
    setNumScenes: s.setNumScenes,
    setErrorMsg: s.setErrorMsg,
  })));
  const needsUpload = needsUploadFor(ctx.activeMode);
  const needsScript = needsScriptFor(ctx.activeMode);
  const needsTopic = needsTopicFor(ctx.activeMode);
  const fileInputRef = useRef(null);
  const coverInputRef = useRef(null);

  const handleUpload = async (e) => {
    const files = Array.from(e.target.files);
    if (!files.length) return;
    ctx.setUploadLoading(true);
    ctx.setErrorMsg('');
    const formData = new FormData();
    files.forEach(f => formData.append('images', f));
    try {
      const res = await fetch(`${API_BASE}/api/upload-images`, { method: 'POST', body: formData });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Upload lỗi');
      }
      const data = await res.json();
      ctx.setUploadSessionId(data.session_id);
      ctx.setUploadedFiles(files.map(f => f.name));
      ctx.setNumScenes(files.length);
    } catch (err) {
      ctx.setErrorMsg(err.message);
    } finally {
      ctx.setUploadLoading(false);
    }
  };

  const handleCoverUpload = async (e) => {
    const files = Array.from(e.target.files);
    if (!files.length) return;
    ctx.setCoverImageLoading(true);
    ctx.setErrorMsg('');
    const formData = new FormData();
    formData.append('images', files[0]);
    try {
      const res = await fetch(`${API_BASE}/api/upload-images`, { method: 'POST', body: formData });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Upload ảnh bìa lỗi');
      }
      const data = await res.json();
      ctx.setCoverImageSessionId(data.session_id);
      ctx.setCoverImageName(files[0].name);
    } catch (err) {
      ctx.setErrorMsg(err.message);
    } finally {
      ctx.setCoverImageLoading(false);
    }
  };

  const showCoverUpload = ctx.activeMode === 'storyteller' || ctx.activeMode === 'quiz' || ctx.activeMode === 'script';

  return (
    <div className="input-section-inner">
      <div className="step-header">
        <div className="step-badge step-2">2</div>
        <span className="step-title">{needsUpload ? 'Upload Ảnh' : needsScript ? 'Nhập Kịch bản' : 'Ý Tưởng / Chủ Đề'}</span>
      </div>

      {needsTopic && (
        <div className="input-group">
          <label className="field-label">
            {ctx.activeMode === 'manual' ? 'TÊN VIDEO / CHỦ ĐỀ' : 'CHỦ ĐỀ VIDEO'}
          </label>
          <textarea 
            className="form-textarea" 
            value={ctx.topic} 
            onChange={e => ctx.setTopic(e.target.value)} 
            placeholder={ctx.activeMode === 'manual' ? 'VD: Video thủ công về thiên nhiên...' : 'VD: 5 sự thật thú vị về vũ trụ mà bạn chưa biết...'} 
            rows={4} 
          />
        </div>
      )}
      
      {ctx.activeMode === 'storyteller' && (
        <div className="input-group" style={{ marginTop: 16 }}>
          <label className="field-label">MÔ TẢ NHÂN VẬT (CHARACTER REFERENCE)</label>
          <textarea 
            className="form-textarea" 
            value={ctx.characterDescription} 
            onChange={e => ctx.setCharacterDescription(e.target.value)} 
            placeholder="VD: Cô gái tóc ngắn đen..." 
            rows={2} 
          />
        </div>
      )}

      {showCoverUpload && (
        <div className="input-group" style={{ marginTop: 16 }}>
          <label className="field-label">📚 ẢNH BÌA SẢN PHẨM (Tùy chọn)</label>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: '4px 0 8px' }}>
            Upload ảnh bìa sách, sản phẩm, hoặc hình đại diện → AI sẽ tự chèn vào cảnh mở đầu video.
          </p>
          <input 
            ref={coverInputRef} 
            type="file" 
            accept="image/jpeg,image/png,image/webp" 
            onChange={handleCoverUpload} 
            style={{ display: 'none' }} 
          />
          {!ctx.coverImageSessionId ? (
            <button 
              className="ratio-btn" 
              onClick={() => coverInputRef.current?.click()}
              style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%', justifyContent: 'center', padding: '10px 16px' }}
            >
              <Image size={16} /> Chọn ảnh bìa
            </button>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div className="upload-done">
                <span>📎 {ctx.coverImageName}</span>
                <button className="btn-icon" onClick={() => { ctx.setCoverImageSessionId(null); ctx.setCoverImageName(''); }}>
                  <X size={16} />
                </button>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: '0.85rem', color: '#888' }}>Vị trí chèn:</span>
                <select 
                  className="form-select" 
                  value={ctx.coverImagePosition}
                  onChange={e => ctx.setCoverImagePosition(e.target.value)}
                  style={{ flex: 1, padding: '4px 8px' }}
                >
                  <option value="start">Chèn lên Cảnh Đầu (Start)</option>
                  <option value="end">Chèn lên Cảnh Cuối (End)</option>
                  <option value="both">Cả Đầu và Cuối</option>
                </select>
              </div>
            </div>
          )}
          {ctx.coverImageLoading && <div className="upload-loading">Đang upload ảnh bìa...</div>}
        </div>
      )}
      
      {needsScript && (
        <div className="input-group">
          <label className="field-label">KỊCH BẢN CỦA BẠN</label>
          <textarea 
            className="form-textarea" 
            value={ctx.scriptText} 
            onChange={e => ctx.setScriptText(e.target.value)} 
            placeholder="Paste toàn bộ script vào đây..." 
            rows={6} 
            style={{ minHeight: 160 }} 
          />
        </div>
      )}
      
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
          {ctx.uploadedFiles.length === 0 ? (
            <div className="upload-placeholder" onClick={() => fileInputRef.current?.click()}>
              <Upload size={32} />
              <p>Nhấn để chọn ảnh (JPG, PNG, WebP)</p>
              <span>Tối đa 20 ảnh, mỗi ảnh ≤ 10MB</span>
            </div>
          ) : (
            <div className="upload-done">
              <span>Đã upload {ctx.uploadedFiles.length} ảnh</span>
              <button className="btn-icon" onClick={() => { ctx.setUploadedFiles([]); ctx.setUploadSessionId(null); }}>
                <X size={16} />
              </button>
            </div>
          )}
          {ctx.uploadLoading && <div className="upload-loading">Đang upload...</div>}
        </div>
      )}
    </div>
  );
}
