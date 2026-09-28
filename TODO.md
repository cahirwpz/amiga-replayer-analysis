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

### Rejected

| Player                     | Reason                              |
| -------------------------- | ----------------------------------- |
| `PreTracker`               | Replay code is a prebuilt binary    |
| `Pokeynoise`, `ADPCM_mono` | Too primitive or already well known |
| `Mugician`                 | Covered by `MugicianII`             |
| `JochenHippel-7V`          | Same mixer as `TFMX-7V`             |
| `PTK-Prowiz`               | `ProTracker`-like                   |

## After the pilot

### Card template 2

The template is in [`docs/card-template.md`](docs/card-template.md). `MED` is
the first card on it, with `specs/med.py`.

- [ ] Composer's view for MED rests on the format notes. Ask the user for an
      OctaMED manual that covers synth sounds.

### Hardware model

- [ ] `hardware/paula.py:Channel` times each word from the last DMA slot. At
      period 428 a word lasts 908 CCK, not 856, so every spec plays flat.
      [Musicline](players/MusiclineEditor.md)'s 8-channel mode ticks at 28 Hz.
- [ ] Make `hardware/paula.py:Sample` the 16-bit words that DMA fetches, each
      two 8-bit samples, high byte first. It must show writes made while it
      plays; `specs/sonic_arranger.py:StartSynthWave` casts a `bytearray` now.
- [ ] `POLL_CCK` is an estimate from 68000 instruction timings. It is 25 in
      `specs/med.py:StartDMA`, 20 in
      `specs/digital_sonix_chrome.py:WaitAudioIrq`, 15 in
      `specs/jochen_hippel_st.py:NotePlay` and 10 in
      `specs/oktalyzer.py:QueueBuffers`. Measure or cite one poll of each.
- [ ] `specs/midi_loriciel.py:StartNote` waits 513 loops of `nop` and `dbra`,
      estimated at 7 CCK each. Measure or cite one loop.
- [ ] `specs/soundmon_22.py:PlayRow` waits 640 CCK, an estimate of 128 `dbra`
      loops. Does a note with a period above 320 miss its restart?
- [ ] `specs/jochen_hippel_st.py` and `specs/soundmon_22.py` run by a 50 Hz
      timer. Check DeliTracker's default rate for a player without `DTP_Timer`.

### New cards

The user's list, triaged. Nothing below is on a card yet. "Docs" means format
notes or comments only; "skimmed" means replay code read in part.

| Order | Player          | Value | Basis   | Lead                                          |
| ----- | --------------- | ----- | ------- | --------------------------------------------- |
| 1     | `MusicMaker-8V` | high  | docs    | Eight voices mixed into four channels         |
| 2     | `PaulRobotham`  | med   | skimmed | Packed note lengths, vibrato scaled by period |

Reading notes, with original labels:

| Player          | Where                                                                                   | Note                                              |
| --------------- | --------------------------------------------------------------------------------------- | ------------------------------------------------- |
| `MusicMaker-8V` | `ext/uade/amigasrc/players/other/music_maker/MusicMaker8.asm`                           | Mixer header comment: `FAST-VOL-MIX`              |
| `MusicMaker-8V` | `ideas/voice-mixing.md`                                                                 | Compare the mixer with this page                  |
| `PaulRobotham`  | `ext/uade/amigasrc/players/wanted_team/PaulRobotham/src/Paul Robotham_v1.asm:lbC015406` | Length: 5 bits, shifted by 3 bits                 |
| `PaulRobotham`  | `:lbC015406`                                                                            | Tempo scaling keeps the remainder                 |
| `PaulRobotham`  | `lbC01562E`                                                                             | Commented: effect takes the voice nearest its end |
| `PaulRobotham`  | —                                                                                       | Voices are fixed, not allocated                   |

Skip unless a new lead turns up:

- `DeltaMusic2.0` and `SIDMon2.0`: only C ports. They show tables close to
  Future Composer, SoundMon and Sonic Arranger.

### Then

- [ ] Review the cards with the user.
- [ ] Write more technique pages in `ideas/`; `voice-mixing` is the first.
- [ ] Add a check that `ideas:` slugs in cards exist.
- [ ] Generate a technique index from the slugs, for the front page.

## Open questions

### Needs outside material

- Modules: which songs use a feature? MED list jumps, TFMX Pro offset loops and
  byte checks, SoundPlayer `DD` and modulation in Lemmings. TFMX 7V notes to
  voice 3.
- Modules for new cards: [SoundFactory](players/SoundFactory.md) sync opcodes.
  [Jason Page](players/JasonPage.md) branch markers and save slots.
- Modules the user can find: FredMonitor (`Fred`), `SIDMon1.0` and
  `DavidWhittaker`. Their replay code ships inside each module.
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
- [ ] Note `ProTracker`-like players in `data/players.yaml`.
- [ ] Pick the first binary-only player to disassemble. Filter by scope first.
- [ ] Before disassembling a player, look for a port of it outside UADE. Use it
      as a map, not as evidence.
- [ ] Module inputs: decide provenance and storage; add IRA raw-binary support.

## Disassembly queue

A port is not evidence (see [`AGENTS.md`](AGENTS.md#evidence)). These players
need 68k code first.

| Player             | Why                                                     | Map                                |
| ------------------ | ------------------------------------------------------- | ---------------------------------- |
| `RobHubbard`       | `PGA_Tour_Golf.lha` available; needs raw-binary support | `ext/c-flod/neoart/flod/hubbard`   |
| `BenDaglish-SID`   | Replay code is in the module; needs a module            | —                                  |
| `JankoMrsicFlogel` | Replay code is in the module; needs a module            | —                                  |
| `Special-FX`       | Replay code is in the module; needs a module            | —                                  |
| `Fred`             | Replay code is in the module; needs a module            | `ext/c-flod/neoart/flod/fred`      |
| `SIDMon1.0`        | Replay code is in the module; needs a module            | `ext/c-flod/neoart/flod/sidmon`    |
| `DavidWhittaker`   | Port reads the module's code (guess: replay in module)  | `ext/c-flod/neoart/flod/whittaker` |

## Disassembly notes

Tooling works for player binaries, executables and object files. vlink links
objects; `listing` checks that vasm rebuilds the input. Workflow:
[`tools/disasm.py`](tools/disasm.py).

- Committed configs: `okplay1` and `okplay2`, Oktalyzer's replay objects. They
  match `okta.asm`. No player config yet.
- `seed` on an object makes every code symbol an entry. `ChannelModes`,
  `SH_Speed` and `SH_Len` are data. Their bogus `CODE` range in `okplay1` and
  `okplay2` was removed by hand.

- Seeding was tried on `DeltaMusic2.0`, `SIDMon2.0`, `Laxity` and
  `TFMX-7V-TFHD`.
- `-preproc` misses code reached by jump tables or pointers. Example:
  `TFMX-7V-TFHD` keeps `4e75` (`rts`) inside data at `$060c`. Add `CODE` ranges
  by hand.
- IRA 2.11 refuses `-preproc` over an existing `.cnf`. So `seed` runs once per
  tag entry and merges the areas.
- IRA may read a slot of a `bra.w` jump table as data. Example: the `$2C0` slot
  of `JumpTable` in `AbyssHighestExperience`. Its replay code was added by hand.
- Many binary-only players are 1–3 kB. Some may be wrappers (guess). Check each
  one when its config is made.
