import React from 'react';
import { Film } from 'lucide-react';
import { useAppStore } from './store';
import SettingsPanel from './components/SettingsPanel';
import ScriptEditor from './components/ScriptEditor';
import RenderProgress from './components/RenderProgress';
import ModeSelector from './components/ModeSelector';
import QuotaBar from './components/QuotaBar';
import { ToastContainer } from './lib/toast.jsx';

export default function App() {
  const step = useAppStore((s) => s.step);

  return (
    <div className="app-container">
      <div className="app-header">
        <div className="app-logo">
          <Film size={24} /> AI Video Studio
        </div>
        <QuotaBar />
        <div className="header-steps">
          <div className={`header-step ${step === 'config' ? 'active' : ''} ${step !== 'config' ? 'completed' : ''}`}>
            <div className="header-step-num">1</div> Cài đặt
          </div>
          <div className="header-step-arrow">→</div>
          <div className={`header-step ${step === 'editor' ? 'active' : ''} ${['rendering', 'done'].includes(step) ? 'completed' : ''}`}>
            <div className="header-step-num">2</div> Kịch bản
          </div>
          <div className="header-step-arrow">→</div>
          <div className={`header-step ${step === 'rendering' || step === 'done' ? 'active' : ''}`}>
            <div className="header-step-num">3</div> Render
          </div>
        </div>
      </div>

      {step === 'config' && <ModeSelector />}
      {step === 'config' && <SettingsPanel />}
      {step === 'editor' && <ScriptEditor />}
      {(step === 'rendering' || step === 'done') && <RenderProgress />}
      <ToastContainer />
    </div>
  );
}
