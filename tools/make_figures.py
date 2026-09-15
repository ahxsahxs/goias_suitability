"""Render thesis figures from the built EE assets (headless).

Fetches per-layer PNG thumbnails via ``ee.Image.getThumbURL`` (a small artifact
leaving GEE, within the project cost policy), composes multi-panel figures with
matplotlib, and writes them to ``docs/thesis/figures/``. Palettes mirror the
notebooks (09/10/13/11). No assets are written.

Every map figure carries a geographic-coordinate graticule (degree ticks with
hemisphere suffix), a north arrow and an approximate scale bar. All figure text is
localised: ``--lang pt`` (default) or ``--lang en`` / ``FIG_LANG``. Rendered PNGs
are also copied into the matching LaTeX tree (``docs/thesis/latex_pt/figures`` for
pt, ``docs/thesis/latex/figures`` for en); set ``FIG_COPY_LATEX=0`` to skip.

Usage:
    EE_PROJECT=probformer ../.venv/bin/python tools/make_figures.py [present|future|diag|all]
    ../.venv/bin/python tools/make_figures.py --check-i18n        # offline audit
    FIG_LANG=en ../.venv/bin/python tools/make_figures.py all     # English article
"""
from __future__ import annotations

import io
import math
import os
import shutil
import sys
from pathlib import Path

import ee
import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import requests
from matplotlib.cm import ScalarMappable
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.ticker import FuncFormatter, MultipleLocator
from mpl_toolkits.axes_grid1 import make_axes_locatable
from mpl_toolkits.axes_grid1.anchored_artists import AnchoredSizeBar
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import utils  # noqa: E402

PROJECT = "probformer"
FIG_DIR = Path(__file__).resolve().parent.parent / "thesis" / "Chapters" / "Figures"
LATEX_FIG = {
    "pt": FIG_DIR,
    "en": FIG_DIR,
}
DIMS = 1024
AOI_EXTENT = [-53.25, -45.90, -19.50, -12.39]   # [lon0, lon1, lat0, lat1] fallback (CLAUDE.md)

# runtime config (set by main() before Renderer() is constructed)
LANG = "pt"
CARTO = True

# palettes (mirror the notebooks)
PAL_SUIT = ["#d7191c", "#fdae61", "#ffffbf", "#a6d96a", "#1a9641"]  # 0..1 red->green
PAL_FAO = ["#d7191c", "#fdae61", "#a6d96a", "#1a9641"]              # N, S3, S2, S1
PAL_ZONE = ["#4575b4", "#91bfdb", "#f46d43", "#fdae61", "#66c2a5", "#1a9850", "#762a83"]  # 7 zones
PAL_ROLE = ["#eeeeee", "#ffd400", "#7b3294", "#d95f0e", "#2c7fb8", "#addd8e", "#006837"]
PAL_DIV = ["#b2182b", "#f7f7f7", "#2166ac"]                          # diverging ΔS
SEGMENTS = ["soybean", "sugarcane", "other_crops", "pisciculture", "cattle",
            "conservation", "solar"]

# --- i18n --------------------------------------------------------------------
# Keys are stable; `en` entries are the strings previously hard-coded in this
# module (zone labels excepted — those were stale and are corrected to the
# 2026-07-25 re-profiling described in both theses). `pt` entries are taken from
# docs/thesis/latex_pt/chapters/04_results.tex and 06_annex.tex.
TR = {
    "en": {
        "seg": {
            "soybean": "Soybean", "sugarcane": "Sugarcane",
            "other_crops": "Other annual crops", "pisciculture": "Pisciculture",
            "cattle": "Cattle", "conservation": "Conservation", "solar": "Solar PV",
        },
        "zone": [
            "Zone 0 — prime cropping plateau",
            "Zone 1 — warm dry shoulder",
            "Zone 2 — high clayey plateau",
            "Zone 3 — riparian lowland",
            "Zone 4 — warm sandy low plain",
            "Zone 5 — cool moist cropping plateau",
            "Zone 6 — steep conservation highland",
        ],
        "role": ["Other", "Soybean", "Sugarcane", "Other crops",
                 "Pisciculture", "Pasture", "Native"],
        "fao": ["N", "S3", "S2", "S1"],
        "factor": {
            "access_logtt": "Log travel time to city",
            "clim_aridity": "Aridity index (P/PET)",
            "clim_dry_months": "Dry-season length",
            "clim_gdd": "Growing degree-days",
            "clim_pr_annual": "Annual precipitation",
            "clim_pr_cv": "Rainfall seasonality (CV)",
            "clim_soil_moist": "Soil moisture",
            "clim_srad": "Solar radiation",
            "clim_twarm_q": "Warmest-quarter temperature",
            "cv_carbon": "Above-ground biomass carbon",
            "cv_pa_dist": "Distance to protected area",
            "cv_ruggedness": "Terrain ruggedness",
            "rl_native_frac": "Native-vegetation fraction",
            "sit_clearness": "Clearness index",
            "sit_water_dist_seas": "Distance to seasonal water",
            "soil_awc": "Plant-available water",
            "soil_clay": "Clay content",
            "soil_ph": "Soil pH",
            "soil_soc": "Soil organic carbon",
            "terr_northing": "Slope northing",
            "terr_slope": "Slope",
            "terr_twi": "Topographic wetness index",
            "water_drain_density": "Drainage density",
        },
        "axis.lon": "Longitude",
        "axis.lat": "Latitude",
        "cbar.suit": "Suitability (0–1)",
        "cbar.meansuit": "mean suitability",
        "cbar.deltaS": "ΔS (future − present), SSP5-8.5 2051–2070",
        "cbar.agreement": "fraction of GCMs agreeing on the sign of change",
        "fig_4_2.panel": "{seg} — FAO class",
        "fig_4_3.title": "Agro-environmental zones (k = 7)",
        "fig_4_4.panel": "Δ {seg}",
        "fig_4_5.title": "Ensemble agreement — other annual crops\n(SSP5-8.5, 2051–2070)",
        "fig_4_5.mean": "territory-mean agreement = {val:.3f}",
        "fig_4_6.title": "Best-crop reallocation\n(most-suitable crop changes, SSP5-8.5 2051–2070)",
        "fig_4_7.title": "Realized land use (majority role, 250 m)",
        "fig_4_8.title": "Soybean under-utilization\n(suitable ≥ S2, not currently soybean)",
        "fig_4_8.annot": "{pct:.1f}% of assessed land",
        "fig_4_9.left": "Municipal mean soybean suitability",
        "fig_4_9.right": "Vulnerable municipalities\n(projected other-crops ΔS < −0.05)",
        "fig_4_10.suptitle": "Cluster-validity indices and stability by k  (selected k = 7)",
        "fig_4_10.panel": ["Silhouette ↑", "Davies–Bouldin ↓", "Gap statistic ↑", "Stability ARI ↑"],
        "fig_4_10.kline": "selected k (7)",
        "fig_4_10.xlabel": "k",
        "fig_4_11.suptitle": "Factor share of the spatial variance of each segment's suitability",
        "fig_4_11.xlabel": "variance share",
        "legend.fao": "FAO class",
        "legend.underused": ["Other", "Under-utilized"],
        "legend.bestcrop": ["Unchanged", "Best crop changes"],
        "legend.vuln": ["not vulnerable", "vulnerable"],
    },
    "pt": {
        "seg": {
            "soybean": "Soja", "sugarcane": "Cana-de-açúcar",
            "other_crops": "Outras culturas anuais", "pisciculture": "Piscicultura",
            "cattle": "Pecuária", "conservation": "Conservação",
            "solar": "Geração fotovoltaica",
        },
        "zone": [
            "Zona 0 — planalto de cultivo privilegiado",
            "Zona 1 — ombro quente e seco",
            "Zona 2 — planalto alto e argiloso",
            "Zona 3 — baixada ripária",
            "Zona 4 — planície baixa, quente e arenosa",
            "Zona 5 — planalto de cultivo frio e úmido",
            "Zona 6 — planalto alto e íngreme de conservação",
        ],
        "role": ["Outros", "Soja", "Cana-de-açúcar", "Outras culturas",
                 "Piscicultura", "Pastagem", "Vegetação nativa"],
        "fao": ["N", "S3", "S2", "S1"],
        "factor": {
            "access_logtt": "Log do tempo de viagem à cidade",
            "clim_aridity": "Índice de aridez (P/ETP)",
            "clim_dry_months": "Duração da estação seca",
            "clim_gdd": "Graus-dia de crescimento",
            "clim_pr_annual": "Precipitação anual",
            "clim_pr_cv": "Sazonalidade da precipitação (CV)",
            "clim_soil_moist": "Umidade do solo",
            "clim_srad": "Radiação solar",
            "clim_twarm_q": "Temp. do trimestre mais quente",
            "cv_carbon": "Carbono em biomassa acima do solo",
            "cv_pa_dist": "Distância a área protegida",
            "cv_ruggedness": "Rugosidade do terreno",
            "rl_native_frac": "Fração de vegetação nativa",
            "sit_clearness": "Índice de claridade",
            "sit_water_dist_seas": "Distância à água sazonal",
            "soil_awc": "Água disponível para as plantas",
            "soil_clay": "Teor de argila",
            "soil_ph": "pH do solo",
            "soil_soc": "Carbono orgânico do solo",
            "terr_northing": "Componente norte da orientação",
            "terr_slope": "Declive",
            "terr_twi": "Índice de umidade topográfica",
            "water_drain_density": "Densidade de drenagem",
        },
        "axis.lon": "Longitude",
        "axis.lat": "Latitude",
        "cbar.suit": "Viabilidade (0–1)",
        "cbar.meansuit": "viabilidade média",
        "cbar.deltaS": "ΔS (futuro − presente), SSP5-8.5 2051–2070",
        "cbar.agreement": "fração de modelos que concordam quanto ao sinal da mudança",
        "fig_4_2.panel": "{seg} — classe FAO",
        "fig_4_3.title": "Zonas agroambientais (k = 7)",
        "fig_4_4.panel": "Δ {seg}",
        "fig_4_5.title": "Concordância entre modelos — outras culturas anuais\n(SSP5-8.5, 2051–2070)",
        "fig_4_5.mean": "concordância média territorial = {val:.3f}",
        "fig_4_6.title": "Realocação de melhor cultura\n(muda a cultura mais viável, SSP5-8.5 2051–2070)",
        "fig_4_7.title": "Uso atual da terra (função majoritária, 250 m)",
        "fig_4_8.title": "Subutilização da soja\n(viável ≥ S2 e sem soja atual)",
        "fig_4_8.annot": "{pct:.1f}% da terra avaliada",
        "fig_4_9.left": "Viabilidade média municipal da soja",
        "fig_4_9.right": "Municípios vulneráveis\n(ΔS projetado de outras culturas < −0,05)",
        "fig_4_10.suptitle": "Índices de validade de agrupamento e estabilidade por k  (k selecionado = 7)",
        "fig_4_10.panel": ["Silhueta ↑", "Davies–Bouldin ↓", "Estatística de gap ↑", "ARI de estabilidade ↑"],
        "fig_4_10.kline": "k selecionado (7)",
        "fig_4_10.xlabel": "k",
        "fig_4_11.suptitle": "Parcela de cada fator na variância espacial da viabilidade, por segmento",
        "fig_4_11.xlabel": "parcela da variância",
        "legend.fao": "classe FAO",
        "legend.underused": ["Outros", "Subutilizada"],
        "legend.bestcrop": ["Inalterado", "Melhor cultura muda"],
        "legend.vuln": ["não vulnerável", "vulnerável"],
    },
}


def _tr():
    return TR.get(LANG, TR["en"])


def t(key, **fmt):
    """Localised string for ``key`` (falls back to en, then to the key itself)."""
    val = _tr().get(key)
    if val is None:
        val = TR["en"].get(key, key)
    if fmt and isinstance(val, str):
        return val.format(**fmt)
    return val


def seg_title(s):
    return _tr()["seg"].get(s, TR["en"]["seg"].get(s, s))


def zone_labels():
    return _tr()["zone"]


def role_labels():
    return _tr()["role"]


def fao_labels():
    return _tr()["fao"]


def factor_name(f):
    d = _tr()["factor"]
    if f in d:
        return d[f]
    for p in ("clim_", "soil_", "terr_", "water_", "cv_", "sit_", "rl_", "access_"):
        if f.startswith(p):
            return f[len(p):].replace("_", " ")
    return f


def _lon_fmt(x, _pos=None):
    suf = ("O", "L") if LANG == "pt" else ("W", "E")
    return f"{abs(int(round(x)))}°{suf[0] if x < 0 else suf[1]}"


def _lat_fmt(y, _pos=None):
    return f"{abs(int(round(y)))}°{'S' if y < 0 else 'N'}"


def _audit_i18n():
    """Offline consistency check — hard-fails so English can't leak into the thesis."""
    en, pt = TR["en"], TR["pt"]
    errs = []
    if set(en) != set(pt):
        errs.append(f"top-level keys differ: only_en={sorted(set(en) - set(pt))} "
                    f"only_pt={sorted(set(pt) - set(en))}")
    for lang, d in (("en", en), ("pt", pt)):
        missing = set(SEGMENTS) - set(d["seg"])
        if missing:
            errs.append(f"{lang}: seg labels missing for {sorted(missing)}")
    if set(en["seg"]) != set(pt["seg"]):
        errs.append("seg keys differ en/pt")
    for key, n in (("zone", 7), ("role", 7), ("fao", 4), ("fig_4_10.panel", 4),
                   ("legend.underused", 2), ("legend.bestcrop", 2), ("legend.vuln", 2)):
        for lang, d in (("en", en), ("pt", pt)):
            got = len(d.get(key, []))
            if got != n:
                errs.append(f"{lang}: {key} must have {n} entries, has {got}")
    try:
        seg_cfg = utils.cfg("segments")["segments"]
        factors = {f for spec in seg_cfg.values() for f in spec.get("factors", {})}
    except Exception as e:                       # config unreadable — report, don't crash
        errs.append(f"could not read config/segments.yaml: {e}")
        factors = set()
    for lang, d in (("en", en), ("pt", pt)):
        missing = factors - set(d["factor"])
        if missing:
            errs.append(f"{lang}: factor labels missing for {sorted(missing)}")
    if set(en["factor"]) != set(pt["factor"]):
        errs.append("factor keys differ en/pt")
    if errs:
        raise SystemExit("i18n audit FAILED:\n  " + "\n  ".join(errs))


def _cmap(palette):
    return LinearSegmentedColormap.from_list("c", palette)


class Renderer:
    def __init__(self):
        utils.init(PROJECT)
        aoi = utils.load_aoi(PROJECT)
        self.geom = aoi if isinstance(aoi, ee.Geometry) else aoi.geometry()
        self.region = self.geom.bounds()
        self.aoi_fc = ee.FeatureCollection([ee.Feature(self.geom)])
        self.outline = ee.Image().byte().paint(self.aoi_fc, 1, 1)
        FIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            ring = self.region.coordinates().getInfo()[0]
            xs = [p[0] for p in ring]
            ys = [p[1] for p in ring]
            self.extent = [min(xs), max(xs), min(ys), max(ys)]
        except Exception as e:
            print(f"  extent: falling back to AOI_EXTENT ({e})")
            self.extent = list(AOI_EXTENT)

    def A(self, name):
        return ee.Image(utils.asset_id(PROJECT, name))

    def thumb(self, vis_img, add_outline=True):
        """Visualized ee.Image -> RGBA numpy array (clipped to AOI, AOI outline drawn)."""
        img = vis_img.clip(self.geom)
        if add_outline:
            img = img.blend(self.outline.visualize(palette=["000000"]))
        url = img.getThumbURL({"region": self.region, "dimensions": DIMS, "format": "png"})
        r = requests.get(url, timeout=180)
        r.raise_for_status()
        return np.asarray(Image.open(io.BytesIO(r.content)).convert("RGBA"))

    # --- shared map furniture ---------------------------------------------------
    def _map_axes(self, ax, *, left=True, bottom=True, labels=False):
        ax.set_xlim(self.extent[0], self.extent[1])
        ax.set_ylim(self.extent[2], self.extent[3])
        ax.xaxis.set_major_locator(MultipleLocator(2))
        ax.yaxis.set_major_locator(MultipleLocator(2))
        ax.xaxis.set_minor_locator(MultipleLocator(1))
        ax.yaxis.set_minor_locator(MultipleLocator(1))
        ax.xaxis.set_major_formatter(FuncFormatter(_lon_fmt))
        ax.yaxis.set_major_formatter(FuncFormatter(_lat_fmt))
        ax.tick_params(which="major", labelsize=8, length=3)
        ax.tick_params(which="minor", length=1.5)
        ax.grid(True, which="major", ls="--", lw=0.4, color="0.55", alpha=0.7)
        ax.tick_params(labelleft=left, labelbottom=bottom)
        if labels and left:
            ax.set_ylabel(t("axis.lat"), fontsize=9)
        if labels and bottom:
            ax.set_xlabel(t("axis.lon"), fontsize=9)

    def _scale_bar(self, ax, km=100):
        lat_c = 0.5 * (self.extent[2] + self.extent[3])
        deg = km / (111.32 * math.cos(math.radians(lat_c)))     # approx (spherical)
        bar = AnchoredSizeBar(
            ax.transData, deg, f"{km} km", "lower left", pad=0.4, borderpad=0.6,
            sep=4, frameon=True, color="k",
            size_vertical=(self.extent[3] - self.extent[2]) * 0.006,
        )
        bar.patch.set_alpha(0.8)
        ax.add_artist(bar)

    def _north_arrow(self, ax):
        ax.annotate("N", xy=(0.055, 0.93), xytext=(0.055, 0.80),
                    xycoords="axes fraction", ha="center", va="center",
                    fontsize=11, fontweight="bold",
                    arrowprops=dict(arrowstyle="-|>", lw=1.4, color="k"))

    def _imshow_map(self, ax, arr, *, carto=False, left=True, bottom=True, labels=False):
        ax.imshow(arr, extent=self.extent, aspect="equal", origin="upper",
                  interpolation="nearest")
        if CARTO and carto:
            self._scale_bar(ax)
            self._north_arrow(ax)
        self._map_axes(ax, left=left, bottom=bottom, labels=labels)

    def _discrete_legend(self, fig, palette, labels, *, ncol=None, anchor=(0.5, 0.02),
                         title=None, loc="lower center", fontsize=9):
        handles = [mpatches.Patch(color=c, label=l) for c, l in zip(palette, labels)]
        fig.legend(handles=handles, loc=loc, ncol=ncol or len(labels), frameon=False,
                   fontsize=fontsize, title=title, bbox_to_anchor=anchor)

    def _save(self, fig, name, *, tight=True):
        if tight:
            fig.tight_layout()
        path = FIG_DIR / f"{name}.png"
        dpi = 200 if name in ("fig_4_1", "fig_4_11") else 150
        fig.savefig(path, dpi=dpi, bbox_inches="tight")
        plt.close(fig)
        if os.environ.get("FIG_COPY_LATEX", "1") != "0":
            dest = LATEX_FIG.get(LANG)
            if dest is not None and dest.parent.exists():
                dest.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, dest / f"{name}.png")
        rel = path.relative_to(FIG_DIR.parent.parent.parent)
        print(f"wrote {rel}  ({path.stat().st_size // 1024} KB, lang={LANG})")

    # --- present-day figures --------------------------------------------------
    def fig_4_1(self):
        """7-panel present suitability surfaces + one shared horizontal colourbar."""
        suit = self.A("suit_present")
        panels = [(seg_title(s),
                   self.thumb(suit.select(f"suit_{s}").visualize(min=0, max=1, palette=PAL_SUIT)))
                  for s in SEGMENTS]
        fig, axes = plt.subplots(2, 4, figsize=(18, 9.5))
        flat = axes.ravel()
        for i, (ax, (title, arr)) in enumerate(zip(flat, panels)):
            self._imshow_map(ax, arr, left=(i % 4 == 0),
                             bottom=(i // 4 == 1 or i == 3), labels=True)
            ax.set_title(title, fontsize=11)
        flat[7].remove()                                    # 8th cell -> colourbar strip
        fig.subplots_adjust(left=0.06, right=0.985, top=0.95, bottom=0.14,
                            wspace=0.10, hspace=0.16)
        cax = fig.add_axes([0.30, 0.06, 0.40, 0.018])
        cb = fig.colorbar(ScalarMappable(Normalize(0, 1), _cmap(PAL_SUIT)),
                          cax=cax, orientation="horizontal")
        cb.set_label(t("cbar.suit"))
        self._save(fig, "fig_4_1", tight=False)

    def fig_4_2(self):
        """FAO class maps: soybean + conservation."""
        suit = self.A("suit_present")
        fig, axes = plt.subplots(1, 2, figsize=(12, 6.5))
        for i, (ax, s) in enumerate(zip(axes, ["soybean", "conservation"])):
            arr = self.thumb(suit.select(f"class_{s}").visualize(min=0, max=3, palette=PAL_FAO))
            self._imshow_map(ax, arr, left=(i == 0), bottom=True, labels=True)
            ax.set_title(t("fig_4_2.panel", seg=seg_title(s)), fontsize=11)
        self._discrete_legend(fig, PAL_FAO, fao_labels(), ncol=4, anchor=(0.5, 0.03),
                              title=t("legend.fao"))
        fig.subplots_adjust(bottom=0.16, wspace=0.12)
        self._save(fig, "fig_4_2", tight=False)

    def fig_4_3(self):
        """Agro-environmental zones (k=7)."""
        arr = self.thumb(self.A("zones_present").visualize(min=0, max=6, palette=PAL_ZONE))
        fig, ax = plt.subplots(figsize=(11, 8))
        self._imshow_map(ax, arr, carto=True, labels=True)
        ax.set_title(t("fig_4_3.title"), fontsize=12)
        handles = [mpatches.Patch(color=c, label=l) for c, l in zip(PAL_ZONE, zone_labels())]
        ax.legend(handles=handles, loc="center left", bbox_to_anchor=(1.03, 0.5),
                  frameon=False, fontsize=9)
        fig.subplots_adjust(left=0.09, right=0.62, top=0.93, bottom=0.08)
        self._save(fig, "fig_4_3", tight=False)

    def fig_4_7(self):
        """Realized land-use role."""
        arr = self.thumb(self.A("feat_realized").select("rl_role")
                         .visualize(min=0, max=6, palette=PAL_ROLE))
        fig, ax = plt.subplots(figsize=(11, 8))
        self._imshow_map(ax, arr, carto=True, labels=True)
        ax.set_title(t("fig_4_7.title"), fontsize=12)
        self._discrete_legend(fig, PAL_ROLE, role_labels(), ncol=4, anchor=(0.5, 0.03))
        fig.subplots_adjust(bottom=0.18)
        self._save(fig, "fig_4_7", tight=False)

    def fig_4_8(self):
        """Soybean potential-vs-realized under-utilization."""
        band = self.A("realized_vs_potential").select("underused_soybean")
        arr = self.thumb(band.visualize(min=0, max=1, palette=["#f7f7f7", "#d7301f"]))
        pct = None
        try:
            m = band.reduceRegion(reducer=ee.Reducer.mean(), geometry=self.region,
                                  scale=1000, bestEffort=True, tileScale=8,
                                  maxPixels=int(1e9)).getInfo()
            v = m.get("underused_soybean")
            pct = 100 * v if v is not None else None
        except Exception as e:
            print(f"  fig_4_8: reduceRegion failed ({e})")
        fig, ax = plt.subplots(figsize=(8.5, 8))
        self._imshow_map(ax, arr, carto=True, labels=True)
        ax.set_title(t("fig_4_8.title"), fontsize=12)
        if pct is not None:
            ax.text(0.02, 0.03, t("fig_4_8.annot", pct=pct), transform=ax.transAxes,
                    fontsize=9, va="bottom",
                    bbox=dict(fc="white", ec="0.5", alpha=0.85, pad=2))
        self._discrete_legend(fig, ["#f7f7f7", "#d7301f"], t("legend.underused"))
        fig.subplots_adjust(bottom=0.12)
        self._save(fig, "fig_4_8", tight=False)

    def fig_4_9(self):
        """Municipal choropleth: mean soybean suitability + projected-decline vulnerability."""
        muni = ee.FeatureCollection(utils.asset_id(PROJECT, "municipal_godf"))
        suit_img = ee.Image().float().paint(muni, "suit_soybean")
        vuln = muni.filter(ee.Filter.lt("delta_other_crops", -0.05))
        vuln_img = ee.Image().byte().paint(vuln, 1).paint(muni, 0, 1)  # fill flag + muni borders
        fig, axes = plt.subplots(1, 2, figsize=(13, 6.5))
        self._imshow_map(
            axes[0], self.thumb(suit_img.visualize(min=0.3, max=0.9, palette=PAL_SUIT)),
            left=True, bottom=True, labels=True)
        axes[0].set_title(t("fig_4_9.left"), fontsize=11)
        cax = make_axes_locatable(axes[0]).append_axes("right", size="4%", pad=0.1)
        cb = fig.colorbar(ScalarMappable(Normalize(0.3, 0.9), _cmap(PAL_SUIT)), cax=cax)
        cb.set_label(t("cbar.meansuit"))
        self._imshow_map(
            axes[1], self.thumb(vuln_img.visualize(min=0, max=1, palette=["#ffffff", "#762a83"])),
            left=False, bottom=True, labels=True)
        axes[1].set_title(t("fig_4_9.right"), fontsize=11)
        vlab = t("legend.vuln")
        axes[1].legend(
            handles=[mpatches.Patch(facecolor="#ffffff", edgecolor="0.4", label=vlab[0]),
                     mpatches.Patch(facecolor="#762a83", label=vlab[1])],
            loc="lower right", fontsize=8, framealpha=0.9)
        fig.subplots_adjust(wspace=0.2, bottom=0.1)
        self._save(fig, "fig_4_9", tight=False)

    # --- future scenario (atlas) --------------------------------------------
    def _crops3(self, img, prefix):
        return [img.select(f"{prefix}_{c}") for c in ["soybean", "sugarcane", "other_crops"]]

    def fig_4_4(self):
        """ΔS for the climate-sensitive segments, SSP5-8.5 2051-70 (diverging).

        Four panels: the three exposed segments (conservation — the steepest loser —
        other annual crops, solar PV) and a resilient cash crop (soybean)."""
        dl = self.A("delta_ssp585_2051_2070")
        segs = ["conservation", "other_crops", "solar", "soybean"]
        fig, axes = plt.subplots(2, 2, figsize=(12, 11.5))
        for i, (ax, s) in enumerate(zip(axes.ravel(), segs)):
            arr = self.thumb(dl.select(f"delta_{s}")
                             .visualize(min=-0.15, max=0.15, palette=PAL_DIV))
            self._imshow_map(ax, arr, left=(i % 2 == 0), bottom=(i // 2 == 1), labels=True)
            ax.set_title(t("fig_4_4.panel", seg=seg_title(s)), fontsize=11)
        fig.subplots_adjust(left=0.08, right=0.97, top=0.95, bottom=0.12,
                            wspace=0.06, hspace=0.12)
        cax = fig.add_axes([0.30, 0.055, 0.40, 0.018])
        cb = fig.colorbar(ScalarMappable(Normalize(-0.15, 0.15), _cmap(PAL_DIV)),
                          cax=cax, orientation="horizontal")
        cb.set_label(t("cbar.deltaS"))
        self._save(fig, "fig_4_4", tight=False)

    def fig_4_5(self):
        """Ensemble agreement for other annual crops, SSP5-8.5 2051-70.

        Agreement is ~1.0 across almost the whole territory, so the colour scale's
        lower bound is pulled to the data's 2nd percentile to reveal contrast and the
        territory-mean agreement is annotated on the map."""
        ag = self.A("agreement_ssp585_2051_2070").select("agreement_other_crops")
        pal = ["#ffffcc", "#a1dab4", "#41b6c4", "#225ea8"]
        lo, mean_ag = 0.5, None
        try:
            red = ee.Reducer.percentile([2]).combine(ee.Reducer.mean(), sharedInputs=True)
            st = ag.reduceRegion(reducer=red, geometry=self.region, scale=1000,
                                 bestEffort=True, tileScale=8,
                                 maxPixels=int(1e9)).getInfo()
            p2 = st.get("agreement_other_crops_p2")
            mean_ag = st.get("agreement_other_crops_mean")
            if p2 is not None:
                lo = min(math.floor(p2 * 100) / 100, 0.99)   # never collapse to [1, 1]
        except Exception as e:
            print(f"  fig_4_5: reduceRegion failed ({e}); using min=0.5")
        arr = self.thumb(ag.visualize(min=lo, max=1.0, palette=pal))
        fig, ax = plt.subplots(figsize=(9, 8))
        self._imshow_map(ax, arr, carto=True, labels=True)
        ax.set_title(t("fig_4_5.title"), fontsize=12)
        cax = make_axes_locatable(ax).append_axes("right", size="4%", pad=0.12)
        cb = fig.colorbar(ScalarMappable(Normalize(lo, 1.0), _cmap(pal)), cax=cax)
        cb.set_label(t("cbar.agreement"))
        if mean_ag is not None:
            ax.text(0.02, 0.03, t("fig_4_5.mean", val=mean_ag), transform=ax.transAxes,
                    fontsize=9, va="bottom",
                    bbox=dict(fc="white", ec="0.5", alpha=0.85, pad=2))
        self._save(fig, "fig_4_5", tight=False)

    def fig_4_6(self):
        """Best-crop reallocation: cells where argmax(soy,cane,other) flips present->future."""
        dl = self.A("delta_ssp585_2051_2070")
        fut = self.A("suit_future_ssp585_2051_2070")

        def argmax3(bands):
            idx = ee.Image.constant(0)
            mx = bands[0]
            for i, b in enumerate(bands[1:], 1):
                gt = b.gt(mx); idx = idx.where(gt, i); mx = mx.max(b)
            return idx.updateMask(bands[0].mask())

        fut_b = self._crops3(fut, "suit")
        pres_b = [f.subtract(d) for f, d in zip(fut_b, self._crops3(dl, "delta"))]
        flip = argmax3(pres_b).neq(argmax3(fut_b))
        arr = self.thumb(flip.visualize(min=0, max=1, palette=["#f7f7f7", "#e6550d"]))
        fig, ax = plt.subplots(figsize=(9, 8))
        self._imshow_map(ax, arr, carto=True, labels=True)
        ax.set_title(t("fig_4_6.title"), fontsize=12)
        self._discrete_legend(fig, ["#f7f7f7", "#e6550d"], t("legend.bestcrop"))
        fig.subplots_adjust(bottom=0.12)
        self._save(fig, "fig_4_6", tight=False)

    # --- CSV-based diagnostic figures (WS-D; no EE) -------------------------
    def _data_dir(self):
        return Path(os.environ.get("SCRATCHPAD", str(FIG_DIR.parent)))

    def _read_diag(self, name):
        path = self._data_dir() / name
        if not path.exists():
            raise SystemExit(
                f"{path} not found — the diagnostic CSVs are not in the repo.\n"
                f"Regenerate them from the built assets (no re-export):\n"
                f"    EE_PROJECT={PROJECT} uv run python tools/gen_diag_csvs.py\n"
                f"or point SCRATCHPAD at the directory that already holds them.")
        import pandas as pd
        return pd.read_csv(path)

    def fig_4_10(self):
        """k-selection: validity indices + cluster stability vs k (marks k=7)."""
        df = self._read_diag("zoning_kselect.csv").sort_values("k")
        K = 7
        fig, axes = plt.subplots(1, 4, figsize=(16, 4))
        titles = t("fig_4_10.panel")
        cols = ["silhouette", "davies_bouldin", "gap", "ari"]
        for j, (ax, col) in enumerate(zip(axes, cols)):
            ax.plot(df["k"], df[col], "-o", color="#2166ac", ms=4)
            if col == "ari" and "ari_std" in df:
                ax.fill_between(df["k"], df[col] - df["ari_std"], df[col] + df["ari_std"],
                                color="#2166ac", alpha=0.15)
            if col == "gap" and "s_k" in df:
                ax.errorbar(df["k"], df[col], yerr=df["s_k"], fmt="none",
                            ecolor="#999", elinewidth=0.8, capsize=2)
            kline = ax.axvline(K, color="#d7191c", ls="--", lw=1)
            if j == 0:
                kline.set_label(t("fig_4_10.kline"))
                ax.legend(fontsize=8, frameon=False, loc="lower right")
            ax.set_title(titles[j], fontsize=10)
            ax.set_xlabel(t("fig_4_10.xlabel"))
            ax.set_xticks(df["k"])
        fig.suptitle(t("fig_4_10.suptitle"), fontsize=12)
        self._save(fig, "fig_4_10")

    def fig_4_11(self):
        """Per-segment factor-variance decomposition (share of suitability variance)."""
        df = self._read_diag("factor_variance.csv")
        segs = [s for s in SEGMENTS if s in set(df["segment"])]
        nc = max(1, math.ceil(len(segs) / 2))
        fig, axes = plt.subplots(2, nc, figsize=(4.2 * nc, 10), squeeze=False)
        flat = axes.ravel()
        xmin = min(0.0, float(df["variance_share"].min()) * 1.08)
        xmax = float(df["variance_share"].max()) * 1.08
        for k, seg in enumerate(segs):
            ax = flat[k]
            d = df[df.segment == seg].sort_values("variance_share")
            vmax = d["variance_share"].max()
            colors = ["#1a9850" if v == vmax else ("#d7191c" if v < 0 else "#2166ac")
                      for v in d["variance_share"]]
            bars = ax.barh(range(len(d)), d["variance_share"], color=colors)
            ax.set_yticks(range(len(d)))
            ax.set_yticklabels([factor_name(f) for f in d["factor"]], fontsize=9)
            ax.set_xlim(xmin, xmax)
            ax.axvline(0, color="#333", lw=0.6)
            ax.bar_label(bars, fmt="%.2f", fontsize=8, padding=2)
            ax.set_title(seg_title(seg), fontsize=11)
            if k + nc >= len(segs):                         # nothing visible below -> label x
                ax.set_xlabel(t("fig_4_11.xlabel"), fontsize=9)
        for j in range(len(segs), len(flat)):
            flat[j].axis("off")
        fig.suptitle(t("fig_4_11.suptitle"), fontsize=12)
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        self._save(fig, "fig_4_11", tight=False)


PRESENT = ["fig_4_1", "fig_4_2", "fig_4_3", "fig_4_7", "fig_4_8", "fig_4_9"]
FUTURE = ["fig_4_4", "fig_4_5", "fig_4_6"]
DIAG = ["fig_4_10", "fig_4_11"]   # WS-D CSV-based diagnostics (k-selection, factor variance)


def _parse_args(argv):
    """Pull --lang / --no-carto / --check-i18n out of argv; env vars win. Returns
    the remaining positional args."""
    global LANG, CARTO
    argv = list(argv)
    lang = LANG
    if "--lang" in argv:
        i = argv.index("--lang")
        lang = argv[i + 1]
        del argv[i:i + 2]
    for a in list(argv):
        if a.startswith("--lang="):
            lang = a.split("=", 1)[1]
            argv.remove(a)
    LANG = os.environ.get("FIG_LANG", lang).lower()
    if LANG not in ("pt", "en"):
        raise SystemExit(f"--lang must be 'pt' or 'en' (got {LANG!r})")
    CARTO = os.environ.get("FIG_CARTO", "1") != "0"
    if "--no-carto" in argv:
        CARTO = False
        argv.remove("--no-carto")
    check = "--check-i18n" in argv
    if check:
        argv.remove("--check-i18n")
    return argv, check


def main():
    argv, check_only = _parse_args(sys.argv[1:])
    if check_only:
        _audit_i18n()
        print("i18n OK")
        return
    _audit_i18n()
    group = argv[0] if argv else "present"
    names = ({"present": PRESENT, "future": FUTURE, "diag": DIAG}.get(group)
             or PRESENT + FUTURE + DIAG)
    r = Renderer()
    for n in names:
        getattr(r, n)()
    print(f"done: {group} ({len(names)} figures, lang={LANG})")


if __name__ == "__main__":
    main()
