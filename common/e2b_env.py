from __future__ import annotations

import logging
import os
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


def _split_csv(value: str) -> list[str]:
    return [p.strip() for p in (value or "").split(",") if p.strip()]


def _dedupe_keep_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _normalize_domain(domain: str) -> str:
    d = (domain or "").strip().lower()
    if not d:
        return ""
    if d.startswith("http://"):
        d = d[len("http://") :]
    if d.startswith("https://"):
        d = d[len("https://") :]
    d = d.strip().lstrip(".")
    if "/" in d:
        d = d.split("/", 1)[0]
    return d


def _e2b_no_proxy_hosts(e2b_domain: Optional[str] = None) -> list[str]:
    bases = ["e2b.app"]
    d = _normalize_domain(e2b_domain or "")
    if d and d not in bases:
        bases.append(d)

    hosts: list[str] = []
    for base in bases:
        if base.startswith("api."):
            root = base[len("api.") :]
            hosts.extend([base, root, f".{root}"])
        else:
            hosts.extend([base, f".{base}", f"api.{base}"])
    return _dedupe_keep_order(hosts)


def prepare_e2b_env(e2b_domain: Optional[str] = None) -> None:
    """
    Make E2B sandbox calls stable under proxy-heavy environments.

    Fixes the common issue where a global SOCKS proxy (ALL_PROXY=socks://...) causes
    E2B's httpx client to fail creating sandboxes with "Server disconnected without
    sending a response.".

    Strategy:
    - If ALL_PROXY/all_proxy is a SOCKS proxy, unset it (httpx doesn't handle that
      combo well here).
    - Ensure NO_PROXY/no_proxy includes E2B control-plane + sandbox domains so E2B
      requests bypass HTTP(S)_PROXY.
    """
    removed: list[str] = []
    for k in ("ALL_PROXY", "all_proxy"):
        v = (os.environ.get(k) or "").strip()
        if v.lower().startswith("socks"):
            os.environ.pop(k, None)
            removed.append(k)

    desired = _e2b_no_proxy_hosts(e2b_domain)
    existing = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
    parts = _split_csv(existing)

    merged = _dedupe_keep_order([*parts, *desired])
    new_value = ",".join(merged)

    updated_no_proxy = False
    if new_value != existing:
        os.environ["NO_PROXY"] = new_value
        os.environ["no_proxy"] = new_value
        updated_no_proxy = True

    if removed or updated_no_proxy:
        changed = []
        if removed:
            changed.append(f"unset {','.join(removed)} (socks)")
        if updated_no_proxy:
            changed.append("updated NO_PROXY for E2B domains")
        logger.info(f"[e2b_env] {'; '.join(changed)}")

