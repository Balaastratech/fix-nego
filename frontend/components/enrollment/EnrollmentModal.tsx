import { Mic, CheckCircle, XCircle, Loader2 } from 'lucide-react';

export const ENROLLMENT_SCRIPT =
  "Hello, I am preparing for an important negotiation today. I want to speak clearly, stay calm under pressure, and explain my position with confidence. My goal is to reach a fair deal, protect my budget, and respond thoughtfully to every offer while keeping the conversation respectful and productive.";

// Design constants matching the existing theme
const G = '#f5c518';
const GL = '#ffd700';
const GF = 'rgba(245,197,24,0.07)';
const GG = 'rgba(245,197,24,0.2)';
const TM = 'rgba(255,255,255,0.75)';
const TB = 'rgba(255,255,255,0.97)';
const GLASS = 'rgba(255,255,255,0.03)';
const BLUR = 'blur(32px) saturate(180%)';

export type EnrollmentState = 'idle' | 'capturing' | 'processing' | 'success' | 'error';

interface EnrollmentModalProps {
  isOpen: boolean;
  onComplete: () => void;
  onSkip: () => void;
  onStartEnrollment: () => void;
  enrollmentState: EnrollmentState;
  countdown: number | null;
  progress?: number | null;
  feedbackMessage?: string;
  errorMessage?: string;
  audioLevel?: number; // 0-100 for volume meter
  allowSkip?: boolean;
}

export function EnrollmentModal({
  isOpen,
  onComplete,
  onSkip,
  onStartEnrollment,
  enrollmentState,
  countdown,
  progress = null,
  feedbackMessage,
  errorMessage,
  audioLevel = 0,
  allowSkip = true,
}: EnrollmentModalProps) {
  if (!isOpen) return null;

  const getStatusMessage = () => {
    switch (enrollmentState) {
      case 'idle':
        return 'Ready to enroll your voice';
      case 'capturing':
        return progress !== null ? `Processing sample... ${Math.round(progress)}%` : 'Listening for a stable voice sample...';
      case 'processing':
        return 'Processing your voice...';
      case 'success':
        return 'Voice registered successfully!';
      case 'error':
        return errorMessage || 'Enrollment failed';
      default:
        return '';
    }
  };

  const getInstructions = () => {
    if (enrollmentState === 'idle') {
      return (
        <div className="text-xs text-center space-y-2" style={{ color: TM }}>
          <p className="font-semibold" style={{ color: GL }}>You will be asked to read a sentence.</p>
          <p>Keep speaking clearly until the system confirms that your voice sample is ready.</p>
          <p className="text-[10px]" style={{ color: 'rgba(245,197,24,0.6)' }}>
            Keep one speaker only during enrollment and speak without long pauses.
          </p>
          <p>This helps the system recognize your voice during negotiations.</p>
          <p className="text-[10px]" style={{ color: TM }}>
            Read the full passage below at a normal speaking pace.
          </p>
        </div>
      );
    }
    
    if (enrollmentState === 'capturing') {
      return (
        <div className="text-xs text-center space-y-2 px-4" style={{ color: TB }}>
          <p className="font-bold text-sm" style={{ color: GL }}>Keep reading until the system confirms your sample is ready:</p>
          <p className="text-sm leading-relaxed italic" style={{ color: TB }}>
            "{ENROLLMENT_SCRIPT}"
          </p>
          {feedbackMessage && (
            <p className="text-[10px]" style={{ color: 'rgba(245,197,24,0.85)' }}>{feedbackMessage}</p>
          )}
        </div>
      );
    }
    
    return null;
  };

  const getStatusIcon = () => {
    switch (enrollmentState) {
      case 'idle':
        return <Mic className="w-12 h-12" style={{ color: G }} />;
      case 'capturing':
        return (
          <div className="relative">
            <Mic className="w-12 h-12 animate-pulse" style={{ color: G }} />
            {progress !== null && (
              <div className="absolute -bottom-2 left-1/2 -translate-x-1/2 text-3xl font-bold" style={{ color: GL }}>
                {Math.round(progress)}%
              </div>
            )}
          </div>
        );
      case 'processing':
        return <Loader2 className="w-12 h-12 animate-spin" style={{ color: G }} />;
      case 'success':
        return <CheckCircle className="w-12 h-12" style={{ color: '#10b981' }} />;
      case 'error':
        return <XCircle className="w-12 h-12" style={{ color: '#ef4444' }} />;
      default:
        return null;
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(8px)' }}>
      <div className="max-w-md w-full rounded-2xl p-8 flex flex-col items-center space-y-6"
        style={{
          background: GLASS,
          backdropFilter: BLUR,
          border: `1px solid ${GG}`,
          boxShadow: `0 0 48px rgba(245,197,24,0.15), inset 0 1px 0 rgba(255,255,255,0.06)`,
        }}>
        
        {/* Icon */}
        <div className="w-24 h-24 rounded-full flex items-center justify-center"
          style={{ background: GF, border: `1px solid ${GG}` }}>
          {getStatusIcon()}
        </div>

        {/* Title */}
        <h2 className="text-2xl font-bold text-center" style={{ color: GL, textShadow: `0 0 10px rgba(245,197,24,0.4)` }}>
          Voice Enrollment
        </h2>

        {/* Status Message */}
        <p className="text-center text-sm" style={{ color: TM }}>
          {getStatusMessage()}
        </p>

        {/* Volume / Progress Meter (only during capturing) */}
        {enrollmentState === 'capturing' && (
          <div className="w-full space-y-2">
            <div className="text-xs text-center" style={{ color: TM }}>
              {progress !== null ? `Processing ${Math.round(progress)}%` : 'Live voice level'}
            </div>
            <div className="w-full h-2 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.1)' }}>
              <div
                className="h-full transition-all duration-100"
                style={{
                  width: `${progress !== null ? progress : audioLevel}%`,
                  background: `linear-gradient(90deg, ${G}, ${GL})`,
                  boxShadow: `0 0 8px ${G}`,
                }}
              />
            </div>
          </div>
        )}

        {/* Instructions */}
        {getInstructions()}

        {/* Error Details */}
        {enrollmentState === 'error' && errorMessage && (
          <div className="w-full p-3 rounded-lg text-xs text-center"
            style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#fca5a5' }}>
            {errorMessage}
          </div>
        )}

        {/* Action Buttons */}
        <div className="w-full flex gap-3">
          {enrollmentState === 'idle' && (
            <>
              <button
                onClick={onStartEnrollment}
                className="flex-1 py-3 rounded-xl text-sm font-bold transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]"
                style={{
                  background: `linear-gradient(135deg, ${G}, ${GL})`,
                  color: '#0b0b14',
                  boxShadow: `0 4px 20px rgba(245,197,24,0.4), inset 0 1px 0 rgba(255,255,255,0.3)`,
                }}
              >
                Start Enrollment
              </button>
              {allowSkip && (
                <button
                  onClick={onSkip}
                  className="flex-1 py-3 rounded-xl text-sm font-bold transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]"
                  style={{
                    background: 'rgba(255,255,255,0.07)',
                    color: TB,
                    border: '1px solid rgba(255,255,255,0.12)',
                  }}
                >
                  Skip
                </button>
              )}
            </>
          )}

          {enrollmentState === 'success' && (
            <button
              onClick={onComplete}
              className="w-full py-3 rounded-xl text-sm font-bold transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]"
              style={{
                background: `linear-gradient(135deg, ${G}, ${GL})`,
                color: '#0b0b14',
                boxShadow: `0 4px 20px rgba(245,197,24,0.4), inset 0 1px 0 rgba(255,255,255,0.3)`,
              }}
            >
              Continue
            </button>
          )}

          {enrollmentState === 'error' && (
            <>
              <button
                onClick={onStartEnrollment}
                className="flex-1 py-3 rounded-xl text-sm font-bold transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]"
                style={{
                  background: `linear-gradient(135deg, ${G}, ${GL})`,
                  color: '#0b0b14',
                  boxShadow: `0 4px 20px rgba(245,197,24,0.4), inset 0 1px 0 rgba(255,255,255,0.3)`,
                }}
              >
                Retry
              </button>
              {allowSkip && (
                <button
                  onClick={onSkip}
                  className="flex-1 py-3 rounded-xl text-sm font-bold transition-all duration-200 hover:scale-[1.02] active:scale-[0.98]"
                  style={{
                    background: 'rgba(255,255,255,0.07)',
                    color: TB,
                    border: '1px solid rgba(255,255,255,0.12)',
                  }}
                >
                  Skip
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
