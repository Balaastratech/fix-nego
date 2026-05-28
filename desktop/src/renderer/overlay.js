"use strict";

const bridge = window.companionBridge;
const channel = new BroadcastChannel("negotiation_companion_ui");
const STORAGE_KEY = "companion_prefs_v2";
const BACKEND_WS_URL = "ws://localhost:8000/ws";

// ─── State ────────────────────────────────────────────────────────────────────
const state = {
  ws: null,
  wsConnecting: false,
  sessionId: null,
  backendState: "IDLE",   // IDLE → CONSENTED → ACTIVE
  _pendingStart: false,
  backendReady: false,    // true once CONNECTION_ESTABLISHED received with ready_to_start
  sessionLive: false,
  sessionStarting: false,
  sessionPaused: false,

  // Hold-to-ask
  holdActive: false,
  holdSource: null,
  awaitingPrivateReply: false,

  // Audio
  playbackCtx: null,
  playbackDest: null,
  playbackEl: null,
  playbackNextAt: 0,
  _playbackDoneTimer: null,
  playbackGain: null,
  playbackPanner: null,
  activePlaybackSources: [],
  ignoreIncomingAiUntil: 0,
  isDucked: false,
  duckTimer: null,
  // Audio mix — reset every session (no persistence per user request).
  // userAiVolume is the baseline 0..2.0 (slider 0-200%); duck multiplies by 0.8.
  userAiVolume: 1.0,
  autoDuckEnabled: true,
  duckMultiplier: 0.8,   // drop to 80% of baseline (was 0.3 = 30%)
  micStream: null,
  selectedMicDeviceId: null,
  selectedMicLabel: null,
  micCapture: null,
  askCapture: null,
  micForwardEl: null,
  meetingCapture: null,
  copilotStarted: false,
  vbCableDeviceId: null,
  vbCableLabel: null,
  listeningDeviceId: null,
  listeningDeviceLabel: null,

  // Meeting
  meetingTargets: [],
  screenSources: [],        // from getScreenSources — has thumbnails for the menu
  selectedTarget: null,
  selectedSourceId: null,   // desktop source id from getScreenSources, used for startMeetingCapture

  // Chat (private AI only)
  chatEntries: [],

  // Full conversation (for full window)
  conversationEntries: [],
  privateEntries: [],

  // UI
  orbState: "idle",   // idle | active | listening | speaking
  menuOpen: false,
  langMenuOpen: false,
  dragging: false,
  dragPointerId: null,
  dragOffX: 0,
  dragOffY: 0,
  dragMoved: false,

  // Ring animation for mouse 3s hold
  ringTimer: null,
  ringStarted: false,

  prefs: {
    lastMeetingTitle: null,
    listeningDeviceId: null,
    vbCableDeviceId: null,
  },
};

// ─── DOM ─────────────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const root           = $("overlay-root");
const orb            = $("assistant-orb");
const orbIcon        = $("orb-icon");
const ringPath       = $("ring-path");
const menu           = $("meeting-menu");
const panel          = $("caption-panel");
const chatFeed       = $("chat-feed");
const video          = $("meeting-video");
const capturePreview = $("capture-preview");

// ─── Prefs ───────────────────────────────────────────────────────────────────
function loadPrefs() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) Object.assign(state.prefs, JSON.parse(raw));
  } catch (_) {}
}
function savePrefs() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state.prefs)); } catch (_) {}
}

// ─── Orb state ───────────────────────────────────────────────────────────────
function setOrbState(s) {
  state.orbState = s;
  updateMicMuteState();
  orb.className = `assistant-orb state-${s}`;
  if (s === "processing") {
    orbIcon.textContent = "...";
    return;
  }
  if (s === "responding") {
    orbIcon.textContent = "o";
    return;
  }
  if (s === "degraded") {
    orbIcon.textContent = "!";
    return;
  }
  if (s === "paused") {
    orbIcon.textContent = "II";
    return;
  }
  orbIcon.textContent = s === "listening" ? "◉" : s === "speaking" ? "◎" : "✦";
}

function updateMicMuteState() {
  if (!state.micForwardEl) return;
  const shouldMute = state.holdActive || state.orbState === "listening";
  state.micForwardEl.muted = shouldMute;
  console.log(`[MicForward] Mic muted = ${shouldMute} (holdActive=${state.holdActive}, orbState=${state.orbState}, awaitingPrivateReply=${state.awaitingPrivateReply})`);
}


// ─── Root classes ─────────────────────────────────────────────────────────────
function updateRootClasses() {
  root.classList.toggle("has-content", state.privateEntries.length > 0 && !state.holdActive);
  root.classList.toggle("is-listening", state.holdActive);
  root.classList.toggle("is-paused", state.sessionPaused);
  root.classList.toggle(
    "live-controls",
    state.sessionLive || state.sessionStarting || state.sessionPaused || state.menuOpen || state.langMenuOpen
  );
}

function desiredOverlayPresentation() {
  // Screen picker needs full panel space to be usable
  const pickerEl = document.getElementById("screen-picker-overlay");
  if (pickerEl && !pickerEl.classList.contains("hidden")) return "panel";
  if (state.menuOpen) return "menu";
  if (state.langMenuOpen) return "panel";
  if (state.sessionPaused) return "compact";
  if (state.holdActive) return "listening";
  if (state.sessionLive || state.sessionStarting) {
    return state.privateEntries.length > 0 ? "captions" : "compact";
  }
  return "idle";
}

function syncOverlayPresentation() {
  updateRootClasses();
  bridge.setOverlayPresentation(desiredOverlayPresentation()).catch(() => {});
}

// ─── Background contrast for adaptive color ──────────────────────────────────
async function refreshContrast() {
  try {
    const result = await bridge.getOverlayContrast();
    root.classList.toggle("bg-light", result?.theme === "dark-text");
    root.classList.toggle("bg-dark",  result?.theme !== "dark-text");
  } catch (_) {}
}
setInterval(refreshContrast, 1500);

// ─── Chat rendering ───────────────────────────────────────────────────────────
function getChatIterations() {
  const iterations = [];
  let currentIteration = null;

  for (const entry of state.privateEntries) {
    if (entry.speaker === "user") {
      if (currentIteration && currentIteration.aiEntry) {
        iterations.push(currentIteration);
        currentIteration = null;
      }
      if (!currentIteration) {
        currentIteration = {
          userEntry: entry,
          aiEntry: null
        };
      } else {
        currentIteration.userEntry = entry;
      }
    } else if (entry.speaker === "ai") {
      if (!currentIteration) {
        currentIteration = {
          userEntry: null,
          aiEntry: entry
        };
      } else {
        currentIteration.aiEntry = entry;
      }
      if (!entry.isPartial) {
        iterations.push(currentIteration);
        currentIteration = null;
      }
    }
  }
  if (currentIteration) {
    iterations.push(currentIteration);
  }
  return iterations;
}

function formatChatTimestamp(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  const pad = (n, w = 2) => String(n).padStart(w, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`;
}

function renderChat() {
  chatFeed.innerHTML = "";
  // Newest pair on top, oldest on bottom. Each pair shows the user question
  // first (left-aligned, yellow) then the AI reply right below it (right-aligned,
  // green). Within a pair, USER comes BEFORE AI so the reader sees the question
  // and then the answer — like a real chat transcript.
  const iterations = getChatIterations().slice().reverse();

  iterations.forEach((iter, idx) => {
    const block = document.createElement("div");
    block.className = `iteration-block ${idx === 0 ? "recent" : "previous"}`;

    const renderBubble = (entry, side) => {
      if (!entry) return;
      const row = document.createElement("div");
      row.className = `chat-row chat-row-${side}`;
      const bubble = document.createElement("div");
      bubble.className = `chat-bubble ${side}${entry.isPartial ? " partial" : ""}`;
      const body = document.createElement("div");
      body.className = "chat-bubble-text";
      body.textContent = entry.text;
      bubble.appendChild(body);
      if (entry.lang) {
        const tag = document.createElement("span");
        tag.className = "lang-tag";
        tag.textContent = entry.lang;
        bubble.appendChild(tag);
      }
      const meta = document.createElement("div");
      meta.className = "chat-bubble-meta";
      const who = document.createElement("span");
      who.className = "chat-bubble-who";
      who.textContent = side === "user" ? "You" : "AI";
      const time = document.createElement("span");
      time.className = "chat-bubble-time";
      time.textContent = formatChatTimestamp(entry.ts);
      meta.appendChild(who);
      meta.appendChild(time);
      row.appendChild(bubble);
      row.appendChild(meta);
      block.appendChild(row);
    };

    // USER first, then AI — matches expected reading order Q → A.
    renderBubble(iter.userEntry, "user");
    renderBubble(iter.aiEntry, "ai");

    chatFeed.appendChild(block);
  });

  // Newest pair is at the TOP — scroll to top on each render so the latest
  // exchange is always visible without manual scrolling.
  chatFeed.scrollTop = 0;

  updateRootClasses();
  syncOverlayPresentation();
}

function pushChat(speaker, text) {
  if (!text?.trim()) return;
  state.chatEntries.push({ speaker, text, ts: Date.now() });
  state.chatEntries = state.chatEntries.slice(-20);
  renderChat();
}

function entryFromPayload(payload, fallbackSpeaker = "unknown") {
  return {
    id: payload.id || `${fallbackSpeaker}_${payload.timestamp || Date.now()}`,
    speaker: payload.speaker || fallbackSpeaker,
    text: payload.text || "",
    ts: payload.timestamp || Date.now(),
    context: payload.context,
    isPartial: Boolean(payload.is_partial || payload.isPartial),
    source: payload.source || null,
  };
}

function normalizeTranscriptText(text) {
  return String(text || "")
    .toLowerCase()
    .replace(/[^\w\s$]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function shouldCollapseHumanEntries(previous, next) {
  if (!previous || !next) return false;
  if (previous.isPartial || next.isPartial) return false;
  if (previous.speaker === "ai" || next.speaker === "ai") return false;
  if (previous.speaker !== next.speaker) return false;
  if ((previous.source || null) !== (next.source || null)) return false;
  if ((previous.context || null) !== (next.context || null)) return false;
  if (Math.abs((next.ts || 0) - (previous.ts || 0)) > 5000) return false;

  const prevText = normalizeTranscriptText(previous.text);
  const nextText = normalizeTranscriptText(next.text);
  if (!prevText || !nextText) return false;
  if (prevText === nextText) return true;

  const longer = prevText.length >= nextText.length ? prevText : nextText;
  const shorter = prevText.length >= nextText.length ? nextText : prevText;
  return shorter.length <= 32 && longer.includes(shorter);
}

function shouldAppendHumanContinuation(previous, next) {
  if (!previous || !next) return false;
  if (previous.isPartial || next.isPartial) return false;
  if (previous.speaker === "ai" || next.speaker === "ai") return false;
  if (previous.speaker !== next.speaker) return false;
  if ((previous.source || null) !== (next.source || null)) return false;
  if ((previous.context || null) !== (next.context || null)) return false;
  if (Math.abs((next.ts || 0) - (previous.ts || 0)) > 12000) return false;

  const prevText = String(previous.text || "").trim();
  const nextText = String(next.text || "").trim();
  const prevNorm = normalizeTranscriptText(prevText);
  const nextNorm = normalizeTranscriptText(nextText);
  if (!prevNorm || !nextNorm || prevNorm === nextNorm) return false;
  if (prevNorm.includes(nextNorm) || nextNorm.includes(prevNorm)) return false;

  const prevEndsSentence = /[.!?]["')\]]*$/.test(prevText);
  const nextStartsLower = /^[a-z]/.test(nextText);
  const nextIsShort = nextNorm.length <= 48;
  const prevIsLong = prevNorm.length >= 48;
  return !prevEndsSentence || nextStartsLower || (nextIsShort && prevIsLong);
}

function mergeHumanEntryText(previousText, nextText) {
  const prevText = String(previousText || "").trim();
  const newText = String(nextText || "").trim();
  const prevNorm = normalizeTranscriptText(prevText);
  const nextNorm = normalizeTranscriptText(newText);
  if (!prevNorm) return newText;
  if (!nextNorm) return prevText;
  if (prevNorm === nextNorm || prevNorm.includes(nextNorm)) return prevText;
  if (nextNorm.includes(prevNorm)) return newText;
  const joiner = /[-/]\s*$/.test(prevText) ? "" : " ";
  return `${prevText}${joiner}${newText}`.replace(/\s+/g, " ").trim();
}

function upsertEntry(list, entry, limit) {
  const next = [...list];
  const existingIndex = next.findIndex((item) => item.id === entry.id);
  if (existingIndex >= 0) {
    next[existingIndex] = { ...next[existingIndex], ...entry };
    return next.slice(-limit);
  }
  const last = next[next.length - 1];
  if (
    last &&
    shouldAppendHumanContinuation(last, entry)
  ) {
    next[next.length - 1] = {
      ...last,
      ...entry,
      id: last.id,
      text: mergeHumanEntryText(last.text, entry.text),
      ts: entry.ts || last.ts,
      isPartial: false,
    };
    return next.slice(-limit);
  }
  if (
    last &&
    shouldCollapseHumanEntries(last, entry)
  ) {
    const lastText = normalizeTranscriptText(last.text);
    const nextText = normalizeTranscriptText(entry.text);
    next[next.length - 1] =
      nextText.length >= lastText.length
        ? { ...last, ...entry }
        : { ...entry, ...last, id: last.id };
    return next.slice(-limit);
  }
  const insertIndex = next.findIndex((item) => (entry.ts || 0) < (item.ts || 0));
  if (insertIndex >= 0) {
    next.splice(insertIndex, 0, entry);
    return next.slice(-limit);
  }
  next.push(entry);
  return next.slice(-limit);
}

// ─── Broadcast to full window ─────────────────────────────────────────────────
function broadcast(type, payload) {
  channel.postMessage({ type, payload });
}
function broadcastSnapshot() {
  broadcast("STATE_SNAPSHOT", {
    sessionLive: state.sessionLive,
    sessionStarting: state.sessionStarting,
    sessionPaused: state.sessionPaused,
    backendReady: state.backendReady,
    selectedTarget: state.selectedTarget || null,
    meetingTitle: state.selectedTarget?.window_title || null,
    meetingTargets: state.meetingTargets,
    conversationEntries: state.conversationEntries.slice(-80),
    privateEntries: state.privateEntries.slice(-40),
    listeningDeviceId: state.listeningDeviceId,
    vbCableDeviceId: state.vbCableDeviceId,
    selectedMicLabel: state.selectedMicLabel || null,
    holdActive: state.holdActive,
    orbState: state.orbState,
  });
}

// ─── PCM helpers ─────────────────────────────────────────────────────────────
function f32ToI16Buffer(f32) {
  const out = new Int16Array(f32.length);
  for (let i = 0; i < f32.length; i++) {
    const s = Math.max(-1, Math.min(1, f32[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out.buffer;
}
function toBase64(buf) {
  const bytes = new Uint8Array(buf);
  let b = "";
  for (let i = 0; i < bytes.byteLength; i++) b += String.fromCharCode(bytes[i]);
  return btoa(b);
}

// ─── WebSocket ────────────────────────────────────────────────────────────────
function wsSend(type, payload) {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) return false;
  state.ws.send(JSON.stringify({ type, payload }));
  return true;
}

function stopActivePlayback(sendDone = false) {
  if (state.activePlaybackSources && state.activePlaybackSources.length > 0) {
    state.activePlaybackSources.forEach((src) => {
      try { src.stop(); } catch (_) {}
    });
    state.activePlaybackSources = [];
  }
  state.playbackNextAt = 0;
  if (state._playbackDoneTimer) {
    clearTimeout(state._playbackDoneTimer);
    state._playbackDoneTimer = null;
  }
  state.ignoreIncomingAiUntil = Date.now() + 500;
  if (sendDone) {
    wsSend("AI_PLAYBACK_DONE", {});
  }
}

function traceClientEvent(eventName, summary, detail = {}) {
  return wsSend("TRACE_CLIENT_EVENT", {
    surface: "overlay",
    event_name: eventName,
    summary,
    detail,
  });
}

function resolvePreferredCaptureSourceId(sourceId = null) {
  return sourceId || state.selectedSourceId || state.selectedTarget?.target_id || null;
}

async function syncDesktopCaptureSelection(sourceId = null) {
  if (!bridge?.rebindMeetingTarget || !state.selectedTarget) return;
  const resolvedSourceId = resolvePreferredCaptureSourceId(sourceId);
  state.selectedSourceId = resolvedSourceId;
  await bridge.rebindMeetingTarget({
    ...state.selectedTarget,
    source_id: resolvedSourceId,
  });
}

async function connectBackend() {
  if (state.ws?.readyState === WebSocket.OPEN) return;
  if (state.wsConnecting) return;
  state.wsConnecting = true;

  await new Promise((resolve, reject) => {
    const ws = new WebSocket(BACKEND_WS_URL);
    ws.binaryType = "arraybuffer";
    ws.onopen = () => { state.ws = ws; state.wsConnecting = false; resolve(); };
    ws.onerror = () => { state.wsConnecting = false; reject(new Error("WS error")); };
    ws.onclose = () => {
      state.wsConnecting = false;
      state.backendState = "IDLE";
      state._pendingStart = false;
      if (!state.sessionLive) state.sessionPaused = false;
    };
    ws.onmessage = handleWsMessage;
  });
}

function handleWsMessage(ev) {
  if (ev.data instanceof ArrayBuffer) {
    if (state.sessionPaused || state.holdActive || Date.now() < state.ignoreIncomingAiUntil) return;
    playPcm(ev.data);
    return;
  }
  let msg;
  try { msg = JSON.parse(ev.data); } catch (_) { return; }

  const t = msg.type;
  const p = msg.payload || {};

  if (t === "CONNECTION_ESTABLISHED") {
    state.sessionId     = p.session_id;
    state.backendState  = "IDLE";
    state.backendReady  = Boolean(p.ready_to_start);
    traceClientEvent("connection_established_received", "Overlay received websocket connection acknowledgement", {
      session_id: p.session_id,
      restored: Boolean(p.restored),
      ready_to_start: Boolean(p.ready_to_start),
      trace_report_path: p.trace_report_path || null,
    });
    if (p.restored) {
      state.sessionLive = true;
      state.sessionStarting = false;
      state.sessionPaused = p.state === "PAUSED";
      state.backendState = state.sessionPaused ? "PAUSED" : "ACTIVE";
      setOrbState(state.sessionPaused ? "paused" : "active");
      updateRootClasses();
      syncOverlayPresentation();
      broadcastSnapshot();
    } else {
      // Fresh connection — broadcast readiness so full window can enable Start button
      broadcastSnapshot();
    }
    // Do NOT send consent here — wait until startSession() so timing is correct
  }
  if (t === "CONSENT_ACKNOWLEDGED") {
    state.backendState = "CONSENTED";
    // If startSession() is waiting for consent ack, proceed to START_NEGOTIATION
    if (state._pendingStart) {
      state._pendingStart = false;
      sendStartNegotiation();
    }
  }
  if (t === "SESSION_STARTED") {
    state.sessionLive = true;
    state.sessionStarting = false;
    state.sessionPaused = false;
    state.backendState = "ACTIVE";
    state.copilotStarted = false;
    setOrbState("active");
    updateRootClasses();
    syncOverlayPresentation();
    traceClientEvent("session_started_received", "Overlay received SESSION_STARTED", {
      meeting_title: state.selectedTarget?.window_title || null,
    });

    // Now that backend is ACTIVE, send the messages that require ACTIVE state
    wsSend("MEETING_BINDING", {
      target_id: state.selectedTarget?.target_id,
      window_title: state.selectedTarget?.window_title,
      platform_hint: state.selectedTarget?.platform_hint || "generic",
      output_device_id: state.vbCableDeviceId,
      output_device_label: state.vbCableLabel,
      is_bound: true,
    });
    reportCaptureHealth({
      mic_forward_ok: Boolean(state.micForwardEl),
      frame_capture_ok: Boolean(state.meetingCapture),
      remote_audio_ok: Boolean(state.meetingCapture?.hasAudio),
    });

    broadcastSnapshot();
  }
  if (t === "COPILOT_STARTED") {
    // Backend confirmed copilot active — ensure local state is consistent
    state.sessionLive = true;
    state.sessionPaused = false;
    state.copilotStarted = true;
    setOrbState("active");
    updateRootClasses();
    syncOverlayPresentation();
    broadcastSnapshot();
  }
  if (t === "SESSION_PAUSED") {
    state.sessionLive = true;
    state.sessionStarting = false;
    state.sessionPaused = true;
    state.backendState = "PAUSED";
    state.holdActive = false;
    state.awaitingPrivateReply = false;
    stopActivePlayback(false);
    setOrbState("paused");
    updateRootClasses();
    syncOverlayPresentation();
    broadcastSnapshot();
  }
  if (t === "SESSION_RESUMED") {
    state.sessionLive = true;
    state.sessionStarting = false;
    state.sessionPaused = false;
    state.backendState = "ACTIVE";
    setOrbState("active");
    updateRootClasses();
    syncOverlayPresentation();
    broadcastSnapshot();
  }
  if (t === "TRANSCRIPT_PARTIAL" || t === "TRANSCRIPT_UPDATE") {
    if (state.sessionPaused) return;
    const isAskAI = p.context === "ask_ai";
    const isAiTranscript = (p.speaker || "").toLowerCase() === "ai";
    if (isAskAI && t === "TRANSCRIPT_PARTIAL" && !state.holdActive && !state.awaitingPrivateReply) {
      console.log("[Audio] Discarding late/stale private ask partial transcript");
      return;
    }
    const entry = entryFromPayload(p, p.speaker || "unknown");
    if (!isAskAI && !isAiTranscript) {
      // Fix: when a FINAL (non-partial) transcript arrives, remove all partial entries
      // for the same speaker so the same utterance doesn't appear twice (partial + final).
      if (t === "TRANSCRIPT_UPDATE" && !entry.isPartial) {
        state.conversationEntries = state.conversationEntries.filter(
          (e) => !(e.isPartial && e.speaker === entry.speaker)
        );
      }
      state.conversationEntries = upsertEntry(state.conversationEntries, entry, 80);
      broadcast("CONVERSATION_ENTRY", entry);
      if (!entry.isPartial && !state.copilotStarted && entry.speaker !== "ai") {
        state.copilotStarted = true;
        wsSend("START_COPILOT", {});
      }
      // Trigger counterparty volume ducking semantically
      if (entry.speaker === "counterparty") {
        duckPlayback(true);
      }
    }
    if (t === "TRANSCRIPT_PARTIAL") {
      // Interim = words arriving live; show "speaking" state
      setOrbState(state.holdActive ? "listening" : "speaking");
    }
    if (t === "TRANSCRIPT_UPDATE" && !isAskAI && !isAiTranscript) {
      // Final transcript received — back to ready
      setOrbState("active");
    }
    if (isAskAI && p.text) {
      if (t === "TRANSCRIPT_UPDATE" && !entry.isPartial) {
        state.privateEntries = state.privateEntries.filter(
          (e) => !(e.isPartial && e.speaker === entry.speaker)
        );
      }
      if (!entry.isPartial) {
        pushChat(entry.speaker === "ai" ? "ai" : "user", p.text);
      }
      state.privateEntries = upsertEntry(state.privateEntries, entry, 40);
      broadcast("PRIVATE_ENTRY", entry);
      
      // Always call renderChat to ensure live transcribing is rendered!
      renderChat();

      if (!entry.isPartial) {
        if (entry.speaker === "ai") {
          state.awaitingPrivateReply = false;
          setOrbState(state.sessionLive ? "active" : "idle");
        } else {
          setOrbState("processing");
        }
      }
    }
    broadcastSnapshot();
  }
  if (t === "TRANSCRIPT_DELETE") {
    const entryId = p.id;
    state.conversationEntries = state.conversationEntries.filter((e) => e.id !== entryId);
    state.privateEntries = state.privateEntries.filter((e) => e.id !== entryId);
    broadcastSnapshot();
  }
  if (t === "AI_RESPONSE") {
    if (state.sessionPaused) return;
    setOrbState("responding");
    const entry = entryFromPayload({ ...p, speaker: "ai" }, "ai");
    pushChat("ai", p.text);
    state.privateEntries = upsertEntry(state.privateEntries, entry, 40);
    broadcast("PRIVATE_ENTRY", entry);
    state.awaitingPrivateReply = false;
    setTimeout(() => { if (state.sessionLive && !state.holdActive) setOrbState("active"); }, 3000);
    broadcastSnapshot();
  }
  if (t === "AI_THINKING") {
    if (state.sessionPaused) return;
    setOrbState("processing");
    broadcastSnapshot();
  }
  if (t === "AUDIO_INTERRUPTED") {
    if (state.activePlaybackSources && state.activePlaybackSources.length > 0) {
      state.activePlaybackSources.forEach((src) => {
        try { src.stop(); } catch (_) {}
      });
      state.activePlaybackSources = [];
    }
    state.playbackNextAt = 0;
    if (state._playbackDoneTimer) {
      clearTimeout(state._playbackDoneTimer);
      state._playbackDoneTimer = null;
    }
    state.ignoreIncomingAiUntil = Date.now() + 250;
    setOrbState(state.holdActive ? "listening" : "active");
    broadcastSnapshot();
  }
  if (t === "AI_LISTENING" && !state.holdActive) {
    setOrbState("active");
    broadcastSnapshot();
  }
  if (t === "RESEARCH_STARTED") {
    broadcast("RESEARCH_STARTED", p);
  }
  if (t === "RESEARCH_COMPLETE") {
    broadcast("RESEARCH_COMPLETE", p);
  }
  if (t === "RESEARCH_FAILED") {
    broadcast("RESEARCH_FAILED", p);
  }
  if (t === "OUTCOME_SUMMARY") {
    void teardownLocalSession({ resetSelection: true, closeSocket: true });
  }
  if (t === "DEGRADED_MODE_UPDATE" && p.active) {
    setOrbState("degraded");
    broadcast("DEGRADED", p);
    broadcastSnapshot();
  }
  if (t === "ERROR" && p.code === "CONNECTION_TIMEOUT") {
    state.sessionStarting = false;
    state.sessionLive = false;
    state.sessionPaused = false;
    state.backendState = "IDLE";
    state.copilotStarted = false;
    state.holdActive = false;
    state.awaitingPrivateReply = false;
    if (state.micForwardEl) state.micForwardEl.muted = false;
    setOrbState("degraded");
    updateRootClasses();
    renderChat();
    broadcast("DEGRADED", {
      active: true,
      mode: "connection_timeout",
      reasons: [p.message || "AI connection timed out"],
    });
    broadcastSnapshot();
  }
}

// ─── Audio playback (AI voice) ────────────────────────────────────────────────
// Atomic init: concurrent playPcm() callers share a single in-flight init
// promise so we never create two AudioContexts (which would reset
// playbackNextAt mid-stream and cause the "plays half then restarts" stutter).
async function ensurePlayback() {
  if (state.playbackCtx) return;
  if (state.playbackInitPromise) return state.playbackInitPromise;
  state.playbackInitPromise = (async () => {
    const ctx = new AudioContext({ sampleRate: 24000, latencyHint: "interactive" });
    const dest = ctx.createMediaStreamDestination();
    const gain = ctx.createGain();
    // No stereo pan — AI voice plays centered in BOTH ears. The old "pan to
    // right ear" was a design experiment that breaks BT earbuds and made users
    // think audio was missing or going to the wrong device.
    gain.gain.setValueAtTime(state.userAiVolume || 1.0, ctx.currentTime);
    gain.connect(dest);
    const panner = null;
    const el = document.createElement("audio");
    el.autoplay = true;
    el.srcObject = dest.stream;

    // Try to bind to the user's chosen listening sink (headphones).
    // If binding fails, fall back to the OS default device rather than refusing
    // to play — the AI-loopback-into-counterparty leak that this used to guard
    // against is already prevented backend-side via _remote_ai_playback_window_active.
    // Refusing to play here just makes the user hear nothing, which is worse.
    // If the listening device is the OS default (or we have no specific device),
    // skip setSinkId entirely — the audio element plays through OS default
    // automatically. setSinkId("default") works but adds a permission roundtrip
    // and can briefly delay playback, contributing to the "AI response late"
    // symptom on cold start.
    let sinkBound = false;
    const wantsOsDefault = !state.listeningDeviceId || state.listeningDeviceId === "default";
    if (!wantsOsDefault && typeof el.setSinkId === "function") {
      try {
        await el.setSinkId(state.listeningDeviceId);
        sinkBound = true;
      } catch (err) {
        console.warn("[Playback] setSinkId failed — falling back to OS default output:", err?.message || err);
      }
    }
    if (wantsOsDefault) {
      console.log("[Playback] AI voice using OS default output (system tray device).");
    } else if (!sinkBound) {
      console.warn("[Playback] Fell back to OS default. Wanted device label:", state.listeningDeviceLabel);
    }

    try {
      await el.play();
    } catch (err) {
      console.error("[Playback] el.play() failed:", err?.message || err);
    }

    state.playbackCtx = ctx;
    state.playbackDest = dest;
    state.playbackGain = gain;
    state.playbackPanner = panner;
    state.playbackNextAt = 0;
    state.playbackEl = el;
    state.playbackSinkBound = sinkBound;
  })();
  try {
    await state.playbackInitPromise;
  } finally {
    state.playbackInitPromise = null;
  }
}

function playPcm(buffer) {
  ensurePlayback().then(() => {
    const ctx = state.playbackCtx;
    
    // Secure casting against odd byte lengths (prevents RangeError crash)
    let safeBuffer = buffer;
    if (buffer.byteLength % 2 !== 0) {
      const padded = new Uint8Array(buffer.byteLength + 1);
      padded.set(new Uint8Array(buffer));
      safeBuffer = padded.buffer;
    }
    const i16 = new Int16Array(safeBuffer);
    
    const ab = ctx.createBuffer(1, i16.length, 24000);
    const ch = ab.getChannelData(0);
    for (let i = 0; i < i16.length; i++) ch[i] = i16[i] / 32768;
    const src = ctx.createBufferSource();
    src.buffer = ab;
    src.connect(state.playbackGain || state.playbackDest);
    
    const now = ctx.currentTime;
    let startAt;
    if (state.playbackNextAt <= now) {
      // Build a small 50ms initial jitter buffer for continuous playback
      startAt = now + 0.05;
    } else {
      // Align exactly at the end of the last queued chunk with no gaps
      startAt = state.playbackNextAt;
    }
    src.start(startAt);
    const chunkEndAt = startAt + ab.duration;
    state.playbackNextAt = chunkEndAt;

    if (!state.activePlaybackSources) {
      state.activePlaybackSources = [];
    }
    state.activePlaybackSources.push(src);
    src.onended = () => {
      state.activePlaybackSources = state.activePlaybackSources.filter(s => s !== src);
    };

    // AI_PLAYBACK_DONE — accurate timer-based approach:
    clearTimeout(state._playbackDoneTimer);
    const msUntilChunkEnd = Math.max(0, (chunkEndAt - ctx.currentTime) * 1000);
    state._playbackDoneTimer = setTimeout(() => {
      if (ctx.currentTime >= state.playbackNextAt - 0.05) {
        traceClientEvent("ai_playback_done_sent", "Overlay sent AI_PLAYBACK_DONE after audio playback finished", {});
        wsSend("AI_PLAYBACK_DONE", {});
        if (state.sessionLive && !state.holdActive && state.orbState === "responding") {
          setOrbState("active");
        }
      }
    }, msUntilChunkEnd + 900);
  }).catch(() => {});
}

// Apply the current effective gain (baseline × duck-multiplier-if-ducked).
// Called whenever the slider, toggle, or duck state changes.
function applyAiGain(rampSeconds = 0.1) {
  if (!state.playbackCtx || !state.playbackGain) return;
  const ctx = state.playbackCtx;
  const baseline = Math.max(0, state.userAiVolume || 0);
  const target = state.isDucked ? baseline * state.duckMultiplier : baseline;
  state.playbackGain.gain.setValueAtTime(state.playbackGain.gain.value, ctx.currentTime);
  state.playbackGain.gain.linearRampToValueAtTime(target, ctx.currentTime + rampSeconds);
}

function duckPlayback(speaking) {
  if (!state.playbackCtx || !state.playbackGain) return;
  // User disabled auto-duck → never touch the gain from here.
  if (!state.autoDuckEnabled) return;
  if (speaking) {
    if (state.duckTimer) {
      clearTimeout(state.duckTimer);
      state.duckTimer = null;
    }
    if (!state.isDucked) {
      state.isDucked = true;
      applyAiGain(0.1);
      console.log(`[Audio] Ducking AI to ${Math.round(state.duckMultiplier * 100)}% of baseline (counterparty speech)`);
    }
    // Automatically restore baseline after 2 seconds of silence (no new speech)
    state.duckTimer = setTimeout(() => {
      state.duckTimer = null;
      if (state.isDucked) {
        state.isDucked = false;
        applyAiGain(0.3);
        console.log("[Audio] Restoring AI volume to baseline (counterparty silent)");
      }
    }, 2000);
  }
}

// Public setters — called from local overlay UI and from the full-window IIFE
// (via BroadcastChannel COMMAND_SET_AUDIO_MIX).
function setUserAiVolume(value01) {
  state.userAiVolume = Math.max(0, Math.min(2.0, Number(value01) || 0));
  applyAiGain(0.05);
}
function setAutoDuckEnabled(enabled) {
  state.autoDuckEnabled = !!enabled;
  // If we turn off mid-duck, restore baseline immediately.
  if (!state.autoDuckEnabled && state.isDucked) {
    if (state.duckTimer) { clearTimeout(state.duckTimer); state.duckTimer = null; }
    state.isDucked = false;
    applyAiGain(0.1);
  }
}

// ─── PCM capture worklet (runs on dedicated audio thread, drift-free) ────────
// Inline AudioWorkletProcessor source code. Loaded via Blob URL inside
// createPcmCapture(). Uses Bresenham integer-phase stepping to downsample from
// the native AudioContext sample rate (e.g. 48000 Hz) to 16000 Hz, then emits
// Int16LE PCM ArrayBuffers via this.port.postMessage with transferable
// ownership (zero-copy). Replaces the deprecated ScriptProcessorNode which
// runs on the main UI thread and is known to drift on long sessions.
const PCM_WORKLET_CODE = `
class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    // 'sampleRate' is a global inside AudioWorkletGlobalScope == ctx.sampleRate
    this._inRate = sampleRate;
    this._outRate = 16000;
    this._phase = 0;        // integer phase accumulator — no float drift
    this._buf = [];
    this._bufSize = 800;    // 50 ms at 16 kHz per posted chunk
  }

  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch || !ch.length) return true;
    for (let i = 0; i < ch.length; i++) {
      this._phase += this._outRate;
      if (this._phase >= this._inRate) {
        this._phase -= this._inRate;
        const s = Math.max(-1, Math.min(1, ch[i]));
        this._buf.push(s < 0 ? (s * 0x8000) | 0 : (s * 0x7fff) | 0);
      }
    }
    while (this._buf.length >= this._bufSize) {
      const ab = new Int16Array(this._buf.splice(0, this._bufSize)).buffer;
      this.port.postMessage(ab, [ab]);
    }
    return true;
  }
}
registerProcessor('pcm-capture-processor', PcmCaptureProcessor);
`;

// ─── PCM capture stream ───────────────────────────────────────────────────────
async function createPcmCapture(stream, msgType, options = {}) {
  const {
    flushMs = 240,
    silenceMs = 700,
    speechThreshold = 0.0015,
    minUtteranceMs = 500,
    minSpeechFrames = 2,
    maxUtteranceMs = 3500,
    forceActive = false,
    startOnForce = false,
    minAverageRms = 0,
    minPeakRms = 0,
    suppressCapture = null,
    deferFinalWhileForced = false,
    stopTracksOnStop = true,
    onSpeaking = null,
  } = options;
  // DO NOT force sampleRate:16000. Chromium's resampler from the native device
  // rate (48kHz on Windows) down to 16kHz outputs all-zero samples in some
  // Electron builds. Use the system native rate and downsample manually inside
  // the AudioWorklet (PCM_WORKLET_CODE) using Bresenham integer-phase stepping.
  const ctx = new AudioContext({ latencyHint: "interactive" });
  const NATIVE_RATE = ctx.sampleRate;            // 48000 on most Windows devices
  const TARGET_RATE = 16000;
  const src = ctx.createMediaStreamSource(stream);

  // Load the inline AudioWorkletProcessor via a Blob URL. No CSP set in
  // overlay.html so this is permitted by Chromium without any extra config.
  const _workletBlob = new Blob([PCM_WORKLET_CODE], { type: "application/javascript" });
  const _workletUrl = URL.createObjectURL(_workletBlob);
  try {
    await ctx.audioWorklet.addModule(_workletUrl);
  } finally {
    URL.revokeObjectURL(_workletUrl);
  }
  const node = new AudioWorkletNode(ctx, "pcm-capture-processor");
  const chunks = [];
  let startedAt = null;
  let utteranceId = null;
  let lastSpeechAt = 0;
  let active = false;
  let consecutiveSpeechFrames = 0;
  let rmsSum = 0;
  let rmsFrames = 0;
  let peakRms = 0;

  const resetCapture = () => {
    chunks.length = 0;
    startedAt = null;
    utteranceId = null;
    lastSpeechAt = 0;
    active = false;
    consecutiveSpeechFrames = 0;
    rmsSum = 0;
    rmsFrames = 0;
    peakRms = 0;
  };

  const rmsFor = (samples) => {
    if (!samples?.length) return 0;
    let sum = 0;
    for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
    return Math.sqrt(sum / samples.length);
  };

  const flush = (final = true) => {
    if (!chunks.length || !utteranceId || !startedAt) return;
    const durationMs = Date.now() - startedAt;
    const avgRms = rmsFrames ? rmsSum / rmsFrames : 0;
    const shouldDropForSilence = final && (
      durationMs < minUtteranceMs ||
      avgRms < minAverageRms ||
      peakRms < minPeakRms
    );
    if (shouldDropForSilence) {
      resetCapture();
      return;
    }
    const total = chunks.reduce((s, c) => s + c.byteLength, 0);
    const merged = new Uint8Array(total);
    let off = 0;
    for (const c of chunks.splice(0)) { merged.set(new Uint8Array(c), off); off += c.byteLength; }
    wsSend(msgType, {
      pcm_base64: toBase64(merged.buffer),
      timestamp_ms: Date.now(),
      started_at_ms: startedAt,
      utterance_id: utteranceId,
      is_final: final,
    });
    if (final) {
      resetCapture();
    }
  };

  // Diagnostic counter: log every 50th frame so you can confirm onaudioprocess fires
  // and see actual RMS vs threshold. Open DevTools on the overlay to view.
  let _diagFrameCount = 0;

  // RMS over an Int16 PCM chunk (worklet already downsampled + converted)
  const rmsForInt16 = (int16) => {
    if (!int16?.length) return 0;
    let sum = 0;
    for (let i = 0; i < int16.length; i++) {
      const s = int16[i] / 32768;
      sum += s * s;
    }
    return Math.sqrt(sum / int16.length);
  };

  node.port.onmessage = (ev) => {
    const buf = ev.data;             // ArrayBuffer of Int16 PCM at 16 kHz
    if (!(buf instanceof ArrayBuffer) || buf.byteLength === 0) return;
    const int16 = new Int16Array(buf);

    const now = Date.now();
    const rms = rmsForInt16(int16);
    const speaking = rms >= speechThreshold;
    if (onSpeaking) onSpeaking(speaking);
    const forced = typeof forceActive === "function" ? Boolean(forceActive()) : Boolean(forceActive);
    const suppressed = typeof suppressCapture === "function" ? Boolean(suppressCapture()) : Boolean(suppressCapture);

    if (suppressed) {
      if (active || chunks.length) resetCapture();
      return;
    }

    _diagFrameCount += 1;
    if (_diagFrameCount % 100 === 0) {
      console.log(`[PCM:${msgType}] ctx=${ctx.state} nativeRate=${NATIVE_RATE} worklet=on rms=${rms.toFixed(5)} threshold=${speechThreshold} speaking=${speaking} active=${active} frames=${_diagFrameCount}`);
    }

    if (speaking) {
      consecutiveSpeechFrames += 1;
    } else {
      consecutiveSpeechFrames = 0;
    }

    if (!active && forced && startOnForce) {
      active = true;
      startedAt = now;
      utteranceId = `${msgType}_${now}`;
      lastSpeechAt = now;
    } else if (!active && consecutiveSpeechFrames >= minSpeechFrames) {
      active = true;
      startedAt = now;
      utteranceId = `${msgType}_${now}`;
      lastSpeechAt = now;
    }
    if (!active) return;

    // Worklet has already downsampled to 16 kHz Int16LE — push the raw
    // ArrayBuffer directly. flush() merges chunks via Uint8Array view.
    chunks.push(buf);
    rmsSum += rms;
    rmsFrames += 1;
    if (rms > peakRms) peakRms = rms;
    if (speaking) {
      lastSpeechAt = now;
    } else if (lastSpeechAt && now - lastSpeechAt >= silenceMs) {
      if (forced && deferFinalWhileForced) return;
      flush(true);
      return;
    }
    if (!speaking && forced && startedAt && now - startedAt >= maxUtteranceMs) {
      if (deferFinalWhileForced) return;
      flush(true);
      return;
    }
    if (startedAt && now - startedAt >= maxUtteranceMs) {
      if (forced && deferFinalWhileForced) return;
      flush(true);
    }
  };

  // AudioWorkletNode does NOT need to connect to ctx.destination to keep
  // running — the source connection is enough to keep process() firing.
  src.connect(node);

  // Resume immediately, then watch for Chromium re-suspending the context
  // when the overlay window loses focus (common on Windows).
  await ctx.resume().catch(() => {});
  const ctxWatchdog = setInterval(() => {
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
  }, 500);

  const timer = setInterval(() => {
    if (!active) return;
    const now = Date.now();
    if (lastSpeechAt && now - lastSpeechAt >= silenceMs) {
      const forced = typeof forceActive === "function" ? Boolean(forceActive()) : Boolean(forceActive);
      if (forced && deferFinalWhileForced) return;
      flush(true);
      return;
    }
    flush(false);
  }, flushMs);

  return {
    flushFinal: () => {
      flush(true);
    },
    stop: async () => {
      clearInterval(timer);
      clearInterval(ctxWatchdog);
      flush(true);
      try { node.port.close(); } catch (_) {}
      try { node.disconnect(); } catch (_) {}
      try { src.disconnect(); } catch (_) {}
      if (stopTracksOnStop) stream.getTracks().forEach(t => t.stop());
      await ctx.close().catch(() => {});
    },
  };
}

// ─── Auto-detect audio devices ───────────────────────────────────────────────
function _isBadMic(label) {
  // Devices that deliver silence or are not real voice mics
  return /virtual|cable|iriun|droidcam|obs|voicemeeter|webcam|epoccam|ivcam|snap camera/i.test(label);
}

function isVirtualRouteDevice(label) {
  return /cable input|vb-audio|voicemeeter input/i.test(label || "");
}

function hasUnsafeDeviceLoopback() {
  if (state.vbCableDeviceId && state.listeningDeviceId && state.vbCableDeviceId === state.listeningDeviceId) {
    return true;
  }
  if (isVirtualRouteDevice(state.listeningDeviceLabel)) {
    return true;
  }
  if (state.vbCableLabel && state.listeningDeviceLabel) {
    return state.vbCableLabel.trim().toLowerCase() === state.listeningDeviceLabel.trim().toLowerCase();
  }
  return false;
}

async function autoSelectDevices() {
  let devices;
  try {
    // Trigger permission prompt first so enumerateDevices returns labels
    await navigator.mediaDevices.getUserMedia({ audio: true }).then(s => s.getTracks().forEach(t => t.stop()));
    devices = await navigator.mediaDevices.enumerateDevices();
  } catch (_) { return; }

  const outputs = devices.filter(d => d.kind === "audiooutput");
  const inputs  = devices.filter(d => d.kind === "audioinput");

  // VB-CABLE: find "CABLE Input" (the output sink to route mic to)
  const vbInput = outputs.find(d => isVirtualRouteDevice(d.label));
  if (vbInput) {
    state.vbCableDeviceId = vbInput.deviceId;
    state.vbCableLabel = vbInput.label || null;
    state.prefs.vbCableDeviceId = vbInput.deviceId;
  }

  // Listening output policy (rewritten 2026-05-25):
  // ALWAYS follow the OS system default output for AI voice. The user already
  // sets their system default in Windows (BT earbuds, wired headphones, etc.)
  // and that's the device they expect to hear AI through. Honoring a saved
  // localStorage pref was causing stale speaker IDs to win forever after one
  // accidental pick. deviceId="default" is a special sentinel that Chromium
  // resolves at play-time to whatever the OS default is — so if the user
  // unplugs earbuds mid-session, AI voice follows automatically.
  const nonVirtualOutputs = outputs.filter(d => !isVirtualRouteDevice(d.label));
  const defaultOutput = outputs.find(d => d.deviceId === "default" && !isVirtualRouteDevice(d.label));
  const listening = defaultOutput || nonVirtualOutputs[0] || outputs[0];
  // Purge any stale saved pref so we don't accidentally pin to a wrong device
  // again on next launch.
  if (state.prefs.listeningDeviceId && state.prefs.listeningDeviceId !== "default") {
    console.log("[AUDIO-OUT] Purging stale saved listeningDeviceId pref:", state.prefs.listeningDeviceId);
    state.prefs.listeningDeviceId = "default";
  }
  console.log("[AUDIO-OUT] Listening device selected:", listening?.label, "id=", listening?.deviceId, "(from", outputs.length, "outputs:", outputs.map(d => `${d.label}[${d.deviceId.slice(0,8)}]`).join(" | "), ")");
  if (listening) {
    state.listeningDeviceId = listening.deviceId;
    state.listeningDeviceLabel = listening.label || null;
    state.prefs.listeningDeviceId = listening.deviceId;
  }

  // Best physical microphone for speech capture.
  // Priority: headset/buds > Realtek/built-in > anything else that isn't virtual/webcam.
  // Explicitly skips virtual cables, Iriun Webcam, DroidCam, OBS virtual mic, etc.
  const realInputs = inputs.filter(d => d.deviceId !== "default" && d.deviceId !== "communications" && d.label && !_isBadMic(d.label));
  const headsetMic = realInputs.find(d => /headset|headphone|buds|earphone|airpod/i.test(d.label));
  const realtekMic = realInputs.find(d => /realtek|array|built.?in|internal/i.test(d.label));
  const bestMic    = headsetMic || realtekMic || realInputs[0];

  if (bestMic) {
    state.selectedMicDeviceId = bestMic.deviceId;
    state.selectedMicLabel = bestMic.label;
    state.prefs.selectedMicDeviceId = bestMic.deviceId;
    console.log('[MIC-SELECT] Auto-selected:', bestMic.label, '(skipped system default which was a virtual/webcam device)');
  } else {
    // Nothing better found — fall back to system default and warn
    state.selectedMicDeviceId = null;
    console.warn('[MIC-SELECT] No real physical mic found — using system default. Available inputs:', inputs.map(d => d.label).join(', '));
  }

  savePrefs();
  broadcastSnapshot();
}

// ─── Mic forward to VB-CABLE ──────────────────────────────────────────────────
async function setupMicForward(stream) {
  // Tear down old
  if (state.micForwardEl) {
    state.micForwardEl.pause();
    state.micForwardEl.srcObject = null;
    state.micForwardEl = null;
  }

  if (!state.vbCableDeviceId) {
    console.warn('[MicForward] No VB-CABLE device found — mic NOT forwarded to meeting');
    return;
  }

  if (typeof HTMLAudioElement.prototype.setSinkId !== "function") {
    console.warn('[MicForward] setSinkId not supported — mic NOT forwarded to prevent echo');
    return;
  }

  const el = document.createElement("audio");
  el.playsInline = true;
  el.srcObject = stream;

  // CRITICAL: setSinkId MUST succeed before we play.
  // If it fails (device not found, permission denied, etc.) we do NOT play —
  // playing without setSinkId routes to default speakers = user hears themselves.
  try {
    await el.setSinkId(state.vbCableDeviceId);
    console.log('[MicForward] Routing mic to VB-CABLE:', state.vbCableDeviceId.slice(0, 20));
  } catch (err) {
    console.error('[MicForward] setSinkId failed — mic NOT forwarded to prevent echo:', err.message);
    el.srcObject = null;
    return;  // ← no play, no echo
  }

  el.autoplay = true;
  try {
    await el.play();
  } catch (err) {
    console.error('[MicForward] play failed — mic NOT forwarded to meeting:', err?.message || err);
    el.srcObject = null;
    return;
  }
  state.micForwardEl = el;
}

// ─── Screen source picker ─────────────────────────────────────────────────────
// Shows a modal grid of screens + windows with 320×180 thumbnails.
// Returns a promise that resolves to the chosen desktop source ID, or null if cancelled.

let _pickerResolve = null;
let _pickerActiveTab = "screen";

async function showScreenPicker() {
  return new Promise((resolve) => {
    _pickerResolve = resolve;
    traceClientEvent("screen_picker_opened", "Overlay opened the screen picker", {
      active_tab: _pickerActiveTab,
    });

    const overlay = document.getElementById("screen-picker-overlay");
    const grid = document.getElementById("screen-picker-grid");
    if (!overlay || !grid) { resolve(null); return; }

    overlay.classList.remove("hidden");
    // Expand overlay window so picker is usable
    syncOverlayPresentation();
    grid.innerHTML = '<div style="color:#666;font-size:12px;padding:20px">Loading sources…</div>';

    const bridge = window.companionBridge;
    if (!bridge?.getScreenSources) { overlay.classList.add("hidden"); syncOverlayPresentation(); resolve(null); return; }

    bridge.getScreenSources().then((sources) => {
      renderPickerTab(sources, _pickerActiveTab);
    }).catch(() => { overlay.classList.add("hidden"); syncOverlayPresentation(); resolve(null); });

    // Tab switching
    overlay.querySelectorAll(".picker-tab").forEach(btn => {
      btn.onclick = () => {
        overlay.querySelectorAll(".picker-tab").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        _pickerActiveTab = btn.dataset.tab;
        bridge.getScreenSources().then(sources => renderPickerTab(sources, _pickerActiveTab));
      };
    });

    // Close button
    const closeBtn = document.getElementById("screen-picker-close");
    if (closeBtn) closeBtn.onclick = () => {
      traceClientEvent("screen_picker_cancelled", "User closed the screen picker without selecting a source", {});
      overlay.classList.add("hidden");
      syncOverlayPresentation();
      resolve(null);
    };

    // Also close on clicking the backdrop (outside the modal)
    overlay.onclick = (e) => {
      if (e.target === overlay) {
        traceClientEvent("screen_picker_cancelled", "User clicked backdrop to close screen picker", {});
        overlay.classList.add("hidden");
        syncOverlayPresentation();
        resolve(null);
      }
    };

    // Escape key to close
    const escHandler = (e) => {
      if (e.key === "Escape") {
        document.removeEventListener("keydown", escHandler);
        traceClientEvent("screen_picker_cancelled", "User pressed Escape to close screen picker", {});
        overlay.classList.add("hidden");
        syncOverlayPresentation();
        resolve(null);
      }
    };
    document.addEventListener("keydown", escHandler);

    function renderPickerTab(sources, tab) {
      const filtered = sources.filter(s => s.kind === tab);
      grid.innerHTML = "";
      if (!filtered.length) {
        grid.innerHTML = '<div style="color:#555;font-size:12px;padding:20px">No sources found.</div>';
        return;
      }
      filtered.forEach(src => {
        const card = document.createElement("div");
        card.className = "picker-source-card";
        const img = document.createElement("img");
        img.className = "picker-source-thumb";
        img.src = src.thumbnail;
        img.alt = src.name;
        const label = document.createElement("div");
        label.className = "picker-source-name";
        label.textContent = src.name;
        card.appendChild(img);
        card.appendChild(label);
        card.onclick = () => {
          traceClientEvent("screen_picker_source_selected", "User selected a screen source for meeting capture", {
            source_id: src.id,
            source_name: src.name,
            source_kind: src.kind,
          });
          overlay.classList.add("hidden");
          syncOverlayPresentation();
          if (_pickerResolve) { _pickerResolve(src.id); _pickerResolve = null; }
        };
        grid.appendChild(card);
      });
    }
  }).catch((err) => {
    console.error("[Playback] AI audio not played:", err?.message || err);
    reportCaptureHealth({ reply_output_ok: false });
  });
}

// ─── Meeting capture ──────────────────────────────────────────────────────────
async function stopMeetingCapture() {
  if (!state.meetingCapture) return;
  clearInterval(state.meetingCapture.frameTimer);
  await state.meetingCapture.audio.stop();
  state.meetingCapture.stream.getTracks().forEach(t => t.stop());
  state.meetingCapture = null;
  video.srcObject = null;
  // Hide preview
  if (capturePreview) { capturePreview.srcObject = null; capturePreview.classList.add("hidden"); }
}

async function teardownLocalSession({ resetSelection = false, closeSocket = false } = {}) {
  stopActivePlayback(false);
  if (state.askCapture) { await state.askCapture.stop().catch(() => {}); state.askCapture = null; }
  if (state.micCapture) { await state.micCapture.stop().catch(() => {}); state.micCapture = null; }
  await stopMeetingCapture().catch(() => {});
  if (state.micForwardEl) {
    try { state.micForwardEl.pause(); } catch (_) {}
    state.micForwardEl.srcObject = null;
    state.micForwardEl = null;
  }
  if (state.micStream) {
    state.micStream.getTracks().forEach(t => t.stop());
    state.micStream = null;
  }
  state.sessionLive = false;
  state.sessionStarting = false;
  state.sessionPaused = false;
  state.backendState = "IDLE";
  state._pendingStart = false;
  state.holdActive = false;
  state.holdSource = null;
  state.awaitingPrivateReply = false;
  state.copilotStarted = false;
  state.conversationEntries = [];
  state.privateEntries = [];
  state.chatEntries = [];
  state.langMenuOpen = false;
  state.menuOpen = false;
  if (resetSelection) {
    state.selectedTarget = null;
    state.selectedSourceId = null;
    state.prefs.lastMeetingTitle = null;
    savePrefs();
  }
  bridge.endCompanionSession().catch(() => {});
  if (closeSocket && state.ws) {
    try { state.ws.close(); } catch (_) {}
    state.ws = null;
  }
  setOrbState("idle");
  updateRootClasses();
  syncOverlayPresentation();
  renderChat();
  broadcastSnapshot();
}

async function startMeetingCapture(sourceId) {
  await stopMeetingCapture();
  const effectiveSourceId = resolvePreferredCaptureSourceId(sourceId);
  if (effectiveSourceId) {
    await syncDesktopCaptureSelection(effectiveSourceId).catch((err) => {
      console.warn("[MeetingCapture] Failed to sync selected desktop source:", err?.message || err);
    });
  }
  traceClientEvent("meeting_capture_requested", "Overlay started meeting capture setup", {
    source_id: effectiveSourceId,
    selected_target: state.selectedTarget?.window_title || null,
  });

  let stream;
  try {
    stream = await navigator.mediaDevices.getDisplayMedia({
      video: { frameRate: { ideal: 4, max: 6 } },
      audio: true,
    });
  } catch (displayErr) {
    traceClientEvent("meeting_capture_primary_failed", "Primary display-media capture failed", {
      source_id: effectiveSourceId,
      error: displayErr?.message || String(displayErr),
    });
    if (!effectiveSourceId) {
      throw displayErr;
    }
    stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        mandatory: {
          chromeMediaSource: "desktop",
          chromeMediaSourceId: effectiveSourceId,
          maxFrameRate: 6,
        },
      },
    });
  }

  // Feed only the video tracks into the video element — audio must NOT play through
  // speakers/earphones or the user hears the meeting audio (including their own echoed voice).
  // Audio is handled separately by createPcmCapture below.
  const videoTracks = stream.getVideoTracks();
  video.srcObject = new MediaStream(videoTracks);
  video.muted = true;
  await video.play().catch(() => {});

  // Small preview in the overlay (below the orb) — same tracks, no audio
  if (capturePreview && videoTracks.length) {
    capturePreview.srcObject = new MediaStream(videoTracks);
    capturePreview.muted = true;
    capturePreview.classList.remove("hidden");
  }

  const hasAudio = stream.getAudioTracks().length > 0;
  const remoteAudioCapture = hasAudio
    ? await createPcmCapture(stream, "REMOTE_APP_PCM", {
        flushMs: 120,
        silenceMs: 1500,
        speechThreshold: 0.0003,
        minUtteranceMs: 100,
        minSpeechFrames: 1,
      minAverageRms: 0.0,
      minPeakRms: 0.0,
      maxUtteranceMs: 12000,
      suppressCapture: () => state.sessionPaused,
    })
    : { stop: async () => {} };

  let lastPixelHash = null;
  let identicalFrameCount = 0;

  const frameTimer = setInterval(() => {
    // Only send frames once the backend is in ACTIVE state.
    // Sending before ACTIVE triggers rejected-message warnings in the backend.
    if (state.sessionPaused || state.backendState !== "ACTIVE") return;
    if (video.paused) {
      console.warn("[MeetingCapture] Video element is paused. Resuming playback...");
      video.play().catch(() => {});
    }
    if (!video.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width  = Math.min(1280, video.videoWidth);
    canvas.height = Math.min(720, video.videoHeight);
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    // Pixel-level freeze detection (checks 5 sample coordinates)
    const samplePoints = [
      { x: Math.floor(canvas.width / 4), y: Math.floor(canvas.height / 4) },
      { x: Math.floor(canvas.width / 2), y: Math.floor(canvas.height / 2) },
      { x: Math.floor(canvas.width * 3 / 4), y: Math.floor(canvas.height * 3 / 4) },
      { x: 15, y: 15 },
      { x: canvas.width - 15, y: canvas.height - 15 }
    ];
    let hash = "";
    try {
      for (const pt of samplePoints) {
        const pix = ctx.getImageData(pt.x, pt.y, 1, 1).data;
        hash += `${pix[0]},${pix[1]},${pix[2]}|`;
      }
    } catch (_) {}

    if (hash && hash === lastPixelHash) {
      identicalFrameCount++;
      // If exactly identical for ~120 seconds (150 consecutive frames of 800ms) to avoid false hot-reloads on static screens
      if (identicalFrameCount >= 150 && state.selectedSourceId) {
        console.warn("[MeetingCapture] Pixel freeze detected (150 consecutive identical frames). Silently hot-reloading capture stream...");
        identicalFrameCount = 0;
        lastPixelHash = null;
        
        // Trigger silent restart using the current sourceId asynchronously
        const activeSourceId = state.selectedSourceId;
        setTimeout(async () => {
          try {
            console.log("[MeetingCapture] Starting silent hot-reload for source:", activeSourceId);
            await startMeetingCapture(activeSourceId);
          } catch (err) {
            console.error("[MeetingCapture] Silent hot-reload failed:", err);
          }
        }, 10);
        return;
      }
    } else {
      identicalFrameCount = 0;
      if (hash) {
        lastPixelHash = hash;
      }
    }

    wsSend("SCREEN_FRAME", {
      image: canvas.toDataURL("image/jpeg", 0.82).split(",")[1],
      timestamp: Date.now(),
      source_mode: "virtual_companion_desktop",
      source: "meeting_window",
    });
  }, 800);

  state.meetingCapture = {
    stream,
    hasAudio,
    audio: remoteAudioCapture,
    frameTimer,
  };
  traceClientEvent("meeting_capture_started", "Meeting capture started successfully", {
    source_id: effectiveSourceId,
    has_audio: hasAudio,
    video_track_label: stream.getVideoTracks()[0]?.label || null,
    audio_track_count: stream.getAudioTracks().length,
  });

  // WGC auto-recovery: when the video track mutes (swap-chain invalidated by window
  // compositor change), silently retry capture with the same source. Only show the
  // picker as a last resort after multiple retries fail.
  const vtrack = stream.getVideoTracks()[0];
  if (vtrack) {
    vtrack.addEventListener("ended", async () => {
      traceClientEvent("meeting_capture_ended", "Meeting capture video track ended", {
        source_id: state.selectedSourceId || effectiveSourceId || null,
      });
      // Track ended permanently — try to silently restart with same source
      const activeSourceId = state.selectedSourceId || effectiveSourceId;
      if (activeSourceId && state.sessionLive) {
        console.warn("[MeetingCapture] Video track ended. Attempting silent restart with same source...");
        try {
          await startMeetingCapture(activeSourceId);
          const newTrack = state.meetingCapture?.stream?.getVideoTracks()[0];
          if (newTrack && newTrack.readyState === "live") {
            console.log("[MeetingCapture] Silent restart after track-ended succeeded.");
            return;
          }
        } catch (err) {
          console.warn("[MeetingCapture] Silent restart after track-ended failed:", err?.message);
        }
      }
      // Fallback: stop capture and notify, but do NOT show picker automatically
      await stopMeetingCapture();
      wsSend("CAPTURE_HEALTH", { remote_audio_ok: false, frame_capture_ok: false,
        unsafe_device_loopback: false, degraded_reasons: ["meeting_capture_ended"] });
      broadcastSnapshot();
    });
    vtrack.onmute = async () => {
      traceClientEvent("meeting_capture_muted", "Meeting capture video track muted — attempting recovery", {
        source_id: state.selectedSourceId || effectiveSourceId || null,
      });
      console.warn("[MeetingCapture] Video track muted — WGC compositor invalidated. Attempting silent hot-reload...");
      
      const activeSourceId = state.selectedSourceId || effectiveSourceId;
      if (activeSourceId) {
        // Retry up to 3 times with increasing delays
        for (let attempt = 1; attempt <= 3; attempt++) {
          try {
            await new Promise(resolve => setTimeout(resolve, attempt * 1000));
            await startMeetingCapture(activeSourceId);
            const newVtrack = state.meetingCapture?.stream?.getVideoTracks()[0];
            if (newVtrack && !newVtrack.muted && newVtrack.readyState === "live") {
              console.log(`[MeetingCapture] Silent hot-reload succeeded on attempt ${attempt}.`);
              return;
            }
          } catch (err) {
            console.warn(`[MeetingCapture] Hot-reload attempt ${attempt} failed:`, err?.message);
          }
        }
      }

      // All retries failed — stop capture and notify user via CAPTURE_HEALTH,
      // but do NOT pop the screen picker overlay during a live session.
      // The user can re-select from the full window meeting picker instead.
      console.warn("[MeetingCapture] All hot-reload attempts failed. Capture stopped. User can re-select from the main window.");
      await stopMeetingCapture();
      wsSend("CAPTURE_HEALTH", { remote_audio_ok: false, frame_capture_ok: false,
        unsafe_device_loopback: false, degraded_reasons: ["wgc_track_muted_unrecoverable"] });
      broadcastSnapshot();
    };
  }

  reportCaptureHealth({ remote_audio_ok: hasAudio, frame_capture_ok: true });
}

// ─── Capture health ───────────────────────────────────────────────────────────
function reportCaptureHealth(overrides = {}) {
  const hasVb = Boolean(state.vbCableDeviceId && state.micForwardEl);
  const unsafeLoopback = hasUnsafeDeviceLoopback();
  const degradedReasons = [];
  if (!hasVb) degradedReasons.push("vbcable_not_detected");
  if (unsafeLoopback) degradedReasons.push("unsafe_device_loopback");
  const health = {
    mic_forward_ok: Boolean(state.micForwardEl),
    remote_audio_ok: Boolean(state.meetingCapture?.hasAudio),
    frame_capture_ok: Boolean(state.meetingCapture),
    reply_output_ok: Boolean(state.listeningDeviceId) && !unsafeLoopback,
    helper_active: hasVb,
    process_loopback_ok: Boolean(state.meetingCapture?.hasAudio),
    unsafe_device_loopback: unsafeLoopback,
    degraded_reasons: degradedReasons,
    ...overrides,
  };
  bridge.setCaptureHealth(health).catch(() => {});
  wsSend("CAPTURE_HEALTH", health);
}

// ─── Session start ────────────────────────────────────────────────────────────
function sendStartNegotiation() {
  // Mark session as optimistically live so hold-to-ask works immediately.
  // The definitive SESSION_STARTED will follow once Gemini connects (~20s).
  state.sessionStarting = true;
  traceClientEvent("start_negotiation_sent", "Overlay sent START_NEGOTIATION", {
    meeting_title: state.selectedTarget?.window_title || null,
    source_mode: "virtual_companion_desktop",
  });
  wsSend("START_NEGOTIATION", {
    context: "Desktop companion virtual meeting session",
    source_mode: "virtual_companion_desktop",
    capture_preset: "meeting_window_default",
    companion_quality_mode: "companion_ready",
    meeting_binding: {
      target_id: state.selectedTarget?.target_id,
      window_title: state.selectedTarget?.window_title,
      process_name: state.selectedTarget?.process_name || null,
      platform_hint: state.selectedTarget?.platform_hint || "generic",
      output_device_id: state.vbCableDeviceId,
      output_device_label: state.vbCableLabel,
      is_bound: true,
    },
    selected_output_device: { device_id: state.listeningDeviceId, label: state.listeningDeviceLabel },
  });
}

async function startSession() {
  if (state.sessionLive || state.sessionStarting) return;
  if (!state.selectedTarget) throw new Error("No meeting target selected");

  state.sessionStarting = true;
  state.sessionPaused = false;
  state.conversationEntries = [];
  state.privateEntries = [];
  state.chatEntries = [];
  traceClientEvent("session_start_requested", "Overlay began session startup", {
    meeting_title: state.selectedTarget?.window_title || null,
    source_id: resolvePreferredCaptureSourceId(state.selectedSourceId || null),
  });
  setOrbState("active");
  broadcastSnapshot();

  try {
    await connectBackend();
    await autoSelectDevices();

    // Bind meeting target in the main process (sets selectedDesktopSourceId so
    // setDisplayMediaRequestHandler can serve the source for getDisplayMedia).
    // Do NOT send MEETING_BINDING via WS yet — backend is still IDLE here.
    // That message is included in the START_NEGOTIATION payload instead.
    await bridge.startCompanionSession();
    const chosenSourceId = resolvePreferredCaptureSourceId(state.selectedSourceId || null);
    await bridge.bindMeetingTarget({
      ...state.selectedTarget,
      source_id: chosenSourceId,
    });

    // Start screen + audio capture using the source already selected in the main window.
    // state.selectedSourceId is set when user clicks a window in the full.js meeting list
    // and sends COMMAND_SELECT_MEETING with { target, source_id }.
    // If not set, startMeetingCapture falls back to the OS native picker.
    await startMeetingCapture(chosenSourceId).catch((captureErr) => {
      console.warn("Meeting capture failed (non-fatal):", captureErr?.message || captureErr);
    });

    if (state.askCapture) await state.askCapture.stop();
    if (state.micCapture) await state.micCapture.stop();
    if (state.micStream) {
      state.micStream.getTracks().forEach(t => t.stop());
      state.micStream = null;
    }

    // Capture physical mic — use the best mic auto-selected in autoSelectDevices,
    // NOT the system default (which may be a virtual/webcam device delivering silence).
    const micAudioConstraints = {
      channelCount: 1,
      sampleRate: { ideal: 48000 },
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    };
    if (state.selectedMicDeviceId) {
      micAudioConstraints.deviceId = { exact: state.selectedMicDeviceId };
    }
    const micStream = await navigator.mediaDevices.getUserMedia({ audio: micAudioConstraints });
    state.micStream = micStream;

    // Log which device was actually captured
    const micTrack = micStream.getAudioTracks()[0];
    const micSettings = micTrack ? micTrack.getSettings() : {};
    state.selectedMicLabel = micTrack?.label || null;
    console.log('[MIC] Using:', micTrack?.label, '| muted:', micTrack?.muted, '| sampleRate:', micSettings.sampleRate);
    if (micTrack?.muted) {
      console.error('[MIC] TRACK IS MUTED — this mic is delivering silence. Check Windows audio settings.');
    }

    // Forward mic to VB-CABLE (meeting app hears us through this)
    await setupMicForward(micStream);
    reportCaptureHealth();

    // Public transcript capture → LOCAL_MIC_PCM.
    // Thresholds tuned so keyboard clicks, fan noise, and brief ambient sounds
    // do NOT trigger capture. Only sustained speech (~500ms+) will activate.
    // Keyboard click: instantaneous spike ~0.002-0.005 RMS for <50ms.
    // Normal speech: sustained 0.01-0.05+ RMS for hundreds of ms.
    state.micCapture = await createPcmCapture(micStream, "LOCAL_MIC_PCM", {
      flushMs: 120,
      silenceMs: 1500,
      speechThreshold: 0.0003,
      minUtteranceMs: 100,
      minSpeechFrames: 1,
      minAverageRms: 0.0,
      minPeakRms: 0.0,
      maxUtteranceMs: 12000,
      suppressCapture: () => state.sessionPaused || state.holdActive,
      stopTracksOnStop: false,
    });

    // Private ask capture → ASK_AI_PCM. This lane is active only while holding the orb.
    state.askCapture = await createPcmCapture(micStream, "ASK_AI_PCM", {
      flushMs: 120,
      silenceMs: 1000,
      speechThreshold: 0.0007,
      minUtteranceMs: 700,
      minSpeechFrames: 2,
      minAverageRms: 0.00025,
      minPeakRms: 0.0007,
      maxUtteranceMs: 15000,
      forceActive: () => state.holdActive && !state.sessionPaused,
      startOnForce: true,
      deferFinalWhileForced: true,
      suppressCapture: () => state.sessionPaused || !state.holdActive,
      stopTracksOnStop: false,
    });

    // CAPTURE_HEALTH and MEETING_BINDING WS messages are sent in the SESSION_STARTED
    // handler after the backend is in ACTIVE state.

    // Drive the consent → start flow based on current backend state.
    if (state.backendState === "CONSENTED") {
      // Already consented (from a previous attempt), go straight to START
      sendStartNegotiation();
    } else {
      // IDLE or unknown — send consent and wait for CONSENT_ACKNOWLEDGED
      state._pendingStart = true;
      traceClientEvent("privacy_consent_sent", "Overlay sent privacy consent before starting session", {
        version: "1.0",
        mode: "live",
      });
      wsSend("PRIVACY_CONSENT_GRANTED", { version: "1.0", mode: "live" });
    }

  } catch (err) {
    state.sessionStarting = false;
    state.sessionLive = false;
    state.sessionPaused = false;
    traceClientEvent("session_start_failed", "Overlay session startup failed", {
      error: err?.message || String(err),
    });
    setOrbState("idle");
    broadcastSnapshot();   // Tell full window the start failed so UI resets
    console.error("[startSession] failed:", err?.message || err);
    throw err;
  }
}

// ─── Meeting target selection ─────────────────────────────────────────────────
function pauseSession() {
  if (!state.sessionLive || state.sessionPaused) return;
  state.sessionPaused = true;
  state.sessionStarting = false;
  state.backendState = "PAUSED";
  state.holdActive = false;
  state.holdSource = null;
  state.awaitingPrivateReply = false;
  stopActivePlayback(true);
  if (state.micForwardEl) state.micForwardEl.muted = false;
  traceClientEvent("session_pause_requested", "Overlay requested desktop session pause", {});
  wsSend("PAUSE_NEGOTIATION", {});
  bridge.setHoldToAsk({ active: false, muted_to_meeting: false }).catch(() => {});
  setOrbState("paused");
  updateRootClasses();
  syncOverlayPresentation();
  reportCaptureHealth();
  broadcastSnapshot();
}

function resumeSession() {
  if (!state.sessionPaused) return;
  state.sessionPaused = false;
  state.backendState = "ACTIVE";
  traceClientEvent("session_resume_requested", "Overlay requested desktop session resume", {});
  wsSend("RESUME_NEGOTIATION", {});
  setOrbState("active");
  updateRootClasses();
  syncOverlayPresentation();
  reportCaptureHealth();
  broadcastSnapshot();
}

function endSession() {
  if (state.ws?.readyState === WebSocket.OPEN && (state.sessionLive || state.sessionStarting || state.sessionPaused)) {
    wsSend("END_NEGOTIATION", {});
    setTimeout(() => {
      if (state.sessionLive || state.sessionStarting || state.sessionPaused) {
        void teardownLocalSession({ resetSelection: true, closeSocket: true });
      }
    }, 1800);
    return;
  }
  void teardownLocalSession({ resetSelection: true, closeSocket: true });
}

async function selectTarget(target, { autoStart = false } = {}) {
  state.selectedTarget = target;
  state.prefs.lastMeetingTitle = target.window_title;
  savePrefs();
  traceClientEvent("meeting_target_selected", "User selected a meeting target from the overlay", {
    target_id: target.target_id,
    window_title: target.window_title,
    platform_hint: target.platform_hint,
    source_id: state.selectedSourceId || null,
    auto_start: autoStart,
  });
  closeMenu();
  // Only auto-start if explicitly requested (e.g. from remembered last meeting on boot).
  // Normal selection from the menu or full window just selects — user must click Start.
  if (autoStart) {
    await startSession().catch(console.error);
  }
  broadcastSnapshot();
}

// ─── Meeting menu ─────────────────────────────────────────────────────────────
function closeMenu() {
  menu.classList.add("hidden");
  state.menuOpen = false;
  syncOverlayPresentation();
}

function _findSourceForTarget(t) {
  if (!state.screenSources || !state.screenSources.length) return null;
  const title = (t.window_title || "").toLowerCase();
  return (
    state.screenSources.find(s => s.name.toLowerCase() === title) ||
    state.screenSources.find(s =>
      title.includes(s.name.toLowerCase()) || s.name.toLowerCase().includes(title)
    ) || null
  );
}

function renderMenu() {
  menu.innerHTML = '<div class="menu-header">Select meeting window</div>';
  if (!state.meetingTargets.length) {
    const e = document.createElement("div");
    e.className = "menu-header";
    e.style.opacity = "0.5";
    e.textContent = "No meeting window found";
    menu.appendChild(e);
    return;
  }
  for (const t of state.meetingTargets) {
    const src = _findSourceForTarget(t);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "meeting-option" + (state.selectedTarget?.target_id === t.target_id ? " active" : "");

    // Thumbnail if available
    if (src?.thumbnail) {
      const img = document.createElement("img");
      img.src = src.thumbnail;
      img.className = "menu-thumb";
      img.alt = t.window_title;
      btn.appendChild(img);
    }

    const info = document.createElement("div");
    info.className = "menu-option-info";

    const label = document.createElement("span");
    label.textContent = t.window_title;
    const badge = document.createElement("span");
    badge.className = "platform-badge";
    badge.textContent = t.platform_hint;

    info.appendChild(label);
    info.appendChild(badge);
    btn.appendChild(info);

    btn.addEventListener("click", () => {
      state.selectedSourceId = src?.id || t.target_id || null;
      void selectTarget(t);
    });
    menu.appendChild(btn);
  }
}

async function openMenu() {
  // Load meeting targets AND thumbnails in parallel
  const [targets, sources] = await Promise.all([
    bridge.listMeetingTargets().catch(() => []),
    bridge.getScreenSources ? bridge.getScreenSources().catch(() => []) : Promise.resolve([]),
  ]);
  if (targets.length) state.meetingTargets = targets;
  if (sources.length) state.screenSources = sources;
  document.getElementById("lang-menu")?.classList.add("hidden");
  state.langMenuOpen = false;
  renderMenu();
  menu.classList.remove("hidden");
  state.menuOpen = true;
  syncOverlayPresentation();
  refreshContrast();
}

function toggleMenu() {
  if (state.menuOpen) closeMenu();
  else void openMenu();
}

// ─── Hold-to-Ask ─────────────────────────────────────────────────────────────
async function setHold(active, source = "orb") {
  // Allow hold once the WS is connected and the session is at least starting.
  // Do NOT require sessionLive — SESSION_STARTED can arrive late (~23s after
  // START_NEGOTIATION), and the user should be able to ask AI immediately.
  const wsOpen = state.ws && state.ws.readyState === WebSocket.OPEN;
  if (state.sessionPaused) return;
  if (!wsOpen || (!state.sessionLive && !state.sessionStarting)) return;
  if (state.holdActive === active) return;

  if (!active && state.askCapture?.flushFinal) {
    state.askCapture.flushFinal();
  }
  state.holdActive = active;
  traceClientEvent(
    active ? "hold_started" : "hold_released",
    active ? "Overlay activated hold-to-ask" : "Overlay released hold-to-ask",
    { source }
  );

  // Update mic forward mute state (state-driven)
  updateMicMuteState();

  if (active) {
    state.ignoreIncomingAiUntil = Date.now() + 1200;
    if (state.activePlaybackSources && state.activePlaybackSources.length > 0) {
      console.log(`[Audio] Aborting ${state.activePlaybackSources.length} active AI audio sources`);
      state.activePlaybackSources.forEach(src => {
        try { src.stop(); } catch (_) {}
      });
      state.activePlaybackSources = [];
    }
    state.playbackNextAt = 0;
    if (state._playbackDoneTimer) {
      clearTimeout(state._playbackDoneTimer);
      state._playbackDoneTimer = null;
    }
    state.awaitingPrivateReply = true;
    setOrbState("listening");
  } else {
    setOrbState(state.awaitingPrivateReply ? "processing" : "active");
  }

  updateRootClasses();
  renderChat();
  bridge.setHoldToAsk({ active, muted_to_meeting: active }).catch(() => {});
  wsSend("HOLD_TO_ASK_STATE", { active, muted_to_meeting: active, source });
  syncOverlayPresentation();
  reportCaptureHealth();
  refreshContrast();
  broadcastSnapshot();
}

// ─── Mouse-hold ring animation ────────────────────────────────────────────────
// The PS script fires mouse_hold_start after 3s — we just animate the ring
// during those 3s to give visual feedback.
// We track mousedown/mouseup on the document to drive the ring.

function startRingFill() {
  if (state.ringStarted) return;
  state.ringStarted = true;
  ringPath.style.transition = "stroke-dashoffset 3s linear";
  ringPath.style.strokeDashoffset = "0";
}

function stopRingFill() {
  state.ringStarted = false;
  ringPath.style.transition = "stroke-dashoffset 0.15s ease";
  ringPath.style.strokeDashoffset = "188";
}


// ─── Global hold events from main process (PS script) ────────────────────────

bridge.onOverlayPresentation(() => void refreshContrast());

// ─── Orb pointer events (drag + hold) ────────────────────────────────────────
orb.addEventListener("pointerdown", (e) => {
  state.dragging = true;
  state.dragPointerId = e.pointerId;
  state.dragOffX = e.clientX;
  state.dragOffY = e.clientY;
  state.dragMoved = false;
  orb.setPointerCapture(e.pointerId);
});

window.addEventListener("pointermove", (e) => {
  if (!state.dragging || e.pointerId !== state.dragPointerId) return;
  const dx = Math.abs(e.movementX || 0), dy = Math.abs(e.movementY || 0);
  if (dx > 2 || dy > 2) state.dragMoved = true;
  if (!state.dragMoved) return;
  bridge.moveOverlayWindow({ x: e.screenX - state.dragOffX, y: e.screenY - state.dragOffY }).catch(() => {});
});

window.addEventListener("pointerup", (e) => {
  if (state.dragging && e.pointerId === state.dragPointerId) {
    state.dragging = false;
    state.dragPointerId = null;
    if (state.holdActive && state.holdSource === "orb") {
      void setHold(false, "orb");
      state.holdSource = null;
    }
  }
});

orb.addEventListener("click", (e) => {
  if (state.dragMoved) { state.dragMoved = false; e.preventDefault(); return; }
  if (state.sessionLive) return;
  toggleMenu();
});

orb.addEventListener("dblclick", (e) => {
  e.preventDefault();
  bridge.openFullWindow().catch(() => {});
});

orb.addEventListener("contextmenu", (e) => {
  e.preventDefault();
  bridge.openFullWindow().catch(() => {});
});

// Orb hold for Hold-to-Ask when session is live
let orbHoldTimer = null;
orb.addEventListener("pointerdown", () => {
  if (state.sessionPaused) return;
  if (!state.sessionLive && !state.sessionStarting) return;
  startRingFill();
  orbHoldTimer = setTimeout(() => {
    if (!state.dragMoved) {
      state.holdSource = "orb";
      void setHold(true, "orb");
    }
  }, 150);
});
window.addEventListener("pointerup", () => {
  clearTimeout(orbHoldTimer);
  stopRingFill();
});

// Close menu when clicking outside
document.addEventListener("click", (e) => {
  if (state.menuOpen && !e.target.closest(".orb-wrap")) closeMenu();
});

// ─── BroadcastChannel (commands from full window) ────────────────────────────
channel.onmessage = (ev) => {
  const { type, payload } = ev.data || {};
  if (type === "REQUEST_STATE") broadcastSnapshot();
  if (type === "COMMAND_START_SESSION") void startSession().catch(console.error);
  if (type === "COMMAND_PAUSE_SESSION") pauseSession();
  if (type === "COMMAND_RESUME_SESSION") resumeSession();
  if (type === "COMMAND_SELECT_MEETING" && payload?.target) {
    void selectTarget(payload.target, { autoStart: false });
    // Store the desktop source_id so startMeetingCapture uses the same source the user picked
    state.selectedSourceId = payload.source_id || payload.target?.target_id || null;
    // If session is already live, restart capture immediately with the new source —
    // no button needed; clicking in the main window switches the captured screen right away
    if (state.sessionLive && !state.sessionPaused) {
      syncDesktopCaptureSelection(state.selectedSourceId).catch(e =>
        console.warn("[Overlay] Live source sync failed:", e?.message)
      );
      startMeetingCapture(state.selectedSourceId).catch(e =>
        console.warn("[Overlay] Live capture switch failed:", e?.message)
      );
    }
  }
  if (type === "COMMAND_END_SESSION") {
    endSession();
  }
  // Forward language change from the full window straight to the backend.
  // Reversible: deleting this branch + the COMMAND_SET_LANGUAGE sender in
  // full.js rolls back the cross-window plumbing without affecting anything else.
  if (type === "COMMAND_SET_LANGUAGE" && payload) {
    wsSend("SET_LANGUAGE_PROFILE", payload);
  }
  // Audio-mix command from the full window. Adjusts user baseline volume and
  // the auto-duck toggle in-process; broadcasts back so both UIs stay in sync.
  if (type === "COMMAND_SET_AUDIO_MIX" && payload) {
    if (typeof payload.aiVolume === "number") setUserAiVolume(payload.aiVolume);
    if (typeof payload.autoDuck === "boolean") setAutoDuckEnabled(payload.autoDuck);
    // Echo to keep overlay's own strip in sync if user changed via full window
    try {
      channel.postMessage({
        type: "AUDIO_MIX_STATE",
        payload: { aiVolume: state.userAiVolume, autoDuck: state.autoDuckEnabled },
      });
    } catch (_) {}
    syncOverlayMixUI();
  }
};

// ─── Boot ─────────────────────────────────────────────────────────────────────
window.addEventListener("load", async () => {
  loadPrefs();
  renderChat();
  updateRootClasses();

  // Pre-connect WS
  await connectBackend().catch(() => {});

  // Load targets and maybe auto-attach to last meeting
  state.meetingTargets = await bridge.listMeetingTargets();
  renderMenu();

  if (state.prefs.lastMeetingTitle) {
    const remembered = state.meetingTargets.find(t => t.window_title === state.prefs.lastMeetingTitle);
    if (remembered) {
      state.selectedTarget = remembered;
      // Only pre-select the target — do NOT auto-start the session.
      // The user must explicitly click Start to begin.
      broadcastSnapshot();
    }
  }

  await autoSelectDevices();
  await refreshContrast();
  broadcastSnapshot();
});

// ─── Audio mix UI (reversible block) ──────────────────────────────────────────
// Compact slider + duck toggle near the orb. Mirrors the main-window card via
// BroadcastChannel — either surface can change values; the other reflects.
// Hoisted so the COMMAND_SET_AUDIO_MIX handler above can call it.
function syncOverlayMixUI() {
  const slider = document.getElementById("mix-volume");
  const label  = document.getElementById("mix-volume-label");
  const duck   = document.getElementById("mix-duck");
  if (!slider || !label || !duck) return;
  const pct = Math.round((state.userAiVolume || 0) * 100);
  slider.value = String(pct);
  label.textContent = `${pct}%`;
  slider.style.setProperty("--mix-pct", `${Math.min(100, pct / 2)}%`);
  duck.classList.toggle("on", !!state.autoDuckEnabled);
  duck.classList.toggle("off", !state.autoDuckEnabled);
  duck.title = state.autoDuckEnabled
    ? "Auto-duck ON — AI drops to 80% while counterparty speaks. Click to disable."
    : "Auto-duck OFF — AI volume stays at your slider value. Click to enable.";
}
(function setupAudioMixUI() {
  const mixStrip = document.getElementById("mix-strip");
  const mixIconBtn = document.getElementById("mix-icon-btn");
  const slider = document.getElementById("mix-volume");
  const duck   = document.getElementById("mix-duck");
  if (!slider || !duck) return;

  // Toggle vertical volume strip expansion on icon click
  if (mixStrip && mixIconBtn) {
    mixIconBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      mixStrip.classList.toggle("expanded");
    });
    // Click outside to automatically collapse
    document.addEventListener("click", (e) => {
      if (!mixStrip.contains(e.target)) {
        mixStrip.classList.remove("expanded");
      }
    });
  }

  // Initialise UI to current state.
  syncOverlayMixUI();
  slider.addEventListener("input", () => {
    const pct = Math.max(0, Math.min(200, Number(slider.value) || 0));
    setUserAiVolume(pct / 100);
    syncOverlayMixUI();
    try {
      channel.postMessage({
        type: "AUDIO_MIX_STATE",
        payload: { aiVolume: state.userAiVolume, autoDuck: state.autoDuckEnabled },
      });
    } catch (_) {}
  });
  duck.addEventListener("click", () => {
    setAutoDuckEnabled(!state.autoDuckEnabled);
    syncOverlayMixUI();
    try {
      channel.postMessage({
        type: "AUDIO_MIX_STATE",
        payload: { aiVolume: state.userAiVolume, autoDuck: state.autoDuckEnabled },
      });
    } catch (_) {}
  });
})();

// ─── Multilanguage adaptation UI (reversible block) ───────────────────────────
// Self-contained: deleting this IIFE + the matching HTML/CSS rolls the feature
// back without touching anything else. The handlers also no-op when the
// backend reports MULTILANG_ENABLED=false in its LANGUAGE_UPDATE reply.
(function setupLanguageUI() {
  const chip   = document.getElementById("lang-chip");
  const label  = document.getElementById("lang-chip-label");
  const menu   = document.getElementById("lang-menu");
  const spoken = document.getElementById("lang-spoken");
  const reply  = document.getElementById("lang-reply");
  const display= document.getElementById("lang-display");
  const apply  = document.getElementById("lang-apply");
  const status = document.getElementById("lang-status");
  if (!chip || !menu || !apply) return;

  // Make the chip visible immediately so the user can discover it.
  // The Apply call itself decides whether the backend honors it.
  chip.classList.add("visible");

  const pickerSync = new Map();
  let openPicker = null;

  function closeOpenPicker() {
    if (!openPicker) return;
    openPicker.wrap.classList.remove("open");
    openPicker.menu.classList.add("hidden");
    openPicker = null;
  }

  function syncPickerValue(select) {
    const sync = pickerSync.get(select);
    if (typeof sync === "function") sync();
  }

  function setSelectValue(select, value) {
    if (!select) return;
    const resolved = Array.from(select.options).some((option) => option.value === value) ? value : "";
    select.value = resolved;
    syncPickerValue(select);
  }

  function applyLanguageState(payload = {}) {
    const profile = payload.language_profile || "auto_multi";
    const responseLanguage = payload.response_language || "";
    const displayLanguage = payload.display_language || "";
    setSelectValue(spoken, profile);
    setSelectValue(reply, responseLanguage);
    setSelectValue(display, displayLanguage);
    label.textContent = chipTextFor(profile, payload.language || responseLanguage);
  }

  function enhanceSelect(select) {
    if (!select || select.dataset.customized === "true") return;
    const wrap = document.createElement("div");
    wrap.className = "lang-picker";
    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "lang-picker-trigger";
    trigger.setAttribute("aria-haspopup", "listbox");
    const value = document.createElement("span");
    value.className = "lang-picker-value";
    const menuEl = document.createElement("div");
    menuEl.className = "lang-picker-menu hidden";
    menuEl.setAttribute("role", "listbox");

    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(select);
    wrap.appendChild(trigger);
    wrap.appendChild(menuEl);

    function sync() {
      const selectedOption = select.options[select.selectedIndex] || select.options[0];
      value.textContent = selectedOption ? selectedOption.textContent : "";
      trigger.replaceChildren(value);
      Array.from(menuEl.children).forEach((child) => {
        child.classList.toggle("active", child.dataset.value === select.value);
      });
    }

    Array.from(select.options).forEach((option) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "lang-picker-option";
      item.dataset.value = option.value;
      item.textContent = option.textContent;
      item.addEventListener("click", () => {
        select.value = option.value;
        sync();
        select.dispatchEvent(new Event("change", { bubbles: true }));
        closeOpenPicker();
      });
      menuEl.appendChild(item);
    });

    trigger.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const shouldOpen = !wrap.classList.contains("open");
      closeOpenPicker();
      if (!shouldOpen) return;
      wrap.classList.add("open");
      menuEl.classList.remove("hidden");
      openPicker = { wrap, menu: menuEl };
    });

    select.addEventListener("change", sync);
    select.dataset.customized = "true";
    pickerSync.set(select, sync);
    sync();
  }

  [spoken, reply, display].forEach(enhanceSelect);

  function toggleMenu(force) {
    const willOpen = typeof force === "boolean" ? force : menu.classList.contains("hidden");
    closeOpenPicker();
    if (willOpen) {
      closeMenu();
    }
    menu.classList.toggle("hidden", !willOpen);
    state.langMenuOpen = willOpen;
    syncOverlayPresentation();
  }
  chip.addEventListener("click", () => toggleMenu());

  // Close when clicking outside
  document.addEventListener("click", (e) => {
    if (openPicker && !openPicker.wrap.contains(e.target)) {
      closeOpenPicker();
    }
    if (menu.classList.contains("hidden")) return;
    if (menu.contains(e.target) || chip.contains(e.target)) return;
    toggleMenu(false);
  });

  function chipTextFor(profile, langCode) {
    if (!profile || profile === "auto_multi") return langCode ? langCode.split("-")[0].toUpperCase() + "·M" : "AUTO";
    if (profile.startsWith("pinned:")) {
      const code = profile.split(":", 2)[1] || "";
      return code.split("-")[0].toUpperCase() || "EN";
    }
    return (langCode || "EN").split("-")[0].toUpperCase();
  }

  function applyClicked() {
    const profileVal = spoken.value || "auto_multi";
    const payload = { display_language: display.value || null };
    if (profileVal === "auto_multi") {
      payload.profile = "auto_multi";
    } else if (profileVal.startsWith("pinned:")) {
      payload.profile = "pinned";
      payload.pinned_code = profileVal.split(":", 2)[1];
    }
    if (reply.value) payload.response_language = reply.value;
    const sent = wsSend("SET_LANGUAGE_PROFILE", payload);
    status.textContent = sent ? "Sending…" : "Offline";
    if (!sent) return;
    // Pre-update chip so feedback is immediate; backend echo will overwrite.
    label.textContent = chipTextFor(payload.profile === "pinned" ? `pinned:${payload.pinned_code}` : "auto_multi", reply.value);
  }
  apply.addEventListener("click", applyClicked);

  // Hook LANGUAGE_UPDATE events. The existing message dispatcher in this file
  // doesn't expose a clean event bus, so we monkey-patch the WS onmessage by
  // listening for backend ACKs via a BroadcastChannel proxy is overkill —
  // instead we wrap window-level handler. We rely on the fact that wsSend()
  // and the message handler share `state.ws`; we tap by overriding the WS
  // onmessage after it's set. Defer to ensure ws is initialised.
  let installed = false;
  function installTap() {
    if (installed) return;
    const ws = (window.state || state || {}).ws || state.ws;
    if (!ws) return;
    const prev = ws.onmessage;
    ws.onmessage = function (ev) {
      try {
        const msg = JSON.parse(ev.data);
        if (msg && msg.type === "LANGUAGE_UPDATE") {
          const p = msg.payload || {};
          if (p.multilang_enabled === false) {
            status.textContent = "Backend flag off — saved for later.";
          } else {
            status.textContent = "Applied.";
          }
          applyLanguageState(p);
          // Echo to the full window so its pill + status line update too.
          try { channel.postMessage({ type: "LANGUAGE_ACK", payload: p }); } catch (_) {}
        }
      } catch (_) { /* fall through */ }
      if (typeof prev === "function") return prev.call(this, ev);
    };
    installed = true;
  }
  // Retry until ws is connected (every 250ms, give up after 30s).
  let attempts = 0;
  const tapTimer = setInterval(() => {
    installTap();
    if (installed || ++attempts > 120) clearInterval(tapTimer);
  }, 250);
})();
