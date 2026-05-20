const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");
const { app, BrowserWindow, desktopCapturer, ipcMain, screen, session } = require("electron");

const runtimeRoot = path.join(os.tmpdir(), "balaastra-negotiation-companion");
fs.mkdirSync(path.join(runtimeRoot, "user-data"), { recursive: true });
fs.mkdirSync(path.join(runtimeRoot, "session-data"), { recursive: true });
fs.mkdirSync(path.join(runtimeRoot, "cache"), { recursive: true });
app.setPath("userData", path.join(runtimeRoot, "user-data"));
app.setPath("sessionData", path.join(runtimeRoot, "session-data"));
app.commandLine.appendSwitch("disk-cache-dir", path.join(runtimeRoot, "cache"));

const companionState = {
  meetingBinding: {
    target_id: null,
    window_title: null,
    process_name: null,
    platform_hint: null,
    output_device_id: null,
    output_device_label: null,
    is_bound: false,
  },
  listeningOutput: {
    device_id: null,
    label: null,
  },
  meetingRouteOutput: {
    device_id: null,
    label: null,
  },
  captureHealth: {
    mic_forward_ok: false,
    remote_audio_ok: false,
    frame_capture_ok: false,
    reply_output_ok: false,
    helper_active: false,
    process_loopback_ok: false,
    unsafe_device_loopback: false,
    degraded_reasons: ["virtual_mic_helper_unavailable"],
  },
  holdState: {
    active: false,
    muted_to_meeting: false,
  },
  sessionActive: false,
  selectedDesktopSourceId: null,
};

let overlayWindow = null;
let fullWindow = null;
let globalHoldProcess = null;
let overlayPresentation = "idle";

function inferPlatform(title) {
  const normalized = String(title || "").toLowerCase();
  if (normalized.includes("zoom")) return "zoom";
  if (normalized.includes("google meet") || normalized.includes("meet")) return "google_meet";
  if (normalized.includes("teams") || normalized.includes("microsoft teams")) return "teams";
  return "generic";
}

function isNoiseWindowTitle(title) {
  const normalized = String(title || "").toLowerCase();
  return (
    !normalized ||
    normalized.includes("entire screen") ||
    normalized.includes("negotiation companion") ||
    normalized.includes("meeting sidecar") ||
    normalized.includes("desktop_companion") ||
    normalized.includes("implementation_plan") ||
    normalized.includes("codex") ||
    normalized.includes("file explorer") ||
    normalized.includes("vb-audio thank you page") ||
    normalized.includes("task switching") ||
    normalized.includes("program manager") ||
    normalized.includes("settings")
  );
}

function targetPriority(title) {
  const normalized = String(title || "").toLowerCase();
  let score = 0;
  if (normalized.includes("zoom")) score += 100;
  if (normalized.includes("teams")) score += 100;
  if (normalized.includes("google meet")) score += 100;
  if (normalized.includes("meet")) score += 60;
  if (normalized.includes("call")) score += 35;
  if (normalized.includes("meeting")) score += 35;
  if (normalized.includes("webinar")) score += 30;
  if (normalized.includes("chrome") || normalized.includes("edge") || normalized.includes("firefox")) score += 10;
  return score;
}

async function listMeetingTargets() {
  const sources = await desktopCapturer.getSources({
    types: ["window"],
    thumbnailSize: { width: 0, height: 0 },
    fetchWindowIcons: false,
  });

  return sources
    .filter((source) => source.name && !isNoiseWindowTitle(source.name))
    .map((source) => ({
      target_id: source.id,
      window_title: source.name,
      process_name: null,
      platform_hint: inferPlatform(source.name),
      is_bound: false,
      priority: targetPriority(source.name),
    }))
    .sort((left, right) => {
      if (right.priority !== left.priority) {
        return right.priority - left.priority;
      }
      return left.window_title.localeCompare(right.window_title);
    });
}

function overlayBounds() {
  const workArea = screen.getPrimaryDisplay().workArea;
  const width = 58;
  const height = 58;
  return {
    width,
    height,
    x: workArea.x + workArea.width - width - 12,
    y: workArea.y + 12,
  };
}

function applyOverlayPresentation(mode) {
  if (!overlayWindow || overlayWindow.isDestroyed()) {
    overlayPresentation = mode;
    return { mode: overlayPresentation };
  }

  overlayPresentation = mode || "idle";
  const current = overlayWindow.getBounds();
  let width = 72;
  let height = 72;

  if (overlayPresentation === "menu") {
    width = 380;
    height = 480;
  } else if (overlayPresentation === "captions") {
    width = 360;
    height = 200;
  } else if (overlayPresentation === "listening") {
    width = 300;
    height = 100;
  } else {
    width = 68;
    height = 68;
  }

  overlayWindow.setBounds(
    {
      x: current.x,
      y: current.y,
      width,
      height,
    },
    true
  );

  overlayWindow.webContents.send("companion:overlayPresentation", { mode: overlayPresentation });
  return { mode: overlayPresentation };
}

function createOverlayWindow() {
  const bounds = overlayBounds();
  overlayWindow = new BrowserWindow({
    ...bounds,
    minWidth: bounds.width,
    minHeight: 58,
    maxWidth: 520,
    maxHeight: 320,
    frame: false,
    transparent: true,
    backgroundColor: "#00000000",
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    maximizable: false,
    minimizable: false,
    hasShadow: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  overlayWindow.loadFile(path.join(__dirname, "renderer", "overlay.html"));
  overlayWindow.webContents.once("did-finish-load", () => {
    applyOverlayPresentation(overlayPresentation);
  });
}

function createFullWindow() {
  fullWindow = new BrowserWindow({
    width: 460,
    height: 860,
    minWidth: 420,
    minHeight: 640,
    backgroundColor: "#0d1019",
    title: "Negotiation Companion",
    autoHideMenuBar: true,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  fullWindow.loadFile(path.join(__dirname, "renderer", "full.html"));
  fullWindow.once("ready-to-show", () => {
    fullWindow.show();
    fullWindow.minimize();
  });
}

function openFullWindow() {
  if (!fullWindow || fullWindow.isDestroyed()) {
    createFullWindow();
    return;
  }
  if (fullWindow.isMinimized()) {
    fullWindow.restore();
  } else {
    fullWindow.show();
  }
  fullWindow.focus();
}

function sendGlobalHoldEvent(active, source = "keyboard") {
  if (!overlayWindow || overlayWindow.isDestroyed()) {
    return;
  }
  overlayWindow.webContents.send("companion:globalHoldState", { active, source });
}

function startGlobalHoldListener() {
  if (globalHoldProcess) {
    return;
  }

  const scriptPath = path.join(__dirname, "..", "scripts", "global-hold-listener.ps1");
  globalHoldProcess = spawn(
    "powershell.exe",
    ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", scriptPath],
    {
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    }
  );

  let stdoutBuffer = "";
  globalHoldProcess.stdout.on("data", (chunk) => {
    stdoutBuffer += chunk.toString();
    const lines = stdoutBuffer.split(/\r?\n/);
    stdoutBuffer = lines.pop() || "";
    for (const line of lines) {
      const trimmed = line.trim().toLowerCase();
      // Space key: immediate activation
      if (trimmed === "space_down" || trimmed === "down") {
        sendGlobalHoldEvent(true, "keyboard");
      } else if (trimmed === "space_up" || trimmed === "up") {
        sendGlobalHoldEvent(false, "keyboard");
      // Mouse: 3-second delayed activation
      } else if (trimmed === "mouse_hold_start") {
        sendGlobalHoldEvent(true, "mouse");
      } else if (trimmed === "mouse_up") {
        sendGlobalHoldEvent(false, "mouse");
      }
    }
  });

  globalHoldProcess.on("exit", () => {
    globalHoldProcess = null;
  });
}

function stopGlobalHoldListener() {
  if (!globalHoldProcess) {
    return;
  }
  try {
    globalHoldProcess.kill();
  } catch (_error) {
    // Best effort only.
  }
  globalHoldProcess = null;
}

ipcMain.handle("companion:listMeetingTargets", async () => listMeetingTargets());

ipcMain.handle("companion:bindMeetingTarget", async (_event, binding) => {
  companionState.meetingBinding = {
    ...companionState.meetingBinding,
    ...binding,
    is_bound: true,
  };
  companionState.selectedDesktopSourceId = binding?.target_id || null;
  return companionState.meetingBinding;
});

ipcMain.handle("companion:rebindMeetingTarget", async (_event, binding) => {
  companionState.meetingBinding = {
    ...companionState.meetingBinding,
    ...binding,
    is_bound: true,
  };
  companionState.selectedDesktopSourceId = binding?.target_id || null;
  return companionState.meetingBinding;
});

ipcMain.handle("companion:listAudioDevices", async () => ({ inputs: [], outputs: [] }));

ipcMain.handle("companion:selectListeningOutput", async (_event, output) => {
  companionState.listeningOutput = {
    device_id: output?.device_id || null,
    label: output?.label || null,
  };
  return companionState.listeningOutput;
});

ipcMain.handle("companion:selectMeetingRouteOutput", async (_event, output) => {
  companionState.meetingRouteOutput = {
    device_id: output?.device_id || null,
    label: output?.label || null,
  };
  companionState.meetingBinding.output_device_id = companionState.meetingRouteOutput.device_id;
  companionState.meetingBinding.output_device_label = companionState.meetingRouteOutput.label;
  return companionState.meetingRouteOutput;
});

ipcMain.handle("companion:startCompanionSession", async () => {
  companionState.sessionActive = true;
  return {
    sessionActive: companionState.sessionActive,
    meetingBinding: companionState.meetingBinding,
    listeningOutput: companionState.listeningOutput,
    meetingRouteOutput: companionState.meetingRouteOutput,
    captureHealth: companionState.captureHealth,
  };
});

ipcMain.handle("companion:setHoldToAsk", async (_event, holdState) => {
  companionState.holdState = {
    active: Boolean(holdState?.active),
    muted_to_meeting: Boolean(holdState?.muted_to_meeting),
  };
  return companionState.holdState;
});

ipcMain.handle("companion:setCaptureHealth", async (_event, health) => {
  companionState.captureHealth = {
    ...companionState.captureHealth,
    ...health,
  };
  return companionState.captureHealth;
});

ipcMain.handle("companion:getCaptureHealth", async () => companionState.captureHealth);

ipcMain.handle("companion:endCompanionSession", async () => {
  companionState.sessionActive = false;
  companionState.holdState = {
    active: false,
    muted_to_meeting: false,
  };
  return { sessionActive: false };
});

ipcMain.handle("companion:openFullWindow", async () => {
  openFullWindow();
  return { ok: true };
});

ipcMain.handle("companion:minimizeFullWindow", async () => {
  if (fullWindow && !fullWindow.isDestroyed()) {
    fullWindow.minimize();
  }
  return { ok: true };
});

ipcMain.handle("companion:moveOverlayWindow", async (_event, position) => {
  if (!overlayWindow || overlayWindow.isDestroyed()) {
    return { ok: false };
  }
  overlayWindow.setPosition(
    Math.round(Number(position?.x || 0)),
    Math.round(Number(position?.y || 0)),
    true
  );
  return { ok: true };
});

ipcMain.handle("companion:setOverlayPresentation", async (_event, mode) => applyOverlayPresentation(mode));

ipcMain.handle("companion:getOverlayContrast", async () => {
  try {
    if (!overlayWindow || overlayWindow.isDestroyed()) {
      return { theme: "light", luminance: 0 };
    }

    const bounds = overlayWindow.getBounds();
    const display = screen.getDisplayMatching(bounds);
    const size = display.size;
    const sources = await desktopCapturer.getSources({
      types: ["screen"],
      thumbnailSize: { width: size.width, height: size.height },
      fetchWindowIcons: false,
    });
    const source = sources[0];
    if (!source) {
      return { theme: "light", luminance: 0 };
    }

    const image = source.thumbnail;
    const bitmap = image.toBitmap();
    const sampleStartX = Math.max(0, bounds.x - display.bounds.x + 72);
    const sampleStartY = Math.max(0, bounds.y - display.bounds.y + 8);
    const sampleWidth = Math.min(220, Math.max(32, bounds.width - 84));
    const sampleHeight = Math.min(120, Math.max(32, bounds.height - 16));
    let total = 0;
    let count = 0;

    for (let y = sampleStartY; y < sampleStartY + sampleHeight; y += 4) {
      for (let x = sampleStartX; x < sampleStartX + sampleWidth; x += 4) {
        const idx = (y * size.width + x) * 4;
        const b = bitmap[idx];
        const g = bitmap[idx + 1];
        const r = bitmap[idx + 2];
        total += 0.299 * r + 0.587 * g + 0.114 * b;
        count += 1;
      }
    }

    const luminance = count ? total / count : 0;
    return {
      theme: luminance > 150 ? "dark-text" : "light-text",
      luminance,
    };
  } catch (_error) {
    return { theme: "light-text", luminance: 0 };
  }
});

app.whenReady().then(() => {
  session.defaultSession.setDisplayMediaRequestHandler(
    (_request, callback) => {
      // Wrap callback so it can only be called once even if a code path
      // accidentally hits it twice (e.g. async + catch both firing).
      let _cbFired = false;
      const once = (result) => {
        if (_cbFired) return;
        _cbFired = true;
        callback(result);
      };

      if (!companionState.selectedDesktopSourceId) {
        once({});
        return;
      }

      desktopCapturer
        .getSources({
          types: ["window"],
          thumbnailSize: { width: 0, height: 0 },
          fetchWindowIcons: false,
        })
        .then((sources) => {
          const selected = sources.find(
            (source) => source.id === companionState.selectedDesktopSourceId
          );
          once(selected ? { video: selected, audio: "loopback" } : {});
        })
        .catch(() => once({}));
    },
    { useSystemPicker: false }
  );

  createOverlayWindow();
  createFullWindow();
  startGlobalHoldListener();

  app.on("activate", () => {
    if (!overlayWindow || overlayWindow.isDestroyed()) {
      createOverlayWindow();
    }
    if (!fullWindow || fullWindow.isDestroyed()) {
      createFullWindow();
    }
  });
});

app.on("before-quit", () => {
  stopGlobalHoldListener();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
