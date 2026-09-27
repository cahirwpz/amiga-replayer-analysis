"""Mugician II's replay: Mugician II_v8.asm, Wanted Team's adaptation
(V1.7, 2014) of Reinier van Vliet's player from the game Clock Wiser.

Card: players/MugicianII.md. Level 2: the control flow runs. Each
CamelCase function is a new name in data/annot/MugicianII.yaml; each
CamelCase class is in its `types:`. Comments name the voice fields by
their offsets in Voices.

Seven voices. Voices 0-2 play Paula channels 3, 1 and 2. Voices 3-4-5-6
are mixed into channel 0; they play samples only. Each instrument reads
128-byte waves: one to play, one as its volume curve, one as its
vibrato. An effect rewrites the played wave in place.

Wanted Team changed three things, as their comments say: channel 0
mixes, not channel 3; the mix rate is set by the user; and the mix loop
is new, 211 cycles per byte instead of the original's 272. DeliTracker's
hooks (ChangeVolume, SetVol, SetAdr, SetLen, PATINFO) are left out.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from hardware import paula
from hardware.amiga import Amiga, Priority

CHANNEL_VOICES = 3
MIXED_VOICES = 4
CHANNEL_OF_VOICE = (3, 1, 2)  # Play: voices 0-2
MIX_CHANNEL = 0
POSITION_SIZE = 8  # 4 entries: pattern, transpose
SUBSONGS = 8
SUBSONG_SIZE = 16  # ?, restart, speed, length, 12-byte name
INSTRUMENT_SIZE = 16
WAVE_SIZE = 128
SAMPLE_HEADER = 32  # start, end, loop start: offsets in the sample data
PATTERN_SIZE = 256  # 64 rows of 4 bytes: note, instrument, effect, argument
ROWS = 64
ARPEGGIO_SIZE = 32  # 8 tables
FIRST_SAMPLE = 0x20  # an instrument wave from $20 up is a sample
COMMAND_BASE = 0x3E  # an effect byte from $40 up: command = byte - $3e
VOLUME_LOOPS = 0x02  # instrument byte 15
EFFECT_SLOTS = 4  # instruments EffectDoneList checks per tick

# Commands, voice byte 15. Command 1: effect byte below $40, a slide target
SLIDE, KEEP_EFFECT, KEEP_VOLUME, KEEP_BOTH = 1, 2, 3, 4
PATTERN_LENGTH, SPEED, FILTER_ON, FILTER_OFF, FILTER_FLIP = 5, 6, 7, 8, 9
LEGATO, ARPEGGIO, PORTAMENTO, SWING = 10, 11, 12, 13

MIX_PERIODS = (  # PeriodsTable: channel 0's period for 1..29 kHz
    *(0, 3580, 1790, 1193, 895, 716, 597, 511, 447, 398, 358, 325, 298),
    *(275, 256, 239, 224, 211, 199, 188, 179, 170, 163, 156, 149, 143, 138),
    *(133, 128, 121),
)
DEFAULT_RATE = 16  # kHz
MIX_CLOCK = 71591  # InitData: bytes per tick = this / period, NTSC-based
MIX_CYCLES = 211  # 68000 cycles per mixed byte; the original took 272
CLIP_EDGE = 384  # Tables: 384 × -128, a 256-byte ramp, 384 × +127

TUNINGS = 16
BELOW = 7  # NotePeriods entries before note 0
PERIODS_0 = (  # NotePeriods, tuning 0: notes -7..56
    *(4825, 4554, 4299, 4057, 3830, 3615, 3412),
    *(3220, 3040, 2869, 2708, 2556, 2412, 2277, 2149, 2029, 1915, 1807, 1706),
    *(1610, 1520, 1434, 1354, 1278, 1206, 1139, 1075, 1014, 957, 904, 853),
    *(805, 760, 717, 677, 639, 603, 569, 537, 507, 479, 452, 426),
    *(403, 380, 359, 338, 319, 302, 285, 269, 254, 239, 226, 213),
    *(201, 190, 179, 169, 160, 151, 142, 134, 127),
)


# --- What the composer edits -------------------------------------------


@dataclass
class Subsong:  # SubsongHeader: 16 bytes
    restart: int  # byte 1: the position after the last
    speed: int  # byte 2: two nibbles, see SwingSpeeds
    length: int  # byte 3: positions
    positions: bytes  # 8 bytes per position


@dataclass
class Instrument:  # InstrumentTable: 16 bytes; the replay writes 4 and 6
    wave: int  # 0: a wave, or $20 + a sample number
    length: int  # 1: words played, and the effect's range
    volume_wave: int  # 2: its bytes are the volume curve
    volume_speed: int  # 3: ticks per volume step
    arpeggio: int  # 4: table 1-7; 0 off
    vibrato_wave: int  # 5: its bytes are pitch offsets; 0 off
    effect_step: int  # 6: shared by all voices on this instrument
    vibrato_delay: int  # 7
    tuning: int  # 8: which of 16 period tables
    vibrato_loop: int  # 9: the vibrato's loop start
    effect: int  # 11: 0-15
    wave_a: int  # 12: copied over the played wave at note start
    wave_b: int  # 13: a second wave, or a number
    effect_speed: int  # 14: ticks between effect steps
    flags: int  # 15: bit 1, the volume curve loops


@dataclass
class SampleHeader:  # SampleTable: 32 bytes
    start: int
    end: int
    loop: int  # 0: no loop


@dataclass
class Score:  # ModulePtr, after LoadModule
    subsongs: list[Subsong]
    instruments: list[Instrument]
    waves: bytearray  # WaveTable: effects write into it
    samples: list[SampleHeader]
    patterns: bytes  # PatternTable
    sample_data: bytes  # SampleData
    arpeggios: bytes  # ArpeggioTable: zero without the header flag


# --- Voice and mixer state ---------------------------------------------


@dataclass
class Voice:  # Voices: 48 bytes per voice
    number: int
    channel: paula.Channel | None  # None: FakeRegisters, for a mixed voice
    pattern: int = 0  # 3
    instrument: int = 0  # 5
    note: int = 0  # 7
    transpose: int = 0  # 9: signed
    command: int = 0  # 15: lasts until the next note
    arg: int = 0  # 13
    target_note: int = 0  # 11
    target: int = 0  # 42: the slide's target period
    slide: int = 0  # 44: added to the period
    period: int = 0  # 16
    volume: int = 0  # 36
    volume_pos: int = 0  # 22
    volume_counter: int = 0  # 24; 0: the curve has stopped
    arpeggio_pos: int = 0  # 26
    vibrato_delay: int = 0  # 29
    vibrato_pos: int = 0  # 30
    effect_delay: int = 0  # 41
    sample: SampleHeader | None = None  # 32
    loop_pending: bool = False  # 20: write the loop at the next tick


@dataclass
class MixedVoice:  # MixPointers, MixEnds, MixLoopLengths, MixStopped
    pointer: int = 0  # into the sample data
    end: int = 0
    loop_length: int = 0  # 0: no loop
    stopped: bool = True  # plays at volume 0
    step: int = 0  # MixSteps: 8.8 bytes per mixed byte
    period: int = 0  # the voice period the step was made for


@dataclass
class Module:  # SongState: TickCounter, NewPosition, NewRow and the rest
    score: Score
    amiga: Amiga
    subsong: int = 0  # SubsongNumber: voices 3-6 read the next one's positions
    voices: list[Voice] = field(default_factory=list)
    mixed: list[MixedVoice] = field(default_factory=list)
    counter: int = 0  # TickCounter
    new_position: bool = True  # NewPosition
    new_row: bool = True  # NewRow
    position: int = 0  # CurrentPos
    row: int = 0  # RowIndex
    speeds: int = 0x55  # SpeedPair: two nibbles, swapped at each row
    pattern_length: int = ROWS  # PatternLength
    filter: bool = False
    effects_done: list[int] = field(default_factory=list)  # EffectDoneList
    rate: int = DEFAULT_RATE
    mix_period: int = 0  # MixPeriod
    mix_bytes: int = 0  # 2 × MixLength
    buffers: list[bytearray] = field(default_factory=list)  # PlayBuffer, NextBuffer
    volume_tables: list[bytes] = field(default_factory=list)  # VolumeTables
    clip: bytes = b""  # Tables


def signed(byte: int) -> int:
    return byte - 256 if byte & 0x80 else byte


def period_of(tuning: int, index: int) -> int:
    """NotePeriods: 16 tunings of 64 words. Tuning t is 1/16 semitone per
    step lower; the model scales tuning 0, within 1 of the listing's
    table. An index past 56 reads the next tuning's low notes."""
    tuning, index = divmod(tuning * 64 + index + BELOW, 64)
    return round(PERIODS_0[index] * 2 ** (tuning / (12 * TUNINGS)))


def instrument(module: Module, voice: Voice) -> Instrument:
    return module.score.instruments[voice.instrument]


def wave_at(number: int) -> int:
    return number * WAVE_SIZE


def new_module(score: Score, amiga: Amiga, subsong: int = 0) -> Module:
    """Channel 0's audio interrupt runs Interrupt: the mixer clocks the
    tick."""
    module = Module(score, amiga, subsong)
    channels = amiga.paula.channels
    module.voices = [
        Voice(n, channels[CHANNEL_OF_VOICE[n]]) for n in range(CHANNEL_VOICES)
    ]
    module.voices += [Voice(CHANNEL_VOICES + n, None) for n in range(MIXED_VOICES)]
    module.mixed = [MixedVoice() for _ in range(MIXED_VOICES)]
    BuildMixTables(module)
    InitSong(module)
    mix = channels[MIX_CHANNEL]
    mix.on_irq(lambda channel: Interrupt(module))
    mix.play(paula.Sample(bytes(module.buffers[0][: module.mix_bytes])))
    return module


def LoadModule(data: bytes) -> Score:
    """Header: pattern count, 8 position counts, instrument, wave and
    sample counts, sample data size, 8 subsong headers. Then positions,
    instruments, waves, sample headers, patterns, sample data, and the
    arpeggio tables if the word at 24 is set."""

    def long(at: int) -> int:
        return int.from_bytes(data[at : at + 4], "big")

    def word(at: int) -> int:
        return int.from_bytes(data[at : at + 2], "big")

    at = 76 + SUBSONGS * SUBSONG_SIZE
    subsongs = []
    for n in range(SUBSONGS):
        count = long(28 + 4 * n)
        header = data[76 + SUBSONG_SIZE * n : 76 + SUBSONG_SIZE * (n + 1)]
        positions = data[at : at + count * POSITION_SIZE]
        subsongs.append(Subsong(header[1], header[2], header[3], positions))
        at += count * POSITION_SIZE
    instruments = []
    for n in range(long(60)):
        b = data[at + INSTRUMENT_SIZE * n : at + INSTRUMENT_SIZE * (n + 1)]
        instruments.append(
            Instrument(*b[0:10], *b[11:16])  # byte 10 is unused
        )
    at += long(60) * INSTRUMENT_SIZE
    waves = bytearray(data[at : at + long(64) * WAVE_SIZE])
    at += long(64) * WAVE_SIZE
    samples = []
    for n in range(long(68)):
        h = at + SAMPLE_HEADER * n
        samples.append(SampleHeader(long(h), long(h + 4), long(h + 8)))
    at += long(68) * SAMPLE_HEADER
    patterns = data[at : at + word(26) * PATTERN_SIZE]
    at += word(26) * PATTERN_SIZE
    sample_data = data[at : at + long(72)]
    at += long(72)
    arpeggios = data[at : at + 8 * ARPEGGIO_SIZE] if word(24) else bytes(256)
    return Score(
        subsongs, instruments, waves, samples, patterns, sample_data, arpeggios
    )


def InitSong(module: Module) -> None:
    """The speed byte is the first counter; both nibbles of its low
    nibble make the speed pair. The mixer runs at `rate` kHz."""
    subsong = module.score.subsongs[module.subsong]
    module.counter = subsong.speed
    module.speeds = (subsong.speed & 0x0F) * 0x11
    module.pattern_length = ROWS
    module.position = module.row = 0
    module.new_position = module.new_row = True
    module.mix_period = MIX_PERIODS[module.rate]
    module.mix_bytes = 2 * ((MIX_CLOCK // module.mix_period + 1) >> 1)
    module.buffers = [bytearray(module.mix_bytes), bytearray(module.mix_bytes)]
    mix = module.amiga.paula.channels[MIX_CHANNEL]
    mix.period = module.mix_period
    mix.set_volume(64)


# --- Tick ---------------------------------------------------------------


def Interrupt(module: Module) -> None:
    """Channel 0 has just started the last buffer. The code queues the
    other buffer, then Play mixes into it, so it plays after this one.
    The model's Paula copies, so Play queues after the mix."""
    Play(module)


def Play(module: Module) -> None:
    """Loops, rows, each voice's tick, the mix, then the tick counter.
    DMA goes on after the mix, which takes about half the tick: that is
    the wait after DMA off."""
    module.effects_done = []
    WriteLoops(module)
    subsongs = module.score.subsongs
    for voice in module.voices[:CHANNEL_VOICES]:
        ReadRow(module, voice, subsongs[module.subsong].positions, voice.number)
    following = subsongs[(module.subsong + 1) % SUBSONGS].positions
    for n, voice in enumerate(module.voices[CHANNEL_VOICES:]):
        started = ReadRow(module, voice, following, n)
        if started is not None:
            mixed = module.mixed[n]
            mixed.pointer, mixed.end = started.start, started.end
            mixed.loop_length = started.end - started.loop if started.loop else 0
            mixed.stopped = False
    for voice in module.voices:
        VoiceTick(module, voice)
    buffer = MixVoices(module)
    mix = module.amiga.paula.channels[MIX_CHANNEL]
    mix.queue(paula.Sample(bytes(buffer)))
    NextTick(module)
    mix_cck = module.mix_bytes * MIX_CYCLES // 2

    def dma_on() -> None:
        for voice in module.voices[:CHANNEL_VOICES]:
            assert voice.channel is not None
            voice.channel.enable()

    module.amiga.after(mix_cck, Priority.CPU, dma_on)


def NextTick(module: Module) -> None:
    """At 0 the counter reloads from the speed pair's low nibble, and the
    nibbles swap: rows alternate between two lengths. The next tick then
    reads a row. After the pattern length, or 64 rows, the next
    position."""
    module.new_position = module.new_row = False
    module.counter = (module.counter - 1) & 0xFFFF
    if module.counter:
        return
    SwingSpeeds(module)
    module.new_row = True
    module.row += 1
    if module.row not in (ROWS, module.pattern_length):
        return
    module.row = 0
    module.new_position = True
    module.position += 1
    subsong = module.score.subsongs[module.subsong]
    if module.position == subsong.length:
        module.position = subsong.restart  # SongEnd tells the host


def SwingSpeeds(module: Module) -> None:
    module.counter = module.speeds & 0x0F
    module.speeds = ((module.speeds & 0x0F) << 4) | (module.speeds >> 4)


def WriteLoops(module: Module) -> None:
    """A tick after a sample starts on voices 0-2, its loop goes to
    AUDxLC and AUDxLEN. Without a loop, a 2-word silent sample."""
    data = module.score.sample_data
    for voice in module.voices[:CHANNEL_VOICES]:
        if not voice.loop_pending:
            continue
        voice.loop_pending = False
        sample = voice.sample
        assert voice.channel is not None and sample is not None
        if sample.loop:
            voice.channel.queue(paula.Sample(data[sample.loop : sample.end]))
        else:
            voice.channel.queue(paula.Sample(bytes(4)))  # EmptySample


# --- Rows ---------------------------------------------------------------


def ReadRow(
    module: Module, voice: Voice, positions: bytes, entry: int
) -> SampleHeader | None:
    """A row without a note only reruns the voice's last command. A
    note sets the command: an effect byte below $40 is a slide target
    note, others are byte - $3e. Command 12 keeps the note and makes the
    row's note the target. Returns the sample a mixed voice starts."""
    if module.new_position:
        at = module.position * POSITION_SIZE + 2 * entry
        voice.pattern, voice.transpose = positions[at], signed(positions[at + 1])
    if not module.new_row:
        RowCommands(module, voice)
        return None
    at = voice.pattern * PATTERN_SIZE + 4 * module.row
    note, number, effect, arg = module.score.patterns[at : at + 4]
    if not note:
        RowCommands(module, voice)
        return None
    if effect != COMMAND_BASE + PORTAMENTO:
        voice.note = note
        if number:
            voice.instrument = number - 1
    voice.instrument &= 0x3F
    voice.command = effect - COMMAND_BASE if effect >= 0x40 else SLIDE
    voice.arg = arg
    inst = instrument(module, voice)
    if voice.command == PORTAMENTO:
        voice.target_note = note
    else:
        voice.target_note = effect
    if voice.command in (SLIDE, PORTAMENTO):
        voice.target = period_of(inst.tuning, voice.target_note + voice.transpose)
    if voice.command == ARPEGGIO:
        inst.arpeggio = arg & 7
    started = None
    if voice.command != PORTAMENTO:
        if inst.wave >= FIRST_SAMPLE:
            started = StartSample(module, voice, inst)
        else:
            StartWave(module, voice, inst)
    RestartLists(module, voice, inst)
    RowCommands(module, voice)
    return started


def StartWave(module: Module, voice: Voice, inst: Instrument) -> None:
    """The wave goes to AUDxLC. DMA off, except for command 10: then
    the new wave follows the old one without a restart. Unless the
    command is 2 or 4, wave A is copied over the played wave and the
    effect restarts. A mixed voice writes FakeRegisters: its sample plays
    on."""
    if voice.channel is not None:
        at = wave_at(inst.wave)
        data = module.score.waves[at : at + 2 * inst.length]
        voice.channel.queue(paula.Sample(bytes(data)))
        if voice.command != LEGATO:
            voice.channel.disable()
    if inst.effect and voice.command not in (KEEP_EFFECT, KEEP_BOTH):
        CopyWaveA(module, voice, inst)


def CopyWaveA(module: Module, voice: Voice, inst: Instrument) -> None:
    waves = module.score.waves
    source = wave_at(inst.wave_a)
    waves[wave_at(inst.wave) : wave_at(inst.wave) + WAVE_SIZE] = waves[
        source : source + WAVE_SIZE
    ]
    inst.effect_step = 0
    voice.effect_delay = inst.effect_speed


def StartSample(module: Module, voice: Voice, inst: Instrument) -> SampleHeader | None:
    """Voices 0-2: the sample goes to AUDxLC, DMA off; its loop follows
    at the next tick. Voices 3-6: Play hands it to the mixer."""
    sample = module.score.samples[inst.wave - FIRST_SAMPLE]
    voice.sample = sample
    if voice.channel is None:
        return sample
    data = module.score.sample_data[sample.start : sample.end]
    voice.channel.queue(paula.Sample(data))
    voice.channel.disable()
    voice.loop_pending = True
    return None


def RestartLists(module: Module, voice: Voice, inst: Instrument) -> None:
    """Unless the command is 3, 4 or 12, the volume curve restarts. Slide,
    vibrato and arpeggio always restart."""
    if voice.command not in (KEEP_VOLUME, KEEP_BOTH, PORTAMENTO):
        voice.volume_counter, voice.volume_pos = 1, 0
    voice.slide = 0
    voice.vibrato_delay = inst.vibrato_delay
    voice.vibrato_pos = voice.arpeggio_pos = 0


def RowCommands(module: Module, voice: Voice) -> None:
    """Commands 5-8 and 13 act at each row, with or without a note."""
    if voice.command == PATTERN_LENGTH:
        CmdPatternLength(module, voice.arg)
    elif voice.command == SPEED:
        CmdSpeed(module, voice.arg)
    elif voice.command == FILTER_ON:
        module.filter = True
    elif voice.command == FILTER_OFF:
        module.filter = False
    elif voice.command == SWING:
        CmdSwing(module, voice)


def CmdPatternLength(module: Module, arg: int) -> None:
    if 0 < arg <= ROWS:
        module.pattern_length = arg


def CmdSpeed(module: Module, arg: int) -> None:
    """Both nibbles: an even speed."""
    if arg & 0x0F:
        module.speeds = (arg & 0x0F) * 0x11


def CmdSwing(module: Module, voice: Voice) -> None:
    """Two speeds, one per nibble; rows alternate between them. The
    command clears itself."""
    voice.command = 0
    if voice.arg & 0x0F and voice.arg & 0xF0:
        module.speeds = voice.arg


# --- Voice tick ---------------------------------------------------------


def VoiceTick(module: Module, voice: Voice) -> None:
    """Command 9 flips the filter every tick. Then the effect, the
    volume curve, the arpeggio, the slide and the vibrato."""
    if voice.command == FILTER_FLIP:
        module.filter = not module.filter
    inst = instrument(module, voice)
    RunEffect(module, voice, inst)
    VolumeFromWave(module, voice, inst)
    ArpeggioStep(module, voice, inst)


def RunEffect(module: Module, voice: Voice, inst: Instrument) -> None:
    """Only on a wave, never a sample. Voices share the instrument's
    effect: it runs once per tick, for the first voice that plays it.
    That voice's delay counter paces it. The Flod port has the same 15
    effects but runs them only in 4-voice songs; this code always runs
    them, as the original's skip flag is a constant 0."""
    if not inst.effect or inst.wave >= FIRST_SAMPLE:
        return
    if not EffectOncePerTick(module, voice.instrument + 1):
        return
    EffectDelay(module, voice, inst)


def EffectOncePerTick(module: Module, number: int) -> bool:
    """Only 4 slots are checked; a fifth instrument could run twice."""
    if number in module.effects_done[:EFFECT_SLOTS]:
        return False
    module.effects_done.append(number)
    return True


def EffectDelay(module: Module, voice: Voice, inst: Instrument) -> None:
    if voice.effect_delay:
        voice.effect_delay -= 1
        return
    voice.effect_delay = inst.effect_speed
    EFFECTS[inst.effect](module.score.waves, inst)


def VolumeFromWave(module: Module, voice: Voice, inst: Instrument) -> None:
    """Every `volume_speed` ticks, the next byte of the volume wave:
    volume = (127 - byte) / 4, so -128 is loud and +127 silent. The first
    step reads byte 1. After byte 127 the curve loops if flag bit 1 is
    set; else the volume holds."""
    if not voice.volume_counter:
        return
    voice.volume_counter -= 1
    if voice.volume_counter:
        return
    voice.volume_counter = inst.volume_speed
    voice.volume_pos = (voice.volume_pos + 1) & 0x7F
    if not voice.volume_pos and not inst.flags & VOLUME_LOOPS:
        voice.volume_counter = 0
        return
    byte = module.score.waves[wave_at(inst.volume_wave) + voice.volume_pos]
    voice.volume = (-(byte + 0x81) & 0xFF) >> 2
    if voice.channel is not None:
        voice.channel.set_volume(voice.volume)


def ArpeggioStep(module: Module, voice: Voice, inst: Instrument) -> None:
    """Every tick, the next of 32 note offsets, if the instrument names
    a table. Then the transpose, and the period from the instrument's
    tuning."""
    note = voice.note
    if inst.arpeggio:
        at = inst.arpeggio * ARPEGGIO_SIZE + voice.arpeggio_pos
        note = (note + module.score.arpeggios[at]) & 0xFF
        voice.arpeggio_pos = (voice.arpeggio_pos + 1) % ARPEGGIO_SIZE
    base = period_of(inst.tuning, note + voice.transpose)
    voice.period = base
    if voice.command in (SLIDE, PORTAMENTO):
        Portamento(voice, base)
    VibratoFromWave(module, voice, inst)
    if voice.channel is not None:
        voice.channel.period = voice.period


def Portamento(voice: Voice, base: int) -> None:
    """The signed argument moves the slide each tick; positive raises
    the pitch. Past the target, the slide is set to it and the argument
    cleared. The period that overshot plays this tick."""
    step = -signed(voice.arg)
    voice.slide = (voice.slide + step) & 0xFFFF
    period = voice.period = (base + voice.slide) & 0xFFFF
    if not voice.arg:
        return
    passed = period <= voice.target if step < 0 else period >= voice.target
    if passed:
        voice.slide = (voice.target - base) & 0xFFFF
        voice.arg = 0


def VibratoFromWave(module: Module, voice: Voice, inst: Instrument) -> None:
    """After the delay, each tick subtracts the next byte of the
    vibrato wave from the period. After byte 127 it loops to byte
    `vibrato_loop`, unmasked: from 128 up it reads the next wave."""
    if not inst.vibrato_wave:
        return
    if voice.vibrato_delay:
        voice.vibrato_delay -= 1
        return
    at = wave_at(inst.vibrato_wave) + voice.vibrato_pos
    voice.vibrato_pos = (voice.vibrato_pos + 1) & 0x7F
    if not voice.vibrato_pos:
        voice.vibrato_pos = inst.vibrato_loop
    waves = module.score.waves
    offset = signed(waves[at]) if at < len(waves) else 0
    voice.period = (voice.period - offset) & 0xFFFF


# --- Wave effects -------------------------------------------------------
# Each rewrites the played wave, `inst.wave`. "Over the length" means
# 2 × `length` bytes; the others work on all 128.


def wave(waves: bytearray, number: int) -> memoryview:
    return memoryview(waves)[wave_at(number) : wave_at(number) + WAVE_SIZE]


def span(inst: Instrument) -> int:
    return (2 * inst.length) & 0xFF


def NoEffect(waves: bytearray, inst: Instrument) -> None:
    """Effect 0 and 16-31."""


def SmoothForward(waves: bytearray, inst: Instrument) -> None:
    """Each byte becomes the mean of itself and the next.
    Likely sound (inference): duller, step by step."""
    w = wave(waves, inst.wave)
    for n in range(WAVE_SIZE - 1):
        w[n] = ((signed(w[n]) + signed(w[n + 1])) >> 1) & 0xFF


def PhaseWithB(waves: bytearray, inst: Instrument) -> None:
    """Over the length: the mean of wave A and wave B, B read from an
    offset that moves by one per step.
    Likely sound (inference): phasing."""
    out, a, b = (
        wave(waves, inst.wave),
        wave(waves, inst.wave_a),
        wave(waves, inst.wave_b),
    )
    offset = inst.effect_step
    inst.effect_step = (inst.effect_step + 1) & 0x7F
    for n in range(span(inst)):
        out[n] = ((signed(a[n]) + signed(b[(offset + n) & 0x7F])) >> 1) & 0xFF


def RotateLeft(waves: bytearray, inst: Instrument) -> None:
    """Rotate left by one byte.
    Likely sound (inference): slight detune."""
    w = wave(waves, inst.wave)
    w[:] = bytes(w[1:]) + bytes(w[:1])


def RotateRight(waves: bytearray, inst: Instrument) -> None:
    """Rotate right by one byte.
    Likely sound (inference): slight detune."""
    w = wave(waves, inst.wave)
    w[:] = bytes(w[-1:]) + bytes(w[:-1])


def OctaveUp(waves: bytearray, inst: Instrument) -> None:
    """Every second byte, twice: one octave up.
    Likely sound (inference): one octave up."""
    w = wave(waves, inst.wave)
    half = bytes(w[0::2])
    w[:] = half + half


def OctaveDown(waves: bytearray, inst: Instrument) -> None:
    """Each byte of the first half, twice: one octave down.
    Likely sound (inference): one octave down."""
    w = wave(waves, inst.wave)
    w[:] = bytes(b for byte in bytes(w[:64]) for b in (byte, byte))


def NegateSweep(waves: bytearray, inst: Instrument) -> None:
    """Negate the byte at the step; the step walks the length.
    Likely sound (inference): a changing pulse width."""
    w = wave(waves, inst.wave)
    w[inst.effect_step & 0x7F] = -w[inst.effect_step & 0x7F] & 0xFF
    step_over_length(inst)


def step_over_length(inst: Instrument) -> None:
    inst.effect_step = (inst.effect_step + 1) & 0xFF
    if inst.effect_step >= span(inst):
        inst.effect_step = 0


def AddRamp(waves: bytearray, inst: Instrument) -> None:
    """Over the length, add a ramp from 3; its slope is wave B's byte at
    the step.
    Likely sound (inference): growing brightness."""
    w, b = wave(waves, inst.wave), wave(waves, inst.wave_b)
    inst.effect_step = (inst.effect_step + 1) & 0x7F
    slope, add = b[inst.effect_step], 3
    for n in range(span(inst)):
        w[n] = (w[n] + add) & 0xFF
        add = (add + slope) & 0xFF


def AddWaveB(waves: bytearray, inst: Instrument) -> None:
    """Over the length, add wave B; sums wrap.
    Likely sound (inference): a changing timbre."""
    w, b = wave(waves, inst.wave), wave(waves, inst.wave_b)
    for n in range(span(inst)):
        w[n] = (w[n] + b[n]) & 0xFF


def SmoothWeighted(waves: bytearray, inst: Instrument) -> None:
    """Bytes 1-126: 3/4 of the new byte before plus 1/4 of the byte
    after.
    Likely sound (inference): duller, faster."""
    w = wave(waves, inst.wave)
    for n in range(WAVE_SIZE - 2):
        w[n + 1] = ((3 * signed(w[n]) + signed(w[n + 2])) >> 2) & 0xFF


def crossfade(waves: bytearray, inst: Instrument, steps: int, shift: int) -> None:
    out, a, b = (
        wave(waves, inst.wave),
        wave(waves, inst.wave_a),
        wave(waves, inst.wave_b),
    )
    inst.effect_step = (inst.effect_step + 1) % steps
    half = steps // 2
    step = inst.effect_step
    weight = step if step < half else steps - 1 - step
    for n in range(span(inst)):
        mix = signed(a[n]) * weight + signed(b[n]) * (half - 1 - weight)
        out[n] = (mix >> shift) & 0xFF


def CrossfadeSlow(waves: bytearray, inst: Instrument) -> None:
    """Over the length: crossfade wave B to wave A and back, over 128
    steps.
    Likely sound (inference): a slow morph."""
    crossfade(waves, inst, 128, 6)


def CrossfadeFast(waves: bytearray, inst: Instrument) -> None:
    """The same crossfade over 32 steps.
    Likely sound (inference): a fast morph."""
    crossfade(waves, inst, 32, 4)


def SmoothNeighbours(waves: bytearray, inst: Instrument) -> None:
    """Bytes 1-126: the mean of the new byte before and the byte
    after.
    Likely sound (inference): duller."""
    w = wave(waves, inst.wave)
    for n in range(WAVE_SIZE - 2):
        w[n + 1] = ((signed(w[n]) + signed(w[n + 2])) >> 1) & 0xFF


def NegatePair(waves: bytearray, inst: Instrument) -> None:
    """Negate two bytes, `wave_b` apart, masked by the length - 1; the
    pair walks the length.
    Likely sound (inference): a pulse-width sweep."""
    w = wave(waves, inst.wave)
    first = inst.effect_step & 0x7F
    w[first] = -w[first] & 0xFF
    second = (inst.effect_step + inst.wave_b) & (span(inst) - 1) & 0x7F
    w[second] = -w[second] & 0xFF
    step_over_length(inst)


def SmoothThenOctave(waves: bytearray, inst: Instrument) -> None:
    """Effect 15: SmoothForward each step; every `wave_b` steps, OctaveUp.
    Likely sound (inference): dull, then bright again."""
    SmoothForward(waves, inst)
    inst.effect_step = (inst.effect_step + 1) & 0xFF
    if inst.effect_step == inst.wave_b:
        inst.effect_step = 0
        OctaveUp(waves, inst)


EFFECTS: list[Callable[[bytearray, Instrument], None]] = [  # by effect number
    NoEffect,  # 0
    SmoothForward,  # 1
    PhaseWithB,  # 2
    RotateLeft,  # 3
    RotateRight,  # 4
    OctaveUp,  # 5
    OctaveDown,  # 6
    NegateSweep,  # 7
    AddRamp,  # 8
    AddWaveB,  # 9
    SmoothWeighted,  # 10
    CrossfadeSlow,  # 11
    CrossfadeFast,  # 12
    SmoothNeighbours,  # 13
    NegatePair,  # 14
    SmoothThenOctave,  # 15
    *[NoEffect] * 16,  # 16-31
]


# --- Mixer --------------------------------------------------------------


def MixVoices(module: Module) -> bytes:
    """Voices 3-6 into one buffer, at the mix period. Per voice, a step
    from its period, only when the period changes. A period of 0 stops
    the voice. Per byte, each voice's byte goes through the table of its
    volume; the sum goes through the clip table. Fractions restart at 0
    each tick. Sample ends are checked once per tick, after the mix."""
    module.buffers.reverse()
    buffer = module.buffers[0]
    data = module.score.sample_data
    for mixed, voice in zip(module.mixed, module.voices[CHANNEL_VOICES:]):
        if not voice.period:
            mixed.stopped, mixed.step = True, 0
        elif voice.period != mixed.period:
            mixed.period = voice.period
            mixed.step = MixStep(module.mix_period, voice.period)
    fractions = [0] * MIXED_VOICES
    for n in range(module.mix_bytes):
        total = 0
        for v, (mixed, voice) in enumerate(zip(module.mixed, module.voices[3:])):
            byte = data[mixed.pointer] if mixed.pointer < len(data) else 0
            volume = 0 if mixed.stopped else voice.volume
            total += module.volume_tables[volume][byte]
            fractions[v] += mixed.step & 0xFF
            mixed.pointer += (mixed.step >> 8) + (fractions[v] >> 8)
            fractions[v] &= 0xFF
        buffer[n] = module.clip[total]
    CheckSampleEnds(module)
    return bytes(buffer)


def MixStep(mix_period: int, period: int) -> int:
    """Mix period / voice period, as 8.8, by two divu."""
    ratio = (period << 8) // mix_period
    whole, rest = divmod(256, ratio)
    return (whole & 0xFF) << 8 | ((rest << 8) // ratio & 0xFF)


def CheckSampleEnds(module: Module) -> None:
    """At or past the end, a looped sample steps back by the loop's
    length, once; a sample without a loop stops. Within a tick, a voice
    reads on past its end."""
    for mixed in module.mixed:
        if mixed.pointer < mixed.end:
            continue
        if mixed.loop_length:
            mixed.pointer -= mixed.loop_length
        else:
            mixed.stopped = True


def BuildMixTables(module: Module) -> None:
    """64 volume tables: a byte × volume / 63, plus $80; for volumes
    1-62 a negative byte gives one less. Four sum to 0..1020 around
    512. The clip table maps the sum to a signed byte."""
    tables = []
    for volume in range(64):
        table = bytearray(256)
        for byte in range(256):
            scaled = int(signed(byte) * volume / 63)
            if 0 < volume < 63 and byte >= 0x80:
                scaled -= 1
            table[byte] = (scaled + 0x80) & 0xFF
        tables.append(bytes(table))
    module.volume_tables = tables
    ramp = bytes(range(0x80, 0x100)) + bytes(range(0x80))
    module.clip = bytes([0x80] * CLIP_EDGE) + ramp + bytes([0x7F] * CLIP_EDGE)
