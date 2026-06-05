"""
scripts/__init__.py
Auto-discovers and registers all script modules in this package.

How it works
------------
Every .py file in this directory (except __init__.py itself) is imported
automatically so that `from scripts import <module>` always works without
manual registration.

To add a new function/module
-----------------------------
1. Create scripts/your_module.py
2. That's it — it will be detected automatically on next run.

Available modules (auto-populated at import time):
"""

import importlib
import pkgutil
from pathlib import Path

# Automatically import every sub-module in this package so callers can do:
#   from scripts.your_module import your_function
# without any manual wiring here.

_package_dir = Path(__file__).parent
_auto_imported: list[str] = []

for _module_info in pkgutil.iter_modules([str(_package_dir)]):
    _mod = importlib.import_module(f"scripts.{_module_info.name}")
    _auto_imported.append(_module_info.name)

__all__ = _auto_imported
