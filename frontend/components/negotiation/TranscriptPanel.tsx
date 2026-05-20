import React, { useRef, useEffect } from 'react';
import { TranscriptEntry } from '../../lib/types';
import { User, MessageSquare, Cpu } from 'lucide-react';

interface TranscriptPanelProps {
  entries: TranscriptEntry[];
  title?: string;
}

const G  = '#f5c518';
const GL = '#ffd700';
const GF = 'rgba(245,197,24,0.07)';
const GG = 'rgba(245,197,24,0.2)';
const TM = 'rgba(255,255,255,0.75)';
const TB = 'rgba(255,255,255,0.97)';
const GLASS = 'rgba(255,255,255,0.03)';
const BLUR  = 'blur(32px) saturate(180%)';

export function TranscriptPanel({ entries, title = 'Transcript' }: TranscriptPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [entries]);

  const panelStyle = {
    background: GLASS,
    backdropFilter: BLUR,
    border: `1px solid ${GG}`,
    boxShadow: `0 0 28px rgba(245,197,24,0.06), inset 0 1px 0 rgba(255,255,255,0.06)`,
  };

  if (entries.length === 0) {
    return (
      <div className="h-full w-full rounded-2xl flex flex-col items-center justify-center text-center space-y-3 p-6" style={panelStyle}>
        <div className="w-12 h-12 rounded-full flex items-center justify-center animate-pulse"
          style={{ background: GF, border: `1px solid ${GG}` }}>
          <MessageSquare className="w-6 h-6" style={{ color: G }} />
        </div>
        <p className="text-sm" style={{ color: TM }}>
          {title === 'AI Advisor' ? 'AI responses will appear here...' : 'Waiting for conversation to start...'}
        </p>
      </div>
    );
  }

  return (
    <div className="h-full w-full rounded-2xl overflow-hidden flex flex-col" style={panelStyle}>
      <div className="px-4 py-2.5 flex items-center gap-2 shrink-0"
        style={{ background: 'rgba(245,197,24,0.05)', borderBottom: `1px solid ${GG}` }}>
        <MessageSquare className="w-4 h-4" style={{ color: G }} />
        <h2 className="text-xs font-bold uppercase tracking-[0.15em]"
          style={{ color: GL, textShadow: `0 0 10px rgba(245,197,24,0.4)` }}>{title}</h2>
      </div>

      <div ref={scrollRef} className="flex-1 p-4 overflow-y-auto space-y-4 scroll-smooth">
        {entries.map((entry, index) => {
          const isUser = entry.speaker === 'user';
          const isCounterparty = entry.speaker === 'counterparty';
          const isAi = entry.speaker === 'ai';
          const isUnknown = entry.speaker === 'unknown';

          const avatarStyle = isUser
            ? { background: 'linear-gradient(135deg, #f5c518, #ffd700)', boxShadow: '0 0 12px rgba(245,197,24,0.4)' }
            : isCounterparty
            ? { background: 'rgba(251,146,60,0.7)' }
            : isUnknown
            ? { background: 'rgba(156,163,175,0.7)' }
            : { background: 'rgba(96,165,250,0.7)' };

          const bubbleStyle = isUser
            ? { background: 'rgba(245,197,24,0.1)', border: '1px solid rgba(245,197,24,0.28)', color: 'rgba(255,255,255,0.97)' }
            : isCounterparty
            ? { background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: 'rgba(255,255,255,0.97)' }
            : isUnknown
            ? { background: 'rgba(156,163,175,0.05)', border: '1px solid rgba(156,163,175,0.2)', color: 'rgba(255,255,255,0.85)' }
            : { background: 'rgba(96,165,250,0.08)', border: '1px solid rgba(96,165,250,0.22)', color: 'rgba(255,255,255,0.97)', fontStyle: 'italic' as const };

          const speakerLabel = isUser ? 'User' : isCounterparty ? 'Counterparty' : isUnknown ? 'Unknown' : 'AI';
          const speakerColor = isUser ? '#f5c518' : isCounterparty ? '#fb923c' : isUnknown ? '#9ca3af' : '#60a5fa';

          return (
            <div key={entry.id || `t-${index}`} className={`flex w-full ${isUser ? 'justify-end' : 'justify-start'}`}>
              <div className={`flex max-w-[80%] ${isUser ? 'flex-row-reverse' : 'flex-row'} items-end gap-2`}>
                <div className="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0" style={avatarStyle}>
                  {isUser
                    ? <User className="w-3.5 h-3.5" style={{ color: '#080810' }} />
                    : isCounterparty
                    ? <MessageSquare className="w-3.5 h-3.5 text-white" />
                    : <Cpu className="w-3.5 h-3.5 text-white" />}
                </div>
                <div className="flex flex-col gap-1">
                  <div className={`px-3 py-2 rounded-2xl ${isUser ? 'rounded-br-none' : 'rounded-bl-none'}`} style={bubbleStyle}>
                    <p className="text-sm leading-relaxed">{entry.text}</p>
                  </div>
                  <div className={`text-[10px] font-medium tracking-wide flex items-center gap-2 ${isUser ? 'justify-end' : 'justify-start'}`}
                    style={{ color: TM }}>
                    <span className="uppercase" style={{ color: speakerColor }}>{speakerLabel}</span>
                    <span>• {new Date(entry.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                    {entry.confidence !== undefined && (
                      <span className="px-1.5 py-0.5 rounded text-[9px]" style={{ background: 'rgba(255,255,255,0.1)' }}>
                        {Math.round(entry.confidence * 100)}%
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
