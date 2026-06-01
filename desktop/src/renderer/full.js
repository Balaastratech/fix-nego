"use strict";

const bridge  = window.companionBridge;
const channel = new BroadcastChannel("negotiation_companion_ui");

// ─── DOM ─────────────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const sessionPill     = $("session-pill");
const dotSession      = $("dot-session");
const dotMeeting      = $("dot-meeting");
const labelSession    = $("label-session");
const labelMeeting    = $("label-meeting");
const holdBadge       = $("hold-badge");
const meetingList     = $("meeting-list");
const btnRefresh      = $("btn-refresh");
const btnStart        = $("btn-start");
const btnPause        = $("btn-pause");
const btnResume       = $("btn-resume");
const btnEnd          = $("btn-end");
const btnMinimize     = $("btn-minimize");
const labelMic        = $("label-mic");
const labelVbcable    = $("label-vbcable");
const labelOutput     = $("label-output");
const dotMic          = $("dot-mic");
const dotVbcable      = $("dot-vbcable");
const dotOutput       = $("dot-output");
const vbcableHint     = $("vbcable-hint");
const listenBanner    = $("listen-banner");
const listenLabel     = $("listen-label");
const transcriptList  = $("transcript-list");
const privateList     = $("private-list");
const transcriptCount = $("transcript-count");
const privateCount    = $("private-count");
const researchList    = $("research-list");
const researchCount   = $("research-count");
const researchPill    = $("research-status-pill");
const researchBar     = $("research-status-bar");
const researchQueryLabel = $("research-query-label");
const captureNote     = $("capture-note");
const btnRepick       = $("btn-repick");

// ─── State ────────────────────────────────────────────────────────────────────
const state = {
  sessionLive: false,
  sessionStarting: false,
  sessionPaused: false,
  backendReady: false,
  wsConnected: false,
  backendStatusMessage: "Connecting to AI services…",
  holdActive: false,
  meetingTitle: null,
  selectedTarget: null,
  selectedSourceId: null,   // desktop source id matched from getScreenSources
  meetingTargets: [],
  screenSources: [],        // from getScreenSources — has thumbnails
  conversationEntries: [],
  privateEntries: [],
  researchEntries: [],
  researchActive: false,
  researchActiveQuery: "",
  listeningDeviceId: null,
  vbCableDeviceId: null,
  privacyStrategy: null,   // "policyconfig" | "hotkey" | "vbcable" | null
  selectedMicLabel: null,
  orbState: null,
};

function upsertEntry(list, entry, limit) {
  const next = [...list];
  const existingIndex = next.findIndex((item) => item.id === entry.id);
  if (existingIndex >= 0) {
    next[existingIndex] = { ...next[existingIndex], ...entry };
    return next.slice(-limit);
  }
  next.push(entry);
  return next.slice(-limit);
}

// ─── Render ───────────────────────────────────────────────────────────────────
function renderSessionStatus() {
  if (state.sessionPaused) {
    sessionPill.textContent = "Paused";
    sessionPill.className   = "pill pill-start";
    dotSession.className    = "status-dot dot-amber";
    labelSession.textContent = "Session paused";
  } else if (state.sessionLive) {
    sessionPill.textContent = "Live";
    sessionPill.className   = "pill pill-live";
    dotSession.className    = "status-dot dot-green";
    labelSession.textContent = "Session active";
  } else if (state.sessionStarting) {
    sessionPill.textContent = "Starting…";
    sessionPill.className   = "pill pill-start";
    dotSession.className    = "status-dot dot-amber";
    labelSession.textContent = "Starting…";
  } else {
    sessionPill.textContent = "Idle";
    sessionPill.className   = "pill pill-idle";
    dotSession.className    = "status-dot";
    labelSession.textContent = "No session";
  }
  holdBadge.style.display = state.holdActive ? "flex" : "none";
  btnStart.style.display  = (state.sessionLive || state.sessionPaused || state.sessionStarting) ? "none" : "flex";
  btnPause.style.display  = (state.sessionLive && !state.sessionPaused) ? "flex" : "none";
  btnResume.style.display = state.sessionPaused ? "flex" : "none";
  btnEnd.style.display    = (state.sessionLive || state.sessionPaused || state.sessionStarting) ? "flex" : "none";

  // Disable Start until BOTH a meeting window is selected AND the backend has
  // finished connecting/warming up. Plain-language tooltip explains why.
  const ready = state.wsConnected && state.backendReady;
  const canStart = Boolean(state.selectedTarget) && ready;
  btnStart.disabled = !canStart;
  btnStart.title = !ready
    ? (state.backendStatusMessage || "Connecting to AI services…")
    : !state.selectedTarget
    ? "Select a meeting window first"
    : "Start session";
  // When the backend isn't ready yet, relabel the button so the user understands
  // the wait instead of clicking a dead button.
  if (!(state.sessionLive || state.sessionPaused || state.sessionStarting)) {
    btnStart.textContent = ready ? "Start Session" : "Connecting…";
  }
  btnPause.disabled = !state.sessionLive || state.sessionPaused || state.sessionStarting;
  btnResume.disabled = !state.sessionPaused;
  btnEnd.disabled = false;
  renderConnectionBanner();
  // Update the card hint so user knows they can click to switch screens mid-session
  const cardHint = document.querySelector("#card-picker .card-hint");
  if (cardHint) {
    cardHint.textContent = state.sessionPaused
      ? "Session is paused. Resume to continue capture and AI processing."
      : state.sessionLive
      ? "Click any screen below to switch capture instantly."
      : "Select your meeting app window. Mic routing, VB-CABLE, and output device are configured automatically.";
  }
}

function renderCaptureNote() {
  if (!captureNote) return;
  const sessionActive = state.sessionLive || state.sessionStarting || state.sessionPaused;
  captureNote.classList.toggle("hidden", !(state.captureFollowingScreen && sessionActive));
}

// ─── Connection / readiness banner ────────────────────────────────────────────
// A prominent, plain-language strip at the top of the dashboard that tells the
// user exactly what's happening: connecting, warming up the AI, ready, or
// reconnecting. Hidden once a session is live (the session status bar covers it).
function renderConnectionBanner() {
  const banner = $("conn-banner");
  if (!banner) return;
  const dot   = $("conn-banner-dot");
  const label = $("conn-banner-label");

  const sessionActive = state.sessionLive || state.sessionStarting || state.sessionPaused;
  if (sessionActive) {
    banner.classList.add("hidden");
    return;
  }
  banner.classList.remove("hidden");

  let cls, text;
  if (!state.wsConnected) {
    cls = "offline";
    text = "Connecting to the AI server… please wait.";
  } else if (!state.backendReady) {
    cls = "warming";
    text = state.backendStatusMessage || "Getting the AI services ready… please wait.";
  } else {
    cls = "ready";
    text = state.selectedTarget
      ? "AI services ready. You can start your session."
      : "AI services ready. Pick your meeting window below, then Start.";
  }
  if (dot)   dot.className = "conn-banner-dot " + cls;
  if (label) label.textContent = text;
  banner.className = "conn-banner " + cls;
}

function renderMeetingStatus() {
  if (state.meetingTitle) {
    dotMeeting.className    = "status-dot dot-green";
    labelMeeting.textContent = state.meetingTitle;
  } else if (state.selectedTarget) {
    dotMeeting.className    = "status-dot dot-green";
    labelMeeting.textContent = state.selectedTarget.window_title;
  } else {
    dotMeeting.className    = "status-dot";
    labelMeeting.textContent = "No meeting selected";
  }
}

const BANNER_LABELS = {
  ready:        "🎙 Listening — speak naturally",
  speaking:     "🔵 Your voice detected — transcribing...",
  transcribing: "⚡ Processing speech...",
  ai:           "🤖 AI is responding...",
};

function renderListenBanner() {
  const orb = state.orbState;
  if (!state.sessionLive && !state.sessionPaused) {
    listenBanner.classList.add("hidden");
    return;
  }
  listenBanner.classList.remove("hidden");
  let bannerState = "ready";
  if (state.sessionPaused)       bannerState = "paused";
  else if (state.holdActive)     bannerState = "ai";
  else if (orb === "responding") bannerState = "ai";
  else if (orb === "processing") bannerState = "transcribing";
  else if (orb === "listening")  bannerState = "speaking";
  else                           bannerState = "ready";

  listenBanner.setAttribute("data-state", bannerState);
  // While holding, reassure the user the counterparty cannot hear the private AI exchange.
  // The mute is real in every strategy (hotkey = Zoom self-mute, vbcable = forward muted,
  // redirect-cable = process redirected). Wording stays strategy-agnostic.
  if (state.holdActive) {
    listenLabel.textContent = "🔒 Counterparty muted — talking privately to AI";
  } else {
    listenLabel.textContent = bannerState === "paused" ? "Paused" : (BANNER_LABELS[bannerState] || BANNER_LABELS.ready);
  }
}

function renderDevices() {
  const strategy = state.privacyStrategy;
  const driverless = strategy === "policyconfig" || strategy === "hotkey";
  const hasVb  = Boolean(state.vbCableDeviceId);
  const hasOut = Boolean(state.listeningDeviceId);

  labelMic.textContent = state.sessionLive
    ? (state.selectedMicLabel || "System default mic")
    : "Auto on session start";
  dotMic.className = "device-dot" + (state.sessionLive ? " ok" : "");

  if (driverless) {
    // Driverless mode: VB-Cable row shows the active isolation strategy
    const strategyLabel = strategy === "policyconfig" ? "Driverless (IAudioPolicyConfig ✓)" : "Driverless (hotkey ✓)";
    labelVbcable.textContent = strategyLabel;
    dotVbcable.className = "device-dot ok";
    vbcableHint.style.display = "none";
  } else if (hasVb) {
    labelVbcable.textContent = "CABLE Input (detected ✓)";
    dotVbcable.className = "device-dot ok";
    vbcableHint.style.display = "none";
  } else {
    labelVbcable.textContent = "Not found";
    dotVbcable.className = "device-dot err";
    vbcableHint.style.display = "block";
  }

  labelOutput.textContent = hasOut ? "Headphones / Default" : "Auto on session start";
  dotOutput.className = "device-dot" + (hasOut ? " ok" : "");
}

function findSourceForTarget(t) {
  // Match a meetingTarget to a screenSource by title substring
  if (!state.screenSources.length) return null;
  const title = (t.window_title || "").toLowerCase();
  // Exact match first
  let match = state.screenSources.find(s => s.name.toLowerCase() === title);
  // Partial match: window title starts with source name or vice-versa
  if (!match) match = state.screenSources.find(s =>
    title.includes(s.name.toLowerCase()) || s.name.toLowerCase().includes(title)
  );
  return match || null;
}

function renderMeetingTargets() {
  meetingList.innerHTML = "";
  if (!state.meetingTargets.length) {
    const e = document.createElement("div");
    e.className = "empty-state";
    e.textContent = "No meeting windows found. Open Zoom, Teams, or Meet first.";
    meetingList.appendChild(e);
    return;
  }
  for (const t of state.meetingTargets) {
    const isSelected = state.selectedTarget?.window_title === t.window_title;
    const src = findSourceForTarget(t);

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "target-btn" + (isSelected ? " selected" : "");

    // Thumbnail (shown if we have a screen source match)
    if (src?.thumbnail) {
      const thumb = document.createElement("img");
      thumb.className = "target-thumb";
      thumb.src = src.thumbnail;
      thumb.alt = t.window_title;
      btn.appendChild(thumb);
    }

    const info = document.createElement("div");
    info.className = "target-info";

    const name = document.createElement("span");
    name.className = "target-name";
    name.textContent = t.window_title;

    const chip = document.createElement("span");
    chip.className = "platform-chip";
    chip.textContent = t.platform_hint;

    info.appendChild(name);
    info.appendChild(chip);
    btn.appendChild(info);

    btn.addEventListener("click", () => {
      state.selectedTarget  = t;
      state.selectedSourceId = src?.id || t.target_id || null;
      state.meetingTitle    = t.window_title;
      renderMeetingTargets();
      renderMeetingStatus();
      renderSessionStatus();
      channel.postMessage({
        type: "COMMAND_SELECT_MEETING",
        payload: {
          target: t,
          source_id: src?.id || t.target_id || null,
          source_name: src?.name || t.window_title || null,
          source_kind: src?.kind || (String(src?.id || t.target_id || "").startsWith("screen:") ? "screen" : "window"),
        },
      });
    });
    meetingList.appendChild(btn);
  }
}

function _fmtTime(ts) {
  const d = new Date(ts || Date.now());
  const pad = (n, w = 2) => String(n).padStart(w, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(d.getMilliseconds(), 3)}`;
}

function renderEntryList(container, entries, emptyText) {
  container.innerHTML = "";
  if (!entries.length) {
    const e = document.createElement("div");
    e.className = "empty-state";
    e.textContent = emptyText;
    container.appendChild(e);
    return;
  }
  for (const entry of entries.slice().reverse()) {
    const card = document.createElement("div");
    card.className = `entry ${entry.speaker || "ai"}`;
    const hdr = document.createElement("div");
    hdr.className = "entry-header";
    const who = document.createElement("span");
    who.className = "entry-who";
    who.textContent = entry.speaker === "counterparty" ? "Counterparty" :
                      entry.speaker === "user"         ? "You" : "AI";
    const when = document.createElement("span");
    when.className = "entry-time";
    when.textContent = _fmtTime(entry.ts || entry.timestamp);
    hdr.appendChild(who); hdr.appendChild(when);
    const body = document.createElement("div");
    body.className = "entry-text";
    body.textContent = entry.text || "";
    card.appendChild(hdr); card.appendChild(body);
    container.appendChild(card);
  }
}

// Paired Q→A renderer for the Private AI Asks panel. Groups consecutive
// user/AI entries into iterations (one user question + its AI reply), renders
// newest pair on top, with user bubble on the left and AI bubble on the right
// — chat-app style. Uses ms-precision timestamps so identical-second messages
// keep their true ordering.
function renderPairedAsks(container, entries, emptyText) {
  container.innerHTML = "";
  if (!entries.length) {
    const e = document.createElement("div");
    e.className = "empty-state";
    e.textContent = emptyText;
    container.appendChild(e);
    return;
  }
  // Build pairs in chronological order (oldest first).
  const pairs = [];
  let cur = null;
  for (const entry of entries) {
    if (entry.speaker === "user") {
      if (cur && cur.user) pairs.push(cur);
      cur = { user: entry, ai: null };
    } else if (entry.speaker === "ai") {
      if (!cur) cur = { user: null, ai: entry };
      else if (cur.ai && !cur.ai.isPartial) {
        pairs.push(cur);
        cur = { user: null, ai: entry };
      } else {
        cur.ai = entry;
      }
    }
  }
  if (cur && (cur.user || cur.ai)) pairs.push(cur);

  // Newest pair at the top.
  for (const pair of pairs.slice().reverse()) {
    const wrap = document.createElement("div");
    wrap.className = "ask-pair";

    const renderSide = (entry, side) => {
      if (!entry) return;
      const row = document.createElement("div");
      row.className = `ask-row ask-row-${side}`;
      const bubble = document.createElement("div");
      bubble.className = `ask-bubble ask-bubble-${side}${entry.isPartial ? " partial" : ""}`;
      const txt = document.createElement("div");
      txt.className = "ask-bubble-text";
      txt.textContent = entry.text || "";
      bubble.appendChild(txt);
      const meta = document.createElement("div");
      meta.className = "ask-bubble-meta";
      const who = document.createElement("span");
      who.className = "ask-bubble-who";
      who.textContent = side === "user" ? "You" : "AI";
      const time = document.createElement("span");
      time.className = "ask-bubble-time";
      time.textContent = _fmtTime(entry.ts || entry.timestamp);
      meta.appendChild(who);
      meta.appendChild(time);
      row.appendChild(bubble);
      row.appendChild(meta);
      wrap.appendChild(row);
    };

    renderSide(pair.user, "user");
    renderSide(pair.ai, "ai");
    container.appendChild(wrap);
  }
}

function renderResearchPanel() {
  // Update status pill
  if (state.researchActive) {
    researchPill.textContent  = "Running…";
    researchPill.className    = "research-pill research-pill-active";
    researchBar.style.display = "flex";
    researchQueryLabel.textContent = state.researchActiveQuery || "Searching…";
  } else if (state.researchEntries.length > 0) {
    researchPill.textContent  = "Done";
    researchPill.className    = "research-pill research-pill-done";
    researchBar.style.display = "none";
  } else {
    researchPill.textContent  = "Idle";
    researchPill.className    = "research-pill research-pill-idle";
    researchBar.style.display = "none";
  }
  researchCount.textContent = state.researchEntries.length;

  researchList.innerHTML = "";
  if (!state.researchEntries.length) {
    const e = document.createElement("div");
    e.className = "empty-state";
    e.textContent = "Market research will appear automatically during negotiation.";
    researchList.appendChild(e);
    return;
  }
  // Render newest first
  for (const r of state.researchEntries.slice().reverse()) {
    const card = document.createElement("div");
    card.className = "research-result";

    const hdr = document.createElement("div");
    hdr.className = "research-result-header";

    const q = document.createElement("span");
    q.className = "research-result-query";
    q.textContent = r.query || "Research";

    const ts = document.createElement("span");
    ts.className = "research-result-time";
    ts.textContent = _fmtTime(r.timestamp ? r.timestamp * 1000 : Date.now());

    hdr.appendChild(q);
    hdr.appendChild(ts);
    card.appendChild(hdr);

    const fields = [
      { key: "price_range", icon: "💰", label: "Price Range" },
      { key: "key_facts",   icon: "📌", label: "Key Facts" },
      { key: "leverage",    icon: "⚖️",  label: "Leverage" },
      { key: "tactics",     icon: "🎯", label: "Tactics" },
      { key: "gap_answer",  icon: "🔎", label: "Gap Answer" },
    ];
    let hasData = false;
    for (const f of fields) {
      const raw = r.market_data_obj ? r.market_data_obj[f.key] : null;
      const txt = raw && raw !== "null" ? String(raw) : null;
      if (!txt) continue;
      hasData = true;
      const row = document.createElement("div");
      row.className = "research-field";
      const lbl = document.createElement("span");
      lbl.className = "research-field-label";
      lbl.textContent = `${f.icon} ${f.label}`;
      const val = document.createElement("span");
      val.className = "research-field-value";
      val.textContent = txt;
      row.appendChild(lbl);
      row.appendChild(val);
      card.appendChild(row);
    }
    if (!hasData && r.market_data) {
      const row = document.createElement("div");
      row.className = "research-field";
      const val = document.createElement("span");
      val.className = "research-field-value";
      val.textContent = r.market_data;
      row.appendChild(val);
      card.appendChild(row);
    }
    researchList.appendChild(card);
  }
}

function renderAll() {
  renderSessionStatus();
  renderMeetingStatus();
  renderDevices();
  renderListenBanner();
  renderEntryList(transcriptList, state.conversationEntries,
    "Transcript appears once the session starts.");
  renderPairedAsks(privateList, state.privateEntries,
    "Hold the floating AI orb to talk to AI privately.");
  renderResearchPanel();
  transcriptCount.textContent = state.conversationEntries.length;
  privateCount.textContent    = state.privateEntries.length;
}

// ─── BroadcastChannel from overlay ───────────────────────────────────────────
channel.onmessage = (ev) => {
  const { type, payload } = ev.data || {};

  if (type === "STATE_SNAPSHOT") {
    state.sessionLive     = Boolean(payload.sessionLive);
    state.sessionStarting = Boolean(payload.sessionStarting);
    state.sessionPaused   = Boolean(payload.sessionPaused);
    // NOTE: backendReady / wsConnected are owned by the /api/ready poller
    // (startReadinessPolling) — it's more reliable than this relayed snapshot,
    // which can arrive stale. Do not overwrite them here.
    state.holdActive      = Boolean(payload.holdActive);
    state.meetingTitle    = payload.meetingTitle || null;
    state.listeningDeviceId  = payload.listeningDeviceId || null;
    state.vbCableDeviceId    = payload.vbCableDeviceId || null;
    state.privacyStrategy    = payload.privacyStrategy || null;
    state.selectedMicLabel   = payload.selectedMicLabel || null;
    state.orbState = payload.orbState || null;
    state.captureFollowingScreen = Boolean(payload.captureFollowingScreen);
    renderCaptureNote();
    renderListenBanner();
    if (Array.isArray(payload.meetingTargets) && payload.meetingTargets.length)
      state.meetingTargets = payload.meetingTargets;
    if (Array.isArray(payload.conversationEntries))
      state.conversationEntries = payload.conversationEntries.filter((entry) => entry.speaker !== "ai");
    if (Array.isArray(payload.privateEntries))
      state.privateEntries = payload.privateEntries;
    if (payload.selectedTarget && !state.selectedTarget)
      state.selectedTarget = payload.selectedTarget;
    if (state.meetingTitle && !state.selectedTarget)
      state.selectedTarget = state.meetingTargets.find(t => t.window_title === state.meetingTitle) || null;
    if (!state.meetingTitle && !state.sessionLive && !state.sessionStarting && !state.sessionPaused) {
      state.selectedTarget = null;
      state.selectedSourceId = null;
    }
    // STATE_SNAPSHOT: only re-render control panels — entry lists are kept
    // current by the targeted CONVERSATION_ENTRY / PRIVATE_ENTRY messages.
    renderSessionStatus();
    renderMeetingStatus();
    renderDevices();
    renderListenBanner();
  }

  if (type === "CONVERSATION_ENTRY" && payload) {
    if (payload.speaker === "ai") return;
    // When a final (non-partial) entry arrives, remove any partials for the same
    // speaker so the same utterance doesn't appear as "Hi" (partial) + "Hello." (final).
    if (!payload.isPartial && payload.speaker) {
      state.conversationEntries = state.conversationEntries.filter(
        (e) => !(e.isPartial && e.speaker === payload.speaker)
      );
    }
    state.conversationEntries = upsertEntry(state.conversationEntries, payload, 80);
    renderEntryList(transcriptList, state.conversationEntries, "");
    transcriptCount.textContent = state.conversationEntries.length;
  }

  if (type === "PRIVATE_ENTRY" && payload) {
    state.privateEntries = upsertEntry(state.privateEntries, payload, 40);
    renderPairedAsks(privateList, state.privateEntries, "");
    privateCount.textContent = state.privateEntries.length;
  }

  if (type === "RESEARCH_STARTED" && payload) {
    state.researchActive      = true;
    state.researchActiveQuery = payload.query || "";
    renderResearchPanel();
  }

  if (type === "RESEARCH_COMPLETE" && payload) {
    state.researchActive      = false;
    state.researchActiveQuery = "";
    // Parse structured data if it came as a plain string in market_data
    const entry = {
      query:          payload.query || "",
      market_data:    payload.market_data || "",
      market_data_obj: payload.market_data_obj || null,
      trigger_reason: payload.trigger_reason || "",
      timestamp:      payload.timestamp || (Date.now() / 1000),
    };
    state.researchEntries = [...state.researchEntries, entry].slice(-20);
    renderResearchPanel();
  }

  if (type === "RESEARCH_FAILED" && payload) {
    state.researchActive      = false;
    state.researchActiveQuery = "";
    renderResearchPanel();
  }

  if (type === "DEGRADED" && payload) {
    dotSession.className = "status-dot dot-red";
    labelSession.textContent = `Degraded: ${payload.mode || "capture issue"}`;
  }

  if (type === "START_BLOCKED" && payload) {
    // The overlay refused a Start because the backend wasn't ready yet. Surface
    // the plain-language reason and refresh the banner/button states.
    if (payload.reason) state.backendStatusMessage = payload.reason;
    renderConnectionBanner();
    renderSessionStatus();
  }

  if (type === "PRIVACY_SETUP_NOTE" && payload) {
    // One-time, dismissable setup guidance for the active privacy method.
    showPrivacyMicWarning(payload.message);
  }
};

function showPrivacyMicWarning(message) {
  // Reuse or create a dismissable info banner at the top of the full window
  let banner = document.getElementById("privacy-mic-warning-banner");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "privacy-mic-warning-banner";
    banner.style.cssText = [
      "position:fixed", "top:0", "left:0", "right:0", "z-index:9999",
      "background:#1d4ed8", "color:#fff", "font-size:13px", "font-weight:500",
      "padding:10px 16px", "display:flex", "align-items:center", "gap:12px",
      "box-shadow:0 2px 8px rgba(0,0,0,0.4)",
    ].join(";");

    const text = document.createElement("span");
    text.style.flex = "1";
    banner.appendChild(text);

    const dismiss = document.createElement("button");
    dismiss.textContent = "✕ Dismiss";
    dismiss.style.cssText = "background:rgba(255,255,255,0.2);border:none;color:#fff;cursor:pointer;padding:4px 10px;border-radius:4px;font-size:12px;";
    dismiss.onclick = () => banner.remove();
    banner.appendChild(dismiss);

    document.body.prepend(banner);
  }
  banner.querySelector("span").textContent = message;
}

// ─── Buttons ──────────────────────────────────────────────────────────────────
btnStart.addEventListener("click", () => {
  if (!state.selectedTarget) return;
  channel.postMessage({ type: "COMMAND_START_SESSION" });
});
btnPause.addEventListener("click", () => {
  channel.postMessage({ type: "COMMAND_PAUSE_SESSION" });
});
btnResume.addEventListener("click", () => {
  channel.postMessage({ type: "COMMAND_RESUME_SESSION" });
});
btnEnd.addEventListener("click", () => {
  channel.postMessage({ type: "COMMAND_END_SESSION" });
});
btnMinimize.addEventListener("click", () => {
  bridge.minimizeFullWindow().catch(() => {});
});
async function refreshTargets() {
  try {
    // Load both the meeting target list AND thumbnails in parallel
    const [targets, sources] = await Promise.all([
      bridge.listMeetingTargets().catch(() => []),
      bridge.getScreenSources ? bridge.getScreenSources().catch(() => []) : Promise.resolve([]),
    ]);
    if (targets.length)  state.meetingTargets = targets;
    if (sources.length)  state.screenSources  = sources;
  } catch (_) {}
  renderMeetingTargets();
}

btnRefresh.addEventListener("click", async () => {
  await refreshTargets();
  channel.postMessage({ type: "REQUEST_STATE" });
});

// Re-pick window: refresh the meeting list and scroll the picker into view so the
// user can re-select the window after capture fell back to following the screen.
if (btnRepick) {
  btnRepick.addEventListener("click", async () => {
    // Ensure we're on the dashboard tab where the picker lives.
    const dashTab = document.querySelector('.tab[data-tab="dashboard"]');
    if (dashTab) dashTab.click();
    await refreshTargets();
    channel.postMessage({ type: "REQUEST_STATE" });
    const picker = document.getElementById("card-picker");
    if (picker) {
      picker.scrollIntoView({ behavior: "smooth", block: "center" });
      picker.classList.add("flash-highlight");
      setTimeout(() => picker.classList.remove("flash-highlight"), 1600);
    }
  });
}

// ─── Audio Mix card (reversible block — delete to roll back) ──────────────────
(function setupAudioMixCard() {
  const slider = document.getElementById("full-mix-volume");
  const label  = document.getElementById("full-mix-volume-label");
  const pill   = document.getElementById("mix-pill");
  const duck   = document.getElementById("full-mix-duck");
  if (!slider || !duck) return;

  // Local cache of the audio-mix state. Source of truth lives in overlay.js
  // (state.userAiVolume / state.autoDuckEnabled); we sync via BroadcastChannel.
  let aiVolume = 1.0;
  let autoDuck = true;
  let suppressEcho = false;   // prevent feedback loop while reflecting incoming state

  function paint() {
    const pct = Math.round(aiVolume * 100);
    slider.value = String(pct);
    label.textContent = `${pct}%`;
    pill.textContent  = `${pct}%`;
    slider.style.setProperty("--mix-pct", `${Math.min(100, pct / 2)}%`);
    duck.classList.toggle("on", !!autoDuck);
    duck.setAttribute("aria-checked", autoDuck ? "true" : "false");
    duck.title = autoDuck
      ? "Auto-duck ON — AI drops to 80% of slider while counterparty speaks. Click to disable."
      : "Auto-duck OFF — AI stays at slider value. Click to enable.";
  }
  paint();

  function send() {
    if (suppressEcho) return;
    channel.postMessage({ type: "COMMAND_SET_AUDIO_MIX", payload: { aiVolume, autoDuck } });
  }

  slider.addEventListener("input", () => {
    aiVolume = Math.max(0, Math.min(2.0, (Number(slider.value) || 0) / 100));
    paint();
    send();
  });
  duck.addEventListener("click", () => {
    autoDuck = !autoDuck;
    paint();
    send();
  });

  // Reflect overlay-side changes (when the user moved the strip in the overlay).
  const prev = channel.onmessage;
  channel.onmessage = (ev) => {
    if (typeof prev === "function") prev(ev);
    const { type, payload } = ev.data || {};
    if (type !== "AUDIO_MIX_STATE" || !payload) return;
    suppressEcho = true;
    if (typeof payload.aiVolume === "number") aiVolume = payload.aiVolume;
    if (typeof payload.autoDuck === "boolean") autoDuck = payload.autoDuck;
    paint();
    suppressEcho = false;
  };
})();

// ─── Language card (reversible block — delete to roll back) ───────────────────
(function setupLanguageCard() {
  const spoken    = document.getElementById("full-lang-spoken");
  const reply     = document.getElementById("full-lang-reply");
  const display   = document.getElementById("full-lang-display");
  const apply     = document.getElementById("full-lang-apply");
  const status    = document.getElementById("full-lang-status");
  const pill      = document.getElementById("lang-pill");
  const sumTrans  = document.getElementById("lang-sum-transcribe");
  const sumReply  = document.getElementById("lang-sum-reply");
  const sumShow   = document.getElementById("lang-sum-display");
  if (!spoken || !apply) return;

  // BCP-47 → friendly name map (kept in sync with the <option> labels).
  const NAMES = {
    "en-US": "English", "en": "English",
    "hi-IN": "Hindi",   "hi": "Hindi",
    "gu-IN": "Gujarati","gu": "Gujarati",
    "es-US": "Spanish", "es": "Spanish",
    "fr-FR": "French",  "fr": "French",
    "de-DE": "German",  "de": "German",
    "it-IT": "Italian", "it": "Italian",
    "ja-JP": "Japanese","ja": "Japanese",
    "zh-CN": "Chinese", "zh": "Chinese",
    "ar":    "Arabic",  "ru": "Russian",
    "pt-BR": "Portuguese","pt": "Portuguese",
    "ta-IN": "Tamil",   "te-IN": "Telugu",
    "bn":    "Bengali", "mr": "Marathi",
  };
  function friendly(code) {
    if (!code) return "";
    return NAMES[code] || NAMES[code.split("-")[0]] || code;
  }

  function pillText(profile, replyLang) {
    if (!profile || profile === "auto_multi") {
      return replyLang ? friendly(replyLang).slice(0,3).toUpperCase() : "AUTO";
    }
    if (profile.startsWith("pinned:")) {
      const code = profile.split(":", 2)[1] || "en-US";
      return (code.split("-")[0] || "EN").toUpperCase();
    }
    return (replyLang || "EN").split("-")[0].toUpperCase();
  }

  function refreshSummary() {
    const profileVal = spoken.value || "auto_multi";
    if (profileVal === "auto_multi") {
      sumTrans.textContent = "Auto detect";
    } else if (profileVal.startsWith("pinned:")) {
      sumTrans.textContent = friendly(profileVal.split(":", 2)[1]);
    }
    sumReply.textContent = reply.value ? friendly(reply.value) : "Same";
    sumShow.textContent  = display.value ? friendly(display.value) : "Same";
  }
  refreshSummary();
  spoken.addEventListener("change", refreshSummary);
  reply.addEventListener("change", refreshSummary);
  display.addEventListener("change", refreshSummary);

  apply.addEventListener("click", () => {
    const profileVal = spoken.value || "auto_multi";
    const payload = { display_language: display.value || null };
    if (profileVal === "auto_multi") {
      payload.profile = "auto_multi";
    } else if (profileVal.startsWith("pinned:")) {
      payload.profile = "pinned";
      payload.pinned_code = profileVal.split(":", 2)[1];
    }
    if (reply.value) payload.response_language = reply.value;
    channel.postMessage({ type: "COMMAND_SET_LANGUAGE", payload });
    status.textContent = "Sent — applying…";
    pill.textContent = pillText(
      payload.profile === "pinned" ? `pinned:${payload.pinned_code}` : "auto_multi",
      reply.value
    );
    refreshSummary();
  });

  // Backend echo via overlay → BroadcastChannel.
  const prev = channel.onmessage;
  channel.onmessage = (ev) => {
    if (typeof prev === "function") prev(ev);
    const { type, payload } = ev.data || {};
    if (type !== "LANGUAGE_ACK") return;
    const p = payload || {};
    if (p.multilang_enabled === false) {
      status.textContent = "Backend flag off — preference saved for next start.";
    } else {
      status.textContent = "Applied · live";
      setTimeout(() => { if (status.textContent === "Applied · live") status.textContent = ""; }, 3000);
    }
    pill.textContent = pillText(p.language_profile, p.language || p.response_language);
  };
})();

// ─── User profile UI ──────────────────────────────────────────────────────────
// Populates the header chip and Settings account card with the signed-in user's
// info from the locally stored auth tokens. Gracefully no-ops if not signed in.

function _initials(email) {
  if (!email) return "?";
  const name = email.split("@")[0];
  const parts = name.split(/[._-]/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

function _shortEmail(email) {
  if (!email) return "";
  if (email.length <= 22) return email;
  const [local, domain] = email.split("@");
  return local.slice(0, 10) + "…@" + domain;
}

async function setupUserProfile() {
  try {
    const auth = await window.companionBridge.getAuth();
    const email = auth?.user?.email || auth?.email || "";
    if (!email) return; // not signed in / dev mode

    const initials = _initials(email);

    // Header chip
    const chip = document.getElementById("user-chip");
    const avatar = document.getElementById("user-avatar");
    const label = document.getElementById("user-label");
    const ddAvatar = document.getElementById("dd-avatar");
    const ddEmail = document.getElementById("dd-email");
    if (chip) chip.style.display = "flex";
    if (avatar) avatar.textContent = initials;
    if (label) label.textContent = _shortEmail(email);
    if (ddAvatar) ddAvatar.textContent = initials;
    if (ddEmail) ddEmail.textContent = email;

    // Settings account card
    const settingsAvatar = document.getElementById("settings-avatar");
    const settingsEmail = document.getElementById("settings-email");
    if (settingsAvatar) settingsAvatar.textContent = initials;
    if (settingsEmail) settingsEmail.textContent = email;

    // Dropdown logout button
    const ddLogout = document.getElementById("btn-logout-dd");
    if (ddLogout) ddLogout.addEventListener("click", handleLogout);

    // Click chip to open/close dropdown (JS toggle, not CSS hover — hover has a
    // gap that closes the dropdown before the user reaches the sign-out button).
    if (chip) {
      chip.addEventListener("click", (e) => {
        // Don't close if clicking inside the dropdown itself
        const dropdown = document.getElementById("user-dropdown");
        if (dropdown && dropdown.contains(e.target)) return;
        chip.classList.toggle("is-open");
      });
    }

    // Close dropdown when clicking anywhere outside the chip
    document.addEventListener("click", (e) => {
      const chipEl = document.getElementById("user-chip");
      if (chipEl && !chipEl.contains(e.target)) {
        chipEl.classList.remove("is-open");
      }
    });

    // Close on Escape key
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        const chipEl = document.getElementById("user-chip");
        if (chipEl) chipEl.classList.remove("is-open");
      }
    });

  } catch (_) { /* not signed in — chip stays hidden */ }
}

async function handleLogout() {
  const btns = [document.getElementById("btn-logout"), document.getElementById("btn-logout-dd")];
  btns.forEach(b => { if (b) { b.disabled = true; b.textContent = "Signing out…"; } });
  try {
    // companion:logout in main.js:
    //   1. Revokes refresh token on backend
    //   2. Clears safeStorage tokens
    //   3. Destroys overlay + full windows
    //   4. Creates the login window
    // This window will be destroyed by step 3 — no need to reload.
    await window.companionBridge.logout();
  } catch (_) {
    // If destroy happened mid-call this may throw — that's fine, window is gone.
    btns.forEach(b => { if (b) { b.disabled = false; b.textContent = "Sign out"; } });
  }
}

// ─── Boot ─────────────────────────────────────────────────────────────────────
window.addEventListener("load", () => {
  renderAll();
  channel.postMessage({ type: "REQUEST_STATE" });
  setTimeout(async () => {
    await refreshTargets();
    channel.postMessage({ type: "REQUEST_STATE" });
  }, 800);
  startReadinessPolling();
  setupUserProfile();
});

// ─── Auth helpers (shared by readiness poll + Settings api()) ────────────────
// JWT is loaded lazily from safeStorage via companionBridge.getAuth().
let _fullAuthTokens = null;
const FULL_SHARED_TOKEN = (window.companionConfig && window.companionConfig.token) || "";

async function _ensureAuthLoaded() {
  if (_fullAuthTokens !== null) return;
  try { _fullAuthTokens = (await window.companionBridge.getAuth()) || false; }
  catch (_) { _fullAuthTokens = false; }
}

async function _getAuthHeader() {
  await _ensureAuthLoaded();
  if (_fullAuthTokens && _fullAuthTokens.access_token) {
    return "Bearer " + _fullAuthTokens.access_token;
  }
  if (FULL_SHARED_TOKEN) return "Bearer " + FULL_SHARED_TOKEN;
  return null;
}

async function _refreshAuth() {
  if (!_fullAuthTokens || !_fullAuthTokens.refresh_token) return false;
  const BACKEND_HTTP = (window.companionConfig && window.companionConfig.http) || "http://localhost:8000";
  try {
    const res = await fetch(BACKEND_HTTP + "/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: _fullAuthTokens.refresh_token }),
    });
    if (!res.ok) { _fullAuthTokens = null; return false; }
    const data = await res.json();
    _fullAuthTokens = { ..._fullAuthTokens, access_token: data.access_token, refresh_token: data.refresh_token };
    await window.companionBridge.setAuth(_fullAuthTokens);
    return true;
  } catch (_) { return false; }
}

// ─── Backend readiness polling (reliable, overlay-independent) ────────────────
// The full window does NOT own the websocket — the overlay does. Relying only on
// the overlay's BroadcastChannel snapshot is fragile (the full window can load
// after the overlay already broadcast "ready", and never hear it). So we ALSO
// poll the backend's /api/ready endpoint directly. A successful response means
// the server is reachable (wsConnected-equivalent); `ready:true` means the AI
// probes finished and it's safe to start.
function startReadinessPolling() {
  const BACKEND_HTTP = (window.companionConfig && window.companionConfig.http) || "http://localhost:8000";
  let stopped = false;

  async function poll() {
    if (stopped) return;
    try {
      // /api/ready is open, but attaching the token is harmless and consistent.
      const authHdr = await _getAuthHeader();
      const headers = authHdr ? { "Authorization": authHdr } : undefined;
      const res = await fetch(BACKEND_HTTP + "/api/ready", { cache: "no-store", headers });
      if (res.ok) {
        const snap = await res.json();
        state.wsConnected = true;
        state.backendReady = Boolean(snap.ready);
        if (snap.status_message) state.backendStatusMessage = snap.status_message;
      } else {
        state.wsConnected = false;
        state.backendReady = false;
        state.backendStatusMessage = "Connecting to the AI server… please wait.";
      }
    } catch (_) {
      // Backend not reachable yet.
      state.wsConnected = false;
      state.backendReady = false;
      state.backendStatusMessage = "Connecting to the AI server… please wait.";
    }
    renderConnectionBanner();
    renderSessionStatus();
    // Poll fast until ready, then slow down to a heartbeat.
    setTimeout(poll, state.backendReady ? 5000 : 1000);
  }

  poll();
  window.addEventListener("beforeunload", () => { stopped = true; });
}

// ═══════════════ Onboarding / How-to guide ═══════════════
// First-launch guidance cards. Dismissible; "Don't show again" persists so the
// user only sees it once unless they re-open it via the Help button.
(function setupOnboarding() {
  const ONBOARDING_KEY = "companion_onboarding_dismissed_v1";
  const overlay   = $("onboarding-overlay");
  const closeBtn  = $("onboarding-close");
  const gotItBtn  = $("onboarding-gotit");
  const dontShow  = $("onboarding-dontshow");
  const helpFab   = $("btn-help");
  if (!overlay) return;

  function dismissed() {
    try { return localStorage.getItem(ONBOARDING_KEY) === "1"; } catch (_) { return false; }
  }
  function open() {
    overlay.classList.remove("hidden");
    if (dontShow) dontShow.checked = dismissed();
  }
  function close() {
    overlay.classList.add("hidden");
    try {
      if (dontShow && dontShow.checked) localStorage.setItem(ONBOARDING_KEY, "1");
      else localStorage.removeItem(ONBOARDING_KEY);
    } catch (_) {}
  }

  closeBtn?.addEventListener("click", close);
  gotItBtn?.addEventListener("click", close);
  helpFab?.addEventListener("click", open);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !overlay.classList.contains("hidden")) close();
  });

  // Auto-show on first launch only.
  if (!dismissed()) open();
})();

// ═══════════════ Settings page (self-contained) ═══════════════
// Talks to the backend REST config API directly. Renderer fetch is allowed; the
// backend CORS layer whitelists the desktop origin. Isolated from the live
// dashboard logic above.
(function setupSettingsPage() {
  const BACKEND_HTTP = (window.companionConfig && window.companionConfig.http) || "http://localhost:8000";
  const SLOT_ORDER = ["live_voice", "reasoning", "fast_text", "vision", "stt"];
  const SLOT_HINTS = {
    live_voice: "Real-time audio for Hold-to-Ask",
    reasoning: "Strategic advice (Pro pre-flight)",
    fast_text: "Extraction, next-move cache, translation",
    vision: "Per-frame screen analysis",
    stt: "Speech-to-text transcription",
  };

  const tabs = Array.from(document.querySelectorAll(".tab"));
  const panelDash = $("tab-dashboard");
  const panelSet = $("tab-settings");
  const providerRows = $("provider-rows");
  const keyRows = $("key-rows");
  const saveBtn = $("btn-settings-save");
  const saveStatus = $("settings-status");
  const refreshBtn = $("btn-providers-refresh");
  const configPathEl = $("advanced-config-path");
  if (!panelSet || !providerRows) return;

  let registry = null;   // { slots: {slot:{label, providers:{pid:{models,source,key_status,supports_custom_model}}}}, providers:{pid:{display_name,...}} }
  let config = null;     // { slots:{slot:{provider,model}}, key_status:{pid:status}, path }
  let loaded = false;

  function setStatus(msg, kind) {
    saveStatus.textContent = msg || "";
    saveStatus.className = "settings-status" + (kind ? " " + kind : "");
  }

  // Auth: attach JWT (or shared token fallback) to gated endpoints.
  // On 401, attempt a token refresh once, then retry the request.
  async function api(path, opts) {
    const makeRequest = async () => {
      const options = { ...(opts || {}) };
      const authHdr = await _getAuthHeader();
      if (authHdr) {
        options.headers = { ...(options.headers || {}), "Authorization": authHdr };
      }
      return fetch(BACKEND_HTTP + path, options);
    };

    let res = await makeRequest();
    if (res.status === 401) {
      // Try refreshing the token once.
      const refreshed = await _refreshAuth();
      if (refreshed) res = await makeRequest();
    }
    if (!res.ok) {
      let detail = "";
      try { detail = (await res.json()).error || ""; } catch (_) {}
      throw new Error(detail || ("HTTP " + res.status));
    }
    return res.json();
  }

  function providerName(pid) {
    return (registry && registry.providers[pid] && registry.providers[pid].display_name) || pid;
  }

  function buildOptions(select, values, selected) {
    select.innerHTML = "";
    for (const v of values) {
      const o = document.createElement("option");
      o.value = v; o.textContent = v;
      if (v === selected) o.selected = true;
      select.appendChild(o);
    }
  }

  function renderProviderRows() {
    providerRows.innerHTML = "";
    for (const slot of SLOT_ORDER) {
      const sdef = registry.slots[slot];
      if (!sdef) continue;
      const provs = sdef.providers || {};
      const provIds = Object.keys(provs);
      const cur = (config.slots && config.slots[slot]) || {};
      const locked = slot === "live_voice"; // Google-only this release

      const row = document.createElement("div");
      row.className = "provider-row" + (locked ? " is-locked" : "");
      row.dataset.slot = slot;

      // label
      const label = document.createElement("div");
      label.className = "provider-slot-label";
      label.innerHTML =
        '<span class="provider-slot-name">' + (sdef.label || slot) + "</span>" +
        '<span class="provider-slot-hint">' + (SLOT_HINTS[slot] || "") + "</span>";
      row.appendChild(label);

      // provider select
      const provSel = document.createElement("select");
      provSel.className = "provider-select";
      provSel.disabled = locked || provIds.length <= 1;
      for (const pid of provIds) {
        const o = document.createElement("option");
        o.value = pid; o.textContent = providerName(pid);
        if (pid === cur.provider) o.selected = true;
        provSel.appendChild(o);
      }
      row.appendChild(provSel);

      // model cell (select + custom input + meta)
      const modelCell = document.createElement("div");
      modelCell.className = "model-cell";
      const modelSel = document.createElement("select");
      modelSel.className = "model-select";
      modelSel.disabled = locked;
      const custom = document.createElement("input");
      custom.className = "custom-model-input";
      custom.type = "text";
      custom.placeholder = "Custom model id…";
      custom.hidden = true;
      const meta = document.createElement("div");
      meta.className = "model-meta";
      const srcTag = document.createElement("span");
      meta.appendChild(srcTag);
      const keyBadge = document.createElement("span");
      meta.appendChild(keyBadge);
      modelCell.appendChild(modelSel);
      modelCell.appendChild(custom);
      modelCell.appendChild(meta);
      row.appendChild(modelCell);

      // spacer (keeps grid 4-col alignment)
      const spacer = document.createElement("div");
      row.appendChild(spacer);

      function paintForProvider(pid) {
        const pdata = provs[pid] || { models: [], source: "fallback", key_status: "missing", supports_custom_model: false };
        const models = pdata.models || [];
        const selModel = (pid === cur.provider && cur.model) ? cur.model : (models[0] || cur.model || "");
        buildOptions(modelSel, models.length ? models : (selModel ? [selModel] : []), selModel);
        // custom model input
        if (pdata.supports_custom_model) {
          custom.hidden = false;
          // if current model isn't in the list, prefill custom
          if (selModel && !models.includes(selModel)) custom.value = selModel;
          else custom.value = "";
        } else {
          custom.hidden = true;
          custom.value = "";
        }
        // source + key tags
        srcTag.className = "source-tag " + (pdata.source === "live" ? "live" : "fallback");
        srcTag.textContent = pdata.source === "live" ? "live" : "offline list";
        keyBadge.className = "key-badge " + (locked ? "locked" : pdata.key_status);
        keyBadge.textContent = locked ? "Google" : (pdata.key_status === "present" ? "key set" : "no key");
      }
      paintForProvider(cur.provider || provIds[0]);

      provSel.addEventListener("change", () => paintForProvider(provSel.value));
      providerRows.appendChild(row);
    }
  }

  function renderKeyRows() {
    keyRows.innerHTML = "";
    const pids = Object.keys(registry.providers);
    for (const pid of pids) {
      const status = (config.key_status && config.key_status[pid]) || "missing";
      const row = document.createElement("div");
      row.className = "key-row";
      row.dataset.provider = pid;

      const name = document.createElement("span");
      name.className = "key-provider-name";
      name.textContent = providerName(pid);
      row.appendChild(name);

      const wrap = document.createElement("div");
      wrap.className = "key-field-wrap";
      const input = document.createElement("input");
      input.className = "key-input";
      input.type = "password";
      input.placeholder = status === "present" ? "•••••••• (saved — type to replace)" : "Paste API key…";
      wrap.appendChild(input);
      row.appendChild(wrap);

      const showBtn = document.createElement("button");
      showBtn.className = "key-show-btn";
      showBtn.type = "button";
      showBtn.textContent = "Show";
      showBtn.addEventListener("click", () => {
        input.type = input.type === "password" ? "text" : "password";
        showBtn.textContent = input.type === "password" ? "Show" : "Hide";
      });
      row.appendChild(showBtn);

      const testBtn = document.createElement("button");
      testBtn.className = "key-test-btn";
      testBtn.type = "button";
      testBtn.textContent = "Test";
      row.appendChild(testBtn);

      const result = document.createElement("span");
      result.className = "key-test-result";
      row.appendChild(result);

      testBtn.addEventListener("click", async () => {
        result.className = "key-test-result pending";
        result.textContent = "Testing…";
        try {
          const body = { provider: pid };
          if (input.value.trim()) body.key = input.value.trim();
          const r = await api("/api/providers/test", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          });
          if (r.ok) {
            result.className = "key-test-result ok";
            result.textContent = "✓ " + (r.latency_ms != null ? r.latency_ms + "ms" : "OK");
          } else {
            result.className = "key-test-result err";
            result.textContent = "✗ " + (r.error ? "failed" : "failed");
            result.title = r.error || "";
          }
        } catch (e) {
          result.className = "key-test-result err";
          result.textContent = "✗ error";
          result.title = String(e);
        }
      });

      keyRows.appendChild(row);
    }
  }

  function collectPatch() {
    const slots = {};
    providerRows.querySelectorAll(".provider-row").forEach((row) => {
      if (row.classList.contains("is-locked")) return; // live_voice not editable
      const slot = row.dataset.slot;
      const provSel = row.querySelector(".provider-select");
      const modelSel = row.querySelector(".model-select");
      const custom = row.querySelector(".custom-model-input");
      const model = (custom && !custom.hidden && custom.value.trim())
        ? custom.value.trim()
        : (modelSel ? modelSel.value : "");
      slots[slot] = { provider: provSel.value, model };
    });
    const keys = {};
    keyRows.querySelectorAll(".key-row").forEach((row) => {
      const input = row.querySelector(".key-input");
      if (input && input.value.trim()) keys[row.dataset.provider] = input.value.trim();
    });
    const settings = {};
    const gb = document.getElementById("google-backend-select");
    if (gb) settings.google_backend = gb.value;
    return { slots, keys, settings };
  }

  async function loadSettings(force) {
    try {
      setStatus("Loading…", "");
      const [reg, cfg] = await Promise.all([
        api(force ? "/api/providers/refresh" : "/api/providers/registry", force ? { method: "POST" } : undefined),
        api("/api/providers/config"),
      ]);
      registry = reg; config = cfg;
      if (configPathEl && cfg.path) configPathEl.textContent = cfg.path;
      const gb = document.getElementById("google-backend-select");
      if (gb && cfg.settings) gb.value = cfg.settings.google_backend || "";
      renderProviderRows();
      renderKeyRows();
      setStatus("", "");
      loaded = true;
    } catch (e) {
      providerRows.innerHTML = '<div class="empty-state">Could not reach backend at ' +
        BACKEND_HTTP + '. Start the backend, then reopen Settings.</div>';
      setStatus("Backend unreachable", "err");
    }
  }

  saveBtn && saveBtn.addEventListener("click", async () => {
    try {
      setStatus("Saving…", "");
      const patch = collectPatch();
      // Phase G — persist locally so the overlay/app WS sends these as a per-session
      // PROVIDER_CONFIG (keys scoped to THIS user's session, no cross-tester clobber).
      try {
        if (window.companionBridge && window.companionBridge.setProviderConfig) {
          await window.companionBridge.setProviderConfig(patch);
        }
      } catch (_err) { /* local persist is best-effort; REST below still applies */ }
      const r = await api("/api/providers/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      config = r.config || config;
      // refresh model lists for any provider whose key changed
      await loadSettings(Object.keys(patch.keys || {}).length > 0);
      setStatus("Saved ✓", "ok");
      setTimeout(() => { if (saveStatus.textContent === "Saved ✓") setStatus("", ""); }, 3000);
    } catch (e) {
      setStatus("Save failed: " + String(e).slice(0, 80), "err");
    }
  });

  refreshBtn && refreshBtn.addEventListener("click", () => loadSettings(true));

  // Tab switching
  function activate(tabName) {
    tabs.forEach((t) => t.classList.toggle("is-active", t.dataset.tab === tabName));
    if (panelDash) panelDash.hidden = tabName !== "dashboard";
    if (panelSet) panelSet.hidden = tabName !== "settings";
    if (tabName === "settings" && !loaded) loadSettings(false);
  }
  tabs.forEach((t) => t.addEventListener("click", () => activate(t.dataset.tab)));

  // ── Logout button (Settings tab) — delegates to shared handleLogout() ──────
  const logoutBtn = $("btn-logout");
  if (logoutBtn) logoutBtn.addEventListener("click", handleLogout);
})();
