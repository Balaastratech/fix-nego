const fs = require("fs");
const http = require("http");
const os = require("os");
const path = require("path");
const child_process = require("child_process");
// Load .env from the desktop/ project root (dev only — packaged builds use OS env vars)
require("dotenv").config({ path: path.join(__dirname, "..", ".env") });
const { app, BrowserWindow, desktopCapturer, ipcMain, safeStorage, screen, session, shell } = require("electron");

// ── Backend endpoint resolution (Phase A) ────────────────────────────────────
// Shipped builds default to the hosted production backend. For local dev set
// COMPANION_BACKEND_WS (and optionally COMPANION_BACKEND_HTTP) in desktop/.env.
// HTTP is derived from the WS URL when not given (ws->http, wss->https, drop /ws).
const PROD_BACKEND_WS = "wss://api.balaastratech.com/ws";
function resolveBackendConfig() {
  const ws = (process.env.COMPANION_BACKEND_WS || PROD_BACKEND_WS).trim();
  let http = (process.env.COMPANION_BACKEND_HTTP || "").trim();
  if (!http) {
    http = ws
      .replace(/^wss:\/\//, "https://")
      .replace(/^ws:\/\//, "http://")
      .replace(/\/ws\/?$/, "");
  }
  // Phase C — shared bearer token for a hosted/public backend. Empty by default
  // (localhost dev). When set, renderers append it to the WS URL (?token=) and
  // send it on REST calls (X-Companion-Token). Set COMPANION_SHARED_TOKEN in
  // desktop/.env (dev) or the packaged build's OS env to match the VM's token.
  const token = (process.env.COMPANION_SHARED_TOKEN || "").trim();
  return { ws, http, token };
}
// Synchronous so preload can expose it before any renderer code runs.
ipcMain.on("companion:getBackendConfig", (event) => {
  event.returnValue = resolveBackendConfig();
});

let startAudioCapture = null;
let stopAudioCapture = null;
let getActiveWindowProcessIds = null;
try {
  const processLoopback = require("application-loopback");
  startAudioCapture = processLoopback.startAudioCapture;
  stopAudioCapture = processLoopback.stopAudioCapture;
  getActiveWindowProcessIds = processLoopback.getActiveWindowProcessIds;
} catch (error) {
  console.warn(
    "[ProcessAudio] application-loopback unavailable; remote audio will fail closed:",
    error?.message || error
  );
}

const runtimeRoot = path.join(os.tmpdir(), "balaastra-negotiation-companion");
fs.mkdirSync(path.join(runtimeRoot, "user-data"), { recursive: true });
fs.mkdirSync(path.join(runtimeRoot, "session-data"), { recursive: true });
// Use a fresh cache dir each run to avoid "Unable to move the cache: Access is denied"
// errors on Windows when a previous Electron process still has the old cache locked.
const cacheDir = path.join(runtimeRoot, "cache");
try { fs.rmSync(cacheDir, { recursive: true, force: true }); } catch (_) {}
fs.mkdirSync(cacheDir, { recursive: true });
app.setPath("userData", path.join(runtimeRoot, "user-data"));
app.setPath("sessionData", path.join(runtimeRoot, "session-data"));
app.commandLine.appendSwitch("disk-cache-dir", cacheDir);
// Suppress GPU shader disk-cache errors ("Gpu Cache Creation failed: -2")
app.commandLine.appendSwitch("disable-gpu-shader-disk-cache");
// Use a smaller in-memory cache — avoids cache-move access-denied errors on Windows
app.commandLine.appendSwitch("disk-cache-size", "1");
// Disable renderer background throttling and native Windows window occlusion tracking to prevent screen capture freezing
app.commandLine.appendSwitch("disable-renderer-backgrounding");
app.commandLine.appendSwitch("disable-background-timer-throttling");
app.commandLine.appendSwitch("disable-features", "CalculateNativeWinOcclusion,AllowWgcScreenCapturer,AllowWgcWindowCapturer,WebRtcAllowWgcScreenCapturer,WebRtcAllowWgcWindowCapturer");


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
  selectedDesktopSourceName: null,
  selectedDesktopSourceKind: null,
  // Capture resilience: when the selected window can't be tracked we fall back to
  // capturing its monitor instead of dropping the session. These fields drive the
  // "Following screen" UI note and let us keep re-trying to re-adopt the window.
  captureFollowingScreen: false,
  captureMissCount: 0,
  meetingDisplayId: null,   // display the meeting window was last on (best-effort)
  remoteAudioMode: "none",
  processAudioCapture: {
    pid: null,
    hwnd: null,
  },
};

// ─── Privacy isolation module ─────────────────────────────────────────────────
// Implements driverless per-process mic isolation via IAudioPolicyConfig COM.
// Strategy (resolved once per session):
//   policyconfig  – redirect meeting app's capture stream to a silent endpoint
//   hotkey        – send the meeting app's mute hotkey via SendInput
//   vbcable       – legacy VB-Cable forward mute (renderer-side, unchanged)
//
// Env vars:
//   COMPANION_PRIVACY_MODE = auto | policyconfig | hotkey | vbcable  (default: auto)
//   COMPANION_VBCABLE      = auto | on | off                          (default: auto)

// Resolve helper path: dev = scripts/ sibling of src/, packaged = extraResources/scripts/
const PRIVACY_HELPER_SCRIPT = app.isPackaged
  ? path.join(process.resourcesPath, "scripts", "audio-isolator.ps1")
  : path.join(__dirname, "..", "scripts", "audio-isolator.ps1");
const PRIVACY_RECOVERY_FILE = path.join(runtimeRoot, "privacy-recovery.json");
const PRIVACY_WATCHDOG_MS   = 30000; // auto-restore if hold not released within 30s

// ── Phase G: per-session BYOK provider config (local, plaintext on disk) ─────
// The Settings page writes the user's own keys + slot/model + google_backend
// here; the overlay/app renderer reads it at WS connect and sends it as a
// PROVIDER_CONFIG message scoped to that session. Stored in the user-data dir,
// 0600 perms, NEVER committed and NEVER baked into the build (BYOK rule).
const PROVIDER_CONFIG_FILE = path.join(runtimeRoot, "user-data", "provider-config.json");
function readProviderConfig() {
  try {
    const raw = fs.readFileSync(PROVIDER_CONFIG_FILE, "utf-8");
    const cfg = JSON.parse(raw);
    if (cfg && typeof cfg === "object") {
      return {
        slots: cfg.slots && typeof cfg.slots === "object" ? cfg.slots : {},
        keys: cfg.keys && typeof cfg.keys === "object" ? cfg.keys : {},
        settings: cfg.settings && typeof cfg.settings === "object" ? cfg.settings : {},
      };
    }
  } catch (_err) {
    // missing/unreadable → empty config (pure backend-default behavior)
  }
  return { slots: {}, keys: {}, settings: {} };
}
function writeProviderConfig(cfg) {
  const safe = {
    slots: cfg && cfg.slots && typeof cfg.slots === "object" ? cfg.slots : {},
    keys: cfg && cfg.keys && typeof cfg.keys === "object" ? cfg.keys : {},
    settings: cfg && cfg.settings && typeof cfg.settings === "object" ? cfg.settings : {},
  };
  fs.mkdirSync(path.dirname(PROVIDER_CONFIG_FILE), { recursive: true });
  fs.writeFileSync(PROVIDER_CONFIG_FILE, JSON.stringify(safe, null, 2), { encoding: "utf-8" });
  try { fs.chmodSync(PROVIDER_CONFIG_FILE, 0o600); } catch (_err) { /* best effort on Windows */ }
  return safe;
}
ipcMain.handle("companion:getProviderConfig", async () => readProviderConfig());
ipcMain.handle("companion:setProviderConfig", async (_event, cfg) => writeProviderConfig(cfg || {}));

// ── Auth token store (Phase auth — Clerk + app-session JWT) ──────────────────
// Stored encrypted via Electron safeStorage (OS keychain / Windows Credential
// Manager). Falls back to null when safeStorage is unavailable (CI / headless).
// The blob is { access_token, refresh_token, user: { clerk_sub, email } }.
const AUTH_TOKEN_FILE = path.join(app.getPath("userData"), "auth.enc");

function readAuthTokens() {
  try {
    if (!safeStorage.isEncryptionAvailable()) return null;
    if (!fs.existsSync(AUTH_TOKEN_FILE)) return null;
    const encrypted = fs.readFileSync(AUTH_TOKEN_FILE);
    const decrypted = safeStorage.decryptString(encrypted);
    return JSON.parse(decrypted);
  } catch (_err) {
    return null;
  }
}

function writeAuthTokens(tokens) {
  try {
    if (!safeStorage.isEncryptionAvailable()) return false;
    const encrypted = safeStorage.encryptString(JSON.stringify(tokens));
    fs.writeFileSync(AUTH_TOKEN_FILE, encrypted);
    return true;
  } catch (_err) {
    return false;
  }
}

function clearAuthTokens() {
  try { fs.unlinkSync(AUTH_TOKEN_FILE); } catch (_err) {}
}

ipcMain.handle("companion:getAuth", async () => readAuthTokens());
ipcMain.handle("companion:setAuth", async (_event, tokens) => writeAuthTokens(tokens));
ipcMain.handle("companion:clearAuth", async () => { clearAuthTokens(); return true; });

// ── Loopback OAuth login (Clerk hosted page → token handoff) ─────────────────
// Opens the backend's /auth/login-page in the system browser with a loopback
// redirect URI. A one-shot HTTP server on 127.0.0.1:<PORT> catches the
// ?clerk_token= callback, POSTs it to the backend /auth/exchange, stores the
// resulting app JWT pair, and resolves. All real auth UI lives in Clerk's page.
ipcMain.handle("companion:startLogin", async (event) => {
  return new Promise((resolve, reject) => {
    // Pick a random OS-assigned port.
    const server = http.createServer();
    server.listen(0, "127.0.0.1", () => {
      const port = server.address().port;
      const callbackUrl = `http://127.0.0.1:${port}/callback`;
      const { http: backendHttp } = resolveBackendConfig();
      // Add signout=1 when the user explicitly signed out, so the browser page
      // calls Clerk.signOut() before showing the form (clears the Clerk cookie).
      const signoutParam = _loginForceSignout ? "&signout=1" : "";
      _loginForceSignout = false; // consume the flag — one-shot
      const loginUrl = `${backendHttp}/auth/login-page?redirect=${encodeURIComponent(callbackUrl)}${signoutParam}`;

      // Push URL to the login window immediately — user can copy & paste it
      // into any browser if auto-open didn't work or they prefer another browser.
      try { event.sender.send("companion:loginUrl", loginUrl); } catch (_) {}

      server.on("request", async (req, res) => {
        const url = new URL(req.url, `http://127.0.0.1:${port}`);
        if (url.pathname !== "/callback") {
          res.writeHead(404).end();
          return;
        }

        const clerkToken = url.searchParams.get("clerk_token") || "";
        res.writeHead(200, { "Content-Type": "text/html" });
        res.end(
          "<html><body style='font-family:sans-serif;background:#0f1117;color:#e8e8f0;" +
          "display:flex;align-items:center;justify-content:center;min-height:100vh'>" +
          "<p>Signed in! You can close this tab and return to the app.</p></body></html>"
        );
        server.close();

        if (!clerkToken) {
          reject(new Error("No clerk_token in callback URL"));
          return;
        }

        try {
          // Exchange the Clerk token for our app tokens.
          const exchangeRes = await fetch(`${backendHttp}/auth/exchange`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ clerk_token: clerkToken }),
          });
          if (!exchangeRes.ok) {
            const body = await exchangeRes.json().catch(() => ({}));
            reject(new Error(body.detail || `Exchange failed: ${exchangeRes.status}`));
            return;
          }
          const data = await exchangeRes.json();
          writeAuthTokens({
            access_token: data.access_token,
            refresh_token: data.refresh_token,
            user: data.user || {},
          });
          resolve({ ok: true, user: data.user });
        } catch (err) {
          reject(err);
        }
      });

      shell.openExternal(loginUrl).catch((err) => {
        server.close();
        reject(new Error(`Failed to open browser: ${err.message}`));
      });
    });

    server.on("error", (err) => reject(err));
  });
});

ipcMain.handle("companion:logout", async () => {
  // Step 1: Revoke refresh token on the backend (best-effort).
  const tokens = readAuthTokens();
  if (tokens?.refresh_token) {
    const { http: backendHttp } = resolveBackendConfig();
    try {
      await fetch(`${backendHttp}/auth/logout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: tokens.refresh_token }),
      });
    } catch (_) { /* backend unreachable — token short-lived anyway */ }
  }

  // Step 2: Wipe all locally stored tokens.
  clearAuthTokens();

  // Step 3: Close overlay + full windows, show the login window.
  // This is the full sign-out: no renderer reload tricks, actual window teardown.
  if (overlayWindow && !overlayWindow.isDestroyed()) {
    overlayWindow.destroy();
    overlayWindow = null;
  }
  if (fullWindow && !fullWindow.isDestroyed()) {
    fullWindow.destroy();
    fullWindow = null;
  }
  createLoginWindow({ forceSignout: true });
  return true;
});

const privacyState = {
  strategy:       null,   // "policyconfig" | "hotkey" | "vbcable" | null
  method:         null,   // "existing-disabled" | "disable-spare" | "none" (within policyconfig)
  targetDeviceId: null,   // WASAPI device ID of the silent redirect target
  needsDisable:   false,  // true => target must be disabled via set-visibility during isolate
  listenerName:   null,   // friendly name of the AI-listener mic (excluded from target choice)
  meetingPid:     null,   // resolved PID of the meeting app
  meetingPlatform: null,  // "zoom" | "teams" | "google_meet" | "generic"
  isMuted:        false,
  disabledSpare:  null,   // device id we disabled (so we re-enable on restore/recovery)
  watchdogTimer:  null,
  helperProc:     null,   // persistent PowerShell child process
  helperReady:    false,
  helperQueue:    [],     // { resolve, reject, timeout } waiting for response
  _pendingLine:   "",     // partial stdout buffer
};

// Resolve helper script path; warn once if missing
let _helperScriptExists = null;
function helperScriptExists() {
  if (_helperScriptExists === null) {
    _helperScriptExists = fs.existsSync(PRIVACY_HELPER_SCRIPT);
    if (!_helperScriptExists) {
      console.warn("[Privacy] audio-isolator.ps1 not found at", PRIVACY_HELPER_SCRIPT);
    }
  }
  return _helperScriptExists;
}

// ── Start/stop the persistent PowerShell helper process ──────────────────────
function startPrivacyHelper() {
  if (privacyState.helperProc && !privacyState.helperProc.killed) return;
  if (!helperScriptExists()) return;

  console.log("[Privacy] Starting audio-isolator server...");
  // -Sta is REQUIRED: Windows audio COM objects (MMDeviceEnumerator, AudioPolicyConfigFactory)
  // are registered as apartment-threaded (STA). PowerShell defaults to MTA, which causes
  // CoCreateInstance to fail silently for STA COM servers. Without -Sta, enumerate returns
  // nothing and strategy always falls back to hotkey.
  const proc = child_process.spawn("powershell.exe", [
    "-Sta",
    "-NonInteractive", "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-File", PRIVACY_HELPER_SCRIPT,
  ], { windowsHide: true, stdio: ["pipe", "pipe", "pipe"] });

  privacyState.helperProc  = proc;
  privacyState.helperReady = false;
  privacyState._pendingLine = "";

  proc.stdout.on("data", (chunk) => {
    privacyState._pendingLine += chunk.toString("utf8");
    const lines = privacyState._pendingLine.split(/\r?\n/);
    privacyState._pendingLine = lines.pop(); // keep incomplete last line
    for (const line of lines) {
      if (!line.trim()) continue;
      let parsed;
      try { parsed = JSON.parse(line); } catch (_) {
        console.warn("[Privacy] Non-JSON from helper:", line.slice(0, 200));
        continue;
      }
      if (parsed.ready) {
        privacyState.helperReady = true;
        console.log("[Privacy] Helper ready");
        continue;
      }
      const pending = privacyState.helperQueue.shift();
      if (pending) {
        clearTimeout(pending.timeout);
        pending.resolve(parsed);
      }
    }
  });

  proc.stderr.on("data", (d) =>
    console.warn("[Privacy] helper stderr:", d.toString("utf8").slice(0, 500))
  );

  proc.on("close", (code) => {
    console.log("[Privacy] Helper exited with code", code);
    privacyState.helperProc  = null;
    privacyState.helperReady = false;
    // Reject any pending requests
    for (const p of privacyState.helperQueue) {
      clearTimeout(p.timeout);
      p.reject(new Error(`Helper exited with code ${code}`));
    }
    privacyState.helperQueue = [];
  });

  proc.on("error", (err) => {
    console.error("[Privacy] Helper spawn error:", err.message);
  });
}

function stopPrivacyHelper() {
  if (!privacyState.helperProc || privacyState.helperProc.killed) return;
  try {
    privacyState.helperProc.stdin.write(JSON.stringify({ cmd: "exit" }) + "\n");
  } catch (_) {}
  setTimeout(() => {
    if (privacyState.helperProc && !privacyState.helperProc.killed) {
      privacyState.helperProc.kill();
    }
  }, 1000);
}

// ── Send a command to the persistent helper (returns Promise<response>) ───────
function helperCmd(cmdObj, timeoutMs = 8000) {
  return new Promise((resolve, reject) => {
    if (!privacyState.helperProc || privacyState.helperProc.killed) {
      return reject(new Error("Helper process not running"));
    }
    const timer = setTimeout(() => {
      const idx = privacyState.helperQueue.findIndex(q => q._id === id);
      if (idx !== -1) privacyState.helperQueue.splice(idx, 1);
      reject(new Error(`Helper command timed out: ${cmdObj.cmd}`));
    }, timeoutMs);
    const id = Date.now() + Math.random();
    privacyState.helperQueue.push({ resolve, reject, timeout: timer, _id: id });
    try {
      privacyState.helperProc.stdin.write(JSON.stringify(cmdObj) + "\n");
    } catch (err) {
      clearTimeout(timer);
      privacyState.helperQueue.pop();
      reject(err);
    }
  });
}

// Wait for helper to be ready (up to 8s)
function waitForHelperReady(maxMs = 8000) {
  return new Promise((resolve) => {
    if (privacyState.helperReady) return resolve(true);
    const start = Date.now();
    const poll = setInterval(() => {
      if (privacyState.helperReady) { clearInterval(poll); resolve(true); return; }
      if (Date.now() - start >= maxMs) { clearInterval(poll); resolve(false); }
    }, 50);
  });
}

// ── Hotkey mapping per platform ───────────────────────────────────────────────
function hotkeyForPlatform(platform) {
  switch (String(platform || "").toLowerCase()) {
    case "zoom":        return "alt+a";
    case "teams":       return "ctrl+shift+m";
    case "google_meet": return "ctrl+d";
    default:            return "alt+a";  // Zoom default as fallback
  }
}

// ── Strategy resolution ───────────────────────────────────────────────────────
// HOTKEY is the default/primary (free, legal, no driver, listener-safe — Zoom mutes itself;
// our getUserMedia mic is never touched). redirect-cable is fragile (needs a virtual cable AND
// the meeting app's mic set to "Same as System"), so it is used ONLY when explicitly requested
// via COMPANION_PRIVACY_MODE=redirect-cable|policyconfig. vbcable via =vbcable / COMPANION_VBCABLE=on.
//   COMPANION_PRIVACY_MODE = auto (=hotkey) | hotkey | redirect-cable | policyconfig | vbcable
async function resolvePrivacyStrategy(platform, listenerName) {
  const modeEnv    = (process.env.COMPANION_PRIVACY_MODE || "auto").toLowerCase().trim();
  const vbcableEnv = (process.env.COMPANION_VBCABLE      || "auto").toLowerCase().trim();
  const vbcableAllowed = vbcableEnv !== "off";

  privacyState.listenerName = listenerName || null;

  // Explicit env overrides
  if (modeEnv === "vbcable" || vbcableEnv === "on") {
    console.log("[Privacy] Strategy forced to vbcable via env");
    privacyState.strategy = "vbcable";
    return { strategy: "vbcable", vbcableEnabled: true, reason: "env_forced" };
  }

  // auto (default) and explicit hotkey both resolve to hotkey — the robust primary.
  // redirect-cable is NOT used in auto (too fragile); only via explicit mode below.
  if (modeEnv === "auto" || modeEnv === "hotkey") {
    const hotkey = hotkeyForPlatform(platform);
    console.log(`[Privacy] Strategy: hotkey (${modeEnv === "auto" ? "auto default" : "forced"}) combo=${hotkey}`);
    privacyState.strategy = "hotkey";
    // Helper provides SendInput for the hotkey — start it so it's ready on first hold.
    if (helperScriptExists()) { startPrivacyHelper(); }
    return { strategy: "hotkey", vbcableEnabled: vbcableAllowed, hotkey, reason: modeEnv === "auto" ? "auto_default" : "env_forced" };
  }

  // Explicit redirect-cable / policyconfig: start helper, run probe to pick a cable target
  if (helperScriptExists()) {
    try {
      startPrivacyHelper();
      const ready = await waitForHelperReady(8000);
      if (ready) {
        const ver = await helperCmd({ cmd: "init" }, 6000).catch(() => ({}));
        if (ver && ver.policyVersion && ver.policyVersion !== "none") {
          const probe = await helperCmd(
            { cmd: "probe", listenerDeviceId: "", listenerName: listenerName || "" },
            8000
          );
          if (probe.ok && probe.method && probe.method !== "none" && probe.targetDeviceId) {
            privacyState.strategy       = "policyconfig";
            privacyState.method         = probe.method;
            privacyState.targetDeviceId = probe.targetDeviceId;
            privacyState.needsDisable   = Boolean(probe.needsDisable);
            console.log(`[Privacy] Strategy: policyconfig | method=${probe.method} | target="${probe.targetName}" | needsDisable=${privacyState.needsDisable}`);
            return {
              strategy:        "policyconfig",
              method:          probe.method,
              targetDeviceId:  probe.targetDeviceId,
              targetName:      probe.targetName,
              needsDisable:    privacyState.needsDisable,
              vbcableEnabled:  vbcableAllowed,
              policyVersion:   ver.policyVersion,
              reason:          "probe_selected",
            };
          }
          console.warn("[Privacy] probe found no usable silent target (single-mic?) — hotkey safety net");
        } else {
          console.warn("[Privacy] IAudioPolicyConfig unavailable (policyVersion=none) — hotkey safety net");
        }
      } else {
        console.warn("[Privacy] helper not ready — hotkey safety net");
      }
    } catch (err) {
      console.warn("[Privacy] policyconfig resolution failed:", err.message, "— hotkey safety net");
    }
  }

  // Only reached when policyconfig is genuinely impossible on this machine
  // (no helper, COM unavailable, or single-mic with no spare). Surface hotkey, not silent.
  const hotkey = hotkeyForPlatform(platform);
  console.log("[Privacy] Strategy: hotkey (", hotkey, ") — policyconfig unavailable on this machine");
  privacyState.strategy = "hotkey";
  return {
    strategy:       "hotkey",
    hotkey,
    vbcableEnabled: vbcableAllowed,
    reason:         "policyconfig_unavailable",
  };
}

// ── Recovery marker: persist redirect + disabled-spare to survive crashes ─────
function writeRecoveryMarker(pid, disabledSpare) {
  try {
    fs.writeFileSync(PRIVACY_RECOVERY_FILE, JSON.stringify({
      pid, disabledSpare: disabledSpare || null, timestamp: Date.now(),
    }), "utf8");
  } catch (err) {
    console.warn("[Privacy] writeRecoveryMarker failed:", err.message);
  }
}

function clearRecoveryMarker() {
  try { fs.unlinkSync(PRIVACY_RECOVERY_FILE); } catch (_) {}
}

// On startup: clear any redirect AND re-enable any device we left disabled in a prior crash.
async function recoverStaleRedirect() {
  let marker;
  try {
    const raw = fs.readFileSync(PRIVACY_RECOVERY_FILE, "utf8");
    marker = JSON.parse(raw);
  } catch (_) { return; }

  if (!marker || (!marker.pid && !marker.disabledSpare)) { clearRecoveryMarker(); return; }

  const age = Date.now() - (marker.timestamp || 0);
  console.warn(`[Privacy] Found stale marker (pid=${marker.pid}, disabledSpare=${marker.disabledSpare}, age=${Math.round(age/1000)}s). Repairing...`);

  if (!helperScriptExists()) { clearRecoveryMarker(); return; }
  try {
    startPrivacyHelper();
    const ready = await waitForHelperReady(6000);
    if (ready) {
      await helperCmd({ cmd: "init" }, 5000).catch(() => {});
      if (marker.pid) {
        const r = await helperCmd({ cmd: "restore", pid: marker.pid }, 5000).catch(e => ({ ok: false, error: e.message }));
        console.log("[Privacy] Stale redirect restore:", r.ok ? "ok" : r.error);
      }
      if (marker.disabledSpare) {
        const v = await helperCmd({ cmd: "set-visibility", deviceId: marker.disabledSpare, visible: 1 }, 5000).catch(e => ({ ok: false, error: e.message }));
        console.log("[Privacy] Stale spare re-enable:", v.ok ? "ok" : v.error);
      }
    }
  } catch (err) {
    console.warn("[Privacy] Stale repair failed:", err.message);
  }
  clearRecoveryMarker();
}

// ── Perform isolate (on hold press) ──────────────────────────────────────────
async function performPrivacyIsolate() {
  if (privacyState.isMuted) return { ok: true, alreadyMuted: true };
  const { strategy, method, targetDeviceId, needsDisable } = privacyState;
  const pid      = privacyState.meetingPid;
  const platform = privacyState.meetingPlatform;

  if (strategy === "policyconfig") {
    if (!pid) {
      console.warn("[Privacy] isolate: no meeting PID — runtime hotkey safety net");
      return performHotkeyMute(hotkeyForPlatform(platform), true);
    }
    try {
      // LISTENER-SAFE: redirect ONLY the meeting app's process to the virtual-cable
      // capture endpoint (silent because nothing feeds the cable's input). We do NOT
      // disable any device — disabling changes the system default and kills the AI
      // listener's getUserMedia stream. The user's mic is never touched.
      const result = await helperCmd({ cmd: "redirect", pid, deviceId: targetDeviceId }, 5000);
      if (!result.ok) {
        console.warn("[Privacy] redirect failed:", result.error, "— hotkey safety net");
        return performHotkeyMute(hotkeyForPlatform(platform), true);
      }

      privacyState.isMuted = true;
      writeRecoveryMarker(pid, null);   // no disabled device to recover
      startWatchdog();
      return { ok: true, strategy: "policyconfig", method, pid };
    } catch (err) {
      console.warn("[Privacy] isolate error:", err.message, "— hotkey safety net");
      if (privacyState.disabledSpare) {
        await helperCmd({ cmd: "set-visibility", deviceId: privacyState.disabledSpare, visible: 1 }, 5000).catch(() => {});
        privacyState.disabledSpare = null;
      }
      return performHotkeyMute(hotkeyForPlatform(platform), true);
    }
  }

  if (strategy === "hotkey") {
    return performHotkeyMute(privacyState.hotkey || hotkeyForPlatform(platform), true);
  }

  return { ok: false, strategy, reason: "no_action_needed" };
}

// ── Perform restore (on hold release) ────────────────────────────────────────
async function performPrivacyRestore() {
  if (!privacyState.isMuted && privacyState.strategy !== "hotkey") {
    return { ok: true, alreadyRestored: true };
  }
  const { strategy, hotkey } = privacyState;
  const pid      = privacyState.meetingPid;
  const platform = privacyState.meetingPlatform;

  stopWatchdog();

  if (strategy === "policyconfig" && pid) {
    let helperOk = false;
    try {
      const result = await helperCmd({ cmd: "restore", pid }, 5000);
      helperOk = result.ok;
    } catch (err) {
      console.warn("[Privacy] restore redirect error:", err.message);
    }
    // Re-enable any spare we disabled (must always run, even if restore threw)
    if (privacyState.disabledSpare) {
      try {
        await helperCmd({ cmd: "set-visibility", deviceId: privacyState.disabledSpare, visible: 1 }, 5000);
      } catch (err) {
        console.warn("[Privacy] re-enable spare error:", err.message);
      }
      privacyState.disabledSpare = null;
    }
    privacyState.isMuted = false;
    clearRecoveryMarker();
    return { ok: true, strategy: "policyconfig", pid, helperOk };
  }

  if (strategy === "hotkey") {
    return performHotkeyMute(hotkey || hotkeyForPlatform(platform), false);
  }

  privacyState.isMuted = false;
  clearRecoveryMarker();
  return { ok: true, strategy };
}

// Send the meeting app's mute-toggle hotkey via the proven C# SendInput helper.
// `desired` is the intended mute state for THIS call (true = muting on hold, false =
// unmuting on release). We update privacyState.isMuted to that explicit value rather than
// blind-toggling, so state stays deterministic across rapid holds. The hotkey itself is a
// toggle in the meeting app, so this is correct as long as the meeting app started unmuted
// (normal talking) — which is the expected case.
async function performHotkeyMute(combo, desired) {
  // Auto-(re)start the helper if it isn't running (it can take a few seconds to
  // boot, or may have died) so the FIRST hold doesn't silently no-op.
  if (helperScriptExists() && (!privacyState.helperProc || privacyState.helperProc.killed)) {
    console.warn("[Privacy] hotkey: helper not running — starting it now");
    startPrivacyHelper();
    await waitForHelperReady(4000).catch(() => {});
  }
  if (!helperScriptExists() || !privacyState.helperProc || privacyState.helperProc.killed) {
    console.warn("[Privacy] hotkey: helper unavailable; cannot send", combo);
    return { ok: false, strategy: "hotkey", combo, reason: "helper_unavailable" };
  }
  try {
    console.log(`[Privacy] hotkey send-keys combo=${combo} desired=${desired}`);
    const r = await helperCmd({ cmd: "send-keys", combo }, 3000);
    console.log("[Privacy] hotkey send-keys result:", JSON.stringify(r));
    if (typeof desired === "boolean") {
      privacyState.isMuted = desired;
    } else {
      privacyState.isMuted = !privacyState.isMuted;
    }
    return { ok: Boolean(r && r.ok), strategy: "hotkey", combo, muted: privacyState.isMuted };
  } catch (err) {
    console.warn("[Privacy] hotkey send-keys failed:", err.message);
    return { ok: false, strategy: "hotkey", combo, reason: err.message };
  }
}

// ── Watchdog: auto-restore if hold not released within 30s ───────────────────
function startWatchdog() {
  stopWatchdog();
  privacyState.watchdogTimer = setTimeout(async () => {
    if (privacyState.isMuted) {
      console.warn("[Privacy] Watchdog: auto-restoring mic after", PRIVACY_WATCHDOG_MS, "ms");
      await performPrivacyRestore().catch(() => {});
    }
  }, PRIVACY_WATCHDOG_MS);
}

function stopWatchdog() {
  if (privacyState.watchdogTimer) {
    clearTimeout(privacyState.watchdogTimer);
    privacyState.watchdogTimer = null;
  }
}

// ── Resolve meeting PID from HWND ─────────────────────────────────────────────
async function resolveMeetingPid(hwnd) {
  if (!hwnd || !helperScriptExists()) return null;
  try {
    startPrivacyHelper();
    const ready = await waitForHelperReady(4000);
    if (!ready) return null;
    const result = await helperCmd({ cmd: "pid-from-hwnd", hwnd: String(hwnd) }, 3000);
    return result.ok ? result.pid : null;
  } catch (err) {
    console.warn("[Privacy] resolveMeetingPid failed:", err.message);
    return null;
  }
}

// End of privacy module
// ─────────────────────────────────────────────────────────────────────────────

let overlayWindow = null;
let fullWindow = null;
let overlayPresentation = "idle";
let activeProcessCapturePid = null;

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
    normalized.includes("program manager")
  );
}

function setRemoteAudioMode(mode) {
  if (mode === "display_loopback" || mode === "process_loopback" || mode === "none") {
    companionState.remoteAudioMode = mode;
    return;
  }
  companionState.remoteAudioMode = "none";
}

function stopRemoteProcessCapture() {
  if (stopAudioCapture && activeProcessCapturePid !== null) {
    try {
      stopAudioCapture(String(activeProcessCapturePid));
    } catch (error) {
      console.warn("[ProcessAudio] stopAudioCapture failed:", error?.message || error);
    }
  }
  activeProcessCapturePid = null;
  companionState.processAudioCapture = {
    pid: null,
    hwnd: null,
  };
  if (companionState.remoteAudioMode === "process_loopback") {
    setRemoteAudioMode("none");
  }
}

function parseWindowHandleFromSourceId(sourceId) {
  const value = String(sourceId || "");
  const match = /^window:([^:]+):/i.exec(value);
  return match ? match[1] : null;
}

function normalizeHandle(value) {
  const raw = String(value ?? "").trim();
  if (!raw) return null;
  try {
    if (/^0x/i.test(raw)) return BigInt(raw).toString();
    if (/^\d+$/.test(raw)) return BigInt(raw).toString();
  } catch (_) {}
  return raw.toLowerCase();
}

function resolveDisplaySource(sources) {
  const exactId = companionState.selectedDesktopSourceId;
  if (!Array.isArray(sources) || !sources.length) {
    return null;
  }
  if (exactId) {
    const selected = sources.find((source) => source.id === exactId);
    if (selected) {
      return selected;
    }
  }

  const selectedName = String(companionState.selectedDesktopSourceName || "").trim().toLowerCase();
  const selectedKind = String(companionState.selectedDesktopSourceKind || "").trim().toLowerCase();
  if (selectedName) {
    const byNameKind = sources.find((source) => {
      const kindMatches = !selectedKind || selectedKind === "unknown" || source.id.startsWith(`${selectedKind}:`);
      return kindMatches && String(source.name || "").trim().toLowerCase() === selectedName;
    });
    if (byNameKind) {
      return byNameKind;
    }
  }

  const targetHandle = normalizeHandle(parseWindowHandleFromSourceId(exactId));
  if (targetHandle) {
    const byHandle = sources.find(
      (source) => normalizeHandle(parseWindowHandleFromSourceId(source.id)) === targetHandle
    );
    if (byHandle) {
      return byHandle;
    }
  }

  const meetingTitle = String(companionState.meetingBinding.window_title || "").trim().toLowerCase();
  if (meetingTitle) {
    const byMeetingTitle = sources.find(
      (source) => String(source.name || "").trim().toLowerCase() === meetingTitle
    );
    if (byMeetingTitle) {
      return byMeetingTitle;
    }
  }

  // ── Fuzzy meeting-window match ──────────────────────────────────────────────
  // The exact id/name can change when the meeting app swaps windows (e.g. a
  // browser opening a new window, or the title gaining a "(3)" unread badge / a
  // call timer). Match on the normalized title (volatile suffixes stripped), and
  // for known meeting apps prefer the highest-priority meeting window present.
  const wantNorm = normalizeTitleForMatch(companionState.selectedDesktopSourceName || meetingTitle);
  const windowSources = sources.filter((s) => String(s.id).startsWith("window:"));
  if (wantNorm) {
    const byFuzzy = windowSources.find((source) => {
      const got = normalizeTitleForMatch(source.name);
      return got && (got === wantNorm || got.startsWith(wantNorm) || wantNorm.startsWith(got));
    });
    if (byFuzzy) {
      return byFuzzy;
    }
  }
  const boundPlatform = inferPlatform(companionState.meetingBinding.window_title || companionState.selectedDesktopSourceName || "");
  if (boundPlatform && boundPlatform !== "generic") {
    // The meeting app is a known platform; re-adopt its current top window even if
    // the handle/title changed (covers the PID/window-swap case from the logs).
    const candidates = windowSources
      .filter((s) => !isNoiseWindowTitle(s.name))
      .map((s) => ({ s, score: targetPriority(s.name) }))
      .filter((c) => c.score > 0 && inferPlatform(c.s.name) === boundPlatform)
      .sort((a, b) => b.score - a.score);
    if (candidates.length) {
      return candidates[0].s;
    }
  }
  return null;
}

// Strip volatile parts of a window title so a moved/renamed window still matches:
// unread badges "(3)", leading counts "5 • ", trailing call timers "00:12:34",
// and "- N new messages" suffixes.
function normalizeTitleForMatch(title) {
  let t = String(title || "").toLowerCase().trim();
  if (!t) return "";
  t = t.replace(/\(\d+\)/g, " ");                       // (3)
  t = t.replace(/\b\d{1,2}:\d{2}(?::\d{2})?\b/g, " ");   // call timers
  t = t.replace(/[-–—]\s*\d+\s*(new\s*)?(messages?|notifications?|unread).*/i, " ");
  t = t.replace(/^\s*\d+\s*[•·\-–—]\s*/, " ");           // leading "5 • "
  t = t.replace(/\s+/g, " ").trim();
  return t;
}

// Pick a screen (monitor) source as a capture fallback when the selected window
// can't be tracked. Best-effort prefers the display the window was last on
// (companionState.meetingDisplayId), then the primary display, then any screen.
// Windows note: desktopCapturer screen sources often have an empty display_id, so
// we degrade gracefully to the primary/first screen rather than failing.
function pickScreenSource(sources) {
  const screens = (sources || []).filter((s) => String(s.id).startsWith("screen:"));
  if (!screens.length) return null;
  const wantDisplay = companionState.meetingDisplayId != null ? String(companionState.meetingDisplayId) : null;
  if (wantDisplay) {
    const byDisplay = screens.find((s) => String(s.display_id || "") === wantDisplay);
    if (byDisplay) return byDisplay;
  }
  try {
    const primaryId = String(screen.getPrimaryDisplay().id);
    const byPrimary = screens.find((s) => String(s.display_id || "") === primaryId);
    if (byPrimary) return byPrimary;
  } catch (_) {}
  // "Entire screen" / first screen as the final safe default.
  return screens.find((s) => /entire screen|screen 1|primary/i.test(s.name || "")) || screens[0];
}

// Update the "following screen" capture state and push it to the overlay renderer
// (which relays to the full window via BroadcastChannel) only when it changes.
function setCaptureFollowingScreen(following) {
  following = !!following;
  if (companionState.captureFollowingScreen === following) return;
  companionState.captureFollowingScreen = following;
  if (overlayWindow && !overlayWindow.isDestroyed()) {
    try {
      overlayWindow.webContents.send("companion:captureFollowingScreen", {
        following_screen: following,
        window_title: companionState.meetingBinding.window_title || companionState.selectedDesktopSourceName || null,
      });
    } catch (_) {}
  }
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
  let width = 80;
  let height = 80;

  if (overlayPresentation === "menu") {
    width = 440;
    height = 540;
  } else if (overlayPresentation === "picker") {
    width = 680;
    height = 520;
  } else if (overlayPresentation === "panel") {
    width = 350;
    height = 380;
  } else if (overlayPresentation === "captions") {
    width = 380;
    height = 280;
  } else if (overlayPresentation === "compact") {
    width = 80;
    height = 236;
  } else if (overlayPresentation === "listening") {
    width = 380;
    height = 180;
  } else {
    width = 80;
    height = 80;
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
    maxWidth: 700,
    maxHeight: 600,
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
      backgroundThrottling: false,
    },
  });
  
  // Make it stay visible across all virtual desktops / workspaces:
  overlayWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  
  // Set always on top level to be screen-saver to overlap full screen apps like Zoom:
  overlayWindow.setAlwaysOnTop(true, "screen-saver", 1);
  
  overlayWindow.loadFile(path.join(__dirname, "renderer", "overlay.html"));
  overlayWindow.webContents.once("did-finish-load", () => {
    applyOverlayPresentation(overlayPresentation);
  });
}

function createFullWindow() {
  fullWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 960,
    minHeight: 600,
    backgroundColor: "#0d1019",
    title: "Negotiation Companion",
    autoHideMenuBar: true,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false,
    },
  });
  fullWindow.loadFile(path.join(__dirname, "renderer", "full.html"));
  fullWindow.once("ready-to-show", () => {
    fullWindow.maximize();
    fullWindow.show();
    fullWindow.minimize();
  });
}

// ── Login window (shown when no valid auth tokens are stored) ─────────────────
let loginWindow = null;

// forceSignout: true when opening login after an explicit sign-out — tells the
// browser page to call Clerk.signOut() before showing the form so the previous
// Clerk browser session doesn't auto-sign the user back in silently.
let _loginForceSignout = false;

function createLoginWindow(opts = {}) {
  _loginForceSignout = Boolean(opts.forceSignout);
  if (loginWindow && !loginWindow.isDestroyed()) {
    loginWindow.focus();
    return;
  }
  loginWindow = new BrowserWindow({
    width: 480,
    height: 640,
    resizable: false,
    maximizable: false,
    title: "Sign in — Balaastra Companion",
    autoHideMenuBar: true,
    backgroundColor: "#0f1117",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  loginWindow.loadFile(path.join(__dirname, "renderer", "login.html"));
  loginWindow.on("closed", () => { loginWindow = null; _loginForceSignout = false; });
}

// Called by the login renderer (via IPC) after a successful login exchange.
ipcMain.handle("companion:loginSuccess", async () => {
  if (loginWindow && !loginWindow.isDestroyed()) {
    loginWindow.close();
  }
  createOverlayWindow();
  createFullWindow();
  return true;
});

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
  fullWindow.maximize();
  fullWindow.focus();
}

ipcMain.handle("companion:listMeetingTargets", async () => listMeetingTargets());

// Screen/window picker — returns sources with 320×180 thumbnails as base64 PNG.
// Screens are listed first (stable WGC surface); windows are secondary.
// The renderer shows these as a clickable grid so the user can confirm what they're capturing.
ipcMain.handle("companion:getScreenSources", async () => {
  try {
    const [screens, windows] = await Promise.all([
      desktopCapturer.getSources({
        types: ["screen"],
        thumbnailSize: { width: 320, height: 180 },
        fetchWindowIcons: false,
      }),
      desktopCapturer.getSources({
        types: ["window"],
        thumbnailSize: { width: 320, height: 180 },
        fetchWindowIcons: false,
      }),
    ]);
    const mapSource = (s, kind) => ({
      id: s.id,
      name: s.name,
      kind,                               // "screen" | "window"
      thumbnail: s.thumbnail.toDataURL(), // base64 PNG, ready for <img src>
    });
    return [
      ...screens.map((s) => mapSource(s, "screen")),
      ...windows
        .filter((s) => s.name && !isNoiseWindowTitle(s.name))
        .map((s) => mapSource(s, "window")),
    ];
  } catch (err) {
    console.error("[IPC] getScreenSources error:", err.message);
    return [];
  }
});

ipcMain.handle("companion:bindMeetingTarget", async (_event, binding) => {
  companionState.meetingBinding = {
    ...companionState.meetingBinding,
    ...binding,
    is_bound: true,
  };
  companionState.selectedDesktopSourceId = binding?.source_id || binding?.target_id || null;
  companionState.selectedDesktopSourceName = binding?.source_name || null;
  companionState.selectedDesktopSourceKind = binding?.source_kind || null;

  // Resolve meeting app PID for privacy isolation (non-blocking)
  const hwnd = parseWindowHandleFromSourceId(binding?.target_id || binding?.source_id);
  if (hwnd) {
    companionState.meetingBinding.hwnd = hwnd;
    privacyState.meetingPlatform = inferPlatform(binding?.window_title || "");
    resolveMeetingPid(hwnd).then((pid) => {
      if (pid) {
        privacyState.meetingPid = pid;
        console.log("[Privacy] Resolved meeting PID:", pid, "platform:", privacyState.meetingPlatform);
      }
    }).catch(() => {});
  }

  return companionState.meetingBinding;
});

ipcMain.handle("companion:rebindMeetingTarget", async (_event, binding) => {
  companionState.meetingBinding = {
    ...companionState.meetingBinding,
    ...binding,
    is_bound: true,
  };
  companionState.selectedDesktopSourceId = binding?.source_id || binding?.target_id || null;
  companionState.selectedDesktopSourceName = binding?.source_name || null;
  companionState.selectedDesktopSourceKind = binding?.source_kind || null;

  // Re-resolve PID in case the meeting app restarted
  const hwnd = parseWindowHandleFromSourceId(binding?.target_id || binding?.source_id);
  if (hwnd) {
    companionState.meetingBinding.hwnd = hwnd;
    privacyState.meetingPlatform = inferPlatform(binding?.window_title || "");
    resolveMeetingPid(hwnd).then((pid) => {
      if (pid) {
        privacyState.meetingPid = pid;
        console.log("[Privacy] Re-resolved meeting PID:", pid);
      }
    }).catch(() => {});
  }

  return companionState.meetingBinding;
});

ipcMain.handle("companion:listAudioDevices", async () => ({ inputs: [], outputs: [] }));

ipcMain.handle("companion:getWindowProcessIds", async () => {
  if (!getActiveWindowProcessIds) {
    return [];
  }
  try {
    return await getActiveWindowProcessIds();
  } catch (error) {
    console.warn("[ProcessAudio] getActiveWindowProcessIds failed:", error?.message || error);
    return [];
  }
});

ipcMain.handle("companion:startProcessAudioCapture", async (_event, request) => {
  if (!startAudioCapture) {
    setRemoteAudioMode("none");
    return { ok: false, reason: "native_module_unavailable" };
  }

  const pid = request?.pid;
  const hwnd = request?.hwnd || null;
  if (!pid) {
    setRemoteAudioMode("none");
    return { ok: false, reason: "missing_process_id" };
  }

  try {
    stopRemoteProcessCapture();
    startAudioCapture(String(pid), {
      onData: (chunk) => {
        if (!overlayWindow || overlayWindow.isDestroyed()) {
          return;
        }
        overlayWindow.webContents.send(
          "companion:processAudioChunk",
          Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)
        );
      },
    });
    activeProcessCapturePid = String(pid);
    companionState.processAudioCapture = {
      pid: String(pid),
      hwnd: hwnd ? String(hwnd) : null,
    };
    setRemoteAudioMode("process_loopback");
    return {
      ok: true,
      pid: String(pid),
      hwnd: hwnd ? String(hwnd) : null,
      mode: companionState.remoteAudioMode,
    };
  } catch (error) {
    stopRemoteProcessCapture();
    setRemoteAudioMode("none");
    console.warn("[ProcessAudio] startAudioCapture failed:", error?.message || error);
    return { ok: false, reason: error?.message || String(error) };
  }
});

ipcMain.handle("companion:stopProcessAudioCapture", async () => {
  stopRemoteProcessCapture();
  setRemoteAudioMode("none");
  return { ok: true, mode: companionState.remoteAudioMode };
});

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
  stopRemoteProcessCapture();
  setRemoteAudioMode("none");
  // Reset capture-resilience state so the next session starts clean.
  companionState.captureMissCount = 0;
  companionState.meetingDisplayId = null;
  setCaptureFollowingScreen(false);
  companionState.holdState = {
    active: false,
    muted_to_meeting: false,
  };
  // Restore privacy isolation on session end
  if (privacyState.isMuted || privacyState.strategy === "policyconfig") {
    await performPrivacyRestore().catch(() => {});
  }
  stopWatchdog();
  stopPrivacyHelper();
  privacyState.strategy       = null;
  privacyState.method         = null;
  privacyState.targetDeviceId = null;
  privacyState.needsDisable   = false;
  privacyState.disabledSpare  = null;
  privacyState.isMuted        = false;
  return { sessionActive: false };
});

// ── Privacy isolation IPC handlers ────────────────────────────────────────────
ipcMain.handle("companion:resolvePrivacyStrategy", async (_event, { platform, listenerName } = {}) => {
  privacyState.meetingPlatform = platform || privacyState.meetingPlatform || "generic";
  try {
    const result = await resolvePrivacyStrategy(privacyState.meetingPlatform, listenerName);
    console.log("[Privacy] Resolved strategy:", result.strategy, "reason:", result.reason);
    return result;
  } catch (err) {
    console.error("[Privacy] resolvePrivacyStrategy error:", err.message);
    privacyState.strategy = "hotkey";
    return {
      strategy: "hotkey",
      hotkey:   hotkeyForPlatform(privacyState.meetingPlatform),
      vbcableEnabled: true,
      reason:   "resolution_error",
      error:    err.message,
    };
  }
});

ipcMain.handle("companion:privacyIsolate", async () => {
  try {
    return await performPrivacyIsolate();
  } catch (err) {
    console.error("[Privacy] privacyIsolate error:", err.message);
    return { ok: false, error: err.message };
  }
});

ipcMain.handle("companion:privacyRestore", async () => {
  try {
    return await performPrivacyRestore();
  } catch (err) {
    console.error("[Privacy] privacyRestore error:", err.message);
    return { ok: false, error: err.message };
  }
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
    const thumbW = Math.min(400, size.width);
    const thumbH = Math.min(300, size.height);
    const scaleX = thumbW / size.width;
    const scaleY = thumbH / size.height;
    const sources = await desktopCapturer.getSources({
      types: ["screen"],
      thumbnailSize: { width: thumbW, height: thumbH },
      fetchWindowIcons: false,
    });
    const source = sources[0];
    if (!source) {
      return { theme: "light", luminance: 0 };
    }

    const image = source.thumbnail;
    const bitmap = image.toBitmap();
    const sampleStartX = Math.max(0, Math.round((bounds.x - display.bounds.x + 72) * scaleX));
    const sampleStartY = Math.max(0, Math.round((bounds.y - display.bounds.y + 8) * scaleY));
    const sampleWidth = Math.min(Math.round(220 * scaleX), Math.max(8, Math.round((bounds.width - 84) * scaleX)));
    const sampleHeight = Math.min(Math.round(120 * scaleY), Math.max(8, Math.round((bounds.height - 16) * scaleY)));
    let total = 0;
    let count = 0;

    for (let y = sampleStartY; y < sampleStartY + sampleHeight; y += 4) {
      for (let x = sampleStartX; x < sampleStartX + sampleWidth; x += 4) {
        const idx = (y * thumbW + x) * 4;
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

// ── Before-quit: restore any active privacy redirect ─────────────────────────
app.on("before-quit", async () => {
  stopWatchdog();
  if (privacyState.isMuted && privacyState.meetingPid) {
    console.log("[Privacy] before-quit: restoring meeting app mic...");
    await performPrivacyRestore().catch(() => {});
  }
  stopPrivacyHelper();
});

app.whenReady().then(() => {
  // ── Startup: clear any stale redirect from a previous crash ──────────────
  recoverStaleRedirect().catch((err) =>
    console.warn("[Privacy] recoverStaleRedirect failed:", err.message)
  );
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
          types: ["screen", "window"],
          thumbnailSize: { width: 0, height: 0 },
          fetchWindowIcons: false,
        })
        .then((sources) => {
          let selected = resolveDisplaySource(sources);
          let followingScreen = false;

          if (!selected) {
            // The exact window can't be tracked right now (HWND changed, window
            // swapped/minimized, or moved to another virtual desktop). Do NOT drop
            // the session and do NOT wipe the selection — fall back to capturing
            // the window's monitor so the AI keeps seeing the call, and keep the
            // original window identity so we can re-adopt it once it reappears.
            const screenSrc = pickScreenSource(sources);
            if (screenSrc) {
              selected = screenSrc;
              followingScreen = true;
              companionState.captureMissCount += 1;
              console.warn(
                "[DisplayMedia] Window not found (miss #%d) — following screen %s instead of %s",
                companionState.captureMissCount,
                screenSrc.id,
                companionState.selectedDesktopSourceId
              );
            } else {
              // No screen source either — keep the selection and report empty so a
              // later attempt can re-find the window. Selection is intentionally NOT
              // cleared here (that was the bug that "dropped" the window).
              console.warn(
                "[DisplayMedia] Selected source not found and no screen fallback:",
                companionState.selectedDesktopSourceId
              );
              once({});
              return;
            }
          }

          if (followingScreen) {
            // Serve the monitor for THIS request but preserve the window selection
            // (id/name) so resolveDisplaySource can re-adopt the real window later.
            setCaptureFollowingScreen(true);
          } else {
            companionState.captureMissCount = 0;
            setCaptureFollowingScreen(false);
            if (selected.id !== companionState.selectedDesktopSourceId) {
              console.warn(
                "[DisplayMedia] Remapped stale source id",
                companionState.selectedDesktopSourceId,
                "->",
                selected.id
              );
            }
            companionState.selectedDesktopSourceId = selected.id;
            companionState.selectedDesktopSourceName = selected.name || companionState.selectedDesktopSourceName;
            companionState.selectedDesktopSourceKind = selected.id.startsWith("screen:")
              ? "screen"
              : selected.id.startsWith("window:")
                ? "window"
                : companionState.selectedDesktopSourceKind;
          }

          const response = { video: selected };
          if (companionState.remoteAudioMode === "display_loopback") {
            response.audio = "loopback";
          }
          once(response);
        })
        .catch(() => once({}));
    },
    { useSystemPicker: false }
  );

  // ── Auth gate: check for stored tokens ───────────────────────────────────
  // If AUTH_REQUIRED is not enabled server-side (or we can't reach the backend),
  // open the app normally so dev/localhost behavior is unchanged.
  // When tokens exist, go straight to the app. When they're missing, show login.
  const storedTokens = readAuthTokens();
  if (storedTokens && storedTokens.access_token) {
    // Tokens on disk — open the app immediately (the WS connect will validate
    // the access token; if it's expired, the renderer will refresh via /auth/refresh).
    createOverlayWindow();
    createFullWindow();
  } else {
    // No tokens — show the login window. It calls companion:loginSuccess on success.
    createLoginWindow();
  }

  app.on("activate", () => {
    // Only recreate the app windows if NOT in the login flow.
    if (loginWindow && !loginWindow.isDestroyed()) {
      loginWindow.focus();
      return;
    }
    if (!overlayWindow || overlayWindow.isDestroyed()) {
      createOverlayWindow();
    }
    if (!fullWindow || fullWindow.isDestroyed()) {
      createFullWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
