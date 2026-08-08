import React, { useRef, useState, useEffect } from 'react';
import { Upload, X, Image, FileJson, FolderOpen, Sparkles, CheckCircle, Clipboard, Trash2, FileText, RotateCcw } from 'lucide-react';
import { useShallow } from 'zustand/react/shallow';
import { useAppStore, needsUpload as needsUploadFor, needsScript as needsScriptFor, needsTopic as needsTopicFor } from '../store';
import { API_BASE, BOOKTOK_API_BASE } from '../constants';
import { validateImportPayload, normalizeImportPayload } from '../lib/sharedSchema';
import { toast } from '../lib/toast.jsx';

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
    scenes: s.scenes, setScenes: s.setScenes,
    setStep: s.setStep,
    setHookText: s.setHookText, setHookQuote: s.setHookQuote,
    setCtaText: s.setCtaText, setOutroText: s.setOutroText,
    setBgm: s.setBgm, setStyle: s.setStyle, setVoice: s.setVoice,
    setContentNiche: s.setContentNiche, setEstimatedDurationS: s.setEstimatedDurationS,
  })));
  const needsUpload = needsUploadFor(ctx.activeMode);
  const needsScript = needsScriptFor(ctx.activeMode);
  const needsTopic = needsTopicFor(ctx.activeMode);
  const fileInputRef = useRef(null);
  const coverInputRef = useRef(null);
  const jsonInputRef = useRef(null);
  const [booktokFiles, setBooktokFiles] = useState([]);
  const [loadingBooktok, setLoadingBooktok] = useState(false);
  const [isDraggingJson, setIsDraggingJson] = useState(false);
  const [showPasteArea, setShowPasteArea] = useState(false);
  const [pastedJsonText, setPastedJsonText] = useState('');

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

  const [isDraggingCover, setIsDraggingCover] = useState(false);

  const processCoverUpload = async (files) => {
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

  const handleCoverUpload = (e) => {
    processCoverUpload(Array.from(e.target.files));
    e.target.value = null; // reset để có thể chọn lại cùng 1 file
  };

  useEffect(() => {
    fetch(`${BOOKTOK_API_BASE}/api/list-exports`)
      .then(res => res.json())
      .then(data => {
        if (data.files && Array.isArray(data.files)) {
          setBooktokFiles(data.files.slice(0, 8));
        }
      })
      .catch(() => {});
  }, []);

  const processImportedJsonString = (jsonStr) => {
    try {
      jsonStr = jsonStr.replace(/^```json\s*/i, '').replace(/^```\s*/, '').replace(/```\s*$/i, '').trim();
      jsonStr = jsonStr.replace(/,\s*([\]}])/g, '$1');
      const data = JSON.parse(jsonStr);

      let normalized;
      if (data.scenes && Array.isArray(data.scenes)) {
        normalized = normalizeImportPayload(data);
      } else if (Array.isArray(data)) {
        normalized = normalizeImportPayload({ scenes: data });
      } else {
        toast('Lỗi: Cấu trúc JSON không hợp lệ (không tìm thấy scenes).', { type: 'error' });
        return false;
      }

      ctx.setScenes(normalized.scenes);
      if (normalized.estimated_duration_s !== undefined) ctx.setEstimatedDurationS(normalized.estimated_duration_s);
      if (data.hook_text !== undefined) ctx.setHookText(data.hook_text);
      if (data.hook_quote !== undefined) ctx.setHookQuote(data.hook_quote);
      if (data.cta_text !== undefined) ctx.setCtaText(data.cta_text);
      if (data.recommended_bgm) ctx.setBgm(data.recommended_bgm);
      if (data.outro_text !== undefined) ctx.setOutroText(data.outro_text);

      if (data.metadata) {
        if (data.metadata.visual_style_preset) ctx.setStyle(data.metadata.visual_style_preset);
        if (data.metadata.recommended_voice) ctx.setVoice(data.metadata.recommended_voice);
        if (data.metadata.niche_category) ctx.setContentNiche(data.metadata.niche_category);
      }

      ctx.setStep('editor');
      toast(`Nhập Kịch bản JSON thành công! ${normalized.scenes.length} cảnh đã nạp.`, { type: 'success' });
      return true;
    } catch (err) {
      toast('Lỗi parse file JSON: ' + err.message, { type: 'error' });
      return false;
    }
  };

  const processImportedJsonFile = (file) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => processImportedJsonString(event.target.result);
    reader.readAsText(file);
  };

  const loadBooktokFile = async (fileName) => {
    setLoadingBooktok(true);
    try {
      const res = await fetch(`${BOOKTOK_API_BASE}/api/read-export?file=${encodeURIComponent(fileName)}`);
      if (!res.ok) throw new Error('Không đọc được file');
      const text = await res.text();
      processImportedJsonString(text);
    } catch (err) {
      toast('Lỗi nạp file từ BookTok: ' + err.message, { type: 'error' });
    } finally {
      setLoadingBooktok(false);
    }
  };

  const handlePasteFromClipboard = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (!text || !text.trim()) {
        toast("Bộ nhớ tạm (Clipboard) đang trống!", { type: 'warning' });
        setShowPasteArea(true);
        return;
      }
      processImportedJsonString(text);
    } catch (err) {
      setShowPasteArea(true);
    }
  };

  const handleClearScript = () => {
    if (window.confirm("Bạn có chắc chắn muốn xóa kịch bản hiện tại trong bộ nhớ để nạp kịch bản mới không?")) {
      ctx.setScenes([]);
      ctx.setHookText('');
      ctx.setHookQuote('');
      ctx.setCtaText('');
      ctx.setOutroText('');
      ctx.setEstimatedDurationS(0);
      ctx.setScriptText('');
      setPastedJsonText('');
      toast("Đã xóa kịch bản cũ! Bạn có thể chọn file hoặc dán JSON mới.", { type: 'info' });
    }
  };

  const handleCoverDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer.types.includes('Files')) {
      setIsDraggingCover(true);
    }
  };

  const handleCoverDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingCover(false);
  };

  const handleCoverDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingCover(false);
    const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'));
    if (files.length > 0) {
      processCoverUpload(files);
    } else if (e.dataTransfer.files.length > 0) {
      toast("Vui lòng thả file hình ảnh hợp lệ (JPG, PNG, WEBP).", { type: 'warning' });
    }
  };

  const showCoverUpload = ctx.activeMode === 'storyteller' || ctx.activeMode === 'quiz' || ctx.activeMode === 'script';

  return (
    <div className="input-section-inner">
      <div className="step-header">
        <div className="step-badge step-2">2</div>
        <span className="step-title">{needsUpload ? 'Upload Ảnh' : needsScript ? 'Nhập Kịch bản' : 'Ý Tưởng / Chủ Đề'}</span>
      </div>

      {/* 📥 KHU VỰC NHẬP FILE JSON TRỰC TIẾP TẠI BƯỚC 1 */}
      <div 
        className="input-group"
        style={{
          marginTop: 12,
          padding: 14,
          borderRadius: 12,
          border: isDraggingJson ? '2px dashed #a855f7' : '1px solid var(--border)',
          background: isDraggingJson ? 'rgba(168, 85, 247, 0.15)' : 'rgba(0,0,0,0.25)',
          transition: 'all 0.2s ease'
        }}
        onDragOver={(e) => { e.preventDefault(); setIsDraggingJson(true); }}
        onDragLeave={(e) => { e.preventDefault(); setIsDraggingJson(false); }}
        onDrop={(e) => {
          e.preventDefault();
          setIsDraggingJson(false);
          const files = Array.from(e.dataTransfer.files).filter(f => f.name.endsWith('.json'));
          if (files.length > 0) processImportedJsonFile(files[0]);
          else toast("Vui lòng thả file kịch bản .json hợp lệ.", { type: 'warning' });
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
          <label className="field-label" style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8, color: '#a855f7', fontSize: '0.85rem' }}>
            <FileJson size={18} /> NHẬP KỊCH BẢN TỪ FILE / DÁN JSON (BOOKTOK AI / MÁY TÍNH)
          </label>
        </div>
        <p style={{ fontSize: 11, color: 'var(--text-muted)', margin: '2px 0 10px' }}>
          Chọn file `.json`, kéo thả, hoặc dán trực tiếp chuỗi JSON để nạp kịch bản & cài đặt tự động.
        </p>

        <input 
          ref={jsonInputRef}
          type="file"
          accept=".json,application/json"
          onChange={(e) => {
            if (e.target.files && e.target.files[0]) {
              processImportedJsonFile(e.target.files[0]);
              e.target.value = null;
            }
          }}
          style={{ display: 'none' }}
        />

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
          <button 
            type="button"
            className="ratio-btn"
            onClick={() => jsonInputRef.current?.click()}
            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 12px', background: 'rgba(168, 85, 247, 0.15)', borderColor: 'rgba(168, 85, 247, 0.4)', color: '#d8b4fe', fontWeight: 600, fontSize: 12 }}
          >
            <FolderOpen size={15} /> Chọn file JSON
          </button>

          <button 
            type="button"
            className="ratio-btn"
            onClick={handlePasteFromClipboard}
            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 12px', background: 'rgba(59, 130, 246, 0.15)', borderColor: 'rgba(59, 130, 246, 0.4)', color: '#93c5fd', fontWeight: 600, fontSize: 12 }}
            title="Tự động đọc chuỗi JSON trong bộ nhớ tạm (Clipboard)"
          >
            <Clipboard size={15} /> Dán từ Clipboard
          </button>

          <button 
            type="button"
            className="ratio-btn"
            onClick={() => setShowPasteArea(!showPasteArea)}
            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 12px', background: 'rgba(234, 179, 8, 0.15)', borderColor: 'rgba(234, 179, 8, 0.4)', color: '#fde047', fontWeight: 600, fontSize: 12 }}
          >
            <FileText size={15} /> {showPasteArea ? 'Ẩn ô dán' : 'Ô dán JSON'}
          </button>

          {booktokFiles.length > 0 && (
            <select
              className="form-select"
              style={{ flex: 1, minWidth: 180, padding: '6px 10px', background: 'rgba(16, 185, 129, 0.15)', borderColor: 'rgba(16, 185, 129, 0.4)', color: '#6ee7b7', fontWeight: 600, fontSize: 12 }}
              onChange={(e) => {
                if (e.target.value) {
                  loadBooktokFile(e.target.value);
                  e.target.value = '';
                }
              }}
              disabled={loadingBooktok}
            >
              <option value="">⚡ Nạp từ BookTok AI ({booktokFiles.length} file gần đây)...</option>
              {booktokFiles.map((f, i) => (
                <option key={i} value={f.name}>{f.name}</option>
              ))}
            </select>
          )}
        </div>

        {/* Khung dán JSON trực tiếp */}
        {showPasteArea && (
          <div style={{ marginTop: 10, padding: 10, borderRadius: 8, background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255,255,255,0.1)' }}>
            <textarea
              className="form-textarea"
              rows={4}
              value={pastedJsonText}
              onChange={(e) => setPastedJsonText(e.target.value)}
              placeholder='Dán chuỗi JSON kịch bản vào đây (VD: { "scenes": [...] })...'
              style={{ fontSize: 12, fontFamily: 'monospace', width: '100%', marginBottom: 8 }}
            />
            <button
              type="button"
              className="btn-generate"
              style={{ padding: '8px 14px', fontSize: 12, width: '100%', background: 'linear-gradient(135deg, #a855f7 0%, #7e22ce 100%)' }}
              onClick={() => {
                if (!pastedJsonText.trim()) {
                  toast("Vui lòng dán chuỗi JSON vào ô trước khi bấm nạp.", { type: 'warning' });
                  return;
                }
                processImportedJsonString(pastedJsonText);
              }}
            >
              <Sparkles size={14} /> Nạp Kịch Bản Từ Chuỗi JSON Vừa Dán
            </button>
          </div>
        )}

        {/* Trạng thái Kịch bản trong bộ nhớ + Nút Xóa & Nạp lại */}
        {ctx.scenes && ctx.scenes.length > 0 && (
          <div style={{ marginTop: 10, padding: '8px 12px', borderRadius: 8, background: 'rgba(34, 197, 94, 0.15)', border: '1px solid rgba(34, 197, 94, 0.3)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 12, color: '#4ade80', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
              <CheckCircle size={14} /> Đã nạp kịch bản: <strong>{ctx.scenes.length} cảnh</strong>
            </span>
            <div style={{ display: 'flex', gap: 6 }}>
              <button 
                type="button"
                onClick={handleClearScript}
                style={{ background: 'rgba(239, 68, 68, 0.2)', color: '#f87171', border: '1px solid rgba(239, 68, 68, 0.4)', borderRadius: 6, padding: '4px 10px', fontSize: 11, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4 }}
                title="Xóa kịch bản cũ trong bộ nhớ để nạp lại kịch bản mới"
              >
                <Trash2 size={12} /> Xóa & Nạp lại
              </button>
              <button 
                type="button"
                onClick={() => ctx.setStep('editor')}
                style={{ background: '#22c55e', color: '#fff', border: 'none', borderRadius: 6, padding: '4px 10px', fontSize: 11, fontWeight: 700, cursor: 'pointer' }}
              >
                Chuyển Bước 2 →
              </button>
            </div>
          </div>
        )}
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
        <div 
          className="input-group" 
          style={{ marginTop: 16, position: 'relative' }}
          onDragOver={handleCoverDragOver}
          onDragLeave={handleCoverDragLeave}
          onDrop={handleCoverDrop}
        >
          {isDraggingCover && (
            <div style={{
              position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
              backgroundColor: 'rgba(34, 197, 94, 0.1)',
              border: '2px dashed var(--green)',
              zIndex: 10,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              backdropFilter: 'blur(2px)',
              borderRadius: 8,
              pointerEvents: 'none'
            }}>
              <div style={{ 
                color: 'var(--green)', fontSize: 16, fontWeight: 600,
                display: 'flex', alignItems: 'center', gap: 8,
                background: 'var(--surface)', padding: '12px 24px', borderRadius: 8,
                boxShadow: '0 4px 12px rgba(0,0,0,0.2)'
              }}>
                <Image size={24} /> Thả ảnh bìa vào đây
              </div>
            </div>
          )}
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
              <Image size={16} /> Chọn ảnh bìa (hoặc kéo thả vào đây)
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
              <span>Tối đa 60 ảnh (Podcast / Kể chuyện dài), mỗi ảnh ≤ 10MB</span>
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
