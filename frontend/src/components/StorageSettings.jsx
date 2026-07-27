import React, { useCallback, useEffect, useState } from 'react';
import { HardDrive, AlertTriangle, Check, RotateCcw, Trash2 } from 'lucide-react';
import { API_BASE } from '../constants';

/**
 * Đổi thư mục lưu dữ liệu sinh ra (ảnh, video, cache) sang ổ đĩa khác.
 *
 * Backend chỉ ghi giá trị xuống .env — đường dẫn của tiến trình đang chạy KHÔNG đổi
 * (xem backend/config.py). Vì thế màn hình này phải nói rõ "khởi động lại", nếu không
 * user sẽ tưởng đã đổi xong rồi ngồi chờ ổ C trống ra.
 */
export default function StorageSettings() {
  const [info, setInfo] = useState(null);
  const [cache, setCache] = useState(null);
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [result, setResult] = useState(null);   // { ok, message, warnings }

  const loadInfo = useCallback(async () => {
    try {
      const [cfgRes, cacheRes] = await Promise.all([
        fetch(`${API_BASE}/api/storage-config`),
        fetch(`${API_BASE}/api/cache-stats`),
      ]);
      if (cfgRes.ok) {
        const data = await cfgRes.json();
        setInfo(data);
        setDraft(data.configured_value || '');
      }
      if (cacheRes.ok) setCache(await cacheRes.json());
    } catch {
      // Backend chưa bật — khối này chỉ là tiện ích, không chặn phần còn lại của UI.
    }
  }, []);

  useEffect(() => { loadInfo(); }, [loadInfo]);

  const clearCache = async () => {
    if (!window.confirm(
      `Xoá ${cache.media_files} file ảnh/giọng đọc đã lưu (${cache.media_size_mb} MB)?\n\n`
      + 'Không mất dữ liệu nào — các cảnh sẽ chuyển 🔴 và được AI tạo lại ở lần render tới '
      + '(chậm hơn, và tốn quota API).'
    )) return;
    setClearing(true);
    setResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/cache?include_script_cache=false`, { method: 'DELETE' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Không dọn được bộ nhớ đệm.');
      setResult({ ok: true, message: data.message, warnings: [] });
      await loadInfo();
    } catch (err) {
      setResult({ ok: false, message: err.message, warnings: [] });
    } finally {
      setClearing(false);
    }
  };

  const save = async (pathValue) => {
    setSaving(true);
    setResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/storage-config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: pathValue }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Không lưu được cấu hình.');
      setResult({ ok: true, message: data.message, warnings: data.warnings || [] });
      await loadInfo();
    } catch (err) {
      setResult({ ok: false, message: err.message, warnings: [] });
    } finally {
      setSaving(false);
    }
  };

  if (!info) return null;

  const freeLow = info.disk_free_gb !== null && info.disk_free_gb < 15;

  return (
    <div className="advanced-box" style={{ marginTop: 16 }}>
      <div className="advanced-title"><HardDrive size={16} style={{ verticalAlign: 'text-bottom' }} /> Thư mục lưu trữ</div>

      <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.7, marginBottom: 12 }}>
        Đang lưu tại: <code style={{ color: 'var(--text-secondary)' }}>{info.data_dir}</code>
        {info.disk_free_gb !== null && (
          <> — còn trống <strong style={{ color: freeLow ? 'var(--red)' : 'var(--green)' }}>{info.disk_free_gb} GB</strong> / {info.disk_total_gb} GB</>
        )}
        <br />
        Nhạc nền &amp; tiếng động vẫn nằm cùng mã nguồn (<code>{info.bundled_assets_dir}</code>) nên không cần chép đi đâu.
      </div>

      {cache && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12,
          padding: '8px 10px', border: '1px solid var(--border)', borderRadius: 8,
        }}>
          <span style={{ flex: 1, fontSize: 12, color: 'var(--text-secondary)' }}>
            Bộ nhớ đệm: <strong>{cache.media_size_mb} MB</strong> ({cache.media_files} ảnh/giọng đọc)
            {cache.script_files > 0 && (
              <span style={{ color: 'var(--text-muted)' }}> + {cache.script_files} kịch bản</span>
            )}
            <span style={{ display: 'block', color: 'var(--text-muted)', marginTop: 2 }}>
              Đây là thứ giúp render lại gần như tức thì — chỉ dọn khi thật sự cần chỗ trống.
            </span>
          </span>
          <button
            className="btn-outline"
            style={{ color: 'var(--red)', borderColor: 'var(--red)', whiteSpace: 'nowrap' }}
            onClick={clearCache}
            disabled={clearing || cache.media_files === 0}
            title="Xoá ảnh và giọng đọc đã lưu. Kịch bản Gemini được giữ lại vì sinh lại sẽ tốn quota API."
          >
            <Trash2 size={14} /> {clearing ? 'Đang dọn...' : 'Dọn'}
          </button>
        </div>
      )}

      {info.fallback_reason && (
        <div className="error-box" style={{ marginBottom: 12, fontSize: 12 }}>
          <AlertTriangle size={14} />
          <span>Đường dẫn đã cấu hình không dùng được ({info.fallback_reason}) — đang tạm dùng thư mục mặc định.</span>
        </div>
      )}

      <label className="field-label">ĐƯỜNG DẪN MỚI (để trống = mặc định)</label>
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          type="text"
          className="form-input form-input-sm"
          style={{ flex: 1 }}
          value={draft}
          onChange={e => setDraft(e.target.value)}
          placeholder="D:\AIVideoAssets"
          spellCheck={false}
        />
        <button className="btn-outline" onClick={() => save(draft)} disabled={saving}>
          {saving ? 'Đang lưu...' : 'Lưu'}
        </button>
        {info.is_custom && (
          <button
            className="btn-icon"
            title="Quay về thư mục mặc định trong mã nguồn"
            onClick={() => { setDraft(''); save(''); }}
            disabled={saving}
          >
            <RotateCcw size={14} />
          </button>
        )}
      </div>

      {result && (
        <div
          className={result.ok ? '' : 'error-box'}
          style={{
            marginTop: 10, fontSize: 12, lineHeight: 1.6,
            ...(result.ok ? { color: 'var(--green)', display: 'flex', gap: 8, alignItems: 'flex-start' } : {}),
          }}
        >
          {result.ok ? <Check size={14} style={{ flexShrink: 0, marginTop: 2 }} /> : <AlertTriangle size={14} />}
          <span>
            {result.message}
            {result.warnings.map((w, i) => (
              <span key={i} style={{ display: 'block', color: 'var(--amber)', marginTop: 4 }}>⚠️ {w}</span>
            ))}
          </span>
        </div>
      )}
    </div>
  );
}
