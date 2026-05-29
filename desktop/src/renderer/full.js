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

// ─── State ────────────────────────────────────────────────────────────────────
const state = {
  sessionLive: false,
  sessionStarting: false,
  sessionPaused: false,
  backendReady: false,
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

  // Disable Start if no target selected or backend not ready
  const canStart = Boolean(state.selectedTarget);
  btnStart.disabled = !canStart;
  btnStart.title = !state.selectedTarget
    ? "Select a meeting window first"
    : !state.backendReady
    ? "Connecting to backend…"
    : "Start session";
  btnPause.disabled = !state.sessionLive || state.sessionPaused || state.sessionStarting;
  btnResume.disabled = !state.sessionPaused;
  btnEnd.disabled = false;
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
  listenLabel.textContent = bannerState === "paused" ? "Paused" : (BANNER_LABELS[bannerState] || BANNER_LABELS.ready);
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
    state.backendReady    = Boolean(payload.backendReady);
    state.holdActive      = Boolean(payload.holdActive);
    state.meetingTitle    = payload.meetingTitle || null;
    state.listeningDeviceId  = payload.listeningDeviceId || null;
    state.vbCableDeviceId    = payload.vbCableDeviceId || null;
    state.privacyStrategy    = payload.privacyStrategy || null;
    state.selectedMicLabel   = payload.selectedMicLabel || null;
    state.orbState = payload.orbState || null;
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
    renderAll();
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

// ─── Boot ─────────────────────────────────────────────────────────────────────
window.addEventListener("load", () => {
  renderAll();
  channel.postMessage({ type: "REQUEST_STATE" });
  setTimeout(async () => {
    await refreshTargets();
    channel.postMessage({ type: "REQUEST_STATE" });
  }, 800);
});
