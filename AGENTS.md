# Working rules

This repo analyses Amiga replayers for distinct ideas, not for every detail.

## Sessions

- Start by reading [`TODO.md`](TODO.md). Progress lives there, never in
  `README.md`.
- Before a session ends or context is cleared, update `TODO.md`. Nothing may
  live only in the conversation.

`TODO.md` keeps:

- open tasks, in order, and questions for the user
- reading notes for unfinished work, with `file:Label`
- decisions still pending

`TODO.md` never keeps:

- finished results: they go to `players/`, `specs/`, `ideas/` or `details/`
- rules and conventions: they go here
- reasons behind finished work: they go to `docs/`
- done items: delete them, git keeps the history
- unmarked guesses, secrets, or chat transcripts

## Scope

- Focus on formats that did not prevail on the Amiga demoscene.
- Skip `ProTracker`-like players; at most note them in `data/players.yaml`.
- Themes: cheap but expressive synthesis, unusual tricks, soft voice mixing.
- Describe control: streams, their state, and what instruments carry. Paula
  features matter less.

## Depth

- Write at executive-summary level by default.
- Go deeper only when the user asks. Put deep dives in `details/`.
- One idea per page. One lineage per card; see `family` in
  [`data/players.yaml`](data/players.yaml).
- A card covers a lineage's latest version. If it is binary-only, disassemble
  it. A version with a distinct idea gets its own card.
- Prefer a table over prose when comparing things.
- A player's model is its spec, `specs/<player>.py`. Its card is
  [prose](docs/card-template.md).

## Writing

Readers are C1 non-native speakers with limited attention. Chat answers follow
the same rules.

- Use plain words. Define each acronym in `data/glossary.yaml`.
- Use glossary terms, only in their defined meaning. Define new concepts there.
- Name a format's own term once, in code. Add it and replaced synonyms to the
  avoided terms.
- One claim per sentence, one fact per table cell. No filler, no hedging.
- Put technical detail in tables or specs; they skip prose limits.
- Name a jump's target, e.g. "jumps to its release part".
- Say each thing once. Elsewhere, link to it or generate it from `data/`. Tool
  usage lives in the tool's docstring.

Before showing a card, read it as that reader. Check each noun against the
glossary and each label against its code.

## Evidence

- Cite code by label, never by line: `file:<Label>`. On a card, paths start at
  the player's source; elsewhere, at the repo root.
- A bare `:<Label>` uses the previous citation's file. On a card, it first names
  a spec function or class.
- Mark guesses as guesses. Mark what you hear as "(inference)".
- Keyword scans only pick candidates. A claim needs 68k replay code that was
  read.
- Record provenance in `data/players.yaml`: `original`, `disassembly` or `ira`.
  A port only shows where to look.
- Our labels: `data/annot/<player>.yaml:<Label>` or
  `data/disasm/<player>.cnf:<Label>`. Add missing ones.
- Cards cite, and specs name, readable CamelCase labels. Rename raw labels
  first. Spec classes go in `types:`.

## Listings

- Binaries: [`tools/disasm.py`](tools/disasm.py). Sources:
  [`tools/annot.py`](tools/annot.py). Commit inputs, never listings.
- Annotate only what a spec needs.

## Repo hygiene

- Never edit submodules in `ext/` or update their pins unasked.
- For a pin update, diff the output of `tools/inventory.py` before and after.
- Link each player name to its card, if any.
- Run `source ./activate` once per shell.
- Before each commit, stage and run `pre-commit run --all-files`. Stage again
  and rerun until it passes.
- Never commit without the user's approval for that commit. Approval never
  carries over.

## Tools

- Markdown is presentation; data lives in `data/` as YAML or CSV. Never parse
  Markdown with regexes; use [`tools/mdtools.py`](tools/mdtools.py).
- Edit the glossary in `data/glossary.yaml`, then run
  `tools/glossary.py --write`.
- Python packages go in `requirements.txt`.

## Shell pitfalls

- Sources are Latin-1, so `grep` finds nothing. Use `tools/srcgrep.py`.
- `ls` is aliased to a long listing. Use Python `glob` in scripts.
- `sed` patterns fail silently. Edit with Python and assert each match.
