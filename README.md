# UADE replayer analysis

UADE ships over 200 Amiga music replayers. Most are variants of a few core
ideas. This repo finds those ideas and explains each one briefly.

## How to read

1. Start here. The summary of ideas will live in this file.
2. Read `ideas/` for one page per idea.
3. Read `players/` for one short card per replayer.
4. `details/` holds deep dives, written only on request.

Background: `docs/paula.md` explains the sound chip. `docs/glossary.md` defines
every acronym.

## Style

Texts are short on purpose, for C1 non-native readers. A pre-commit hook
enforces size limits; `CLAUDE.md` lists them.

## Layout

| Path               | Content                         |
| ------------------ | ------------------------------- |
| `uade/`            | UADE source, as a git submodule |
| `ideas/`           | One page per distinct idea      |
| `players/`         | One card per replayer           |
| `details/`         | Deep dives on request           |
| `docs/`            | Paula summary, glossary         |
| `tools/cogload.py` | Cognitive load checker          |

## Setup

Run `source ./activate` in the repo root. It fetches the submodule, creates a
Python venv and installs the pre-commit hooks.

## Status

| Step                                           | State   |
| ---------------------------------------------- | ------- |
| 1. Scaffold                                    | done    |
| 2. Inventory of replayers                      | next    |
| 3. Pilot on about 10 players, then tune limits | planned |
| 4. Full survey and idea pages                  | planned |
