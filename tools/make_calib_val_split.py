"""Build calibration/validation 50/50 spatial split for GO+DF at 16×16 block granularity.

Strategy: build a 16×16 coarse grid (~45 km blocks) over the AOI bounding box,
determine the dominant realized role per block, then assign blocks to calibration
(split=0) or validation (split=1) with a stratified 50/50 shuffle (seed=2026).

Outputs
-------
data/mart/calib_val_blocks.csv
    Columns: block_id (int 0–255), dom_role (int 0–6), strat (= dom_role),
    split (0=calibration, 1=validation).  Committed to git.

EE image asset: projects/probformer/assets/goias/calib_val_split
    Single band "split" (Byte), 250 m, value 0/1.  Submitted async; prints task_id.

Run:
    EE_PROJECT=probformer uv run python tools/make_calib_val_split.py
"""
from __future__ import annotations

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
    )
    return zoning.fc_to_df(fc)[["strat_grid", "rl_role"]].astype(int)


def dominant_role_per_block(role_df: pd.DataFrame) -> pd.Series:
    """Mode of rl_role within each block.  Returns Series indexed by block_id."""
    def _mode(s: pd.Series) -> int:
        return int(s.mode().iloc[0])
    return role_df.groupby("strat_grid")["rl_role"].agg(_mode).rename("dom_role")


def stratified_50_50_split(dom_role: pd.Series, seed: int = 2026) -> pd.Series:
    """50/50 calibration/validation split stratified by dominant role.

    For each stratum (role value 0–6) shuffles block IDs with a fixed seed and
    alternates 0 (calibration) / 1 (validation).  Deterministic given seed.
    Returns Series indexed by block_id with values 0 or 1.
    """
    rng = np.random.default_rng(seed)
    split: dict[int, int] = {}
    for role in sorted(dom_role.unique()):
        blocks = sorted(dom_role[dom_role == role].index.tolist())
        perm = rng.permutation(len(blocks)).tolist()
        for rank, pos in enumerate(perm):
            split[blocks[pos]] = rank % 2
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
    return table


def variogram_check(suit_present: "ee.Image", aoi,
                    n_sample: int = 6000, n_sub: int = 2000, seed: int = 42):
    """Empirical semivariogram of suit_soybean to confirm range < 45 km.

    Samples n_sample pixels with lon/lat, subsamples to n_sub for the pairwise
    computation.  Warns if estimated range >= 45 km (the block size).
    """
    lonlat = ee.Image.pixelLonLat()
    sample_img = suit_present.select("suit_soybean").addBands(lonlat)
    fc = sample_img.sample(
        region=aoi, scale=250, numPixels=n_sample,
        seed=seed, dropNulls=True, geometries=False,
    )
    df = zoning.fc_to_df(fc)
    vdf, range_km = metrics.empirical_variogram(
        df, "suit_soybean", "longitude", "latitude",
        n_sub=n_sub, max_lag_km=120.0, n_bins=12, seed=seed,
    )
    log(f"Variogram: estimated range = {range_km:.1f} km  "
        f"(block size ≈ 45 km at 16×16 grid over GO+DF)")
    log("Semivariance by lag:\n" + vdf.round(4).to_string(index=False))
    if not np.isnan(range_km) and range_km >= 45.0:
        log(f"  WARNING: autocorrelation range ({range_km:.1f} km) >= block size "
            f"(45 km) — consider n_side > 16")
    return vdf, range_km


def main() -> None:
    log(f"=== calib/val spatial split  project={P}  n_side=16  seed=2026 ===")

    # Step 1: 16×16 block image
    log("Building 16×16 block image ...")
    block_img = zoning.build_strat_band(AOI, n_side=16)

    # Step 2: sample rl_role per block (~30 pts / block)
    log("Sampling rl_role per block ...")
    realized = ee.Image(aid("feat_realized"))
    role_df = sample_role_per_block(block_img, realized, AOI, n_per_block=30, seed=2026)
    log(f"  {len(role_df)} points across {role_df['strat_grid'].nunique()} blocks")

    # Step 3: dominant role per block + 50/50 split
    dom_role = dominant_role_per_block(role_df)
    split_ser = stratified_50_50_split(dom_role, seed=2026)
    log(f"  {len(split_ser)} blocks — cal={int((split_ser == 0).sum())}  "
        f"val={int((split_ser == 1).sum())}")

    # Step 4: write CSV
    MART_DIR.mkdir(parents=True, exist_ok=True)
    csv_df = pd.DataFrame({
        "block_id": dom_role.index,
        "dom_role": dom_role.values,
        "strat": dom_role.values,
        "split": [int(split_ser[b]) for b in dom_role.index],
    })
    csv_path = MART_DIR / "calib_val_blocks.csv"
    csv_df.to_csv(csv_path, index=False)
    log(f"  wrote {csv_path}")

    # Step 5: build and export split image (async)
    log("Building split image ...")
    split_img = build_split_image(block_img, split_ser)
    log("Submitting EE export for calib_val_split ...")
    task = utils.export_image(split_img.toByte(), P, "calib_val_split", AOI)
    log(f"  submitted; task_id={task.status()['id']}")

    # Step 6: balance check (uses in-memory EE expression, not the async asset)
    log("Balance check (~20k pixel sample) ...")
    balance_check(split_img, realized, AOI)

    # Step 7: variogram check (offline after EE sample)
    log("Variogram check (suit_soybean, 2 000-pt subsample) ...")
    suit_present = ee.Image(aid("suit_present"))
    variogram_check(suit_present, AOI)

    log("=== make_calib_val_split done ===")
    log("Next: git add data/mart/calib_val_blocks.csv && git commit")
    log("Monitor export: EE_PROJECT=probformer uv run earthengine task list")


if __name__ == "__main__":
    main()
