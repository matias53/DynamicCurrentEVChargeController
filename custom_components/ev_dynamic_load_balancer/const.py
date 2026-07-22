"""Constants for the EV Dynamic Load Balancer integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "ev_dynamic_load_balancer"

# ---------------------------------------------------------------------------
# Configuration keys — entity selection
# ---------------------------------------------------------------------------
CONF_GRID_POWER_ENTITY: Final = "grid_power_entity"
CONF_CHARGER_POWER_ENTITY: Final = "charger_power_entity"
CONF_CHARGING_STATUS_ENTITY: Final = "charging_status_entity"
CONF_CHARGING_CURRENT_ENTITY: Final = "charging_current_entity"

# ---------------------------------------------------------------------------
# Configuration keys — electrical parameters
# ---------------------------------------------------------------------------
CONF_TARGET_POWER: Final = "target_power"
CONF_EMERGENCY_POWER: Final = "emergency_power"
CONF_VOLTAGE: Final = "voltage"
CONF_PHASES: Final = "phases"
CONF_MIN_CURRENT: Final = "min_current"
CONF_MAX_CURRENT: Final = "max_current"

# ---------------------------------------------------------------------------
# Configuration keys — controller parameters
# ---------------------------------------------------------------------------
CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_DEADBAND: Final = "deadband"
CONF_MAX_STEP: Final = "max_step"
CONF_GAIN: Final = "gain"
CONF_AVERAGE_WINDOW: Final = "average_window"
CONF_RESPONSE_TIMEOUT: Final = "response_timeout"
CONF_MIN_CHANGE_INTERVAL: Final = "min_change_interval"
CONF_EMERGENCY_REDUCTION: Final = "emergency_reduction"
CONF_CURRENT_STEP: Final = "current_step"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_TARGET_POWER: Final = 7000.0
DEFAULT_EMERGENCY_POWER: Final = 8500.0
DEFAULT_VOLTAGE: Final = 230.0
DEFAULT_PHASES: Final = "single"
DEFAULT_MIN_CURRENT: Final = 6.0
DEFAULT_MAX_CURRENT: Final = 32.0

DEFAULT_UPDATE_INTERVAL: Final = 15
DEFAULT_DEADBAND: Final = 300.0
DEFAULT_MAX_STEP: Final = 2.0
DEFAULT_GAIN: Final = 0.5
DEFAULT_AVERAGE_WINDOW: Final = 30.0
DEFAULT_RESPONSE_TIMEOUT: Final = 15.0
DEFAULT_MIN_CHANGE_INTERVAL: Final = 10.0
DEFAULT_EMERGENCY_REDUCTION: Final = 6.0
DEFAULT_CURRENT_STEP: Final = 1.0

UPDATE_INTERVAL_OPTIONS: Final[list[int]] = [5, 10, 15, 20, 30, 60, 90, 120]

# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
EVENT_CURRENT_CHANGED: Final = "evdlb_current_changed"
EVENT_EMERGENCY: Final = "evdlb_emergency"
EVENT_CONTROLLER_STARTED: Final = "evdlb_controller_started"
EVENT_CONTROLLER_STOPPED: Final = "evdlb_controller_stopped"

# ---------------------------------------------------------------------------
# Event / service attributes
# ---------------------------------------------------------------------------
ATTR_ENTRY_ID: Final = "entry_id"
ATTR_OLD_CURRENT: Final = "old_current"
ATTR_NEW_CURRENT: Final = "new_current"
ATTR_GRID_POWER: Final = "grid_power"
ATTR_AVERAGE_GRID_POWER: Final = "average_grid_power"
ATTR_REASON: Final = "reason"
ATTR_EMERGENCY: Final = "emergency"

# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------
SERVICE_ENABLE: Final = "enable"
SERVICE_DISABLE: Final = "disable"
SERVICE_PAUSE: Final = "pause"
SERVICE_RESUME: Final = "resume"
SERVICE_FORCE_RECALCULATE: Final = "force_recalculate"
SERVICE_RESET_AVERAGE: Final = "reset_average"

# ---------------------------------------------------------------------------
# Coordinator level reasons (non-controller reasons)
# ---------------------------------------------------------------------------
REASON_DISABLED: Final = "disabled"
REASON_PAUSED: Final = "paused"
REASON_WRITE_FAILED: Final = "write_failed"

# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------
MANUFACTURER: Final = "EV Dynamic Load Balancer"
MODEL: Final = "Dynamic load balancing controller"
ENTITY_ID_PREFIX: Final = "evdlb"
