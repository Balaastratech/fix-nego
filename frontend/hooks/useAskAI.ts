import { useState, useCallback } from 'react';
import { NegotiationWebSocket } from '../lib/websocket';
import { NegotiationState, TranscriptEntry } from './useNegotiationState';

/**
 * Hook for handling one-shot Ask AI requests.
 * 
 * Features:
 * - Manages loading state during AI response
 * - Bundles negotiation state and sends ASK_ADVICE message
 * - Formats transcript as string for backend
 * - Validates websocket availability
 * - Triggers research state updates
 * 
 * Requirements: 5.3, 13.1, 13.2
 * 
 * @param state - Current negotiation state
 * @param websocket - WebSocket connection to backend
 * @param setResearchState - Function to update research state
 * @returns askAI callback and loading state
 */
export function useAskAI(
  state: NegotiationState,
  websocket: NegotiationWebSocket | null,
  setResearchState: (isResearching: boolean, progress: string | null) => void
) {
  const [isLoading, setIsLoading] = useState(false);

  /**
   * Ask AI based on current negotiation state.
   */
  const askAI = useCallback(async () => {
    // Check if websocket is available
    if (!websocket || !websocket.isConnected) {
      console.error('Cannot ask AI: WebSocket not connected');
      return;
    }

    // Prevent multiple simultaneous requests
    if (isLoading) {
      console.warn('AI request already in progress');
      return;
    }

    // Set loading state
    setIsLoading(true);
    
    // Trigger research state
    setResearchState(true, 'Analyzing conversation...');

    try {
      // Format transcript as string with speaker labels
      const formattedTranscript = formatTranscript(state.transcript);

      // CRITICAL: Resume AudioContext before anything else
      // Button clicks can suspend it, causing corrupted audio frames
      if (typeof (websocket as any).resumeAudioContexts === 'function') {
        await (websocket as any).resumeAudioContexts();
        // Small delay to let the worklet stabilize after resume
        await new Promise(resolve => setTimeout(resolve, 50));
      }

      // Bundle state and send ASK_ADVICE message
      websocket.sendControl('ASK_ADVICE', {
        state: {
          item: state.item,
          seller_price: state.seller_price,
          target_price: state.target_price,
          max_price: state.max_price,
          market_data: state.market_data,
          transcript: formattedTranscript
        }
      });

      // Update progress after a short delay
      setTimeout(() => {
        setResearchState(true, 'Researching market prices...');
      }, 1500);

      // Note: Loading state will be cleared by parent component
      // when AI_SPEAKING or AI_THINKING message is received
    } catch (error) {
      console.error('Failed to ask AI:', error);
      // Clear loading state on error
      setIsLoading(false);
      setResearchState(false, null);
    }
  }, [state, websocket, isLoading, setResearchState]);

  /**
   * Manually clear loading state.
   * Used by parent component when AI response starts or errors occur.
   */
  const clearLoading = useCallback(() => {
    setIsLoading(false);
  }, []);

  return {
    askAI,
    isLoading,
    clearLoading
  };
}

/**
 * Format transcript entries as a string with speaker labels.
 * 
 * Format: "[SPEAKER] text\n[SPEAKER] text\n..."
 * 
 * @param entries - Transcript entries to format
 * @returns Formatted transcript string
 */
function formatTranscript(entries: TranscriptEntry[]): string {
  return entries
    .map(entry => `[${entry.speaker}] ${entry.text}`)
    .join('\n');
}
