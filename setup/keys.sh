#!/bin/bash
# Usage: keys.sh NAME=CONTENT...
#
# Write build/keys/NAME for each argument and for the keys below, but only
# when its content changed. Make compares mtimes, so a key file is newer than
# its target only when an input really changed. A checkout's fresh mtimes, or
# a CI cache restore, rebuild nothing.

set -e
mkdir -p build/keys

put() {
  [ "$(cat "build/keys/$1" 2>/dev/null)" = "$2" ] ||
    printf '%s\n' "$2" >"build/keys/$1"
}

for arg; do
  put "${arg%%=*}" "${arg#*=}"
done
# The pins of ext/, and the submodule URLs.
put submodules "$(git ls-tree HEAD ext/ && sha1sum .gitmodules)"
put venv "$(sha1sum requirements.txt)"
# The pin that build/amiga-timing was built from.
put vacore "$(git rev-parse HEAD:ext/vamiga)"
put amiga-timing "$(git rev-parse HEAD:ext/vamiga &&
  sha1sum tools/timing/driver.cpp tools/timing/CMakeLists.txt)"
