#!/usr/bin/env python3
"""
Wrapper entrypoint to execute the script from the project root even when
`scripts/` is git-ignored in some environments (CI/docker builds).

Usage:
  ./bin/apply_title_counters.py
"""

import os
import runpy
import sys

# Locate project root (this file lives in bin/ at project root)
ROOT = os.path.dirname(os.path.dirname(__file__))
SCRIPT = os.path.join(ROOT, "scripts", "apply_title_counters.py")

if not os.path.exists(SCRIPT):
    print("Script not found:", SCRIPT)
    sys.exit(2)

# Execute script in-process so imports resolve to project modules
runpy.run_path(SCRIPT, run_name="__main__")
