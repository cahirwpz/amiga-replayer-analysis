# Working rules

This repo analyses Amiga replayers in UADE. It looks for distinct ideas, not for
every detail. See `README.md` for layout and status.

## Scope

- Focus on formats that did not prevail on the Amiga demoscene.
- Skip `ProTracker`-like players; at most tag them in the inventory.
- Themes: cheap but expressive synthesis, unusual tricks, soft voice mixing.
- Describe control: streams, their state, and what instruments carry. Paula
  features matter less.
- Current work: [the pilot](docs/pilot.md). Track progress only in
  [`TODO.md`](TODO.md), never in `README.md`.

## Depth

- Write at executive-summary level by default.
- Go deeper only when the user asks. Put deep dives in `details/`.
- One idea per page. One replayer per card.
- Prefer a table over prose when comparing things.

## Writing

Readers are C1 non-native speakers with limited attention.

- Use plain words. Define each acronym in `docs/glossary.md`.
- One claim per sentence. No filler, no hedging.
- Put technical detail in tables or code, which skip prose limits.
- Answer chat questions in the same style.

## Limits

`tools/cogload.py` enforces size limits at commit time. The numbers live only
there, in `DEFAULT` and `PROFILES`. Run it before committing.

## Evidence

- In player cards, cite as `file:line` relative to the card's `source`.
  Elsewhere, cite as `ext/uade/path:line`.
- Say when a player has no source, only a binary. `data/inventory.csv` knows.
- Mark guesses as guesses. Mark what you hear as "(inference)".
- Keyword scans only pick candidates. A claim needs code that was read.
- Use only players whose `replay` is `uade` or `port` in the inventory.
- Evidence levels: `code` (original or disassembled replayer), `port` (a port of
  the original), `docs`. No guessed replay logic.

## Repo hygiene

- Never edit `ext/`. Update submodule pins only on request.
- After a pin update, run `tools/inventory.py --write`. Then run
  `tools/links.py --fix-rows .` to repoint links to inventory rows.
- Link player names to their inventory row, with the name as link title.
- Run `source ./activate` once per shell. Python tools go in `requirements.txt`.
- Before each commit, stage and run `pre-commit run --all-files`. Formatters
  change files, so stage again and rerun until it passes.
- Checks: `cogload` for size, `links` for links and citations, `cards` for card
  shape. Also `inventory` for fresh data and `tool-tests` for the checkers.
- Never commit without the user's approval for that commit. Approval never
  carries over.

## Shell pitfalls

- Sources are Latin-1. `grep` silently finds nothing in them. Use
  `tools/srcgrep.py`.
- `ls` is aliased to a long listing. Use Python `glob` in scripts.
- `sed` patterns fail silently. Edit with Python and assert each match.
