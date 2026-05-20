import React from 'react';
import { NegotiationState } from '../../lib/types';
import { NegotiationState as ButtonTriggeredState, ValidationError } from '../../hooks/useNegotiationState';
import { PrivacyConsent } from './PrivacyConsent';
import { VideoCapture } from './VideoCapture';
import { TranscriptPanel } from './TranscriptPanel';
import { ControlBar } from './ControlBar';
import { AIStateIndicator } from './AIStateIndicator';
import { ValidationErrors } from './ValidationErrors';
import { NegotiationStateCard } from './NegotiationStateCard';
import { ResearchIndicator } from './ResearchIndicator';
import { AskAIButton } from './AskAIButton';
import { SpeakerModeToggle } from './SpeakerModeToggle';

interface NegotiationDashboardProps {
  state: NegotiationState;
  negotiationState: ButtonTriggeredState;
  validationErrors: ValidationError[];
  onConsent: () => void;
  onToggleAudio: () => void;
  onToggleVision: () => void;
  onVisionFrame?: (base64Jpeg: string, isLiveMode: boolean) => void;
  onStartNegotiation: () => void;
  onEndNegotiation: () => void;
  onStartCopilot: () => void;
  onGetAdvice: () => void;
  onGetCommand: () => void;
  onUserAddressingAI: (active: boolean) => void;
  isAILoading: boolean;
  onSpeakerSelected?: (speaker: 'user' | 'counterparty') => void;
  currentSpeaker?: 'user' | 'counterparty' | null;
  responseMode?: 'advice' | 'command' | null;
  responseLanguage?: string | null;
  onResponseLanguageChange?: (language: string) => void;
  aiLiveTranscription?: string | null;
  liveTranscript?: import('../../lib/types').TranscriptEntry[];
  speakerMode?: 'auto' | 'manual';
  onSpeakerModeChange?: (mode: 'auto' | 'manual') => void;
  sessionResearchHistory?: Array<Record<string, any>>;
  sessionVisionHistory?: Array<Record<string, any>>;
}

export function NegotiationDashboard({
  state, negotiationState, validationErrors,
  onConsent, onToggleAudio, onToggleVision,
  onVisionFrame,
  onStartNegotiation, onEndNegotiation, onStartCopilot,
  onGetAdvice, onGetCommand, onUserAddressingAI,
  isAILoading, onSpeakerSelected, currentSpeaker,
  responseMode, aiLiveTranscription, liveTranscript = [],
  responseLanguage, onResponseLanguageChange,
  speakerMode = 'manual', onSpeakerModeChange,
  sessionResearchHistory = [], sessionVisionHistory = [],
}: NegotiationDashboardProps) {
  const [isAddressingAI, setIsAddressingAI] = React.useState(false);
  const longPressTimerRef = React.useRef<NodeJS.Timeout | null>(null);

  const handlePointerDown = React.useCallback(() => {
    if (!state.copilotActive) return;
    longPressTimerRef.current = setTimeout(() => {
      if (navigator.vibrate) navigator.vibrate(30);
      setIsAddressingAI(true);
      onUserAddressingAI(true);
    }, 600);
  }, [state.copilotActive, onUserAddressingAI]);

  const handlePointerEnd = React.useCallback(() => {
    if (longPressTimerRef.current) { clearTimeout(longPressTimerRef.current); longPressTimerRef.current = null; }
    if (isAddressingAI) { setIsAddressingAI(false); onUserAddressingAI(false); }
  }, [isAddressingAI, onUserAddressingAI]);

  if (!state.consentGiven) return <PrivacyConsent onAccept={onConsent} />;

  return (
    <div
      className="flex flex-col h-screen w-full overflow-hidden relative"
      onPointerDown={handlePointerDown}
      onPointerUp={handlePointerEnd}
      onPointerCancel={handlePointerEnd}
      onMouseLeave={handlePointerEnd}
      style={{ background: 'linear-gradient(135deg, #0b0b14 0%, #10101e 50%, #0b0b14 100%)' }}
    >
      {/* Blurred ambient blobs — like the reference image background */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-32 left-1/4 w-96 h-96 rounded-full opacity-20"
          style={{ background: 'radial-gradient(circle, #f5c518 0%, transparent 70%)', filter: 'blur(60px)' }} />
        <div className="absolute top-1/3 -right-24 w-72 h-72 rounded-full opacity-15"
          style={{ background: 'radial-gradient(circle, #c084fc 0%, transparent 70%)', filter: 'blur(50px)' }} />
        <div className="absolute bottom-1/4 -left-16 w-64 h-64 rounded-full opacity-12"
          style={{ background: 'radial-gradient(circle, #60a5fa 0%, transparent 70%)', filter: 'blur(50px)' }} />
        <div className="absolute bottom-0 right-1/3 w-80 h-48 rounded-full opacity-10"
          style={{ background: 'radial-gradient(circle, #f5c518 0%, transparent 70%)', filter: 'blur(60px)' }} />
      </div>

      <AIStateIndicator state={state.aiState} />
      <ResearchIndicator isResearching={negotiationState.isResearching} progress={negotiationState.researchProgress} />

      {validationErrors.length > 0 && (
        <div className="px-6 pt-4 relative z-10"><ValidationErrors errors={validationErrors} /></div>
      )}

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden p-4 gap-4 relative z-10">

        {/* Left Column */}
        <div className="w-[55%] flex flex-col gap-4 min-w-0">

          {/* Camera + Speaker selector */}
          <div className="shrink-0 flex gap-3 h-52">

            {/* Camera */}
            <div className="flex-1 rounded-2xl overflow-hidden"
              style={{
                border: '1px solid rgba(255,255,255,0.12)',
                boxShadow: '0 8px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.08)',
              }}>
              <VideoCapture
                isActive={state.isVisionActive}
                onToggle={onToggleVision}
                onFrameCapture={onVisionFrame}
                isLiveActive={isAddressingAI}
              />
            </div>

            {/* Speaker selector — frosted glass card */}
            <div className="flex-1 rounded-2xl flex flex-col items-center justify-center p-4 gap-3"
              style={{
                background: 'rgba(255,255,255,0.06)',
                backdropFilter: 'blur(40px) saturate(200%)',
                border: '1px solid rgba(255,255,255,0.13)',
                boxShadow: '0 8px 32px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.1)',
              }}>
              <div className="flex items-center justify-between w-full">
                <span className="text-[10px] font-bold uppercase tracking-[0.2em]"
                  style={{ color: '#f5c518', textShadow: '0 0 10px rgba(245,197,24,0.5)' }}>
                  Who is speaking?
                </span>
                {onSpeakerModeChange && (
                  <SpeakerModeToggle
                    mode={speakerMode}
                    onModeChange={onSpeakerModeChange}
                    disabled={!state.isNegotiating}
                  />
                )}
              </div>
              {state.responseLanguage && (
                <div className="w-full flex flex-col gap-2">
                  <div className="text-[10px] uppercase tracking-[0.18em]" style={{ color: 'rgba(255,255,255,0.55)' }}>
                    Response language
                  </div>
                  <select
                    value={responseLanguage || state.responseLanguage || 'en-US'}
                    onChange={(event) => onResponseLanguageChange?.(event.target.value)}
                    disabled={!state.isNegotiating}
                    className="w-full rounded-xl px-3 py-2 text-xs font-semibold outline-none"
                    style={{
                      background: 'rgba(255,255,255,0.08)',
                      color: 'rgba(255,255,255,0.9)',
                      border: '1px solid rgba(255,255,255,0.12)',
                    }}
                  >
                    <option value="en-US">English</option>
                    <option value="hi-IN">Hindi</option>
                    <option value="es-US">Spanish</option>
                  </select>
                </div>
              )}
              {speakerMode === 'manual' && (
                <div className="flex flex-col gap-2 w-full">
                  <button
                    onClick={() => onSpeakerSelected?.('user')}
                    disabled={!state.isNegotiating}
                    className={`w-full py-3 rounded-xl text-sm font-bold transition-all duration-200 ${!state.isNegotiating ? 'opacity-25 cursor-not-allowed' : 'hover:scale-[1.02] active:scale-[0.98]'}`}
                    style={currentSpeaker === 'user'
                      ? { background: 'linear-gradient(135deg, #f5c518, #ffd700)', color: '#0b0b14', boxShadow: '0 4px 20px rgba(245,197,24,0.5), inset 0 1px 0 rgba(255,255,255,0.3)' }
                      : { background: 'rgba(255,255,255,0.07)', color: 'rgba(255,255,255,0.92)', border: '1px solid rgba(255,255,255,0.12)' }}
                  >
                    🙋 Me
                  </button>
                  <button
                    onClick={() => onSpeakerSelected?.('counterparty')}
                    disabled={!state.isNegotiating}
                    className={`w-full py-3 rounded-xl text-sm font-bold transition-all duration-200 ${!state.isNegotiating ? 'opacity-25 cursor-not-allowed' : 'hover:scale-[1.02] active:scale-[0.98]'}`}
                    style={currentSpeaker === 'counterparty'
                      ? { background: 'linear-gradient(135deg, #f5c518, #ffd700)', color: '#0b0b14', boxShadow: '0 4px 20px rgba(245,197,24,0.5), inset 0 1px 0 rgba(255,255,255,0.3)' }
                      : { background: 'rgba(255,255,255,0.07)', color: 'rgba(255,255,255,0.92)', border: '1px solid rgba(255,255,255,0.12)' }}
                  >
                    🤝 Counterparty
                  </button>
                </div>
              )}
              {speakerMode === 'auto' && (
                <div className="text-xs text-center" style={{ color: 'rgba(245,197,24,0.7)' }}>
                  <p>🎤 Voice recognition active</p>
                  <p className="mt-1 text-[10px]" style={{ color: 'rgba(255,255,255,0.5)' }}>
                    Speakers identified automatically
                  </p>
                </div>
              )}
              <span className="text-[10px]" style={{ color: 'rgba(245,197,24,0.5)' }}>
                {state.isNegotiating 
                  ? (speakerMode === 'manual' ? 'Tap to switch' : 'Toggle for manual mode')
                  : 'Start session to enable'}
              </span>
            </div>
          </div>

          {/* Transcript panels */}
          <div className="flex-1 min-h-0 flex gap-3">
            <div className="flex-1 min-w-0">
              {/* Real negotiation only — excludes AI responses and anything the user said to AI */}
              <TranscriptPanel
                entries={state.transcript.filter(e => e.speaker !== 'ai' && e.context !== 'ask_ai')}
                title="Conversation"
              />
            </div>
            <div className="flex-1 min-w-0">
              {/* AI Advisor — AI responses + what the user asked the AI */}
              <TranscriptPanel
                entries={state.transcript.filter(e => e.speaker === 'ai' || e.context === 'ask_ai')}
                title="AI Advisor"
              />
            </div>
          </div>
        </div>

        {/* Right Column */}
        <div className="flex-1 min-w-[300px] flex flex-col overflow-hidden">
          <div className="flex-1 overflow-y-auto pr-0.5 flex flex-col gap-4">
            <NegotiationStateCard
              state={negotiationState}
              isDualModelActive={state.isNegotiating}
              liveTranscript={liveTranscript}
              isAddressingAI={isAddressingAI}
            />
            <div
              className="rounded-2xl p-4 flex flex-col gap-4"
              style={{
                background: 'rgba(255,255,255,0.06)',
                backdropFilter: 'blur(40px) saturate(200%)',
                border: '1px solid rgba(255,255,255,0.13)',
                boxShadow: '0 8px 32px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.1)',
              }}
            >
              <div>
                <div className="text-[10px] font-bold uppercase tracking-[0.2em]" style={{ color: '#f5c518' }}>
                  Session History
                </div>
                <div className="mt-1 text-xs" style={{ color: 'rgba(255,255,255,0.55)' }}>
                  Research and vision events now persist and resume with the session.
                </div>
              </div>

              <div className="flex flex-col gap-2">
                <div className="text-[10px] uppercase tracking-[0.18em]" style={{ color: 'rgba(255,255,255,0.5)' }}>
                  Research
                </div>
                {sessionResearchHistory.length === 0 ? (
                  <div className="text-xs" style={{ color: 'rgba(255,255,255,0.45)' }}>
                    No research events yet.
                  </div>
                ) : (
                  sessionResearchHistory.slice(-5).reverse().map((event, index) => (
                    <div
                      key={`research-${event.timestamp || index}`}
                      className="rounded-xl px-3 py-2 text-xs"
                      style={{ background: 'rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.82)' }}
                    >
                      <div className="font-semibold" style={{ color: '#f5c518' }}>
                        {event.query || event.provider || 'Research event'}
                      </div>
                      <div>{event.summary || event.results || event.status || 'Completed'}</div>
                    </div>
                  ))
                )}
              </div>

              <div className="flex flex-col gap-2">
                <div className="text-[10px] uppercase tracking-[0.18em]" style={{ color: 'rgba(255,255,255,0.5)' }}>
                  Vision
                </div>
                {sessionVisionHistory.length === 0 ? (
                  <div className="text-xs" style={{ color: 'rgba(255,255,255,0.45)' }}>
                    No vision events yet.
                  </div>
                ) : (
                  sessionVisionHistory.slice(-5).reverse().map((event, index) => (
                    <div
                      key={`vision-${event.timestamp || index}`}
                      className="rounded-xl px-3 py-2 text-xs"
                      style={{ background: 'rgba(255,255,255,0.05)', color: 'rgba(255,255,255,0.82)' }}
                    >
                      <div className="font-semibold" style={{ color: '#f5c518' }}>
                        {event.event || 'Vision event'}
                      </div>
                      <div>{event.observation || event.message || `Frame size: ${event.size || 'n/a'}`}</div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Bar */}
      <div className="shrink-0 relative z-10"
        style={{
          background: 'rgba(11,11,20,0.6)',
          backdropFilter: 'blur(40px) saturate(200%)',
          borderTop: '1px solid rgba(255,255,255,0.1)',
          boxShadow: '0 -1px 0 rgba(255,255,255,0.04), 0 -8px 32px rgba(0,0,0,0.3)',
        }}>
        <div className="relative flex items-center justify-center p-4">
          <ControlBar
            isAudioActive={state.isAudioActive}
            isVisionActive={state.isVisionActive}
            isNegotiating={state.isNegotiating}
            onToggleAudio={onToggleAudio}
            onToggleVision={onToggleVision}
            onStartNegotiation={onStartNegotiation}
            onEndNegotiation={onEndNegotiation}
          />
          <div className="absolute right-6 top-1/2 -translate-y-1/2">
            <AskAIButton
              onStartCopilot={onStartCopilot}
              onGetAdvice={onGetAdvice}
              onGetCommand={onGetCommand}
              isLoading={isAILoading}
              isDisabled={!state.isNegotiating}
              copilotActive={state.copilotActive}
              responseMode={responseMode}
            />
          </div>
        </div>
      </div>

      {/* AI Live Transcription */}
      {aiLiveTranscription && state.aiState === 'speaking' && (
        <div className="fixed bottom-28 left-1/2 -translate-x-1/2 z-40 max-w-lg w-full px-4 pointer-events-none">
          <div className="px-5 py-3 rounded-2xl text-sm leading-relaxed"
            style={{
              background: 'rgba(11,11,20,0.7)',
              backdropFilter: 'blur(40px) saturate(200%)',
              border: '1px solid rgba(245,197,24,0.25)',
              boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
            }}>
            <span className="font-bold text-[10px] uppercase tracking-widest block mb-1" style={{ color: '#f5c518' }}>AI</span>
            <span style={{ color: 'rgba(255,255,255,0.9)' }}>{aiLiveTranscription}</span>
          </div>
        </div>
      )}

      {/* Addressing AI */}
      {isAddressingAI && (
        <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 pointer-events-none">
          <div className="px-8 py-4 rounded-2xl flex items-center gap-3 animate-pulse"
            style={{
              background: 'rgba(245,197,24,0.08)',
              backdropFilter: 'blur(40px)',
              border: '1px solid rgba(245,197,24,0.4)',
              boxShadow: '0 0 48px rgba(245,197,24,0.2)',
            }}>
            <div className="w-3 h-3 rounded-full animate-ping" style={{ background: '#f5c518' }} />
            <span className="font-bold text-lg" style={{ color: '#ffd700', textShadow: '0 0 16px rgba(245,197,24,0.7)' }}>
              Listening to you...
            </span>
          </div>
        </div>
      )}

      {/* Degraded */}
      {state.aiDegraded && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-50 animate-bounce">
          <div className="px-6 py-2 rounded-full flex items-center"
            style={{ background: 'rgba(245,197,24,0.08)', border: '1px solid rgba(245,197,24,0.3)', backdropFilter: 'blur(20px)' }}>
            <span className="font-semibold text-sm" style={{ color: '#ffd700' }}>
              Connection unstable. Operating in text-only fallback mode.
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
