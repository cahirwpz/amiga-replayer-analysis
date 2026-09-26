# Working rules

This repo analyses Amiga replayers in UADE. It looks for distinct ideas, not for
every detail. See `README.md` for layout and status.

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
- Mark guesses as guesses.
- Evidence levels: `code` (original or disassembled replayer), `port` (a port of
  the original), `docs`. No guessed replay logic.

## Repo hygiene

- Never edit `ext/`. Update submodule pins only on request.
- After a pin update, regenerate `data/inventory.csv` with `tools/inventory.py`.
- Run `source ./activate` once per shell. Python tools go in `requirements.txt`.
- Run `pre-commit run --all-files` before each commit. Markdown checks:
  `cogload` (size), `links` (links and citations), `cards` (card shape),
  `tool-tests` (self-tests of the checkers).
- Never commit without the user's approval for that commit. Approval never
  carries over.
