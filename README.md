# Amiga replayer analysis

How did Amiga musicians get so much out of four 8-bit sample channels? This repo
reads the source of the replayers in UADE and records their ideas, briefly.

The focus is on formats that did not become the demoscene standard. `ProTracker`
and its many relatives are left out.

## Where to start

1. [Paula in one page](docs/paula.md): the hardware every replayer works around.
2. [Paula techniques](docs/paula-techniques.md): common ways replayers drive it.
3. [Player cards](players/): one page per replayer.
4. [Player facts](data/players.yaml): provenance, lineage, authors.
5. [Specs](specs/): each player's model; deep dives are in its docstrings.
6. [Ideas](ideas/): technique families, compared across players.

Unknown terms are in [the glossary](docs/glossary.md).

## What a card tells you

- What steps through data per song, per voice and per instrument.
- What state the player keeps, and what an instrument can carry.
- Unique ideas, each with the source line that shows it.

The shape is fixed by [the card template](docs/card-template.md).

## Evidence

- Every claim in a player card cites a source line.
- Sources: UADE's replayers, original or disassembled, C ports, and other
  disassemblies. [Player facts](data/players.yaml) records each player's
  provenance.
- Binary-only players: our own IRA disassembly. See
  [`tools/disasm.py`](tools/disasm.py).
- Replay code inside a music file: our own IRA disassembly of one module.
- What you would hear is marked as "(inference)".

`tools/inventory.py` lists every UADE replayer and its source.
[Sources](ext/README.md) describes where the source code comes from.

## Contributing

- Run `source ./activate` in the repo root. It fetches the sources, builds the
  tools and installs the pre-commit checks. [`setup/`](setup/Makefile) does the
  work; a rerun rebuilds only what changed.
- Writing rules and checks: [`AGENTS.md`](AGENTS.md).
- Open work: [`TODO.md`](TODO.md).
