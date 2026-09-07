"""What the anonymous daily report may contain (stats_extra.py).

The driver commands a hub, it does not meter a house, and the report must
reflect that: sizes and counts, never a power reading and never a series.
"""

from custom_components.ferroamp_control.stats_extra import ErrorCounter, build_extra


def _extra(**kw):
    args = {"control_enabled": True, "grid_limit_w": None, "max_charge_w": 7000,
            "max_discharge_w": 9000, "commanded": True, "naks": 0}
    args.update(kw)
    return build_extra(**args)


def test_report_holds_only_the_agreed_keys():
    extra = _extra()
    assert set(extra) == {"models", "features", "metrics", "errors"}
    assert set(extra["features"]) == {"control", "commanded", "grid_limit"}
    assert extra["models"] == ["energyhub"]


def test_battery_power_is_the_larger_direction_in_kw():
    assert _extra()["metrics"]["battery_kw"] == 9.0


def test_an_unconfigured_power_is_left_out_rather_than_sent_as_zero():
    assert _extra(max_charge_w=0, max_discharge_w=0)["metrics"] == {}


def test_grid_limit_is_reported_as_used_or_not_never_its_value():
    assert _extra(grid_limit_w=None)["features"]["grid_limit"] is False
    on = _extra(grid_limit_w=11000)
    assert on["features"]["grid_limit"] is True
    assert 11000 not in on["metrics"].values()


def test_refusals_are_counted_never_their_messages():
    extra = _extra(naks=3)
    assert extra["errors"] == 3
    for value in extra["features"].values():
        assert isinstance(value, bool)


def test_error_counter_reports_the_change_since_last_time():
    counter = ErrorCounter()
    assert counter.delta(0) == 0
    assert counter.delta(2) == 2
    assert counter.delta(2) == 0


def test_error_counter_survives_a_reload():
    counter = ErrorCounter()
    counter.delta(9)
    assert counter.delta(1) == 1
