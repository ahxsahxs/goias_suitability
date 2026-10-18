"""One entry point for the whole pipeline. Each subcommand runs one or more scripts
in tools/ (unchanged) with the right environment.

    uv run python pipeline.py <command> --help

Order for a NEW territory (edit config/territory.yaml first; see README.md):

    mesh                                    IBGE zips -> municipal mesh (local)
    build --until realized                  Parts 1-8 + MapBiomas realized use
    build --until suit                      provisional suitability (current weights)
    split                                   50/50 spatial holdout (Gate 0)
    horizon                                 cache the CMIP6 horizon climate
    calibrate breakpoints                   percentiles -> PROPOSED breakpoint edits
        (apply the printed edits to config/segments.yaml by hand)
    calibrate weights                       sigma(mu) -> AHP weights into segments.yaml
    build --until suit --force suit         suitability with the new weights
    build --until zones                     writes zoning_kselect.csv -> choose K
    build --k K --force zones               zoning with K pinned, then CMIP6 + Part 12/13
    verify                                  footprint/CRS/scale of every asset
    validate                                Part 14 validation metrics
    diagnostics                             lambda sweep, zoning-axis probe
    report                                  CSVs -> thesis tables + figures
    dashboard                               docs/dashboard/public/data

Every EE command needs EE_PROJECT set (your Earth Engine cloud project).
`check` runs the offline regression suite (no Earth Engine).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOOLS = ROOT / "tools"

# `--force` shorthands -> asset names.
FORCE_GROUPS = {
    "suit": "suit_present,suit_present_comp,suit_present_sens",
    "zones": "zones_present",
}


def run(script: str, *args: str, **env: str) -> None:
    """Run tools/<script> with extra env vars; abort the pipeline on failure."""
    cmd = [sys.executable, str(TOOLS / script), *args]
    shown = " ".join(f"{k}={v}" for k, v in env.items())
    print(f"\n>>> {shown + ' ' if shown else ''}{' '.join(cmd[1:])}", flush=True)
    rc = subprocess.run(cmd, cwd=ROOT, env={**os.environ, **env}).returncode
    if rc:
        raise SystemExit(f"[pipeline] {script} exited with {rc}")


def cmd_mesh(a):
    run("build_malha_municipal.py")


def cmd_build(a):
    env = {"REBUILD_UNTIL": a.until}
    if a.force:
        env["REBUILD_FORCE"] = ",".join(FORCE_GROUPS.get(f, f) for f in a.force.split(","))
        print("[pipeline] --force deletes those assets before re-exporting; "
              "run `pipeline.py backup` first if you may need them.")
    if a.k:
        env["ZONE_K"] = str(a.k)
    run("run_rebuild_full.py", **env)


def cmd_split(a):
    run("make_calib_val_split.py", *(["--check-only"] if a.check else []))


def cmd_horizon(a):
    run("export_horizon_climate.py", "--wait")


def cmd_calibrate(a):
    if a.step == "breakpoints":
        run("anchor_breakpoints.py", "percentiles", SPLIT_HALF="all")
        run("diff_breakpoints.py", "--half", "calib")
        print("\n[pipeline] Apply the edits printed above to config/segments.yaml "
              "(re-stamp anchor.anchored_at), then run `pipeline.py calibrate weights`.")
    else:
        run("anchor_breakpoints.py", "discrimination", SPLIT_HALF="all")
        run("diff_sigma_domains.py")
        run("derive_weights.py", "--half", "calib")
        run("derive_weights.py", "--check")


def cmd_validate(a):
    run("run_validation.py")


def cmd_diagnostics(a):
    run("lambda_diagnostic.py")
    run("probe_zoning_candidates.py")


def cmd_report(a):
    run("extract_present.py")
    run("extract_cmip6.py")
    run("gen_diag_csvs.py", "all")
    run("make_calib_val_split.py", "--check-only")
    run("gen_thesis_tables.py")
    run("make_figures.py", "all")


def cmd_dashboard(a):
    run("build_dashboard_assets.py", *(["--only", a.only] if a.only else []))


def cmd_verify(a):
    run("verify_assets.py")


def cmd_backup(a):
    run("backup_assets.py", *([a.suffix] if a.suffix else []))


def cmd_check(a):
    """Offline regression suite: everything a refactor must leave unchanged."""
    import py_compile

    for f in sorted([*ROOT.glob("src/*.py"), *TOOLS.glob("*.py"), ROOT / "pipeline.py"]):
        py_compile.compile(str(f), doraise=True)
    print(f"compiled {len(list(ROOT.glob('src/*.py'))) + len(list(TOOLS.glob('*.py'))) + 1} files")
    run("derive_weights.py", "--check")
    run("gen_thesis_tables.py")
    rc = subprocess.run(["git", "diff", "--exit-code", "--stat", "thesis/Chapters/Tables"],
                        cwd=ROOT).returncode
    if rc:
        raise SystemExit("[check] generated thesis tables differ from the committed ones")
    print("\n[check] OK: weights in sync, thesis tables reproduce the committed ones")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("mesh", help="build the municipal mesh from the IBGE zips")
    b = sub.add_parser("build", help="build/resume EE assets (Parts 1-13)")
    b.add_argument("--until", default="all",
                   choices=["features", "stack", "realized", "suit", "zones", "cmip6", "all"])
    b.add_argument("--force", help="comma list of assets to rebuild "
                                   "(shorthands: suit, zones; or 'all')")
    b.add_argument("--k", type=int, help="pin the number of zones")
    s = sub.add_parser("split", help="build the calib/val holdout (or --check it)")
    s.add_argument("--check", action="store_true", help="audit only, export nothing")
    sub.add_parser("horizon", help="cache the CMIP6 horizon climate asset")
    c = sub.add_parser("calibrate", help="re-anchor breakpoints / derive AHP weights")
    c.add_argument("step", choices=["breakpoints", "weights"])
    sub.add_parser("validate", help="Part 14 validation (writes validation_*.csv)")
    sub.add_parser("diagnostics", help="lambda sweep + zoning-axis probe")
    sub.add_parser("report", help="summary CSVs, thesis tables and figures")
    d = sub.add_parser("dashboard", help="build docs/dashboard/public/data")
    d.add_argument("--only", help="a single stage, or 'offline'")
    sub.add_parser("verify", help="metadata-only footprint check of every asset")
    k = sub.add_parser("backup", help="server-side copy of the asset folder")
    k.add_argument("suffix", nargs="?")
    sub.add_parser("check", help="offline regression suite (no EE)")

    a = ap.parse_args()
    globals()[f"cmd_{a.cmd}"](a)


if __name__ == "__main__":
    main()
