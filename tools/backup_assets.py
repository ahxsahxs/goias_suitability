"""Server-side backup of the goias EE asset folder before a re-export.

Copies every asset under projects/<project>/assets/goias to a sibling
`goias_backup_<YYYYMMDD>` folder via ee.data.copyAsset (fast, server-side, no
download). Idempotent: re-running overwrites the backup copies.

Run:  EE_PROJECT=probformer ../.venv/bin/python tools/backup_assets.py [suffix]
"""
from __future__ import annotations

import sys
from datetime import date

sys.path.insert(0, "src")

import ee  # noqa: E402
import utils  # noqa: E402


def main():
    project = utils.init()
    root = utils.asset_root(project)
    suffix = sys.argv[1] if len(sys.argv) > 1 else date.today().strftime("%Y%m%d")
    backup = f"{root}_backup_{suffix}"

    try:
        ee.data.createAsset({"type": "FOLDER"}, backup)
        print(f"created backup folder {backup}")
    except ee.EEException:
        print(f"backup folder exists: {backup}")

    assets = ee.data.listAssets({"parent": root})["assets"]
    print(f"backing up {len(assets)} assets ...")
    ok = 0
    for a in assets:
        src = a["name"]
        name = src.split("/")[-1]
        dst = f"{backup}/{name}"
        try:
            ee.data.copyAsset(src, dst, allowOverwrite=True)
            ok += 1
            print(f"  copied {a['type'][:5]:5s} {name}")
        except ee.EEException as e:
            print(f"  FAILED {name}: {e}")

    got = len(ee.data.listAssets({"parent": backup})["assets"])
    print(f"\ndone: {ok}/{len(assets)} copied; backup folder now holds {got} assets")
    print(f"backup root: {backup}")


if __name__ == "__main__":
    main()
