"""Wait for the in-flight present-atlas exports to finish, then run the
(fixed, resumable) recalibration cascade. Used to resume after the window-bug
failure without racing the still-running suit_present/_comp/_sens tasks.

Run (background):  EE_PROJECT=probformer ../.venv/bin/python tools/wait_then_recal.py
"""
import sys
import time

sys.path.insert(0, "tools")
sys.path.insert(0, "src")

import run_recal as R  # noqa: E402  (module import runs utils.init())

NEED = ["suit_present", "suit_present_comp", "suit_present_sens"]

R.log("waiting for in-flight present-atlas exports to finish ...")
while not all(R.exists(n) for n in NEED):
    time.sleep(45)
R.log("present atlas ready — resuming cascade (window bug fixed; Stage 1/2 will skip)")
R.main()
