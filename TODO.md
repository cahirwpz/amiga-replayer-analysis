# Open work

The hand-off between sessions. What belongs here: see
[`AGENTS.md`](AGENTS.md#sessions).

## Pilot

Twelve cards test the card template before the full survey.

Selection rules:

- Formats that did not prevail on the demoscene. No `ProTracker`-like players.
- Themes: cheap but expressive synthesis, unusual tricks, soft voice mixing.
- `replay` must be `uade` in the output of `tools/inventory.py`.

All twelve pilot cards exist.

## After the pilot

### Card reviews

- [ ] Run the card reviews on the other cards. The user chose this as the next
      task.
  - Check each finding against the code before recording it.
  - Runs vary. Writing found 1 issue, then 14. MaxTrax coverage found 0, then 7
    real gaps.
  - Coverage overclaimed once.
  - Next card: `TFMX-7V`. Go on alphabetically, three cards per batch.
    `tools/reviews.py` lists the state.
  - A glossary edit makes every writing review stale. Rerun the stale ones at
    the end, not after each edit.
  - Writing reviews ask to split field lists ("A row: note, instrument, …") and
    "fact. Consequence." cells. Both stay, as on the Fred card.
  - The session may not load `.claude/agents/`. Then run a general-purpose agent
    with the agent file as its prompt.

### Hardware model

- [ ] Test `hardware/paula.py` against vAmiga's Paula. Case: a SoundMon note
      restart above the period limit in `specs/soundmon_22.py:PlayRow`. The
      driver of `tools/timing.py` must read the audio channel state.
- [ ] vAmiga bug: bitplane DMA before the first frame's end crashes it.
      `tools/timing.py` works around it. Ask the user: report it upstream?
- [ ] Sound from vAmiga: save its audio port's samples to a file. Then a replay
      can be heard without a display.

### New cards

Skip unless a new lead turns up:

- `ActionAmics`: the one-byte sweep, once per tick per shared sample.

### Print layout

Fix in `tools/print.py:write_pdf`:

- [ ] A table split across two pages repeats no header row.
- [ ] A heading can land on the last line of a page.

### Then

- [ ] Review the cards with the user.
- [ ] Decide how to group `ideas/`: pages per technique slug, or per control
      dimension (see `docs/control-dimensions.md`).
- [ ] Write more technique pages in `ideas/`; `voice-mixing` is the first.
- [ ] Add a check that `ideas:` slugs in cards exist.
- [ ] Generate a technique index from the slugs, for the front page.

## Open questions

### Needs outside material

- Modules: which songs use a feature? MED list jumps, TFMX Pro offset loops and
  byte checks, SoundPlayer `DD` and modulation in Lemmings. TFMX 7V notes to
  voice 3.
- Modules for cards:
  - [Fred](players/Fred.md): a module with morph instruments.
  - [David Whittaker](players/DavidWhittaker.md): a version that rewrites a
    pulse wave (inference from
    `DavidWhittakerWorker.cs:ExtractInfoFromPlayFunction`). It may earn a delta
    card. Also Xenon 2's effect waves and effect samples, past `dw.ingame`.
  - [SoundFactory](players/SoundFactory.md): sync opcodes.
  - [Jason Page](players/JasonPage.md): branch markers and save slots.
  - [Paul Robotham](players/PaulRobotham.md): pulses per quarter note.
  - [MusicMaker 8V](players/MusicMaker-8V.md): quarter tones.
- Releases: did a game or demo ship Oktalyzer's replay 1? Which games used
  MaxTrax?
- Docs or credits: Sonic Arranger's `AMF` name. Other games with Digital Sonix &
  Chrome. Other Synth Dream composers.
- [MIDI-Loriciel](players/MIDI-Loriciel.md): which scores avoid overlapping
  notes on one MIDI channel?
- The sound chip's datasheet: compare the Hippel ST volume table with the chip.

## Later

- [ ] Full survey of the remaining players with readable source.
- [ ] Compare code for the `name` lineage links in `data/players.yaml`.
- [ ] Mark `ProTracker`-like players `skip: protracker` in `data/players.yaml`.
- [ ] Pick the first binary-only player to disassemble. Filter by scope first.
- [ ] Before disassembling a player, look for a port of it outside UADE. Use it
      as a map, not as evidence.

## Disassembly queue

A port is not evidence (see [`AGENTS.md`](AGENTS.md#evidence)). These players
need 68k code first.

| Player             | Why                                          | Map |
| ------------------ | -------------------------------------------- | --- |
| `BenDaglish-SID`   | Replay code is in the module; needs a module | —   |
| `JankoMrsicFlogel` | Replay code is in the module; needs a module | —   |
| `Special-FX`       | Replay code is in the module; needs a module | —   |

## Disassembly notes

Tooling works for player binaries, executables and object files. vlink links
objects; `listing` checks that vasm rebuilds the input. Workflow:
[`tools/disasm.py`](tools/disasm.py).

- Committed configs: `okplay1` and `okplay2`, Oktalyzer's replay objects. They
  match `okta.asm`. No player config yet.
- `seed` on an object makes every code symbol an entry. `ChannelModes`,
  `SH_Speed` and `SH_Len` are data. Their bogus `CODE` range in `okplay1` and
  `okplay2` was removed by hand.

- Seeding was tried on `Laxity` and `TFMX-7V-TFHD`.
- `-preproc` misses code reached by jump tables or pointers. Example:
  `TFMX-7V-TFHD` keeps `4e75` (`rts`) inside data at `$060c`. Add `CODE` ranges
  by hand.
- IRA 2.11 refuses `-preproc` over an existing `.cnf`. So `seed` runs once per
  tag entry and merges the areas.
- IRA may read a slot of a `bra.w` jump table as data. Example: the `$2C0` slot
  of `JumpTable` in `AbyssHighestExperience`. Its replay code was added by hand.
- Many binary-only players are 1–3 kB. Some may be wrappers (guess). Check each
  one when its config is made.
