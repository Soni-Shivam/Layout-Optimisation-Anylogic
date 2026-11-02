#!/bin/bash
# Runs the reference simulator (plain Java, same flowchart as the AnyLogic model) on every candidate
# layout x every day file and summarises results/refsim_runs.csv. These are the expected numbers for the
# AnyLogic CompareLayouts experiment (small differences come from simultaneous-event order).
# Usage: tools/refsim.sh [N_DAYS]     (run tools/check.sh first)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/tools/anylogic_env.sh"
cd "$ROOT"
D=model/WarehouseSim/data
N="${1:-5}"
mkdir -p results
rm -f results/refsim_runs.csv
for L in $(cat $D/layouts/index.txt); do
  for s in $(seq 1 "$N"); do
    "$JAVA" -cp build/classes wh.RefSim "$D/layouts/$L" "$D/config/run_config.json" "$D/scenarios/day_$s.csv" "$D/skus.csv" "$s" results > /dev/null
  done
  echo "  $L done"
done
(cd python && python3 -m whsim.analyze ../results/refsim_runs.csv --baseline I_v_c0_central_random)
