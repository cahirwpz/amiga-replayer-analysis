#!/bin/bash
# Usage: sparse-submodule.sh DIR FOLDER...
#
# Clone submodule DIR shallow, partial and sparse: only the commit we pin,
# only the given folders, and only the files in them. Git keeps sparse
# settings per clone, so this runs before `git submodule update`, which then
# finds the submodule at its pin. Does nothing if DIR is already cloned.

set -e
dir=$1
shift
[ -e "$dir/.git" ] && exit 0
url=$(git config -f .gitmodules "submodule.$dir.url")
sha=$(git rev-parse ":$dir")
git init -q "$dir"
git -C "$dir" remote add origin "$url"
git -C "$dir" sparse-checkout set "$@"
git -C "$dir" fetch -q --depth 1 --filter=blob:none origin "$sha"
git -C "$dir" checkout -q "$sha"
git submodule init -- "$dir"
git submodule absorbgitdirs -- "$dir"
