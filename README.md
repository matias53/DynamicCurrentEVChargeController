# EV Dynamic Load Balancer

A manufacturer-independent dynamic load balancing controller for EV chargers in [Home Assistant](https://www.home-assistant.io/).

The integration continuously adjusts the charging current of your EV charger so the **total imported grid power never exceeds a configurable target** — letting you charge as fast as possible without tripping your main breaker or exceeding your contracted power.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Overview

Most homes have a limited grid connection (e.g. 7 kW). An EV charger can easily consume most of it. When the oven, air conditioning or water heater turn on, the total demand can exceed the limit and trip the main breaker.

This integration solves the problem with a **proportional feedback controller**:

- When the house consumes little power, the charging current is raised.
- When other appliances turn on, the charging current is lowered.
- When consumption spikes above an emergency threshold, current is shed **immediately**.

It works with **any** EV charger — Tuya, OCPP, Wallbox, Easee, Zaptec, ESPHome DIY builds, anything — as long as it exposes a **Number entity** for the charging current. There is no manufacturer-specific code whatsoever. You simply select four existing Home Assistant entities:

| Role | Example | Description |
|---|---|---|
| Grid power sensor | `sensor.consumo_ute` | Instantaneous imported grid power (W or kW) |
| Charger power sensor | `sensor.cargadorauto_power` | EV charger power (W or kW) |
| Charging status | `binary_sensor.ev_charger_status` | ON while the vehicle charges |
| Charging current | `number.chargepoint_set_charge_current` | Sets the charging current in Amps |

## Features

- ✅ **Fully UI configurable** — config flow + options flow, no YAML
- ✅ **Manufacturer independent** — works with any Number-based charger
- ✅ **Proportional controller** with configurable gain (0.1 – 2.0)
- ✅ **Moving average** of grid power (configurable window) — never reacts to raw spikes
- ✅ **Deadband / hysteresis** — no oscillation around the target
- ✅ **Rate limiting** — max step per cycle + minimum time between changes
- ✅ **Response awareness** — after writing a current, waits until the charger power actually changes (or a timeout expires) before commanding again
- ✅ **Emergency mode** — instant current shedding when a hard threshold is exceeded
- ✅ **Single and three phase** installations
- ✅ **kW → W conversion** — power sensors reported in kW are handled automatically
- ✅ Diagnostic sensors, enable switch, services, events and downloadable diagnostics
- ✅ Pure-Python controller core, fully covered by unit tests

## Installation

### HACS (recommended)

1. In HACS, open **⋮ → Custom repositories**.
2. Add this repository URL with category **Integration**.
3. Search for **EV Dynamic Load Balancer** and install it.
4. Restart Home Assistant.

### Manual

1. Copy `custom_components/ev_dynamic_load_balancer/` into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

Go to **Settings → Devices & Services → Add Integration → EV Dynamic Load Balancer**. The wizard has three steps:

### 1. Entities

| Setting | Notes |
|---|---|
| Grid power sensor | Must report imported grid power in W or kW |
| Charger power sensor | Used to detect that the charger reacted to a command |
| Charging status entity | `binary_sensor`, `switch` or `input_boolean`; ON = charging |
| Charging current number | The Number entity that sets Amps on your charger |

### 2. Electrical parameters

| Setting | Default | Description |
|---|---|---|
| Target power | 7000 W | The controller keeps average grid import at/below this |
| Emergency power | 8500 W | Above this, current is shed immediately |
| Voltage | 230 V | Nominal phase voltage |
| Phases | Single | Single or three phase charger connection |
| Minimum current | 6 A | Never set below (most EVs stop charging < 6 A) |
| Maximum current | 32 A | Never set above |

### 3. Controller tuning

| Setting | Default | Description |
|---|---|---|
| Execution interval | 15 s | How often the controller runs (5–120 s) |
| Deadband | 300 W | No action while the error is inside this band |
| Max current change per cycle | 2 A | Upper bound on each adjustment |
| Gain | 0.5 | Proportional gain (0.1 gentle … 2.0 aggressive) |
| Moving average window | 30 s | Smoothing applied to grid power |
| Response timeout | 15 s | Max wait for the charger to react to a command |
| Min time between changes | 10 s | Cooldown between consecutive writes |
| Emergency reduction | 6 A | Amps shed instantly in emergency mode |
| Current resolution | 1 A | Computed current is rounded to this step |

All settings can be changed later via **Configure** on the integration card. Changes apply immediately (the entry reloads).

## Algorithm

Every execution interval the controller:

1. **Exits** if the vehicle is not charging.
2. Reads grid power, charger power and the current setpoint; **rejects** `unknown` / `unavailable` states.
3. Pushes the grid power sample into a **time-based circular buffer** and computes the moving average.
4. **Emergency check** (uses the *raw* instantaneous grid power):
   `grid_power > emergency_power` → immediately reduce the current by the configured emergency reduction, bypassing everything else.
5. If a previous command is still **awaiting a charger response**, waits until the charger power moves (≥ 100 W) or the response timeout expires.
6. Computes the error: `error = target_power − average_grid_power`.
7. **Deadband**: if `|error| ≤ deadband`, do nothing.
8. Converts Watts to Amps:
   - Single phase: `delta = error / voltage`
   - Three phase: `delta = error / (√3 × voltage)`
9. Applies the **gain**: `delta *= gain`.
10. Limits the step to `± max_step`, rounds to the current resolution, and clamps to `[min_current, max_current]`.
11. Skips if the result equals the present current, or if the last change was less than *min time between changes* ago.
12. Writes the Number entity and starts waiting for the charger to react.

The controller is deliberately conservative: it prefers a few well-damped adjustments over rapid oscillation, which is friendlier to the charger, the vehicle's onboard charger, and your relays.

### Tuning tips

- **Oscillates around the target?** Lower the gain, raise the deadband, or lengthen the average window.
- **Reacts too slowly to load changes?** Raise the gain, shorten the interval and the average window.
- **Breaker still trips on big spikes?** Lower the emergency power threshold and/or raise the emergency reduction.

## Entities

| Entity | Description |
|---|---|
| `sensor.evdlb_error` | Current control error (target − average) in W |
| `sensor.evdlb_average_grid_power` | Moving average of grid power in W |
| `sensor.evdlb_target_power` | Configured target power |
| `sensor.evdlb_delta_current` | Last applied current delta in A |
| `sensor.evdlb_next_current` | Last computed current setpoint in A |
| `sensor.evdlb_last_execution` | Timestamp of the last controller cycle |
| `sensor.evdlb_last_reason` | Why the last cycle did (or didn't) act |
| `binary_sensor.evdlb_controller_active` | ON while enabled, not paused and charging |
| `binary_sensor.evdlb_emergency` | ON while an emergency reduction is in effect |
| `switch.evdlb_enabled` | Master enable switch (state survives restarts) |

> Entity ids are suggestions; if you run multiple instances Home Assistant will suffix them.

## Services

All services accept an optional `entry_id` (pick the instance in the UI); when omitted they target every loaded instance.

| Service | Description |
|---|---|
| `ev_dynamic_load_balancer.enable` | Enable the controller |
| `ev_dynamic_load_balancer.disable` | Disable the controller |
| `ev_dynamic_load_balancer.pause` | Pause temporarily (e.g. during a boost charge) |
| `ev_dynamic_load_balancer.resume` | Resume a paused controller |
| `ev_dynamic_load_balancer.force_recalculate` | Run one cycle immediately |
| `ev_dynamic_load_balancer.reset_average` | Clear the moving average buffer |

## Events

| Event | Fired when |
|---|---|
| `evdlb_current_changed` | A new current was written (payload: old/new current, grid power, reason) |
| `evdlb_emergency` | An emergency reduction occurred |
| `evdlb_controller_started` | The controller was set up or enabled |
| `evdlb_controller_stopped` | The controller was unloaded or disabled |

Example automation — notify on emergency:

```yaml
automation:
  - alias: Notify on EV emergency reduction
    trigger:
      - platform: event
        event_type: evdlb_emergency
    action:
      - service: notify.mobile_app_phone
        data:
          message: >
            Grid overload! Charging current reduced from
            {{ trigger.event.data.old_current }} A to
            {{ trigger.event.data.new_current }} A.
```

## Architecture

```
custom_components/ev_dynamic_load_balancer/
├── controller.py     ← pure control algorithm (zero HA imports, unit tested)
├── coordinator.py    ← DataUpdateCoordinator: reads entities, applies decisions
├── config_flow.py    ← initial UI setup wizard
├── options_flow.py   ← reconfiguration wizard + shared form schemas
├── sensor.py         ← diagnostic sensors
├── binary_sensor.py  ← controller active / emergency
├── switch.py         ← enable switch (restores state)
├── services.py       ← domain services
├── diagnostics.py    ← downloadable diagnostics
├── entity.py         ← shared entity base (device, unique ids)
└── const.py          ← configuration keys, defaults, event names
```

The design principle: **`controller.py` knows nothing about Home Assistant**. It receives plain values (`ControllerInputs`) and returns decisions (`ControlDecision`). The coordinator is a thin adapter that reads entity states, executes decisions via `number.set_value`, and fires events. This separation is what makes the algorithm fully unit-testable.

Scheduling uses the coordinator's internal asyncio interval — no `time_pattern` automations, no polling helpers.

## Diagnostics

Open the integration → **⋮ → Download diagnostics** to get a JSON snapshot including the full configuration, controller state, moving average buffer contents, the last decision, and runtime statistics (cycles, commands sent, emergencies, response timeouts, skip reasons). Attach this file to bug reports.

Enable debug logging with:

```yaml
logger:
  logs:
    custom_components.ev_dynamic_load_balancer: debug
```

## FAQ

**Does it support solar excess charging?**
Not yet — the current algorithm targets a grid import ceiling. Solar-aware charging (target = export surplus) is on the roadmap.

**My grid sensor reports kW, not W.**
That's fine. Power sensors with a `kW` unit are converted to W automatically.

**My charger only accepts whole Amps.**
That's the default (`current resolution = 1 A`). If your charger accepts finer steps, lower the resolution in the options.

**Can I run multiple chargers?**
Yes — add one integration instance per charger. Note they don't (yet) coordinate with each other; give each a share of your total headroom.

**What happens if a sensor becomes unavailable?**
The cycle is skipped and `sensor.evdlb_last_reason` shows *Invalid input*. The controller never acts on `unknown`/`unavailable` data.

**Why didn't the current change even though the error is large?**
Check `sensor.evdlb_last_reason`: the controller may be inside the deadband, rate limited, or awaiting the charger's response to the previous command.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Current never changes | Charging status entity is not ON; verify it reports `on` while charging |
| `Write failed` reason | The Number entity rejected the value — check its min/max/step |
| Oscillation | Gain too high or deadband too small; also lengthen the average window |
| Slow reaction | Interval or average window too long, gain too low |
| Breaker trips despite controller | Lower emergency power, raise emergency reduction, shorten the interval |
| Entities missing after restart | Check the log for warnings about missing source entities |

## Future roadmap

- Solar/excess-aware charging target
- Per-phase current sensors and per-phase balancing
- Multiple charger coordination (shared headroom arbitration)
- Optional PI(D) control mode
- Energy dashboards / long-term statistics helpers
- Publication in the HACS default repository

## Contributing

PRs are welcome. Please keep the controller core (`controller.py`) free of Home Assistant imports, add unit tests for algorithm changes, and make sure `ruff check`, `ruff format` and `pytest` pass.

## License

[MIT](LICENSE) © 2026 Matias Settimo
