import { useState, useEffect, useRef, useCallback, useReducer } from 'react';
import { NegotiationWebSocket } from '../lib/websocket';
import { AudioWorkletManager } from '../lib/audio-worklet-manager';
import {
    NegotiationState,
    INITIAL_NEGOTIATION_STATE,
    TranscriptEntry,
    Strategy,
    OutcomeSummary,
    ServerMessageType,
    WebSocketMessage
} from '../lib/types';

const SESSION_STORAGE_KEY = 'negotiation_session_id';

function normalizeTranscriptText(text: string): string {
    return (text || '')
        .toLowerCase()
        .replace(/[^\w\s$]/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
}

export function shouldCollapseHumanTranscriptEntries(previous: TranscriptEntry | undefined, next: TranscriptEntry): boolean {
    if (!previous) return false;
    if (previous.isPartial || next.isPartial) return false;
    if (previous.speaker === 'ai' || next.speaker === 'ai') return false;
    if (previous.speaker !== next.speaker) return false;
    if ((previous.source || null) !== (next.source || null)) return false;
    if ((previous.context || null) !== (next.context || null)) return false;
    if (Math.abs(next.timestamp - previous.timestamp) > 5000) return false;

    const prevText = normalizeTranscriptText(previous.text);
    const nextText = normalizeTranscriptText(next.text);
    if (!prevText || !nextText) return false;
    if (prevText === nextText) return true;

    const longer = prevText.length >= nextText.length ? prevText : nextText;
    const shorter = prevText.length >= nextText.length ? nextText : prevText;
    return shorter.length <= 32 && longer.includes(shorter);
}

type Action =
    | { type: 'RESET_SESSION' }
    | { type: 'SET_CONNECTED'; payload: boolean }
    | { type: 'SET_CONSENTED'; payload: boolean }
    | { type: 'SET_NEGOTIATING'; payload: boolean }
    | { type: 'SET_SESSION_ID'; payload: string }
    | { type: 'UPSERT_TRANSCRIPT'; payload: TranscriptEntry }
    | { type: 'SET_STRATEGY'; payload: Strategy }
    | { type: 'SET_OUTCOME'; payload: OutcomeSummary }
    | { type: 'SET_ERROR'; payload: string | null }
    | { type: 'SET_DEGRADED'; payload: boolean }
    | { type: 'SET_AI_STATE'; payload: 'idle' | 'connecting' | 'connected' | 'listening' | 'thinking' | 'speaking' }
    | { type: 'SET_COPILOT_ACTIVE'; payload: boolean }
    | { type: 'SET_RESPONSE_MODE'; payload: 'advice' | 'command' | null }
    | { type: 'SET_AI_LIVE_TRANSCRIPTION'; payload: string | null }
    | { type: 'SET_LANGUAGE'; payload: string | null }
    | { type: 'SET_RESPONSE_LANGUAGE'; payload: string | null }
    | { type: 'SET_PERSISTENCE_READY'; payload: boolean }
    | { type: 'SET_DEGRADED_MODE'; payload: string | null }
    | { type: 'SET_ENROLLMENT_STATE'; payload: 'idle' | 'capturing' | 'processing' | 'success' | 'error' }
    | { type: 'SET_ENROLLMENT_COUNTDOWN'; payload: number | null }
    | { type: 'SET_ENROLLMENT_ERROR'; payload: string | null }
    | { type: 'SET_ENROLLMENT_PROGRESS'; payload: number | null }
    | { type: 'SET_ENROLLMENT_FEEDBACK'; payload: string | null }
    | { type: 'SET_SPEAKER_MODE'; payload: 'auto' | 'manual' }
    | { type: 'SET_VISION_INTEL'; payload: any | null };

function negotiationReducer(state: NegotiationState, action: Action): NegotiationState {
    switch (action.type) {
        case 'RESET_SESSION':
            return { ...INITIAL_NEGOTIATION_STATE };
        case 'SET_CONNECTED':
            return { ...state, isConnected: action.payload };
        case 'SET_CONSENTED':
            return { ...state, consentGiven: action.payload };
        case 'SET_NEGOTIATING':
            return { ...state, isNegotiating: action.payload };
        case 'SET_SESSION_ID':
            return { ...state, sessionId: action.payload };
        case 'UPSERT_TRANSCRIPT':
            const newEntry = action.payload;
            const existingIndex = state.transcript.findIndex((entry) => entry.id === newEntry.id);
            if (existingIndex >= 0) {
                const updatedTranscript = [...state.transcript];
                updatedTranscript[existingIndex] = {
                    ...updatedTranscript[existingIndex],
                    ...newEntry,
                };
                return { ...state, transcript: updatedTranscript };
            }
            const lastEntry = state.transcript[state.transcript.length - 1];
            
            // Merge only AI responses. Human turns should remain separate so repeated
            // attempts or corrected transcriptions do not collapse into one bubble.
            if (
                lastEntry && 
                lastEntry.speaker === 'ai' &&
                newEntry.speaker === 'ai' &&
                lastEntry.speaker === newEntry.speaker && 
                (newEntry.timestamp - lastEntry.timestamp) < 30000
            ) {
                // Ensure a space between segments if needed
                const separator = (lastEntry.text.endsWith(' ') || newEntry.text.startsWith(' ')) ? '' : ' ';
                
                const updatedLastEntry = {
                    ...lastEntry,
                    text: lastEntry.text + separator + newEntry.text,
                    timestamp: newEntry.timestamp // refresh timestamp to extend the window
                };
                
                return { 
                    ...state, 
                    transcript: [...state.transcript.slice(0, -1), updatedLastEntry] 
                };
            }

            if (shouldCollapseHumanTranscriptEntries(lastEntry, newEntry)) {
                const previousText = normalizeTranscriptText(lastEntry?.text || '');
                const nextText = normalizeTranscriptText(newEntry.text);
                const preferNew = nextText.length >= previousText.length;
                return {
                    ...state,
                    transcript: [
                        ...state.transcript.slice(0, -1),
                        preferNew
                            ? { ...lastEntry, ...newEntry }
                            : { ...newEntry, ...lastEntry, id: lastEntry!.id },
                    ],
                };
            }
            
            return { ...state, transcript: [...state.transcript, newEntry] };
        case 'SET_STRATEGY':
            return { ...state, strategy: action.payload };
        case 'SET_OUTCOME':
            return { ...state, outcome: action.payload };
        case 'SET_ERROR':
            return { ...state, error: action.payload };
        case 'SET_DEGRADED':
            return { ...state, aiDegraded: action.payload };
        case 'SET_AI_STATE':
            return { ...state, aiState: action.payload };
        case 'SET_COPILOT_ACTIVE':
            return { ...state, copilotActive: action.payload };
        case 'SET_RESPONSE_MODE':
            return { ...state, responseMode: action.payload };
        case 'SET_AI_LIVE_TRANSCRIPTION':
            return { ...state, aiLiveTranscription: action.payload };
        case 'SET_LANGUAGE':
            return { ...state, language: action.payload };
        case 'SET_RESPONSE_LANGUAGE':
            return { ...state, responseLanguage: action.payload };
        case 'SET_PERSISTENCE_READY':
            return { ...state, persistenceReady: action.payload };
        case 'SET_DEGRADED_MODE':
            return { ...state, degradedMode: action.payload };
        case 'SET_ENROLLMENT_STATE':
            return { ...state, enrollmentState: action.payload };
        case 'SET_ENROLLMENT_COUNTDOWN':
            return { ...state, enrollmentCountdown: action.payload };
        case 'SET_ENROLLMENT_ERROR':
            return { ...state, enrollmentError: action.payload };
        case 'SET_ENROLLMENT_PROGRESS':
            return { ...state, enrollmentProgress: action.payload };
        case 'SET_ENROLLMENT_FEEDBACK':
            return { ...state, enrollmentFeedback: action.payload };
        case 'SET_SPEAKER_MODE':
            return { ...state, speakerMode: action.payload };
        case 'SET_VISION_INTEL':
            return { ...state, visionIntel: action.payload };
        default:
            return state;
    }
}

export function useNegotiation() {
    const [state, dispatch] = useReducer(negotiationReducer, INITIAL_NEGOTIATION_STATE);

    const wsRef = useRef<NegotiationWebSocket | null>(null);
    const audioManagerRef = useRef<AudioWorkletManager | null>(null);
    const speakerDebounceTimerRef = useRef<NodeJS.Timeout | null>(null);
    const isEnrollmentStartingRef = useRef(false);

    const hasInitialized = useRef(false);
    const reconnectTimerRef = useRef<NodeJS.Timeout | null>(null);
    const reconnectAttemptsRef = useRef(0);
    const lastWsUrlRef = useRef<string | null>(null);
    const isNegotiatingRef = useRef(false);
    const sessionIdRef = useRef<string | null>(null);

    useEffect(() => {
        isNegotiatingRef.current = state.isNegotiating;
        sessionIdRef.current = state.sessionId;
    }, [state.isNegotiating, state.sessionId]);

    useEffect(() => {
        if (!hasInitialized.current) {
            audioManagerRef.current = new AudioWorkletManager();
            hasInitialized.current = true;
        }

        return () => {
            // Only disconnect on true unmount not inside strict effect reload
            if (wsRef.current?.isConnected) {
                wsRef.current.disconnect();
            }
        };
    }, []);

    const connect = useCallback(async (wsUrl: string) => {
        if (!audioManagerRef.current) return;
        let resolvedUrl = wsUrl;
        if (typeof window !== 'undefined') {
            const savedSessionId = window.localStorage.getItem(SESSION_STORAGE_KEY);
            if (savedSessionId) {
                const url = new URL(wsUrl, window.location.href);
                url.searchParams.set('session_id', savedSessionId);
                resolvedUrl = url.toString();
            }
        }
        lastWsUrlRef.current = resolvedUrl;

        wsRef.current = new NegotiationWebSocket(resolvedUrl, audioManagerRef.current);

        wsRef.current.onMessage((msg: WebSocketMessage) => {
            switch (msg.type) {
                case 'CONNECTION_ESTABLISHED':
                    // Do NOT reset session if session_id changes — a new session_id after
                    // reconnect was wiping all state (consent, transcript, enrollment) and
                    // sending the user back to the privacy screen mid-negotiation.
                    dispatch({ type: 'SET_CONNECTED', payload: true });
                    if ((msg.payload as any)?.session_id) {
                        const sessionId = (msg.payload as any).session_id;
                        dispatch({ type: 'SET_SESSION_ID', payload: sessionId });
                        if (typeof window !== 'undefined') {
                            window.localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
                        }
                    }
                    break;
                case 'CONSENT_ACKNOWLEDGED':
                    dispatch({ type: 'SET_CONSENTED', payload: true });
                    break;
                case 'ENROLLMENT_STARTED':
                    dispatch({ type: 'SET_ENROLLMENT_STATE', payload: 'capturing' });
                    dispatch({ type: 'SET_ENROLLMENT_COUNTDOWN', payload: null });
                    dispatch({ type: 'SET_ENROLLMENT_PROGRESS', payload: null });
                    dispatch({ type: 'SET_ENROLLMENT_FEEDBACK', payload: (msg.payload as any)?.message || null });
                    break;
                case 'ENROLLMENT_PROGRESS':
                    dispatch({ type: 'SET_ENROLLMENT_STATE', payload: 'capturing' });
                    dispatch({ type: 'SET_ENROLLMENT_PROGRESS', payload: (msg.payload as any)?.progress ?? null });
                    dispatch({ type: 'SET_ENROLLMENT_FEEDBACK', payload: (msg.payload as any)?.feedback_message || null });
                    break;
                case 'ENROLLMENT_COMPLETE':
                    console.log('[Enrollment] ENROLLMENT_COMPLETE received:', msg.payload);
                    dispatch({ type: 'SET_ENROLLMENT_STATE', payload: 'success' });
                    dispatch({ type: 'SET_ENROLLMENT_COUNTDOWN', payload: null });
                    dispatch({ type: 'SET_ENROLLMENT_PROGRESS', payload: (msg.payload as any)?.progress ?? null });
                    dispatch({ type: 'SET_ENROLLMENT_FEEDBACK', payload: (msg.payload as any)?.message || 'Voice sample ready.' });
                    dispatch({ type: 'SET_SPEAKER_MODE', payload: 'auto' });
                    audioManagerRef.current?.setBypassVAD(false);
                    break;
                case 'ENROLLMENT_FAILED':
                    const enrollFailPayload = msg.payload as any;
                    dispatch({ type: 'SET_ENROLLMENT_STATE', payload: 'error' });
                    dispatch({ type: 'SET_ENROLLMENT_COUNTDOWN', payload: null });
                    dispatch({ type: 'SET_ENROLLMENT_ERROR', payload: enrollFailPayload.message || 'Enrollment failed' });
                    dispatch({ type: 'SET_ENROLLMENT_PROGRESS', payload: enrollFailPayload.progress ?? null });
                    dispatch({ type: 'SET_ENROLLMENT_FEEDBACK', payload: enrollFailPayload.feedback_message || null });
                    audioManagerRef.current?.setBypassVAD(false);
                    break;
                case 'SPEAKER_MODE_CHANGED':
                    const modeChangePayload = msg.payload as any;
                    dispatch({ type: 'SET_SPEAKER_MODE', payload: modeChangePayload.mode });
                    break;
                case 'SESSION_STARTED':
                    dispatch({ type: 'SET_NEGOTIATING', payload: true });
                    dispatch({ type: 'SET_AI_STATE', payload: 'connected' });
                    dispatch({ type: 'SET_PERSISTENCE_READY', payload: true });
                    // Brief "Connected" flash, then switch to listening
                    setTimeout(() => dispatch({ type: 'SET_AI_STATE', payload: 'listening' }), 2000);
                    break;
                case 'AI_CONNECTING':
                    dispatch({ type: 'SET_AI_STATE', payload: 'connecting' });
                    break;
                case 'AI_LISTENING':
                    dispatch({ type: 'SET_AI_STATE', payload: 'listening' });
                    // Clear live AI transcription when AI finishes speaking
                    dispatch({ type: 'SET_AI_LIVE_TRANSCRIPTION', payload: null });
                    break;
                case 'AI_THINKING':
                    dispatch({ type: 'SET_AI_STATE', payload: 'thinking' });
                    break;
                case 'AI_SPEAKING':
                    dispatch({ type: 'SET_AI_STATE', payload: 'speaking' });
                    break;
                case 'SESSION_RESTORED':
                    window.dispatchEvent(new CustomEvent('negotiation-session-restored', {
                        detail: msg.payload
                    }));
                    break;
                case 'TRANSCRIPT_PARTIAL':
                case 'TRANSCRIPT_UPDATE':
                    const transcriptPayload = msg.payload as any;
                    const normalizedEntry: TranscriptEntry = {
                        id: transcriptPayload.id || `t-${Date.now()}`,
                        speaker: (transcriptPayload.speaker || 'unknown').toLowerCase() as 'user' | 'counterparty' | 'ai' | 'unknown',
                        text: transcriptPayload.text || '',
                        timestamp: transcriptPayload.timestamp || Date.now(),
                        isPartial: Boolean(transcriptPayload.is_partial ?? transcriptPayload.isPartial),
                        confidence: transcriptPayload.confidence,
                        context: transcriptPayload.context,
                        transcriptionConfidence: transcriptPayload.transcription_confidence,
                        eligibleForContext: transcriptPayload.eligible_for_context,
                        eligibleForResearch: transcriptPayload.eligible_for_research,
                        source: transcriptPayload.source,
                    };
                    dispatch({ type: 'UPSERT_TRANSCRIPT', payload: normalizedEntry });
                    if (!normalizedEntry.isPartial) {
                        window.dispatchEvent(new CustomEvent('negotiation-transcript', {
                            detail: { speaker: normalizedEntry.speaker, text: normalizedEntry.text }
                        }));
                    }
                    break;
                case 'STRATEGY_UPDATE':
                    dispatch({ type: 'SET_STRATEGY', payload: msg.payload as Strategy });
                    break;
                case 'AI_RESPONSE':
                    const aiPayload = msg.payload as any;
                    dispatch({
                        type: 'UPSERT_TRANSCRIPT',
                        payload: {
                            id: `ai_${Date.now()}`,
                            speaker: 'ai',
                            text: aiPayload.text,
                            timestamp: aiPayload.timestamp || Date.now()
                        }
                    });
                    break;
                case 'NEGOTIATION_STATE_CHANGED':
                    // Session state changed (IDLE, CONSENTED, ACTIVE, ENDING)
                    console.log('NEGOTIATION_STATE_CHANGED:', msg.payload);
                    const statePayload = msg.payload as any;
                    if (statePayload.current_state === 'ACTIVE') {
                        dispatch({ type: 'SET_NEGOTIATING', payload: true });
                    } else if (statePayload.current_state === 'IDLE') {
                        // Backend transitioned to IDLE — could be a Gemini error, session end,
                        // or internal failure. Do NOT reset consent or send user to privacy screen.
                        // Only update the UI states that don't cause navigation:
                        dispatch({ type: 'SET_NEGOTIATING', payload: false });
                        dispatch({ type: 'SET_AI_STATE', payload: 'idle' });
                        dispatch({ type: 'SET_COPILOT_ACTIVE', payload: false });
                        // NOTE: consentGiven, enrollmentState, transcript are preserved.
                        // The user explicitly consented — a backend error should not un-consent them.
                    }
                    break;
                case 'STATE_UPDATE':
                    // Button-triggered system: AI extracted state from transcript
                    console.log('STATE_UPDATE received:', msg.payload);
                    // This will be handled by parent component via custom event
                    window.dispatchEvent(new CustomEvent('negotiation-state-update', {
                        detail: msg.payload
                    }));
                    break;
                case 'RESEARCH_STARTED':
                    console.log('RESEARCH_STARTED received:', msg.payload);
                    window.dispatchEvent(new CustomEvent('market-research-started', {
                        detail: msg.payload
                    }));
                    break;
                case 'RESEARCH_COMPLETE':
                    // Market research completed
                    console.log('RESEARCH_COMPLETE received:', msg.payload);
                    window.dispatchEvent(new CustomEvent('market-research-complete', {
                        detail: msg.payload
                    }));
                    break;
                case 'CONTEXT_UPDATE':
                    // Dual-Model: ListenerAgent extracted context from background audio analysis
                    console.log('[ListenerAgent] CONTEXT_UPDATE received:', msg.payload);
                    window.dispatchEvent(new CustomEvent('negotiation-context-update', {
                        detail: msg.payload
                    }));
                    break;
                case 'LANGUAGE_UPDATE':
                    const languagePayload = msg.payload as any;
                    dispatch({ type: 'SET_LANGUAGE', payload: languagePayload.language || null });
                    dispatch({ type: 'SET_RESPONSE_LANGUAGE', payload: languagePayload.response_language || null });
                    break;
                case 'PERSISTENCE_STATUS':
                    dispatch({ type: 'SET_PERSISTENCE_READY', payload: Boolean((msg.payload as any)?.ready) });
                    break;
                case 'VISION_STATUS':
                    window.dispatchEvent(new CustomEvent('negotiation-vision-status', {
                        detail: msg.payload
                    }));
                    break;
                case 'VISION_INTEL':
                    // Structured scene observation from Pro vision analysis.
                    // Dispatch to global event so any UI component can react.
                    dispatch({ type: 'SET_VISION_INTEL', payload: msg.payload as any });
                    window.dispatchEvent(new CustomEvent('negotiation-vision-intel', {
                        detail: msg.payload
                    }));
                    break;
                case 'DEGRADED_MODE_UPDATE':
                    dispatch({ type: 'SET_DEGRADED', payload: Boolean((msg.payload as any)?.active) });
                    dispatch({ type: 'SET_DEGRADED_MODE', payload: (msg.payload as any)?.mode || null });
                    break;
                case 'OUTCOME_SUMMARY':
                    if (typeof window !== 'undefined') {
                        window.localStorage.removeItem(SESSION_STORAGE_KEY);
                    }
                    dispatch({ type: 'SET_OUTCOME', payload: msg.payload as OutcomeSummary });
                    dispatch({ type: 'SET_NEGOTIATING', payload: false });
                    dispatch({ type: 'SET_CONSENTED', payload: false });
                    dispatch({ type: 'SET_AI_STATE', payload: 'idle' });
                    dispatch({ type: 'SET_DEGRADED', payload: false });
                    dispatch({ type: 'SET_DEGRADED_MODE', payload: null });
                    dispatch({ type: 'SET_ERROR', payload: null });
                    dispatch({ type: 'SET_COPILOT_ACTIVE', payload: false });
                    dispatch({ type: 'SET_ENROLLMENT_STATE', payload: 'idle' });
                    break;
                case 'AUDIO_INTERRUPTED':
                    if (typeof (audioManagerRef.current as any).clearQueue === 'function') {
                        (audioManagerRef.current as any).clearQueue();
                    }
                    dispatch({ type: 'SET_AI_STATE', payload: 'listening' });
                    break;
                case 'COPILOT_STARTED':
                    dispatch({ type: 'SET_COPILOT_ACTIVE', payload: true });
                    console.log('[Copilot] Proactive monitoring mode activated');
                    break;
                case 'RESPONSE_MODE_SET':
                    const modePayload = msg.payload as { mode: 'advice' | 'command' };
                    dispatch({ type: 'SET_RESPONSE_MODE', payload: modePayload.mode });
                    console.log('[Copilot] Response mode set to:', modePayload.mode);
                    break;
                case 'AI_TRANSCRIPTION_DISPLAY':
                    // disabled
                    break;
                case 'SESSION_RECONNECTING':
                    dispatch({ type: 'SET_ERROR', payload: 'Reconnecting to AI...' });
                    break;
                case 'AI_DEGRADED':
                    dispatch({ type: 'SET_DEGRADED', payload: true });
                    dispatch({ type: 'SET_DEGRADED_MODE', payload: (msg.payload as any)?.mode || 'manual_only' });
                    break;
                case 'ERROR':
                    const errPayload = msg.payload as any;
                    dispatch({ type: 'SET_ERROR', payload: errPayload.message || 'Unknown error' });
                    break;
            }
        });

        wsRef.current.onClose(() => {
            // Mark as disconnected but DO NOT auto-reconnect and DO NOT reset state.
            // Auto-reconnect creates a new backend session → new session_id → RESET_SESSION
            // → user dumped to privacy screen mid-negotiation.
            // The user must explicitly re-open the connection themselves.
            dispatch({ type: 'SET_CONNECTED', payload: false });
            dispatch({ type: 'SET_ERROR', payload: 'Connection lost. Please refresh to reconnect.' });
        });

        wsRef.current.onError((err: any) => {
            dispatch({ type: 'SET_ERROR', payload: 'WebSocket connection error' });
        });

        await wsRef.current.connect();
    }, []);

    const grantConsent = useCallback((version: string, mode: string) => {
        wsRef.current?.sendControl('PRIVACY_CONSENT_GRANTED', { version, mode });
    }, []);

    const startNegotiation = useCallback(async (contextStr: string, userContext?: Record<string, unknown>) => {
        audioManagerRef.current?.setBypassVAD(false);
        await audioManagerRef.current?.initPlayback();

        await audioManagerRef.current?.startCapture({
            onChunk: (chunk: ArrayBuffer) => {
                wsRef.current?.sendAudioChunk(chunk);
            },
            onSpeech: () => {
                // local VAD — do not change AI state indicator
            },
            onUtteranceEnd: (utterance) => {
                wsRef.current?.sendUtteranceEnd({
                    utterance_id: utterance.utteranceId,
                    started_at: utterance.startedAt / 1000,
                    ended_at: utterance.endedAt / 1000,
                    duration_ms: utterance.durationMs,
                    rms: utterance.rms,
                });
            },
        });

        wsRef.current?.sendControl('START_NEGOTIATION', {
            context: contextStr,
            user_context: userContext ?? {},
        });
    }, []);

    const endNegotiation = useCallback((finalPrice: number | null, initialPrice: number | null) => {
        wsRef.current?.sendControl('END_NEGOTIATION', { final_price: finalPrice, initial_price: initialPrice });
        audioManagerRef.current?.stopCapture();
        if (reconnectTimerRef.current) {
            clearTimeout(reconnectTimerRef.current);
            reconnectTimerRef.current = null;
        }
    }, []);

    const sendFrame = useCallback((base64Image: string, isLiveMode: boolean = false) => {
        wsRef.current?.sendControl('VISION_FRAME', {
            image: base64Image,
            timestamp: Date.now(),
            live_mode: isLiveMode,
        });
    }, []);

    // Manual speaker selection (bypasses voice fingerprinting)
    const setManualSpeaker = useCallback((speaker: 'user' | 'counterparty') => {
        const speakerUpper = speaker.toUpperCase() as 'USER' | 'COUNTERPARTY';
        
        // ═══════════════════════════════════════════════════════════
        // 🖱️ MANUAL BUTTON CLICK LOG
        // ═══════════════════════════════════════════════════════════
        console.log('');
        console.log('╔═══════════════════════════════════════════════════════╗');
        console.log('║         🖱️  MANUAL SPEAKER BUTTON CLICKED            ║');
        console.log('╚═══════════════════════════════════════════════════════╝');
        console.log(`📊 Speaker Selected: ${speakerUpper}`);
        console.log(`⏰ Timestamp: ${new Date().toLocaleTimeString()}`);
        console.log('');
        console.log('📤 Sending to Backend:');
        console.log('   Message Type: SPEAKER_IDENTIFIED');
        console.log(`   Payload: { speaker: "${speaker.toLowerCase()}", timestamp: ${Date.now()} }`);
        console.log('');
        console.log('✅ Backend will label transcript with this speaker.');
        console.log('═══════════════════════════════════════════════════════');
        console.log('');

        // Send to backend immediately
        wsRef.current?.sendControl('SPEAKER_IDENTIFIED', {
            speaker: speaker.toLowerCase(),
            timestamp: Date.now()
        });
    }, []);

    const startCopilot = useCallback(() => {
        console.log('[Copilot] Starting proactive monitoring mode');
        wsRef.current?.sendControl('START_COPILOT', {});
    }, []);

    const setUserAddressingAI = useCallback((active: boolean) => {
        console.log(`[Copilot] User addressing AI: ${active}`);
        // Bypass VAD when user is holding to speak to AI — ensures all audio
        // flows immediately without silence-detection dropping the first chunks.
        audioManagerRef.current?.setBypassVAD(active);
        wsRef.current?.sendControl('USER_ADDRESSING_AI', { active });
    }, []);

    const startEnrollment = useCallback(async () => {
        console.log('[Enrollment] Starting voice enrollment');

        // Guard against re-entrant calls (double-click or retry while still starting)
        if (isEnrollmentStartingRef.current) {
            console.warn('[Enrollment] Already starting, ignoring duplicate call');
            return;
        }
        isEnrollmentStartingRef.current = true;

        try {
            // If audio capture is somehow still active from a previous failed attempt, stop it first
            const captureState = audioManagerRef.current?.currentCaptureState;
            if (captureState && captureState !== 'idle' && captureState !== 'error') {
                console.log(`[Enrollment] Stopping existing capture in state "${captureState}" before restart`);
                audioManagerRef.current?.stopCapture();
                // Brief pause for teardown to complete
                await new Promise(resolve => setTimeout(resolve, 100));
            }

            // Force bypass VAD for enrollment - send ALL audio (including silence gaps)
            audioManagerRef.current?.setBypassVAD(true);

            await audioManagerRef.current?.startCapture({
                onChunk: (chunk: ArrayBuffer) => {
                    wsRef.current?.sendAudioChunk(chunk);
                },
                onSilence: () => {
                    // Ignore silence during enrollment - VAD bypass sends everything
                },
                onSpeech: () => {
                    // Ignore speech detection during enrollment
                }
            });

            console.log('[Enrollment] Audio capture started (VAD bypassed), waiting 500ms for stabilization...');

            // Wait 500ms for audio to stabilize before notifying backend
            await new Promise(resolve => setTimeout(resolve, 500));

            console.log('[Enrollment] Sending ENROLLMENT_START to backend');
            wsRef.current?.sendControl('ENROLLMENT_START', {});
        } catch (error) {
            console.error('[Enrollment] Failed to start audio capture:', error);
            dispatch({ type: 'SET_ENROLLMENT_ERROR', payload: 'Failed to access microphone' });
        } finally {
            isEnrollmentStartingRef.current = false;
        }
    }, []);

    const sendEnrollmentAudio = useCallback((audioChunk: ArrayBuffer) => {
        wsRef.current?.sendAudioChunk(audioChunk);
    }, []);

    const setSpeakerMode = useCallback((mode: 'auto' | 'manual') => {
        console.log(`[SpeakerMode] Changing mode to: ${mode}`);
        wsRef.current?.sendControl('SPEAKER_MODE_CHANGE', { mode });
    }, []);

    const setResponseLanguage = useCallback((language: string) => {
        dispatch({ type: 'SET_RESPONSE_LANGUAGE', payload: language });
        wsRef.current?.sendControl('SET_RESPONSE_LANGUAGE', { language });
    }, []);

    return {
        state,
        connect,
        grantConsent,
        startNegotiation,
        endNegotiation,
        sendFrame,
        setManualSpeaker,
        startCopilot,
        setUserAddressingAI,
        startEnrollment,
        sendEnrollmentAudio,
        setSpeakerMode,
        setResponseLanguage,
        websocket: wsRef.current,
        aiLiveTranscription: state.aiLiveTranscription,
        audioManager: audioManagerRef.current,
    };
}
