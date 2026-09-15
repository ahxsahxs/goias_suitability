"""Join the IBGE malha municipal geometry to the municipal ranking table and
emit a simplified GeoJSON for the future atlas dashboard (CLAUDE.md §10, P6).

Reads the committed ``data/mart/malha_municipal.gpkg`` (precise municipal
polygons, built by ``tools/build_malha_municipal.py``) and
``thesis/Chapters/Figures/municipal_ranking.csv`` (per-municipality
suitability/opportunity/vulnerability stats, written by
``tools/extract_present.py``'s ``municipal()`` block) and joins them on
``NM_MUN`` — both sides come from the same IBGE mesh now, so this is an exact
key join, no GAUL name-matching involved.

Run:  uv run python tools/build_municipal_geojson.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from utils import cfg  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
RANKING_CSV = REPO_ROOT / "thesis" / "Chapters" / "Figures" / "municipal_ranking.csv"
OUTPUT_PATH = REPO_ROOT / "thesis" / "Chapters" / "Figures" / "municipal_ranking.geojson"


def main():
    m = cfg()["municipal_mesh"]
    mesh_path = REPO_ROOT / m["path"]

    mesh = gpd.read_file(mesh_path, layer=m.get("layer"))
    if mesh.crs is None or mesh.crs.to_epsg() != 4326:
        mesh = mesh.to_crs(4326)
    mesh["geometry"] = mesh.geometry.simplify(m["simplify_tolerance_deg"], preserve_topology=True)

    ranking = pd.read_csv(RANKING_CSV)

    key = m["join_key"]
    merged = mesh.merge(ranking, on=key, how="inner", validate="one_to_one")

    missing = set(mesh[key]) - set(ranking[key])
    if missing:
        print(f"  !! {len(missing)} mesh municipalities without a ranking row: {sorted(missing)}")
    extra = set(ranking[key]) - set(mesh[key])
    if extra:
        print(f"  !! {len(extra)} ranking rows without a mesh match: {sorted(extra)}")

    assert len(merged) == len(ranking), (
        f"join dropped rows: mesh={len(mesh)} ranking={len(ranking)} merged={len(merged)}"
    )

    keep = [m["code_col"], m["name_col"], m["uf_col"], "opportunity", "zone",
            "suit_soybean", "suit_sugarcane", "delta_other_crops",
            "underused_soybean", "underused_sugarcane", "geometry"]
    merged = merged[keep].round(
        {c: 4 for c in merged.columns if c not in (m["code_col"], m["name_col"], m["uf_col"], "geometry")}
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged.to_file(OUTPUT_PATH, driver="GeoJSON")
    print(f"wrote {OUTPUT_PATH} ({len(merged)} municipalities, "
          f"{OUTPUT_PATH.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
