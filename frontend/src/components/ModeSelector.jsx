import React from 'react';
import { useAppContext } from '../AppContext';
import { MODES } from '../constants';

export default function ModeSelector() {
  const { activeMode, setActiveMode, setErrorMsg } = useAppContext();

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
