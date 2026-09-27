# MED state

State, constants and helpers of the four-channel replay, version 7.0, as typed
Python. Used by the [MED card](../players/MED.md). Comments name the replay's
fields. A body of `...` is behavior that the card or the code describes.

```python
NEVER = -1                              # hold_left: the key is never released
MAX_VOLUME = 64                         # volumes run 0..MAX_VOLUME
LIST_LENGTH = 128                       # bytes per volume or wave list
FIRST_OPCODE = 0x80                     # list bytes from here on are opcodes
WAVE_COUNT = 64                         # waveforms per synth sound
FINETUNE = range(-8, 8)
CMD_PORTAMENTO = 3                      # pattern command that keeps a hold
TRACK_VOLUME_BITS = 8                   # track_volume is a fixed-point factor

class Kind(Enum):                       # trk_synthtype
    NONE = auto()
    SAMPLE = auto()
    SYNTH = auto()
    HYBRID = auto()

class Channel:                          # one Paula channel
    def play(self, sound: bytes | Sample) -> None: ...
    def stop(self) -> None: ...

@dataclass
class ListCursor:                       # one per list and voice
    pos: int                            # trk_volcmd, trk_wfcmd
    wait: int                           # visits left, WAI: trk_volwait, trk_wfwait
    counter: int                        # ticks to the next visit: trk_volxcnt, trk_wfxcnt
    speed: int                          # counter reload: trk_initvolxspd, trk_initwfxspd

    def due(self) -> bool: ...          # counts down; True on a visit
    def value(self) -> int | None: ...  # runs opcodes; the value read, if any
    def restart(self, speed: int, keep_pos: bool = False) -> None: ...

@dataclass
class Envelope:                         # trk_envptr, trk_envcount, trk_envrestart
    wave: bytes | None                  # None: off
    pos: int
    loop: bool

    def next(self) -> int: ...          # the next wave byte, as a volume

@dataclass
class Arpeggio:                         # trk_arpsoffs, trk_arpgoffs
    start: int
    pos: int                            # 0: off

    def running(self) -> bool:
        return self.pos != 0

    def period(self) -> int: ...        # this step's note period; steps on

@dataclass
class Vibrato:                          # trk_synvibdep, trk_synthvibspd, trk_synviboffs
    depth: int                          # 0: off
    speed: int
    phase: int
    wave: bytes                         # trk_synvibwf: sine, or an instrument wave

    def offset(self) -> int: ...        # period offset; the phase steps on

@dataclass
class Portamento:                       # trk_porttrgper, trk_prevportspd
    target: int
    speed: int

@dataclass
class Voice:                            # one per track; track n plays on channel n
    channel: Channel
    kind: Kind
    period: int                         # trk_prevper: the Pattern's period
    note_volume: int                    # trk_prevvol
    track_volume: int                   # trk_trackvol: master and track volume
    hold_left: int                      # trk_noteoffcnt
    decay: int                          # trk_decay
    fade_speed: int                     # trk_fadespd
    command_e: bool                     # trk_miscflags bit 0
    volume_list: ListCursor
    wave_list: ListCursor
    synth_volume: int                   # trk_synvol
    volume_slide: int                   # trk_volchgspd: 0 is off
    envelope: Envelope
    pitch_slide: int                    # trk_perchg: the summed offset
    pitch_slide_speed: int              # trk_wfchgspd
    synth_arpeggio: Arpeggio
    synth_vibrato: Vibrato
    pattern_portamento: Portamento
    pattern_vibrato: int                # trk_vibradjust; command 13 too
    pattern_arpeggio: int               # trk_arpadjust

    def reset_modulation(self) -> None: ...   # arpeggio, slides, envelope, vibrato

@dataclass
class Song:                             # playback position
    section: int                        # mmd_psecnum
    position: int                       # mmd_pseqnum
    row: int                            # mmd_pline
    loop_row: int
    loop_count: int

def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))

def note_period(note: int, finetune: int) -> int: ...   # the period table

def track_scale(volume: int, voice: Voice) -> int:      # RELVOL
    return volume * voice.track_volume >> TRACK_VOLUME_BITS
```
