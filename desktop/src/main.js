const fs = require("fs");
const os = require("os");
const path = require("path");
const child_process = require("child_process");
// Load .env from the desktop/ project root (dev only — packaged builds use OS env vars)
require("dotenv").config({ path: path.join(__dirname, "..", ".env") });
const { app, BrowserWindow, desktopCapturer, ipcMain, screen, session } = require("electron");

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

// ── Strategy resolution (policyconfig-FIRST, probe-driven) ────────────────────
// policyconfig is the ALWAYS-chosen primary. No pre-emptive hotkey fallback. The probe
// only selects WHICH silent-target method (existing-disabled vs disable-spare). Hotkey is
// a runtime safety net only (see performPrivacyIsolate). Env overrides still honored.
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
  if (modeEnv === "hotkey") {
    console.log("[Privacy] Strategy forced to hotkey via env");
    privacyState.strategy = "hotkey";
    return { strategy: "hotkey", vbcableEnabled: vbcableAllowed, hotkey: hotkeyForPlatform(platform), reason: "env_forced" };
  }

  // policyconfig (auto or explicit): start helper, run probe to pick the silent-target method
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
      return performHotkeyMute(hotkeyForPlatform(platform));
    }
    try {
      // LISTENER-SAFE: redirect ONLY the meeting app's process to the virtual-cable
      // capture endpoint (silent because nothing feeds the cable's input). We do NOT
      // disable any device — disabling changes the system default and kills the AI
      // listener's getUserMedia stream. The user's mic is never touched.
      const result = await helperCmd({ cmd: "redirect", pid, deviceId: targetDeviceId }, 5000);
      if (!result.ok) {
        console.warn("[Privacy] redirect failed:", result.error, "— hotkey safety net");
        return performHotkeyMute(hotkeyForPlatform(platform));
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
      return performHotkeyMute(hotkeyForPlatform(platform));
    }
  }

  if (strategy === "hotkey") {
    return performHotkeyMute(privacyState.hotkey || hotkeyForPlatform(platform));
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
    return performHotkeyMute(hotkey || hotkeyForPlatform(platform));
  }

  privacyState.isMuted = false;
  clearRecoveryMarker();
  return { ok: true, strategy };
}

async function performHotkeyMute(combo) {
  // Try helper first (has SendInput), then inline PowerShell
  if (helperScriptExists() && privacyState.helperProc && !privacyState.helperProc.killed) {
    try {
      const r = await helperCmd({ cmd: "send-keys", combo }, 3000);
      privacyState.isMuted = !privacyState.isMuted; // toggle
      return { ok: r.ok, strategy: "hotkey", combo };
    } catch (_) {}
  }
  // Inline fallback: spawn a one-shot PowerShell command
  return new Promise((resolve) => {
    const psCmd = `
$k=@{alt=0x12;ctrl=0x11;shift=0x10};
$sig='[DllImport(\"user32.dll\")] public static extern bool SendInput(uint n,IntPtr[] a,int s);';
$t=Add-Type -MemberDefinition $sig -Name U32 -Namespace W -PassThru;
$parts='${combo}'.Split('+');
$vks=@();foreach($p in $parts){if($k[$p]){$vks+=$k[$p]}else{$vks+=[byte][char]$p.ToUpper()[0]}};
Add-Type -TypeDefinition '[StructLayout(LayoutKind.Sequential)]struct KI{public ushort v,s;public uint f,t;public IntPtr e;}[StructLayout(LayoutKind.Explicit)]struct IN{[FieldOffset(0)]public uint tp;[FieldOffset(8)]public KI k;}' -Language CSharp;
$a=@();foreach($v in $vks){$i=[IN]::new();$i.tp=1;$i.k=[KI]::new();$i.k.v=$v;$a+=$i};
foreach($v in ($vks|Sort -Desc)){$i=[IN]::new();$i.tp=1;$i.k=[KI]::new();$i.k.v=$v;$i.k.f=2;$a+=$i};
[System.Runtime.InteropServices.Marshal]::SizeOf([IN])`;
    child_process.exec(`powershell.exe -NonInteractive -NoProfile -WindowStyle Hidden -Command "${psCmd.replace(/\n/g, "")}"`,
      { windowsHide: true }, (err) => {
        privacyState.isMuted = !privacyState.isMuted;
        resolve({ ok: !err, strategy: "hotkey_inline", combo });
      }
    );
  });
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
  return null;
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
          const selected = resolveDisplaySource(sources);
          if (!selected) {
            console.warn(
              "[DisplayMedia] Selected source not found:",
              companionState.selectedDesktopSourceId
            );
            // Clear stale source so user can re-select
            companionState.selectedDesktopSourceId = null;
            companionState.selectedDesktopSourceName = null;
            companionState.selectedDesktopSourceKind = null;
          }
          if (!selected) {
            once({});
            return;
          }
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

  createOverlayWindow();
  createFullWindow();

  app.on("activate", () => {
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
