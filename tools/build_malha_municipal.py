"""Merge the IBGE Malha Municipal Digital 2025 GO+DF shapefiles into one GeoPackage.

Reads the raw per-state downloads (gitignored, regenerable from IBGE's
malhas-territoriais portal) and writes the small committed artifact that
src/ibge_mesh.py loads at runtime to build the AOI and municipal
FeatureCollections client-side (replacing GAUL — see CLAUDE.md §7).

Run:  uv run python tools/build_malha_municipal.py
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = REPO_ROOT / "data" / "input" / "ibge"
OUTPUT_PATH = REPO_ROOT / "data" / "mart" / "malha_municipal.gpkg"

KEEP_COLS = ["CD_MUN", "NM_MUN", "CD_UF", "NM_UF", "SIGLA_UF", "AREA_KM2", "geometry"]


def main():
    parts = [
        gpd.read_file(f"zip://{INPUT_DIR / name}")
        for name in ("GO_Municipios_2025.zip", "DF_Municipios_2025.zip")
    ]
    mesh = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=parts[0].crs)
    mesh = mesh.to_crs(4326)[KEEP_COLS]

    assert len(mesh) == 247, f"expected 247 GO+DF municipalities, got {len(mesh)}"

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    mesh.to_file(OUTPUT_PATH, layer="malha_municipal", driver="GPKG")
    print(f"wrote {OUTPUT_PATH} ({len(mesh)} municipalities, EPSG:{mesh.crs.to_epsg()})")


if __name__ == "__main__":
    main()
