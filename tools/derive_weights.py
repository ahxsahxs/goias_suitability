"""Part 9 — derive the AHP weights from literature-anchored pairwise judgements.

Replaces ``tools/build_ahp.py``, which ran the derivation **backwards**: it took the
weights already written in ``config/segments.yaml`` and manufactured a Saaty matrix
that reproduced them (``a_ij = snap(w_i/w_j)``), so the resulting consistency ratios
(1e-4..1e-3) measured the care of the reconstruction, not the coherence of any
judgement.

Here the arrow points the other way::

    config/ahp_matrices.yaml      anchors: one ordinal band per factor, plus the
        (hand-written INPUT)      published priority r where a factor maps onto a
             |                    source criterion
             |  rules A / B / C   every a_ij is a deterministic function of the
             v                    anchors, recomputed and asserted here
        pairwise matrix  ->  true principal eigenvector  =  w_lit
             |
             |  x sigma_h(mu)^lambda   regional adaptation, lambda fixed a priori,
             v                       sigma_h measured over present U future
        config/segments.yaml      weight: (machine-written)

The point of the band mechanism is arithmetic, not moral: the author sets *n*
ordinals per segment instead of n(n-1)/2 free matrix cells, so "was a target weight
vector fitted?" becomes a property this tool can check rather than a claim the
thesis has to assert. See ``docs/ahp_literatura.md`` for the full protocol.

Run::

    uv run python tools/derive_weights.py            # derive + write
    uv run python tools/derive_weights.py --check    # verify sync, write nothing
    uv run python tools/derive_weights.py --dry-run  # derive + report only

Offline and deterministic; no Earth Engine. The discrimination column ``d`` is read
from ``thesis/Chapters/factor_discrimination.csv`` (produced by
``tools/anchor_breakpoints.py``); without it the tool reports ``w_lit`` and stops
before the regional stage.

``d`` is ``sigma_mu_horizon`` -- sigma(mu) over the present UNION the CMIP6 horizon
(SSP5-8.5, 2051-2070) -- not ``sigma_mu_available``, which is the present alone.
A factor whose observed range sits inside its own optimal plateau has
sigma_mu_available = 0 exactly, so w = w_lit * 0^lambda = 0, mu^0 = 1, and the
factor drops out of the geometric mean, taking its CMIP6 lever with it. That was
what the ``role: gate`` exemption existed to avoid; measuring the gradation over
the horizon instead removes the exemption without reintroducing the trap. See the
header of ``config/ahp_matrices.yaml``.
"""
from __future__ import annotations

import argparse
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402
from ruamel.yaml import YAML  # noqa: E402

import membership  # noqa: E402

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
AHP_YAML = os.path.join(ROOT, "config", "ahp_matrices.yaml")
SEG_YAML = os.path.join(ROOT, "config", "segments.yaml")
CHAPTERS = os.path.join(ROOT, "thesis", "Chapters")
DISCRIM_CSV = os.path.join(CHAPTERS, "factor_discrimination.csv")
WEIGHTS_CSV = os.path.join(CHAPTERS, "ahp_weights.csv")
LAMBDA_CSV = os.path.join(CHAPTERS, "lambda_sweep.csv")

SAATY = np.arange(1, 10, dtype=float)      # integer Saaty scale, R2
LADDER = {0: 1.0, 1: 3.0, 2: 5.0, 3: 7.0}  # band-difference ladder, R4
LAMBDA_GRID = [0.0, 0.25, 0.5, 0.75, 1.0]


# --- rule primitives ---------------------------------------------------------
def snap_saaty(ratio: float) -> float:
    """Nearest point of {1..9} u reciprocals to ``ratio``, in log space (R2/R3)."""
    if ratio >= 1.0:
        return float(SAATY[np.argmin(np.abs(np.log(SAATY) - math.log(ratio)))])
    return 1.0 / snap_saaty(1.0 / ratio)


def ladder(delta_band: int) -> float:
    """``a_ij`` from a band difference (R4). Band 1 = most important."""
    mag = LADDER[min(abs(delta_band), 3)]
    return mag if delta_band >= 0 else 1.0 / mag


def tercile(rank: int, n_criteria: int) -> int:
    """Tercile (1..3) of a published rank within its source's criterion set."""
    return min(3, math.ceil(rank * 3 / n_criteria))


def allowed_bands(anchor: dict) -> tuple[int, int]:
    """Band range a factor may occupy: tercile-constrained when anchored (R4)."""
    if "r" not in anchor:
        return (1, 4)
    t = tercile(anchor["rank"], anchor["n_criteria"])
    return (t, t + 1)


def r_star(anchors: dict) -> dict:
    """Published priorities renormalized within each source+block (R3)."""
    out = {}
    blocks: dict[tuple, list] = {}
    for f, a in anchors.items():
        if "r" in a:
            blocks.setdefault((a["source"], a["block"]), []).append(f)
    for key, fs in blocks.items():
        tot = sum(anchors[f]["r"] for f in fs)
        for f in fs:
            out[f] = anchors[f]["r"] / tot
    return out


# --- matrix construction -----------------------------------------------------
def build_matrix(factors, anchors, bands, overrides):
    """Saaty matrix + the judgement record, both derived from the anchors."""
    rs = r_star(anchors)
    n = len(factors)
    A = np.ones((n, n))
    judgements = []
    for i in range(n):
        for j in range(i + 1, n):
            fi, fj = factors[i], factors[j]
            ai, aj = anchors[fi], anchors[fj]
            same_block = (
                "r" in ai and "r" in aj
                and ai["source"] == aj["source"] and ai["block"] == aj["block"]
            )
            if same_block:
                rule, a = "A", snap_saaty(rs[fi] / rs[fj])
                basis = (f"r*({fi})/r*({fj}) = {rs[fi]:.4f}/{rs[fj]:.4f} "
                         f"= {rs[fi] / rs[fj]:.3f}")
                src = f"{ai['source']}, {ai['locator']}"
            else:
                # C only when NEITHER factor is anchored; a cross-block or
                # cross-source pair between two anchored factors is still B —
                # their published priorities are normalized over different
                # criterion sets, so the ratio carries no meaning (R3), but the
                # bands are still literature-constrained.
                rule = "C" if ("r" not in ai and "r" not in aj) else "B"
                a = ladder(bands[fj] - bands[fi])
                basis = f"faixa {bands[fi]} vs {bands[fj]}"
                src = "faixa ordinal (R4)"
            key = f"{fi}|{fj}"
            if key in overrides:
                a = float(overrides[key]["value"])
                rule += "*"
                basis = f"override: {overrides[key]['reason']}"
            A[i, j], A[j, i] = a, 1.0 / a
            judgements.append({
                "pair": [fi, fj], "a_ij": round(float(a), 4), "rule": rule,
                "basis": basis, "source": src,
            })
    return A, judgements


def factor_is_free(anchors, f):
    return "r" not in anchors[f]


def derive_segment(name, spec, cr_max, max_rev, verbose=True):
    """Matrix -> w_lit, with the bounded band-revision loop of R6."""
    factors = list(spec["factors"])
    anchors = spec["anchors"]
    overrides = spec.get("overrides", {}) or {}
    bands = {f: anchors[f]["band"] for f in factors}
    revisions = []

    for it in range(max_rev + 1):
        A, judgements = build_matrix(factors, anchors, bands, overrides)
        cr, w = membership.consistency_ratio(A)
        lam = float(np.linalg.eigvals(A).real.max())
        if cr <= cr_max:
            break
        if it == max_rev:
            raise SystemExit(
                f"\n[FALHA] {name}: RC = {cr:.4f} > {cr_max} apos {max_rev} revisoes.\n"
                "        O protocolo (R6.6) proibe continuar revisando: o segmento precisa\n"
                "        ser reestruturado como hierarquia de dois niveis, nao ajustado."
            )
        # R6: worst Saaty deviation, then revise a BAND by exactly +-1
        wv = np.asarray(w)
        dev = np.abs(np.log(A * (wv[None, :] / wv[:, None])))
        np.fill_diagonal(dev, 0.0)
        i, j = np.unravel_index(np.argmax(dev), dev.shape)
        pair = [factors[i], factors[j]]
        # free (class-C) factors first, then anchored ones within their tercile
        cands = [f for f in pair if factor_is_free(anchors, f)] or pair
        best = None
        for f in cands:
            lo, hi = allowed_bands(anchors[f])
            for step in (-1, 1):
                nb = bands[f] + step
                if not (lo <= nb <= hi):
                    continue
                trial = dict(bands, **{f: nb})
                tA, _ = build_matrix(factors, anchors, trial, overrides)
                tcr, _ = membership.consistency_ratio(tA)
                if best is None or tcr < best[0]:
                    best = (tcr, f, nb, trial)
        if best is None:
            raise SystemExit(
                f"\n[FALHA] {name}: RC = {cr:.4f} e nenhuma revisao de faixa admissivel "
                "(todas violariam o tercil da fonte)."
            )
        tcr, f, nb, trial = best
        revisions.append({
            "iteration": it + 1, "factor": f,
            "band_before": bands[f], "band_after": nb,
            "cr_before": round(cr, 4), "cr_after": round(tcr, 4),
            "reason": f"maior desvio de Saaty no par {pair[0]}x{pair[1]}",
        })
        if verbose:
            print(f"    revisao {it + 1}: {f} faixa {bands[f]} -> {nb} "
                  f"(RC {cr:.4f} -> {tcr:.4f})")
        bands = trial

    n = len(factors)
    approx = membership.approx_eigenvector(A)
    approx = [x / sum(approx) for x in approx]
    classes = {}
    for jd in judgements:
        classes[jd["rule"][0]] = classes.get(jd["rule"][0], 0) + 1
    n_pairs = n * (n - 1) // 2
    return {
        "factors": factors,
        "bands_final": {f: bands[f] for f in factors},
        "matrix": [[round(float(x), 4) for x in row] for row in A],
        "judgements": judgements,
        "lambda_max": round(lam, 4),
        "consistency_index": round((lam - n) / (n - 1), 4) if n > 1 else 0.0,
        "random_index": membership.random_index(n),
        "consistency_ratio": round(float(cr), 4),
        "priority_vector": [round(float(x), 4) for x in w],
        "approx_eigenvector_max_gap": round(
            float(np.max(np.abs(np.asarray(w) - np.asarray(approx)))), 4),
        "class_counts": {k: classes.get(k, 0) for k in ("A", "B", "C")},
        "anchored_fraction": round(classes.get("A", 0) / n_pairs, 4),
        "author_judgement_count": sum(
            1 for a in spec["anchors"].values()
            if str(a.get("rationale", "")).startswith("author judgement")),
        "override_count": len(overrides),
        "revisions": revisions,
    }


# --- regional adaptation -----------------------------------------------------
D_COLUMN = "sigma_mu_horizon"


def load_discrimination():
    """``d = sigma(mu)`` over present U horizon, per (segment, factor)."""
    if not os.path.exists(DISCRIM_CSV):
        return None
    df = pd.read_csv(DISCRIM_CSV)
    if D_COLUMN not in df.columns:
        raise SystemExit(
            f"\n[FALHA] {os.path.relpath(DISCRIM_CSV, ROOT)} nao tem a coluna "
            f"{D_COLUMN!r}.\n"
            "        O CSV e anterior a remocao dos fatores-porta (2026-10-02).\n"
            "        Rode:  EE_PROJECT=probformer uv run python "
            "tools/anchor_breakpoints.py discrimination\n"
            "        Usar sigma_mu_available aqui zeraria o peso de todo fator\n"
            "        saturado no presente -- o que a mudanca existe para evitar."
        )
    return {(r.segment, r.factor): float(getattr(r, D_COLUMN))
            for r in df.itertuples()}


def adapt(w_lit, d, lam):
    """``w = normalize(w_lit * d^lambda)`` (the d-bar divisor cancels here)."""
    v = np.asarray(w_lit, dtype=float) * np.power(np.asarray(d, dtype=float), lam)
    if v.sum() <= 0:
        raise ValueError("todos os fatores com d = 0: segmento sem poder discriminante")
    return (v / v.sum()).tolist()


def round_to_unit(w, places=4):
    """Round to ``places`` dp and put the residual on the largest weight."""
    r = [round(x, places) for x in w]
    r[int(np.argmax(r))] += round(1.0 - sum(r), places)
    return [round(x, places) for x in r]


# --- segments.yaml write-back ------------------------------------------------
def segments_rt():
    y = YAML(typ="rt")
    y.width = 4096
    y.preserve_quotes = True
    with open(SEG_YAML, encoding="utf-8") as fh:
        return y, y.load(fh)


def write_segments(weights):
    """Write ``weight:`` back into config/segments.yaml, preserving comments."""
    y, doc = segments_rt()
    for seg, per_factor in weights.items():
        for f, w in per_factor.items():
            doc["segments"][seg]["factors"][f]["weight"] = w
    with open(SEG_YAML, "w", encoding="utf-8") as fh:
        y.dump(doc, fh)


# --- main --------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="verify segments.yaml matches the derivation; write nothing")
    ap.add_argument("--dry-run", action="store_true",
                    help="derive and report; write nothing")
    args = ap.parse_args()

    with open(AHP_YAML, encoding="utf-8") as fh:
        ahp = yaml.safe_load(fh)
    cr_max = ahp["scale"]["cr_threshold"]
    max_rev = ahp["scale"]["max_revisions_per_segment"]

    # R5: in derive mode the current weights are not read at all.
    seg_cfg = yaml.safe_load(open(SEG_YAML, encoding="utf-8"))
    lam_reg = seg_cfg.get("aggregation", {}).get("lambda_regional")
    current = {s: {f: v.get("weight") for f, v in d["factors"].items()}
               for s, d in seg_cfg["segments"].items()}

    print(f"{'segmento':14s} {'n':>2s} {'lmax':>6s} {'CI':>6s} {'RI':>5s} "
          f"{'RC':>6s} {'A/B/C':>9s} {'anc.':>5s} {'rev':>3s}")
    print("-" * 72)
    derived = {}
    for name, spec in ahp["segments"].items():
        res = derive_segment(name, spec, cr_max, max_rev)
        derived[name] = res
        c = res["class_counts"]
        print(f"{name:14s} {len(res['factors']):2d} {res['lambda_max']:6.3f} "
              f"{res['consistency_index']:6.3f} {res['random_index']:5.2f} "
              f"{res['consistency_ratio']:6.4f} "
              f"{c['A']:3d}/{c['B']:2d}/{c['C']:2d} "
              f"{res['anchored_fraction']:5.2f} {len(res['revisions']):3d}")
    print("-" * 72)
    worst = max(r["consistency_ratio"] for r in derived.values())
    gap = max(r["approx_eigenvector_max_gap"] for r in derived.values())
    print(f"pior RC = {worst:.4f} (limiar {cr_max});  "
          f"maior discordancia autovetor exato x aproximado = {gap:.4f}")
    ovr = sum(r["override_count"] for r in derived.values())
    print(f"overrides = {ovr};  julgamentos 'author judgement' = "
          f"{sum(r['author_judgement_count'] for r in derived.values())}")

    d_map = load_discrimination()
    if d_map is None:
        print(f"\n[parcial] {os.path.relpath(DISCRIM_CSV, ROOT)} ausente — "
              "w_lit derivado, estagio regional nao executado.\n"
              "          Rode tools/anchor_breakpoints.py primeiro.")
        return 0
    if lam_reg is None:
        print("\n[erro] aggregation.lambda_regional ausente em config/segments.yaml")
        return 1

    # --- regional stage ------------------------------------------------------
    rows, sweep, final = [], [], {}
    for name, res in derived.items():
        fs = res["factors"]
        missing = [f for f in fs if (name, f) not in d_map]
        if missing:
            print(f"\n[erro] sem d para {name}: {missing}")
            return 1
        d = [d_map[(name, f)] for f in fs]
        w_lit = res["priority_vector"]
        w_fin = round_to_unit(adapt(w_lit, d, lam_reg))
        final[name] = dict(zip(fs, w_fin))
        for f, wl, di, wf in zip(fs, w_lit, d, w_fin):
            cur = current.get(name, {}).get(f)
            rows.append({
                "segment": name, "factor": f, "w_lit": round(wl, 4),
                "d": round(di, 4), "w_final": wf, "w_atual": cur,
                "delta": None if cur is None else round(wf - cur, 4),
            })
        for lv in LAMBDA_GRID:
            for f, wv in zip(fs, round_to_unit(adapt(w_lit, d, lv))):
                sweep.append({"segment": name, "factor": f, "lambda": lv, "weight": wv})

    os.makedirs(CHAPTERS, exist_ok=True)
    wdf = pd.DataFrame(rows)
    sdf = pd.DataFrame(sweep)

    if args.check:
        drift = [r for r in rows
                 if r["w_atual"] is None or abs(r["w_final"] - r["w_atual"]) > 5e-5]
        if drift:
            print(f"\n[FORA DE SINCRONIA] {len(drift)} fator(es) divergem da derivacao:")
            print(pd.DataFrame(drift)[
                ["segment", "factor", "w_atual", "w_final", "delta"]].to_string(index=False))
            return 1
        print("\nconfig/segments.yaml em sincronia com a derivacao.")
        return 0

    print("\n" + wdf.to_string(index=False))
    if args.dry_run:
        print("\n[dry-run] nada escrito.")
        return 0

    wdf.to_csv(WEIGHTS_CSV, index=False)
    sdf.to_csv(LAMBDA_CSV, index=False)
    write_segments(final)

    y = YAML(typ="rt")
    y.width = 4096
    with open(AHP_YAML, encoding="utf-8") as fh:
        doc = y.load(fh)
    for name, res in derived.items():
        doc["segments"][name]["derived"] = {
            k: v for k, v in res.items() if k != "factors"}
    with open(AHP_YAML, "w", encoding="utf-8") as fh:
        y.dump(doc, fh)

    for p in (WEIGHTS_CSV, LAMBDA_CSV, SEG_YAML, AHP_YAML):
        print(f"escrito {os.path.relpath(p, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
