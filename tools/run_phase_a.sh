#!/usr/bin/env bash
# Execute Phase-A Parts 1-8 notebooks in order (in place), using the venv kernel.
# Requires a valid Earth Engine login:  ../.venv/bin/earthengine authenticate
set -euo pipefail

cd "$(dirname "$0")/.."
PY="../.venv/bin"
KERNEL="goias"
TIMEOUT="${NB_TIMEOUT:-3600}"

# Feature notebooks submit async exports; the stack (08) LOADS those cached
# assets, so it must wait until the feature exports have actually completed.
FEATURE_NBS=(
  01_setup_aoi
  02_features_climate
  03_features_terrain
  04_features_soil
  05_features_water
  06_features_phenology
  07_features_access
  07b_landcover_mask
)

run_nb() {
  echo "=== executing notebooks/${1}.ipynb ==="
  "$PY/jupyter" nbconvert --to notebook --execute --inplace \
    --ExecutePreprocessor.kernel_name="$KERNEL" \
    --ExecutePreprocessor.timeout="$TIMEOUT" \
    "notebooks/${1}.ipynb"
}

for nb in "${FEATURE_NBS[@]}"; do run_nb "$nb"; done

echo "=== waiting for feature exports to complete before assembling the stack ==="
"$PY/python" tools/wait_for_assets.py \
  feat_climate feat_terrain feat_soil feat_water feat_phenology feat_access \
  --timeout "${ASSET_WAIT:-7200}"

run_nb 08_feature_stack
echo "All Phase-A notebooks executed. Export tasks submitted to Earth Engine."
echo "Check status:  $PY/earthengine task list"
