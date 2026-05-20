import React from 'react';
import { Zap, Hand } from 'lucide-react';

// Design constants matching the existing theme
const G = '#f5c518';
const GL = '#ffd700';
const GF = 'rgba(245,197,24,0.07)';
const GG = 'rgba(245,197,24,0.2)';
const TM = 'rgba(255,255,255,0.75)';
const TB = 'rgba(255,255,255,0.97)';

export type SpeakerMode = 'auto' | 'manual';

interface SpeakerModeToggleProps {
  mode: SpeakerMode;
  onModeChange: (mode: SpeakerMode) => void;
  disabled?: boolean;
}

export function SpeakerModeToggle({ mode, onModeChange, disabled = false }: SpeakerModeToggleProps) {
  const [showTooltip, setShowTooltip] = React.useState(false);

  const handleToggle = () => {
    if (!disabled) {
      onModeChange(mode === 'auto' ? 'manual' : 'auto');
    }
  };

  return (
    <div className="relative">
      {/* Toggle Button */}
      <button
        onClick={handleToggle}
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        disabled={disabled}
        className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold transition-all duration-200 ${
          disabled ? 'opacity-40 cursor-not-allowed' : 'hover:scale-[1.02] active:scale-[0.98]'
        }`}
        style={
          mode === 'auto'
            ? {
                background: `linear-gradient(135deg, ${G}, ${GL})`,
                color: '#0b0b14',
                boxShadow: `0 4px 16px rgba(245,197,24,0.4), inset 0 1px 0 rgba(255,255,255,0.3)`,
              }
            : {
                background: 'rgba(255,255,255,0.07)',
                color: TB,
                border: '1px solid rgba(255,255,255,0.12)',
              }
        }
      >
        {mode === 'auto' ? (
          <>
            <Zap className="w-4 h-4" />
            <span>Auto</span>
          </>
        ) : (
          <>
            <Hand className="w-4 h-4" />
            <span>Manual</span>
          </>
        )}
      </button>

      {/* Mode Indicator Badge */}
      <div
        className="absolute -top-1 -right-1 w-3 h-3 rounded-full animate-pulse"
        style={{
          background: mode === 'auto' ? '#10b981' : '#f59e0b',
          boxShadow: `0 0 8px ${mode === 'auto' ? '#10b981' : '#f59e0b'}`,
        }}
      />

      {/* Tooltip */}
      {showTooltip && !disabled && (
        <div
          className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 rounded-lg text-xs whitespace-nowrap pointer-events-none z-50"
          style={{
            background: 'rgba(11,11,20,0.95)',
            backdropFilter: 'blur(20px)',
            border: `1px solid ${GG}`,
            boxShadow: '0 4px 16px rgba(0,0,0,0.3)',
            color: TM,
          }}
        >
          {mode === 'auto' ? (
            <div className="space-y-1">
              <div className="font-bold" style={{ color: GL }}>
                Auto Mode
              </div>
              <div>Voice recognition identifies speakers automatically</div>
            </div>
          ) : (
            <div className="space-y-1">
              <div className="font-bold" style={{ color: GL }}>
                Manual Mode
              </div>
              <div>Click buttons to identify speakers manually</div>
            </div>
          )}
          {/* Tooltip arrow */}
          <div
            className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0"
            style={{
              borderLeft: '6px solid transparent',
              borderRight: '6px solid transparent',
              borderTop: `6px solid ${GG}`,
            }}
          />
        </div>
      )}
    </div>
  );
}
