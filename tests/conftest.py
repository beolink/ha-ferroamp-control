"""Register package stubs so the pure command-logic modules import without HA."""

from __future__ import annotations

import pathlib
import sys
import types

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_CC = _ROOT / "custom_components"
_PKG = _CC / "ferroamp_control"

for _name, _path in (("custom_components", _CC), ("custom_components.ferroamp_control", _PKG)):
    if _name not in sys.modules:
        _mod = types.ModuleType(_name)
        _mod.__path__ = [str(_path)]
        sys.modules[_name] = _mod
