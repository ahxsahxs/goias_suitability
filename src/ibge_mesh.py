"""Local IBGE malha-municipal loader + ee.FeatureCollection/ee.Geometry builder.

Reads the committed ``data/mart/malha_municipal.gpkg`` with geopandas and
embeds the geometries client-side into ``ee`` objects. Nothing here is ever
exported as a persistent EE asset — the FeatureCollection/Geometry is rebuilt
in memory on every run (same zero-external-uploads guarantee as the GAUL
catalog pull this module replaces). Kept separate from ``features.py``/
``external.py`` so those two keep their "no server call at import" contract —
the local file read here only happens lazily, inside functions.
"""
from __future__ import annotations

from functools import lru_cache

import ee

from utils import PKG_ROOT, cfg


@lru_cache(maxsize=None)
def _load_gdf():
    import geopandas as gpd

    m = cfg()["municipal_mesh"]
    gdf = gpd.read_file(PKG_ROOT / m["path"], layer=m.get("layer"))
    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)
    if m.get("uf_values"):
        gdf = gdf[gdf[m["uf_col"]].isin(m["uf_values"])].reset_index(drop=True)
    keep = [m["code_col"], m["name_col"], m["uf_col"], m["state_name_col"], "geometry"]
    return gdf[keep]


@lru_cache(maxsize=None)
def municipal_ee_fc() -> "ee.FeatureCollection":
    """247 GO+DF municipalities, each an ee.Feature with a simplified geometry."""
    m = cfg()["municipal_mesh"]
    gdf = _load_gdf().copy()
    gdf["geometry"] = gdf.geometry.simplify(m["simplify_tolerance_deg"], preserve_topology=True)
    feats = [
        ee.Feature(
            ee.Geometry(row.geometry.__geo_interface__),
            {
                m["code_col"]: row[m["code_col"]],
                m["name_col"]: row[m["name_col"]],
                m["uf_col"]: row[m["uf_col"]],
                m["state_name_col"]: row[m["state_name_col"]],
            },
        )
        for _, row in gdf.iterrows()
    ]
    return ee.FeatureCollection(feats)


@lru_cache(maxsize=None)
def aoi_ee_geometry() -> "ee.Geometry":
    """Dissolved GO+DF outer boundary.

    Unions the full-precision geometries first (cancels shared municipal
    borders before any simplification), then simplifies the single result —
    far fewer vertices than simplifying every feature and dissolving after.
    """
    m = cfg()["municipal_mesh"]
    dissolved = _load_gdf().union_all().simplify(m["simplify_tolerance_deg"], preserve_topology=True)
    return ee.Geometry(dissolved.__geo_interface__)
