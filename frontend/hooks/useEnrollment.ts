import { useState, useEffect, useRef, useCallback } from 'react';
import { AudioWorkletManager } from '../lib/audio-worklet-manager';

export type EnrollmentState = 'idle' | 'capturing' | 'processing' | 'success' | 'error';

interface UseEnrollmentProps {
  audioManager: AudioWorkletManager | null;
  onStartEnrollment: () => void;
  onSendAudioChunk: (chunk: ArrayBuffer) => void;
  enrollmentState: EnrollmentState;
  enrollmentCountdown: number | null;
}

export function useEnrollment({
  audioManager,
  onStartEnrollment,
  onSendAudioChunk,
  enrollmentState,
  enrollmentCountdown,
}: UseEnrollmentProps) {
  const [audioLevel, setAudioLevel] = useState(0);
  const audioLevelIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const enrollmentCaptureRef = useRef<boolean>(false);

  // Start enrollment process
  const startEnrollment = useCallback(async () => {
    if (!audioManager) {
      console.error('[Enrollment] AudioManager not available');
      return;
    }

    try {
      console.log('[Enrollment] Triggering enrollment...');
      
      // Audio capture is already started by useNegotiation.startEnrollment()
      // Just notify the backend to start enrollment
      onStartEnrollment();
      
      console.log('[Enrollment] Enrollment triggered');
    } catch (error) {
      console.error('[Enrollment] Failed to start enrollment:', error);
    }
  }, [audioManager, onStartEnrollment]);

  // Stop enrollment capture when state changes to success or error
  useEffect(() => {
    if (enrollmentState === 'success' || enrollmentState === 'error') {
      console.log('[Enrollment] Stopping capture, state:', enrollmentState);
      enrollmentCaptureRef.current = false;
      
      // Stop audio capture
      if (audioManager) {
        audioManager.stopCapture();
      }
    }
  }, [enrollmentState, audioManager]);

  // Simulate audio level during capture (for visual feedback)
  useEffect(() => {
    if (enrollmentState === 'capturing') {
      audioLevelIntervalRef.current = setInterval(() => {
        // Simulate audio level fluctuation
        setAudioLevel(Math.random() * 60 + 40); // 40-100%
      }, 100);
    } else {
      if (audioLevelIntervalRef.current) {
        clearInterval(audioLevelIntervalRef.current);
        audioLevelIntervalRef.current = null;
      }
      setAudioLevel(0);
    }

    return () => {
      if (audioLevelIntervalRef.current) {
        clearInterval(audioLevelIntervalRef.current);
      }
    };
  }, [enrollmentState]);

  return {
    startEnrollment,
    audioLevel,
  };
}
