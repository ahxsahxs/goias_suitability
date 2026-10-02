"""Per-band regression diff of a rebuilt asset against a backup snapshot.

Exists for one job: a from-scratch re-execution has to be able to prove that a
stage which was NOT supposed to change did not change. Parts 1-8 are the case that
matters -- their builders in src/features.py are untouched, so any difference means
an upstream catalog (MapBiomas, TerraClimate, SoilGrids, HydroSHEDS, ...) moved
under the project, and that would propagate into every number in the thesis for a
reason that has nothing to do with the work under review.

For each band common to both images it reduces (new - old) over the AOI with
minMax + the count of differing pixels, and reports the band as CLEAN or CHANGED.
Band sets that differ are reported too -- a band appearing or disappearing is
itself a regression.

Known non-bug: terr_tpi differs in ~0.1% of pixels between any two full exports
(tile-edge noise in focalMean/reproject, CLAUDE.md S11). --eps is compared against
the max |delta|, so a genuine catalog shift still shows up.

Run::

    EE_PROJECT=probformer uv run python tools/diff_vs_backup.py \
        --backup goias_backup_ahp_20260928 \
        feat_climate feat_terrain feat_soil feat_water feat_phenology \
        feat_access feat_landcover feat_siting feat_conservation \
        feature_stack_250m feature_stack_250m_z

Exit code is 1 if any band changed, so it can gate a cascade.
"""
from __future__ import annotations

import argparse
import sys

sys.path.insert(0, "src")

import ee  # noqa: E402
import utils  # noqa: E402

SCALE = 250


def diff_asset(project, name, backup_root, region, scale, tile_scale, eps):
    """Diff one asset against its backup copy. Returns True when clean.

    One reduceRegion per asset, not per band: ``minMax`` over the multi-band
    difference image yields ``<band>_min`` / ``<band>_max`` in a single call.
    """
    new = ee.Image(utils.asset_id(project, name))
    old = ee.Image(f"{backup_root}/{name}")
    try:
        nb = new.bandNames().getInfo()
        ob = old.bandNames().getInfo()
    except ee.EEException as e:
        print(f"  SKIP -- {e}")
        return False

    clean = True
    missing, added = sorted(set(ob) - set(nb)), sorted(set(nb) - set(ob))
    if missing:
        print(f"  BANDS REMOVED {missing}")
        clean = False
    if added:
        print(f"  BANDS ADDED   {added}")
        clean = False

    common = [b for b in nb if b in set(ob)]
    if not common:
        print("  no common bands")
        return False

    d = new.select(common).subtract(old.select(common))
    stats = d.reduceRegion(
        reducer=ee.Reducer.minMax(), geometry=region, scale=scale,
        maxPixels=int(1e13), tileScale=tile_scale,
    ).getInfo()

    for band in common:
        lo, hi = stats.get(f"{band}_min"), stats.get(f"{band}_max")
        if lo is None or hi is None:
            print(f"  {band:24s} NO DATA")
            clean = False
            continue
        worst = max(abs(lo), abs(hi))
        if worst <= eps:
            print(f"  {band:24s} clean")
        else:
            clean = False
            print(f"  {band:24s} CHANGED  delta in [{lo:+.6g}, {hi:+.6g}]")
    return clean


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("assets", nargs="+", help="asset names under the goias folder")
    ap.add_argument("--backup", required=True,
                    help="backup folder name, e.g. goias_backup_ahp_20260928")
    ap.add_argument("--eps", type=float, default=1e-6,
                    help="max |delta| still counted as float noise (default 1e-6)")
    ap.add_argument("--scale", type=int, default=SCALE)
    ap.add_argument("--tile-scale", type=int, default=8)
    args = ap.parse_args()

    project = utils.init()
    region = utils.load_aoi(project)
    root = utils.asset_root(project).rsplit("/", 1)[0]
    backup_root = f"{root}/{args.backup}"
    print(f"diffing against {backup_root}  (eps={args.eps}, scale={args.scale} m)\n")

    changed = []
    for name in args.assets:
        print(f"{name}:")
        if not diff_asset(project, name, backup_root, region,
                          args.scale, args.tile_scale, args.eps):
            changed.append(name)
        print()

    if changed:
        print(f"CHANGED: {', '.join(changed)}")
        print("Investigate before letting this propagate downstream.")
        sys.exit(1)
    print(f"ALL CLEAN -- {len(args.assets)} assets identical to the backup.")


if __name__ == "__main__":
    main()
