# Ferroamp Control for Home Assistant

A writable control driver for the **Ferroamp Energy Hub** that implements the
[EMS inverter contract](https://github.com/beolink/ha-ems) so it can be
orchestrated by `ha-ems` (EMS Steward). It exposes the mode selector and battery
power setpoint and actuates the hub over its local **MQTT ExtAPI**.

## Status — v0.2 (MQTT ExtAPI, control OFF by default, hub answers paired)

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
| `sensor.ferroamp_last_command` | `idle` / `pending` / `ack` / `nak`: the hub's answer to the latest command, with `last_command` (and in it `refreshed_at` once the command has been sent again), `last_ack`, `last_nak`, `last_result` as attributes |
| `binary_sensor.ferroamp_following` | on = the hub acknowledged the latest command, off = it refused it (NAK); EMS raises a Repairs issue after two ticks of NAK |

Telemetry sensors (`sensor.ferroamp_soc`, `_battery_power`, `_grid_power`,
`_solar_power`, `_battery_capacity`) are consumed by EMS directly from the
`ferroamp` telemetry integration and are not re-published here.

See `custom_components/ems/inverter_contract.py` in the EMS repo for the
authoritative contract definition.

### The hub answers back (0.2.0)

Every command carries a `transId`; the hub answers on
`<base_topic>/control/response` (receipt: `ack` "sending cmd to ESOs", or
`nak`, typically "transaction in progress") and on
`<base_topic>/control/result` (outcome: "all ESOs have changed setting").
The driver subscribes to both, pairs the answers with what it sent and
shows the verdict on `sensor.ferroamp_last_command` and
`binary_sensor.ferroamp_following`. A NAK is logged as a warning. Answers to
transactions the driver did not send (another app or integration commanding
the same hub) are ignored and counted in the `unmatched` attribute, which is
the quickest way to see that something else is talking to the hub. A command
the hub refused is published again on the next write even when the setpoint
is unchanged (0.2.1); EMS Steward 0.30's recovery from a NAK depends on it.

### A standing command is sent again (0.3.6)

The hub can drop an ExtAPI command without a word: when a slot of its own
schedule in the Ferroamp portal begins, or when its portal settings change,
it goes back to its own logic, sends no NAK, and
`binary_sensor.ferroamp_following` stays on. Until 0.3.5 the driver
published only when the command changed, so the hub could stay on its own
logic for hours while the setpoint said charge or hold. The same command
sent again takes the battery back within half a minute, so a charge or
discharge that has stood for five minutes (`REFRESH_S`, 300 s) is now
published again:

- **with the next write** of the setpoint. EMS writes it on every tick, so
  with its default five-minute tick each tick sends a standing charge or
  hold again, as that tick's one transaction.
- **from the driver's own timer** when nothing writes: EMS stopped without
  handing the hub back, a setpoint set by hand, or EMS ticking less often
  than every five minutes. The timer fires five and a half minutes after
  the last write and then every five minutes, which keeps it half a minute
  off EMS's whole-minute ticks. The hub needs about ten seconds to apply a
  command and refuses one that arrives meanwhile ("transaction in
  progress"), so a refresh just ahead of EMS's next, changed command would
  cost that command a tick.

`auto` is never sent again: re-sending it makes the hub re-ramp its
self-consumption. A refresh waits while a transaction is still open (sent,
no result yet), so refreshes cannot pile NAKs onto the hub, and a NAK is
handled as before: the command is forgotten and the next write sends it. A
refresh keeps the hub's verdict until the hub answers it, so
`binary_sensor.ferroamp_following` does not blink, and `last_command` keeps
the time the command was given, with the latest repeat as `refreshed_at`.
Switching control off, or unloading the entry, stops the timer, an unload
for good even while a publish is still on its way to the broker; after a
restart it starts with the first command. While a charge or hold stands
that is one more transaction every five minutes, at most 288 a day.

## Roadmap

- **A test that holds the report to stats.py's key list.** `stats.py` passes
  only the keys in its `EXTRA_KEYS` on; anything else `stats_extra` builds is
  dropped without a word. Read `EXTRA_KEYS` from stats.py and check that every
  key the report builds is in it, so a dropped key fails locally. (The shared
  file itself was synced from ha-ctc in 0.3.3.)
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

## Anonymous statistics

The driver sends one report per day to <https://stats.rnet.se>: which version
you run, your Home Assistant version and installation type, the country you
have set in Home Assistant, an approximate position rounded to about 11 km, the
battery power it is allowed to command, whether control is enabled and has
actually been used, whether the grid limit is in use, and how many commands the
hub refused since the last report.

No power readings, no energy, no time series: this driver commands a hub, it
does not meter a house. It never sends a name, an address, an exact position, a
serial number, an MQTT topic or an entity name, and your IP address is not
stored. The refusal count is the one number that says whether the driver
actually works in the field, which is exactly what a maintainer cannot see from
one installation.

To opt out: *Settings, Devices and services, Ferroamp Control, Configure, Send
anonymous usage statistics.* Switching it off also erases what has already been
sent. The full list of fields and the reasoning:
<https://stats.rnet.se/integritet>.

## License

Apache License 2.0, see [LICENSE](LICENSE).
