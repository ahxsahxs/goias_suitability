"""Build (or audit) the calibration/validation 50/50 spatial split for GO+DF.

Strategy: build an N_SIDE x N_SIDE coarse grid over the AOI bounding box (default
6, i.e. ~130 km blocks -- sized from the MEASURED residual autocorrelation range,
see variogram_check), determine the dominant realized role per block, then assign
blocks to calibration (split=0) or validation (split=1) with a stratified 50/50
shuffle (seed=2026).

Two modes
---------
``--check-only`` (the Gate-0 audit; writes no asset, rebuilds nothing)
    Reads the EXISTING split -- the exported ``calib_val_split`` asset, falling
    back to rebuilding it in memory from the committed block CSV -- and writes the
    two evidence artifacts the holdout design rests on:

      * ``variogram_suit.csv``   empirical semivariogram + estimated autocorrelation
        range for all three crop suitability bands. The block size is only
        defensible if the range is shorter than the block; this is the number that
        decides it, and it used to exist solely as a line of stdout.
      * ``split_balance.csv``    realized-role x half pixel counts, i.e. whether
        each half actually carries enough of each role to validate on.

    Read ``range_km`` together with ``nugget_share``: when the nugget share
    approaches 1 the variance is almost all noise at the sampling support and the
    range estimate carries no information about structural autocorrelation.

(default, no flag) -- (re)build the split and export the asset
    WARNING: this re-samples ``rl_role`` and rewrites data/mart/calib_val_blocks.csv,
    so it invalidates the provenance of every result already computed against the
    committed split. Only run it to create the split for the first time, or
    deliberately to replace it; the audit mode is what day-to-day work needs.

Outputs
-------
data/mart/calib_val_blocks.csv   (build mode only)
    Columns: block_id (int, 0..N_SIDE^2-1), dom_role (int 0–6),
    strat (= dom_role), split (0=calibration, 1=validation).  Committed to git.

EE image asset: projects/probformer/assets/goias/calib_val_split   (build mode only)
    Single band "split" (Byte), 250 m, value 0/1.  Submitted async; prints task_id.

thesis/Chapters/{variogram_suit,split_balance}.csv   (both modes; $SCRATCHPAD overrides)

Run:
    EE_PROJECT=probformer uv run python tools/make_calib_val_split.py --check-only
    EE_PROJECT=probformer uv run python tools/make_calib_val_split.py   # rebuilds!
    SPLIT_NSIDE=8 EE_PROJECT=probformer uv run python tools/make_calib_val_split.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import ee          # noqa: E402
import utils       # noqa: E402
import zoning      # noqa: E402
import metrics     # noqa: E402

P = utils.init()
AOI = utils.load_aoi(P)
MART_DIR = ROOT / "data" / "mart"
BLOCKS_CSV = MART_DIR / "calib_val_blocks.csv"

# House pattern: evidence CSVs land in thesis/Chapters/; $SCRATCHPAD overrides.
OUT = Path(os.environ.get("SCRATCHPAD", str(ROOT / "thesis" / "Chapters")))

# Crop bands whose autocorrelation range has to be shorter than the block.
# All three, not just soybean: sugarcane and other_crops are the metrics with the
# least statistical power, so their range is the one that binds.
VARIO_CROPS = {"soybean": 1, "sugarcane": 2, "other_crops": 3}

# Grid granularity. 2026-10-03: moved from 16 (~49 km) to 6 (~130 km) because the
# measured residual autocorrelation range over GO+DF is 105-150 km, so 49 km
# blocks left roughly half the spatially structured variance shared across the
# block boundary -- i.e. they did not decorrelate the halves at all. Coarsening
# costs almost nothing in balance (the rare roles are limited by realized AREA,
# not by block count) and buys the only thing the holdout exists for.
N_SIDE = int(os.environ.get("SPLIT_NSIDE", "6"))


def block_km(aoi) -> float:
    """Nominal block edge in km, from the AOI bounding box -- never hardcoded.

    The verdicts below compare a measured range against the block size, so the
    block size has to follow N_SIDE automatically; a stale constant here would
    silently validate the wrong geometry.
    """
    coords = ee.Geometry(aoi).bounds().coordinates().get(0).getInfo()
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    width_km = (max(lons) - min(lons)) * 111.0 * np.cos(np.radians(np.mean(lats)))
    return width_km / N_SIDE


def log(m: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def aid(name: str) -> str:
    return utils.asset_id(P, name)


def sample_role_per_block(
    block_img: "ee.Image",
    feat_realized: "ee.Image",
    aoi,
    n_per_block: int = 30,
    seed: int = 2026,
) -> pd.DataFrame:
    """Sample rl_role for every spatial block (~n_per_block points per block).

    Uses stratifiedSample on the block band so every AOI block contributes at
    least one point.  Returns DataFrame: strat_grid (block id), rl_role.
    """
    sample_img = block_img.addBands(feat_realized.select("rl_role"))
    fc = sample_img.stratifiedSample(
        numPoints=n_per_block,
        classBand="strat_grid",
        region=aoi,
        scale=250,
        seed=seed,
        dropNulls=True,
        geometries=False,
        tileScale=8,   # house pattern: trade compute tiles for lower per-tile memory
    )
    return zoning.fc_to_df(fc)[["strat_grid", "rl_role"]].astype(int)


def dominant_role_per_block(role_df: pd.DataFrame) -> pd.Series:
    """Mode of rl_role within each block.  Returns Series indexed by block_id."""
    def _mode(s: pd.Series) -> int:
        return int(s.mode().iloc[0])
    return role_df.groupby("strat_grid")["rl_role"].agg(_mode).rename("dom_role")


def block_area_km2(block_img: "ee.Image", aoi, scale: int = 1000) -> pd.Series:
    """AOI area (km^2) inside each block. Indexed by block id.

    Needed because the blocks are a bounding-box grid: an edge block may hold a
    sliver of the AOI while an interior one holds all of it. Counting BLOCKS
    therefore says nothing about how much territory each half gets. Reduced at
    1 km -- only the ratios matter here, and 250 m would cost 16x for no gain.
    """
    grouped = (ee.Image.pixelArea().divide(1e6).addBands(block_img)
               .reduceRegion(
                   reducer=ee.Reducer.sum().group(groupField=1, groupName="block"),
                   geometry=aoi, scale=scale, maxPixels=int(1e13),
                   bestEffort=True, tileScale=8).getInfo())
    rows = {int(g["block"]): float(g["sum"]) for g in grouped["groups"]}
    return pd.Series(rows, name="area_km2").sort_index()


def stratified_50_50_split(dom_role: pd.Series, seed: int = 2026,
                           area: pd.Series | None = None) -> pd.Series:
    """50/50 calibration/validation split stratified by dominant role.

    Within each role stratum, blocks are assigned so the two halves end up with
    as nearly EQUAL AREA as possible -- greedy largest-first onto whichever half
    currently holds less area, the standard balanced-partition heuristic.

    Why not simply alternate ``rank % 2`` as this did until 2026-10-03: the blocks
    are a bounding-box grid with very unequal AOI overlap, so equal block COUNTS
    give unequal territory. At n_side=6 the alternating rule produced 17/14 blocks
    but a 64/36 split of the pixels, with 2.6x as much realized soybean in the
    calibration half as in the validation half -- which guts the power of exactly
    the half every reported metric comes from. Balancing on area fixes the thing
    that matters instead of the thing that is easy to count.

    ``seed`` still orders tied blocks, so the result stays deterministic, and the
    function falls back to the alternating rule when no area is supplied.
    Returns Series indexed by block_id with values 0 (calibration) or 1 (validation).
    """
    rng = np.random.default_rng(seed)
    split: dict[int, int] = {}
    for role in sorted(dom_role.unique()):
        blocks = sorted(dom_role[dom_role == role].index.tolist())
        if area is None:
            perm = rng.permutation(len(blocks)).tolist()
            for rank, pos in enumerate(perm):
                split[blocks[pos]] = rank % 2
            continue
        # jitter breaks exact ties reproducibly, so the order does not depend on
        # dict/sort incidentals
        w = {b: float(area.get(b, 0.0)) for b in blocks}
        jitter = {b: rng.random() * 1e-9 for b in blocks}
        order = sorted(blocks, key=lambda b: (-w[b], -jitter[b]))
        load = [0.0, 0.0]
        for b in order:
            h = 0 if load[0] <= load[1] else 1
            split[b] = h
            load[h] += w[b]
    return pd.Series(split, name="split")


def build_split_image(block_img: "ee.Image", split_ser: pd.Series) -> "ee.Image":
    """Remap block_id image to split (0=cal, 1=val).

    Blocks not present in split_ser (outside AOI but inside bounding box)
    default to 0 (calibration; harmless since AOI mask suppresses them).
    Returns ee.Image with one band 'split'.
    """
    from_list = [int(k) for k in split_ser.index.tolist()]
    to_list = [int(v) for v in split_ser.values.tolist()]
    return block_img.remap(from_list, to_list, defaultValue=0).rename("split")


def balance_check(
    split_img: "ee.Image",
    feat_realized: "ee.Image",
    aoi,
    n: int = 20000,
    seed: int = 7,
) -> pd.DataFrame:
    """Sample ~n pixels; count presence per segment per split half.

    Uses rl_role to identify realized land use. Warns for any role/split < 1000.
    Returns DataFrame: rows=split (0/1), cols=rl_role (0–6).
    """
    sample_img = (feat_realized.select("rl_role")
                  .addBands(split_img.rename("split")))
    fc = sample_img.sample(
        region=aoi, scale=250, numPixels=n,
        seed=seed, dropNulls=True, geometries=False,
    )
    df = zoning.fc_to_df(fc).astype({"rl_role": int, "split": int})
    table = df.groupby(["split", "rl_role"]).size().unstack(fill_value=0)
    log("Balance table (rows=split, cols=rl_role):\n" + table.to_string())
    for s in [0, 1]:
        if s in table.index:
            low = table.loc[s][table.loc[s] < 1000]
            if not low.empty:
                log(f"  WARNING: split={s} roles below 1 000 pixels: {low.to_dict()}")

    # Long form, so the thesis/dashboard read it without reshaping and a missing
    # (role, half) cell is a visible absent row rather than a silent zero column.
    rows = [{"split": int(sp), "half": "calib" if int(sp) == 0 else "val",
             "rl_role": int(rl), "n_pixels": int(table.loc[sp, rl]),
             "n_sample": int(len(df)), "seed": int(seed), "scale_m": 250}
            for sp in table.index for rl in table.columns]
    out = pd.DataFrame(rows).sort_values(["rl_role", "split"])
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / "split_balance.csv"
    out.to_csv(dest, index=False)
    log(f"  wrote {dest}")
    return table


def variogram_check(suit_present: "ee.Image", realized: "ee.Image", aoi,
                    n_sample: int = 14000, n_sub: int = 6000, seed: int = 42,
                    windows: tuple[float, ...] = (400.0, 800.0),
                    tile_scale: int = 8):
    """Gate 0: is the block big enough to decorrelate the two halves?

    Measures the empirical semivariogram in THREE framings per crop, because they
    answer different questions and only the last one sizes a block:

      * ``suit_<crop>``  the fitted surface. Built from smooth climate/soil
        gradients, so its range largely measures PREDICTOR smoothness -- a
        deterministic regional trend the covariates explain. Reported for
        contrast; sizing a block from it would overstate the requirement.
      * ``pres_<crop>``  the response (realized presence, 0/1).
      * ``resid_<crop>`` presence minus fitted suitability. This is the residual
        dependence that actually inflates out-of-sample optimism, and it is what
        Roberts et al. (2017) / Valavi et al. (2019) size blocks from.

    Two windows, because a range estimate is only trustworthy if the window can
    contain the plateau: when the estimate GROWS with the window, the field has no
    finite range inside the study area and no feasible block fully decorrelates it.

    Read every range together with ``nugget_share``: as it approaches 1 the
    variance is nearly all at-support noise and the range says nothing about
    structure (this is what makes the other_crops presence row uninterpretable --
    too few presences for a binary field to carry signal).

    Returns (vario_df_long, {(field, window): range_km}).
    """
    blk = block_km(aoi)
    log(f"  block size ~{blk:.0f} km (n_side={N_SIDE})")

    # ONE draw for every field and window: ranges are then directly comparable,
    # and per-field draws would confound field differences with sampling noise.
    img = ee.Image.cat(
        [suit_present.select([f"suit_{c}"]) for c in VARIO_CROPS]
        + [realized.select("rl_role").eq(code).rename(f"pres_{c}")
           for c, code in VARIO_CROPS.items()]
    ).addBands(ee.Image.pixelLonLat())
    fc = img.sample(region=aoi, scale=250, numPixels=n_sample, seed=seed,
                    dropNulls=True, geometries=False, tileScale=tile_scale)
    df = zoning.fc_to_df(fc)
    log(f"  variogram sample: n={len(df)} px")
    for c in VARIO_CROPS:
        df[f"resid_{c}"] = df[f"pres_{c}"] - df[f"suit_{c}"]
        log(f"    {c:12s} presences in sample = {int(df[f'pres_{c}'].sum())}")

    frames, ranges = [], {}
    log(f"  {'field':22s} {'win':>5s} {'range_km':>9s} {'nugget':>7s} "
        f"{'g/sill@blk':>10s}  verdict")
    for c in VARIO_CROPS:
        for kind in ("suit", "pres", "resid"):
            col = f"{kind}_{c}"
            for win in windows:
                vdf, range_km = metrics.empirical_variogram(
                    df, col, "longitude", "latitude", n_sub=n_sub,
                    max_lag_km=win, n_bins=40, seed=seed,
                )
                sill = float(vdf["sill"].iloc[0])
                nug = float(vdf["nugget_share"].iloc[0])
                # share of the SPATIALLY STRUCTURED variance still shared at the
                # block edge -- the number that says how much dependence a block
                # of this size fails to break
                g_blk = float(np.interp(blk, vdf["lag_km_center"], vdf["gamma"]))
                struct = sill - float(vdf["nugget"].iloc[0])
                # Share of the SPATIALLY STRUCTURED variance still shared at the
                # block edge. Clamped to [0, 1]: gamma is an empirical estimate and
                # need not be monotone, so a noisy bin below the nugget would
                # otherwise yield a nonsensical share above 1 (seen at 1.30 for
                # other_crops presence, whose nugget is 0.87 of the sill and whose
                # structured component is therefore too small to divide by safely).
                shared = ((sill - g_blk) / struct) if struct > 0 else float("nan")
                if not np.isnan(shared):
                    shared = min(1.0, max(0.0, shared))

                verdict = _verdict(kind, range_km, nug, blk)
                rtxt = "nan" if np.isnan(range_km) else f"{range_km:.0f}"
                log(f"  {col:22s} {win:5.0f} {rtxt:>9s} {nug:7.3f} "
                    f"{g_blk / sill:10.3f}  {verdict}")

                ranges[(col, win)] = range_km
                vdf = vdf.copy()
                vdf.insert(0, "field", col)
                vdf.insert(1, "crop", c)
                vdf.insert(2, "framing", kind)
                vdf["window_km"] = win
                vdf["range_km"] = range_km
                vdf["block_km"] = blk
                vdf["n_side"] = N_SIDE
                vdf["struct_shared_at_block"] = shared
                vdf["n_sub"] = min(n_sub, len(df))
                vdf["seed"] = seed
                frames.append(vdf)

    out = pd.concat(frames, ignore_index=True)
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / "variogram_suit.csv"
    out.to_csv(dest, index=False)
    log(f"  wrote {dest}")

    # The decision rests on the RESIDUAL framing at the narrower window.
    win0 = min(windows)
    res = {c: ranges.get((f"resid_{c}", win0)) for c in VARIO_CROPS}
    worst = max((r for r in res.values() if r is not None and not np.isnan(r)),
                default=float("nan"))
    log("")
    log(f"  GATE 0 (residual framing @ {win0:.0f} km window): "
        + "  ".join(f"{c}={('nan' if r is None or np.isnan(r) else f'{r:.0f} km')}"
                    for c, r in res.items()))
    if np.isnan(worst):
        log("  => NO-GO: no residual range estimable; the block cannot be justified.")
    elif worst < blk:
        log(f"  => GO: worst residual range {worst:.0f} km < block {blk:.0f} km.")
    elif worst < 2 * blk:
        log(f"  => GO WITH DECLARED CAVEAT: worst residual range {worst:.0f} km vs "
            f"block {blk:.0f} km (ratio {worst / blk:.2f}); report the residual "
            f"optimism bound.")
    else:
        log(f"  => NO-GO: worst residual range {worst:.0f} km >= 2x block "
            f"{blk:.0f} km. Coarsen the grid (lower SPLIT_NSIDE) or drop the "
            f"holdout framing.")
    return out, ranges


def _verdict(kind: str, range_km: float, nugget_share: float, blk: float) -> str:
    """One-word reading of a single (field, window) row."""
    if nugget_share > 0.95:
        return "uninterpretable (nugget ~ sill)"
    if kind == "suit":
        return "context only (fitted surface)"
    if np.isnan(range_km):
        return "no plateau in window"
    if range_km < blk:
        return "OK < block"
    if range_km < 2 * blk:
        return "caveat: >= block"
    return "FAIL: >= 2x block"


def load_split_image() -> "ee.Image":
    """The split image every consumer must see: the exported asset, verbatim.

    Falls back to rebuilding it in memory from the committed block CSV when the
    asset is absent. The fallback is NOT equivalent in general -- build_strat_band
    bins ee.Geometry(AOI).bounds(), so if `aoi` were ever re-exported the in-memory
    grid would shift while the asset would not -- so it says loudly which one it
    used. Never re-samples rl_role: the audit must test the committed split, not a
    fresh draw that happens to resemble it.
    """
    try:
        img = ee.Image(aid("calib_val_split")).select("split")
        img.bandNames().getInfo()
        log("  split source: cached asset calib_val_split")
        return img
    except Exception:
        pass
    if not BLOCKS_CSV.exists():
        raise SystemExit(
            f"neither the calib_val_split asset nor {BLOCKS_CSV} exists -- "
            f"run this tool without --check-only to build the split first")
    log(f"  split source: REBUILT IN MEMORY from {BLOCKS_CSV.name} "
        f"(asset absent; valid only while `aoi` is unchanged)")
    blocks = pd.read_csv(BLOCKS_CSV)
    split_ser = pd.Series(blocks["split"].values, index=blocks["block_id"].values,
                          name="split")
    return build_split_image(zoning.build_strat_band(AOI, n_side=N_SIDE), split_ser)


def check_only() -> None:
    """Gate 0: audit the EXISTING split. Writes no asset and rebuilds nothing."""
    log(f"=== Gate 0: audit calib/val split  project={P} ===")
    log("Loading split ...")
    split_img = load_split_image()
    realized = ee.Image(aid("feat_realized"))

    if BLOCKS_CSV.exists():
        b = pd.read_csv(BLOCKS_CSV)
        log(f"  committed blocks: {len(b)}  calib={int((b.split == 0).sum())}  "
            f"val={int((b.split == 1).sum())}")
        per_role = (b.groupby(["dom_role", "split"]).size().unstack(fill_value=0))
        log("  blocks by dominant role (cols=split):\n" + per_role.to_string())

    log("Balance check (~20k pixel sample) ...")
    balance_check(split_img, realized, AOI)

    log("Variogram check (3 framings x 3 crops x 2 windows) ...")
    variogram_check(ee.Image(aid("suit_present")), realized, AOI)

    log("=== Gate 0 audit done ===")
    log("Read range_km in variogram_suit.csv together with nugget_share before "
        "relying on any held-out metric; the residual framing is the one that "
        "sizes the block.")


def build() -> None:
    log(f"=== calib/val spatial split  project={P}  n_side={N_SIDE}  seed=2026 ===")
    if BLOCKS_CSV.exists():
        log(f"!! {BLOCKS_CSV} already exists and will be OVERWRITTEN. Every result "
            f"already computed against the committed split loses its provenance. "
            f"Use --check-only to audit the existing split instead.")

    # Step 1: coarse block image
    log(f"Building {N_SIDE}×{N_SIDE} block image ...")
    block_img = zoning.build_strat_band(AOI, n_side=N_SIDE)

    # Step 2: sample rl_role per block (~30 pts / block)
    log("Sampling rl_role per block ...")
    realized = ee.Image(aid("feat_realized"))
    role_df = sample_role_per_block(block_img, realized, AOI, n_per_block=30, seed=2026)
    log(f"  {len(role_df)} points across {role_df['strat_grid'].nunique()} blocks")

    # Step 3: dominant role per block + area-balanced 50/50 split
    dom_role = dominant_role_per_block(role_df)
    log("Measuring AOI area per block ...")
    area = block_area_km2(block_img, AOI)
    split_ser = stratified_50_50_split(dom_role, seed=2026, area=area)
    a0 = float(area[[b for b in area.index if split_ser.get(b) == 0]].sum())
    a1 = float(area[[b for b in area.index if split_ser.get(b) == 1]].sum())
    log(f"  {len(split_ser)} blocks — cal={int((split_ser == 0).sum())}  "
        f"val={int((split_ser == 1).sum())}")
    log(f"  area: calib={a0:,.0f} km2 ({a0/(a0+a1)*100:.1f}%)  "
        f"val={a1:,.0f} km2 ({a1/(a0+a1)*100:.1f}%)")

    # Step 4: write CSV
    MART_DIR.mkdir(parents=True, exist_ok=True)
    csv_df = pd.DataFrame({
        "block_id": dom_role.index,
        "dom_role": dom_role.values,
        "strat": dom_role.values,
        "split": [int(split_ser[b]) for b in dom_role.index],
        "area_km2": [round(float(area.get(b, 0.0)), 2) for b in dom_role.index],
        "n_side": N_SIDE,
    })
    csv_df.to_csv(BLOCKS_CSV, index=False)
    log(f"  wrote {BLOCKS_CSV}")

    # Step 5: build and export split image (async)
    log("Building split image ...")
    split_img = build_split_image(block_img, split_ser)
    log("Submitting EE export for calib_val_split ...")
    # overwrite=True deletes the old asset BEFORE submitting, so a failed task
    # leaves no asset at all (CLAUDE.md S4). The block CSV written above is the
    # recovery path: --check-only rebuilds the image from it in memory.
    task = utils.export_image(split_img.toByte(), P, "calib_val_split", AOI,
                              overwrite=True)
    log(f"  submitted; task_id={task.status()['id']}")

    # Steps 6-7: the same evidence the audit mode writes, on the in-memory
    # expression (the async asset is not there yet).
    log("Balance check (~20k pixel sample) ...")
    balance_check(split_img, realized, AOI)
    log("Variogram check (3 framings x 3 crops x 2 windows) ...")
    variogram_check(ee.Image(aid("suit_present")), realized, AOI)

    log("=== make_calib_val_split done ===")
    log("Next: git add data/mart/calib_val_blocks.csv && git commit")
    log("Monitor export: EE_PROJECT=probformer uv run earthengine task list")


if __name__ == "__main__":
    args = set(sys.argv[1:])
    unknown = args - {"--check-only"}
    if unknown:
        raise SystemExit(f"unknown argument(s) {sorted(unknown)}; "
                         f"usage: make_calib_val_split.py [--check-only]")
    if "--check-only" in args:
        check_only()
    else:
        build()
