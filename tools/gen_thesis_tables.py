"""Generate the thesis' data tables as \\input-able LaTeX fragments.

Every numeric table in the thesis used to be a hand-typed tabular, wired to
nothing. That is how the k-selection prose came to quote a silhouette maximum at
k=10 while the CSV behind its own figure peaked at k=6, and how tab:spec-longtable
kept factor counts the AHP derivation had already changed. This tool makes the
CSVs the single source: the chapters keep the float, the caption and the label,
and \\input the tabular body from thesis/Chapters/Tables/.

Fragments are complete `tabular` environments (column spec included), so the
zone-indexed tables follow K automatically -- nothing to retype when K moves.

    \\input{Chapters/Tables/zone_suit.tex}

The path is relative to thesis/ (latexmk's CWD), not to the chapter file --
\\graphicspath does not apply to \\input.

Zone ids are 1-based everywhere here, matching zone_profiles.csv and the prose.
The zones_present raster is 0-based; that +1 is applied once, in
zoning.profile_zones and in the extract_* tools, never again here.

Run:  uv run python tools/gen_thesis_tables.py [name ...]      (default: all)
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pandas as pd
import yaml

REPO = Path(__file__).resolve().parent.parent
CHAPTERS = REPO / "thesis" / "Chapters"
IN = Path(os.environ.get("SCRATCHPAD", str(CHAPTERS)))
OUT = CHAPTERS / "Tables"

# Thesis-facing PT names. These are the strings already used in the chapters, so
# regenerating a table does not silently reword it.
SEG_PT = {
    "soybean": "Soja",
    "sugarcane": "Cana-de-açúcar",
    "other_crops": "Outras culturas anuais",
    "pisciculture": "Piscicultura",
    "cattle": "Pecuária",
    "conservation": "Conservação",
    "solar": "Geração fotovoltaica",
}
SEG_SHORT = {                      # for the narrow "melhor comparativo" row
    "soybean": "soja", "sugarcane": "cana", "other_crops": "outras",
    "pisciculture": "pisc.", "cattle": "pecuária", "conservation": "consv.",
    "solar": "solar",
}
FACTOR_PT = {
    "access_logtt": "Log do tempo de viagem à cidade",
    "clim_aridity": "Índice de aridez (P/ETP)",
    "clim_dry_months": "Meses secos (n)",
    "clim_gdd": "Graus-dia de crescimento",
    "clim_pr_annual": "Precipitação anual (mm)",
    "clim_pr_cv": "CV da precipitação",
    "clim_soil_moist": "Umidade do solo (mm)",
    "clim_srad": "Radiação solar (W/m$^2$)",
    "clim_twarm_q": "Temp. do trimestre mais quente ($^\\circ$C)",
    "cv_carbon": "Carbono em biomassa acima do solo (Mg~C/ha)",
    "cv_pa_dist": "Distância a área protegida (m)",
    "cv_ruggedness": "Rugosidade do terreno (m)",
    "rl_native_frac": "Fração de vegetação nativa",
    "sit_clearness": "Índice de claridade (cobertura de nuvens)",
    "sit_water_dist_seas": "Distância à água sazonal (m)",
    "soil_awc": "Teor de água disponível para as plantas",
    "soil_clay": "Teor de argila (\\%)",
    "soil_ph": "pH do solo",
    "soil_soc": "Carbono orgânico do solo (g/kg)",
    "terr_northing": "Componente norte da orientação",
    "terr_slope": "Declive ($^\\circ$)",
    "terr_twi": "Índice de umidade topográfica",
    "water_drain_density": "Densidade de drenagem",
}
SHAPE_PT = {"increasing": "crescente", "decreasing": "decrescente",
            "range": "intervalar", "trapezoid": "intervalar"}
MASK_PT = {"available": "disponível", "exclude_only": "apenas exclusão",
           "none": "nenhuma"}
# Conservation's two *mobile* climate factors -- what keeps it CMIP6-responsive.
# The paragraph after tab:spec-longtable refers to them by this dagger.
DAGGER = {("conservation", "clim_aridity"), ("conservation", "clim_twarm_q")}
# tab:zone-means rows: (zone_profiles.csv column, PT label, decimals)
BIOPHYS = [
    ("terr_elev", "Elevação (m)", 0),
    ("terr_slope", "Declive ($^\\circ$)", 1),
    ("terr_twi", "Índice de umidade topográfica", 1),
    ("clim_twarm_q", "Temp. do trimestre mais quente ($^\\circ$C)", 1),
    ("clim_aridity", "Índice de aridez (P/ETP)", 2),
    ("clim_soil_moist", "Umidade do solo (mm)", 0),
    ("soil_clay", "Teor de argila (\\%)", 1),
    ("soil_soc", "Carbono orgânico do solo (g/kg)", 1),
    ("water_drain_density", "Densidade de drenagem (fração)", 3),
    ("water_dist", "Distância à água (m)", 0),
]
REALIZED = [
    ("rl_soybean_frac", "Soja"),
    ("rl_sugarcane_frac", "Cana-de-açúcar"),
    ("rl_other_crops_frac", "Outras culturas anuais"),
    ("rl_pasture_frac", "Pastagem"),
    ("rl_native_frac", "Vegetação nativa"),
]
SSP_PT = {"ssp245": "SSP2-4.5", "ssp585": "SSP5-8.5"}


# --- formatting -----------------------------------------------------------------
def num(v, dec=2):
    """PT number: comma decimal, dot thousands separator."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "---"
    s = f"{v:,.{dec}f}"                       # 1,234.56
    return s.replace(",", "\u0001").replace(".", ",").replace("\u0001", ".")


def pct(v, dec=1):
    return f"{num(100 * v, dec)}\\%"


def signed(v, dec=3):
    """Aligned +/- for delta columns, as the thesis writes them."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "---"
    return ("$+$" if v >= 0 else "$-$") + num(abs(v), dec)


def tabular(colspec, header, rows, *, midrules=()):
    """A complete booktabs tabular. `rows` are lists of already-formatted cells."""
    out = [f"\\begin{{tabular}}{{@{{}}{colspec}@{{}}}}", "\\toprule",
           " & ".join(header) + " \\\\", "\\midrule"]
    for i, r in enumerate(rows):
        if i in midrules:
            out.append("\\midrule")
        out.append(" & ".join(r) + " \\\\")
    out += ["\\bottomrule", "\\end{tabular}"]
    return "\n".join(out) + "\n"


def write(name, body):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    header = ("% GENERATED by tools/gen_thesis_tables.py -- do not edit by hand.\n"
              "% Edit the source CSV and regenerate; see CLAUDE.md §9.\n")
    path.write_text(header + body, encoding="utf-8")
    print(f"  wrote {path.relative_to(REPO)}")


def read_csv(name):
    """$SCRATCHPAD -> thesis/Chapters -> repo root.

    The repo-root leg is for zone_profiles.csv, which the Part-10 cascade writes
    beside the code rather than into thesis/Chapters (make_figures.zone_k() does
    the same dance).
    """
    for path in (IN / name, CHAPTERS / name, REPO / name):
        if path.exists():
            return pd.read_csv(path)
    raise FileNotFoundError(name)


def zones_of(df):
    return sorted(int(z) for z in df["zone"].unique())


def zone_header(first, zs):
    return [first] + [f"Z{z}" for z in zs]


# --- fragments ------------------------------------------------------------------
def zone_suit():
    """Per-zone mean suitability, closed by the comparative vocation rows.

    Two label rows, not one: with K below the seven segments a single argmax
    leaves segments spoken for by no zone at all, so the runner-up is reported
    beside the winner, with the z-gap between them. A small margin is the honest
    way to say the headline label is nearly a tie (zoning.profile_zones).
    """
    p = read_csv("zone_profiles.csv").set_index("zone")
    zs = sorted(p.index)
    rows = [[SEG_PT[s]] + [num(p.loc[z, f"suit_{s}"], 2) for z in zs] for s in SEG_PT]
    label_rows = [["\\textbf{Vocação primária}"]
                  + [SEG_SHORT[p.loc[z, "comparative_segment"]] for z in zs]]
    if "comparative_segment_2" in p.columns:
        label_rows.append(["\\textbf{Vocação secundária}"]
                          + [SEG_SHORT[p.loc[z, "comparative_segment_2"]] for z in zs])
    if "comparative_margin" in p.columns:
        label_rows.append(["\\textbf{Margem} ($z$)"]
                          + [num(p.loc[z, "comparative_margin"], 2) for z in zs])
    rows += label_rows
    write("zone_suit.tex",
          tabular("l" + "r" * len(zs), zone_header("Segmento", zs), rows,
                  midrules={len(rows) - len(label_rows)}))


def zone_means():
    p = read_csv("zone_profiles.csv").set_index("zone")
    zs = sorted(p.index)
    try:
        area = read_csv("zone_area.csv").set_index("zone")
    except FileNotFoundError:
        print("  !! zone_area.csv missing -- run tools/extract_present.py first "
              "(sample n is NOT an area share)")
        return
    rows = [["Tamanho da amostra (pontos)"] + [num(p.loc[z, "n"], 0) for z in zs],
            ["Parcela da área de interesse"]
            + [f"{num(area.loc[z, 'share_pct'], 1)}\\%" for z in zs]]
    rows += [[lab] + [num(p.loc[z, col], dec) for z in zs] for col, lab, dec in BIOPHYS]
    write("zone_means.tex",
          tabular("l" + "r" * len(zs), zone_header("Variável", zs), rows))


def zone_realized():
    p = read_csv("zone_profiles.csv").set_index("zone")
    zs = sorted(p.index)
    rows = [[lab] + [pct(p.loc[z, col], 1) for z in zs] for col, lab in REALIZED]
    write("zone_realized.tex",
          tabular("l" + "r" * len(zs), zone_header("Uso atual", zs), rows))


def zone_shift():
    try:
        d = read_csv("cmip6_zone_shift.csv")
    except FileNotFoundError:
        print("  !! cmip6_zone_shift.csv missing -- run tools/extract_cmip6.py first")
        return
    zs = zones_of(d)
    rows, midrules, prev = [], set(), None
    for seg in [s for s in SEG_PT if s in set(d["segment"])]:
        for ssp in ["ssp245", "ssp585"]:
            for win in sorted(d["window"].unique()):
                sub = d[(d.segment == seg) & (d.ssp == ssp) & (d.window == win)]
                if sub.empty:
                    continue
                if prev is not None and seg != prev:
                    midrules.add(len(rows))
                prev = seg
                byz = dict(zip(sub["zone"], sub["delta_s"]))
                label = f"{SSP_PT[ssp]} {win.replace('_', '--')}"
                rows.append([SEG_PT[seg], label]
                            + [signed(byz.get(z), 3) for z in zs])
    write("zone_shift.tex",
          tabular("ll" + "r" * len(zs),
                  ["Segmento", "Cenário--janela"] + [f"Z{z}" for z in zs],
                  rows, midrules=midrules))


def _combo_cols(d):
    """Ordered (ssp, window) pairs present in a CMIP6 CSV, with PT header labels."""
    combos = sorted({(r.ssp, r.window) for r in d.itertuples()})
    heads = [f"{SSP_PT[ssp]} {win.replace('_', '--')}" for ssp, win in combos]
    return combos, heads


def shift_mean():
    try:
        d = read_csv("cmip6_shift_mean.csv")
    except FileNotFoundError:
        print("  !! cmip6_shift_mean.csv missing -- run tools/extract_cmip6.py first")
        return
    combos, heads = _combo_cols(d)
    idx = {(r.segment, r.ssp, r.window): r.delta_s for r in d.itertuples()}
    rows = [[SEG_PT[seg]] + [signed(idx.get((seg, ssp, win)), 4) for ssp, win in combos]
            for seg in SEG_PT if any(k[0] == seg for k in idx)]
    write("shift_mean.tex",
          tabular("l" + "r" * len(combos), ["Segmento"] + heads, rows))


def shift_share():
    try:
        d = read_csv("cmip6_shift_share.csv")
    except FileNotFoundError:
        print("  !! cmip6_shift_share.csv missing -- run tools/extract_cmip6.py first")
        return
    combos, heads = _combo_cols(d)
    fut = {(r.segment, r.ssp, r.window): r.future_share for r in d.itertuples()}
    pres = {r.segment: r.present_share for r in d.itertuples()}
    rows = [[SEG_PT[seg], pct(pres[seg], 1)]
            + [pct(fut.get((seg, ssp, win)), 1) for ssp, win in combos]
            for seg in SEG_PT if seg in pres]
    write("shift_share.tex",
          tabular("lr" + "r" * len(combos), ["Segmento", "Presente"] + heads, rows))


def downgrade():
    try:
        d = read_csv("cmip6_downgrade.csv")
    except FileNotFoundError:
        print("  !! cmip6_downgrade.csv missing -- run tools/extract_cmip6.py first")
        return
    combos, heads = _combo_cols(d)
    idx = {(r.segment, r.ssp, r.window): r.downgrade_share for r in d.itertuples()}
    rows = [[SEG_PT[seg]] + [pct(idx.get((seg, ssp, win)), 1) for ssp, win in combos]
            for seg in SEG_PT if any(k[0] == seg for k in idx)]
    write("downgrade_share.tex",
          tabular("l" + "r" * len(combos), ["Segmento"] + heads, rows))


def transition():
    try:
        d = read_csv("cmip6_transition_othercrops.csv")
    except FileNotFoundError:
        print("  !! cmip6_transition_othercrops.csv missing -- run tools/extract_cmip6.py first")
        return
    order = ["N", "S3", "S2", "S1"]
    idx = {(r.present, r.future): r.share_pct for r in d.itertuples()}
    rows = []
    for pres in order:
        cells = [f"{num(idx.get((pres, f), 0.0), 1)}\\%" for f in order]
        tot = sum(idx.get((pres, f), 0.0) for f in order)
        rows.append([pres] + cells + [f"\\textbf{{{num(tot, 1)}\\%}}"])
    write("transition_othercrops.tex",
          tabular("lrrrrr",
                  ["Presente $\\downarrow$ / futuro $\\rightarrow$"] + order
                  + ["Total presente"], rows))


def ahp_weights():
    """tab:spec-longtable body: every factor of every segment.

    The roster comes from breakpoint_anchoring.csv (it carries the shape and the
    adopted thresholds) and the weight from ahp_weights.csv. Since the removal of
    the ``role: gate`` exemption (2026-10-02) every factor carries a weight, so
    there is no longer a "porta" row and no second sort key. w_atual/delta are
    deliberately NOT printed: they are a snapshot of the previous derivation, not
    current drift.
    """
    bp = read_csv("breakpoint_anchoring.csv")
    w = read_csv("ahp_weights.csv").set_index(["segment", "factor"])["w_final"]
    seg_cfg = yaml.safe_load((REPO / "config" / "segments.yaml").read_text())["segments"]

    lines = []
    for seg in SEG_PT:
        sub = bp[bp.segment == seg]
        if sub.empty:
            continue
        # by descending weight
        sub = sub.assign(
            _w=[w.get((seg, f), float("nan")) for f in sub.factor],
        ).sort_values("_w", ascending=False)
        spec = seg_cfg.get(seg, {})
        mask_pt = MASK_PT.get(spec.get("mask", "available"), spec.get("mask"))
        if spec.get("aggregate") == "arithmetic":
            mask_pt += "; compensatória"      # the one non-geometric segment
        first = True
        for _, r in sub.iterrows():
            name = FACTOR_PT.get(r.factor, r.factor.replace("_", "\\_"))
            if (seg, r.factor) in DAGGER:
                name += " $\\dagger$"      # the prose after the table explains these
            pts = ast.literal_eval(r.points_adotados)
            thresh = ", ".join(num(v, 2).rstrip("0").rstrip(",") if isinstance(v, float)
                               else str(v) for v in pts)
            weight = num(r._w, 2)
            head = f"\\textbf{{{SEG_PT[seg]}}} ({mask_pt})" if first else ""
            first = False
            lines.append([head, name, weight, SHAPE_PT.get(r.type, r.type), thresh])
    # Body rows only: the target is a longtable that must break across pages, so
    # the chapter keeps the skeleton (colspec, caption, \endfirsthead/\endhead).
    # Its column count is fixed at 5 and does not follow K, unlike the zone tables.
    # \bottomrule MUST be emitted here, not left in the chapter after the \input:
    # a \noalign (which \bottomrule is) placed after an \input inside an alignment
    # is "Misplaced \noalign" -- the file boundary already opened the next row.
    body = "\n".join(" & ".join(r) + " \\\\" for r in lines)
    write("ahp_weights.tex", body + "\n\\bottomrule\n")


def ahp_cr():
    doc = yaml.safe_load((REPO / "config" / "ahp_matrices.yaml").read_text())
    rows = []
    for seg, label in SEG_PT.items():
        d = (doc["segments"].get(seg) or {}).get("derived")
        if not d:
            continue
        rows.append([label, str(len(d["priority_vector"])),
                     num(d["consistency_ratio"], 4)])
    write("ahp_cr.tex",
          tabular("lrr", ["Segmento", "Fatores ($n$)", "Razão de consistência"], rows))


def validation():
    try:
        a = read_csv("validation_zone_anova.csv")
    except FileNotFoundError:
        print("  !! validation_zone_anova.csv missing -- run tools/run_validation.py first")
        return
    rows = [[f"Z{int(r.zone)}", num(r.mean_npp, 3), num(r.n, 0)]
            for r in a.sort_values("zone").itertuples()]
    write("validation.tex",
          tabular("lrr", ["Zona", "NPP média (MOD17)", "$n$"], rows))


TABLES = {
    "zone_suit": zone_suit, "zone_means": zone_means, "zone_realized": zone_realized,
    "zone_shift": zone_shift, "shift_mean": shift_mean, "shift_share": shift_share,
    "downgrade": downgrade, "transition": transition,
    "ahp_weights": ahp_weights, "ahp_cr": ahp_cr,
    "validation": validation,
}


def main():
    want = sys.argv[1:] or list(TABLES)
    if bad := [n for n in want if n not in TABLES]:
        raise SystemExit(f"unknown table(s): {bad}\navailable: {list(TABLES)}")
    print(f"=== generating {len(want)} table fragment(s) into "
          f"{OUT.relative_to(REPO)} ===")
    for n in want:
        try:
            TABLES[n]()
        except FileNotFoundError as e:
            print(f"  !! {n}: missing input {e}")
    print("=== done ===")


if __name__ == "__main__":
    main()
