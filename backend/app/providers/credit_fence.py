"""The one door every Anthropic messages call in this repo goes through.

It puts the call behind Mission Control's API credit fence (voice/bridge/api_credit.py,
DEC-20261103-API-CREDIT-ADAPTIVE): a hold before the call (refused = the client is never
called, nothing is spent), then the hold is settled with the response's real usage numbers.

Mission Control's folder comes from env MC_HOME (default C:\\Balaastra\\MISSION-CONTROL).
When the fence cannot be reached (a deployed server without Mission Control):
- a product call goes ahead and its usage is appended to api-credit-unrecorded.jsonl
  (category, who, model, token counts, time; never a key) for a later `api_credit.py record`;
- demo / internal / planner calls are refused with a plain message.

A call made with a key the session brought itself (per-session BYOK overlay) does not spend
the Team plan's credit, so it goes straight to the client.

Never reads, logs or stores a key: the client the caller made holds it.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

CATEGORY = "product"            # Negotiation Copilot is a product: its live features spend as product
WHO = "negotiation-copilot"
_DEFAULT_MC_HOME = r"C:\Balaastra\MISSION-CONTROL"
_DEFAULT_UNRECORDED = Path(__file__).resolve().parents[2] / "data" / "api-credit-unrecorded.jsonl"

_lock = threading.Lock()
_fence_cache: dict[str, object] = {}


class Refused(RuntimeError):
    """The credit fence said no (str() is the plain reason); the client was never called."""


def _mc_home() -> Path:
    return Path(os.environ.get("MC_HOME") or _DEFAULT_MC_HOME)


def unrecorded_path() -> Path:
    return Path(os.environ.get("API_CREDIT_UNRECORDED_PATH") or _DEFAULT_UNRECORDED)


def _fence():
    """Mission Control's api_credit module, or None when it is not on this machine."""
    src = _mc_home() / "voice" / "bridge" / "api_credit.py"
    key = str(src)
    with _lock:
        if key in _fence_cache:
            return _fence_cache[key]
        mod = None
        if src.is_file():
            try:
                bridge = str(src.parent)
                if bridge not in sys.path:
                    sys.path.insert(0, bridge)
                spec = importlib.util.spec_from_file_location("api_credit", src)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                sys.modules.setdefault("api_credit", mod)
            except Exception as exc:  # broken checkout = unreachable, same as absent
                logger.warning("credit fence at %s could not load (%s); treating as unreachable",
                               src.parent, type(exc).__name__)
                mod = None
        _fence_cache[key] = mod
        return mod


def _tokens(usage) -> dict[str, int]:
    get = (lambda k: (usage.get(k) if isinstance(usage, dict) else getattr(usage, k, 0)) or 0)
    return {"input": int(get("input_tokens")), "output": int(get("output_tokens")),
            "cache_write": int(get("cache_creation_input_tokens")),
            "cache_read": int(get("cache_read_input_tokens"))}


def _append_unrecorded(category: str, who: str, model: str, usage) -> None:
    row = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "category": category, "who": who, "model": model, **_tokens(usage)}
    path = unrecorded_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _lock, path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except OSError as exc:
        logger.warning("could not append API usage to %s (%s)", path, type(exc).__name__)


async def create(client, *, category: str = CATEGORY, who: str = WHO,
                 own_key: bool = False, **kwargs):
    """`await client.messages.create(**kwargs)` behind the credit fence.

    Raises Refused before the client is called when the fence says no.
    `own_key=True`: the session brought its own key, so the Team credit is not spent.
    """
    if own_key:
        return await client.messages.create(**kwargs)
    model = kwargs.get("model", "")
    fence = _fence()
    hid = None
    if fence is not None:
        try:
            hid = await asyncio.to_thread(fence.hold, category, who, model, fence.estimate(model, kwargs))
        except fence.Refused as exc:
            raise Refused(f"API credit fence refused this {category} call: {exc}") from None
        except Exception as exc:  # ledger unreadable: same as no fence
            logger.warning("credit fence unreachable (%s)", type(exc).__name__)
            fence = None
    if fence is None and category != "product":
        raise Refused(f"API credit fence unreachable: {category} calls only run where Mission Control "
                      f"can count them (set MC_HOME)")

    try:
        resp = await client.messages.create(**kwargs)
    except BaseException:
        if hid is not None:
            try:
                await asyncio.to_thread(fence.settle, hid, model, None, failed=True)
            except Exception as exc:
                logger.warning("credit fence settle failed (%s)", type(exc).__name__)
        raise

    used_model = getattr(resp, "model", None) or model
    usage = getattr(resp, "usage", None) or {}
    if hid is None:
        _append_unrecorded(category, who, used_model, usage)
        return resp
    try:
        await asyncio.to_thread(fence.settle, hid, used_model, usage)
    except Exception as exc:  # the answer is already paid for; keep it, keep the count locally
        logger.warning("credit fence settle failed (%s); usage kept locally", type(exc).__name__)
        _append_unrecorded(category, who, used_model, usage)
    return resp
