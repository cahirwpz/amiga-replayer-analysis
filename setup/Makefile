# Sets up the environment: submodules, the venv, IRA, vlink, vasm and the
# timing driver. activate runs it from the repo root:
#
#   make -s -j"$(nproc)" -f setup/Makefile
#
# Targets depend on key files in build/keys/, not on sources; see
# setup/keys.sh. So a set-up checkout costs one call of keys.sh, and a CI
# cache restore builds nothing.

.DELETE_ON_ERROR:

BIN := .venv/bin
KEYS := build/keys

# IRA: the current Aminet release; vlink and vasm: pinned tags. The archive
# URL and the make arguments form the key; a new tag rebuilds the tool.
IRA := https://aminet.net/dev/asm/ira.lha
VLINK := http://phoenix.owl.de/tags/vlink0_18a.tar.gz
VASM := http://phoenix.owl.de/tags/vasm2_0f.tar.gz CPU=m68k SYNTAX=mot

$(shell setup/keys.sh "ira=$(IRA)" "vlink=$(VLINK)" "vasmm68k_mot=$(VASM)")

ARCHIVE_TOOLS := $(BIN)/ira $(BIN)/vlink $(BIN)/vasmm68k_mot

all: build/submodules.ok .venv/.installed $(ARCHIVE_TOOLS) $(BIN)/amiga-timing

# CI runs the hooks directly; a git hook there would be pointless.
ifneq ($(GITHUB_ACTIONS),true)
HOOK := $(shell git rev-parse --git-path hooks/pre-commit)
all: $(HOOK)
$(HOOK): | .venv/.installed
	$(BIN)/pre-commit install
endif

# Only a build needs the packages. Checked once; CI caches the mark.
build/packages.ok:
	@setup/check-packages.sh
	@touch $@

# NostalgicPlayer: 162 MB in full; we read only its replayer ports and its
# format notes. vAmiga: we build only its emulator core, for tools/timing.py.
build/submodules.ok: $(KEYS)/submodules
	@setup/sparse-submodule.sh ext/nostalgicplayer \
	  Source/Agents/Players Format_Descriptions
	@setup/sparse-submodule.sh ext/vamiga Core
	@git submodule update --init
	@touch $@

.venv/.installed: $(KEYS)/venv | build/packages.ok
	@python3 -m venv .venv
	@$(BIN)/python3 -m pip -q install -U -r requirements.txt
	@touch $@

# The key holds the URL, then the make arguments. The archive holds one
# directory with a Makefile; bsdtar reads both LHA and tar.gz.
$(ARCHIVE_TOOLS): $(BIN)/%: $(KEYS)/% | .venv/.installed build/packages.ok
	@echo "setup: building $@"
	@rm -rf build/src/$*
	@mkdir -p build/src/$*
	@set -- $$(cat $<); url=$$1; shift; \
	{ curl -fsSL "$$url" | bsdtar -xf - -C build/src/$* && \
	  src=$$(find build/src/$* -mindepth 1 -maxdepth 1 -type d) && \
	  mkdir -p "$$src/objects" && \
	  $(MAKE) -C "$$src" "$$@" && \
	  cp "$$src/$*" $@; } >build/$*.log 2>&1 || \
	{ tail -20 build/$*.log; exit 1; }

# The driver of tools/timing.py, linked with vAmiga's core. The first build
# takes about three minutes; ninja rebuilds only what changed. The install
# may keep an unchanged binary's mtime, hence the touch.
$(BIN)/amiga-timing: $(KEYS)/amiga-timing \
  | build/submodules.ok .venv/.installed build/packages.ok
	@echo "setup: building $@"
	@{ cmake -S tools/timing -B build/amiga-timing -G Ninja \
	    -DCMAKE_BUILD_TYPE=Release -DVAMIGA_CORE="$(CURDIR)/ext/vamiga/Core" && \
	  cmake --build build/amiga-timing && \
	  cmake --install build/amiga-timing --prefix .venv; \
	} >build/amiga-timing.log 2>&1 || \
	{ tail -20 build/amiga-timing.log; exit 1; }
	@touch $@
