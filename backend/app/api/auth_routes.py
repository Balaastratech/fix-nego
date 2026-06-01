"""Auth REST endpoints (Phase auth — Clerk + app-session JWT).

Routes:
    GET  /auth/login-page              Hosted Clerk sign-in page (serves HTML).
    POST /auth/exchange   {clerk_token} Verify Clerk token, mint app tokens.
    POST /auth/refresh    {refresh_token} Rotate refresh token, return new pair.
    POST /auth/logout     {refresh_token} Revoke refresh token.
    GET  /auth/me                      Current user info (requires app JWT).

All endpoints except /auth/login-page are JSON.
The /auth/login-page route is intentionally left OPEN (no auth dependency) so
the desktop can redirect the system browser to it without a token.
"""

from __future__ import annotations

import base64
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.api.auth import get_current_user, AuthUser
from app.config import settings
from app.services.clerk_verify import verify_clerk_token, ClerkTokenError
from app.services.app_tokens import make_token_pair, verify_refresh_token, TokenError
from app.services import auth_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ── /auth/login-page ──────────────────────────────────────────────────────────

def _clerk_fapi_url(publishable_key: str) -> str:
    """Derive Clerk's Frontend API URL from the publishable key.

    The key is: pk_(test|live)_<base64(frontend-api-host + "$")>
    Clerk hosts its own JS bundles at this URL — this is the correct CDN,
    not npm/jsDelivr/esm.sh.
    """
    try:
        b64 = publishable_key.split("_", 2)[-1]
        padding = 4 - len(b64) % 4
        if padding != 4:
            b64 += "=" * padding
        host = base64.b64decode(b64).decode("utf-8").rstrip("$")
        return f"https://{host}"
    except Exception:
        return (settings.CLERK_ISSUER or "").rstrip("/")


# Official Clerk loading pattern — from clerk.com/docs/quickstarts/javascript.
# Scripts are served from YOUR Clerk Frontend API host (derived from publishable key).
# Two scripts in order: UI bundle first, then core clerk.js (defer preserves order).
# After load, `Clerk` is a global PRE-INITIALIZED instance — not a class to new-up.
_LOGIN_PAGE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sign in — Balaastra Companion</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
    background:#0f1117;color:#e8e8f0;display:flex;flex-direction:column;
    align-items:center;justify-content:center;min-height:100vh;gap:20px;padding:24px}}
  h1{{font-size:1.3rem;font-weight:600;color:#fff;letter-spacing:-.02em}}
  #clerk-mount{{width:100%;max-width:420px;min-height:300px}}
  #status{{font-size:.85rem;color:#9ca3af;text-align:center;max-width:420px;min-height:1.2em}}
  .err{{color:#f87171}}.ok{{color:#34d399}}
</style>
<script defer crossorigin="anonymous"
  src="{fapi_url}/npm/@clerk/ui@1/dist/ui.browser.js"></script>
<script defer crossorigin="anonymous"
  data-clerk-publishable-key="{publishable_key}"
  src="{fapi_url}/npm/@clerk/clerk-js@6/dist/clerk.browser.js"
  onload="initClerk()"></script>
</head>
<body>
<h1>Balaastra AI Companion</h1>
<div id="clerk-mount"></div>
<p id="status">Loading sign-in form…</p>
<p id="debug" style="font-size:11px;color:#4b5563;margin-top:8px;font-family:monospace"></p>

<script>
  const REDIRECT_URI  = {redirect_uri!r};
  const FORCE_SIGNOUT = {force_signout};   // injected as JS boolean literal true/false
  let _completing = false;   // guard against double-firing

  function setStatus(msg, cls) {{
    const el = document.getElementById('status');
    if (el) {{ el.textContent = msg; el.className = cls || ''; }}
  }}
  function dbg(msg) {{
    console.log('[clerk-login] ' + msg);
    const el = document.getElementById('debug');
    if (el) el.textContent = msg;
  }}

  async function completeSignIn() {{
    if (_completing) return;
    _completing = true;
    setStatus('Signed in — getting token…', 'ok');
    dbg('completeSignIn(): session=' + !!Clerk.session);
    try {{
      // Wait for the session object to be ready (it's in memory after sign-in).
      for (let i = 0; i < 40 && !Clerk.session; i++)
        await new Promise(r => setTimeout(r, 250));
      if (!Clerk.session) throw new Error('No Clerk session after sign-in.');

      const token = await Clerk.session.getToken();
      dbg('got token: ' + (token ? token.slice(0, 16) + '…' : 'EMPTY'));
      if (!token) throw new Error(
        'Empty token. Add email + email_verified claims in Clerk Dashboard → ' +
        'Configure → Sessions → Customize session token, then retry.'
      );
      setStatus('Redirecting back to app…', 'ok');
      const url = new URL(REDIRECT_URI);
      url.searchParams.set('clerk_token', token);
      dbg('redirecting to ' + url.origin + url.pathname);
      window.location.href = url.toString();
    }} catch (e) {{
      _completing = false;
      setStatus('Error: ' + e.message, 'err');
      dbg('ERROR: ' + e.message);
    }}
  }}

  // Bulletproof: poll Clerk's in-memory state every 500ms. The instant a user +
  // session appear (right after the form sign-in completes), grab the token.
  // This does NOT depend on any event firing or on cookie persistence.
  function startSessionPoll() {{
    let ticks = 0;
    const iv = setInterval(() => {{
      ticks++;
      if (Clerk && Clerk.user && Clerk.session && !_completing) {{
        clearInterval(iv);
        dbg('poll detected signed-in user');
        completeSignIn();
      }}
      if (ticks % 6 === 0) dbg('waiting for sign-in… (user=' + !!(Clerk && Clerk.user) + ')');
    }}, 500);
  }}

  async function initClerk() {{
    try {{
      dbg('Clerk.load()…');
      await Clerk.load({{ ui: {{ ClerkUI: window.__internal_ClerkUICtor }} }});
      dbg('loaded. user=' + !!Clerk.user + ' forceSignout=' + FORCE_SIGNOUT);

      if (Clerk.user && FORCE_SIGNOUT) {{
        // Explicit desktop sign-out: clear Clerk's browser session ONCE, then land
        // on /auth/clear-signout which wipes the signout flag (so the next fresh
        // sign-in does NOT get force-signed-out again — that was the infinite loop).
        setStatus('Clearing previous session…');
        const clearUrl = window.location.origin +
          '/auth/clear-signout?redirect=' + encodeURIComponent(REDIRECT_URI);
        await Clerk.signOut({{ redirectUrl: clearUrl }});
        return;
      }}

      if (Clerk.user) {{
        // Already signed in — complete immediately.
        await completeSignIn();
        return;
      }}

      // Not signed in — show the form and start polling for completion.
      setStatus('');
      Clerk.mountSignIn(document.getElementById('clerk-mount'), {{ routing: 'virtual' }});
      startSessionPoll();
    }} catch (e) {{
      setStatus('Clerk error: ' + e.message, 'err');
      dbg('INIT ERROR: ' + e.message);
    }}
  }}
</script>
</body>
</html>"""


@router.get("/login-page", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request, redirect: str = "", signout: str = ""):
    """Serve the hosted Clerk sign-in page.

    The desktop app opens this URL in the system browser via shell.openExternal,
    passing ``?redirect=http://127.0.0.1:<PORT>/callback`` as the loopback
    destination. ``?signout=1`` tells the page to call Clerk.signOut() before
    mounting the sign-in form (used after an explicit desktop sign-out).
    """
    publishable_key = (settings.CLERK_PUBLISHABLE_KEY or "").strip()
    redirect_uri = redirect.strip() or "http://127.0.0.1:0/callback"
    fapi_url = _clerk_fapi_url(publishable_key) if publishable_key else ""
    force_signout = "true" if signout == "1" else "false"

    if not publishable_key:
        return HTMLResponse(
            content="<h2 style='font-family:sans-serif;color:#f87171;padding:2rem'>"
                    "CLERK_PUBLISHABLE_KEY is not set in backend/.env. "
                    "Restart the backend after adding it.</h2>",
            status_code=503,
        )

    html = _LOGIN_PAGE_TEMPLATE.format(
        publishable_key=publishable_key,
        redirect_uri=redirect_uri,
        fapi_url=fapi_url,
        force_signout=force_signout,
    )
    response = HTMLResponse(content=html)
    # _clerk_redirect: lets GET / (handshake handler) bounce the browser back here
    # with the correct loopback callback after Clerk syncs cookies to our domain.
    if redirect_uri:
        response.set_cookie("_clerk_redirect", redirect_uri, max_age=600, samesite="lax", httponly=False)
    # _clerk_signout: short-lived flag so the signout intent survives the ONE
    # handshake round-trip needed to populate Clerk.user before we sign out.
    # It is wiped by /auth/clear-signout right after the sign-out completes, so it
    # can never re-trigger on a subsequent fresh sign-in (the old infinite loop).
    if signout == "1":
        response.set_cookie("_clerk_signout", "1", max_age=120, samesite="lax", httponly=False)
    else:
        # Normal login — make sure no stale signout flag lingers.
        response.delete_cookie("_clerk_signout")
    return response


@router.get("/clear-signout", include_in_schema=False)
async def clear_signout(redirect: str = ""):
    """Land here after Clerk.signOut() completes. Wipe the _clerk_signout flag and
    bounce to a CLEAN login page (no signout param) so the next sign-in is normal.
    This is what breaks the sign-out → re-sign-out infinite loop."""
    from urllib.parse import quote as _quote
    from fastapi.responses import RedirectResponse
    url = "/auth/login-page"
    if redirect.strip():
        url += f"?redirect={_quote(redirect.strip(), safe='')}"
    resp = RedirectResponse(url=url, status_code=302)
    resp.delete_cookie("_clerk_signout")
    return resp


# ── /auth/exchange ────────────────────────────────────────────────────────────

@router.post("/exchange")
async def exchange_clerk_token(payload: dict = Body(...)):
    """Exchange a Clerk session token for our own access + refresh tokens."""
    clerk_token = (payload.get("clerk_token") or "").strip()
    if not clerk_token:
        raise HTTPException(status_code=400, detail="clerk_token is required")

    try:
        claims = await verify_clerk_token(clerk_token)
    except ClerkTokenError as exc:
        logger.warning("Clerk token verification failed: %s", exc)
        raise HTTPException(status_code=401, detail=f"Clerk token invalid: {exc}")

    clerk_sub: str = claims.get("sub", "")
    if not clerk_sub:
        raise HTTPException(status_code=401, detail="Clerk token missing 'sub' claim")

    email: str = (
        claims.get("email")
        or claims.get("primary_email_address")
        or ""
    )
    email_verified: bool = bool(
        claims.get("email_verified", False)
        or claims.get("primary_email_address_verified", False)
    )

    if not email_verified:
        raise HTTPException(
            status_code=403,
            detail="Please verify your email address before signing in.",
        )

    auth_db.upsert_user(clerk_sub, email, email_verified)
    token_pair, jti, expires_at = make_token_pair(clerk_sub, email)
    auth_db.store_refresh_token(jti, clerk_sub, expires_at)

    logger.info("User authenticated via Clerk sub=%s", clerk_sub[:8] + "…")
    return {
        **token_pair,
        "user": {"clerk_sub": clerk_sub, "email": email},
    }


# ── /auth/refresh ─────────────────────────────────────────────────────────────

@router.post("/refresh")
async def refresh_tokens(payload: dict = Body(...)):
    """Rotate a refresh token. Old jti is revoked; a new pair is returned."""
    raw = (payload.get("refresh_token") or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="refresh_token is required")

    try:
        claims = verify_refresh_token(raw)
    except TokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    jti: str = claims.get("jti", "")
    if not auth_db.is_refresh_token_valid(jti):
        raise HTTPException(status_code=401, detail="Refresh token has been revoked or expired")

    clerk_sub: str = claims["sub"]
    user = auth_db.get_user(clerk_sub)
    email = user["email"] if user else ""

    auth_db.revoke_refresh_token(jti)
    token_pair, new_jti, expires_at = make_token_pair(clerk_sub, email)
    auth_db.store_refresh_token(new_jti, clerk_sub, expires_at)

    return token_pair


# ── /auth/logout ──────────────────────────────────────────────────────────────

@router.post("/logout")
async def logout(payload: dict = Body(...)):
    """Revoke a refresh token (logout)."""
    raw = (payload.get("refresh_token") or "").strip()
    if not raw:
        return {"ok": True}

    try:
        claims = verify_refresh_token(raw)
        jti = claims.get("jti", "")
        if jti:
            auth_db.revoke_refresh_token(jti)
    except TokenError:
        pass

    return {"ok": True}


# ── /auth/me ──────────────────────────────────────────────────────────────────

@router.get("/me")
async def me(current_user: AuthUser = Depends(get_current_user)):
    """Return the current user's info. Requires a valid app access JWT."""
    if not current_user.clerk_sub or current_user.is_admin:
        return {"clerk_sub": None, "email": None, "is_admin": current_user.is_admin}
    user = auth_db.get_user(current_user.clerk_sub)
    return {
        "clerk_sub": current_user.clerk_sub,
        "email": current_user.email,
        "is_admin": False,
        "email_verified": bool(user["email_verified"]) if user else None,
        "last_login_at": user["last_login_at"] if user else None,
    }
