"""Pytest configuration for the pure controller tests.

The integration package ``__init__`` imports Home Assistant, which is not
needed (or wanted) for the pure controller unit tests.  This conftest
registers lightweight namespace packages and loads ``controller.py`` directly
so the tests run without a Home Assistant installation — both locally and in
CI.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

_ROOT = Path(__file__).resolve().parent.parent
_COMPONENT = _ROOT / "custom_components" / "ev_dynamic_load_balancer"


def _register_namespace(name: str, path: Path) -> None:
    """Register an empty namespace package without executing its __init__."""
    if name in sys.modules:
        return
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module


_register_namespace("custom_components", _ROOT / "custom_components")
_register_namespace("custom_components.ev_dynamic_load_balancer", _COMPONENT)

_spec = importlib.util.spec_from_file_location(
    "custom_components.ev_dynamic_load_balancer.controller",
    _COMPONENT / "controller.py",
)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)
