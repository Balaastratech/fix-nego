"use client";

import { useEffect, useState, useRef, useCallback } from 'react';
import { useNegotiation } from '@/hooks/useNegotiation';
import { useNegotiationState } from '@/hooks/useNegotiationState';
import { useAskAI } from '@/hooks/useAskAI';
import { useEnrollment } from '@/hooks/useEnrollment';
import { NegotiationDashboard } from '@/components/negotiation/NegotiationDashboard';
import { EnrollmentModal } from '@/components/enrollment/EnrollmentModal';

// ─── Main Page ─────────────────────────────────────────────────────────────────
export default function Home() {
    const autoSpeakerRecognitionEnabled =
      process.env.NEXT_PUBLIC_AUTO_SPEAKER_RECOGNITION_ENABLED !== 'false';

    const {
        state,
        connect,
        grantConsent,
        startNegotiation,
        endNegotiation,
        setManualSpeaker,
        startCopilot,
        setUserAddressingAI,
        startEnrollment,
        sendEnrollmentAudio,
        setSpeakerMode,
        setResponseLanguage,
        websocket,
        audioManager,
    } = useNegotiation();

  const {
    state: negotiationState,
    validationErrors,
    addTranscriptEntry,
    updateStateFromAI,
    updateMarketData,
    setResearchState,
    resetState,
    updateStateFromAI: updateFromSetup,
  } = useNegotiationState();

  const { askAI, isLoading: isAILoading, clearLoading } = useAskAI(
    negotiationState,
    websocket,
    setResearchState
  );

  const [currentSpeaker, setCurrentSpeaker] = useState<'user' | 'counterparty' | null>(null);
  const [showEnrollmentModal, setShowEnrollmentModal] = useState(false);

  const { startEnrollment: startEnrollmentCapture, audioLevel } = useEnrollment({
    audioManager,
    onStartEnrollment: startEnrollment,
    onSendAudioChunk: sendEnrollmentAudio,
    enrollmentState: state.enrollmentState,
    enrollmentCountdown: state.enrollmentCountdown,
  });


  const [isSessionActive, setIsSessionActive] = useState(false);
  const [isAudioActive, setIsAudioActive] = useState(false);
  const [sessionResearchHistory, setSessionResearchHistory] = useState<any[]>([]);
  const [sessionVisionHistory, setSessionVisionHistory] = useState<any[]>([]);

  const lastSpeakerRef = useRef<'USER' | 'COUNTERPARTY' | null>(null);
  const lastSessionIdRef = useRef<string | null>(null);

  // Connect to WebSocket on mount
  useEffect(() => {
    if (!state.isConnected) {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.hostname;
      const wsUrl = process.env.NEXT_PUBLIC_WS_URL || `${protocol}//${host}:8000/ws`;
      connect(wsUrl).catch(console.error);
    }
  }, [connect, state.isConnected]);

  // Clear AI loading state when AI responds
  useEffect(() => {
    if (state.aiState === 'thinking' || state.aiState === 'speaking') {
      clearLoading();
    }
  }, [state.aiState, clearLoading]);

  // Wire TRANSCRIPT_UPDATE → negotiationState so ADVISOR_QUERY has conversation history
  useEffect(() => {
    const handleTranscript = (event: CustomEvent) => {
      const entry = event.detail as { speaker?: string; text?: string; transcript?: string };
      const text = entry.text || entry.transcript || '';
      if (!text.trim()) return;

      const rawSpeaker = (entry.speaker || '').toUpperCase();
      if (rawSpeaker !== 'USER' && rawSpeaker !== 'COUNTERPARTY') {
        return;
      }
      const speaker: 'USER' | 'COUNTERPARTY' =
        rawSpeaker === 'USER' ? 'USER' : 'COUNTERPARTY';
      addTranscriptEntry(speaker, text);
    };

    window.addEventListener('negotiation-transcript', handleTranscript as EventListener);
    return () => window.removeEventListener('negotiation-transcript', handleTranscript as EventListener);
  }, [addTranscriptEntry]);

  // Listen for STATE_UPDATE, RESEARCH_STARTED, RESEARCH_COMPLETE, and CONTEXT_UPDATE from backend
  useEffect(() => {
    const handleStateUpdate = (event: CustomEvent) => updateStateFromAI(event.detail);
    
    const handleResearchStarted = (event: CustomEvent) => {
      setResearchState(true, `Researching market for ${event.detail.query}...`);
    };
    
    const handleResearchComplete = (event: CustomEvent) => {
      if (event.detail.market_data) updateMarketData(event.detail.market_data);
      setResearchState(false);
      setSessionResearchHistory(prev => [...prev, event.detail].slice(-20));
    };
    
    const handleContextUpdate = (event: CustomEvent) => {
      const detail = event.detail as any;
      if (detail) updateStateFromAI(detail);
    };

    const handleSessionRestored = (event: CustomEvent) => {
      const detail = event.detail || {};
      setSessionResearchHistory(detail.research || []);
      setSessionVisionHistory(detail.vision || []);
    };

    const handleVisionStatus = (event: CustomEvent) => {
      if (!event.detail) return;
      setSessionVisionHistory(prev => [...prev, event.detail].slice(-20));
    };
    
    window.addEventListener('negotiation-state-update', handleStateUpdate as EventListener);
    window.addEventListener('market-research-started', handleResearchStarted as EventListener);
    window.addEventListener('market-research-complete', handleResearchComplete as EventListener);
    window.addEventListener('negotiation-session-restored', handleSessionRestored as EventListener);
    window.addEventListener('negotiation-vision-status', handleVisionStatus as EventListener);
    window.addEventListener('negotiation-context-update', handleContextUpdate as EventListener);
    
    return () => {
      window.removeEventListener('negotiation-state-update', handleStateUpdate as EventListener);
      window.removeEventListener('market-research-started', handleResearchStarted as EventListener);
      window.removeEventListener('market-research-complete', handleResearchComplete as EventListener);
      window.removeEventListener('negotiation-session-restored', handleSessionRestored as EventListener);
      window.removeEventListener('negotiation-vision-status', handleVisionStatus as EventListener);
      window.removeEventListener('negotiation-context-update', handleContextUpdate as EventListener);
    };
  }, [updateStateFromAI, updateMarketData, setResearchState]);

  const handleConsent = () => {
    grantConsent('1.0', 'live');
    if (autoSpeakerRecognitionEnabled) {
      setShowEnrollmentModal(true);
      return;
    }

    setShowEnrollmentModal(false);
    setSpeakerMode('manual');
  };

  const handleStartEnrollment = () => {
    startEnrollmentCapture();
  };

  const handleSkipEnrollment = () => {
    setShowEnrollmentModal(false);
  };

  const handleEnrollmentComplete = () => {
    setShowEnrollmentModal(false);
  };

  // Close enrollment modal when enrollment succeeds
  useEffect(() => {
    if (state.enrollmentState === 'success') {
      setTimeout(() => {
        setShowEnrollmentModal(false);
      }, 2000); // Show success message for 2 seconds
    }
  }, [state.enrollmentState]);

  useEffect(() => {
    setIsSessionActive(state.isNegotiating);
  }, [state.isNegotiating]);

  useEffect(() => {
    if (!state.sessionId) {
      return;
    }
    if (lastSessionIdRef.current === null) {
      lastSessionIdRef.current = state.sessionId;
      return;
    }
    if (lastSessionIdRef.current !== state.sessionId) {
      resetState();
      setSessionResearchHistory([]);
      setSessionVisionHistory([]);
      setCurrentSpeaker(null);
      setShowEnrollmentModal(false);
      setIsSessionActive(false);
      setIsAudioActive(false);
      lastSessionIdRef.current = state.sessionId;
    }
  }, [resetState, state.sessionId]);

  const handleSpeakerModeChange = (mode: 'auto' | 'manual') => {
    setSpeakerMode(mode);
  };

  const handleStartNegotiation = useCallback(() => {
    setIsSessionActive(true);
    setIsAudioActive(true);
    startNegotiation('', {}).catch(err => {
      console.error('Failed to start negotiation:', err);
      setIsSessionActive(false);
      setIsAudioActive(false);
    });
  }, [startNegotiation]);

  const handleEndNegotiation = () => {
    setIsSessionActive(false);
    setIsAudioActive(false);
    endNegotiation(null, null);
  };

  const handleToggleAudio = () => setIsAudioActive(prev => !prev);

  const handleSpeakerSelected = (speaker: 'user' | 'counterparty') => {
    setCurrentSpeaker(speaker);
    setManualSpeaker(speaker);
  };

  const dashboardState = { ...state, isNegotiating: isSessionActive, isAudioActive, isVisionActive: false };

  return (
    <main className="h-screen w-screen overflow-hidden text-neutral-900 bg-neutral-100 font-sans">
      <EnrollmentModal
        isOpen={autoSpeakerRecognitionEnabled && showEnrollmentModal}
        onComplete={handleEnrollmentComplete}
        onSkip={handleSkipEnrollment}
        onStartEnrollment={handleStartEnrollment}
        enrollmentState={state.enrollmentState}
        countdown={state.enrollmentCountdown}
        progress={state.enrollmentProgress}
        feedbackMessage={state.enrollmentFeedback || undefined}
        errorMessage={state.enrollmentError || undefined}
        audioLevel={audioLevel}
        allowSkip={true}
      />
      <NegotiationDashboard
        state={dashboardState}
        negotiationState={negotiationState}
        validationErrors={validationErrors}
        onConsent={handleConsent}
        onToggleAudio={handleToggleAudio}
        onStartNegotiation={handleStartNegotiation}
        onEndNegotiation={handleEndNegotiation}
        onStartCopilot={startCopilot}
        onUserAddressingAI={setUserAddressingAI}
        isAILoading={isAILoading}
        onSpeakerSelected={handleSpeakerSelected}
        currentSpeaker={currentSpeaker}
        responseLanguage={state.responseLanguage}
        onResponseLanguageChange={setResponseLanguage}
        aiLiveTranscription={state.aiLiveTranscription}
        liveTranscript={state.transcript.slice(-6)}
        speakerMode={state.speakerMode}
        onSpeakerModeChange={handleSpeakerModeChange}
        sessionResearchHistory={sessionResearchHistory}
      />
    </main>
  );
}
