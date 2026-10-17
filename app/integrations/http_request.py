"""
HTTP Request integration with SSRF protection.

SSRF mitigations:
- Resolve the hostname to an IP before connecting.
- Reject private/loopback/link-local/reserved IP ranges.
- Restrict allowed schemes to http and https only.
- Enforce a hard timeout on every request.
- Limit response body size.

Uses httpx (sync) so it can be called from both the ARQ worker thread
and unit tests without an event loop.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

# Hard limits
_REQUEST_TIMEOUT_SECONDS = 30
_MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB

_ALLOWED_SCHEMES = {"http", "https"}

_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


def execute_http_request(config: dict[str, Any]) -> dict[str, Any]:
    """
    Perform an HTTP request described by *config*.

    Config keys:
        url         (str, required)  — destination URL
        method      (str, required)  — HTTP method
        headers     (dict, optional) — extra request headers
        body        (any,  optional) — request body (sent as JSON if dict, else raw)
        params      (dict, optional) — URL query parameters
        timeout     (int,  optional) — override timeout in seconds (max 30)

    Returns a dict with: status_code, headers, body (decoded text or dict).
    Raises NodeExecutionError on SSRF detection, timeout, or HTTP error.
    """
    from app.engine.node_executor import NodeExecutionError

    url: str = config.get("url", "")
    method: str = (config.get("method") or "GET").upper()

    if not url:
        raise NodeExecutionError("http_request: 'url' is required")

    if method not in _ALLOWED_METHODS:
        raise NodeExecutionError(
            f"http_request: method '{method}' is not allowed. "
            f"Allowed: {sorted(_ALLOWED_METHODS)}"
        )

    # ── SSRF check ────────────────────────────────────────────────────────────
    _check_ssrf(url)

    # ── Build request ─────────────────────────────────────────────────────────
    headers: dict[str, str] = dict(config.get("headers") or {})
    params: dict[str, str] | None = config.get("params") or None
    body = config.get("body")
    timeout = min(int(config.get("timeout") or _REQUEST_TIMEOUT_SECONDS), _REQUEST_TIMEOUT_SECONDS)

    try:
        with httpx.Client(
            follow_redirects=True,
            max_redirects=5,
            timeout=httpx.Timeout(timeout),
        ) as client:
            if isinstance(body, dict):
                response = client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=body,
                )
            elif body is not None:
                response = client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    content=str(body).encode(),
                )
            else:
                response = client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                )

            # Enforce response size limit
            if len(response.content) > _MAX_RESPONSE_BYTES:
                raise NodeExecutionError(
                    f"http_request: response body exceeds {_MAX_RESPONSE_BYTES // (1024*1024)} MB limit"
                )

            # Attempt JSON decode; fall back to text
            try:
                response_body: Any = response.json()
            except Exception:
                response_body = response.text

            return {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response_body,
                "ok": response.is_success,
            }

    except httpx.TimeoutException as exc:
        raise NodeExecutionError(f"http_request: request timed out after {timeout}s") from exc
    except httpx.RequestError as exc:
        raise NodeExecutionError(f"http_request: network error — {exc}") from exc


# ── SSRF protection ────────────────────────────────────────────────────────────

def _check_ssrf(url: str) -> None:
    """
    Raises NodeExecutionError if the URL targets a private/reserved address.
    """
    from app.engine.node_executor import NodeExecutionError

    parsed = urlparse(url)

    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise NodeExecutionError(
            f"http_request: scheme '{scheme}' is not allowed. Use http or https."
        )

    hostname = parsed.hostname
    if not hostname:
        raise NodeExecutionError("http_request: could not parse hostname from URL")

    # Resolve to IP(s)
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise NodeExecutionError(
            f"http_request: DNS resolution failed for '{hostname}': {exc}"
        ) from exc

    for _family, _type, _proto, _canonname, sockaddr in addr_infos:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        if _is_ssrf_risk(ip):
            raise NodeExecutionError(
                f"http_request: SSRF protection — '{hostname}' resolves to a "
                f"private/reserved address ({ip_str}) and cannot be accessed."
            )


def _is_ssrf_risk(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if the IP is in a range that must not be reached externally."""
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )
