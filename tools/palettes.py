"""Shared vis-param/color-ramp definitions.

Single source of truth for palettes used by both `tools/make_figures.py` (thesis PNGs)
and `tools/build_dashboard_assets.py` (dashboard PMTiles/Plotly), so the two never drift
into different color scales for the same layer (docs/dashboard_ux_plan.md §2.2).

These hex lists are also mirrored by hand into `docs/dashboard/src/styles/tokens.css`.
"""
from __future__ import annotations

from matplotlib import colormaps
from matplotlib.colors import rgb2hex

PAL_SUIT = ["#d7191c", "#fdae61", "#ffffbf", "#a6d96a", "#1a9641"]  # 0..1 red->green
PAL_FAO = ["#d7191c", "#fdae61", "#a6d96a", "#1a9641"]              # N, S3, S2, S1
PAL_ZONE = ["#4575b4", "#91bfdb", "#f46d43", "#fdae61", "#66c2a5", "#1a9850", "#762a83"]  # 7-zone legacy constant (kept for make_figures.py backward-compat; see zone_palette() for the current zone count)
PAL_ROLE = ["#eeeeee", "#ffd400", "#7b3294", "#d95f0e", "#2c7fb8", "#addd8e", "#006837"]
PAL_DIV = ["#b2182b", "#f7f7f7", "#2166ac"]                          # diverging ΔS
PAL_PR = ["#f7fbff", "#9ecae1", "#3182bd", "#08306b"]                 # sequential, precipitation
PAL_TEMP = ["#fff5eb", "#fd8d3c", "#d94801", "#7f2704"]               # sequential, temperature
PAL_AGREEMENT = ["#ffffcc", "#a1dab4", "#41b6c4", "#225ea8"]          # sequential, GCM sign-agreement
PAL_UNDERUSED = ["#f7f7f7", "#d7301f"]                                # binary, potential-vs-realized gap

SEGMENTS = [
    "soybean",
    "sugarcane",
    "other_crops",
    "pisciculture",
    "cattle",
    "conservation",
    "solar",
]

FAO_CODES = {"N": 0, "S3": 1, "S2": 2, "S1": 3}
FAO_ORDER = ["N", "S3", "S2", "S1"]


def zone_palette(n: int) -> list[str]:
    """A categorical palette with exactly `n` colors, for whatever the current zone
    count actually is (zoning is re-run under different K over time — see
    zone_profiles.csv row count for ground truth, not a hardcoded literal)."""
    cmap = colormaps["tab10"] if n <= 10 else colormaps["tab20"]
    return [rgb2hex(cmap(i / max(n - 1, 1))) for i in range(n)]
