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
  sessionLive: false,
  sessionStarting: false,

  // Hold-to-ask
  holdActive: false,
  holdSource: null,
  awaitingPrivateReply: false,

  // Audio
  playbackCtx: null,
  playbackDest: null,
  playbackEl: null,
  micStream: null,
  micCapture: null,
  micForwardEl: null,
  meetingCapture: null,
  vbCableDeviceId: null,
  listeningDeviceId: null,

  // Meeting
  meetingTargets: [],
  selectedTarget: null,

  // Chat (private AI only)
  chatEntries: [],

  // Full conversation (for full window)
  conversationEntries: [],
  privateEntries: [],

  // UI
  orbState: "idle",   // idle | active | listening | speaking
  menuOpen: false,
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
const root      = $("overlay-root");
const orb       = $("assistant-orb");
const orbIcon   = $("orb-icon");
const ringPath  = $("ring-path");
const menu      = $("meeting-menu");
const panel     = $("caption-panel");
const chatFeed  = $("chat-feed");
const video     = $("meeting-video");

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
  orb.className = `assistant-orb state-${s}`;
  orbIcon.textContent = s === "listening" ? "◉" : s === "speaking" ? "◎" : "✦";
}

// ─── Root classes ─────────────────────────────────────────────────────────────
function updateRootClasses() {
  root.classList.toggle("has-content", state.chatEntries.length > 0 && !state.holdActive);
  root.classList.toggle("is-listening", state.holdActive);
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
function renderChat() {
  chatFeed.innerHTML = "";
  const visible = state.chatEntries.slice(-3);
  for (const e of visible) {
    const b = document.createElement("div");
    b.className = `chat-bubble ${e.speaker}`;
    b.textContent = e.speaker === "user" ? `You: ${e.text}` : `AI: ${e.text}`;
    chatFeed.appendChild(b);
  }
  updateRootClasses();
  bridge.setOverlayPresentation(
    state.holdActive ? "listening" :
    state.chatEntries.length > 0 ? "captions" : "idle"
  ).catch(() => {});
}

function pushChat(speaker, text) {
  if (!text?.trim()) return;
  state.chatEntries.push({ speaker, text, ts: Date.now() });
  state.chatEntries = state.chatEntries.slice(-20);
  renderChat();
}

// ─── Broadcast to full window ─────────────────────────────────────────────────
function broadcast(type, payload) {
  channel.postMessage({ type, payload });
}
function broadcastSnapshot() {
  broadcast("STATE_SNAPSHOT", {
    sessionLive: state.sessionLive,
    sessionStarting: state.sessionStarting,
    meetingTitle: state.selectedTarget?.window_title || null,
    meetingTargets: state.meetingTargets,
    conversationEntries: state.conversationEntries.slice(-80),
    privateEntries: state.privateEntries.slice(-40),
    listeningDeviceId: state.listeningDeviceId,
    vbCableDeviceId: state.vbCableDeviceId,
    holdActive: state.holdActive,
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

async function connectBackend() {
  if (state.ws?.readyState === WebSocket.OPEN) return;
  if (state.wsConnecting) return;
  state.wsConnecting = true;

  await new Promise((resolve, reject) => {
    const ws = new WebSocket(BACKEND_WS_URL);
    ws.binaryType = "arraybuffer";
    ws.onopen = () => { state.ws = ws; state.wsConnecting = false; resolve(); };
    ws.onerror = () => { state.wsConnecting = false; reject(new Error("WS error")); };
    ws.onclose = () => { state.wsConnecting = false; state.backendState = "IDLE"; state._pendingStart = false; };
    ws.onmessage = handleWsMessage;
  });
}

function handleWsMessage(ev) {
  if (ev.data instanceof ArrayBuffer) { playPcm(ev.data); return; }
  let msg;
  try { msg = JSON.parse(ev.data); } catch (_) { return; }

  const t = msg.type;
  const p = msg.payload || {};

  if (t === "CONNECTION_ESTABLISHED") {
    state.sessionId     = p.session_id;
    state.backendState  = "IDLE";
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
    state.backendState = "ACTIVE";
    setOrbState("active");

    // Now that backend is ACTIVE, send the messages that require ACTIVE state
    wsSend("MEETING_BINDING", {
      target_id: state.selectedTarget?.target_id,
      window_title: state.selectedTarget?.window_title,
      platform_hint: state.selectedTarget?.platform_hint || "generic",
      is_bound: true,
    });
    reportCaptureHealth({
      mic_forward_ok: Boolean(state.micForwardEl),
      frame_capture_ok: Boolean(state.meetingCapture),
      remote_audio_ok: Boolean(state.meetingCapture?.hasAudio),
    });

    // Activate copilot for proactive AI monitoring + intel injection
    wsSend("START_COPILOT", {});
    broadcastSnapshot();
  }
  if (t === "COPILOT_STARTED") {
    // Backend confirmed copilot active — ensure local state is consistent
    state.sessionLive = true;
    setOrbState("active");
    broadcastSnapshot();
  }
  if (t === "TRANSCRIPT_UPDATE") {
    const isAskAI = p.context === "ask_ai";
    const entry = { speaker: p.speaker, text: p.text, ts: p.timestamp || Date.now(), context: p.context };
    state.conversationEntries.push(entry);
    state.conversationEntries = state.conversationEntries.slice(-80);
    broadcast("CONVERSATION_ENTRY", entry);
    // Show the user's own private question in the overlay chat panel
    if (isAskAI && p.speaker === "user" && p.text) {
      pushChat("user", p.text);
      state.privateEntries.push(entry);
      broadcast("PRIVATE_ENTRY", entry);
    }
    broadcastSnapshot();
  }
  if (t === "AI_RESPONSE") {
    setOrbState("speaking");
    const entry = { speaker: "ai", text: p.text, ts: p.timestamp || Date.now() };
    state.conversationEntries.push(entry);
    state.conversationEntries = state.conversationEntries.slice(-80);
    broadcast("CONVERSATION_ENTRY", entry);
    // Always show AI response in overlay private panel when awaiting a reply
    if (state.awaitingPrivateReply) {
      pushChat("ai", p.text);
      state.privateEntries.push(entry);
      broadcast("PRIVATE_ENTRY", entry);
      state.awaitingPrivateReply = false;
    }
    setTimeout(() => { if (state.sessionLive) setOrbState("active"); }, 3000);
    broadcastSnapshot();
  }
  if (t === "OUTCOME_SUMMARY") {
    state.sessionLive = false;
    setOrbState("idle");
    broadcastSnapshot();
  }
  if (t === "DEGRADED_MODE_UPDATE" && p.active) {
    broadcast("DEGRADED", p);
  }
}

// ─── Audio playback (AI voice) ────────────────────────────────────────────────
async function ensurePlayback() {
  if (state.playbackCtx) return;
  state.playbackCtx = new AudioContext({ sampleRate: 24000, latencyHint: "interactive" });
  state.playbackDest = state.playbackCtx.createMediaStreamDestination();
  const el = document.createElement("audio");
  el.autoplay = true;
  el.srcObject = state.playbackDest.stream;
  // Route to user's listening device (headphones or default speaker)
  if (state.listeningDeviceId && typeof el.setSinkId === "function") {
    await el.setSinkId(state.listeningDeviceId).catch(() => {});
  }
  await el.play().catch(() => {});
  state.playbackEl = el;
}

function playPcm(buffer) {
  ensurePlayback().then(() => {
    const i16 = new Int16Array(buffer);
    const ab = state.playbackCtx.createBuffer(1, i16.length, 24000);
    const ch = ab.getChannelData(0);
    for (let i = 0; i < i16.length; i++) ch[i] = i16[i] / 32768;
    const src = state.playbackCtx.createBufferSource();
    src.buffer = ab;
    src.connect(state.playbackDest);
    src.start();
  }).catch(() => {});
}

// ─── PCM capture stream ───────────────────────────────────────────────────────
function createPcmCapture(stream, msgType, flushMs = 1200) {
  const ctx = new AudioContext({ sampleRate: 16000, latencyHint: "interactive" });
  const src = ctx.createMediaStreamSource(stream);
  const proc = ctx.createScriptProcessor(4096, 1, 1);
  const chunks = [];
  let startedAt = null;

  const flush = (final = true) => {
    if (!chunks.length) return;
    const total = chunks.reduce((s, c) => s + c.byteLength, 0);
    const merged = new Uint8Array(total);
    let off = 0;
    for (const c of chunks.splice(0)) { merged.set(new Uint8Array(c), off); off += c.byteLength; }
    wsSend(msgType, {
      pcm_base64: toBase64(merged.buffer),
      timestamp_ms: Date.now(),
      started_at_ms: startedAt || Date.now(),
      utterance_id: `${msgType}_${Date.now()}`,
      is_final: final,
    });
    startedAt = null;
  };

  proc.onaudioprocess = (e) => {
    if (!startedAt) startedAt = Date.now();
    chunks.push(f32ToI16Buffer(e.inputBuffer.getChannelData(0)));
  };

  src.connect(proc);
  proc.connect(ctx.destination);
  const timer = setInterval(() => flush(true), flushMs);

  return {
    stop: async () => {
      clearInterval(timer);
      flush(true);
      proc.disconnect(); src.disconnect();
      stream.getTracks().forEach(t => t.stop());
      await ctx.close();
    },
  };
}

// ─── Auto-detect audio devices ───────────────────────────────────────────────
async function autoSelectDevices() {
  let devices;
  try {
    // Trigger permission prompt first
    await navigator.mediaDevices.getUserMedia({ audio: true }).then(s => s.getTracks().forEach(t => t.stop()));
    devices = await navigator.mediaDevices.enumerateDevices();
  } catch (_) { return; }

  const outputs = devices.filter(d => d.kind === "audiooutput");
  const inputs  = devices.filter(d => d.kind === "audioinput");

  // VB-CABLE: find "CABLE Input" (the output sink to route mic to)
  const vbInput = outputs.find(d => /cable input|vb-audio|voicemeeter input/i.test(d.label));
  if (vbInput) {
    state.vbCableDeviceId = vbInput.deviceId;
    state.prefs.vbCableDeviceId = vbInput.deviceId;
  }

  // Listening output: prefer headphones/headset, then current default
  const headphones = outputs.find(d => /headphone|headset|earphone|airpod|buds/i.test(d.label));
  const listening = headphones || outputs.find(d => d.deviceId === "default") || outputs[0];
  if (listening) {
    state.listeningDeviceId = listening.deviceId;
    state.prefs.listeningDeviceId = listening.deviceId;
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
  }

  if (!state.vbCableDeviceId) return;

  const el = document.createElement("audio");
  el.autoplay = true;
  el.srcObject = stream;
  if (typeof el.setSinkId === "function") {
    await el.setSinkId(state.vbCableDeviceId).catch(() => {});
  }
  await el.play().catch(() => {});
  state.micForwardEl = el;
}

// ─── Meeting capture ──────────────────────────────────────────────────────────
async function stopMeetingCapture() {
  if (!state.meetingCapture) return;
  clearInterval(state.meetingCapture.frameTimer);
  await state.meetingCapture.audio.stop();
  state.meetingCapture.stream.getTracks().forEach(t => t.stop());
  state.meetingCapture = null;
  video.srcObject = null;
}

async function startMeetingCapture() {
  await stopMeetingCapture();

  const stream = await navigator.mediaDevices.getDisplayMedia({
    video: { frameRate: { ideal: 4, max: 8 } },
    audio: true,
  });

  video.srcObject = stream;
  await video.play().catch(() => {});

  const hasAudio = stream.getAudioTracks().length > 0;

  const frameTimer = setInterval(() => {
    // Only send frames once the backend is in ACTIVE state.
    // Sending before ACTIVE triggers rejected-message warnings in the backend.
    if (state.backendState !== "ACTIVE") return;
    if (!video.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width  = Math.min(960, video.videoWidth);
    canvas.height = Math.min(540, video.videoHeight);
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    wsSend("SCREEN_FRAME", {
      image: canvas.toDataURL("image/jpeg", 0.65).split(",")[1],
      timestamp: Date.now(),
      source_mode: "virtual_companion_desktop",
      source: "meeting_window",
    });
  }, 1200);

  state.meetingCapture = {
    stream,
    hasAudio,
    audio: createPcmCapture(stream, "REMOTE_APP_PCM", 1400),
    frameTimer,
  };

  // Recover if capture ends unexpectedly
  const vtrack = stream.getVideoTracks()[0];
  if (vtrack) {
    vtrack.addEventListener("ended", async () => {
      await stopMeetingCapture();
      wsSend("CAPTURE_HEALTH", { remote_audio_ok: false, frame_capture_ok: false,
        unsafe_device_loopback: false, degraded_reasons: ["meeting_capture_ended"] });
      broadcastSnapshot();
    });
  }

  reportCaptureHealth({ remote_audio_ok: hasAudio, frame_capture_ok: true });
}

// ─── Capture health ───────────────────────────────────────────────────────────
function reportCaptureHealth(overrides = {}) {
  const hasVb = Boolean(state.vbCableDeviceId && state.micForwardEl);
  const health = {
    mic_forward_ok: Boolean(state.micForwardEl),
    remote_audio_ok: Boolean(state.meetingCapture?.hasAudio),
    frame_capture_ok: Boolean(state.meetingCapture),
    reply_output_ok: Boolean(state.listeningDeviceId),
    helper_active: hasVb,
    process_loopback_ok: Boolean(state.meetingCapture?.hasAudio),
    unsafe_device_loopback: false,
    degraded_reasons: hasVb ? [] : ["vbcable_not_detected"],
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
      output_device_id: state.listeningDeviceId,
      output_device_label: null,
      is_bound: true,
    },
    selected_output_device: { device_id: state.listeningDeviceId, label: null },
  });
}

async function startSession() {
  if (state.sessionLive || state.sessionStarting) return;
  if (!state.selectedTarget) throw new Error("No meeting target selected");

  state.sessionStarting = true;
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
    await bridge.bindMeetingTarget(state.selectedTarget);

    // Start screen + audio capture.  SCREEN_FRAME is gated inside startMeetingCapture
    // to only transmit once backendState reaches "ACTIVE".
    await startMeetingCapture().catch((captureErr) => {
      console.warn("Meeting capture failed (non-fatal):", captureErr?.message || captureErr);
    });

    // Capture physical mic
    const micStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    state.micStream = micStream;

    // Forward mic to VB-CABLE (meeting app hears us through this)
    await setupMicForward(micStream);

    // PCM capture → LOCAL_MIC_PCM.  Backend silently drops it until ACTIVE.
    if (state.micCapture) await state.micCapture.stop();
    state.micCapture = createPcmCapture(micStream, "LOCAL_MIC_PCM", 1200);

    // CAPTURE_HEALTH and MEETING_BINDING WS messages are sent in the SESSION_STARTED
    // handler after the backend is in ACTIVE state.

    // Drive the consent → start flow based on current backend state.
    if (state.backendState === "CONSENTED") {
      // Already consented (from a previous attempt), go straight to START
      sendStartNegotiation();
    } else {
      // IDLE or unknown — send consent and wait for CONSENT_ACKNOWLEDGED
      state._pendingStart = true;
      wsSend("PRIVACY_CONSENT_GRANTED", { version: "1.0", mode: "live" });
    }

  } catch (err) {
    state.sessionStarting = false;
    state.sessionLive = false;
    setOrbState("idle");
    broadcastSnapshot();   // Tell full window the start failed so UI resets
    console.error("[startSession] failed:", err?.message || err);
    throw err;
  }
}

// ─── Meeting target selection ─────────────────────────────────────────────────
async function selectTarget(target) {
  state.selectedTarget = target;
  state.prefs.lastMeetingTitle = target.window_title;
  savePrefs();
  closeMenu();
  await startSession().catch(console.error);
  broadcastSnapshot();
}

// ─── Meeting menu ─────────────────────────────────────────────────────────────
function closeMenu() {
  menu.classList.add("hidden");
  state.menuOpen = false;
  bridge.setOverlayPresentation(state.chatEntries.length > 0 ? "captions" : "idle").catch(() => {});
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
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "meeting-option" + (state.selectedTarget?.target_id === t.target_id ? " active" : "");
    const label = document.createElement("span");
    label.textContent = t.window_title;
    const badge = document.createElement("span");
    badge.className = "platform-badge";
    badge.textContent = t.platform_hint;
    btn.appendChild(label);
    btn.appendChild(badge);
    btn.addEventListener("click", () => void selectTarget(t));
    menu.appendChild(btn);
  }
}

async function openMenu() {
  state.meetingTargets = await bridge.listMeetingTargets();
  renderMenu();
  menu.classList.remove("hidden");
  state.menuOpen = true;
  bridge.setOverlayPresentation("menu").catch(() => {});
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
  if (!wsOpen || (!state.sessionLive && !state.sessionStarting)) return;
  if (state.holdActive === active) return;
  state.holdActive = active;

  // Mute/unmute mic forward to VB-CABLE (meeting mic path)
  if (state.micForwardEl) state.micForwardEl.muted = active;

  if (active) {
    state.awaitingPrivateReply = true;
    setOrbState("listening");
  } else {
    setOrbState("active");
  }

  updateRootClasses();
  renderChat();
  bridge.setHoldToAsk({ active, muted_to_meeting: active }).catch(() => {});
  wsSend("HOLD_TO_ASK_STATE", { active, muted_to_meeting: active, source });
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

document.addEventListener("mousedown", () => {
  if (state.sessionLive) startRingFill();
});
document.addEventListener("mouseup", () => {
  stopRingFill();
  // If hold is active via mouse, end it on release
  if (state.holdActive && state.holdSource === "mouse") {
    void setHold(false, "mouse");
    state.holdSource = null;
  }
});

// ─── Global hold events from main process (PS script) ────────────────────────
bridge.onGlobalHoldState((payload) => {
  const active = Boolean(payload?.active);
  const source = payload?.source || "keyboard";

  if (active) {
    state.holdSource = source;
    void setHold(true, source);
    if (source === "mouse") startRingFill();
  } else {
    if (source === state.holdSource || !state.holdSource) {
      stopRingFill();
      void setHold(false, source);
      state.holdSource = null;
    }
  }
});

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
  if (!state.sessionLive) return;
  orbHoldTimer = setTimeout(() => {
    if (!state.dragMoved) {
      state.holdSource = "orb";
      void setHold(true, "orb");
    }
  }, 150);
});
window.addEventListener("pointerup", () => {
  clearTimeout(orbHoldTimer);
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
  if (type === "COMMAND_SELECT_MEETING" && payload?.target) void selectTarget(payload.target);
  if (type === "COMMAND_END_SESSION") {
    wsSend("END_NEGOTIATION", {});
    state.sessionLive = false;
    state.holdActive  = false;
    setOrbState("idle");
    if (state.micForwardEl) { state.micForwardEl.muted = false; }
    bridge.endCompanionSession().catch(() => {});
    broadcastSnapshot();
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
      // Auto-start after a short delay to let the window settle
      setTimeout(() => void startSession().catch(() => {}), 500);
    }
  }

  await autoSelectDevices();
  await refreshContrast();
  broadcastSnapshot();
});
