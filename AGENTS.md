# Working rules

This repo analyses Amiga replayers for distinct ideas, not for every detail.

## Sessions

- Start by reading [`TODO.md`](TODO.md). Progress lives there, never in
  `README.md`.
- Before a session ends or context is cleared, update `TODO.md`. Nothing may
  live only in the conversation.

`TODO.md` keeps:

- open tasks, in order, and questions for the user
- reading notes for unfinished work, with `file:line`
- decisions still pending

`TODO.md` never keeps:

- finished results: they go to `players/`, `ideas/` or `details/`
- rules and conventions: they go here
- reasons behind finished work: they go to `docs/`
- done items: delete them, git keeps the history
- unmarked guesses, secrets, or chat transcripts

## Scope

- Focus on formats that did not prevail on the Amiga demoscene.
- Skip `ProTracker`-like players; at most tag them in the inventory.
- Themes: cheap but expressive synthesis, unusual tricks, soft voice mixing.
- Describe control: streams, their state, and what instruments carry. Paula
  features matter less.
- Current work: the pilot, in `TODO.md`.

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

## Evidence

- In player cards, cite as `file:line` relative to the card's `source`.
  Elsewhere, cite as `ext/uade/path:line`.
- Mark guesses as guesses. Mark what you hear as "(inference)".
- Keyword scans only pick candidates. A claim needs code that was read.
- Use only players whose `replay` is `uade` or `port` in the inventory.
- Evidence levels are defined in [the glossary](docs/glossary.md).

## Repo hygiene

- Never edit `ext/`. Update submodule pins only on request.
- After a pin update, run `tools/inventory.py --write`. Then run
  `tools/links.py --fix-rows *.md docs players` to repoint links to inventory
  rows.
- Link player names to their inventory row, with the name as link title.
- Run `source ./activate` once per shell. Python tools go in `requirements.txt`.
- Before each commit, stage and run `pre-commit run --all-files`. Formatters
  change files, so stage again and rerun until it passes.
- Checks: `cogload` (size limits, set in its `PROFILES`), `links`, `cards`,
  `inventory`, `tool-tests`.
- Never commit without the user's approval for that commit. Approval never
  carries over.

## Shell pitfalls

- Sources are Latin-1. `grep` silently finds nothing in them. Use
  `tools/srcgrep.py`.
- `ls` is aliased to a long listing. Use Python `glob` in scripts.
- `sed` patterns fail silently. Edit with Python and assert each match.
