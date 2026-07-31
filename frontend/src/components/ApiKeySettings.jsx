import React, { useState, useEffect, useCallback } from 'react';
import { Key, Check, AlertCircle, Eye, EyeOff, Save, ShieldCheck, Image, Video, Sparkles } from 'lucide-react';
import { API_BASE } from '../constants';

export default function ApiKeySettings() {
  const [geminiKeysText, setGeminiKeysText] = useState('');
  const [pexelsKey, setPexelsKey] = useState('');
  const [pixabayKey, setPixabayKey] = useState('');
  const [falKey, setFalKey] = useState('');
  
  const [status, setStatus] = useState({ gemini: false, pexels: false, pixabay: false, fal: false });
  const [showKeys, setShowKeys] = useState({ gemini: false, pexels: false, pixabay: false, fal: false });

  // Key thật chỉ được nạp vào state sau khi người dùng chủ động bấm "Hiện Key"
  // (revealKeys → GET /api/api-keys-config/reveal). Trước đó các ô chỉ hiển thị
  // giá trị đã che (GET /api/api-keys-config thường, tự chạy lúc mount) và bị
  // khoá readOnly — tránh việc gõ đè lên chuỗi che rồi lỡ tay Lưu, ghi rác vào .env.
  const [revealed, setRevealed] = useState(false);
  const [revealing, setRevealing] = useState(false);
  const [dirty, setDirty] = useState({ gemini: false, pexels: false, pixabay: false, fal: false });

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState(null);

  const loadKeysConfig = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/api-keys-config`);
      if (res.ok) {
        const data = await res.json();
        setGeminiKeysText((data.gemini_api_keys || []).join('\n'));
        setPexelsKey(data.pexels_api_key || '');
        setPixabayKey(data.pixabay_api_key || '');
        setFalKey(data.fal_key || '');
        if (data.status) {
          setStatus(data.status);
        }
      }
    } catch (err) {
      console.error('Không thể tải cấu hình Key API:', err);
    } finally {
      setLoading(false);
      setRevealed(false);
      setDirty({ gemini: false, pexels: false, pixabay: false, fal: false });
    }
  }, []);

  useEffect(() => {
    loadKeysConfig();
  }, [loadKeysConfig]);

  const revealKeys = useCallback(async () => {
    if (revealed || revealing) return;
    setRevealing(true);
    try {
      const res = await fetch(`${API_BASE}/api/api-keys-config/reveal`);
      if (res.ok) {
        const data = await res.json();
        setGeminiKeysText((data.gemini_api_keys || []).join('\n'));
        setPexelsKey(data.pexels_api_key || '');
        setPixabayKey(data.pixabay_api_key || '');
        setFalKey(data.fal_key || '');
        setRevealed(true);
      }
    } catch (err) {
      console.error('Không thể lấy key nguyên văn:', err);
    } finally {
      setRevealing(false);
    }
  }, [revealed, revealing]);

  const toggleShowKey = (field) => {
    if (!revealed) revealKeys();
    setShowKeys((prev) => ({ ...prev, [field]: !prev[field] }));
  };

  const markDirty = (field) => setDirty((prev) => ({ ...prev, [field]: true }));

  const handleSave = async (e) => {
    if (e) e.preventDefault();
    setResult(null);

    // Chỉ gửi field người dùng thật sự đã sửa (sau khi Hiện Key). Field chưa đụng
    // tới thì KHÔNG gửi — request cũ gửi cả 4 field trong mọi lần Lưu; nếu người
    // dùng chỉ đổi 1 key mà 3 field còn lại chưa từng Hiện Key, ta không có giá trị
    // thật của chúng để gửi lại và tuyệt đối không được gửi chuỗi đã che.
    const payload = {};
    if (dirty.gemini) {
      payload.gemini_api_keys = geminiKeysText.split('\n').map((k) => k.trim()).filter(Boolean);
    }
    if (dirty.pexels) payload.pexels_api_key = pexelsKey.trim();
    if (dirty.pixabay) payload.pixabay_api_key = pixabayKey.trim();
    if (dirty.fal) payload.fal_key = falKey.trim();

    if (Object.keys(payload).length === 0) {
      setResult({ ok: true, message: 'Chưa có thay đổi nào để lưu.' });
      return;
    }

    setSaving(true);
    try {
      const res = await fetch(`${API_BASE}/api/api-keys-config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Không thể lưu cài đặt API Keys.');

      setResult({ ok: true, message: data.message || 'Đã lưu cấu hình API Key thành công!' });
      setDirty({ gemini: false, pexels: false, pixabay: false, fal: false });
      if (revealed) {
        setRevealed(false);
        await revealKeys();
      } else {
        await loadKeysConfig();
      }
    } catch (err) {
      setResult({ ok: false, message: err.message });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="advanced-box" style={{ marginTop: 16 }}>
      <div className="advanced-title" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span>
          <Key size={16} style={{ verticalAlign: 'text-bottom', marginRight: 6 }} /> 
          Quản Lý Key API (Gemini, Pixabay, Pexels)
        </span>
        <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--text-muted)' }}>
          Tự động ghi vào file <code>.env</code>
        </span>
      </div>

      <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.6, marginBottom: 14 }}>
        Cấu hình và lưu trữ bảo mật các Key API để gọi AI sinh kịch bản, tạo ảnh và lấy video stock thực tế.
      </div>

      {/* Trạng thái tổng quan Badges */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
        <div className={`status-badge ${status.gemini ? 'active' : ''}`} style={{ padding: '4px 10px', borderRadius: 20, fontSize: 11, border: '1px solid var(--border)', background: status.gemini ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)', color: status.gemini ? '#10b981' : '#ef4444', display: 'flex', alignItems: 'center', gap: 4 }}>
          <Sparkles size={12} /> Gemini AI: {status.gemini ? '🟢 Đã có Key' : '🔴 Chưa có Key'}
        </div>
        <div className={`status-badge ${status.pexels ? 'active' : ''}`} style={{ padding: '4px 10px', borderRadius: 20, fontSize: 11, border: '1px solid var(--border)', background: status.pexels ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)', color: status.pexels ? '#10b981' : '#ef4444', display: 'flex', alignItems: 'center', gap: 4 }}>
          <Video size={12} /> Pexels Stock: {status.pexels ? '🟢 Đã có Key' : '🔴 Chưa cấu hình'}
        </div>
        <div className={`status-badge ${status.pixabay ? 'active' : ''}`} style={{ padding: '4px 10px', borderRadius: 20, fontSize: 11, border: '1px solid var(--border)', background: status.pixabay ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)', color: status.pixabay ? '#10b981' : '#ef4444', display: 'flex', alignItems: 'center', gap: 4 }}>
          <Image size={12} /> Pixabay Stock: {status.pixabay ? '🟢 Đã có Key' : '🔴 Chưa cấu hình'}
        </div>
      </div>

      <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {/* 1. Gemini API Keys */}
        <div className="input-group">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
              1. Gemini API Keys (Sinh kịch bản &amp; Ảnh AI)
            </label>
            <button
              type="button"
              onClick={() => toggleShowKey('gemini')}
              style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 11, display: 'flex', alignItems: 'center', gap: 4 }}
            >
              {showKeys.gemini ? <EyeOff size={13} /> : <Eye size={13} />} {showKeys.gemini ? 'Ẩn Key' : 'Hiện Key'}
            </button>
          </div>
          <textarea
            rows={2}
            value={geminiKeysText}
            onChange={(e) => { setGeminiKeysText(e.target.value); markDirty('gemini'); }}
            readOnly={!revealed}
            onFocus={() => { if (!revealed) revealKeys(); }}
            placeholder="AIzaSy...&#10;AIzaSy... (Nhập mỗi Key một dòng để tự động xoay vòng khi hết Quota)"
            style={{
              width: '100%',
              padding: '8px 10px',
              borderRadius: 8,
              border: '1px solid var(--border)',
              background: 'var(--bg-input, #0f172a)',
              color: 'var(--text-primary)',
              fontSize: 12,
              fontFamily: showKeys.gemini ? 'monospace' : 'caption',
              WebkitTextSecurity: showKeys.gemini ? 'none' : 'disc',
              resize: 'vertical',
              cursor: revealed ? 'text' : 'pointer',
            }}
          />
          <span style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
            {revealed
              ? '💡 Hỗ trợ nhiều key (mỗi dòng 1 key). Hệ thống tự xoay vòng chống lỗi 429 Quota Exceeded.'
              : '🔒 Đã che bớt để tránh lộ qua log/network tab. Bấm "Hiện Key" hoặc bấm vào ô để sửa.'}
          </span>
        </div>

        {/* 2. Pexels API Key */}
        <div className="input-group">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
              2. Pexels API Key (Tải Video/Ảnh Stock HD Thực tế)
            </label>
            <button
              type="button"
              onClick={() => toggleShowKey('pexels')}
              style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 11, display: 'flex', alignItems: 'center', gap: 4 }}
            >
              {showKeys.pexels ? <EyeOff size={13} /> : <Eye size={13} />} {showKeys.pexels ? 'Ẩn' : 'Hiện'}
            </button>
          </div>
          <input
            type={showKeys.pexels ? 'text' : 'password'}
            value={pexelsKey}
            onChange={(e) => { setPexelsKey(e.target.value); markDirty('pexels'); }}
            readOnly={!revealed}
            onFocus={() => { if (!revealed) revealKeys(); }}
            placeholder="Nhập Pexels API Key..."
            style={{
              width: '100%',
              padding: '8px 10px',
              borderRadius: 8,
              border: '1px solid var(--border)',
              background: 'var(--bg-input, #0f172a)',
              color: 'var(--text-primary)',
              fontSize: 12,
              fontFamily: showKeys.pexels ? 'monospace' : 'inherit',
            }}
          />
        </div>

        {/* 3. Pixabay API Key */}
        <div className="input-group">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
              3. Pixabay API Key (Tải thêm Kho Ảnh/Video HD Miễn phí)
            </label>
            <button
              type="button"
              onClick={() => toggleShowKey('pixabay')}
              style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 11, display: 'flex', alignItems: 'center', gap: 4 }}
            >
              {showKeys.pixabay ? <EyeOff size={13} /> : <Eye size={13} />} {showKeys.pixabay ? 'Ẩn' : 'Hiện'}
            </button>
          </div>
          <input
            type={showKeys.pixabay ? 'text' : 'password'}
            value={pixabayKey}
            onChange={(e) => { setPixabayKey(e.target.value); markDirty('pixabay'); }}
            readOnly={!revealed}
            onFocus={() => { if (!revealed) revealKeys(); }}
            placeholder="Ví dụ: 48123456-a1b2c3d4e5f67890abcdef123"
            style={{
              width: '100%',
              padding: '8px 10px',
              borderRadius: 8,
              border: '1px solid var(--border)',
              background: 'var(--bg-input, #0f172a)',
              color: 'var(--text-primary)',
              fontSize: 12,
              fontFamily: showKeys.pixabay ? 'monospace' : 'inherit',
            }}
          />
        </div>

        {/* 4. FAL AI Key (Option) */}
        <div className="input-group">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
              4. FAL AI Key (Tùy chọn - Sinh ảnh FLUX siêu tốc)
            </label>
            <button
              type="button"
              onClick={() => toggleShowKey('fal')}
              style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 11, display: 'flex', alignItems: 'center', gap: 4 }}
            >
              {showKeys.fal ? <EyeOff size={13} /> : <Eye size={13} />} {showKeys.fal ? 'Ẩn' : 'Hiện'}
            </button>
          </div>
          <input
            type={showKeys.fal ? 'text' : 'password'}
            value={falKey}
            onChange={(e) => { setFalKey(e.target.value); markDirty('fal'); }}
            readOnly={!revealed}
            onFocus={() => { if (!revealed) revealKeys(); }}
            placeholder="Nhập FAL_KEY (nếu có)..."
            style={{
              width: '100%',
              padding: '8px 10px',
              borderRadius: 8,
              border: '1px solid var(--border)',
              background: 'var(--bg-input, #0f172a)',
              color: 'var(--text-primary)',
              fontSize: 12,
              fontFamily: showKeys.fal ? 'monospace' : 'inherit',
            }}
          />
        </div>

        {/* Nút Save & Phản hồi */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 4 }}>
          <button
            type="submit"
            disabled={saving || loading}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '8px 16px',
              borderRadius: 8,
              border: 'none',
              background: 'linear-gradient(135deg, #3b82f6, #2563eb)',
              color: '#fff',
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            {saving ? <div className="spinner" style={{ width: 14, height: 14 }} /> : <Save size={14} />}
            {saving ? 'Đang lưu vào .env...' : 'Lưu Cấu Hình Key API'}
          </button>

          {result && (
            <span style={{ fontSize: 12, color: result.ok ? '#10b981' : '#ef4444', display: 'flex', alignItems: 'center', gap: 4 }}>
              {result.ok ? <Check size={14} /> : <AlertCircle size={14} />}
              {result.message}
            </span>
          )}
        </div>
      </form>
    </div>
  );
}
