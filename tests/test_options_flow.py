"""The entry's settings flow opens on Home Assistant 2025.12 and later.

From 2025.12 ``OptionsFlow.config_entry`` is a property without a setter,
and a flow that set it in ``__init__`` raised AttributeError: Configure on
the entry said the flow could not be loaded (seen on 2026.11). The flow
keeps the entry as its own ``_entry``.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

FLOW = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "ferroamp_control" / "config_flow.py"


def test_the_flow_never_assigns_config_entry():
    """Runs without Home Assistant too (CI): no ``self.config_entry = ...``."""
    tree = ast.parse(FLOW.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        targets = node.targets if isinstance(node, ast.Assign) else (
            [node.target] if isinstance(node, (ast.AnnAssign, ast.AugAssign)) else [])
        for t in targets:
            assert not (isinstance(t, ast.Attribute) and t.attr == "config_entry"), ast.dump(t)


_REAL_HA = r"""
import asyncio, sys
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
from custom_components.ferroamp_control.config_flow import (
    FerroampControlConfigFlow, FerroampControlOptionsFlow)
from custom_components.ferroamp_control.const import CONF_PREFIX
entry = SimpleNamespace(data={CONF_PREFIX: "ferroamp"}, options={}, entry_id="e1")
flow = FerroampControlConfigFlow.async_get_options_flow(entry)
assert isinstance(flow, FerroampControlOptionsFlow)
shown = asyncio.run(flow.async_step_init(None))
assert shown["type"] == "form" and shown["step_id"] == "init", shown
defaults = {str(k): k.default() for k in shown["data_schema"].schema
            if callable(getattr(k, "default", None))}
assert defaults.get(CONF_PREFIX) == "ferroamp", defaults
print("FLOW_OK")
"""


def test_the_options_flow_opens_and_reads_the_entry_on_this_home_assistant():
    """On a real Home Assistant, in a process of its own: the other tests
    stub ``homeassistant.core`` in this one. Skipped where Home Assistant
    is not installed (CI)."""
    import subprocess
    import sys

    root = FLOW.parents[2]
    probe = subprocess.run([sys.executable, "-c", "import homeassistant.config_entries"],
                           capture_output=True)
    if probe.returncode:
        pytest.skip("Home Assistant is not installed")
    out = subprocess.run([sys.executable, "-c", _REAL_HA, str(root)], capture_output=True,
                         text=True, cwd=root)
    assert "FLOW_OK" in out.stdout, out.stderr[-2000:]
