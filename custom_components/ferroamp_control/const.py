"""Constants for the Ferroamp Control driver."""

from __future__ import annotations

DOMAIN = "ferroamp_control"

# Config keys
CONF_PREFIX = "prefix"              # entity prefix, must match what EMS drives
CONF_BASE_TOPIC = "base_topic"      # Ferroamp ExtAPI MQTT base topic
CONF_MAX_CHARGE_W = "max_charge_w"
CONF_MAX_DISCHARGE_W = "max_discharge_w"

DEFAULT_PREFIX = "ferroamp"
DEFAULT_BASE_TOPIC = "extapi"       # commands go to "<base>/control/request"
DEFAULT_MAX_W = 5000

# Inverter contract modes — must stay identical to ha-ems const.INVERTER_MODES.
MODE_SELF_CONSUMPTION = "self_consumption"
MODE_PEAK_SHAVING = "peak_shaving"
MODE_FORCED_CHARGE = "forced_charge"
MODE_FORCED_DISCHARGE = "forced_discharge"
MODE_IDLE = "idle"
INVERTER_MODES = [
    MODE_SELF_CONSUMPTION,
    MODE_PEAK_SHAVING,
    MODE_FORCED_CHARGE,
    MODE_FORCED_DISCHARGE,
    MODE_IDLE,
]

# Ferroamp ExtAPI command names.
CMD_CHARGE = "charge"
CMD_DISCHARGE = "discharge"
CMD_AUTO = "auto"

# A standing charge or discharge is published again once it has stood this
# long (0.3.6): the hub can drop a command without a word (runtime.py).
REFRESH_S = 300.0
# How far the refresh keeps out of the writer's way: a write refreshes once
# the command has stood REFRESH_S less this, and the driver's own timer
# fires REFRESH_S plus this after the last write (runtime._arm_refresh).
REFRESH_OFFSET_S = 30.0

# Must match OPTION_KEY in stats.py. Kept here so config_flow can build its
# schema without importing stats.py, which pulls in Home Assistant.
CONF_SEND_STATISTICS = "send_statistics"
