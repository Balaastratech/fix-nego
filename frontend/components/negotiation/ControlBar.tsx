import React from 'react';
import { Mic, MicOff, PhoneOff, Phone } from 'lucide-react';

interface ControlBarProps {
  isAudioActive: boolean;
  isNegotiating: boolean;
  onToggleAudio: () => void;
  onStartNegotiation: () => void;
  onEndNegotiation: () => void;
}

export function ControlBar({
  isAudioActive, isNegotiating,
  onToggleAudio, onStartNegotiation, onEndNegotiation,
}: ControlBarProps) {
  return (
    <div className="flex items-center space-x-6">

      <button
        onClick={onToggleAudio}
        disabled={!isNegotiating}
        className={`flex items-center justify-center p-4 rounded-full transition-all duration-200 ${!isNegotiating ? 'opacity-25 cursor-not-allowed' : 'hover:scale-105'}`}
        style={isAudioActive
          ? { background: 'rgba(245,197,24,0.15)', border: '1px solid rgba(245,197,24,0.5)', color: '#f5c518', boxShadow: '0 0 16px rgba(245,197,24,0.25)' }
          : { background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.12)', color: 'rgba(255,255,255,0.85)' }}
        title={isAudioActive ? 'Mute Microphone' : 'Unmute Microphone'}
      >
        {isAudioActive ? <Mic className="w-6 h-6" /> : <MicOff className="w-6 h-6" />}
      </button>

      {isNegotiating ? (
        <button
          onClick={onEndNegotiation}
          className="flex items-center justify-center px-8 py-4 rounded-full font-bold transition-all duration-200 hover:scale-105"
          style={{
            background: 'linear-gradient(135deg, #dc2626, #ef4444)',
            color: '#fff',
            boxShadow: '0 0 28px rgba(239,68,68,0.4), inset 0 1px 0 rgba(255,255,255,0.15)',
            border: '1px solid rgba(239,68,68,0.5)',
          }}
        >
          <PhoneOff className="w-5 h-5 mr-2" />End Session
        </button>
      ) : (
        <button
          onClick={onStartNegotiation}
          className="flex items-center justify-center px-8 py-4 rounded-full font-bold transition-all duration-200 hover:scale-105"
          style={{
            background: 'linear-gradient(135deg, #f5c518, #ffd700)',
            color: '#080810',
            boxShadow: '0 0 32px rgba(245,197,24,0.5), inset 0 1px 0 rgba(255,255,255,0.3)',
            border: '1px solid rgba(245,197,24,0.6)',
          }}
        >
          <Phone className="w-5 h-5 mr-2" />Start Session
        </button>
      )}
    </div>
  );
}
