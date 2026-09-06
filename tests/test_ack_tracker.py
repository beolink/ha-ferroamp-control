"""Pairing commands with the hub's ack / nak (F42).

The hub answers on control/response (receipt) and control/result (outcome),
each carrying the request's transId. The tracker pairs them with what was
sent, ignores answers to someone else's commands, and says whether the hub
follows the LATEST command; that is what the status sensor, the following
binary sensor and EMS's inverter_not_following Repairs issue read.
"""

import json

from custom_components.ferroamp_control.ack_tracker import (
    KIND_RESPONSE,
    KIND_RESULT,
    PENDING_TTL_S,
    CommandTracker,
    parse_control_message,
)
from custom_components.ferroamp_control.mqtt_control import answer_topics, request_topic


def _answer(trans_id, status, msg):
    return json.dumps({"transId": trans_id, "status": status, "msg": msg})


def test_the_topics_follow_the_base_topic():
    assert request_topic("extapi") == "extapi/control/request"
    assert answer_topics("extapi/") == {"response": "extapi/control/response",
                                        "result": "extapi/control/result"}


def test_parser_reads_the_hub_payload_and_tolerates_noise():
    assert parse_control_message(_answer("t1", "ack", "sending cmd to ESOs")) == (
        "t1", "ack", "sending cmd to ESOs")
    assert parse_control_message(_answer("t1", "NAK", "transaction in progress")) == (
        "t1", "nak", "transaction in progress")
    # No status: the verdict is the start of the message.
    assert parse_control_message(json.dumps({"transId": "t2", "msg": "ack: sending"})) == (
        "t2", "ack", "ack: sending")
    assert parse_control_message("not json") == (None, None, "not json")
    assert parse_control_message(json.dumps([1, 2])) == (None, None, "[1, 2]")
    assert parse_control_message(json.dumps({"status": "ack"})) == (None, "ack", "")


def test_ack_on_response_and_result_means_following():
    tr = CommandTracker()
    assert tr.status == "idle" and tr.following is None
    tr.sent("t1", "charge", "3000", at=100.0)
    assert tr.status == "pending" and tr.pending == {"t1": {"cmd": {"name": "charge", "arg": "3000"}, "sent_at": 100.0}}
    assert tr.receive(KIND_RESPONSE, _answer("t1", "ack", "sending cmd to ESOs"), 100.5) == "ack"
    assert tr.following is True and tr.status == "ack"
    assert tr.last_ack["msg"] == "sending cmd to ESOs" and tr.last_ack["cmd"]["name"] == "charge"
    assert "t1" in tr.pending                       # the result is still to come
    assert tr.receive(KIND_RESULT, _answer("t1", "ack", "all ESOs have changed setting"), 102.0) == "ack"
    assert tr.last_result["verdict"] == "ack" and tr.pending == {}
    assert tr.as_attributes()["last_nak"] is None


def test_a_nak_means_not_following_until_the_next_ack():
    tr = CommandTracker()
    tr.sent("t1", "discharge", "2000", at=100.0)
    assert tr.receive(KIND_RESPONSE, _answer("t1", "nak", "transaction in progress"), 100.3) == "nak"
    assert tr.following is False and tr.status == "nak"
    assert tr.last_nak["msg"] == "transaction in progress"
    assert tr.as_attributes()["last_nak"]["cmd"] == {"name": "discharge", "arg": "2000"}
    tr.sent("t2", "discharge", "2000", at=400.0)
    assert tr.status == "pending"                   # a new command, no verdict yet
    tr.receive(KIND_RESPONSE, _answer("t2", "ack", "sending cmd to ESOs"), 400.4)
    assert tr.following is True
    assert tr.last_nak["trans_id"] == "t1"          # history is kept


def test_answers_to_other_clients_and_old_commands_do_not_change_the_verdict():
    tr = CommandTracker()
    tr.sent("t1", "charge", "3000", at=100.0)
    tr.sent("t2", "auto", None, at=101.0)
    # Someone else's transaction on the same broker.
    assert tr.receive(KIND_RESPONSE, _answer("zz", "nak", "transaction in progress"), 101.2) is None
    assert tr.following is None and tr.unmatched == 1
    # The late result of the OLD command is recorded but the hub follows t2.
    assert tr.receive(KIND_RESULT, _answer("t1", "nak", "PowerLimitsInvalid"), 101.5) == "nak"
    assert tr.following is None and tr.last_nak["trans_id"] == "t1"
    assert tr.receive(KIND_RESPONSE, _answer("t2", "ack", "sending cmd to ESOs"), 101.6) == "ack"
    assert tr.following is True
    # Garbage is counted, never raised.
    assert tr.receive(KIND_RESPONSE, "{", 102.0) is None
    assert tr.unmatched == 2


def test_unanswered_commands_expire_and_reset_forgets_the_verdict():
    tr = CommandTracker()
    tr.sent("t1", "charge", "3000", at=0.0)
    tr.sent("t2", "charge", "3500", at=PENDING_TTL_S + 1.0)
    assert "t1" not in tr.pending and "t2" in tr.pending
    assert tr.receive(KIND_RESULT, _answer("t1", "ack", "late"), PENDING_TTL_S + 2.0) is None
    tr.receive(KIND_RESPONSE, _answer("t2", "nak", "transaction in progress"), PENDING_TTL_S + 3.0)
    assert tr.following is False
    tr.reset()                                      # control switched off
    assert tr.following is None and tr.pending == {} and tr.status == "idle"
    assert tr.last_nak is not None                  # the record stays for the attributes
