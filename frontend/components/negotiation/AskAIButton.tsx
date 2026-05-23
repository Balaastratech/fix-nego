import React from 'react';
import { Sparkles, Loader2, Mic } from 'lucide-react';

interface AskAIButtonProps {
  onStartCopilot: () => void;
  isLoading: boolean;
  isDisabled: boolean;
  copilotActive: boolean;
}

export function AskAIButton({ onStartCopilot, isLoading, isDisabled, copilotActive }: AskAIButtonProps) {
  const goldBtn = {
    background: 'linear-gradient(135deg, #f5c518, #ffd700)',
    color: '#080810',
    boxShadow: '0 0 28px rgba(245,197,24,0.45), inset 0 1px 0 rgba(255,255,255,0.3)',
    border: '1px solid rgba(245,197,24,0.6)',
  };
  const disabledBtn = {
    background: 'rgba(255,255,255,0.04)',
    color: 'rgba(255,255,255,0.2)',
    border: '1px solid rgba(255,255,255,0.08)',
    cursor: 'not-allowed' as const,
  };

  return (
    <div className="flex flex-col gap-2 items-end">
      {!copilotActive && (
        <button
          onClick={onStartCopilot}
          disabled={isDisabled || isLoading}
          className="flex items-center justify-center px-6 py-3 rounded-full font-bold transition-all duration-200 hover:scale-105"
          style={isDisabled || isLoading ? disabledBtn : goldBtn}
          aria-label="Start Copilot"
        >
          {isLoading
            ? <><Loader2 className="w-5 h-5 mr-2 animate-spin" /><span>Starting...</span></>
            : <><Sparkles className="w-5 h-5 mr-2" /><span>Start Copilot</span></>}
        </button>
      )}

      {copilotActive && (
        <div className="flex flex-col gap-2 items-end">
          <div
            className="flex items-center gap-1.5 text-xs font-bold"
            style={{ color: '#f5c518', textShadow: '0 0 10px rgba(245,197,24,0.5)' }}
          >
            <Mic className="w-3 h-3 animate-pulse" />
            Copilot Active
          </div>
          <div className="text-[10px]" style={{ color: 'rgba(245,197,24,0.45)' }}>
            Then press and hold to talk
          </div>
        </div>
      )}
    </div>
  );
}
