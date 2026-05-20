import React, { useEffect, useState, useRef } from 'react';
import {
  Package, DollarSign, Target, TrendingUp, Radio, MessageSquare,
  Activity, AlertTriangle, Zap, FileText, User, Users
} from 'lucide-react';
import { NegotiationState } from '../../hooks/useNegotiationState';
import { TranscriptEntry } from '../../lib/types';

interface NegotiationStateCardProps {
  state: NegotiationState;
  isDualModelActive?: boolean;
  liveTranscript?: TranscriptEntry[];
  isAddressingAI?: boolean;
}

const GLASS = 'rgba(255,255,255,0.06)';
const BLUR  = 'blur(40px) saturate(200%)';
const BORDER = '1px solid rgba(255,255,255,0.13)';
const SHADOW = '0 8px 32px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.08)';
const G  = '#f5c518';
const GL = '#ffd700';
const GF = 'rgba(245,197,24,0.08)';
const GG = 'rgba(245,197,24,0.2)';
const TM = 'rgba(255,255,255,0.75)';
const TB = 'rgba(255,255,255,0.97)';

function StateField({ label, value, icon, isUpdated, valueColor }: {
  label: string; value: string; icon: React.ReactNode; isUpdated?: boolean; valueColor?: string;
}) {
  return (
    <div className="flex items-center justify-between p-2.5 rounded-xl transition-all duration-300"
      style={{
        background: isUpdated ? 'rgba(245,197,24,0.15)' : 'rgba(255,255,255,0.05)',
        border: isUpdated ? `1px solid ${GG}` : '1px solid rgba(255,255,255,0.09)',
        boxShadow: isUpdated ? '0 0 16px rgba(245,197,24,0.2)' : 'none',
      }}>
      <div className="flex items-center gap-2">
        <div style={{ color: G }}>{icon}</div>
        <span className="text-xs font-medium" style={{ color: TM }}>{label}</span>
      </div>
      <span className="text-xs font-bold" style={{ color: valueColor || GL }}>{value}</span>
    </div>
  );
}

function SentimentBadge({ sentiment }: { sentiment: string | null }) {
  if (!sentiment || sentiment === 'unknown') return <span className="text-xs" style={{ color: TM }}>Unknown</span>;
  const map: Record<string, { bg: string; color: string; label: string }> = {
    positive: { bg: 'rgba(74,222,128,0.1)',  color: '#4ade80', label: '😊 Positive' },
    neutral:  { bg: 'rgba(250,204,21,0.1)',  color: '#facc15', label: '😐 Neutral'  },
    negative: { bg: 'rgba(248,113,113,0.1)', color: '#f87171', label: '😠 Negative' },
  };
  const s = map[sentiment.toLowerCase()] || { bg: GF, color: GL, label: sentiment };
  return (
    <span className="text-xs font-bold px-2 py-0.5 rounded-full"
      style={{ background: s.bg, color: s.color, border: `1px solid ${s.color}40` }}>
      {s.label}
    </span>
  );
}

function NegotiationTypeBadge({ type }: { type: string | null }) {
  if (!type || type === 'unknown') return <span className="text-xs" style={{ color: TM }}>Unknown</span>;
  const labels: Record<string, string> = {
    buying_goods: '🛒 Buying', selling_goods: '🏷️ Selling', renting: '🏠 Renting',
    salary: '💼 Salary', service: '🔧 Service', contract: '📄 Contract', other: '🤝 Other',
  };
  return (
    <span className="text-xs font-bold px-2 py-0.5 rounded-full"
      style={{ background: GF, color: GL, border: `1px solid ${GG}` }}>
      {labels[type] || type}
    </span>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="pt-1 pb-0.5 flex items-center gap-2">
      <span className="text-[10px] font-bold uppercase tracking-[0.18em]"
        style={{ color: G, textShadow: '0 0 8px rgba(245,197,24,0.5)' }}>{children}</span>
      <div className="flex-1 h-px" style={{ background: 'linear-gradient(to right, rgba(245,197,24,0.3), transparent)' }} />
    </div>
  );
}

export function NegotiationStateCard({ state, isDualModelActive = false, liveTranscript = [], isAddressingAI = false }: NegotiationStateCardProps) {
  const [recentlyUpdated, setRecentlyUpdated] = useState<string | null>(null);
  const prevStateRef = useRef(state);

  useEffect(() => {
    const prev = prevStateRef.current;
    const checks: [boolean, string][] = [
      [state.item !== prev.item && !!state.item, 'item'],
      [state.seller_price !== prev.seller_price && state.seller_price !== null, 'seller_price'],
      [state.user_offer !== prev.user_offer && state.user_offer !== null, 'user_offer'],
      [state.target_price !== prev.target_price && state.target_price > 0, 'target_price'],
      [state.max_price !== prev.max_price && state.max_price > 0, 'max_price'],
      [state.counterparty_sentiment !== prev.counterparty_sentiment, 'sentiment'],
      [state.counterparty_goal !== prev.counterparty_goal && !!state.counterparty_goal, 'goal'],
      [state.key_moments.length !== prev.key_moments.length, 'key_moments'],
      [state.leverage_points.length !== prev.leverage_points.length, 'leverage'],
      [state.market_data !== prev.market_data && !!state.market_data, 'market_data'],
    ];
    for (const [changed, key] of checks) {
      if (changed) { setRecentlyUpdated(key); setTimeout(() => setRecentlyUpdated(null), 2000); break; }
    }
    prevStateRef.current = state;
  }, [state]);

  return (
    <div className="rounded-2xl p-4" style={{ background: GLASS, backdropFilter: BLUR, border: BORDER, boxShadow: SHADOW }}>
      <h3 className="text-sm font-bold mb-3 flex items-center gap-2">
        <Package className="w-4 h-4" style={{ color: G }} />
        <span style={{ color: GL, textShadow: '0 0 10px rgba(245,197,24,0.35)' }}>Negotiation Context</span>
        {isDualModelActive && (
          <span className="ml-auto flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded-full"
            style={{ background: 'rgba(52,211,153,0.1)', color: '#34d399', border: '1px solid rgba(52,211,153,0.25)' }}>
            <Radio className="w-3 h-3 animate-pulse" />Listener Active
          </span>
        )}
      </h3>

      <div className="space-y-2">
        <StateField label="Item" value={state.item || 'Not detected yet'}
          icon={<Package className="w-3.5 h-3.5" />} isUpdated={recentlyUpdated === 'item'} />

        <div className="flex items-center justify-between p-2.5 rounded-xl"
          style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.09)' }}>
          <div className="flex items-center gap-2">
            <Activity className="w-3.5 h-3.5" style={{ color: G }} />
            <span className="text-xs font-medium" style={{ color: TM }}>Your Role</span>
          </div>
          <NegotiationTypeBadge type={state.negotiation_type} />
        </div>

        <SectionLabel>Prices</SectionLabel>
        <StateField label="Counterparty's Price" value={state.seller_price != null ? `${state.seller_price}` : 'Not mentioned'}
          icon={<Users className="w-3.5 h-3.5" />} isUpdated={recentlyUpdated === 'seller_price'} valueColor="#f87171" />
        <StateField label="Your Price / Offer" value={state.user_offer != null ? `${state.user_offer}` : 'Not mentioned'}
          icon={<User className="w-3.5 h-3.5" />} isUpdated={recentlyUpdated === 'user_offer'} valueColor="#60a5fa" />
        <StateField label="Your Target" value={state.target_price > 0 ? `${state.target_price}` : 'Not set'}
          icon={<Target className="w-3.5 h-3.5" />} isUpdated={recentlyUpdated === 'target_price'} valueColor="#4ade80" />
        <StateField label="Your Walk-Away" value={state.max_price > 0 ? `${state.max_price}` : 'Not set'}
          icon={<DollarSign className="w-3.5 h-3.5" />} isUpdated={recentlyUpdated === 'max_price'} valueColor={GL} />

        <SectionLabel>Counterparty</SectionLabel>
        <div className="flex items-center justify-between p-2.5 rounded-xl"
          style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.09)' }}>
          <div className="flex items-center gap-2">
            <Activity className="w-3.5 h-3.5" style={{ color: G }} />
            <span className="text-xs font-medium" style={{ color: TM }}>Sentiment</span>
          </div>
          <SentimentBadge sentiment={state.counterparty_sentiment} />
        </div>

        {state.counterparty_goal && (
          <div className="p-2.5 rounded-xl"
            style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.09)' }}>
            <div className="flex items-start gap-2">
              <Target className="w-3.5 h-3.5 mt-0.5 shrink-0" style={{ color: G }} />
              <div>
                <span className="text-xs font-medium block mb-0.5" style={{ color: TM }}>Their Goal</span>
                <span className="text-xs" style={{ color: TB }}>{state.counterparty_goal}</span>
              </div>
            </div>
          </div>
        )}

        {state.key_moments.length > 0 && (
          <div className="p-2.5 rounded-xl"
            style={{ background: 'rgba(245,197,24,0.06)', border: '1px solid rgba(245,197,24,0.18)' }}>
            <div className="flex items-center gap-1.5 mb-1.5">
              <Zap className="w-3.5 h-3.5" style={{ color: GL }} />
              <span className="text-xs font-bold" style={{ color: GL }}>Key Moments</span>
            </div>
            <ul className="space-y-1">
              {state.key_moments.slice(-3).map((m, i) => (
                <li key={i} className="text-xs flex gap-1.5" style={{ color: TB }}>
                  <span style={{ color: G }}>•</span>{m}
                </li>
              ))}
            </ul>
          </div>
        )}

        {state.leverage_points.length > 0 && (
          <div className="p-2.5 rounded-xl"
            style={{ background: 'rgba(167,139,250,0.06)', border: '1px solid rgba(167,139,250,0.18)' }}>
            <div className="flex items-center gap-1.5 mb-1.5">
              <AlertTriangle className="w-3.5 h-3.5" style={{ color: '#c4b5fd' }} />
              <span className="text-xs font-bold" style={{ color: '#c4b5fd' }}>Leverage Points</span>
            </div>
            <ul className="space-y-1">
              {state.leverage_points.slice(-3).map((l, i) => (
                <li key={i} className="text-xs flex gap-1.5" style={{ color: TB }}>
                  <span style={{ color: '#a78bfa' }}>•</span>{l}
                </li>
              ))}
            </ul>
          </div>
        )}

        {state.market_data && (
          <div className="p-2.5 rounded-xl"
            style={{ background: 'rgba(96,165,250,0.06)', border: '1px solid rgba(96,165,250,0.18)' }}>
            <div className="flex items-start gap-2">
              <TrendingUp className="w-3.5 h-3.5 mt-0.5 shrink-0" style={{ color: '#60a5fa' }} />
              <div className="flex-1">
                <div className="text-xs font-bold mb-1" style={{ color: '#93c5fd' }}>Market Research</div>
                <div className="text-xs leading-relaxed" style={{ color: TB }}>
                  {typeof state.market_data === 'string' ? state.market_data : (
                    <div className="space-y-0.5">
                      {state.market_data.price_range && (
                        <div className="font-medium">Range: {typeof state.market_data.price_range === 'object'
                          ? `${state.market_data.price_range.min} – ${state.market_data.price_range.max}`
                          : state.market_data.price_range}</div>
                      )}
                      {state.market_data.key_facts && <div>{state.market_data.key_facts}</div>}
                      {state.market_data.leverage && <div style={{ color: GL }}>⚡ {state.market_data.leverage}</div>}
                      {state.market_data.summary && <div>{state.market_data.summary}</div>}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {state.transcript_snippet && (
          <div className="p-2.5 rounded-xl"
            style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.09)' }}>
            <div className="flex items-center gap-1.5 mb-1">
              <FileText className="w-3.5 h-3.5" style={{ color: G }} />
              <span className="text-xs font-medium" style={{ color: TM }}>Last Snippet</span>
            </div>
            <p className="text-xs italic leading-relaxed line-clamp-3" style={{ color: TB }}>{state.transcript_snippet}</p>
          </div>
        )}

        {liveTranscript.length > 0 && (
          <div className="mt-1 pt-2" style={{ borderTop: '1px solid rgba(255,255,255,0.08)' }}>
            <div className="flex items-center gap-2 mb-1.5">
              <MessageSquare className="w-3.5 h-3.5" style={{ color: G }} />
              <span className="text-xs font-bold uppercase tracking-wide" style={{ color: TM }}>
                {isAddressingAI ? 'Speaking to AI' : 'Live Conversation'}
              </span>
              <span className="ml-auto w-2 h-2 rounded-full animate-pulse" style={{ background: '#4ade80' }} />
            </div>
            <div className="space-y-1 max-h-36 overflow-y-auto">
              {liveTranscript.slice(-6).map((entry, index) => {
                const isUser = entry.speaker === 'user';
                const isAI = entry.speaker === 'ai';
                const bg = isAI ? 'rgba(96,165,250,0.07)' : isUser ? 'rgba(167,139,250,0.07)' : 'rgba(245,197,24,0.07)';
                const color = isAI ? '#93c5fd' : isUser ? '#c4b5fd' : GL;
                return (
                  <div key={`${entry.timestamp}-${index}`} className="text-xs px-2 py-1 rounded-lg leading-relaxed"
                    style={{ background: bg, border: `1px solid ${color}25`, color: TB }}>
                    <span className="font-bold mr-1" style={{ color }}>{isAI ? 'AI:' : isUser ? 'You:' : 'Counterparty:'}</span>
                    {entry.text}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
