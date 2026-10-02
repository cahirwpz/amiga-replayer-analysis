# Printed cards. Run after `source ./activate`, which fetches the font:
#
#   make build/cards.pdf
#   make build/players/MaxTrax.pdf

.DELETE_ON_ERROR:

# The book: Paula pages, technique families, every card, then the glossary.
FRONT := docs/paula.md docs/paula-techniques.md $(sort $(wildcard ideas/*.md))
BACK := docs/glossary.md
CARDS := $(sort $(wildcard players/*.md))

build/cards.pdf: $(FRONT) $(CARDS) $(BACK) tools/print.py
	./tools/print.py --pdf $@ $(FRONT) players/ $(BACK)

build/players/%.pdf: players/%.md tools/print.py
	./tools/print.py --pdf $@ $<
