# Ferroamp Control for Home Assistant

A writable control driver for the **Ferroamp Energy Hub** that implements the
[EMS inverter contract](https://github.com/beolink/ha-ems) so it can be
orchestrated by `ha-ems` (EMS Steward). It exposes the mode selector and battery
power setpoint and actuates the hub over its local **MQTT ExtAPI**.

## Status — v0.1 (MQTT ExtAPI, control OFF by default)

The driver is implemented against Ferroamp's local MQTT ExtAPI. It publishes
`charge` / `discharge` / `auto` commands to `<base_topic>/control/request`
(requires the ExtAPI / EMS option to be enabled on your hub).

**Safety first — nothing reaches the battery until you opt in:**

1. A per-entry **`switch.ferroamp_control_enabled`** defaults **OFF**. While
   off, the driver builds no command and publishes nothing.
2. EMS ships in read-only mode, so it won't even write to these entities until
   you disable *its* read-only switch.

So you can install, configure and wire everything up, watch what EMS *would*
send in the logs, and only flip control on once you trust it.

Telemetry (SoC, powers, capacity) still comes from the existing read-only
[`ferroamp`](https://github.com/henricm/ha-ferroamp) MQTT integration — install
this driver *alongside* it. This driver provides only the writable surface.

### Verify against your hub before enabling control

- **Base topic** — default `extapi`; commands go to `extapi/control/request`.
  Confirm your hub's ExtAPI topic (some setups namespace it differently).
- **Command format** — `{"transId": "<uuid>", "cmd": {"name": "charge",
  "arg": "<watts>"}}`, `discharge` likewise, `auto` to hand back. Confirm
  against your ExtAPI documentation.
- With control still OFF, set `number.ferroamp_battery_power_setpoint` manually
  and check the log line `Ferroamp control → …` shows the payload you expect.

## Inverter contract (entities exposed)

| Entity | Purpose |
|--------|---------|
| `switch.ferroamp_control_enabled` | Master gate — OFF by default |
| `select.ferroamp_mode` | `self_consumption`, `peak_shaving`, `forced_charge`, `forced_discharge`, `idle` |
| `number.ferroamp_battery_power_setpoint` | W, ± (charge / discharge → ExtAPI command) |
| `number.ferroamp_grid_power_limit` | W, advisory peak cap (peak shaving realised via setpoint) |

Telemetry sensors (`sensor.ferroamp_soc`, `_battery_power`, `_grid_power`,
`_solar_power`, `_battery_capacity`) are consumed by EMS directly from the
`ferroamp` telemetry integration and are not re-published here.

See `custom_components/ems/inverter_contract.py` in the EMS repo for the
authoritative contract definition.

## Roadmap

- **Modbus TCP** transport as an alternative to MQTT, once a verified Ferroamp
  register map is available (the config flow is structured to add it).

## Why a separate plugin?

Brand-specific control logic doesn't belong in the brand-agnostic EMS. Each
inverter family gets its own driver repo; users install the driver matching
their hardware. Future siblings:

- `ha-solaredge-control`
- `ha-huawei-control`
- `ha-victron-control`

## Disclaimer

Not affiliated with Ferroamp AB.
