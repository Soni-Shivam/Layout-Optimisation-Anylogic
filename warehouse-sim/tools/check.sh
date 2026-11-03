#!/bin/bash
# Builds and checks everything, then writes the AnyLogic model:
#   1. Python: tests (layout compiler, real-building designs, input models)
#   2. Java core: compile + CoreTest (Java vs Python tour cross-check, batching, reference-sim full days)
#   3. AnyLogic model: generate the .alp, compile every Java snippet against the AnyLogic 8.9 engine jars,
#      load it with AnyLogic's own serializer + version converters and ship the canonical file.
# Inputs are NOT regenerated here (they come from the data): run  python3 -m whsim.cli scenarios / config
# and python3 -m whsim.optimize (writes the designs + layouts) before, see README.
# Usage: tools/check.sh            (AL_PLUGINS / JAVA_HOME: see tools/anylogic_env.sh)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/tools/anylogic_env.sh"
cd "$ROOT"
MODEL=model/WarehouseSim

echo "== 1. Python: fixtures + tests"
(cd python && python3 -m whsim.cli layouts > /dev/null && python3 -m whsim.fixtures && python3 -m pytest -q)

echo "== 2. Java core: compile + tests"
rm -rf build/classes && mkdir -p build/classes
"$JAVAC" -Xlint:all -Werror -d build/classes java/src/wh/*.java java/test/CoreTest.java
"$JAVA" -cp build/classes CoreTest

echo "== 3a. AnyLogic model: generate"
python3 anylogic/build_model.py

echo "== 3b. compile all model Java against the AnyLogic engine"
rm -rf build/shadow.out && mkdir -p build/shadow.out
"$JAVAC" -proc:none -nowarn --release 17 -cp "$CP_RUNTIME" -d build/shadow.out build/shadow/warehousesim/*.java
test -f build/shadow.out/warehousesim/Main.class && echo "   compiled OK"

echo "== 3c. AnyLogic serializer: load + convert + write canonical .alp"
mkdir -p build/loader
"$JAVAC" -proc:none -nowarn -cp "$CP_IDE:$CP_RUNTIME" -d build/loader tools/verify/java/LoadAlp.java
cp tools/verify/java/stubs.txt build/loader/
GEN="$ROOT/build/WarehouseSim.generated.alp"
RT="$ROOT/build/WarehouseSim.rt.alp"
( cd build/loader && "$JAVA" -Dconvert=1 -Dname=WarehouseSim -cp ".:$CP_IDE:$CP_RUNTIME" LoadAlp "$GEN" "$RT" 2>&1 \
    | grep -E "LOADED|converted|LOG|Exception|Re-serialized" )
echo "   tags the serializer dropped (expected: only the default 'connections' AgentLinks):"
python3 tools/verify/dropped_tags.py "$GEN" "$RT" | grep -v -E "ApplyOnStartup|SceneSkybox|AgentLink|ConnectionsId" || true
python3 tools/verify/compare_roundtrip.py "$GEN" "$RT" | grep -E "^DIFF|PROBLEMS|MISSING" | grep -v "__experiments__" || true
sed "s/AnyLogicVersion=\"0.0.0.0\"/AnyLogicVersion=\"$AL_BUILD\"/" "$RT" > "$MODEL/WarehouseSim.alp"
echo "== done: $MODEL/WarehouseSim.alp"
