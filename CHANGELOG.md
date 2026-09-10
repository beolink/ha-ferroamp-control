# Changelog

All notable changes to Ferroamp Control are documented here. Versions follow
[Semantic Versioning](https://semver.org/); the release workflow takes the
notes for a tag from the matching `## [x.y.z]` section.

## [0.3.4] - 2026-09-11

### Fixed
- An entry unloaded while its first daily report was still on the wire no
  longer arms the daily timer when the answer comes. Nothing held that
  reporter any more, so the timer could never be stopped and an old reporter
  kept sending beside the new one. The shared `stats.py` now matches EMS
  Steward 0.35.2's copy byte for byte.

## [0.3.3] — 2026-09-10

### Added
- The daily report carries `ha_id`, a hash that links the beolink plugins on
  the same Home Assistant, and the number of warnings and errors the driver
  logged since the previous report. Counts only, never a message.

## [0.3.2] - 2026-09-10

### Fixed
- **The daily report keeps going while the device is offline.** A device that
  is unreachable at start-up makes the entry raise ConfigEntryNotReady, and
  Home Assistant then retries the set-up for as long as it stays away,
  running the entry's on-unload callbacks after every failed attempt. The
  reporter was built at the end of a successful set-up and stopped by such a
  callback, so an installation went silent exactly while something was wrong
  with it. It is armed before the first call that can raise, kept in
  `hass.data` by the shared client, re-pointed rather than re-armed when a
  retry comes round, and stopped only from `async_unload_entry`. Its payload
  is resolved when the report is built, so a set-up that never finished still
  reports the installation.

### Changed
- **Apache License 2.0** instead of MIT, like the rest of the family.
- **Brand icons ship with the integration**, in
  `custom_components/ferroamp_control/brand/`, which Home Assistant reads
  since 2026.3.
- `hacs.json` names the minimum Home Assistant version.

## [0.3.1] - 2026-09-09

### Fixed
- **The verdict sensor has its own entity id.** It used to claim
  `sensor.<prefix>_control_status`, the id the Ferroamp integration's own
  control-status sensor already holds, and so ended up as
  `sensor.<prefix>_control_status_2`. It is `sensor.<prefix>_last_command`
  now (states idle, pending, ack, nak, same attributes); an existing
  registry entry is renamed once at setup.

## [0.2.1] - 2026-09-06

### Fixed
- **A refused command is sent again.** The driver publishes only when the
  command changes (0.1.1), and it remembered the command even when the hub
  answered NAK ("transaction in progress" against the previous command), so
  EMS's re-write of the same setpoint on the next tick was deduped away and
  the hub ran on the OLD command until the plan changed its setpoint: hours
  in a hold period, with EMS's *inverter_not_following* issue raised and no
  way for EMS to repair it. A NAK on the latest command now forgets the
  dedupe key, and nothing is deduped while `binary_sensor.<prefix>_following`
  is off. EMS Steward 0.30 relies on this: its hold mode changes the command
  at every quarter boundary where the plan switches between charge, hold and
  auto, so a NAK is far more common than before, and its self-healing on a
  NAK ("the next tick's re-write clears it") needs this release on the hub.

## [0.2.0] - 2026-09-06

### Added
- **The hub's answer is paired with the command.** The driver subscribes to
  `<base_topic>/control/response` (the receipt) and `<base_topic>/control/result`
  (the outcome) and matches each answer's `transId` with the command it
  published. `sensor.<prefix>_control_status` shows `idle` / `pending` /
  `ack` / `nak` with `last_command`, `last_ack`, `last_nak` and `last_result`
  as attributes, each with the hub's own message ("sending cmd to ESOs",
  "transaction in progress", "PowerLimitsInvalid"), and
  `binary_sensor.<prefix>_following` is on while the hub acknowledged the
  latest command, off after a NAK, unknown until it has answered. A NAK is
  logged as a warning; it used to be invisible outside the hub's own logs.
  EMS Steward (0.30) reads the binary sensor and raises the Repairs issue
  *inverter_not_following* after two ticks of NAK, instead of comparing
  battery power with the plan, which in auto always differs. Answers to
  another client's transactions on the same broker are ignored (counted as
  `unmatched`), commands unanswered for 60 s are forgotten, and switching
  control off clears the verdict so a NAK from last week never counts
  (EMS review F42).

## [0.1.1] - 2026-08-29

### Changed
- Only publish when the command actually changes, so a re-written `auto`
  does not make the hub re-ramp its self-consumption.

## [0.1.0] - 2026-08-28

### Added
- First release: the EMS inverter contract (mode select, battery power
  setpoint, advisory grid limit) over the local MQTT ExtAPI, control OFF by
  default.
