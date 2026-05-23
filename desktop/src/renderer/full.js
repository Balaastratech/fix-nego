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

// ─── State ────────────────────────────────────────────────────────────────────
const state = {
  sessionLive: false,
  sessionStarting: false,
  holdActive: false,
  meetingTitle: null,
  selectedTarget: null,
  selectedSourceId: null,   // desktop source id matched from getScreenSources
  meetingTargets: [],
  screenSources: [],        // from getScreenSources — has thumbnails
  conversationEntries: [],
  privateEntries: [],
  listeningDeviceId: null,
  vbCableDeviceId: null,
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
  if (state.sessionLive) {
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
  btnStart.style.display  = state.sessionLive ? "none" : "flex";
  btnEnd.style.display    = state.sessionLive ? "flex" : "none";
  btnStart.disabled = !state.selectedTarget || state.sessionLive || state.sessionStarting;
  // Update the card hint so user knows they can click to switch screens mid-session
  const cardHint = document.querySelector("#card-picker .card-hint");
  if (cardHint) {
    cardHint.textContent = state.sessionLive
      ? "Click any screen below to switch capture instantly."
      : "Select your meeting app window. Mic routing, VB-CABLE, and output device are configured automatically.";
  }
}

function renderMeetingStatus() {
  if (state.meetingTitle) {
    dotMeeting.className    = "status-dot dot-green";
    labelMeeting.textContent = state.meetingTitle;
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
  if (!state.sessionLive) {
    listenBanner.classList.add("hidden");
    return;
  }
  listenBanner.classList.remove("hidden");
  let bannerState = "ready";
  if (state.holdActive)          bannerState = "ai";
  else if (orb === "responding") bannerState = "ai";
  else if (orb === "processing") bannerState = "transcribing";
  else if (orb === "listening")  bannerState = "speaking";
  else                           bannerState = "ready";

  listenBanner.setAttribute("data-state", bannerState);
  listenLabel.textContent = BANNER_LABELS[bannerState] || BANNER_LABELS.ready;
}

function renderDevices() {
  const hasVb  = Boolean(state.vbCableDeviceId);
  const hasOut = Boolean(state.listeningDeviceId);
  labelMic.textContent = state.sessionLive
    ? (state.selectedMicLabel || "System default mic")
    : "Auto on session start";
  dotMic.className = "device-dot" + (state.sessionLive ? " ok" : "");
  labelVbcable.textContent = hasVb ? "CABLE Input (detected ✓)" : "Not found";
  dotVbcable.className = "device-dot" + (hasVb ? " ok" : " err");
  vbcableHint.style.display = hasVb ? "none" : "block";
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
        payload: { target: t, source_id: src?.id || t.target_id || null },
      });
    });
    meetingList.appendChild(btn);
  }
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
    when.textContent = new Date(entry.ts || entry.timestamp || Date.now()).toLocaleTimeString();
    hdr.appendChild(who); hdr.appendChild(when);
    const body = document.createElement("div");
    body.className = "entry-text";
    body.textContent = entry.text || "";
    card.appendChild(hdr); card.appendChild(body);
    container.appendChild(card);
  }
}

function renderAll() {
  renderSessionStatus();
  renderMeetingStatus();
  renderDevices();
  renderListenBanner();
  renderEntryList(transcriptList, state.conversationEntries,
    "Transcript appears once the session starts.");
  renderEntryList(privateList, state.privateEntries,
    "Hold the floating AI orb to talk to AI privately.");
  transcriptCount.textContent = state.conversationEntries.length;
  privateCount.textContent    = state.privateEntries.length;
}

// ─── BroadcastChannel from overlay ───────────────────────────────────────────
channel.onmessage = (ev) => {
  const { type, payload } = ev.data || {};

  if (type === "STATE_SNAPSHOT") {
    state.sessionLive     = Boolean(payload.sessionLive);
    state.sessionStarting = Boolean(payload.sessionStarting);
    state.holdActive      = Boolean(payload.holdActive);
    state.meetingTitle    = payload.meetingTitle || null;
    state.listeningDeviceId  = payload.listeningDeviceId || null;
    state.vbCableDeviceId    = payload.vbCableDeviceId || null;
    state.selectedMicLabel   = payload.selectedMicLabel || null;
    state.orbState = payload.orbState || null;
    renderListenBanner();
    if (Array.isArray(payload.meetingTargets) && payload.meetingTargets.length)
      state.meetingTargets = payload.meetingTargets;
    if (Array.isArray(payload.conversationEntries))
      state.conversationEntries = payload.conversationEntries;
    if (Array.isArray(payload.privateEntries))
      state.privateEntries = payload.privateEntries;
    if (state.meetingTitle && !state.selectedTarget)
      state.selectedTarget = state.meetingTargets.find(t => t.window_title === state.meetingTitle) || null;
    renderAll();
  }

  if (type === "CONVERSATION_ENTRY" && payload) {
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
    renderEntryList(privateList, state.privateEntries, "");
    privateCount.textContent = state.privateEntries.length;
  }

  if (type === "DEGRADED" && payload) {
    dotSession.className = "status-dot dot-red";
    labelSession.textContent = `Degraded: ${payload.mode || "capture issue"}`;
  }
};

// ─── Buttons ──────────────────────────────────────────────────────────────────
btnStart.addEventListener("click", () => {
  channel.postMessage({ type: "COMMAND_START_SESSION" });
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

// ─── Boot ─────────────────────────────────────────────────────────────────────
window.addEventListener("load", () => {
  renderAll();
  channel.postMessage({ type: "REQUEST_STATE" });
  setTimeout(async () => {
    await refreshTargets();
    channel.postMessage({ type: "REQUEST_STATE" });
  }, 800);
});
