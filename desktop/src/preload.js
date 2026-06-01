const { contextBridge, ipcRenderer } = require("electron");

// Resolve the backend endpoints once (synchronously) from the main process so
// every renderer (overlay, full) reads the same packaged/dev URL. See main.js
// resolveBackendConfig(). Falls back to localhost only if the IPC is unavailable.
let backendConfig = { ws: "ws://localhost:8000/ws", http: "http://localhost:8000" };
try {
  const resolved = ipcRenderer.sendSync("companion:getBackendConfig");
  if (resolved && resolved.ws) backendConfig = resolved;
} catch (_err) {
  // keep localhost fallback
}
contextBridge.exposeInMainWorld("companionConfig", backendConfig);

async function enumerateAudioDevices() {
  if (!navigator.mediaDevices?.enumerateDevices) {
    return { inputs: [], outputs: [] };
  }

  const devices = await navigator.mediaDevices.enumerateDevices();
  return {
    inputs: devices
      .filter((device) => device.kind === "audioinput")
      .map((device) => ({ device_id: device.deviceId, label: device.label || "Microphone" })),
    outputs: devices
      .filter((device) => device.kind === "audiooutput")
      .map((device) => ({ device_id: device.deviceId, label: device.label || "Speaker" })),
  };
}

contextBridge.exposeInMainWorld("companionBridge", {
  listMeetingTargets: () => ipcRenderer.invoke("companion:listMeetingTargets"),
  getScreenSources: () => ipcRenderer.invoke("companion:getScreenSources"),
  bindMeetingTarget: (binding) => ipcRenderer.invoke("companion:bindMeetingTarget", binding),
  rebindMeetingTarget: (binding) => ipcRenderer.invoke("companion:rebindMeetingTarget", binding),
  getWindowProcessIds: () => ipcRenderer.invoke("companion:getWindowProcessIds"),
  startProcessAudioCapture: (request) => ipcRenderer.invoke("companion:startProcessAudioCapture", request),
  stopProcessAudioCapture: () => ipcRenderer.invoke("companion:stopProcessAudioCapture"),
  listAudioDevices: () => enumerateAudioDevices(),
  // Phase G — per-session BYOK provider config (keys/slots/google_backend)
  getProviderConfig: () => ipcRenderer.invoke("companion:getProviderConfig"),
  setProviderConfig: (cfg) => ipcRenderer.invoke("companion:setProviderConfig", cfg),
  // Auth (Clerk + app-session JWT)
  getAuth: () => ipcRenderer.invoke("companion:getAuth"),
  setAuth: (tokens) => ipcRenderer.invoke("companion:setAuth", tokens),
  clearAuth: () => ipcRenderer.invoke("companion:clearAuth"),
  startLogin: () => ipcRenderer.invoke("companion:startLogin"),
  onLoginUrl: (handler) => {
    const listener = (_event, url) => handler(url);
    ipcRenderer.on("companion:loginUrl", listener);
    return () => ipcRenderer.removeListener("companion:loginUrl", listener);
  },
  logout: () => ipcRenderer.invoke("companion:logout"),
  loginSuccess: () => ipcRenderer.invoke("companion:loginSuccess"),
  selectListeningOutput: (output) => ipcRenderer.invoke("companion:selectListeningOutput", output),
  selectMeetingRouteOutput: (output) => ipcRenderer.invoke("companion:selectMeetingRouteOutput", output),
  startCompanionSession: () => ipcRenderer.invoke("companion:startCompanionSession"),
  setHoldToAsk: (holdState) => ipcRenderer.invoke("companion:setHoldToAsk", holdState),
  setCaptureHealth: (health) => ipcRenderer.invoke("companion:setCaptureHealth", health),
  getCaptureHealth: () => ipcRenderer.invoke("companion:getCaptureHealth"),
  endCompanionSession: () => ipcRenderer.invoke("companion:endCompanionSession"),
  openFullWindow: () => ipcRenderer.invoke("companion:openFullWindow"),
  minimizeFullWindow: () => ipcRenderer.invoke("companion:minimizeFullWindow"),
  setOverlayPresentation: (mode) => ipcRenderer.invoke("companion:setOverlayPresentation", mode),
  getOverlayContrast: () => ipcRenderer.invoke("companion:getOverlayContrast"),
  moveOverlayWindow: (position) => ipcRenderer.invoke("companion:moveOverlayWindow", position),
  onOverlayPresentation: (handler) => {
    const listener = (_event, payload) => handler(payload);
    ipcRenderer.on("companion:overlayPresentation", listener);
    return () => ipcRenderer.removeListener("companion:overlayPresentation", listener);
  },
  onProcessAudioChunk: (handler) => {
    const listener = (_event, chunk) => handler(chunk);
    ipcRenderer.on("companion:processAudioChunk", listener);
    return () => ipcRenderer.removeListener("companion:processAudioChunk", listener);
  },
  onCaptureFollowingScreen: (handler) => {
    const listener = (_event, payload) => handler(payload);
    ipcRenderer.on("companion:captureFollowingScreen", listener);
    return () => ipcRenderer.removeListener("companion:captureFollowingScreen", listener);
  },
  // ── Privacy isolation ──────────────────────────────────────────────────────
  // Resolve strategy once at session start (policyconfig | hotkey | vbcable)
  resolvePrivacyStrategy: (opts) =>
    ipcRenderer.invoke("companion:resolvePrivacyStrategy", opts || {}),
  // Called on Hold-to-Ask press — mutes meeting app mic without a virtual cable
  privacyIsolate: () => ipcRenderer.invoke("companion:privacyIsolate"),
  // Called on Hold-to-Ask release — restores meeting app mic
  privacyRestore: () => ipcRenderer.invoke("companion:privacyRestore"),
});
