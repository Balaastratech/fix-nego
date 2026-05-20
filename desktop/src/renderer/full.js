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
  meetingTargets: [],
  conversationEntries: [],
  privateEntries: [],
  listeningDeviceId: null,
  vbCableDeviceId: null,
};

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

function renderDevices() {
  const hasVb  = Boolean(state.vbCableDeviceId);
  const hasOut = Boolean(state.listeningDeviceId);
  labelMic.textContent = state.sessionLive ? "System default mic" : "Auto on session start";
  dotMic.className = "device-dot" + (state.sessionLive ? " ok" : "");
  labelVbcable.textContent = hasVb ? "CABLE Input (detected ✓)" : "Not found";
  dotVbcable.className = "device-dot" + (hasVb ? " ok" : " err");
  vbcableHint.style.display = hasVb ? "none" : "block";
  labelOutput.textContent = hasOut ? "Headphones / Default" : "Auto on session start";
  dotOutput.className = "device-dot" + (hasOut ? " ok" : "");
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
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "target-btn" +
      (state.selectedTarget?.window_title === t.window_title ? " selected" : "");
    const name = document.createElement("span");
    name.className = "target-name";
    name.textContent = t.window_title;
    const chip = document.createElement("span");
    chip.className = "platform-chip";
    chip.textContent = t.platform_hint;
    btn.appendChild(name);
    btn.appendChild(chip);
    btn.addEventListener("click", () => {
      state.selectedTarget = t;
      state.meetingTitle   = t.window_title;
      renderMeetingTargets();
      renderMeetingStatus();
      renderSessionStatus();
      channel.postMessage({ type: "COMMAND_SELECT_MEETING", payload: { target: t } });
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
  renderEntryList(transcriptList, state.conversationEntries,
    "Transcript appears once the session starts.");
  renderEntryList(privateList, state.privateEntries,
    "Hold Space or hold left mouse for 3 s to talk to AI privately.");
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
    state.listeningDeviceId = payload.listeningDeviceId || null;
    state.vbCableDeviceId   = payload.vbCableDeviceId || null;
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
    state.conversationEntries.push(payload);
    state.conversationEntries = state.conversationEntries.slice(-80);
    renderEntryList(transcriptList, state.conversationEntries, "");
    transcriptCount.textContent = state.conversationEntries.length;
  }

  if (type === "PRIVATE_ENTRY" && payload) {
    state.privateEntries.push(payload);
    state.privateEntries = state.privateEntries.slice(-40);
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
btnRefresh.addEventListener("click", async () => {
  try {
    state.meetingTargets = await bridge.listMeetingTargets();
  } catch (_) {}
  renderMeetingTargets();
  channel.postMessage({ type: "REQUEST_STATE" });
});

// ─── Boot ─────────────────────────────────────────────────────────────────────
window.addEventListener("load", () => {
  renderAll();
  channel.postMessage({ type: "REQUEST_STATE" });
  // Try to get fresh target list
  setTimeout(async () => {
    try { state.meetingTargets = await bridge.listMeetingTargets(); renderMeetingTargets(); } catch (_) {}
    channel.postMessage({ type: "REQUEST_STATE" });
  }, 800);
});
