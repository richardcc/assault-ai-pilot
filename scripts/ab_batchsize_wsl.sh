#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash scripts/ab_batchsize_wsl.sh
# Optional env vars:
#   BASE_CFG=/tmp/muzero_wsl_nano.yaml EPISODES=3 ITERATIONS=1 BATCH_A=8 BATCH_B=16

BASE_CFG="${BASE_CFG:-/tmp/muzero_wsl_nano.yaml}"
EPISODES="${EPISODES:-3}"
ITERATIONS="${ITERATIONS:-1}"
BATCH_A="${BATCH_A:-8}"
BATCH_B="${BATCH_B:-16}"
EXP_NAME="${EXP_NAME:-assault_muzero}"

if [[ ! -f "$BASE_CFG" ]]; then
  echo "Base config not found: $BASE_CFG" >&2
  exit 1
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
CFG_A="/tmp/muzero_wsl_bs${BATCH_A}_${STAMP}.yaml"
CFG_B="/tmp/muzero_wsl_bs${BATCH_B}_${STAMP}.yaml"

make_cfg () {
  local src="$1"
  local dst="$2"
  local bs="$3"
  cp "$src" "$dst"
  sed -i "s/^\([[:space:]]*episodes_per_iter:\).*/\1 ${EPISODES}/" "$dst"
  sed -i "s/^\([[:space:]]*iterations:\).*/\1 ${ITERATIONS}/" "$dst"
  sed -i "s/^\([[:space:]]*batch_size:\).*/\1 ${bs}/" "$dst"
}

make_cfg "$BASE_CFG" "$CFG_A" "$BATCH_A"
make_cfg "$BASE_CFG" "$CFG_B" "$BATCH_B"

echo "== A/B batch_size benchmark =="
echo "Base: $BASE_CFG"
echo "A: $CFG_A (batch_size=$BATCH_A)"
echo "B: $CFG_B (batch_size=$BATCH_B)"

run_one () {
  local cfg="$1"
  local tag="$2"
  OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  python -m agents.muzero.train.train_muzero \
    --config "$cfg" \
    --mlflow-experiment "$EXP_NAME" \
    --mlflow-run-name "wsl_ab_${tag}_${STAMP}"
}

echo ""
echo "-- Run A --"
run_one "$CFG_A" "bs${BATCH_A}"

echo ""
echo "-- Run B --"
run_one "$CFG_B" "bs${BATCH_B}"

echo ""
echo "Done. Compare timing_train_s / timing_iter_s and losses in MLflow."
