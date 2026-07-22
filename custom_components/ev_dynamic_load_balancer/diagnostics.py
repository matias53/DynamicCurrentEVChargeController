"""Diagnostics support for the EV Dynamic Load Balancer."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import EVDLBConfigEntry, merged_config


def _serialize(value: Any) -> Any:
    """Make a value JSON serializable."""
    if isinstance(value, datetime):
        return value.isoformat()
    return value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: EVDLBConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator
    data = (
        {key: _serialize(value) for key, value in asdict(coordinator.data).items()}
        if coordinator.data
        else None
    )
    return {
        "config": merged_config(entry),
        "controller_status": {
            "enabled": coordinator.enabled,
            "paused": coordinator.paused,
            "awaiting_response": coordinator.controller.awaiting_response,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval
                else None
            ),
            "last_update_success": coordinator.last_update_success,
        },
        "controller": coordinator.controller.snapshot(),
        "data": data,
    }
