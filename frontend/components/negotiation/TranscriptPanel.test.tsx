import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TranscriptPanel } from './TranscriptPanel';
import { TranscriptEntry } from '../../lib/types';

describe('TranscriptPanel', () => {
  const mockEntries: TranscriptEntry[] = [
    {
      id: '1',
      speaker: 'user',
      text: 'Hello, I would like to negotiate.',
      timestamp: Date.now(),
    },
    {
      id: '2',
      speaker: 'counterparty',
      text: 'Sure, what price are you thinking?',
      timestamp: Date.now() + 1000,
    },
    {
      id: '3',
      speaker: 'unknown',
      text: 'This is an unknown speaker.',
      timestamp: Date.now() + 2000,
    },
  ];

  it('should display speaker labels correctly', () => {
    render(<TranscriptPanel entries={mockEntries} />);
    
    expect(screen.getByText('User')).toBeInTheDocument();
    expect(screen.getByText('Counterparty')).toBeInTheDocument();
    expect(screen.getByText('Unknown')).toBeInTheDocument();
  });

  it('should display confidence score when provided', () => {
    const entriesWithConfidence: TranscriptEntry[] = [
      {
        id: '1',
        speaker: 'user',
        text: 'Test message',
        timestamp: Date.now(),
        confidence: 0.95,
      },
    ];
    
    render(<TranscriptPanel entries={entriesWithConfidence} />);
    expect(screen.getByText('95%')).toBeInTheDocument();
  });
});
