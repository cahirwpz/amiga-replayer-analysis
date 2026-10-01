# Sets up the environment: submodules, the venv, IRA, vlink, vasm, the timing
# driver and the font of tools/print.py. activate runs it from the repo root:
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

# JetBrains Mono (OFL): a pinned release; tools/print.py embeds it in PDFs.
FONTS := https://github.com/JetBrains/JetBrainsMono/releases/download/v2.304/JetBrainsMono-2.304.zip
FONT_DIR := .venv/share/fonts
FONT_FILES := $(foreach s,Regular Bold Italic BoldItalic,fonts/ttf/JetBrainsMono-$(s).ttf)

$(shell setup/keys.sh "ira=$(IRA)" "vlink=$(VLINK)" "vasmm68k_mot=$(VASM)" \
  "fonts=$(FONTS) $(FONT_FILES)")

ARCHIVE_TOOLS := $(BIN)/ira $(BIN)/vlink $(BIN)/vasmm68k_mot

all: build/submodules.ok .venv/.installed $(ARCHIVE_TOOLS) $(BIN)/amiga-timing \
  $(FONT_DIR)/.installed

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

# Only the regular and bold faces, and the licence.
$(FONT_DIR)/.installed: $(KEYS)/fonts | .venv/.installed build/packages.ok
	@echo "setup: fetching fonts"
	@rm -rf $(FONT_DIR)
	@mkdir -p $(FONT_DIR)
	@curl -fsSL "$(FONTS)" | bsdtar -xf - -C $(FONT_DIR) -s '|.*/||' \
	  $(FONT_FILES) OFL.txt
	@touch $@

# The build directory is valid for one pin only; a new pin starts it empty.
build/amiga-timing/.vacore: $(KEYS)/vacore
	@rm -rf build/amiga-timing
	@mkdir -p build/amiga-timing
	@touch $@

# The driver of tools/timing.py, linked with vAmiga's core. The first build
# takes about eight minutes in CI. A checkout gives the core's sources fresh
# mtimes, so they get the pin's commit time instead; the core's objects then
# stay up to date and only the driver is rebuilt. This is safe only because
# the rule above empties a directory built from another pin. The install
# may keep an unchanged binary's mtime, hence the touch.
$(BIN)/amiga-timing: $(KEYS)/amiga-timing build/amiga-timing/.vacore \
  | build/submodules.ok .venv/.installed build/packages.ok
	@echo "setup: building $@"
	@t=$$(git -C ext/vamiga log -1 --format=%ct) && \
	git -C ext/vamiga ls-files -z Core | \
	  (cd ext/vamiga && xargs -0 touch -d @$$t)
	@{ cmake -S tools/timing -B build/amiga-timing -G Ninja \
	    -DCMAKE_BUILD_TYPE=Release -DVAMIGA_CORE="$(CURDIR)/ext/vamiga/Core" && \
	  cmake --build build/amiga-timing && \
	  cmake --install build/amiga-timing --prefix .venv; \
	} >build/amiga-timing.log 2>&1 || \
	{ tail -20 build/amiga-timing.log; exit 1; }
	@touch $@
