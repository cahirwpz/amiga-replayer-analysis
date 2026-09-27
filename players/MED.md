---
player: MED
template: 2
ideas:
  [volume-list, wave-list, cross-list-jumps, waveform-as-table, release-jump]
---

# MED

A synth sound runs a volume list and a wave list that jump into each other.

## Context

| Fact      | Value                                                                                            |
| --------- | ------------------------------------------------------------------------------------------------ |
| Player    | `MED`                                                                                            |
| Author    | Teijo Kinnunen                                                                                   |
| Code read | original: `ext/uade/amigasrc/players/uade/med`                                                   |
| Links     | [archive.org](https://archive.org/details/OctaMED_Professional_v3.00_1992_RBF_Software_CU_Amiga) |

## Key ideas

- Two opcode lists per instrument, each at its own speed. `:SynthTick`
  - Enables: a slow volume shape beside fast wave changes.
  - Costs: 256 bytes of lists per synth sound; CPU low.
- Each list can set the other's position. `:VolJumpWaveList` `:WaveJumpVolList`
  - Enables: a volume phase can start a new wave phrase.
  - Costs: jumps have no conditions; the target keeps its own clock.
- Waveforms double as volume envelopes and vibrato shapes. `:VolEnvOnce`
  `:VibratoWave`
  - Enables: drawn envelope and vibrato shapes, with no new data type.
  - Costs: an envelope takes 128 list visits; it shares the 64-wave pool.
- Hybrid instruments run a sample through the same lists. `:StartSynthNote`
  - Enables: list envelopes and pitch on a sampled sound.
  - Costs: the sample fills the first of the 64 waveform entries.
- Hold ends in a jump to the volume list's release part. `:HoldAndFade`
  `:SynthRelease`
  - Enables: the list itself shapes the release.
  - Costs: a note-off command skips it and stops the note at once.

## Composer's view

What the composer edits, from the author's
[format notes](../ext/uade/amigasrc/players/uade/med/MMD_FileFormat.doc).

```python
Note = NewType("Note", int)

@dataclass
class Command:
    number: int                         # e.g. CMD_PORTAMENTO
    argument: int

@dataclass
class Row:                              # MED: `line`
    note: Note | None
    instrument: int | None              # without a note: the hold goes on
    commands: list[Command]             # one per command page

@dataclass
class Pattern:                          # MED: `block`
    tracks: list[list[Row]]             # one track per voice; own row count

@dataclass
class Score:
    patterns: list[Pattern]
    position_lists: list[list[int]]     # pattern numbers; older modules: one
    sections: list[int]                 # position-list numbers; may repeat
    play_transpose: int                 # shifts every note
    ticks_per_row: int
    tempo: int
    track_volumes: list[int]
    instruments: list[Instrument]       # Instrument.transpose shifts its notes
```

| Aspect   | Answer                                                    | Source           |
| -------- | --------------------------------------------------------- | ---------------- |
| Notation | A tracker grid: one column per track, one line per row.   | (manual)         |
| Notation | Synth sounds: two lists of values and opcodes.            | format notes     |
| Cost     | A synth arpeggio is one wave-list opcode.                 | `:ArpeggioStart` |
| Cost     | A pattern arpeggio needs its command on every row.        | `:ArpeggioTick`  |
| Cost     | A drawn envelope is one waveform and one opcode.          | `:VolEnvOnce`    |
| Cost     | A release needs no pattern data: hold and decay start it. | `:SynthRelease`  |

## Timing

| Stream    | Scope | Carries                   | Control         | Advances by |
| --------- | ----- | ------------------------- | --------------- | ----------- |
| Positions | song  | pattern number            | loop            | pattern end |
| Pattern   | song  | note, instrument, command | loop, jump, end | row         |

| Aspect  | Value           | Label                     |
| ------- | --------------- | ------------------------- |
| Time    | rows            | `:PlayTick`               |
| Unit    | row             | `:PlayTick`               |
| Routing | fixed           | `:PlayRowNotes`           |
| Reuse   | patterns, loops | `:NextPlaySeq` `:CmdLoop` |
| Tempo   | speed, timer    | `:SetTempo`               |

Lifecycle handlers. Types and constants: [MED state](../details/MED-state.md).

```python
def on_note(voice: Voice, note: Note, instrument: Instrument,
            score: Score) -> None:          # PlayRowNotes, StartSynthNote
    kind = instrument.kind()
    voice.hold_left = instrument.hold or NEVER   # hold 0: never released
    voice.decay = instrument.decay
    voice.period = note_period(note + score.play_transpose + instrument.transpose,
                               instrument.finetune)  # AddTransposes
    if not (voice.kind == Kind.SYNTH and kind == Kind.SYNTH):
        voice.channel.stop()                # KeepSynthChannel skips this
    sound = instrument.sound
    if isinstance(sound, Sample):
        voice.channel.play(sound)
    else:
        if sound.hybrid:
            voice.channel.play(sound.waves[0])
        voice.volume_list.restart(sound.volume_speed)
        voice.wave_list.restart(sound.wave_speed, keep_pos=voice.command_e)
        voice.reset_modulation()
    voice.kind = kind

def before_row(voice: Voice, next_row: Row, score: Score) -> None:  # ExtendHold
    if voice.hold_left == NEVER:            # MED has no key-up
        return
    if next_row.note is None:
        keep = next_row.instrument is not None
    else:
        keep = (bool(next_row.commands)
                and next_row.commands[0].number == CMD_PORTAMENTO)
    if keep:
        voice.hold_left += score.ticks_per_row      # the key stays down

def on_tick(voice: Voice) -> None:          # HoldAndFade
    if voice.hold_left != NEVER:
        voice.hold_left -= 1
        if voice.hold_left == NEVER:
            on_release(voice)
    if voice.fade_speed:                    # samples only
        voice.note_volume -= voice.fade_speed
        if voice.note_volume < 0:
            voice.note_volume, voice.fade_speed = 0, 0

def on_release(voice: Voice) -> None:       # SynthRelease
    if voice.kind in (Kind.SYNTH, Kind.HYBRID):
        jump(voice.volume_list, voice.decay)    # decay: release position
    elif voice.decay:
        voice.fade_speed = voice.decay
    else:
        voice.channel.stop()

def on_note_off_command(voice: Voice) -> None:  # CmdNoteOff: no release
    voice.kind = Kind.NONE
    voice.channel.stop()                    # ChannelOff

# Program end: END parks a list on itself. Later visits read END again,
# while slides, envelope and arpeggio run on.    VolListEnd, WaveListEnd
```

## Sound

### Period

```python
def period(voice: Voice) -> int:            # UpdatePerVol
    base = voice.period                     # pattern_portamento moves it
    if voice.kind in (Kind.SYNTH, Kind.HYBRID):
        if voice.synth_arpeggio.running():
            base = voice.synth_arpeggio.period()
        base += voice.synth_vibrato.offset() + voice.pitch_slide
    return base + voice.pattern_vibrato - voice.pattern_arpeggio
```

Pattern vibrato shares its offset with command 13.
[Full order](../details/MED-control.md#pitch-and-volume)

| Controller         | Kind          | Advances by | Owner | Set by    | Label             |
| ------------------ | ------------- | ----------- | ----- | --------- | ----------------- |
| Pattern            | command list  | row         | song  | Positions | `:PlayRowNotes`   |
| Pattern portamento | state machine | tick        | voice | Pattern   | `:PortamentoTick` |
| Synth arpeggio     | table walker  | tick        | voice | Wave list | `:SynthArpeggio`  |
| Synth vibrato      | table walker  | tick        | voice | Wave list | `:SynthVibrato`   |
| Pitch slide        | state machine | list visit  | voice | Wave list | `:WaveListTick`   |
| Pattern vibrato    | state machine | tick        | voice | Pattern   | `:VibratoTick`    |
| Pattern arpeggio   | state machine | tick        | voice | Pattern   | `:ArpeggioTick`   |

### Volume

```python
def volume(voice: Voice) -> int:            # SynthTick, UpdatePerVol
    if voice.kind not in (Kind.SYNTH, Kind.HYBRID):
        return track_scale(voice.note_volume, voice)  # Hold fades it
    if voice.volume_list.due():             # each step overwrites the last
        if voice.volume_slide:
            voice.synth_volume = clamp(voice.synth_volume + voice.volume_slide,
                                       0, MAX_VOLUME)
        if voice.envelope.wave is not None:
            voice.synth_volume = voice.envelope.next()
        value = voice.volume_list.value()
        if value is not None:
            voice.synth_volume = value
    return track_scale(voice.synth_volume * voice.note_volume // MAX_VOLUME,
                       voice)
```

| Controller   | Kind          | Advances by   | Owner | Set by              | Label              |
| ------------ | ------------- | ------------- | ----- | ------------------- | ------------------ |
| Pattern      | command list  | row           | song  | Positions           | `:UpdatePerVol`    |
| Volume slide | state machine | list visit    | voice | Volume list         | `:SynthTick`       |
| Envelope     | table walker  | list visit    | voice | Volume list         | `:VolEnvelopeStep` |
| Volume list  | command list  | every N ticks | voice | instrument          | `:SynthTick`       |
| Hold         | state machine | tick          | voice | instrument, Pattern | `:HoldAndFade`     |

### Sample

```python
def wave_list_step(voice: Voice, sound: SynthSound) -> None:  # WaveListTick
    if voice.wave_list.due():
        number = voice.wave_list.value()
        if number is not None:
            voice.channel.play(sound.waves[number])   # in place, no copy
```

A Pattern note starts the sound; see `on_note` in Timing.

| Controller | Kind         | Advances by   | Owner | Set by     | Label             |
| ---------- | ------------ | ------------- | ----- | ---------- | ----------------- |
| Pattern    | command list | row           | song  | Positions  | `:StartSynthNote` |
| Wave list  | command list | every N ticks | voice | instrument | `:WaveListTick`   |

## Instrument

Fields from the author's
[format notes](../ext/uade/amigasrc/players/uade/med/MMD_FileFormat.doc).

```python
@dataclass
class Instrument:                       # MMD0sample, InstrExt
    volume: int                         # 0..MAX_VOLUME: the note volume
    transpose: int                      # semitones added to each note
    hold: int                           # ticks the key stays down; 0: forever
    decay: int                          # synth: release position; sample: fade speed
    finetune: int                       # in FINETUNE
    sound: Sample | SynthSound

    def kind(self) -> Kind:
        if isinstance(self.sound, Sample):
            return Kind.SAMPLE
        return Kind.HYBRID if self.sound.hybrid else Kind.SYNTH

@dataclass
class Sample:
    data: bytes
    repeat: range                       # the looped part

@dataclass
class SynthSound:                       # SynthInstr
    hybrid: bool                        # waves[0] is a Sample
    volume_list: bytes                  # up to LIST_LENGTH; from FIRST_OPCODE: opcodes
    wave_list: bytes                    # up to LIST_LENGTH; from FIRST_OPCODE: opcodes
    volume_speed: int                   # ticks per volume-list visit
    wave_speed: int                     # ticks per wave-list visit
    waves: list[bytes | Sample]         # up to WAVE_COUNT, played in place
```

| Question               | Answer                                         |
| ---------------------- | ---------------------------------------------- |
| Starts on note-on      | both lists and their modulation, see `on_note` |
| Survives the last note | the running channel, if synth follows synth    |
| Track overrides        | Command E sets the wave list start.            |
| Track overrides        | Instrument-only rows extend the hold.          |

## Interactions

```python
def jump(target: ListCursor, pos: int) -> None:  # the counter runs on, so the
    target.pos, target.wait = pos, 0             # target acts at its next visit

def on_jws(voice: Voice, arg: int) -> None:     # VolJumpWaveList: volume-list opcode
    jump(voice.wave_list, arg)

def on_jvs(voice: Voice, arg: int) -> None:     # WaveJumpVolList: wave-list opcode
    jump(voice.volume_list, arg)

def on_command_e(voice: Voice, arg: int) -> None:  # CmdWaveListPos: pattern command
    voice.wave_list.pos = arg               # its wait stays
    voice.command_e = True                  # a note on this row keeps this start
```

- Pattern commands add effects like `ProTracker`'s. `:ChannelFX`

## Open questions

- Which songs use the jumps between lists?
