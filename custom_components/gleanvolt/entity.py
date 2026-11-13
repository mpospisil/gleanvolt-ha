"""Shared entity plumbing."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, Concatenate

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import GleanvoltError, GleanvoltRequestError
from .const import DOMAIN
from .data import GleanvoltRuntime


def resolve(data: dict[str, Any] | None, path: str) -> Any:
    """``dayPlan.evBudgetWh`` -> the value, or None anywhere along the way."""
    value: Any = data
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def device_info(runtime: GleanvoltRuntime) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, runtime.system_id)},
        name=runtime.system_name,
        manufacturer="Gleanvolt",
        model="Charging controller",
        sw_version=runtime.version,
        configuration_url=runtime.client.base_url,
    )


class GleanvoltEntity(Entity):
    """One entity of the installation's device."""

    _attr_has_entity_name = True

    def __init__(self, runtime: GleanvoltRuntime, key: str) -> None:
        self.runtime = runtime
        self._attr_translation_key = key
        self._attr_unique_id = f"{runtime.system_id}_{key}"
        self._attr_device_info = device_info(runtime)


class GleanvoltCoordinatorEntity(GleanvoltEntity, CoordinatorEntity):
    """An entity fed by one of the two polls."""

    def __init__(self, runtime: GleanvoltRuntime, key: str, coordinator: Any) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        GleanvoltEntity.__init__(self, runtime, key)


def raise_for_controller[**P, R](
    func: Callable[Concatenate[Any, P], Awaitable[R]],
) -> Callable[Concatenate[Any, P], Awaitable[R]]:
    """Turn the controller's refusal into an error the person who pressed the button sees."""

    @wraps(func)
    async def wrapper(self: Any, *args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await func(self, *args, **kwargs)
        except GleanvoltError as err:
            raise controller_error(err) from err

    return wrapper


def controller_error(err: GleanvoltError) -> HomeAssistantError:
    if isinstance(err, GleanvoltRequestError):
        return HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="refused",
            translation_placeholders={"message": err.message},
        )
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="cannot_connect",
        translation_placeholders={"error": str(err)},
    )
