# Changelog

All notable changes to Ferroamp Control are documented here. Versions follow
[Semantic Versioning](https://semver.org/); the release workflow takes the
notes for a tag from the matching `## [x.y.z]` section.

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
