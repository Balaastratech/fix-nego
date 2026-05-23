const bridge = window.companionBridge;

const STORAGE_KEY = "negotiation_companion_prefs_v2";
const WINDOW_MODE = {
  COMPACT: "compact",
  EXPANDED: "expanded",
};

const state = {
  ws: null,
  wsReadyPromise: null,
  playbackContext: null,
  playbackDestination: null,
  playbackAudioEl: null,
  micCapture: null,
  meetingCapture: null,
  micForwardAudioEl: null,
  sessionId: null,
  meetingBinding: null,
  listeningOutput: null,
  meetingRouteOutput: null,
  holdActive: false,
  sessionLive: false,
  sessionStarting: false,
  awaitingPrivateReply: false,
  selectedMeetingTarget: null,
  meetingTargets: [],
  audioOutputs: [],
  conversationEntries: [],
  privateEntries: [],
  autoAttachAttempted: false,
  prefs: {
    lastMeetingWindowTitle: null,
    listeningOutputDeviceId: null,
    meetingRouteOutputDeviceId: null,
    windowMode: WINDOW_MODE.COMPACT,
  },
};

const elements = {
  shell: document.getElementById("shell"),
  assistantOrb: document.getElementById("assistant-orb"),
  miniStatus: document.getElementById("mini-status"),
  miniTarget: document.getElementById("mini-target"),
  miniThread: document.getElementById("mini-thread"),
  miniMeetingMenu: document.getElementById("mini-meeting-menu"),
  collapseExpanded: document.getElementById("collapse-expanded"),
  endSession: document.getElementById("end-session"),
  backendStatus: document.getElementById("backend-status"),
  sessionStatus: document.getElementById("session-status"),
  privacyStatus: document.getElementById("privacy-status"),
  fullMeetingButton: document.getElementById("full-meeting-button"),
  fullMeetingMenu: document.getElementById("full-meeting-menu"),
  audioOutputButton: document.getElementById("audio-output-button"),
  audioOutputMenu: document.getElementById("audio-output-menu"),
  virtualOutputButton: document.getElementById("virtual-output-button"),
  virtualOutputMenu: document.getElementById("virtual-output-menu"),
  selectedTargetLabel: document.getElementById("selected-target-label"),
  meetingVideo: document.getElementById("meeting-video"),
  transcriptList: document.getElementById("transcript-list"),
  privateThread: document.getElementById("private-thread"),
  refreshTargets: document.getElementById("refresh-targets"),
  refreshDevices: document.getElementById("refresh-devices"),
  forceStart: document.getElementById("force-start"),
  rebindPreview: document.getElementById("rebind-preview"),
  healthJson: document.getElementById("health-json"),
  runtimeLog: document.getElementById("runtime-log"),
};

const BACKEND_WS_URL = "ws://localhost:8000/ws";

function loadPrefs() {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored) {
      state.prefs = {
        ...state.prefs,
        ...JSON.parse(stored),
      };
    }
  } catch (_error) {
    // Ignore malformed local state.
  }
}

function savePrefs() {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state.prefs));
  } catch (_error) {
    // Ignore storage failures.
  }
}

function log(message, extra) {
  const line = document.createElement("div");
  line.textContent = `[${new Date().toLocaleTimeString()}] ${message}${extra ? ` ${JSON.stringify(extra)}` : ""}`;
  elements.runtimeLog.prepend(line);
}

function setMiniStatus(text) {
  elements.miniStatus.textContent = text;
}

function setExpandedStatus(element, text) {
  element.textContent = text;
}

function describeMeetingTarget(target) {
  if (!target) {
    return "No meeting attached yet";
  }
  return `${target.window_title} (${target.platform_hint})`;
}

function isVirtualRouteDevice(label) {
  const normalized = String(label || "").toLowerCase();
  return (
    normalized.includes("cable input") ||
    normalized.includes("vb-audio") ||
    normalized.includes("voicemeeter input") ||
    normalized.includes("virtual")
  );
}

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function int16BufferFromFloat32(channelData) {
  const out = new Int16Array(channelData.length);
  for (let i = 0; i < channelData.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, channelData[i]));
    out[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return out.buffer;
}

function closeMenus() {
  elements.miniMeetingMenu.classList.add("hidden");
  elements.fullMeetingMenu.classList.add("hidden");
  elements.audioOutputMenu.classList.add("hidden");
  elements.virtualOutputMenu.classList.add("hidden");
}

function setWindowMode(mode) {
  const nextMode = mode === WINDOW_MODE.EXPANDED ? WINDOW_MODE.EXPANDED : WINDOW_MODE.COMPACT;
  elements.shell.className = `shell ${nextMode}`;
  state.prefs.windowMode = nextMode;
  savePrefs();
  bridge.setWindowMode(nextMode).catch(() => {});
  updateOverlayState();
}

function updateOverlayState() {
  elements.shell.classList.toggle("attached", Boolean(state.sessionLive));
  elements.shell.classList.toggle("meeting-picked", Boolean(state.selectedMeetingTarget));
}

function updateTargetUi() {
  const label = describeMeetingTarget(state.selectedMeetingTarget);
  elements.miniTarget.textContent = label;
  elements.selectedTargetLabel.textContent = state.selectedMeetingTarget
    ? state.selectedMeetingTarget.window_title
    : "No meeting attached yet";
  elements.fullMeetingButton.textContent = label;
  updateOverlayState();
}

function renderPicker(menuElement, items, selectedItem, labelFor, onSelect) {
  menuElement.innerHTML = "";
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Nothing available yet.";
    menuElement.appendChild(empty);
    return;
  }

  for (const item of items) {
    const button = document.createElement("button");
    button.type = "button";
    const isSelected =
      (selectedItem?.target_id && selectedItem.target_id === item.target_id) ||
      (selectedItem?.device_id && selectedItem.device_id === item.device_id);
    button.className = `picker-option${isSelected ? " active" : ""}`;
    button.textContent = labelFor(item);
    button.addEventListener("click", () => void onSelect(item));
    menuElement.appendChild(button);
  }
}

function renderMeetingPickers() {
  const onPick = async (target) => {
    state.selectedMeetingTarget = target;
    state.prefs.lastMeetingWindowTitle = target.window_title;
    savePrefs();
    updateTargetUi();
    renderMeetingPickers();
    closeMenus();
    if (!state.sessionLive) {
      await startSession().catch((error) => {
        setMiniStatus("Tap again to attach");
        log("Auto attach failed", { error: String(error) });
      });
    } else {
      await startMeetingCapture().catch((error) => log("Re-attach failed", { error: String(error) }));
    }
  };

  renderPicker(
    elements.miniMeetingMenu,
    state.meetingTargets,
    state.selectedMeetingTarget,
    (target) => `${target.window_title} (${target.platform_hint})`,
    onPick
  );
  renderPicker(
    elements.fullMeetingMenu,
    state.meetingTargets,
    state.selectedMeetingTarget,
    (target) => `${target.window_title} (${target.platform_hint})`,
    onPick
  );
}

function renderOutputPickers() {
  renderPicker(
    elements.audioOutputMenu,
    state.audioOutputs,
    state.listeningOutput,
    (output) => output.label || "Speaker",
    async (output) => {
      state.listeningOutput = output;
      state.prefs.listeningOutputDeviceId = output.device_id;
      savePrefs();
      elements.audioOutputButton.textContent = output.label || "Speaker";
      closeMenus();
      await bridge.selectListeningOutput(output);
      if (state.playbackAudioEl && typeof state.playbackAudioEl.setSinkId === "function") {
        await state.playbackAudioEl.setSinkId(output.device_id).catch(() => {});
      }
      await reportCaptureHealth().catch(() => {});
    }
  );

  renderPicker(
    elements.virtualOutputMenu,
    state.audioOutputs,
    state.meetingRouteOutput,
    (output) => output.label || "Speaker",
    async (output) => {
      state.meetingRouteOutput = output;
      state.prefs.meetingRouteOutputDeviceId = output.device_id;
      savePrefs();
      elements.virtualOutputButton.textContent = output.label || "Speaker";
      closeMenus();
      await bridge.selectMeetingRouteOutput(output);
      await reportCaptureHealth().catch(() => {});
    }
  );
}

function renderMiniThread() {
  elements.miniThread.innerHTML = "";
  const entries = state.privateEntries.slice(-3).reverse();
  if (!entries.length) {
    const empty = document.createElement("div");
    empty.className = "mini-empty";
    empty.textContent = "Private AI questions and replies will appear here.";
    elements.miniThread.appendChild(empty);
    return;
  }

  for (const entry of entries) {
    const bubble = document.createElement("div");
    bubble.className = `mini-bubble ${entry.speaker}`;
    bubble.textContent = entry.text;
    elements.miniThread.appendChild(bubble);
  }
}

function renderFullTranscript() {
  elements.transcriptList.innerHTML = "";
  if (!state.conversationEntries.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "The meeting transcript will appear here after attachment.";
    elements.transcriptList.appendChild(empty);
    return;
  }

  for (const entry of state.conversationEntries.slice().reverse()) {
    const card = document.createElement("div");
    card.className = `transcript-entry ${entry.speaker}`;

    const meta = document.createElement("div");
    meta.className = "entry-meta";
    const who = document.createElement("span");
    who.textContent = entry.speaker === "counterparty" ? "Counterparty" : entry.speaker === "ai" ? "AI" : "User";
    const when = document.createElement("span");
    when.textContent = new Date(entry.timestamp).toLocaleTimeString();
    meta.appendChild(who);
    meta.appendChild(when);

    const body = document.createElement("div");
    body.className = "entry-text";
    body.textContent = entry.text;

    card.appendChild(meta);
    card.appendChild(body);
    elements.transcriptList.appendChild(card);
  }
}

function renderPrivateThread() {
  elements.privateThread.innerHTML = "";
  if (!state.privateEntries.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Hold the orb to ask AI privately.";
    elements.privateThread.appendChild(empty);
    renderMiniThread();
    return;
  }

  for (const entry of state.privateEntries.slice().reverse()) {
    const card = document.createElement("div");
    card.className = `thread-entry ${entry.speaker}`;

    const meta = document.createElement("div");
    meta.className = "entry-meta";
    const who = document.createElement("span");
    who.textContent = entry.speaker === "ai" ? "AI" : "You";
    const when = document.createElement("span");
    when.textContent = new Date(entry.timestamp).toLocaleTimeString();
    meta.appendChild(who);
    meta.appendChild(when);

    const body = document.createElement("div");
    body.className = "entry-text";
    body.textContent = entry.text;

    card.appendChild(meta);
    card.appendChild(body);
    elements.privateThread.appendChild(card);
  }
  renderMiniThread();
}

function pushConversationEntry(entry) {
  state.conversationEntries.push(entry);
  state.conversationEntries = state.conversationEntries.slice(-80);
  renderFullTranscript();
}

function pushPrivateEntry(entry) {
  state.privateEntries.push(entry);
  state.privateEntries = state.privateEntries.slice(-40);
  renderPrivateThread();
}

async function ensurePlayback() {
  if (state.playbackContext) {
    return;
  }

  state.playbackContext = new AudioContext({ sampleRate: 24000, latencyHint: "interactive" });
  state.playbackDestination = state.playbackContext.createMediaStreamDestination();
  state.playbackAudioEl = document.createElement("audio");
  state.playbackAudioEl.autoplay = true;
  state.playbackAudioEl.srcObject = state.playbackDestination.stream;
  if (state.listeningOutput?.device_id && typeof state.playbackAudioEl.setSinkId === "function") {
    await state.playbackAudioEl.setSinkId(state.listeningOutput.device_id).catch(() => {});
  }
  await state.playbackAudioEl.play().catch(() => {});
}

async function playPcmChunk(arrayBuffer) {
  await ensurePlayback();
  const int16 = new Int16Array(arrayBuffer);
  const audioBuffer = state.playbackContext.createBuffer(1, int16.length, 24000);
  const channel = audioBuffer.getChannelData(0);
  for (let i = 0; i < int16.length; i += 1) {
    channel[i] = int16[i] / 32768;
  }
  const source = state.playbackContext.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(state.playbackDestination);
  source.start();
}

function safeSendControl(type, payload) {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    return false;
  }
  state.ws.send(JSON.stringify({ type, payload }));
  return true;
}

function sendControl(type, payload) {
  if (!safeSendControl(type, payload)) {
    throw new Error("Backend WebSocket is not connected");
  }
}

function createPcmCapture(stream, messageType, { flushMs = 1200 } = {}) {
  const ctx = new AudioContext({ sampleRate: 16000, latencyHint: "interactive" });
  const source = ctx.createMediaStreamSource(stream);
  const processor = ctx.createScriptProcessor(4096, 1, 1);
  const chunks = [];
  let segmentStartedAt = null;

  const flush = (isFinal = true) => {
    if (!chunks.length) {
      return;
    }
    const total = chunks.reduce((sum, chunk) => sum + chunk.byteLength, 0);
    const merged = new Uint8Array(total);
    let offset = 0;
    for (const chunk of chunks.splice(0, chunks.length)) {
      merged.set(new Uint8Array(chunk), offset);
      offset += chunk.byteLength;
    }
    safeSendControl(messageType, {
      pcm_base64: arrayBufferToBase64(merged.buffer),
      timestamp_ms: Date.now(),
      started_at_ms: segmentStartedAt || Date.now(),
      utterance_id: `${messageType.toLowerCase()}_${Date.now()}`,
      is_final: isFinal,
    });
    segmentStartedAt = null;
  };

  processor.onaudioprocess = (event) => {
    const channelData = event.inputBuffer.getChannelData(0);
    if (!segmentStartedAt) {
      segmentStartedAt = Date.now();
    }
    chunks.push(int16BufferFromFloat32(channelData));
  };

  source.connect(processor);
  processor.connect(ctx.destination);
  const flushTimer = window.setInterval(() => flush(true), flushMs);

  return {
    stop: async () => {
      window.clearInterval(flushTimer);
      flush(true);
      processor.disconnect();
      source.disconnect();
      stream.getTracks().forEach((track) => track.stop());
      await ctx.close();
    },
  };
}

async function connectBackend() {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    return;
  }
  if (state.wsReadyPromise) {
    return state.wsReadyPromise;
  }

  setExpandedStatus(elements.backendStatus, "Connecting");
  state.wsReadyPromise = new Promise((resolve, reject) => {
    state.ws = new WebSocket(BACKEND_WS_URL);
    state.ws.binaryType = "arraybuffer";

    state.ws.onopen = () => {
      setExpandedStatus(elements.backendStatus, "Connected");
      resolve();
      log("Backend WebSocket connected");
    };

    state.ws.onclose = () => {
      state.wsReadyPromise = null;
      setExpandedStatus(elements.backendStatus, "Disconnected");
      if (!state.sessionLive) {
        setExpandedStatus(elements.sessionStatus, "Idle");
      }
      log("Backend WebSocket closed");
    };

    state.ws.onerror = () => {
      state.wsReadyPromise = null;
      setExpandedStatus(elements.backendStatus, "Error");
      reject(new Error("Backend WebSocket failed"));
    };

    state.ws.onmessage = async (event) => {
      if (event.data instanceof ArrayBuffer) {
        await playPcmChunk(event.data);
        return;
      }

      const message = JSON.parse(event.data);
      if (message.type === "CONNECTION_ESTABLISHED") {
        state.sessionId = message.payload.session_id;
      }
      if (message.type === "SESSION_STARTED") {
        state.sessionLive = true;
        state.sessionStarting = false;
        setExpandedStatus(elements.sessionStatus, "Live");
        setMiniStatus("Listening to both sides");
        updateOverlayState();
      }
      if (message.type === "MEETING_BINDING_UPDATE") {
        state.meetingBinding = message.payload.binding;
      }
      if (message.type === "CAPTURE_HEALTH_UPDATE") {
        elements.healthJson.textContent = JSON.stringify(message.payload.health || message.payload, null, 2);
      }
      if (message.type === "DEGRADED_MODE_UPDATE") {
        const reasons = (message.payload.reasons || []).join(", ") || "Capture degraded";
        elements.healthJson.textContent = JSON.stringify(message.payload, null, 2);
        setMiniStatus(`Need attention: ${reasons}`);
      }
      if (message.type === "TRANSCRIPT_UPDATE") {
        handleTranscriptUpdate(message.payload);
      }
      if (message.type === "AI_RESPONSE") {
        handleTranscriptUpdate({
          speaker: "ai",
          text: message.payload.text,
          timestamp: message.payload.timestamp,
          context: state.awaitingPrivateReply ? "ask_ai" : "advisor",
        });
      }
      if (message.type === "OUTCOME_SUMMARY") {
        state.sessionLive = false;
        state.sessionStarting = false;
        setExpandedStatus(elements.sessionStatus, "Ended");
        setMiniStatus("Session ended");
        updateOverlayState();
      }
    };
  });

  return state.wsReadyPromise;
}

function handleTranscriptUpdate(payload) {
  const entry = {
    speaker: payload.speaker || "ai",
    text: payload.text || "",
    timestamp: payload.timestamp || Date.now(),
    context: payload.context || null,
  };

  if (!entry.text) {
    return;
  }

  const isPrivate = entry.context === "ask_ai" || (entry.speaker === "ai" && state.awaitingPrivateReply);
  if (isPrivate) {
    pushPrivateEntry(entry);
    state.awaitingPrivateReply = false;
    if (entry.speaker === "ai") {
      setMiniStatus("AI replied privately");
    }
    return;
  }

  pushConversationEntry(entry);
  if (entry.speaker === "counterparty") {
    setMiniStatus("Counterparty speaking");
  } else if (entry.speaker === "user") {
    setMiniStatus("You speaking");
  }
}

async function loadMeetingTargets() {
  state.meetingTargets = await bridge.listMeetingTargets();
  const remembered = state.prefs.lastMeetingWindowTitle
    ? state.meetingTargets.find((target) => target.window_title === state.prefs.lastMeetingWindowTitle)
    : null;

  if (remembered) {
    state.selectedMeetingTarget = remembered;
  } else if (
    state.selectedMeetingTarget &&
    state.meetingTargets.some((target) => target.target_id === state.selectedMeetingTarget.target_id)
  ) {
    state.selectedMeetingTarget = state.meetingTargets.find((target) => target.target_id === state.selectedMeetingTarget.target_id);
  } else {
    state.selectedMeetingTarget = state.meetingTargets[0] || null;
  }

  updateTargetUi();
  renderMeetingPickers();
  log("Meeting targets loaded", { count: state.meetingTargets.length });
}

async function loadAudioDevices() {
  const devices = await bridge.listAudioDevices();
  state.audioOutputs = devices.outputs.length ? devices.outputs : [{ device_id: "default", label: "System Default" }];

  const preferredListening = state.audioOutputs.find((item) => item.device_id === state.prefs.listeningOutputDeviceId);
  const preferredRoute = state.audioOutputs.find((item) => item.device_id === state.prefs.meetingRouteOutputDeviceId);

  state.listeningOutput =
    preferredListening ||
    state.audioOutputs.find((item) => !isVirtualRouteDevice(item.label)) ||
    state.audioOutputs[0];
  state.meetingRouteOutput =
    preferredRoute ||
    state.audioOutputs.find((item) => isVirtualRouteDevice(item.label)) ||
    state.audioOutputs[0];

  state.prefs.listeningOutputDeviceId = state.listeningOutput?.device_id || null;
  state.prefs.meetingRouteOutputDeviceId = state.meetingRouteOutput?.device_id || null;
  savePrefs();

  elements.audioOutputButton.textContent = state.listeningOutput?.label || "Auto-selecting speaker";
  elements.virtualOutputButton.textContent = state.meetingRouteOutput?.label || "Auto-selecting VB-CABLE";
  renderOutputPickers();

  if (state.listeningOutput) {
    await bridge.selectListeningOutput(state.listeningOutput);
  }
  if (state.meetingRouteOutput) {
    await bridge.selectMeetingRouteOutput(state.meetingRouteOutput);
  }
}

async function bindSelectedTarget() {
  if (!state.selectedMeetingTarget) {
    throw new Error("Choose the meeting window first");
  }
  state.meetingBinding = await bridge.bindMeetingTarget(state.selectedMeetingTarget);
  safeSendControl("MEETING_BINDING", state.meetingBinding);
}

async function configureMicForward(stream) {
  if (state.micForwardAudioEl) {
    state.micForwardAudioEl.pause();
    state.micForwardAudioEl.srcObject = null;
  }

  const audioEl = document.createElement("audio");
  audioEl.autoplay = true;
  audioEl.srcObject = stream;
  if (state.meetingRouteOutput?.device_id && typeof audioEl.setSinkId === "function") {
    await audioEl.setSinkId(state.meetingRouteOutput.device_id).catch(() => {});
  }
  await audioEl.play().catch((error) => log("Mic forwarding play failed", { error: String(error) }));
  state.micForwardAudioEl = audioEl;
}

async function reportCaptureHealth(overrides = {}) {
  const helperActive = Boolean(state.meetingRouteOutput && isVirtualRouteDevice(state.meetingRouteOutput.label));
  const health = await bridge.setCaptureHealth({
    mic_forward_ok: Boolean(state.micForwardAudioEl),
    remote_audio_ok: Boolean(state.meetingCapture),
    frame_capture_ok: Boolean(state.meetingCapture),
    reply_output_ok: Boolean(state.listeningOutput),
    helper_active: helperActive,
    process_loopback_ok: Boolean(state.meetingCapture?.hasAudioTrack),
    unsafe_device_loopback: false,
    degraded_reasons: helperActive ? [] : ["virtual_mic_helper_unavailable"],
    ...overrides,
  });

  elements.healthJson.textContent = JSON.stringify(health, null, 2);
  setExpandedStatus(elements.privacyStatus, helperActive ? "Virtual mic ready" : "Need VB-CABLE route");
  safeSendControl("CAPTURE_HEALTH", health);
}

async function stopMeetingCapture() {
  if (!state.meetingCapture) {
    return;
  }
  await state.meetingCapture.audio.stop();
  window.clearInterval(state.meetingCapture.frameTimer);
  state.meetingCapture.stream.getTracks().forEach((track) => track.stop());
  state.meetingCapture = null;
  elements.meetingVideo.srcObject = null;
}

async function startMeetingCapture() {
  if (!state.selectedMeetingTarget) {
    throw new Error("Choose the meeting window first");
  }

  await connectBackend();
  await bindSelectedTarget();
  await stopMeetingCapture();

  const stream = await navigator.mediaDevices.getDisplayMedia({
    video: { frameRate: 4 },
    audio: true,
  });

  elements.meetingVideo.srcObject = stream;
  await elements.meetingVideo.play().catch(() => {});

  const hasAudioTrack = stream.getAudioTracks().length > 0;
  state.meetingCapture = {
    stream,
    hasAudioTrack,
    audio: createPcmCapture(stream, "REMOTE_APP_PCM", { flushMs: 1400 }),
    frameTimer: window.setInterval(() => {
      const video = elements.meetingVideo;
      if (video.paused) {
        video.play().catch(() => {});
      }
      if (!video.videoWidth || !video.videoHeight) {
        return;
      }
      const canvas = document.createElement("canvas");
      canvas.width = Math.min(960, video.videoWidth);
      canvas.height = Math.min(540, video.videoHeight);
      const ctx = canvas.getContext("2d");
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const dataUrl = canvas.toDataURL("image/jpeg", 0.65);
      safeSendControl("SCREEN_FRAME", {
        image: dataUrl.split(",")[1],
        timestamp: Date.now(),
      });
    }, 1000),
  };

  const track = stream.getVideoTracks()[0];
  if (track) {
    track.addEventListener("ended", async () => {
      await stopMeetingCapture();
      await reportCaptureHealth({ remote_audio_ok: false, frame_capture_ok: false });
      setMiniStatus("Meeting window detached");
    });
  }

  await reportCaptureHealth({ remote_audio_ok: hasAudioTrack, frame_capture_ok: true });
  setMiniStatus("Meeting attached");
}

async function startSession() {
  if (state.sessionLive || state.sessionStarting) {
    return;
  }
  if (!state.selectedMeetingTarget) {
    throw new Error("Choose the meeting window first");
  }

  state.sessionStarting = true;
  setExpandedStatus(elements.sessionStatus, "Starting");
  setMiniStatus("Attaching to meeting...");

  try {
    await connectBackend();
    await loadAudioDevices();
    await startMeetingCapture();
    await bridge.startCompanionSession();

    const micStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    await configureMicForward(micStream);
    if (state.micCapture) {
      await state.micCapture.stop();
    }
    state.micCapture = createPcmCapture(micStream, "LOCAL_MIC_PCM", { flushMs: 1200 });

    sendControl("START_NEGOTIATION", {
      context: "Desktop companion meeting session",
      source_mode: "virtual_companion_desktop",
      capture_preset: "meeting_window_default",
      companion_quality_mode: "companion_ready",
      meeting_binding: state.meetingBinding,
      selected_output_device: state.listeningOutput,
      user_context: {
        meeting_route_output: state.meetingRouteOutput,
      },
    });

    state.sessionLive = true;
    await reportCaptureHealth({ mic_forward_ok: true });
    setExpandedStatus(elements.sessionStatus, "Live");
    setMiniStatus("Listening to both sides");
    updateOverlayState();
  } catch (error) {
    state.sessionLive = false;
    setExpandedStatus(elements.sessionStatus, "Needs action");
    setMiniStatus("Choose meeting window to attach");
    updateOverlayState();
    throw error;
  } finally {
    state.sessionStarting = false;
  }
}

async function setHoldState(active, source = "orb") {
  if (!state.sessionLive || state.holdActive === active) {
    return;
  }

  state.holdActive = active;
  elements.assistantOrb.classList.toggle("active", active);

  if (state.micForwardAudioEl) {
    state.micForwardAudioEl.muted = active;
  }

  if (!active) {
    state.awaitingPrivateReply = true;
  }

  await bridge.setHoldToAsk({
    active,
    muted_to_meeting: active,
  });
  safeSendControl("HOLD_TO_ASK_STATE", {
    active,
    muted_to_meeting: active,
    source,
  });

  await reportCaptureHealth({ mic_forward_ok: Boolean(state.micForwardAudioEl) });
  setMiniStatus(active ? "Private AI mode active" : "Waiting for private AI reply");
  updateOverlayState();
}

async function endSession() {
  state.sessionLive = false;
  state.sessionStarting = false;
  state.holdActive = false;
  elements.assistantOrb.classList.remove("active");

  if (state.micForwardAudioEl) {
    state.micForwardAudioEl.pause();
    state.micForwardAudioEl.srcObject = null;
    state.micForwardAudioEl = null;
  }
  if (state.micCapture) {
    await state.micCapture.stop();
    state.micCapture = null;
  }
  await stopMeetingCapture();
  await bridge.endCompanionSession();
  safeSendControl("END_NEGOTIATION", {});
  await reportCaptureHealth({ mic_forward_ok: false, remote_audio_ok: false, frame_capture_ok: false });
  setExpandedStatus(elements.sessionStatus, "Idle");
  setMiniStatus("Double-click AI to choose meeting");
  updateOverlayState();
}

async function maybeAutoAttach() {
  if (state.autoAttachAttempted || !state.selectedMeetingTarget || !state.prefs.lastMeetingWindowTitle) {
    return;
  }
  if (state.selectedMeetingTarget.window_title !== state.prefs.lastMeetingWindowTitle) {
    return;
  }
  state.autoAttachAttempted = true;
  window.setTimeout(() => {
    void startSession().catch((error) => log("Auto attach failed", { error: String(error) }));
  }, 300);
}

elements.fullMeetingButton.addEventListener("click", () => {
  elements.fullMeetingMenu.classList.toggle("hidden");
  elements.miniMeetingMenu.classList.add("hidden");
  elements.audioOutputMenu.classList.add("hidden");
  elements.virtualOutputMenu.classList.add("hidden");
});

elements.audioOutputButton.addEventListener("click", () => {
  elements.audioOutputMenu.classList.toggle("hidden");
  elements.fullMeetingMenu.classList.add("hidden");
  elements.miniMeetingMenu.classList.add("hidden");
  elements.virtualOutputMenu.classList.add("hidden");
});

elements.virtualOutputButton.addEventListener("click", () => {
  elements.virtualOutputMenu.classList.toggle("hidden");
  elements.fullMeetingMenu.classList.add("hidden");
  elements.miniMeetingMenu.classList.add("hidden");
  elements.audioOutputMenu.classList.add("hidden");
});

elements.collapseExpanded.addEventListener("click", () => setWindowMode(WINDOW_MODE.COMPACT));
elements.refreshTargets.addEventListener("click", () => void loadMeetingTargets());
elements.refreshDevices.addEventListener("click", () => void loadAudioDevices());
elements.forceStart.addEventListener("click", () => void startSession().catch((error) => log("Manual start failed", { error: String(error) })));
elements.rebindPreview.addEventListener("click", () => void startMeetingCapture().catch((error) => log("Re-attach failed", { error: String(error) })));
elements.endSession.addEventListener("click", () => void endSession().catch((error) => log("End session failed", { error: String(error) })));

elements.assistantOrb.addEventListener("pointerdown", () => void setHoldState(true, "orb"));
elements.assistantOrb.addEventListener("dblclick", (event) => {
  event.preventDefault();
  closeMenus();
  if (state.selectedMeetingTarget && state.sessionLive) {
    setWindowMode(WINDOW_MODE.EXPANDED);
    return;
  }
  elements.miniMeetingMenu.classList.toggle("hidden");
});
elements.assistantOrb.addEventListener("contextmenu", (event) => {
  event.preventDefault();
  if (state.selectedMeetingTarget && !state.sessionLive) {
    elements.miniMeetingMenu.classList.toggle("hidden");
    return;
  }
  setWindowMode(WINDOW_MODE.EXPANDED);
});
elements.miniTarget.addEventListener("click", () => {
  if (!state.sessionLive) {
    elements.miniMeetingMenu.classList.toggle("hidden");
  }
});
window.addEventListener("pointerup", () => {
  if (state.holdActive) {
    void setHoldState(false, "orb");
  }
});
elements.assistantOrb.addEventListener("pointerleave", () => {
  if (state.holdActive) {
    void setHoldState(false, "orb");
  }
});

document.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }
  if (!target.closest(".picker")) {
    closeMenus();
  }
});

bridge.onWindowModeChanged((payload) => {
  const mode = payload?.mode === WINDOW_MODE.EXPANDED ? WINDOW_MODE.EXPANDED : WINDOW_MODE.COMPACT;
  elements.shell.className = `shell ${mode}`;
  state.prefs.windowMode = mode;
  savePrefs();
  updateOverlayState();
});

window.addEventListener("load", async () => {
  loadPrefs();
  const modeInfo = await bridge.getWindowMode().catch(() => ({ mode: state.prefs.windowMode }));
  setWindowMode(modeInfo?.mode || state.prefs.windowMode || WINDOW_MODE.COMPACT);

  renderMiniThread();
  renderFullTranscript();
  renderPrivateThread();
  updateTargetUi();
  updateOverlayState();
  setExpandedStatus(elements.backendStatus, "Connecting");
  setExpandedStatus(elements.sessionStatus, "Idle");
  setExpandedStatus(elements.privacyStatus, "Need VB-CABLE route");
  setMiniStatus("Double-click AI to choose meeting");

  await connectBackend().catch((error) => log("Backend connect failed", { error: String(error) }));
  await loadMeetingTargets();
  await loadAudioDevices();
  await reportCaptureHealth().catch(async () => {
    elements.healthJson.textContent = JSON.stringify(await bridge.getCaptureHealth(), null, 2);
  });
  await maybeAutoAttach();
});
