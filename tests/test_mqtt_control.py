"""Command translation: signed setpoint → Ferroamp ExtAPI command."""

from custom_components.ferroamp_control.mqtt_control import build_payload, command_for
from custom_components.ferroamp_control.const import CMD_AUTO, CMD_CHARGE, CMD_DISCHARGE


def test_positive_setpoint_charges_clamped():
    name, watts = command_for(3000, max_charge_w=5000, max_discharge_w=5000)
    assert name == CMD_CHARGE and watts == 3000
    name, watts = command_for(9000, max_charge_w=5000, max_discharge_w=5000)
    assert name == CMD_CHARGE and watts == 5000  # clamped to max charge


def test_negative_setpoint_discharges_clamped():
    name, watts = command_for(-2000, max_charge_w=5000, max_discharge_w=4000)
    assert name == CMD_DISCHARGE and watts == 2000
    name, watts = command_for(-9000, max_charge_w=5000, max_discharge_w=4000)
    assert name == CMD_DISCHARGE and watts == 4000


def test_zero_setpoint_hands_back_to_auto():
    name, watts = command_for(0, max_charge_w=5000, max_discharge_w=5000)
    assert name == CMD_AUTO and watts is None


def test_payload_shape():
    p = build_payload(CMD_CHARGE, 1500)
    assert p["cmd"] == {"name": "charge", "arg": "1500"}
    assert "transId" in p and isinstance(p["transId"], str)
    p2 = build_payload(CMD_AUTO)
    assert p2["cmd"] == {"name": "auto"}
