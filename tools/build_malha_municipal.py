"""Merge the IBGE Malha Municipal zips of the territory's UFs into one GeoPackage.

Inputs : data/input/ibge/<UF>_Municipios_<year>.zip  (one per UF in config/territory.yaml;
         gitignored, download from IBGE's malhas-territoriais portal)
Output : territory `mesh_path` (EPSG:4326), loaded by src/ibge_mesh.py to build the AOI
         and the municipal FeatureCollection client-side.

Run:  uv run python pipeline.py mesh
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import utils  # noqa: E402

INPUT_DIR = utils.REPO / "data" / "input" / "ibge"
IBGE_URL = ("https://www.ibge.gov.br/geociencias/organizacao-do-territorio/"
            "malhas-territoriais/15774-malhas.html")
KEEP_COLS = ["CD_MUN", "NM_MUN", "CD_UF", "NM_UF", "SIGLA_UF", "AREA_KM2", "geometry"]


def main():
    t = utils.territory()
    zips = [INPUT_DIR / f"{uf}_Municipios_{t['ibge_year']}.zip" for uf in t["ufs"]]
    missing = [z.name for z in zips if not z.exists()]
    if missing:
        raise SystemExit(f"missing in {INPUT_DIR}: {missing}\nDownload them from {IBGE_URL}")

    parts = [gpd.read_file(f"zip://{z}") for z in zips]
    mesh = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=parts[0].crs)
    mesh = mesh.to_crs(4326)[KEEP_COLS]

    absent = set(t["ufs"]) - set(mesh["SIGLA_UF"])
    if absent:
        raise SystemExit(f"UFs with no municipality in the zips: {sorted(absent)}")
    if mesh[t["join_key"]].duplicated().any():
        raise SystemExit(f"join_key {t['join_key']!r} is not unique across "
                         f"{t['ufs']}; set join_key: CD_MUN in config/territory.yaml")

    out = utils.REPO / t["mesh_path"]
    out.parent.mkdir(parents=True, exist_ok=True)
    mesh.to_file(out, layer="malha_municipal", driver="GPKG")
    print(f"wrote {out} ({len(mesh)} municipalities in {t['ufs']}, "
          f"EPSG:{mesh.crs.to_epsg()})")


if __name__ == "__main__":
    main()
