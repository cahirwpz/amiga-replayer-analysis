# Open work

The hand-off between sessions. What belongs here: see
[`AGENTS.md`](AGENTS.md#sessions).

## After the pilot

### Priorities

In this order:

1. [ ] Review the cards with the user. The user opens each card; record verdicts
       here. Order, synthesis first:
   - Synthesis: SoundMon2.2, Fred, MugicianII, SynthDream, ArtOfNoise-8V,
     FutureComposer1.4, Jochen_Hippel_ST, SonicArranger, AbyssHighestExperience,
     VoodooSupremeSynthesizer, DigitalSonixChrome, MusiclineEditor,
     DavidWhittaker, RobHubbard, TimFollin.
   - Sequencing: TFMX-Pro, SoundFactory, JasonPage, PaulRobotham, MaxTrax,
     MIDI-Loriciel, SonixMusicDriver, SoundPlayer, MED, FaceTheMusic.
   - Mixing: MusicMaker-8V, Oktalyzer, TFMX-7V.
   - All cards are in template 3. The user calls SoundMon2.2 solid.
2. Ideas:
   - [ ] Decide how to group `ideas/`: pages per technique slug, or per control
         dimension (see `docs/control-dimensions.md`).
   - [ ] Write more technique pages in `ideas/`; `voice-mixing` is the first.
   - [ ] Add a check that `ideas:` slugs in cards exist.
   - [ ] Generate a technique index from the slugs, for the front page.
3. [ ] Triage players, synthesis first. See [Triage](#triage).

### Triage

NostalgicPlayer's ports (`ext/nostalgicplayer/Source/Agents/Players`) are the
shortlist and the map. A card still needs 68k code. Record each decision in
`data/players.yaml`: a card, or a `skip`.

Synthesis gaps (guess):

- ring modulation and amplitude modulation
- hard sync
- synthesis per output sample
- interpolation
- C64-style pulse and filter

Check `family` first. A newer version of a carded lineage needs a distinct idea.

- [ ] The other 77 players with `replay` `uade` and no decision.

Not in UADE, so not in `data/players.yaml`:

- `Sawteeth`: a BeOS editor, not an Amiga format. Out of scope.
- `HivelyTracker`: skipped by the user. Its replay is C, with no 68k code.
- `RonKlaren`: a one-byte sweep, as on [Fred](players/Fred.md) (port).

Reading notes:

- `ext/uade/amigasrc/players/uade/artofnoise/ArtofNoise8.s:mix_channels`: a
  linear interpolation pass, commented out. The only interpolation attempt seen
  so far.

### Review notes

All card reviews are current. For the next rerun:

- Ask the user first. A rerun costs one agent per card.
- Check each finding against the code before recording it. Coverage overclaimed
  "spec misses it" twice.
- Writing reviews ask to split field lists ("A row: note, instrument, …") and
  "fact. Consequence." cells. Both stay, as on the Fred card.
- Writing reviews flag "wave" as missing from the glossary. It stays a plain
  word, as in the glossary's own entries.
- A count computed from code constants gets "(estimate)".
- The glossary page is at the cogload limit of 3000 words. Reword cards in plain
  words before adding a term.
- The session may not load `.claude/agents/`. Then run a general-purpose agent
  with the agent file as its prompt.

### Spec fixes

Found during the template 3 rewrites. Not yet checked by the user.

- [ ] `specs/synth_dream.py`: a modifier that starts a pattern is dropped. The
      68k code skips the opcode twice, so it misreads it.
- [ ] `specs/tfmx_pro.py`: a loop comment says the counter is 0 on the first
      visit. The 68k code starts it at -1. The logic is right.
- [ ] `specs/tfmx_pro.py`: register writes at the tick's end match only the "DMA
      wait" path of the listing. Trace the default path.
- [ ] `specs/voodoo_supreme_synthesizer.py`: docstrings say the fill uses the
      idle half. The tick fills the half Paula may play, so it can tear. Test
      the Paula reload rule in an emulator.
- [ ] `specs/voodoo_supreme_synthesizer.py`: after a sample's end, the spec
      keeps the voice silent. The 68k code moves the pointer on from
      `EmptySample`. Open question on the card.
- [ ] `specs/tfmx_7v.py`: `MixOff` must turn off the replay's interrupt
      (`INTENA`). DMA on and off on voices 4–7 must call `FakeDma` at once. The
      card already states both from the listing.

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

Workflow and IRA pitfalls: [`tools/disasm.py`](tools/disasm.py).

- Committed configs: `okplay1` and `okplay2`, Oktalyzer's replay objects. No
  player config yet. Seeding was tried on `Laxity` and `TFMX-7V-TFHD`.
- Many binary-only players are 1–3 kB. Some may be wrappers (guess). Check each
  one when its config is made.
