const { contextBridge, ipcRenderer } = require("electron");

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
  bindMeetingTarget: (binding) => ipcRenderer.invoke("companion:bindMeetingTarget", binding),
  rebindMeetingTarget: (binding) => ipcRenderer.invoke("companion:rebindMeetingTarget", binding),
  listAudioDevices: () => enumerateAudioDevices(),
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
  onGlobalHoldState: (handler) => {
    const listener = (_event, payload) => handler(payload);
    ipcRenderer.on("companion:globalHoldState", listener);
    return () => ipcRenderer.removeListener("companion:globalHoldState", listener);
  },
  onOverlayPresentation: (handler) => {
    const listener = (_event, payload) => handler(payload);
    ipcRenderer.on("companion:overlayPresentation", listener);
    return () => ipcRenderer.removeListener("companion:overlayPresentation", listener);
  },
});
