# Amiga replayer analysis

How did Amiga musicians get so much out of four 8-bit sample channels? This repo
reads the source of the replayers in UADE and records their ideas, briefly.

The focus is on formats that did not become the demoscene standard. `ProTracker`
and its many relatives are left out.

## Where to start

1. [Paula in one page](docs/paula.md): the hardware every replayer works around.
2. [Players](docs/players.md): every card, with provenance and lineage.
3. [Details](details/): deep dives, only where a card needs one.

Unknown terms are in [the glossary](docs/glossary.md).

## What a card tells you

- What steps through data per song, per voice and per instrument.
- What state the player keeps, and what an instrument can carry.
- Key ideas, each with the source line that shows it.

The shape is fixed by [the card template](docs/card-template.md).

## Evidence

- Every claim in a player card cites a source line.
- Sources: UADE's replayers, original or disassembled, and C ports.
  [Players](docs/players.md) lists each card's provenance and lineage.
- Binary-only players: our own IRA disassembly. See
  [`tools/disasm.py`](tools/disasm.py).
- Players whose replay code hides inside music files are left out.
- What you would hear is marked as "(inference)".

[The inventory](data/inventory.csv) lists every UADE replayer and its source.
[Sources](ext/README.md) describes where the source code comes from.

## Contributing

- Run `source ./activate` in the repo root. It fetches the sources and installs
  the pre-commit checks.
- Writing rules and checks: [`AGENTS.md`](AGENTS.md).
- Open work: [`TODO.md`](TODO.md).
