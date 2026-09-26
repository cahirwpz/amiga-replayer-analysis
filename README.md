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
enforces size limits; `tools/cogload.py` defines them.

## Layout

| Path                 | Content                                        |
| -------------------- | ---------------------------------------------- |
| `ext/`               | UADE and other replayer sources, as submodules |
| `ideas/`             | One page per distinct idea                     |
| `players/`           | One card per replayer                          |
| `details/`           | Deep dives on request                          |
| `docs/`              | Paula summary, glossary, inventory             |
| `data/inventory.csv` | Every replayer and its source                  |
| `tools/cogload.py`   | Cognitive load checker                         |
| `tools/inventory.py` | Builds the inventory                           |

## Setup

Run `source ./activate` in the repo root. It fetches the submodule, creates a
Python venv and installs the pre-commit hooks.

## Status

| Step                                           | State                              |
| ---------------------------------------------- | ---------------------------------- |
| 1. Scaffold                                    | done                               |
| 2. Inventory of replayers                      | done: 176 players, 131 with source |
| 3. Pilot on about 10 players, then tune limits | next                               |
| 4. Full survey and idea pages                  | planned                            |
