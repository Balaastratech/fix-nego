import { describe, expect, it } from 'vitest';

import { shouldCollapseHumanTranscriptEntries } from './useNegotiation';
import type { TranscriptEntry } from '../lib/types';

describe('shouldCollapseHumanTranscriptEntries', () => {
  it('collapses trivial duplicate human turns from the same source', () => {
    const previous: TranscriptEntry = {
      id: '1',
      speaker: 'user',
      text: 'Hello.',
      timestamp: 1000,
      source: 'desktop_local_mic',
    };
    const next: TranscriptEntry = {
      id: '2',
      speaker: 'user',
      text: 'hello',
      timestamp: 2200,
      source: 'desktop_local_mic',
    };

    expect(shouldCollapseHumanTranscriptEntries(previous, next)).toBe(true);
  });

  it('does not collapse materially different human turns', () => {
    const previous: TranscriptEntry = {
      id: '1',
      speaker: 'user',
      text: 'Should I sell this for $800?',
      timestamp: 1000,
      source: 'desktop_local_mic',
    };
    const next: TranscriptEntry = {
      id: '2',
      speaker: 'user',
      text: 'What if I wait another week?',
      timestamp: 2200,
      source: 'desktop_local_mic',
    };

    expect(shouldCollapseHumanTranscriptEntries(previous, next)).toBe(false);
  });
});
