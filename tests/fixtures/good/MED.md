---
player: MED
template: 2
ideas: [volume-list]
---

# MED fixture

A template 2 card with one row per table.

## Context

| Fact      | Value                                                                                            |
| --------- | ------------------------------------------------------------------------------------------------ |
| Player    | `MED`                                                                                            |
| Author    | Teijo Kinnunen                                                                                   |
| Code read | original: `ext/uade/amigasrc/players/uade/med`                                                   |
| Links     | [archive.org](https://archive.org/details/OctaMED_Professional_v3.00_1992_RBF_Software_CU_Amiga) |

## Key ideas

- Each list runs at its own speed. `:SynthTick`
  - Enables: slow envelopes beside fast waves.
  - Costs: one counter per list; CPU low.

## Composer's view

```python
@dataclass
class Score:
    instruments: list[Instrument]
```

| Aspect   | Answer       | Source   |
| -------- | ------------ | -------- |
| Notation | tracker grid | (manual) |
| Cost     | one opcode   | `:DoFX`  |

## Timing

| Stream  | Scope | Carries                   | Control         | Advances by |
| ------- | ----- | ------------------------- | --------------- | ----------- |
| Pattern | song  | note, instrument, command | loop, jump, end | row         |

| Aspect  | Value    | Label          |
| ------- | -------- | -------------- |
| Time    | rows     | `:PlayTick` |
| Unit    | row      | `:PlayTick` |
| Routing | fixed    | `:PlayRowNotes`   |
| Reuse   | patterns | `:NextPlaySeq` |
| Tempo   | speed    | `:SetTempo`   |

```python
def on_note(voice: Voice, instrument: Instrument) -> None:  # KeepSynthChannel
    voice.hold_left = instrument.hold or NEVER
```

## Sound

### Volume

```python
def volume(voice: Voice) -> int:
    value = voice.volume_list.value()
    return value if value is not None else voice.envelope.next()
```

| Controller  | Kind         | Advances by   | Owner | Set by     | Label        |
| ----------- | ------------ | ------------- | ----- | ---------- | ------------ |
| Volume list | command list | every N ticks | voice | instrument | `:SynthTick` |
| Envelope    | table walker | list visit    | voice | Volume list | `:VolEnvOnce` |

## Instrument

```python
@dataclass
class Instrument:
    hold: int                           # ticks the key stays down

@dataclass
class Sample:
    data: bytes
```

| Question               | Answer          |
| ---------------------- | --------------- |
| Starts on note-on      | both lists      |
| Survives the last note | nothing         |
| Track overrides        | wave list start |

## Interactions

```python
def on_command_e(voice: Voice, arg: int) -> None:  # CmdWaveListPos
    voice.wave_list.pos = arg
```
