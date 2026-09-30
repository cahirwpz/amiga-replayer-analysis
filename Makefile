# Printed cards. Run after `source ./activate`, which fetches the font:
#
#   make build/players/MaxTrax.pdf

.DELETE_ON_ERROR:

build/players/%.pdf: players/%.md tools/print.py
	./tools/print.py --pdf $@ $<
