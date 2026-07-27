import React from 'react';
import { useShallow } from 'zustand/react/shallow';
import { useAppStore } from '../store';
import { MODES } from '../constants';

export default function ModeSelector() {
  const { activeMode, setActiveMode, setErrorMsg } = useAppStore(
    useShallow((s) => ({ activeMode: s.activeMode, setActiveMode: s.setActiveMode, setErrorMsg: s.setErrorMsg }))
  );

  return (
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
  );
}
