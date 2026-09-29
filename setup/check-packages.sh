#!/bin/bash
# Check for the commands the setup needs: Python, git with LFS, and what
# builds IRA, vasm, vlink and the timing driver. Commands, not packages: a
# CI image may install a tool outside the package manager. Reports all
# missing at once, with the apt-get line that installs them.

if ! [ -e /etc/debian_version ]; then
  echo "setup: only Debian and Ubuntu are supported."
  exit 1
fi
missing=()
# COMMAND:PACKAGE
for need in git:git git-lfs:git-lfs python3:python3 venv:python3-venv \
  curl:curl bsdtar:libarchive-tools make:make gcc:gcc g++:g++ \
  cmake:cmake ninja:ninja-build; do
  if [ "${need%%:*}" = venv ]; then
    python3 -c "import ensurepip, venv" 2>/dev/null && continue
  else
    command -v "${need%%:*}" >/dev/null && continue
  fi
  missing+=("${need#*:}")
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "setup: missing packages: ${missing[*]}"
  echo "  Run: sudo apt-get install ${missing[*]}"
  exit 1
fi
