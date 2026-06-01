/* login.js — renderer logic for the login window.
 * All real auth UI lives in Clerk's hosted page (opened in system browser).
 * This window only has the "Sign in" button that triggers the loopback flow.
 */

function setStatus(msg, kind) {
  const el = document.getElementById("status");
  el.textContent = msg;
  el.className = kind || "";
}

function setLoading(loading) {
  const btn = document.getElementById("btn-signin");
  btn.disabled = loading;
  btn.querySelector("span").textContent = loading
    ? "Waiting for browser sign-in…"
    : "Sign in / Create account";
}

document.getElementById("btn-signin").addEventListener("click", startLogin);

// Listen for the login URL pushed by the main process as soon as the loopback
// server starts — show it so the user can copy & paste into any browser.
window.companionBridge.onLoginUrl((url) => {
  const input = document.getElementById("login-url");
  const row = document.getElementById("link-row");
  if (input && row) {
    input.value = url;
    row.style.display = "flex";
  }
});

function copyLoginUrl() {
  const input = document.getElementById("login-url");
  const btn = document.getElementById("btn-copy");
  if (!input || !input.value) return;

  function onCopied() {
    if (btn) { btn.textContent = "Copied ✓"; setTimeout(() => { btn.textContent = "Copy"; }, 2000); }
  }

  // navigator.clipboard requires HTTPS — use execCommand fallback on HTTP.
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(input.value).then(onCopied).catch(() => {
      input.select(); input.setSelectionRange(0, 99999);
      document.execCommand("copy");
      onCopied();
    });
  } else {
    input.select();
    input.setSelectionRange(0, 99999);
    try { document.execCommand("copy"); onCopied(); }
    catch (_) { if (btn) btn.textContent = "Press Ctrl+C"; }
  }
}

async function startLogin() {
  setLoading(true);
  setStatus("Opening your browser…", "info");
  try {
    const result = await window.companionBridge.startLogin();
    setStatus("Signed in! Opening app…", "ok");
    await window.companionBridge.loginSuccess();
  } catch (err) {
    const msg = err.message || "Sign-in failed.";
    const hint = msg.includes("fetch") || msg.includes("ECONNREFUSED") || msg.includes("Failed to open")
      ? msg + " — Is the backend running? Start it with: uvicorn app.main:app"
      : msg;
    setStatus(hint, "err");
    setLoading(false);
    // Hide the link row on failure (the loopback server closed)
    const row = document.getElementById("link-row");
    if (row) row.style.display = "none";
  }
}
