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

`tools/cogload.py` enforces these at commit time. Tune them in `DEFAULT` and
`PROFILES`.

| Rule                            | Default | `players/` | `ideas/` | `details/` |
| ------------------------------- | ------- | ---------- | -------- | ---------- |
| Words per sentence              | 16      | 16         | 16       | 20         |
| Sentences per paragraph or item | 3       | 3          | 3        | 5          |
| Items per list                  | 7       | 7          | 7        | 10         |
| List depth                      | 2       | 2          | 2        | 3          |
| Words per file                  | 450     | 150        | 300      | 1000       |
| Words per table cell            | 15      | 15         | 15       | 25         |
| FK grade                        | 12      | 12         | 12       | 14         |

The glossary has a higher file limit. Code blocks and inline code are exempt.

## Evidence

- Cite UADE source as `uade/path:line`.
- Say when a player has no source, only a binary.
- Mark guesses as guesses.

## Repo hygiene

- Never edit `uade/`. Update the submodule pin only on request.
- Run `source ./activate` once per shell. Python tools go in `requirements.txt`.
- Run `pre-commit run --all-files` before each commit.
