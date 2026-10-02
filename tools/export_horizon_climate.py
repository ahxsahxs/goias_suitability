"""Export the CMIP6 horizon climate image as a cached intermediate asset.

``tools/anchor_breakpoints.py discrimination`` measures ``sigma_mu_horizon`` -- the
discriminating power of each factor over the present UNION the future -- which means
it needs the future climate. Built live, that is a 5-GCM x 20-yr monthly graph under
an interactive ``reduceRegion``, and CLAUDE.md section 11 is explicit that such a
call can run well past ten minutes and stall. Caching the ensemble as an asset first
is the documented remedy: once this asset exists, ``anchor_breakpoints`` finds it by
name and the discrimination pass is as cheap as the present-only one ever was.

The scenario/window pair must match ``anchor_breakpoints.HORIZON_SCENARIO`` /
``HORIZON_WINDOW``; they are imported from there rather than retyped, so the two can
never drift apart.

Run:  EE_PROJECT=probformer uv run python tools/export_horizon_climate.py [--wait]
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

import ee  # noqa: E402

import utils  # noqa: E402
import cmip6  # noqa: E402
from anchor_breakpoints import HORIZON_SCENARIO, HORIZON_WINDOW  # noqa: E402

NAME = f"clim_future_{HORIZON_SCENARIO}_{HORIZON_WINDOW}"


def main():
    project = utils.init()
    aoi = utils.load_aoi(project)
    c = utils.cfg()["cmip6"]

    try:
        ee.data.getAsset(utils.asset_id(project, NAME))
        print(f"{NAME} already exists -- nothing to do")
        return 0
    except ee.EEException:
        pass

    print(f"building {NAME}: {HORIZON_SCENARIO} {HORIZON_WINDOW}, "
          f"{len(c['models'])} GCMs")
    base = cmip6.baseline_monthly(aoi)
    fac = cmip6.ensemble_factors(
        c["models"], HORIZON_SCENARIO, c["windows"][HORIZON_WINDOW], aoi)
    img = cmip6.future_climate_image(base, fac, aoi)

    task = utils.export_image(img, project, NAME, aoi, overwrite=True)
    print(f"submitted export {NAME} (batch task {task.id})")

    if "--wait" not in sys.argv:
        print("monitor with: uv run earthengine task list")
        return 0

    while True:
        st = task.status()
        state = st["state"]
        if state in ("COMPLETED", "FAILED", "CANCELLED"):
            print(f"{NAME}: {state} {st.get('error_message', '')}")
            return 0 if state == "COMPLETED" else 1
        print(f"  {time.strftime('%H:%M:%S')} {state} ...", flush=True)
        time.sleep(45)


if __name__ == "__main__":
    sys.exit(main())
