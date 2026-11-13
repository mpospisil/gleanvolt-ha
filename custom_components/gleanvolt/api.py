"""A small typed async client for the Gleanvolt HTTP API (1.2.0 and later).

Only what the integration uses. Every route it calls is listed in ``ROUTES``, and the contract test
checks each one, and every field read or sent, against ``contract/openapi.json``.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import aiohttp

API_PREFIX = "/api/v1"
REQUEST_TIMEOUT = 15

# Logical name -> (method, path under /api/v1, response schema or None).
ROUTES: dict[str, tuple[str, str, str | None]] = {
    "health": ("GET", "/health", "HealthResponse"),
    "status": ("GET", "/status", "StatusResponse"),
    "vehicle": ("GET", "/vehicle", "VehicleResponse"),
    "tariff": ("GET", "/tariff", "TariffResponse"),
    "low_tariff_only": ("GET", "/charging/low-tariff-only", "LowTariffOnlyResponse"),
    "set_low_tariff_only": ("PUT", "/charging/low-tariff-only", "LowTariffOnlyResponse"),
    "until_full": ("GET", "/charging/until-full", "UntilFullResponse"),
    # Without ?weather=true: the cached forecast, no call to a weather provider.
    "forecast": ("GET", "/forecast", "ForecastResponse"),
    "set_until_full": ("PUT", "/charging/until-full", "UntilFullResponse"),
    "start": ("POST", "/charging/start", "ControlActionResponse"),
    "stop": ("POST", "/charging/stop", "ControlActionResponse"),
    "battery_hold": ("PUT", "/battery-hold", "ControlActionResponse"),
    "preview_targeted": ("POST", "/plans/targeted/preview", "TargetedPreviewResponse"),
}

# Request schema of each route that takes a body, for the contract test.
REQUEST_SCHEMAS: dict[str, str] = {
    "set_low_tariff_only": "LowTariffOnlyRequest",
    "set_until_full": "UntilFullRequest",
    "start": "StartChargingRequest",
    "battery_hold": "BatteryHoldRequest",
    "preview_targeted": "TargetedChargeRequestBody",
}


class GleanvoltError(Exception):
    """Anything that went wrong talking to Gleanvolt."""


class GleanvoltConnectionError(GleanvoltError):
    """No answer: the host is unreachable, or it timed out."""


class GleanvoltAuthError(GleanvoltError):
    """401: the API key is wrong."""


class GleanvoltApiDisabledError(GleanvoltError):
    """404 on a route that exists in 1.2.0: the API is switched off (no route is mapped)."""


class GleanvoltNotReadyError(GleanvoltError):
    """503: the controller is up but has no poll to report yet."""


class GleanvoltRequestError(GleanvoltError):
    """The controller refused the request (400 or 409), or the action reported ``succeeded: false``.

    ``message`` is the controller's own reason, meant to be shown to the person who asked.
    """

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def parse_version(version: str | None) -> tuple[int, int, int] | None:
    """``1.2.0 (31bf347)`` or ``1.2.0-dev`` -> (1, 2, 0). None when there is no version in it."""
    if not version:
        return None
    match = _VERSION.search(version)
    if match is None:
        return None
    return int(match[1]), int(match[2]), int(match[3])


def number(value: Any) -> float | None:
    """The API writes a number, or a string for one it cannot write as a JSON number (NaN, ∞)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed and parsed not in (float("inf"), float("-inf")) else None


class GleanvoltClient:
    """One installation's API, behind one key."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int,
        api_key: str,
    ) -> None:
        self._session = session
        self._host = host
        self._port = port
        self._api_key = api_key

    @property
    def base_url(self) -> str:
        """The web UI's address."""
        host = f"[{self._host}]" if ":" in self._host else self._host
        return f"http://{host}:{self._port}"

    async def _request(self, route: str, body: dict[str, Any] | None = None) -> Any:
        method, path, _ = ROUTES[route]
        url = f"{self.base_url}{API_PREFIX}{path}"
        headers = {"Authorization": f"Bearer {self._api_key}", "Accept": "application/json"}
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.request(
                    method, url, json=body, headers=headers
                ) as response:
                    if response.status == 401:
                        raise GleanvoltAuthError("The API key was refused")
                    if response.status == 404:
                        raise GleanvoltApiDisabledError(f"{method} {path} answered 404")
                    if response.status == 503:
                        raise GleanvoltNotReadyError(await _problem_detail(response))
                    if response.status in (400, 409):
                        raise GleanvoltRequestError(
                            await _problem_detail(response), response.status
                        )
                    if response.status >= 400:
                        raise GleanvoltError(
                            f"{method} {path} answered {response.status}: "
                            f"{await _problem_detail(response)}"
                        )
                    return await response.json(content_type=None)
        except (TimeoutError, aiohttp.ClientConnectionError) as err:
            raise GleanvoltConnectionError(str(err) or type(err).__name__) from err
        except aiohttp.ClientError as err:
            raise GleanvoltError(str(err)) from err

    async def _action(self, route: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """An action: a refused hardware write is 200 with ``succeeded: false``, read the flag."""
        result = await self._request(route, body)
        if not result.get("succeeded", False):
            raise GleanvoltRequestError(result.get("message") or "The controller did not do it")
        return result

    async def health(self) -> dict[str, Any]:
        return await self._request("health")

    async def status(self) -> dict[str, Any]:
        return await self._request("status")

    async def vehicle(self) -> dict[str, Any]:
        return await self._request("vehicle")

    async def tariff(self) -> dict[str, Any]:
        return await self._request("tariff")

    async def low_tariff_only(self) -> dict[str, Any]:
        return await self._request("low_tariff_only")

    async def set_low_tariff_only(
        self, *, fast_no_battery: bool | None = None, solar_grid: bool | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if fast_no_battery is not None:
            body["fastNoBattery"] = fast_no_battery
        if solar_grid is not None:
            body["solarGrid"] = solar_grid
        return await self._request("set_low_tariff_only", body)

    async def until_full(self) -> dict[str, Any]:
        return await self._request("until_full")

    async def forecast(self) -> dict[str, Any]:
        return await self._request("forecast")

    async def set_until_full(self, until_full: bool) -> dict[str, Any]:
        return await self._request("set_until_full", {"untilFull": until_full})

    async def start(self, body: dict[str, Any]) -> dict[str, Any]:
        return await self._action("start", body)

    async def stop(self) -> dict[str, Any]:
        return await self._action("stop")

    async def set_battery_hold(self, hold: bool) -> dict[str, Any]:
        return await self._action("battery_hold", {"hold": hold})

    async def preview_targeted(self, body: dict[str, Any]) -> dict[str, Any]:
        return await self._request("preview_targeted", body)


async def _problem_detail(response: aiohttp.ClientResponse) -> str:
    """RFC 9457 problem details: ``detail`` is the reason, in the caller's terms."""
    try:
        problem = await response.json(content_type=None)
    except (aiohttp.ContentTypeError, ValueError):
        text = await response.text()
        return text.strip() or f"HTTP {response.status}"
    if isinstance(problem, dict):
        return problem.get("detail") or problem.get("title") or f"HTTP {response.status}"
    return f"HTTP {response.status}"
