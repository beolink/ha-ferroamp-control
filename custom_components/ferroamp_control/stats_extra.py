"""What this driver contributes to the anonymous daily report.

Free of Home Assistant imports on purpose, so the tests can prove without a
Home Assistant installation that only agreed numbers leave. Everything here is
either the plant's own size or a count of what the hub answered. No power
readings, no energy, no time series: this driver commands the hub, it does not
meter the house.

See https://stats.rnet.se/integritet for the full list and the reasoning.
"""

from __future__ import annotations

from typing import Any

#: The hub this driver speaks to. Fixed, never taken from the device.
MODEL = "energyhub"


class ErrorCounter:
    """Turns a cumulative nak count into 'since the previous report'.

    A reload starts the tracker over, so a value below the one seen last time
    means a fresh start, not a negative number of refusals.
    """

    def __init__(self) -> None:
        self._seen = 0

    def delta(self, total: int) -> int:
        if total < self._seen:
            self._seen = 0
        change = total - self._seen
        self._seen = total
        return change


def build_extra(
    *,
    control_enabled: bool,
    grid_limit_w: float | None,
    max_charge_w: float | None,
    max_discharge_w: float | None,
    commanded: bool,
    naks: int,
) -> dict[str, Any]:
    """Assemble the driver's part of the report.

    ``naks`` is how many commands the hub refused since the last report, which
    is the one number that says whether this driver actually works in the
    field. Nothing about it identifies a house.
    """
    metrics: dict[str, float] = {}
    power_w = max(float(max_charge_w or 0.0), float(max_discharge_w or 0.0))
    if power_w:
        metrics["battery_kw"] = round(power_w / 1000.0, 1)

    return {
        "models": [MODEL],
        "features": {
            # Whether the driver is allowed to write at all, whether it has
            # ever written, and whether the grid limit is in use.
            "control": bool(control_enabled),
            "commanded": bool(commanded),
            "grid_limit": grid_limit_w is not None,
        },
        "metrics": metrics,
        "errors": max(0, int(naks)),
    }
