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

- Cite UADE source as `uade/path:line`.
- Say when a player has no source, only a binary. `data/inventory.csv` knows.
- Mark guesses as guesses.

## Repo hygiene

- Never edit `uade/`. Update the submodule pin only on request.
- After a pin update, regenerate `data/inventory.csv` with `tools/inventory.py`.
- Run `source ./activate` once per shell. Python tools go in `requirements.txt`.
- Run `pre-commit run --all-files` before each commit.
- Never commit without the user's approval for that commit. Approval never
  carries over.
