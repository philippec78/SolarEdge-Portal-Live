"""Read the SolarEdge portal's live power flow using its OAuth PKCE session."""

from __future__ import annotations

import asyncio
import base64
import hashlib
from html.parser import HTMLParser
import json
import math
import secrets
from time import monotonic
from urllib.parse import parse_qs, urljoin, urlsplit

from aiohttp import ClientError, ClientSession, ClientTimeout

AUTH = "https://login.solaredge.com"
PORTAL = "https://monitoring.solaredge.com"
CALLBACK = f"{PORTAL}/mfe/auth/callback"
CLIENT_ID = "ugfnsujd3384sshcjehaphlh3"
DASHBOARD = f"{PORTAL}/one"
TIMEOUT = ClientTimeout(total=12)
REDIRECTS = {301, 302, 303, 307, 308}


class PortalError(Exception):
    """A sanitized error safe to show in Home Assistant."""


class LoginRequired(PortalError):
    """SolarEdge requires credentials or an interactive login."""


class SiteAccessDenied(PortalError):
    """The requested site is unavailable to this account."""


class TemporaryError(PortalError):
    """A connection error that should be retried without a new login."""

    def __init__(self, message: str, retry_after: int = 60) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class _TokenRejected(LoginRequired):
    """The token endpoint explicitly refused the grant."""


class _AccessExpired(LoginRequired):
    """The portal refused the current access token."""


class _LoginPage(HTMLParser):
    """Read the CSRF field from the hosted login form."""

    csrf: str | None = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "input" and attributes.get("name") == "csrf":
            self.csrf = attributes.get("value")


class PortalClient:
    """Keep one OAuth session and serialize authentication per site."""

    def __init__(
        self, session: ClientSession, username: str, password: str,
        site_id: str, refresh_token: str | None = None,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._site_id = site_id
        self.refresh_token = refresh_token
        self._access_token: str | None = None
        self._renew_at = 0.0
        self._lock = asyncio.Lock()

    async def power_flow(self) -> dict:
        """Fetch live data, retrying once after an expired access token."""
        async with self._lock:
            if not self._access_token or monotonic() >= self._renew_at:
                await self._renew()
            try:
                return await self._fetch_power()
            except _AccessExpired:
                self._access_token = None
                await self._renew()
                return await self._fetch_power()

    async def _renew(self) -> None:
        if self.refresh_token:
            try:
                await self._token({
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                })
                return
            except _TokenRejected:
                self.refresh_token = None
        await self._login()

    async def _login(self) -> None:
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).decode("ascii").rstrip("=")
        cookies: dict[str, str] = {}

        status, headers, _ = await self._request(
            "GET", f"{AUTH}/oauth2/authorize", login_cookies=cookies,
            params={
                "client_id": CLIENT_ID,
                "response_type": "code",
                "scope": "email openid",
                "redirect_uri": CALLBACK,
                "code_challenge_method": "S256",
                "code_challenge": challenge,
            },
        )
        form_url = urljoin(AUTH, headers.get("Location", ""))
        form = urlsplit(form_url)
        if status not in REDIRECTS or (
            form.scheme, form.netloc, form.path
        ) != ("https", "login.solaredge.com", "/login"):
            raise LoginRequired("SolarEdge requires an interactive sign-in.")

        status, _, body = await self._request("GET", form_url, login_cookies=cookies)
        page = _LoginPage()
        page.feed(body)
        if status != 200 or not page.csrf:
            raise LoginRequired("SolarEdge did not provide its login form.")

        status, headers, _ = await self._request(
            "POST", form_url, login_cookies=cookies,
            headers={"Origin": AUTH, "Referer": form_url},
            data={
                "csrf": page.csrf,
                "username": self._username,
                "password": self._password,
                "cognitoAsfData": "",
            },
        )
        target = urlsplit(urljoin(form_url, headers.get("Location", "")))
        code = parse_qs(target.query).get("code", [None])[0]
        if status not in REDIRECTS or not code or (
            target.scheme, target.netloc, target.path
        ) != ("https", "monitoring.solaredge.com", "/mfe/auth/callback"):
            raise LoginRequired("SolarEdge rejected the sign-in or requires verification.")

        await self._token({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": CALLBACK,
            "code_verifier": verifier,
        })

    async def _token(self, grant: dict[str, str]) -> None:
        status, _, body = await self._request(
            "POST", f"{AUTH}/oauth2/token", data={"client_id": CLIENT_ID, **grant},
            headers={"Accept": "application/json", "Origin": PORTAL, "Referer": f"{PORTAL}/"},
        )
        data = _json_object(body)
        if status == 401 or (status in (400, 403) and data.get("error") == "invalid_grant"):
            raise _TokenRejected("SolarEdge refused the OAuth grant.")
        access = data.get("access_token")
        lifetime = data.get("expires_in")
        if (
            status != 200 or not isinstance(access, str) or not access
            or type(lifetime) not in (int, float) or not math.isfinite(lifetime)
            or lifetime <= 0
        ):
            raise TemporaryError("SolarEdge did not return a usable OAuth token.")
        self._access_token = access
        self._renew_at = monotonic() + lifetime - min(120, lifetime / 2)
        if isinstance(new_token := data.get("refresh_token"), str) and new_token:
            self.refresh_token = new_token

    async def _fetch_power(self) -> dict:
        status, headers, body = await self._request(
            "GET", f"{PORTAL}/services/dashboard/power-flow/v2/sites/{self._site_id}",
            params=[("components", "grid"), ("components", "consumption")],
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._access_token}",
                "Referer": DASHBOARD,
            },
        )
        if status == 401 or (
            status in REDIRECTS
            and urlsplit(urljoin(PORTAL, headers.get("Location", ""))).hostname
            == "login.solaredge.com"
        ):
            raise _AccessExpired("SolarEdge refused the access token.")
        if status in (403, 404):
            raise SiteAccessDenied("SolarEdge denied access to this site.")
        data = _json_object(body)
        if status != 200 or not isinstance(data.get("isRealTime"), bool):
            raise TemporaryError("SolarEdge did not return a power flow.")
        return data

    async def _request(self, method, url, *, login_cookies=None, **kwargs):
        try:
            async with self._session.request(
                method, url, allow_redirects=False, timeout=TIMEOUT,
                cookies=login_cookies, **kwargs,
            ) as response:
                status = response.status
                headers = response.headers
                if status == 429 or status >= 500:
                    delay = headers.get("Retry-After", "")
                    raise TemporaryError(
                        f"SolarEdge returned HTTP {status}.",
                        max(60, int(delay)) if delay.isascii() and delay.isdecimal() else 120,
                    )
                if login_cookies is not None:
                    login_cookies.update(
                        (name, cookie.value) for name, cookie in response.cookies.items()
                    )
                return status, headers, await response.text(errors="replace")
        except (ClientError, TimeoutError):
            raise TemporaryError("Could not reach SolarEdge.") from None


def _json_object(body: str) -> dict:
    try:
        value = json.loads(body)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}
