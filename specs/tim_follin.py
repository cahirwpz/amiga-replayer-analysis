"""Tim Follin's replay, Follin Player II: DP_TimFollin.asm.

Card: players/TimFollin.md. Level 2: the control flow runs; leaf math is a
stub. Each CamelCase function is a label in data/annot/TimFollin.yaml;
each CamelCase class is in its `types:`. Comments name the replay's
fields as offsets from tmp+$80: bytes per voice, then words and longs.

There is no instrument program. Each voice's track sets parameters of
small state machines; they stay set until the track changes them.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from hardware import paula
from hardware.amiga import Amiga
from specs.controls import Program, StateMachine

PULSE_INSTRUMENTS = 4  # instruments 0-3 are pulse waves
PULSE_MIN, PULSE_MAX, PULSE_RESET = 4, 0x1E, 7  # wave byte indexes
PULSE_LOW, PULSE_HIGH = 0x00, 0x80  # the pulse's two byte values
SAMPLE_DATA = 0x32  # a sample's bytes start here; the word at 0 is its length
RESET_AT = 2  # ResetPulse writes from here, not from SAMPLE_DATA
RESET_WAVE = bytes([PULSE_HIGH] * 8 + [PULSE_LOW] * 24)  # 32 bytes
ATTACK_TOP = 0x3F  # attack ends at exactly this volume
CALL_SLOTS = 4  # return addresses per voice
SILENT_SUBSONG = 14  # all voices start inactive
SPECIAL_SUBSONG = 13  # SetVolume's override; nothing here arms it
FIRST_COMMAND = 0x80
GATE_OFF = 0x80  # flags bit 7
CHAIN = 0x40  # flags bit 6
SECOND_SAMPLE = 0x3F  # flags bits 0-5


# --- What the composer edits -------------------------------------------


@dataclass
class Subsong:  # the tables at +4, +$104 and +$144 of the module
    tracks: list[int]  # per voice, an offset into the module's bytes
    instruments: list[bytearray]  # each subsong has its own list
    voices: int  # 3 or 4; voice 3 is left alone with 3


# --- Voice state -------------------------------------------------------


ATTACK, DECAY, HOLD = 0, 1, 2  # envelope phases, $60; 3 and up also hold


@dataclass
class Envelope(StateMachine):  # $60 phase, $64 count, -$14 volume
    phase: int = ATTACK
    count: int = 0
    volume: int = 0  # the volume byte; the output
    step: int = 0  # -$50: added or subtracted per update
    attack_ticks: int = 0  # $68
    decay_ticks: int = 0  # $6C
    sustain: int = 0  # $70: decay holds here
    start: int = 0  # -$3C: a restarting note's volume
    start_phase: int = ATTACK  # -$40
    restart: bool = False  # -$44: notes restart the envelope


@dataclass
class Vibrato(StateMachine):  # $74, $78, -$78, -$6C, -$70, -$48
    delay: int = 0  # 0: off; else ticks before it starts, from a note
    delay_left: int = 0
    step: int = 0  # period units per tick
    half: int = 0  # ticks per half cycle; 0: one sweep
    count: int = 0
    first_up: int = 0  # the direction byte a note starts with


@dataclass
class Trill(StateMachine):  # -$60, -$64, $7C, -$68
    interval: int = 0  # semitones
    upper_ticks: int = 0  # 0: off
    lower_ticks: int = 0
    count: int = 0


@dataclass
class Pulse(StateMachine):  # $5C index, $58 narrowing, -$18, -$1C
    index: int = PULSE_RESET
    narrowing: bool = False
    speed: int = 0  # ticks per step
    count: int = 0


@dataclass
class Voice(Program):  # the fields at tmp+$80, per voice
    channel: paula.Channel = field(kw_only=True)
    track: bytes = b""  # the module's bytes; pos: (A6,D4)
    active: bool = False  # -$10
    ticks_left: int = 1  # -$4C
    fixed_length: int = 0  # -$2C: 0, notes carry a length byte
    loop_count: int = 0  # -$38: one loop slot
    loop_to: int = 0  # $10(A6,D4)
    returns: list[int] = field(default_factory=list)  # CallStacks
    instrument: int = 0  # -4
    sample: bytearray | None = None  # $30(A6,D4): length word, header, bytes
    note: int = 0  # -$5C: an index into the period table
    target: int = 0  # -$54: portamento's target note
    glide: int = 0  # -$58: semitones per tick; 0 off
    transpose: int = 0  # -$34
    skip_transpose: bool = False  # -$30: for the next note only
    up: int = 0  # -$74: vibrato's direction, and trill's side; EOR 1 flips it
    period: int = 0  # $48(A6,D5)
    flags: int = 0  # -$20: second sample, chain, gate off
    chain_due: bool = False  # -8
    envelope: Envelope = field(default_factory=Envelope)
    vibrato: Vibrato = field(default_factory=Vibrato)
    trill: Trill = field(default_factory=Trill)
    pulse: Pulse = field(default_factory=Pulse)


@dataclass
class Module:  # tmp, and L_12E6, L_12EA, L_12ED
    data: bytes  # the module; tracks, calls and jumps address it
    origin: int  # the address its pointers were built for; dx undoes it
    subsongs: list[Subsong]
    voices: list[Voice]
    amiga: Amiga
    subsong: int = 0
    fade: int = 0  # L_12ED: nothing in this player sets it


# --- Tick ---------------------------------------------------------------


def new_module(
    data: bytes, origin: int, subsongs: list[Subsong], amiga: Amiga
) -> Module:
    """The vertical blank runs ChainTick, then Tick."""
    voices = [Voice(channel=channel) for channel in amiga.paula.channels]
    module = Module(data, origin, subsongs, voices, amiga)

    def interrupt() -> None:
        ChainTick(module)
        Tick(module)

    amiga.vblank.handler = interrupt
    return module


def StartSubsong(module: Module, number: int) -> None:
    """_init. Subsong 14 starts with every voice inactive: it plays
    nothing. With 3 voices, voice 3 stays untouched."""
    module.subsong = number & 0x0F
    subsong = module.subsongs[module.subsong]
    module.voices = [Voice(channel=v.channel) for v in module.voices]  # clears tmp
    for n, voice in enumerate(module.voices[: subsong.voices]):
        voice.track, voice.pos = module.data, subsong.tracks[n]
        voice.active = module.subsong != SILENT_SUBSONG


def Tick(module: Module) -> None:
    """A fade, once started, counts down by 2 per tick. At 0 it starts
    subsong 0 (guess: a game's leftover)."""
    if module.fade:
        module.fade = max(module.fade - 2, 0)
        if module.fade == 0:
            StartSubsong(module, 0)
            return
    for voice in module.voices:
        VoiceTick(module, voice)


def VoiceTick(module: Module, voice: Voice) -> None:
    """Pulse sweep, envelope, vibrato or trill, portamento, then the note
    timer. A trill step skips portamento for this tick."""
    if not voice.active:
        return
    PulseSweep(voice)
    EnvelopeTick(module, voice)
    if voice.vibrato.delay and vibrato_due(voice):
        VibratoTick(voice)
        Portamento(voice)
    elif not TrillTick(voice):
        Portamento(voice)
    NoteTimer(module, voice)


# --- State machines ----------------------------------------------------


def PulseSweep(voice: Voice) -> None:
    """Instruments 0-3 only. Every `speed` ticks, the pulse widens by one
    byte up to index $1e, then narrows down to 4. It edits the sample
    itself, so voices on one pulse instrument share the wave."""
    pulse, sample = voice.pulse, voice.sample
    if voice.instrument >= PULSE_INSTRUMENTS or sample is None:
        return
    pulse.count -= 1
    if pulse.count:
        return
    pulse.count = pulse.speed
    if not pulse.narrowing:
        pulse.index += 1
        pulse.narrowing = pulse.index == PULSE_MAX
        write_wave(sample, pulse.index, PULSE_HIGH)
    else:
        pulse.index -= 1
        pulse.narrowing = pulse.index != PULSE_MIN
        write_wave(sample, pulse.index, PULSE_LOW)


def EnvelopeTick(module: Module, voice: Voice) -> None:
    """Attack adds `step` every attack_ticks + 1 ticks and
    ends only at exactly $3f. Decay subtracts it until the volume equals
    the sustain level, or goes negative. Then the volume holds. The
    volume goes out every tick."""
    env = voice.envelope
    if env.phase == ATTACK:
        env.count -= 1
        if env.count < 0:
            env.count = env.attack_ticks
            env.volume = (env.volume + env.step) & 0xFF
            if env.volume == ATTACK_TOP:
                env.phase, env.count = DECAY, env.decay_ticks
    elif env.phase == DECAY:
        env.count -= 1
        if env.count < 0:
            env.count = env.decay_ticks
            if env.volume == env.sustain:
                env.phase = HOLD
            else:
                env.volume = (env.volume - env.step) & 0xFF
                if env.volume >= 0x80:
                    env.phase = HOLD
    SetVolume(module, voice, env.volume)


def SetVolume(module: Module, voice: Voice, volume: int) -> None:
    """Caps the volume at fade / 4 while a fade runs. Subsong 13 has an
    override that nothing here arms."""
    if module.fade:
        volume = min(volume, module.fade >> 2)
    voice.channel.set_volume(volume)


def vibrato_due(voice: Voice) -> bool:
    """After a note, the delay counts down; trill runs meanwhile."""
    vibrato = voice.vibrato
    if not vibrato.delay_left:
        return True
    vibrato.delay_left -= 1
    return vibrato.delay_left == 0


def VibratoTick(voice: Voice) -> None:
    """Adds or subtracts `step` period units every tick.
    The direction turns every 2 × half ticks; the first turn comes after
    `half`, so the swing is centred. The turn flips bit 0 only: a
    direction byte other than 0 or 1 stays non-zero, so it never turns."""
    vibrato = voice.vibrato
    voice.period += vibrato.step if voice.up else -vibrato.step
    voice.channel.period = voice.period
    vibrato.count = (vibrato.count - 1) & 0xFF
    if vibrato.count == 0 and vibrato.half:
        vibrato.count = 2 * vibrato.half
        voice.up ^= 1


def TrillTick(voice: Voice) -> bool:
    """Moves the note itself up by `interval`, then down,
    for upper_ticks and lower_ticks. The first lower part, from the
    note's start, lasts upper_ticks too. It shares `up` with vibrato; a
    direction byte other than 0 or 1 only climbs. True: a step happened,
    so portamento skips this tick."""
    trill = voice.trill
    if not trill.count:
        return False
    trill.count -= 1
    if trill.count:
        return False
    voice.up ^= 1
    if voice.up:
        voice.note += trill.interval
        trill.count = trill.upper_ticks
    else:
        voice.note -= trill.interval
        trill.count = trill.lower_ticks
    set_note(voice, voice.note)
    return True


def Portamento(voice: Voice) -> None:
    """The note moves towards the target by `glide` semitones per tick.
    The period comes from the table, so portamento steps by semitones. A
    step overwrites vibrato's period for this tick."""
    if not voice.glide or voice.note == voice.target:
        return
    if voice.note > voice.target:
        note = max(voice.note - voice.glide, voice.target)
    else:
        note = min(voice.note + voice.glide, voice.target)
    set_note(voice, note)


def NoteTimer(module: Module, voice: Voice) -> None:
    """One tick before the note ends, the gate may stop the channel. At
    the end, the track reads on."""
    voice.ticks_left = (voice.ticks_left - 1) & 0xFF
    if voice.ticks_left == 1:
        GateOff(voice)
    elif voice.ticks_left == 0:
        ReadTrack(module, voice)


def GateOff(voice: Voice) -> None:
    """With flags bit 7, DMA off: the next note restarts the sample.
    Without it, the channel plays on, and the next note's sample starts
    at the end of this one's loop."""
    if voice.flags & GATE_OFF:
        voice.channel.disable()


# --- Track -------------------------------------------------------------


def ReadTrack(module: Module, voice: Voice) -> None:
    """Commands take no time: they run until a note or the end."""
    while voice.active:
        byte = voice.track[voice.pos]
        voice.pos += 1
        if 0 < byte < FIRST_COMMAND:
            PlayNote(module, voice, byte)
            return
        COMMANDS[byte & 0x7F](module, voice)


def PlayNote(module: Module, voice: Voice, byte: int) -> None:
    """With portamento on, the note becomes the target and the pitch
    stays. The envelope restarts after this tick's volume write, so the
    change is heard next tick."""
    note = byte + (0 if voice.skip_transpose else voice.transpose)
    voice.skip_transpose = False
    if voice.glide:
        voice.target = note & 0xFF
    else:
        voice.note = note & 0xFF
    voice.period = note_period(voice.note)
    StartSample(voice)
    voice.ticks_left = voice.fixed_length or voice.track[voice.pos]
    if not voice.fixed_length:
        voice.pos += 1
    voice.trill.count = voice.trill.upper_ticks
    vibrato = voice.vibrato
    voice.up = 0
    if vibrato.delay:
        vibrato.delay_left, vibrato.count = vibrato.delay, vibrato.half
        voice.up = vibrato.first_up
    env = voice.envelope
    if env.restart:
        env.phase = env.start_phase
        env.count = env.decay_ticks if env.phase else env.attack_ticks
        env.volume = env.start


def StartSample(voice: Voice) -> None:
    """Queues the sample and sets DMA on. If the channel still plays,
    DMA on does nothing: the new sample waits for the loop's end. With
    the chain flag, ChainSample follows one tick later."""
    assert voice.sample is not None
    voice.channel.queue(playable(voice.sample))
    voice.channel.enable()
    voice.chain_due = bool(voice.flags & CHAIN)
    voice.channel.period = voice.period


def ChainTick(module: Module) -> None:
    for voice in module.voices:
        ChainSample(module, voice)


def ChainSample(module: Module, voice: Voice) -> None:
    """Queues the second sample, flags bits 0-5 of the subsong's list.
    Paula took the first sample at DMA on, so the first plays once and
    the second loops. Waiting a tick keeps it from replacing the first."""
    if not voice.chain_due:
        return
    voice.chain_due = False
    subsong = module.subsongs[module.subsong]
    voice.channel.queue(playable(subsong.instruments[voice.flags & SECOND_SAMPLE]))
    voice.channel.enable()


# --- Commands ----------------------------------------------------------

Command = Callable[[Module, Voice], None]


def arg(voice: Voice) -> int:
    byte = voice.track[voice.pos]
    voice.pos += 1
    return byte


def CmdNop(module: Module, voice: Voice) -> None:
    """$00 and $80."""


def CmdInstrument(module: Module, voice: Voice) -> None:
    """$81 n: from the subsong's own instrument list."""
    voice.instrument = arg(voice)
    voice.sample = module.subsongs[module.subsong].instruments[voice.instrument]


def CmdCall(module: Module, voice: Voice) -> None:
    """$82 address. Four return slots per voice; nothing checks them."""
    target = address(module, voice)
    voice.returns.append(voice.pos)
    voice.pos = target


def CmdReturn(module: Module, voice: Voice) -> None:
    """$83."""
    voice.pos = voice.returns.pop()


def CmdLoopStart(module: Module, voice: Voice) -> None:
    """$84 count. One loop slot: loops do not nest."""
    voice.loop_count = arg(voice)
    voice.loop_to = voice.pos


def CmdLoop(module: Module, voice: Voice) -> None:
    """$85. Back to the loop start until the count runs out."""
    voice.loop_count = (voice.loop_count - 1) & 0xFF
    if voice.loop_count:
        voice.pos = voice.loop_to


def CmdEnvelope(module: Module, voice: Voice) -> None:
    """$86: start and sustain level, 4 × a nibble each; attack and decay
    ticks, a nibble each; the start phase."""
    env = voice.envelope
    levels, speeds = arg(voice), arg(voice)
    env.start, env.sustain = (levels >> 4) * 4, (levels & 0x0F) * 4
    env.attack_ticks, env.decay_ticks = speeds >> 4, speeds & 0x0F
    env.start_phase = arg(voice)


def CmdPortamento(module: Module, voice: Voice) -> None:
    """$87 semitones per tick; 0 off. Later notes become targets."""
    voice.glide = arg(voice)


def CmdTrill(module: Module, voice: Voice) -> None:
    """$88 interval, upper ticks, lower ticks. A two-note trill; an
    arpeggio is written as track notes instead."""
    voice.trill.interval = arg(voice)
    voice.trill.upper_ticks = arg(voice)
    voice.trill.lower_ticks = arg(voice)


def CmdVibrato(module: Module, voice: Voice) -> None:
    """$89 delay, step, half cycle, first direction. It starts at the
    next note."""
    vibrato = voice.vibrato
    vibrato.delay, vibrato.step = arg(voice), arg(voice)
    vibrato.half, vibrato.first_up = arg(voice), arg(voice)


def CmdTranspose(module: Module, voice: Voice) -> None:
    """$8a semitones."""
    voice.transpose = arg(voice)


def CmdFixedLength(module: Module, voice: Voice) -> None:
    """$8b ticks. Notes then carry no length byte; 0 turns it off."""
    voice.fixed_length = arg(voice)


def CmdEnvelopeRestart(module: Module, voice: Voice) -> None:
    """$8c on or off. Off: a note keeps the running envelope."""
    voice.envelope.restart = bool(arg(voice))


def CmdFlags(module: Module, voice: Voice) -> None:
    """$8d: bits 0-5 second sample, bit 6 chain, bit 7 gate off."""
    voice.flags = arg(voice)


def CmdPulseSpeed(module: Module, voice: Voice) -> None:
    """$8e ticks per pulse step; resets the sweep."""
    voice.pulse.speed = arg(voice)
    ResetPulse(voice)


def CmdEnd(module: Module, voice: Voice) -> None:
    """$8f. The voice stops: DMA off, volume 0."""
    voice.active = False
    voice.channel.disable()
    voice.channel.set_volume(0)


def CmdEnvelopeStep(module: Module, voice: Voice) -> None:
    """$90 step."""
    voice.envelope.step = arg(voice)


def CmdNoTranspose(module: Module, voice: Voice) -> None:
    """$91. The next note ignores the transpose."""
    voice.skip_transpose = True


def CmdJump(module: Module, voice: Voice) -> None:
    """$92 address."""
    voice.pos = address(module, voice)


def ResetPulse(voice: Voice) -> None:
    """Restarts the sweep at index 7, widening. It writes a fresh pulse
    at +2 to +$21, but the played wave starts at +$32. So the wave that
    plays is not reset (guess: $2 is a typo for $32)."""
    voice.pulse.count, voice.pulse.index = voice.pulse.speed, PULSE_RESET
    voice.pulse.narrowing = False
    if voice.sample is not None:
        voice.sample[RESET_AT : RESET_AT + len(RESET_WAVE)] = RESET_WAVE


COMMANDS: list[Command] = [
    CmdNop,  # $00 and $80
    CmdInstrument,
    CmdCall,
    CmdReturn,
    CmdLoopStart,  # $84
    CmdLoop,
    CmdEnvelope,
    CmdPortamento,
    CmdTrill,  # $88
    CmdVibrato,
    CmdTranspose,
    CmdFixedLength,
    CmdEnvelopeRestart,  # $8c
    CmdFlags,
    CmdPulseSpeed,
    CmdEnd,
    CmdEnvelopeStep,  # $90
    CmdNoTranspose,
    CmdJump,
]  # CommandTable


# --- Helpers -----------------------------------------------------------


def set_note(voice: Voice, note: int) -> None:
    voice.note = note & 0xFF
    voice.period = note_period(voice.note)
    voice.channel.period = voice.period


PERIODS = (  # Periodes: 97 notes, 12 per octave
    *(3822, 3608, 3405, 3214, 3034, 2863, 2703, 2551, 2408, 2273, 2145, 2025),
    *(1911, 1804, 1703, 1607, 1517, 1432, 1351, 1276, 1204, 1136, 1073, 1012),
    *(956, 902, 851, 804, 758, 716, 676, 638, 602, 568, 536, 506),
    *(478, 451, 426, 402, 379, 358, 338, 319, 301, 284, 268, 253),
    *(239, 225, 213, 201, 190, 179, 169, 159, 150, 142, 134, 127),
    *(119, 113, 106, 100, 95, 89, 84, 80, 75, 71, 67, 63),
    *(60, 56, 53, 50, 47, 45, 42, 40, 38, 36, 34, 32),
    *(30, 28, 27, 25, 24, 22, 21, 20, 19, 18, 17, 16, 8),
)  # from index 60, below paula.MIN_PERIOD: faster than DMA can fetch


def note_period(note: int) -> int:
    """Notes above 96 read past the table (not modelled)."""
    return PERIODS[note]


def address(module: Module, voice: Voice) -> int:
    """A long at the next even position, relocated: an offset into the
    module's bytes."""
    voice.pos += voice.pos & 1
    value = int.from_bytes(voice.track[voice.pos : voice.pos + 4], "big")
    voice.pos += 4
    return value - module.origin


def write_wave(sample: bytearray, index: int, value: int) -> None:
    """One byte of the played wave; every voice on the instrument hears it."""
    sample[SAMPLE_DATA + index] = value


def playable(sample: bytearray) -> paula.Sample:
    """The word at +0 is the length in words; the bytes start at +$32.
    The model's Paula copies them; the real one reads the live bytes."""
    words = int.from_bytes(sample[0:2], "big")
    return paula.Sample(bytes(sample[SAMPLE_DATA : SAMPLE_DATA + 2 * words]))
