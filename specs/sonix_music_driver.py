"""The Sonix Music Driver by Mark Riley: Sonix Music Driver_v1.asm,
Wanted Team's adaptation. The file holds three copies of the driver, for
SNX, TINY and SMUS scores; this spec models the SNX copy.

Card: players/SonixMusicDriver.md. Level 2: the control flow runs. Each
CamelCase function is a new name in data/annot/SonixMusicDriver.yaml;
each CamelCase class is in its `types:`. Comments name the voice fields
by their offsets in a voice record.

A score is four tracks of events: note with velocity, wait, instrument,
volume, tempo, bend. Each instrument type is a driver with two entry
points: a tick, then a register write. The synthesis driver filters its
wave through a bank of 64 low-pass copies, picked each tick by envelope
and LFO. Rates scale with the tick's length, so tempo changes them not.
The AIFF driver, the TINY and SMUS readers, sound effects that steal a
track, and DeliTracker's hooks (SetAdr, SetLen, SetPer, ChangeVolume)
are left out.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from hardware import paula
from hardware.amiga import Amiga, Priority
from hardware.clock import LINE_CCK

VOICES = 4
TRACK_END, WAIT = 0xFFFF, 0xC000  # event words; waits count & $3fff ticks
SET_INSTRUMENT, SET_VOLUME, SET_TEMPO, SET_BEND = 0x80, 0x81, 0x82, 0x83
TICK_SCALE = 0x4B0000  # SetTempo: tick length = this / tempo
DEFAULT_TEMPO = 125  # 50 Hz with DeliTracker's timer
DELI_LATCH = 14187  # DeliTracker's 50 Hz latch (guess); Clock is 125 × it
IN_TUNE = 0x80  # InstallSNX sets the tune; SNX events never change it
WAVE = 128  # a synthesis wave, and each filtered copy
FILTERS = 64
LOWEST_NOTE, TOP_NOTE = 0x24, 0x6C  # synthesis notes 36-107
SYNTH_BASE = 0xD5C8  # SynthTick: period factor for octave 0
MAX_PERIOD = 0x1AC  # OctaveShift halves the period down to this
DMA_WAIT_LINES = 9  # DMAWait, Wanted Team's: 9 line changes before DMA on

# EnvelopeSetup stages, voice field $2a
ATTACK, DECAY, SUSTAIN, RELEASE = 0, 2, 4, 6

SEMITONES = (  # SemitoneRatios: 2^(-n/12) × $8000, one octave
    *(0x8000, 0x78D1, 0x7209, 0x6BA2, 0x6598, 0x5FE4, 0x5A82),
    *(0x556E, 0x50A3, 0x4C1C, 0x47D6, 0x43CE, 0x4000),
)
FILTER_CUTOFFS = tuple(  # FilterCutoffs: from $8000, 2^(-1/9) per step
    int(0x8000 * 2 ** (-n / 9))
    for n in range(FILTERS)  # matches the listing
)
BEND_FACTORS = (  # BendFactors: 64 period factors, × 1.52 to × 0.67
    *(0xC24D, 0xBFC8, 0xBD4C, 0xBAD8, 0xB86C, 0xB608, 0xB3AC, 0xB158),
    *(0xAF0C, 0xACC7, 0xAA8A, 0xA854, 0xA626, 0xA3FF, 0xA1DF, 0x9FC6),
    *(0x9DB4, 0x9BA9, 0x99A4, 0x97A6, 0x95AF, 0x93BF, 0x91D5, 0x8FF1),
    *(0x8E13, 0x8C3C, 0x8A6B, 0x88A0, 0x86DA, 0x851B, 0x8362, 0x81AE),
    *(0x8000, 0x7E57, 0x7CB4, 0x7B16, 0x797E, 0x77EB, 0x765D, 0x74D4),
    *(0x7351, 0x71D2, 0x7059, 0x6EE4, 0x6D74, 0x6C09, 0x6AA2, 0x6941),
    *(0x67E4, 0x668B, 0x6537, 0x63E7, 0x629C, 0x6154, 0x6012, 0x5ED3),
    *(0x5D98, 0x5C62, 0x5B2F, 0x5A01, 0x58D6, 0x57B0, 0x568D, 0x556E),
)


# --- What the composer edits -------------------------------------------


@dataclass
class EnvelopeSetup:  # four levels and four rates, one per stage
    levels: tuple[int, int, int, int]  # 0-255; release's is the end level
    rates: tuple[int, int, int, int]  # bits 5-7: a shift; bits 0-4: a step


@dataclass
class SynthInstrument:  # SyntTech: the 'Synthesis' file, 502 bytes
    wave: bytes  # $24: 128 bytes
    lfo_table: bytes  # $a4: 256 bytes
    volume: int  # $1ac
    envelope_to_volume: int  # $1ae: 0 means the release cuts the note
    lfo_to_volume: int  # $1b0
    portamento: int  # $1b2: a time; scaled by the tick length
    lfo_to_pitch: int  # $1b4
    filter_base: int  # $1b6: 255 is the brightest copy
    envelope_to_filter: int  # $1b8
    lfo_to_filter: int  # $1ba
    lfo_rate: int  # $1bc
    lfo_mode: int  # $1be: 0 off; above 0 once; below 0 loops
    lfo_delay: int  # $1c0
    wave_rate: int  # $1c2: 0 plain; else BlendCopy or StretchHalves
    stretch: int  # $1c4: 0 means BlendCopy
    envelope: EnvelopeSetup  # $1c6, $1ce
    bank: bytes = b""  # 64 filtered copies of the wave, from SetFilter


@dataclass
class SampledSound:  # SSTech: a '.ss' sample with its octaves in a row
    data: bytes  # $3e onwards in the sample file
    octave_length: int  # 0: bytes of the highest octave
    loop: int  # 2: the loop start, in the same unit
    low: int  # 4: octave numbers 0-10; the sample holds low..high
    high: int  # 5
    volume: int  # $48
    vibrato_depth: int  # $5a
    vibrato_rate: int  # $5c
    vibrato_delay: int  # $5e
    envelope: EnvelopeSetup  # $4a, $52


@dataclass
class IffSound:  # IFFTech: an 8SVX file
    body: bytes
    one_shot: int  # VHDR oneShotHiSamples
    repeat: int  # VHDR repeatHiSamples
    octaves: int  # VHDR ctOctave
    shift: int  # $38: octaves InstallIFF drops so lengths stay even
    volume: int  # VHDR volume, 16.16


Instrument = SynthInstrument | SampledSound | IffSound


@dataclass
class Score:  # an SNX file
    tracks: list[bytes]  # four tracks of word events
    tempo: int  # header $12
    instruments: dict[int, Instrument]  # by the numbers events use


# --- Voice state -------------------------------------------------------


@dataclass
class SynthState:  # voice field $20 on: the synthesis driver's
    period: int = 0  # $20: 0 before the first note
    glide_steps: int = 0  # $22
    glide_delta: int = 0  # $24
    buffer: int = 0  # $26: 0 or 128, the half written this tick
    shift: int = 0  # $28: octaves the wave is decimated by
    stage: int = ATTACK  # $2a
    level: int = 0  # $2c: 16.16, 0-255
    lfo_phase: int = 0  # $30
    lfo_wait: int = 0  # $32: -1 once a one-shot LFO has ended
    lfo: int = 0  # $34: a signed table byte
    wave_phase: int = 0  # $36
    direction: int = 1  # $38: StretchHalves' sign


@dataclass
class SampleState:  # voice field $3a on: the sample drivers'
    period: int = 0
    stage: int = ATTACK
    level: int = 0
    vibrato_phase: int = 0
    vibrato_wait: int = 0
    vibrato: int = 0


@dataclass
class Voice:  # a voice record: $54 bytes
    channel: paula.Channel
    number: int
    event: int = 0  # the next event word in the track
    wait: int = 0  # ticks to the next event
    instrument: Instrument | None = None  # the track's; $80 events set it
    track_volume: int = 0xFF  # $81 events
    bend: int = 0  # $83 events: a signed byte
    request: int = 0  # 0: 0 none, 1 start, 2 release
    state: int = 0  # 1: 0 off, 1 held, 2 released
    note: int = 0  # 2
    playing: Instrument | None = None  # 4
    velocity: int = 0  # 8: 0-255
    new_note: bool = False  # 10: set DMA on at the next write
    start: bytes = b""  # 12: the sample, or this tick's wave buffer
    loop: bytes = b""  # 18
    period: int = 0  # 24
    volume: int = 0  # 26
    synth: SynthState = field(default_factory=SynthState)
    sample: SampleState = field(default_factory=SampleState)
    buffers: list[bytearray] = field(
        default_factory=lambda: [bytearray(WAVE), bytearray(WAVE)]
    )


@dataclass
class Module:  # the driver's globals, at Sonix
    score: Score
    amiga: Amiga
    voices: list[Voice] = field(default_factory=list)
    tempo: int = DEFAULT_TEMPO  # 0
    tune: int = IN_TUNE  # 2: $80 plays in tune
    tick_length: int = 0  # $32: rates scale with it
    ticks: int = 0  # 14: since the start
    master: list[int] = field(default_factory=lambda: [0xFF00] * VOICES)  # $5a
    ramp: list[int] = field(default_factory=lambda: [0] * VOICES)  # $7a
    ramp_target: list[int] = field(default_factory=lambda: [0] * VOICES)  # $6a
    dma_on: set[int] = field(default_factory=set)


def signed(byte: int) -> int:
    return byte - 256 if byte & 0x80 else byte


def word(data: bytes, at: int) -> int:
    return int.from_bytes(data[at : at + 2], "big")


def new_module(score: Score, amiga: Amiga) -> Module:
    """DeliTracker's timer runs PlaySNX. Its latch is 125 × DeliTracker's
    own latch / tempo, so tempo 125 gives 50 Hz."""
    module = Module(score, amiga)
    module.voices = [Voice(c, n) for n, c in enumerate(amiga.paula.channels)]
    for inst in score.instruments.values():
        if isinstance(inst, SynthInstrument):
            SetFilter(inst)
    amiga.timer.on_underflow = lambda: PlaySNX(module)
    PlayScore(module)
    return module


def PlayScore(module: Module) -> None:
    """Start at tick 0, at the score's tempo, voices at full volume."""
    module.ticks = 0
    module.tempo = module.score.tempo
    RestartScore(module)
    for number in range(VOICES):
        RampVolume(module, number, 0xFF, 0)


def RestartScore(module: Module) -> None:
    """Each track from its start; each voice's note released. The tempo
    stays: after a loop, the last tempo event still holds."""
    module.ticks = 0
    for voice in module.voices:
        voice.event, voice.wait = 0, 0
        voice.instrument, voice.track_volume, voice.bend = None, 0xFF, 0
        ReleaseNote(voice)


# --- Tick ---------------------------------------------------------------


def PlaySNX(module: Module) -> None:
    """Volume ramps, the tracks, then the instruments."""
    StepRamps(module)
    ReadTracks(module)
    TickInstruments(module)


def SetTempo(module: Module, tempo: int) -> None:
    """The timer's latch follows the tempo; the tick length is kept for
    the rates, so a faster tempo takes smaller steps per tick."""
    module.tempo = tempo
    module.amiga.timer.set_latch(DELI_LATCH * DEFAULT_TEMPO // tempo)
    module.tick_length = TICK_SCALE // tempo


def ReadTracks(module: Module) -> None:
    """Every tick, each track whose wait has run out reads events up to
    the next wait. When all four tracks have ended, the score restarts."""
    SetTempo(module, module.tempo)
    ended = 0
    for voice in module.voices:
        if voice.wait:
            voice.wait -= 1
            if voice.wait:
                continue
        if not ReadEvent(module, voice):
            ended += 1
    module.ticks += 1
    if ended == VOICES:
        RestartScore(module)  # SongEnd tells the host


def ReadEvent(module: Module, voice: Voice) -> bool:
    """Words: 0 is skipped; $ffff ends the track; from $c000 a wait;
    a high byte below $80 is a note with its velocity; $80-$83 set the
    instrument, volume, tempo or bend. False once the track has ended."""
    track = module.score.tracks[voice.number]
    while True:
        if voice.event + 2 > len(track):
            return False
        event = word(track, voice.event)
        if event == TRACK_END:
            return False
        voice.event += 2
        if not event:
            continue
        if event >= WAIT:
            if event & 0x3FFF:
                voice.wait = event & 0x3FFF
                return True
            continue
        kind, arg = event >> 8, event & 0xFF
        if kind < 0x80:
            NoteEvent(module, voice, kind, arg)
        elif kind == SET_INSTRUMENT:
            InstrumentEvent(module, voice, arg)
        elif kind == SET_VOLUME:
            voice.track_volume = arg
        elif kind == SET_TEMPO:
            TempoEvent(module, arg)
        elif kind == SET_BEND:
            voice.bend = signed(arg)


def NoteEvent(module: Module, voice: Voice, note: int, velocity: int) -> None:
    """Velocity 0 releases the note. Else the volume is track volume ×
    velocity, and the note plays with the track's instrument."""
    if not velocity:
        ReleaseNote(voice)
        return
    if voice.instrument is None:
        return
    volume = ((voice.track_volume + 1) * (2 * velocity + 1)) >> 8
    StartNote(voice, voice.instrument, note, volume)


def InstrumentEvent(module: Module, voice: Voice, number: int) -> None:
    voice.instrument = module.score.instruments.get(number)


def TempoEvent(module: Module, tempo: int) -> None:
    SetTempo(module, tempo)


def StartNote(voice: Voice, instrument: Instrument, note: int, volume: int) -> None:
    """A held voice of another instrument type stops first. The driver
    starts the note at its next tick."""
    if voice.state and type(voice.playing) is not type(instrument):
        StopNote(voice)
    voice.playing, voice.note, voice.velocity = instrument, note, volume & 0xFF
    voice.request = 1


def ReleaseNote(voice: Voice) -> None:
    """Only a held note has a release."""
    voice.request = 2 if voice.state == 1 else 0


def StopNote(voice: Voice) -> None:
    voice.request = 0
    if voice.state:
        voice.state = 0
        cut_channel(voice)


def cut_channel(voice: Voice) -> None:
    """DMA off, and period 2, meant to end the channel's word at once
    (guess: Paula reloads its period counter only at a word's end)."""
    voice.channel.disable()
    voice.channel.period = 2


def StepRamps(module: Module) -> None:
    """Each voice's master volume moves towards its target by its step,
    scaled by the tick length."""
    for n in range(VOICES):
        step = module.ramp[n]
        if not step:
            continue
        move = (step * module.tick_length * 2) >> 16
        now, target = module.master[n], module.ramp_target[n]
        if move >= abs(target - now):
            module.master[n], module.ramp[n] = target, 0
        else:
            module.master[n] = now + (move if target > now else -move)


def RampVolume(module: Module, number: int, volume: int, ticks: int) -> None:
    """Master volume to `volume`, over `ticks`; 0 sets it at once."""
    target = volume << 8
    if not ticks:
        module.master[number] = target
        module.ramp[number] = 0
        return
    module.ramp_target[number] = target
    module.ramp[number] = max(abs(module.master[number] - target) // ticks, 1)


# --- Instrument drivers -------------------------------------------------


def TickInstruments(module: Module) -> None:
    """Each voice with a request or a note runs its driver's tick. Then
    each playing voice writes Paula; a busy-wait of 8 lines; DMA on for
    the voices that asked."""
    for voice in module.voices:
        if not voice.request and not voice.state:
            continue
        driver = DRIVERS[type(voice.playing)] if voice.playing else None
        if driver is not None:
            driver[0](module, voice)
            if voice.request in (1, 2):
                voice.state = voice.request
        else:
            voice.state = 0
        voice.request = 0
    module.dma_on.clear()
    for voice in module.voices:
        if voice.state and voice.playing is not None:
            DRIVERS[type(voice.playing)][1](module, voice)
    starting = sorted(module.dma_on)

    def dma_on() -> None:
        for number in starting:
            module.voices[number].channel.enable()

    module.amiga.after(DMA_WAIT_LINES * LINE_CCK, Priority.CPU, dma_on)


def master_volume(module: Module, voice: Voice) -> int:
    """The master volume × the note's volume, as 0-255."""
    return (module.master[voice.number] * (voice.velocity + 1)) >> 16


def bent_period(module: Module, voice: Voice, period: int) -> int:
    """The track's bend: one of 64 factors, from × 1.52 to × 0.67."""
    if not voice.bend:
        return period
    factor = BEND_FACTORS[((voice.bend + 0x80) & 0xFF) >> 2]
    return (period * factor * 2) >> 16


def envelope_step(
    module: Module, env: EnvelopeSetup, stage: int, level: int
) -> tuple[int, int]:
    """Move the 16.16 level towards the stage's level. The step is the
    rate's low 5 bits + 33, shifted by its top 3 bits, times the tick
    length. At the target, attack and decay go to the next stage."""
    target = env.levels[stage // 2] << 16
    rate = env.rates[stage // 2]
    step = (((rate & 0x1F) + 0x21) * module.tick_length << 3) >> ((rate >> 5) ^ 7)
    if abs(target - level) <= step:
        return (stage + 2 if stage < SUSTAIN else stage), target
    return stage, level + step if target > level else level - step


# --- The synthesis driver -----------------------------------------------


def SynthTick(module: Module, voice: Voice) -> None:
    """A start sets the pitch, a glide from the last pitch, the envelope
    and the LFO. A note on a held voice keeps its envelope: legato. Then
    LFO, envelope, pitch, volume, filter and wave."""
    inst = voice.playing
    assert isinstance(inst, SynthInstrument)
    s = voice.synth
    if voice.request == 1:
        if not LOWEST_NOTE <= voice.note < TOP_NOTE:
            voice.request = 0
            if not voice.state:
                return
        else:
            SynthStart(module, voice, inst)
    elif voice.request == 2:
        s.stage = RELEASE
    Lfo(module, inst, s)
    s.stage, s.level = envelope_step(module, inst.envelope, s.stage, s.level)
    OctaveShift(module, voice, inst)
    SelectFilter(module, voice, inst)


def SynthStart(module: Module, voice: Voice, inst: SynthInstrument) -> None:
    s = voice.synth
    note = voice.note - LOWEST_NOTE
    if not voice.state:
        s.level = 0
    Legato(voice, inst)
    octave, semitone = divmod(note, 12)
    period = (SYNTH_BASE * SEMITONES[semitone]) >> (octave + 17)
    period = Portamento(module, s, inst, period)
    s.period, s.direction = period, 1
    if not inst.wave_rate:
        s.wave_phase = 0
    s.lfo_wait = 0
    if inst.lfo_mode:
        s.lfo_phase = 0
        s.lfo_wait = (((inst.lfo_delay << 16) >> 1) // module.tick_length) >> 2
        s.lfo = signed(inst.lfo_table[0])
    voice.new_note = True


def Legato(voice: Voice, inst: SynthInstrument) -> None:
    """Unless the voice is held, the envelope restarts from attack."""
    if voice.state != 1:
        voice.synth.stage = ATTACK


def Portamento(
    module: Module, s: SynthState, inst: SynthInstrument, period: int
) -> int:
    """From the last note's period, in steps over the portamento time.
    Returns where the glide starts."""
    if not s.period:
        s.glide_steps = 0
        return period
    steps = ((((inst.portamento << 16) >> 1) // module.tick_length) >> 3) + 1
    delta = int((period - s.period) / steps)
    s.glide_steps, s.glide_delta = steps, delta
    return period - delta * steps


def Lfo(module: Module, inst: SynthInstrument, s: SynthState) -> None:
    """After its delay, the phase steps by rate × tick length and picks a
    table byte. A one-shot LFO holds at the table's end."""
    if s.lfo_wait < 0:
        return
    if s.lfo_wait:
        s.lfo_wait -= 1
        return
    step = (inst.lfo_rate * module.tick_length << 6) >> 16
    phase = s.lfo_phase + step
    if inst.lfo_mode > 0 and phase >= 0xFE00:
        phase, s.lfo_wait = 0xFE00, -1
    s.lfo_phase = phase & 0xFFFF
    s.lfo = signed(inst.lfo_table[s.lfo_phase >> 8])


def OctaveShift(module: Module, voice: Voice, inst: SynthInstrument) -> None:
    """The glide steps on. The period halves until it is at most 428;
    each halving drops every second byte of the wave instead. So high
    notes play fewer bytes, never a short period."""
    s = voice.synth
    if s.glide_steps:
        s.glide_steps -= 1
        s.period += s.glide_delta
    period, shift = s.period, 5
    while period > MAX_PERIOD:
        period >>= 1
        shift -= 1
    s.shift = shift
    factor = ((s.lfo * inst.lfo_to_pitch) >> 7) - (module.tune - 0x80) + 0x1000
    voice.period = bent_period(module, voice, (period * factor) >> 12)
    volume = inst.volume
    if inst.lfo_to_volume:
        volume -= (s.lfo * inst.lfo_to_volume) >> 8
    if inst.envelope_to_volume:
        volume = (volume * (s.level >> 16)) >> 8
    elif s.stage == RELEASE:
        volume = 0
    volume = ((volume & 0xFF) + 1) * master_volume(module, voice) >> 8
    voice.volume = (volume + 1) >> 2


def SelectFilter(module: Module, voice: Voice, inst: SynthInstrument) -> None:
    """Index = inverted base - envelope × amount + LFO × amount; its top
    6 bits pick one of 64 filtered copies. The copy goes into the voice's
    other buffer, decimated by the shift, or through a wave mode."""
    s = voice.synth
    index = (inst.filter_base ^ 0xFF) - (
        ((s.level >> 16) * inst.envelope_to_filter) >> 8
    )
    index = ((index + ((s.lfo * inst.lfo_to_filter) >> 8)) & 0xFF) >> 2
    source = inst.bank[index * WAVE : (index + 1) * WAVE] if inst.bank else inst.wave
    s.buffer ^= WAVE
    out = voice.buffers[s.buffer // WAVE]
    count = WAVE >> s.shift
    if not inst.wave_rate:
        out[:count] = source[:: 1 << s.shift][:count]
    elif not inst.stretch:
        BlendCopy(module, s, inst, source, out, count)
    else:
        StretchHalves(module, s, inst, source, out, count)
    voice.start = voice.loop = bytes(out[:count])


def BlendCopy(
    module: Module,
    s: SynthState,
    inst: SynthInstrument,
    src: bytes,
    out: bytearray,
    count: int,
) -> None:
    """Each byte is the mean of the wave and the wave read from a moving
    offset: a sweeping comb, like phasing."""
    s.wave_phase = (
        s.wave_phase + ((inst.wave_rate * module.tick_length) >> 13)
    ) & 0xFFFF
    offset, step = s.wave_phase >> 9, 1 << s.shift
    for n in range(count):
        a = signed(src[n * step])
        b = signed(src[(offset + n * step) % WAVE])
        out[n] = ((a + b) >> 1) & 0xFF


def StretchHalves(
    module: Module,
    s: SynthState,
    inst: SynthInstrument,
    src: bytes,
    out: bytearray,
    count: int,
) -> None:
    """The first half of the wave plays in `half + d` bytes, the second in
    `half - d`. d swings as a triangle, times the depth: a moving pulse
    width on any wave."""
    step = ((inst.wave_rate * module.tick_length) >> 11) * s.direction
    phase = s.wave_phase + step
    if not -0x8000 <= phase < 0x8000:  # overflow: turn back
        phase = to_word(phase)
        if phase == -0x8000:
            phase = to_word(phase + s.direction)
        s.direction = -s.direction
        phase = to_word(-phase)
    s.wave_phase = phase
    half = count // 2
    d = (phase * inst.stretch) >> (17 + s.shift)
    first, second = half + d, half - d
    at = 0
    for length, base in ((first, 0), (second, WAVE // 2)):
        for n in range(max(length, 0)):
            if at < count:
                out[at] = src[base + (n * (WAVE // 2)) // length]
                at += 1


def SynthWrite(module: Module, voice: Voice) -> None:
    """Every tick: the new buffer, its length, period and volume. Paula
    takes the buffer at the next loop, so the wave changes without a
    restart. DMA on only for a new note."""
    channel = voice.channel
    channel.queue(paula.Sample(voice.start))
    channel.period = voice.period
    channel.set_volume(voice.volume)
    if voice.new_note:
        voice.new_note = False
        module.dma_on.add(voice.number)


def SetFilter(inst: SynthInstrument) -> None:
    """At load: 64 copies of the wave, one per cutoff. OneFilter."""
    inst.bank = OneFilter(inst.wave)


def OneFilter(wave: bytes) -> bytes:
    """A resonant low-pass: a velocity follows the input at the cutoff,
    and decays by about 0.9 × (1 - cutoff) per byte. The output and the
    velocity carry on from one cutoff to the next."""
    out = bytearray()
    velocity, level = 0, signed(wave[-1]) << 7
    for cutoff in FILTER_CUTOFFS:
        feedback = ((0x8000 - cutoff) * 0xE666) >> 16
        gain = cutoff >> 1
        for byte in wave:
            x = (signed(byte) << 7) - level
            velocity = to_word(velocity + (((to_word(x) * gain) << 2) >> 16))
            level = to_word(level + velocity)
            out.append((level >> 7) & 0xFF)
            velocity = to_word((velocity * feedback * 2) >> 16)
    return bytes(out)


def to_word(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


# --- The sample drivers -------------------------------------------------


def SampledTick(module: Module, voice: Voice) -> None:
    """A '.ss' sample holds each octave at twice the last one's length.
    A note picks its octave; out of range, it does not play. Vibrato
    and an envelope follow, both scaled by the tick length."""
    inst = voice.playing
    assert isinstance(inst, SampledSound)
    s = voice.sample
    if voice.request == 1:
        octave, semitone = divmod(voice.note, 12)
        octave = 10 - octave
        if not inst.low <= octave <= inst.high:
            voice.request = 0
            return
        s.period = (0x1AB9 * SEMITONES[semitone]) >> 15
        start = ((1 << octave) - (1 << inst.low)) * inst.octave_length
        length = inst.octave_length << octave
        loop = inst.loop << octave
        set_sample(voice, inst.data[start : start + length], loop)
        s.stage, s.level, s.vibrato_phase = ATTACK, 0, 0
        s.vibrato_wait = (((inst.vibrato_delay << 16) >> 1) // module.tick_length) >> 1
        cut_channel(voice)
    elif voice.request == 2:
        s.stage = RELEASE
    if s.vibrato_wait:
        s.vibrato_wait -= 1
    else:
        s.vibrato_phase += ((inst.vibrato_rate * module.tick_length << 7) >> 16) + 0x40
        s.vibrato_phase &= 0xFFFF
    s.vibrato = triangle(s.vibrato_phase)
    s.stage, s.level = envelope_step(module, inst.envelope, s.stage, s.level)
    factor = ((s.vibrato * inst.vibrato_depth) >> 7) - (module.tune - 0x80) + 0x1000
    voice.period = bent_period(module, voice, (s.period * factor) >> 16)
    volume = ((master_volume(module, voice) + 1) * inst.volume) >> 8
    voice.volume = (volume * (s.level >> 16)) >> 10


def triangle(phase: int) -> int:
    """The phase as a signed triangle, -128 to 127."""
    value = (phase >> 7) + 0x80
    if value & 0x100:
        value ^= 0xFF
    return -signed((value ^ 0x80) & 0xFF)


def IffTick(module: Module, voice: Voice) -> None:
    """An 8SVX sample, its octaves as the file stores them. No envelope:
    a release cuts the volume to 0."""
    inst = voice.playing
    assert isinstance(inst, IffSound)
    s = voice.sample
    if voice.request == 1:
        octave, semitone = divmod(voice.note, 12)
        octave = 10 - octave - inst.shift
        if not 0 <= octave < inst.octaves:
            voice.request = 0
            return
        s.period = (0x1AC * SEMITONES[semitone] * 2) >> 16
        one_shot, repeat = inst.one_shot << octave, inst.repeat << octave
        start = ((1 << octave) - 1) * (inst.one_shot + inst.repeat)
        set_sample(voice, inst.body[start : start + one_shot + repeat], one_shot)
        s.level = 1
        cut_channel(voice)
    elif voice.request == 2:
        s.level = 0
    period = (((0x1080 - module.tune) * s.period) << 4) >> 16
    voice.period = bent_period(module, voice, period)
    volume = 0
    if s.level:
        volume = (((master_volume(module, voice) + 1) * (inst.volume >> 1)) >> 16) >> 1
    voice.volume = volume


def set_sample(voice: Voice, data: bytes, loop: int) -> None:
    """The whole sample first, then its loop. Without a loop, a silent
    8-byte one."""
    voice.start = data
    voice.loop = data[loop:] if loop < len(data) else bytes(8)
    voice.new_note = True


def SampleWrite(module: Module, voice: Voice) -> None:
    """A new note writes its sample and asks for DMA on; the next tick
    writes the loop. Then period and volume, every tick."""
    channel = voice.channel
    if voice.new_note:
        voice.new_note = False
        channel.queue(paula.Sample(voice.start))
        module.dma_on.add(voice.number)
    elif voice.loop:
        channel.queue(paula.Sample(voice.loop))
        voice.loop = b""
    channel.period = voice.period
    channel.set_volume(voice.volume)


DRIVERS: dict[
    type, tuple[Callable[[Module, Voice], None], Callable[[Module, Voice], None]]
] = {
    SynthInstrument: (SynthTick, SynthWrite),
    SampledSound: (SampledTick, SampleWrite),
    IffSound: (IffTick, SampleWrite),
}
