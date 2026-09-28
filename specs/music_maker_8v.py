"""MusicMaker V8 by Thomas Winischhofer: eight voices on four channels.
MusicMaker8.asm, the author's EaglePlayer source. Its mixer is Dire
Cracks' Multi-Channel Player V1.9, linked in.

Card: players/MusicMaker-8V.md. Level 2: the control flow runs. Each
CamelCase function is a new name in data/annot/MusicMaker-8V.yaml; each
CamelCase class is in its `types:`.

Each voice has its own position list of pattern numbers. A pattern is a
list of 3-byte events: a note or a command, and its length in ticks.
Voices 2n and 2n+1 share channel n. Each tick, the mixer writes one
buffer per channel. The channel plays it at the higher voice's period,
so that voice needs no resampling. The louder voice sets the channel
volume; a table scales the quieter one. The replay halves every sample
byte at load, so two voices add up without clipping.

There is no timer. Each buffer lasts one tick, whatever its period, and
the channels' audio interrupts run the replay.

Left out: the game's song fade and channel mute, the one-shot song
mode, and the player's cache control.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from hardware import paula
from hardware.amiga import Amiga

CHANNELS = 4
TICK_CCK = 115  # TickLength counts units of 115 CCK
IDLE_PERIOD = 230  # a channel with no voice plays silence at this period
MIN_PERIOD, MAX_PERIOD = 113, 856  # ClampPeriod
MAX_VOLUME = 64
RATIO_STEPS = 64  # MakeTables: the quieter voice's volume, in 64ths
PATTERN_BLOCK = 64  # BuildStepPattern: output bytes per step pattern
FADE_NONE, FADE_IN_START, FADE_OUT_END = 256, 4096, 8192  # volume divisors
MIN_SPEED = 600  # SetSpeed's floor
HULL_BYTES = 40  # sample bytes per hull entry
END_OF_LIST, PAUSE = 999, 0  # position list words
PATTERN_END, CONTINUE, SKIP = 0xFF, 0xF0, 0xF3
SOFT_MODULATION = (0xF2, 0xFB)
BANK, HULL = 0xF8, 0xFA

# NoteTable: quarter tones from 856 to 170, then semitones up to 113
PERIODS = (
    *(856, 832, 808, 784, 760, 740, 720, 700, 680, 660, 640, 622, 604, 588),
    *(572, 556, 540, 524, 508, 494, 480, 466, 452, 440, 428, 416, 404, 392),
    *(380, 370, 360, 350, 340, 330, 320, 311, 302, 294, 286, 278, 270, 262),
    *(254, 247, 240, 233, 226, 220, 214, 208, 202, 196, 190, 185, 180, 175),
    *(170, 160, 151, 143, 135, 127, 120, 113),
)
# VolumeSteps: an event's 4-bit volume
VOLUMES = (0, 1, 2, 3, 5, 7, 11, 16, 22, 28, 34, 40, 46, 52, 58, 64)
# LoudnessTable: a note's volume divisor, in 256ths; high notes play at half
LOUDNESS = (
    *(256, 264, 268, 273, 277, 287, 292, 297, 303, 309, 315, 321, 327, 334),
    *(341, 348, 356, 364, 372, 372, 381, 390, 399, 399, 409, 420, 420, 431),
    *(431, 442, 442, 455, 468, 468, 468, 481, 481, 481, 496, 496, 496),
    *(512,) * 11,
    *(511,) * 12,
)


# --- Player state ------------------------------------------------------


@dataclass
class Instrument:  # four words each
    data: bytes  # halved by HalveSamples
    attack: int  # 2: bytes played before the loop
    loop_start: int  # 4: bytes
    loop_length: int  # 6: words; 0: no loop


@dataclass
class Voice:  # three structures per voice in the replay
    number: int
    positions: list[int] = field(default_factory=list)  # its position list
    position: int = 0
    pattern: bytes = b""
    pos: int = 0  # bytes into the pattern
    ticks: int = 1  # to the next event
    finished: bool = False  # the position list wrapped
    # the sound: the mixer takes a new sample once, then the loop
    sample: bytes = b""
    new_sample: bool = False  # NewNotes bit: the mixer takes `sample`
    loop: bytes = b""
    rest: bytes = b""  # what the mixer has not played yet
    saved: bytes = b""  # BreakNote: `rest` when the sample was cut
    period: int = 0  # after slides; the hull's change is not kept
    out_period: int = 0  # the period the mixer uses
    volume: int = 0  # 0 to 64, after all changes
    note: int = 0
    level: int = 0  # the event's volume, in half steps, after slides
    fade_divisor: int = FADE_NONE  # FadeTick: 256 is full volume
    fade_in: bool = False
    fade_out: bool = False
    loudness: bool = False  # LoudnessSwitch
    period_step: int = 0  # added each tick
    volume_step: int = 0
    wobble: int = 0  # >0 tremolo, <0 vibrato, 0 slides
    flip: bool = False  # the wobble's sign flips every second tick
    hull: bytes = b""  # this note's hull table; empty: off
    hull_pos: int = 0  # sample bytes played
    hull_length: int = 0
    hull_loop: int = 0  # bytes; 0: the hull stops at the sample end


@dataclass
class MixChannel:  # one Paula channel and its two voices
    channel: paula.Channel
    a: bytes = b""  # the odd voice's bytes still to play
    b: bytes = b""  # the even voice's
    period: int = IDLE_PERIOD  # written at the next interrupt
    volume: int = 0
    buffer: bytes = b""  # the buffer mixed this tick
    carry: int = 0x10000  # 42: the fraction of a byte, in 1/65536
    last_period: int = 0  # 8: the period that `carry` counts in
    correction: int = 0  # 10: bytes, from CorrectDrift and BufferLength
    slow: bool = False  # MixerType bit: the dbra mixer
    late: int = 0  # raster lines waited in WaitAllChannels
    variant: str = ""  # PickMixer's choice


@dataclass
class Module:
    amiga: Amiga
    instruments: list[Instrument]
    slots: int  # INSTNUM: instrument slots; the next number resumes a break
    patterns: list[bytes]
    hull_tables: list[bytes]  # HullTables: 15; word 0 names an instrument
    high_table: dict[int, int]  # HighTable: a mix period per period
    speed: int  # TickLength: one tick lasts speed × 115 CCK
    pause_length: int  # PauseLength: position word 0 waits this × 2 ticks
    mix_limit: int  # MixLimit: periods up to this use HighTable
    voices: list[Voice] = field(default_factory=list)
    mix: list[MixChannel] = field(default_factory=list)
    base_speed: int = 0
    new_speed: int = 0  # SetSpeed: taken at the next interrupt
    fade_in_speed: int = 63
    fade_out_speed: int = 21
    hull_for: dict[int, bytes] = field(default_factory=dict)  # SetHull
    pending: set[int] = field(default_factory=set)  # channels that interrupted
    game_routine: Callable[[int], None] | None = None  # CallGame
    call_game: bool = False
    calls: int = 0
    audio_filter: bool = False
    song_end: bool = False


# --- Load and start ----------------------------------------------------


def DeltaDecode(packed: bytes, bits: int, table: bytes, length: int) -> bytes:
    """Each code of `bits` bits picks a delta from `table`. The deltas
    add up to the sample bytes."""
    out, value, acc, have, at = bytearray(), 0, 0, 0, 0
    while len(out) < length:
        code = 0
        for _ in range(bits):
            if not have:
                acc, have, at = packed[at], 8, at + 1
            code = code << 1 | acc >> 7
            acc, have = acc << 1 & 0xFF, have - 1
        value = (value + table[code]) & 0xFF
        out.append(value)
    return bytes(out)


def HalveSamples(data: bytes) -> bytes:
    """Each byte shifts right by 1. The sum of two voices then fits in a
    byte, and a voice loses 1 bit."""
    return bytes((signed_byte(b) >> 1) & 0xFF for b in data)


def MakeTables() -> list[bytes]:
    """Row k scales a byte by k/64."""
    return [
        bytes((signed_byte(x) * k // RATIO_STEPS) & 0xFF for x in range(256))
        for k in range(RATIO_STEPS + 1)
    ]


def new_module(module: Module) -> Module:
    """The replay replaces the level 4 interrupt vector. DMA runs from
    the start, so the channels' interrupts start the ticks."""
    module.base_speed = module.speed
    module.mix = [MixChannel(c) for c in module.amiga.paula.channels]
    for mix in module.mix:
        mix.channel.on_irq(lambda c: AudioInterrupt(module, c))
    ResetSong(module)
    SoundOn(module)
    return module


def ResetSong(module: Module) -> None:
    InitVoices(module)


def InitVoices(module: Module) -> None:
    """Each voice starts at its position list's first pattern, with one
    tick to wait."""
    for voice in module.voices:
        voice.position, voice.pos, voice.ticks = 0, 0, 1
        voice.pattern = module.patterns[voice.positions[0]]


def SoundOn(module: Module) -> None:
    """Each channel starts with one tick of silence, at period 230."""
    for mix in module.mix:
        mix.channel.period = IDLE_PERIOD
        mix.channel.play(paula.Sample(bytes(module.speed // 2 & ~1)))


# --- Tick: the audio interrupt -----------------------------------------


def AudioInterrupt(module: Module, channel: paula.Channel) -> None:
    """A channel started its buffer. It gets the period and volume that
    the mixer chose for that buffer. When all four have started, the
    replay runs one tick. The replay busy-waits for the other channels."""
    mix = module.mix[channel.number]
    channel.period = mix.period
    channel.set_volume(mix.volume)
    module.pending.add(channel.number)
    if len(module.pending) < CHANNELS:
        return
    module.pending.clear()
    WaitAllChannels(module)
    CorrectDrift(module)
    if module.new_speed:
        module.speed, module.new_speed = module.new_speed, 0
    PlaySound(module)
    MixChannels(module)


def WaitAllChannels(module: Module) -> None:
    """The replay counts raster lines until each channel's interrupt
    comes. The model has no raster: every channel is on time."""
    for mix in module.mix:
        mix.late = 0


def CorrectDrift(module: Module) -> None:
    """A channel that started late gets a shorter next buffer: 1 byte
    after 4 lines, 2 after 10, 5 after 15."""
    for mix in module.mix:
        steps = ((4, 1), (10, 1), (15, 3))
        mix.correction -= sum(n for lines, n in steps if mix.late >= lines)


def PlaySound(module: Module) -> None:
    """Voices 7 down to 0: the sequencer, then volume and period. Then
    the game's routine, if a voice asked for it."""
    for voice in reversed(module.voices):
        HandleVoice(module, voice)
        StepVoices(module, voice)
    if module.call_game and module.game_routine is not None:
        module.calls += 1
        module.game_routine(module.calls)
    module.call_game = False


def StepVoices(module: Module, voice: Voice) -> None:
    """The order of changes to one voice's volume and period."""
    FadeTick(module, voice)
    volume = VolumeSlide(voice)
    volume = HullVolume(voice, volume)
    volume = Loudness(voice, volume)
    if voice.fade_divisor != FADE_NONE:
        volume = volume * FADE_NONE // voice.fade_divisor
    voice.volume = ClampVolume(volume, MAX_VOLUME)
    voice.period = PeriodSlide(voice)
    voice.out_period = HullStep(module, voice)


def FadeTick(module: Module, voice: Voice) -> None:
    """A voice fade moves the volume divisor by the song's fade speed:
    in from 4096 down to 256, out up to 8192. The fade in checks before
    it steps, so the divisor can dip below 256 for one tick."""
    d = voice.fade_divisor
    if voice.fade_in:
        if d > FADE_IN_START:
            d = FADE_IN_START - module.fade_in_speed
        elif d <= FADE_NONE:
            d, voice.fade_in = FADE_NONE, False
        else:
            d -= module.fade_in_speed
    elif voice.fade_out:
        if d >= FADE_OUT_END:
            d, voice.fade_out = FADE_OUT_END, False
        else:
            d += module.fade_out_speed
    voice.fade_divisor = d


def VolumeSlide(voice: Voice) -> int:
    """The volume step adds each tick. With tremolo, its sign flips
    every second tick."""
    if voice.wobble > 0:
        voice.flip = not voice.flip
        if not voice.flip:
            voice.volume_step = -voice.volume_step
    voice.level = ClampVolume(voice.level + voice.volume_step, 2 * MAX_VOLUME)
    return voice.level // 2


def HullVolume(voice: Voice, volume: int) -> int:
    """The hull entry at the sample position: volume × (1 + v / 32)."""
    if not voice.hull:
        return volume
    at = 2 + 2 * (voice.hull_pos // HULL_BYTES)
    change = signed_byte(voice.hull[at])
    return ClampVolume(volume + (volume * change >> 5), MAX_VOLUME)


def Loudness(voice: Voice, volume: int) -> int:
    """LoudnessSwitch on: the volume shrinks with the note, down to half
    at the top."""
    if not voice.loudness:
        return volume
    return (volume << 8) // LOUDNESS[voice.note]


def PeriodSlide(voice: Voice) -> int:
    """The period step adds each tick. With vibrato, its sign flips every
    second tick: a triangle of 4 ticks."""
    if voice.wobble < 0:
        voice.flip = not voice.flip
        if not voice.flip:
            voice.period_step = -voice.period_step
    return ClampPeriod(voice.period + voice.period_step)


def HullStep(module: Module, voice: Voice) -> int:
    """The hull's period change: period × (1 + p / 256). Then the hull
    moves on by the bytes that the sample plays in one tick, so it
    follows the sample at any pitch. At the sample's end it wraps by the
    loop, or stops."""
    if not voice.hull:
        return voice.period
    at = 2 + 2 * (voice.hull_pos // HULL_BYTES)
    change = signed_byte(voice.hull[at + 1])
    period = ClampPeriod(voice.period + (voice.period * change >> 8))
    voice.hull_pos += module.speed * TICK_CCK // period  # bytes per tick
    if voice.hull_pos > voice.hull_length:
        if voice.hull_loop:
            voice.hull_pos -= voice.hull_loop
        else:
            voice.hull = b""
    return period


def ClampVolume(volume: int, top: int) -> int:
    return max(0, min(volume, top))


def ClampPeriod(period: int) -> int:
    return max(MIN_PERIOD, min(period, MAX_PERIOD))


# --- The sequencer -----------------------------------------------------


def HandleVoice(module: Module, voice: Voice) -> None:
    """At 0 ticks left, the voice reads its next event."""
    voice.ticks -= 1
    if voice.ticks:
        return
    ReadEvent(module, voice)


def ReadEvent(module: Module, voice: Voice) -> None:
    """Three bytes. Byte 0: a command from $F2, else instrument (high
    nibble) and volume (low nibble). Byte 1: bit 7 loop, bit 6 filter
    state, bits 0-5 note. Byte 2: bit 7 soft modulation, bit 6 sets the
    filter, bits 0-5 length. A command takes time too: (length + 1) × 2
    ticks. A soft modulation event or $F8 lends the next event's
    length."""
    pattern, at = voice.pattern, voice.pos
    event = pattern[at : at + 3]
    lends = pattern[at + 3] in SOFT_MODULATION or event[0] == BANK
    voice.ticks = ((pattern[at + 5 if lends else at + 2] & 0x3F) + 1) * 2
    bank = 0
    if event[0] == BANK:
        bank = InstrumentBank(voice, event[1])
        event = pattern[voice.pos : voice.pos + 3]
    handler = COMMANDS.get(event[0])
    if event[0] == HULL:
        SetHull(module, event[1], bank)
    elif handler is not None:
        handler(module, voice, event[1])
    else:
        NoteEvent(module, voice, event, bank)
    NextEvent(module, voice)


def NoteEvent(module: Module, voice: Voice, event: bytes, bank: int) -> None:
    """A note clears the voice's slides. $F1 cuts the sample and keeps
    its rest for ResumeBreak. Volume 0 is a rest."""
    voice.period_step = voice.volume_step = 0
    if event[2] & 0x40:
        module.audio_filter = bool(event[1] & 0x40)
    note = event[1] & 0x3F
    if event[0] == 0xF1:
        BreakNote(voice, note)
        return
    if not event[0] & 0x0F:
        voice.sample, voice.loop, voice.new_sample = b"", b"", True
        return
    StartNote(module, voice, event, note, bank)


def BreakNote(voice: Voice, note: int) -> None:
    """$F1: keeps what the sample has left to play. With note 0 it also
    silences the voice; else the sample plays on."""
    voice.saved = voice.rest
    if not note:
        voice.sample, voice.loop, voice.new_sample = b"", b"", True


def StartNote(module: Module, voice: Voice, event: bytes, note: int, bank: int) -> None:
    """Sets note, period and volume. Soft modulation keeps the sample:
    a legato. Else a new sample starts: once, or its attack part and then
    the loop."""
    voice.note, voice.period = note, PERIODS[note]
    voice.level = 2 * VOLUMES[event[0] & 0x0F]
    if event[2] & 0x80:
        SoftModulation(voice)
        return
    number = (event[0] >> 4) + bank
    if number == module.slots:
        ResumeBreak(voice)
        return
    instrument = module.instruments[number]
    if event[1] & 0x80 and instrument.loop_length:
        voice.sample = instrument.data[: instrument.attack]
        start = instrument.loop_start
        voice.loop = instrument.data[start : start + 2 * instrument.loop_length]
    else:
        voice.sample, voice.loop = instrument.data, b""
    voice.new_sample = True
    start_hull(module, voice, number)


def ResumeBreak(voice: Voice) -> None:
    """The instrument number after the last slot: the cut sample plays
    on from where BreakNote kept it, with no loop."""
    voice.sample, voice.loop, voice.new_sample = voice.saved, b"", True


def SoftModulation(voice: Voice) -> None:
    """The note changes pitch and volume, and the sample plays on. A
    following $F2 or $FB event holds two signed nibbles: volume step and
    period step. $FB doubles the period step. The event is skipped."""
    event = voice.pattern[voice.pos + 3 : voice.pos + 6]
    if event[0] not in SOFT_MODULATION:
        return
    voice.volume_step = signed_nibble(event[1] >> 4)
    period = signed_nibble(event[1] & 0x0F)
    voice.period_step = period << 1 if event[0] == 0xFB else period
    voice.pos += 3


def start_hull(module: Module, voice: Voice, number: int) -> None:
    """A new sample starts its instrument's hull, if SetHull gave one."""
    voice.hull = module.hull_for.get(number, b"")
    voice.hull_pos = 0
    voice.hull_length = len(voice.sample)
    voice.hull_loop = len(voice.loop)


def NextEvent(module: Module, voice: Voice) -> None:
    """A $F3 event is skipped with the 6 bytes after it. At the
    pattern's end, the next position. If that pattern starts with $F0,
    the note that ended the last one plays on for its length."""
    while True:
        voice.pos += 3
        if voice.pattern[voice.pos] == SKIP:
            voice.pos += 6
        if voice.pattern[voice.pos] != PATTERN_END:
            return
        wrapped = NextPattern(module, voice)
        voice.pos = 0
        if wrapped or voice.pattern[0] != CONTINUE:
            return
        voice.ticks += ((voice.pattern[2] & 0x3F) + 1) * 2


def NextPattern(module: Module, voice: Voice) -> bool:
    """Position word 0 waits PauseLength × 2 ticks. 999 wraps to the
    start and marks the voice finished. True: it wrapped."""
    wrapped = False
    while True:
        voice.position += 1
        number = voice.positions[voice.position]
        if number == PAUSE:
            voice.ticks += 2 * module.pause_length
            continue
        if number == END_OF_LIST:
            voice.position, voice.finished, wrapped = 0, True, True
            number = voice.positions[0]
            module.song_end = all(v.finished for v in module.voices)
        voice.pattern = module.patterns[number]
        return wrapped


# --- Commands: byte 0 from $F4 -----------------------------------------

Command = Callable[[Module, Voice, int], None]


def LoudnessSwitch(module: Module, voice: Voice, value: int) -> None:
    """$F4: 0 off, else on."""
    voice.loudness = bool(value)


def SetSpeed(module: Module, voice: Voice, value: int) -> None:
    """$FC: the song's tick length × high nibble / low nibble, at least
    600 and at most the song's own. So a song can only speed up."""
    speed = module.base_speed * (value >> 4) // (value & 0x0F)
    module.new_speed = min(max(speed, MIN_SPEED), module.base_speed)


def CallGame(module: Module, voice: Voice, value: int) -> None:
    """$F5: the game's routine runs after this tick's voices."""
    module.call_game = True


def VoiceFade(module: Module, voice: Voice, value: int) -> None:
    """$F6: 0 stops. Positive fades out, negative fades in. Its size
    sets the song's speed for that direction."""
    voice.fade_in = voice.fade_out = False
    if value & 0x80:
        voice.fade_in, module.fade_in_speed = True, 0x100 - value
    elif value:
        voice.fade_out, module.fade_out_speed = True, value


def FadeState(module: Module, voice: Voice, value: int) -> None:
    """$F7: 0 sets the voice to 1/32 volume, else to full."""
    voice.fade_divisor = FADE_NONE if value else FADE_OUT_END


def InstrumentBank(voice: Voice, value: int) -> int:
    """$F8: the next event is read at once. Its instrument number, or
    SetHull's, adds this value."""
    voice.pos += 3
    return value


def Modulation(module: Module, voice: Voice, value: int) -> None:
    """$F9: a signed step. Byte 2's top bits pick a period slide (0x), a
    volume slide (10), or vibrato or tremolo (11) by the step's sign.
    Vibrato and tremolo share one switch: starting one clears the
    other's step."""
    step = signed_byte(value)
    kind = voice.pattern[voice.pos + 2] >> 6
    if kind < 2:
        voice.period_step = step
        voice.wobble = max(voice.wobble, 0)  # a period slide ends vibrato
    elif kind == 2:
        voice.volume_step = step
        voice.wobble = min(voice.wobble, 0)  # a volume slide ends tremolo
    elif step < 0:
        if voice.wobble < 0:
            voice.period_step = 0
        voice.volume_step, voice.wobble, voice.flip = -step, 1, False
    else:
        if voice.wobble > 0:
            voice.volume_step = 0
        voice.period_step, voice.wobble, voice.flip = step, -1, False


def SetHull(module: Module, value: int, bank: int) -> None:
    """$FA: high nibble instrument, low nibble hull table, 1 to 15. The
    table's first word must name the same instrument; else, and for
    table 0, the instrument has no hull."""
    number = (value >> 4) + bank
    table = module.hull_tables[(value & 0x0F) - 1] if value & 0x0F else b""
    module.hull_for[number] = table if table and word(table, 0) == number else b""


def no_command(module: Module, voice: Voice, value: int) -> None:
    """$FD: the event only waits. Other bytes from $F2 play as notes."""


COMMANDS: dict[int, Command] = {
    0xF4: LoudnessSwitch, 0xF5: CallGame, 0xF6: VoiceFade,
    0xF7: FadeState, 0xF9: Modulation, 0xFC: SetSpeed, 0xFD: no_command,
}  # fmt: skip


# --- The mixer ---------------------------------------------------------


def MixChannels(module: Module) -> None:
    """Pairs 7+6, 5+4, 3+2, 1+0 into channels 3 to 0."""
    for n, mix in enumerate(module.mix):
        MixPair(module, mix, module.voices[2 * n + 1], module.voices[2 * n])
        SwapBuffers(mix)


def MixPair(module: Module, mix: MixChannel, a: Voice, b: Voice) -> None:
    """A new sample replaces the rest of the old one; 3 bytes or fewer
    left switch to the loop. The mix period is the lower period of the
    voices that have bytes left. The channel volume is the louder
    voice's. With no bytes left, the channel plays silence at 230."""
    for voice, attr in ((a, "a"), (b, "b")):
        if voice.new_sample:
            setattr(mix, attr, voice.sample)
            voice.new_sample = False
        elif len(getattr(mix, attr)) <= 3:
            setattr(mix, attr, voice.loop)
    sounding = [v for v, left in ((a, mix.a), (b, mix.b)) if left]
    if not sounding:
        mix.period, mix.volume = IDLE_PERIOD, 0
        mix.buffer = bytes((module.speed // 4 + mix.correction) * 2)
        mix.correction = 0
        return
    mix.period = min(mix_period(module, mix, v) for v in sounding)
    mix.volume = max(v.volume for v in sounding)
    mix.variant = PrepareMixer(mix, a, b)
    mix.buffer = MixSpan(mix, a, b, BufferLength(module, mix))
    a.rest, b.rest = mix.a, mix.b


def mix_period(module: Module, mix: MixChannel, voice: Voice) -> int:
    """With the fast mixer, a period up to MixLimit plays at HighTable's
    period: a lower rate that skips bytes."""
    if not mix.slow and voice.out_period <= module.mix_limit:
        return module.high_table[voice.out_period]
    return voice.out_period


def BufferLength(module: Module, mix: MixChannel) -> int:
    """Bytes that last one tick at the mix period: speed × 115 / period.
    The length stays even. The fraction carries in 2-byte steps, which
    change the next buffer's length."""
    if mix.last_period and mix.last_period != mix.period:
        mix.carry = mix.carry // mix.period * mix.last_period
    mix.last_period = mix.period
    length, remainder = divmod(module.speed * TICK_CCK, mix.period)
    fraction = (remainder << 16) // mix.period
    length += mix.correction
    mix.correction = 0
    if length & 1:
        length += 1
        mix.carry -= 0xFFFF - fraction
    else:
        mix.carry += fraction
    if mix.carry < 0:
        mix.carry += 0x20000
        mix.correction -= 2
    elif mix.carry > 0x1FFFF:
        mix.carry -= 0x20000
        mix.correction += 2
    return length


def MixSpan(mix: MixChannel, a: Voice, b: Voice, length: int) -> bytes:
    """Each output byte is the louder voice's byte plus the quieter
    one's, scaled. The voice at the mix period steps one byte; the other
    steps by its period ratio. At a sample's end, WrapSample continues
    with the loop, or with silence."""
    loud, quiet = (a, b) if a.volume >= b.volume else (b, a)
    table = VolumeTable(loud.volume, quiet.volume)
    data = {a.number: mix.a, b.number: mix.b}
    pos = {a.number: 0, b.number: 0}
    steps = {v.number: step_pattern(mix, v.out_period, length) for v in (a, b)}
    out = bytearray()
    for i in range(length):
        total = 0
        for voice in (a, b):
            n = voice.number
            if data[n] and pos[n] >= len(data[n]):
                data[n], pos[n] = WrapSample(voice), 0
            byte = data[n][pos[n]] if pos[n] < len(data[n]) else 0
            total += signed_byte(byte if voice is loud else table[byte])
            pos[n] += steps[n][i]
        out.append(total & 0xFF)
    mix.a, mix.b = data[a.number][pos[a.number] :], data[b.number][pos[b.number] :]
    return bytes(out)


def WrapSample(voice: Voice) -> bytes:
    """A looping sound continues with its loop; a single-shot sound with
    silence. The replay then picks a new mixer for the rest."""
    return voice.loop


def step_pattern(mix: MixChannel, period: int, length: int) -> list[int]:
    """Bytes that each output byte moves this voice on."""
    if period == mix.period:
        return [1] * length
    if mix.slow:
        return DbraStep(mix.period, period, length)
    return BuildStepPattern(mix.period, period, length)


def BuildStepPattern(mix_period: int, period: int, length: int) -> list[int]:
    """The fast mixer's code has one step instruction per output byte:
    `nop`, `addq #1` or `addq #2`. This routine writes them for a block
    of 64 output bytes. The block's whole steps are spread evenly. A
    16-bit fraction adds after each block; its carry moves the voice one
    more byte. So the pitch stays exact over many blocks. Each mixer
    variant keeps the period pair it was written for, so an unchanged
    pair costs nothing."""
    per_block = (mix_period << 16) * PATTERN_BLOCK // period
    whole, fraction = per_block >> 16, per_block & 0xFFFF
    block, error = [], 0
    for _ in range(PATTERN_BLOCK):
        error += whole
        block.append(error // PATTERN_BLOCK)
        error %= PATTERN_BLOCK
    out: list[int] = []
    acc = 0
    while len(out) < length:
        steps = list(block)
        acc += fraction
        if acc > 0xFFFF:
            acc &= 0xFFFF
            steps[-1] += 1
        out += steps
    return out[:length]


def DbraStep(mix_period: int, period: int, length: int) -> list[int]:
    """The slow mixer, and every mixer on a 68020 or later: a 16-bit
    fraction adds each byte; its carry steps the voice."""
    step, acc = (mix_period << 16) // period, 0
    out: list[int] = []
    for _ in range(length):
        acc += step
        out.append(acc >> 16)
        acc &= 0xFFFF
    return out


def SwapBuffers(mix: MixChannel) -> None:
    """The mixed buffer's address and length take effect at the channel's
    next wrap. Its period and volume wait for that wrap's interrupt."""
    mix.channel.queue(paula.Sample(mix.buffer))


def PickMixer(a: Voice, b: Voice) -> str:
    """One unrolled copy of the inner loop per case, so each does only
    the work its case needs. Cases: periods equal or not, volumes equal
    or not, one voice silent, a period above MixLimit's rate."""
    periods = "same periods" if a.out_period == b.out_period else "resampled"
    volumes = "same volumes" if a.volume == b.volume else "scaled"
    return f"{periods}, {volumes}"


def PrepareMixer(mix: MixChannel, a: Voice, b: Voice) -> str:
    """Picks the variant. The fast mixer then patches its step
    instructions, and VolumeTable fills its volume buffer."""
    return PickMixer(a, b)


def VolumeTable(loud: int, quiet: int) -> bytes:
    """The row for quiet / loud, in 64ths. The fast mixer copies it to a
    256-byte aligned buffer: the sample byte becomes the address's low
    byte, so a lookup takes no index arithmetic. Four buffers cache the
    last volume pairs."""
    return RATIOS[quiet * RATIO_STEPS // loud] if loud else RATIOS[0]


# --- Helpers -----------------------------------------------------------


def signed_byte(value: int) -> int:
    return value - 0x100 if value & 0x80 else value


def signed_nibble(value: int) -> int:
    return value - 0x10 if value & 0x08 else value


def word(data: bytes, at: int) -> int:
    return data[at] << 8 | data[at + 1]


RATIOS = MakeTables()  # built at load
