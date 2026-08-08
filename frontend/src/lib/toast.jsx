// Lightweight toast system — no extra dependencies needed.
// Renders into a fixed overlay div that App mounts once at the root.
import { createPortal } from 'react-dom';
import { useState, useEffect } from 'react';

let _addFn = null;
// Register the add function from ToastContainer so other modules can call toast().
export function registerToast(addFn) { _addFn = addFn; }

export function toast(message, { type = 'info', duration = 4000 } = {}) {
  if (_addFn) _addFn({ message, type, id: Date.now() + Math.random(), duration });
}

export function ToastContainer() {
  const [toasts, setToasts] = useState([]);

  useEffect(() => {
    registerToast((t) => setToasts((prev) => [...prev, t]));
  }, []);

  const remove = (id) => setToasts((prev) => prev.filter((t) => t.id !== id));

  return createPortal(
    <div style={{ position: 'fixed', bottom: 20, right: 20, zIndex: 9999, display: 'flex', flexDirection: 'column', gap: 8 }}>
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} onRemove={remove} />
      ))}
    </div>,
    document.body
  );
}

function ToastItem({ toast: t, onRemove }) {
  useEffect(() => {
    const timer = setTimeout(() => onRemove(t.id), t.duration);
    return () => clearTimeout(timer);
  }, [t.id, t.duration, onRemove]);

  const colors = {
    success: { bg: '#1a3a2a', border: '#2ecc71', text: '#a8f0c0' },
    error:   { bg: '#3a1a1a', border: '#e74c3c', text: '#f5a8a8' },
    warning: { bg: '#3a2e1a', border: '#f39c12', text: '#ffeaa7' },
    info:    { bg: '#1a2a3a', border: '#3498db', text: '#a8d8f5' },
  };
  const c = colors[t.type] || colors.info;

  return (
    <div style={{
      background: c.bg,
      border: `1px solid ${c.border}`,
      color: c.text,
      borderRadius: 8,
      padding: '10px 16px',
      fontSize: '0.875rem',
      fontFamily: 'inherit',
      minWidth: 240,
      maxWidth: 380,
      boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
      cursor: 'pointer',
    }}
    onClick={() => onRemove(t.id)}
    >
      {t.message}
    </div>
  );
}
