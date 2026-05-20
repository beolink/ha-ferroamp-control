# Ferroamp Control for Home Assistant

A control driver for the **Ferroamp Energy Hub** that implements the
[EMS inverter contract](https://github.com/andrei/ha-ems) so it can be
orchestrated by `ha-ems`. It exposes mode selection, battery power setpoints
and the standard sensor surface.

## Status — Phase 2 (planned)

**This driver is currently a scaffold only.** Phase 1 of the EMS project uses
a built-in mock inverter for safe development. Once the EMS interface is
stable, this driver will be implemented against:

- **Modbus TCP** (primary, planned)
- MQTT (possible alternative — requires EMS license, has slightly different
  semantics)

It will *not* replace the existing read-only
[`ferroamp`](https://github.com/henricm/ha-ferroamp) HACS integration —
that integration provides excellent telemetry via MQTT, and this driver is
intended to be installed *alongside* it for the writable control surface.

## Inverter contract (entities to be exposed)

| Entity | Purpose |
|--------|---------|
| `select.ferroamp_mode` | `self_consumption`, `peak_shaving`, `forced_charge`, `forced_discharge`, `idle` |
| `number.ferroamp_battery_power_setpoint` | W, ± (charge / discharge) |
| `number.ferroamp_grid_power_limit` | W, peak shaving cap |
| `sensor.ferroamp_soc` | % |
| `sensor.ferroamp_battery_capacity` | kWh |
| `sensor.ferroamp_battery_power` | W, ± (actual) |
| `sensor.ferroamp_grid_power` | W, ± (actual exchange) |
| `sensor.ferroamp_solar_power` | W (current PV production) |

See `custom_components/ems/inverter_contract.py` in the EMS repo for the
authoritative definition.

## Why a separate plugin?

Brand-specific control logic doesn't belong in the brand-agnostic EMS. Each
inverter family gets its own driver repo; users install the driver matching
their hardware. Future siblings:

- `ha-solaredge-control`
- `ha-huawei-control`
- `ha-victron-control`

## Disclaimer

Not affiliated with Ferroamp AB.
