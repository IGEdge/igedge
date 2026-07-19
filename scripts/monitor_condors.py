#!/usr/bin/env python3
"""
DEPRECATO (issue #16) — usa `scripts/monitor_spreads.py`.

Questo stub resta per non rompere script/docs vecchi: delega al nuovo comando.
"""
import runpy
import sys
import warnings

warnings.warn(
    "monitor_condors.py è deprecato: usa scripts/monitor_spreads.py (issue #16)",
    DeprecationWarning,
    stacklevel=1,
)
print("⚠️ DEPRECATO: usa  python scripts/monitor_spreads.py  "
      "(naming generico — issue #16)", flush=True)
sys.argv[0] = "monitor_spreads.py"
runpy.run_path(
    __file__.replace("monitor_condors.py", "monitor_spreads.py"),
    run_name="__main__",
)
