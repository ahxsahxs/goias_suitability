"""Block until the named EE assets exist (or timeout). Used to gate the
feature-stack step on the feature exports completing.

Usage:
    python tools/wait_for_assets.py feat_climate feat_terrain ... [--timeout 7200]
Exit code 0 if all assets exist, 1 on timeout.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import ee  # noqa: E402
import utils  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="+", help="asset short names under the goias folder")
    ap.add_argument("--timeout", type=int, default=7200, help="seconds (default 2h)")
    ap.add_argument("--interval", type=int, default=120, help="poll seconds")
    args = ap.parse_args()

    project = utils.init()

    def exists(name):
        try:
            ee.data.getAsset(utils.asset_id(project, name))
            return True
        except ee.EEException:
            return False

    deadline = time.time() + args.timeout
    while True:
        missing = [n for n in args.names if not exists(n)]
        if not missing:
            print("all assets present:", ", ".join(args.names))
            return 0
        if time.time() > deadline:
            print("TIMEOUT; still missing:", ", ".join(missing), file=sys.stderr)
            return 1
        print("waiting on:", ", ".join(missing), flush=True)
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
