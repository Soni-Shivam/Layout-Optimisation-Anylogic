# Source this file: sets JAVA and the AnyLogic 8.9 classpaths built from the local install.
# Override AL_PLUGINS / JAVA_HOME if your paths differ.
TOOLS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${AL_PLUGINS:=$HOME/AnyLogic/anylogic/plugins}"
: "${JAVA_HOME:=$HOME/AnyLogic/anylogic/jre}"
JAVA="$JAVA_HOME/bin/java"; JAVAC="$JAVA_HOME/bin/javac"
# the jar lists name the 8.9.9 build; use the build actually installed (e.g. 8.9.10.202609241721)
AL_BUILD="$(ls "$AL_PLUGINS" | sed -n 's/^com\.anylogic\.engine_\([0-9.]*\)$/\1/p' | head -1)"
al_jar() {   # jar path for this build; a bundled library whose version changed (e.g. jackson-core-*.jar) is matched by name
  local p="$AL_PLUGINS/${1//8.9.9.202607020720/$AL_BUILD}"
  [ -e "$p" ] || p="$(ls "${p%-*}"-*.jar 2>/dev/null | head -1)"
  printf '%s' "$p"
}
CP_RUNTIME=""; while read -r j; do CP_RUNTIME="$CP_RUNTIME:$(al_jar "$j")"; done < "$TOOLS/verify/runtime_jars.txt"
CP_IDE=""; while read -r j; do CP_IDE="$CP_IDE:$(al_jar "$j")"; done < "$TOOLS/verify/ide_jars.txt"
CP_RUNTIME="${CP_RUNTIME#:}"; CP_IDE="${CP_IDE#:}"
export AL_PLUGINS JAVA_HOME JAVA JAVAC CP_RUNTIME CP_IDE
