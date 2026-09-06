"""Pair every published command with the hub's answer (F42).

The EnergyHub answers a ``control/request`` twice, both carrying the
request's ``transId``:

* ``<base_topic>/control/response`` — the receipt: ``ack`` ("sending cmd
  to ESOs") when the command was accepted, ``nak`` when it was refused
  (typically "transaction in progress": the previous command is still
  being applied, or another controller is talking to the hub).
* ``<base_topic>/control/result`` — the outcome once the ESOs have applied
  it ("all ESOs have changed setting"), again ``ack`` or ``nak``.

Payloads are JSON ``{"transId": "...", "status": "ack"|"nak", "msg": "..."}``
as observed on VSH's hub (2026-08-29). The parser is tolerant about case
and about a missing ``status`` (then the verdict is read from the start of
``msg``), and ignores answers whose ``transId`` it never sent: those belong
to another client on the same broker.

Pure Python, no Home Assistant: the tracker is what the tests exercise; the
runtime feeds it and the entities read it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

KIND_RESPONSE = "response"
KIND_RESULT = "result"
KINDS = (KIND_RESPONSE, KIND_RESULT)

VERDICT_ACK = "ack"
VERDICT_NAK = "nak"

# A command the hub has not answered within this many seconds is forgotten:
# a late answer would otherwise be paired with a stale command, and the
# pending list would grow with every lost message. The hub's response
# arrives within a second on VSH; result within a few. 60 s is generous.
PENDING_TTL_S = 60.0


def parse_control_message(payload: str) -> tuple[str | None, str | None, str]:
    """``(trans_id, verdict, msg)`` from an answer payload. ``verdict`` is
    ``"ack"``, ``"nak"`` or None when the payload says neither; ``trans_id``
    None when the payload is not JSON or carries no transId."""
    try:
        data = json.loads(payload)
    except (TypeError, ValueError):
        return None, None, str(payload)[:200]
    if not isinstance(data, dict):
        return None, None, str(payload)[:200]
    trans_id = data.get("transId") or data.get("transid") or data.get("trans_id")
    msg = str(data.get("msg") or data.get("message") or "")
    status = str(data.get("status") or "").strip().lower()
    verdict = None
    if status in (VERDICT_ACK, "acked", "ok", "success"):
        verdict = VERDICT_ACK
    elif status in (VERDICT_NAK, "nack", "error", "fail", "failed"):
        verdict = VERDICT_NAK
    elif not status:
        head = msg.strip().lower()
        if head.startswith(VERDICT_ACK):
            verdict = VERDICT_ACK
        elif head.startswith(VERDICT_NAK):
            verdict = VERDICT_NAK
    return (str(trans_id) if trans_id else None), verdict, msg


@dataclass
class CommandTracker:
    """What was sent, what the hub said back, and whether it follows.

    ``following`` is the hub's verdict on the LATEST command sent: True on
    ack (response or result), False on nak, None until the hub has
    answered anything (or after a reset). An answer to an older command
    is still recorded in ``last_ack`` / ``last_nak`` / ``last_result``,
    but does not change ``following``: the hub follows what it was told
    last.
    """

    pending: dict = field(default_factory=dict)     # transId -> {cmd, sent_at}
    latest_trans_id: str | None = None
    last_command: dict | None = None                # {name, arg, trans_id, at}
    last_ack: dict | None = None                    # {kind, msg, cmd, at}
    last_nak: dict | None = None
    last_result: dict | None = None                 # the last control/result
    following: bool | None = None
    unmatched: int = 0                              # answers to someone else's commands

    def sent(self, trans_id: str, name: str, arg: str | None, at: float) -> None:
        cmd = {"name": name, "arg": arg}
        self.expire(at)
        self.pending[trans_id] = {"cmd": cmd, "sent_at": at}
        self.latest_trans_id = trans_id
        self.last_command = {**cmd, "trans_id": trans_id, "at": at}
        # A new command has no verdict yet; the old one's does not carry over.
        self.following = None

    def expire(self, now: float) -> None:
        for tid in [t for t, p in self.pending.items() if now - p["sent_at"] > PENDING_TTL_S]:
            self.pending.pop(tid, None)

    def receive(self, kind: str, payload: str, at: float) -> str | None:
        """Feed one answer. Returns the verdict when it concerned a command
        we sent (``"ack"`` / ``"nak"``), None when it did not."""
        trans_id, verdict, msg = parse_control_message(payload)
        if trans_id is None or verdict is None:
            self.unmatched += 1
            return None
        entry = self.pending.get(trans_id)
        if entry is None:
            self.unmatched += 1
            return None
        record = {"kind": kind, "msg": msg, "cmd": entry["cmd"], "trans_id": trans_id, "at": at}
        if verdict == VERDICT_ACK:
            self.last_ack = record
        else:
            self.last_nak = record
        if kind == KIND_RESULT:
            self.last_result = {**record, "verdict": verdict}
            # The result closes the transaction; a response alone keeps it
            # pending for its result (or the TTL).
            self.pending.pop(trans_id, None)
        if trans_id == self.latest_trans_id:
            self.following = verdict == VERDICT_ACK
        return verdict

    def reset(self) -> None:
        """Forget every verdict (control switched off): the hub is on its
        own and there is nothing for it to follow."""
        self.pending.clear()
        self.latest_trans_id = None
        self.following = None

    @property
    def status(self) -> str:
        """One word for the status sensor: idle / pending / ack / nak."""
        if self.last_command is None or self.latest_trans_id is None:
            return "idle"
        if self.following is None:
            return "pending"
        return VERDICT_ACK if self.following else VERDICT_NAK

    def as_attributes(self) -> dict:
        return {
            "last_command": self.last_command,
            "last_ack": self.last_ack,
            "last_nak": self.last_nak,
            "last_result": self.last_result,
            "pending": len(self.pending),
            "unmatched": self.unmatched,
        }
