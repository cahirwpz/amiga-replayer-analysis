"""Voodoo Supreme Synthesizer's replay, by Tomas Partl (1993), in the
DeliTracker player VSS V1.5 (31 May 95).

Card: players/VoodooSupremeSynthesizer.md. Level 2: the control flow
runs. Each CamelCase function is a LABEL in
data/disasm/VoodooSupremeSynthesizer.cnf; each CamelCase class is in the
`types:` of data/annot/VoodooSupremeSynthesizer.yaml. Comments name the
voice fields by their offsets in a voice record, $42 bytes each.

Each voice reads its own byte stream. Commands call, return and loop on
one small stack per voice. A note starts three tables: volume, period
and wave. The wave table drives one of four modes:

- mix, exclusive or, morph: each tick, the replay fills the idle half of
  a 2 × 32-byte buffer from two samples, and Paula plays the other half.
- chunks: Paula plays a long sample 128 bytes at a time. Each audio
  interrupt starts the next chunk and moves a pointer by a step. The
  step can follow the period, so the sample keeps its speed at any
  pitch.

The tick is a vertical blank server. Period and volume reach Paula one
tick after they are computed.

Left out: DeliTracker's hooks, the channel allocation, and the check of
the footer's subsong count.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from hardware import paula
from hardware.amiga import Amiga

FOOTER = b"VSS0"
FOOTER_SEARCH = 64  # FindFooter: the mark is in the last 64 bytes
WAVE_BYTES = 32  # a buffer half; the wave modes play 16 words
WAVE_MASK = WAVE_BYTES - 1
CHUNK_WORDS = 64  # CmdWaveTable: AUDxLEN in chunk mode
CHUNK_BYTES = 2 * CHUNK_WORDS  # ChunkStep: the step without the period
STACK_ENTRIES = 20  # 80 bytes per voice; nothing checks for overflow
EMPTY = bytes(256)  # EmptySample
MAX_VOLUME = 64
ALL_LOOPED = 0xF  # LoopedVoices: four gotos in one tick end the song
NOTE_CUT = 0x7F  # a command byte $FF
TABLE_JUMP = 0x88  # a volume table entry: jump
TABLE_END = 0xFF  # a period, exclusive-or, morph or chunk table entry: jump
OCTAVE = 12

# Mode bits, voice field $3A
FREQUENCY_BASED = 0x01  # chunks: the step follows the period
STOPPED = 0x02  # chunks: past the sample's end, play EmptySample
CHUNKS = 0x20
XOR = 0x40
MORPH = 0x80
PLAIN_COPY = 0x80  # a morph table command: copy sample 1

# Keep flags, voice field $2A: a note leaves these tables running
KEEP_WAVE, KEEP_PERIOD, KEEP_VOLUME = 0x20, 0x40, 0x80

# Period commands, voice field $34
OCTAVE_DOWN, OCTAVE_UP, INTERVAL = 0xFE, 0x7F, 0x7E

# Periods: one word per note, 8 octaves. Entry 11 is $4519; the pattern
# gives $4280. So the lowest B plays about 66 cents flat.
PERIODS = (
    32256, 30464, 28672, 27136, 25600, 24192, 22784, 21504, 20352, 19200, 18048, 17689,
    16128, 15232, 14336, 13568, 12800, 12096, 11392, 10752, 10176, 9600, 9024, 8512,
    8064, 7616, 7168, 6784, 6400, 6048, 5696, 5376, 5088, 4800, 4512, 4256,
    4032, 3808, 3584, 3392, 3200, 3024, 2848, 2688, 2544, 2400, 2256, 2128,
    2016, 1904, 1792, 1696, 1600, 1512, 1424, 1344, 1272, 1200, 1128, 1064,
    1008, 952, 896, 848, 800, 756, 712, 672, 636, 600, 564, 532,
    504, 476, 448, 424, 400, 378, 356, 336, 318, 300, 282, 266,
    252, 238, 224, 212, 200, 189, 178, 168, 159, 150, 141, 133,
)  # fmt: skip

# Ratios: 0 to 12 semitones as fractions. 107/101 is a semitone.
RATIOS = (
    (1, 1), (107, 101), (55, 49), (44, 37), (160, 127), (4, 3), (140, 99),
    (218, 146), (100, 63), (111, 66), (98, 55), (168, 89), (2, 1),
)  # fmt: skip


# --- Player state ------------------------------------------------------


@dataclass
class Voice:  # Voice0: $42 bytes each
    channel: paula.Channel
    buffer: bytearray = field(default_factory=lambda: bytearray(2 * WAVE_BYTES))  # $0C
    pointer: int | None = None  # 0: sample 1; chunk mode reuses it; None: EmptySample
    sample2: int = 0  # 4
    half: int = 0  # 8: 0 or 32, the half the next fill writes
    wave_pos: int = 0  # 9: 0-31
    step: int = 1  # $0A: a byte in the wave modes, a word in chunk mode
    start_pos: int = 0  # $0B: wave_pos at each note
    mask: int = 0  # $10: mix and exclusive-or mask; chunks: the base note
    wave_count: int = 0  # $11
    stream: int = 0  # $16
    ticks: int = 1  # $1A
    volume: int = 0  # $1B
    period: int = 0  # $1C
    stack: list[int] = field(default_factory=list)  # $1E: return addresses, loop counts
    volume_table: int = 0  # $22
    period_table: int = 0  # $26
    keep: int = 0  # $2A
    porta_step: int = 0  # $2B: bit 7 set: down
    porta_delay: int = 0  # $2C
    porta_ticks: int = 0  # $2D
    volume_count: int = 0  # $2E
    period_count: int = 0  # $2F
    porta_count: int = 0  # $30
    transpose: int = 0  # $31
    volume_pos: int = 0  # $32
    period_pos: int = 0  # $33
    period_command: int = 0  # $34
    wave_pos_table: int = 0  # $35
    wave_table: int = 0  # $36
    mode: int = 0  # $3A
    morph_speed: int = 0  # $3B
    hw_period: int = 0  # $3C: written to Paula next tick
    hw_volume: int = 0  # $3E: written to Paula next tick
    volume_delta: int = 0  # $3F
    master: int = MAX_VOLUME  # $40: DeliTracker's volume and balance


@dataclass
class Module:  # Globals
    amiga: Amiga
    data: bytearray  # the file: samples, streams, tables, offsets, footer
    base: int = 0  # Offsets: the subsong record; command offsets count from it
    voices: list[Voice] = field(default_factory=list)
    looped: int = 0  # LoopedVoices: a bit per goto this tick
    extra_ticks: int = 0  # ExtraTicks: DeliTracker's fast forward, 0-5
    ended: bool = False  # DeliTracker's song-end signal


# --- Start -------------------------------------------------------------


def new_module(module: Module, song: int) -> Module:
    module.voices = [Voice(c) for c in module.amiga.paula.channels]
    StartSong(module, song)
    for n, channel in enumerate(module.amiga.paula.channels):
        channel.on_irq(audio_irq(module, n))
    module.amiga.vblank.handler = lambda: TickServer(module)
    module.amiga.vblank.start()
    return module


def audio_irq(module: Module, n: int) -> Callable[[paula.Channel], None]:
    """AudioIrq0-3: each channel's handler runs NextChunk on its voice."""
    return lambda _: NextChunk(module, module.voices[n])


def FindFooter(data: bytes | bytearray) -> int:
    """The mark `VSS0`, at an even offset in the last 64 bytes."""
    start = len(data) - FOOTER_SEARCH
    for at in range(start - start % 2, len(data) - 3, 2):
        if data[at : at + 4] == FOOTER:
            return at
    raise ValueError("no VSS0 footer")


def StartSong(module: Module, song: int) -> None:
    """The footer holds a subsong count, then an offset per subsong,
    counted from the mark. The record there starts with one offset per
    voice's stream, counted from the record. Offsets are signed."""
    footer = FindFooter(module.data)
    module.base = footer + signed_long(module.data, footer + 8 + 4 * song)
    InitVoices(module)


def InitVoices(module: Module) -> None:
    """Every voice plays EmptySample, 16 words, at volume 0. DMA starts
    here and stays on."""
    for n, old in enumerate(module.voices):
        voice = module.voices[n] = Voice(old.channel, master=old.master)
        voice.stream = AddressAt(module, n)
        voice.channel.set_volume(0)
        voice.channel.play(paula.Sample(EMPTY, 0, WAVE_BYTES // 2))


# --- Interrupts --------------------------------------------------------


def TickServer(module: Module) -> None:
    """The vertical blank server: one tick per frame."""
    Tick(module)


def NextChunk(module: Module, voice: Voice) -> None:
    """Each channel's audio interrupt. Chunk mode only: queue the chunk
    at the pointer, then move the pointer by the step. Past the end of
    sample 2, queue EmptySample until a chunk table entry or a note."""
    if not voice.mode & CHUNKS:
        return
    old = voice.pointer
    end = voice.sample2 + word(module.data, voice.sample2 - 2)
    if voice.mode & STOPPED or old is None or old + voice.step > end:
        voice.pointer, old = None, None
        voice.mode |= STOPPED
    else:
        voice.pointer = old + voice.step
    voice.channel.queue(chunk(module, old))


# --- Tick --------------------------------------------------------------


def Tick(module: Module) -> None:
    """All voices, 1 to 6 times per frame. Four gotos in one tick end
    the song."""
    for _ in range(module.extra_ticks + 1):
        module.looped = 0
        for voice in module.voices:
            VoiceTick(module, voice)
        if module.looped == ALL_LOOPED:
            module.ended = True


def VoiceTick(module: Module, voice: Voice) -> None:
    voice.ticks = (voice.ticks - 1) & 0xFF
    if not voice.ticks:
        ReadStream(module, voice)
    VolumeEnvelope(module, voice)
    PeriodTable(module, voice)
    Portamento(voice)
    PeriodCommand(voice)
    SetHardware(module, voice)


def VolumeEnvelope(module: Module, voice: Voice) -> None:
    """Entries of two bytes: TABLE_JUMP jumps; (level, 0) sets the volume;
    (delta, ticks) adds delta every tick for that many ticks. The
    volume wraps: nothing clamps it."""
    data = module.data
    voice.volume_count = (voice.volume_count - 1) & 0xFF
    if not voice.volume_count:
        at = voice.volume_table + voice.volume_pos
        while data[at] == TABLE_JUMP:
            voice.volume_pos = data[at + 1]
            at = voice.volume_table + voice.volume_pos
        if not data[at + 1]:
            VolumeLevel(voice, data[at])
            return
        voice.volume_delta, voice.volume_count = data[at], data[at + 1]
        voice.volume_pos += 2
    voice.volume = (voice.volume + voice.volume_delta) & 0xFF


def VolumeLevel(voice: Voice, level: int) -> None:
    voice.volume, voice.volume_count = level, 1
    voice.volume_pos += 2


def PeriodTable(module: Module, voice: Voice) -> None:
    """Entries of two bytes: TABLE_END jumps; (command, ticks) runs the command
    every tick for that many ticks."""
    data = module.data
    voice.period_count = (voice.period_count - 1) & 0xFF
    if voice.period_count:
        return
    at = voice.period_table + voice.period_pos
    while data[at] == TABLE_END:
        voice.period_pos = data[at + 1]
        at = voice.period_table + voice.period_pos
    voice.period_command, voice.period_count = data[at], data[at + 1]
    voice.period_pos += 2


def Portamento(voice: Voice) -> None:
    """Every `porta_delay` ticks, the period moves by the step, until
    `porta_ticks` run out."""
    voice.porta_ticks = (voice.porta_ticks - 1) & 0xFF
    if not voice.porta_ticks:
        voice.porta_step = voice.porta_count = 0
        return
    voice.porta_count = (voice.porta_count - 1) & 0xFF
    if voice.porta_count:
        return
    voice.porta_count = voice.porta_delay
    if voice.porta_step >= 0x7F:
        voice.period = (voice.period - (voice.porta_step & 0x7F)) & 0xFFFF
    else:
        voice.period = (voice.period + voice.porta_step) & 0xFFFF


def PeriodCommand(voice: Voice) -> None:
    """OCTAVE_DOWN: an octave down. OCTAVE_UP: an octave up. INTERVAL: an
    interval, once. Below OCTAVE_UP: add to the period. Else: subtract bits 0-6. Each runs
    every tick of its entry."""
    command = voice.period_command
    if command == OCTAVE_DOWN:
        voice.period = voice.period << 1 & 0xFFFF
    elif command == OCTAVE_UP:
        voice.period >>= 1
    elif command == INTERVAL:
        Interval(voice)
    elif command < OCTAVE_UP:
        voice.period = (voice.period + command) & 0xFFFF
    else:
        voice.period = (voice.period - (command & 0x7F)) & 0xFFFF


def Interval(voice: Voice) -> None:
    """The entry's tick byte is the interval: bit 7 down, bits 0-6
    semitones. Whole octaves shift the period; the rest multiplies it
    by a ratio. Down rounds up."""
    arg, voice.period_count = voice.period_count, 1
    down, semitones = bool(arg & 0x80), arg & 0x7F
    if semitones > OCTAVE:
        octaves, semitones = divmod(semitones, OCTAVE)
        octaves &= 7
        voice.period = voice.period << octaves if down else voice.period >> octaves
        voice.period &= 0xFFFF
    high, low = RATIOS[semitones]
    num, den = (high, low) if down else (low, high)
    value, rest = divmod(voice.period * num, den)
    voice.period = (value + (1 if down and rest else 0)) & 0xFFFF


def SetHardware(module: Module, voice: Voice) -> None:
    """DMA on; Paula gets last tick's period and volume. Then the mode's
    routine runs."""
    channel = voice.channel
    channel.enable()
    channel.period = voice.hw_period
    channel.set_volume(voice.hw_volume)
    voice.hw_period = voice.period
    voice.hw_volume = (voice.volume * voice.master >> 6) & 0xFF
    if voice.mode & XOR:
        XorWaves(module, voice)
    elif voice.mode & MORPH:
        MorphWave(module, voice)
    elif voice.mode & CHUNKS:
        ChunkTable(module, voice)
    else:
        MixWaves(module, voice)


# --- Wave modes --------------------------------------------------------


def MixWaves(module: Module, voice: Voice) -> None:
    """Entries (step, ticks); bit 7 set jumps. Each tick, sample 2's
    phase moves by the step. The fill averages sample 1 with sample 2
    at that phase, then ORs the mask into each byte's magnitude."""
    data = module.data
    voice.wave_count = (voice.wave_count - 1) & 0xFF
    if not voice.wave_count:
        at = voice.wave_table + voice.wave_pos_table
        while data[at] & 0x80:
            voice.wave_pos_table = data[at + 1]
            at = voice.wave_table + voice.wave_pos_table
        voice.step, voice.wave_count = data[at], data[at + 1]
        voice.wave_pos_table += 2
    voice.wave_pos = (voice.wave_pos + voice.step) & WAVE_MASK
    fill = swap_halves(voice)
    for n in range(WAVE_BYTES):
        one = signed(read(module, voice.pointer, n))
        two = signed(data[voice.sample2 + (voice.wave_pos + n & WAVE_MASK)])
        value = (one + two) >> 1 & 0xFF
        if value & 0x80:
            value = -(-signed(value) | voice.mask) & 0xFF
        else:
            value |= voice.mask
        voice.buffer[fill + n] = value


def XorWaves(module: Module, voice: Voice) -> None:
    """Entries (step, ticks); TABLE_END jumps. Inside a window from wave_pos,
    step & 31 bytes long, each byte of the playing half is XORed with
    sample 2 & mask into the other half. So changes add up, tick by
    tick. Step bit 7: a plain copy of sample 1."""
    data = module.data
    voice.wave_count = (voice.wave_count - 1) & 0xFF
    if not voice.wave_count:
        at = voice.wave_table + voice.wave_pos_table
        while data[at] == TABLE_END:
            voice.wave_pos_table = data[at + 1]
            at = voice.wave_table + voice.wave_pos_table
        voice.step, voice.wave_count = data[at], data[at + 1]
        voice.wave_pos_table += 2
    playing = voice.half
    fill = swap_halves(voice)
    if voice.step & 0x80:
        CopyWave(module, voice, fill)
        return
    for n, inside in enumerate(window(voice.wave_pos, voice.step)):
        byte = voice.buffer[playing + n]
        if inside:
            byte ^= data[voice.sample2 + n] & voice.mask
        voice.buffer[fill + n] = byte
    voice.wave_pos = (voice.step + voice.wave_pos) & WAVE_MASK


def MorphWave(module: Module, voice: Voice) -> None:
    """Entries (command, speed, ticks); TABLE_END jumps. Inside the window,
    each byte of the playing half moves toward the target by at most
    `speed` per tick. Command bits 6-7: 01 targets sample 1, else sample
    2; 11 keeps the window still, else it moves by its length.
    PLAIN_COPY copies sample 1."""
    data = module.data
    voice.wave_count = (voice.wave_count - 1) & 0xFF
    if not voice.wave_count:
        at = voice.wave_table + voice.wave_pos_table
        while data[at] == TABLE_END:
            voice.wave_pos_table = data[at + 1]
            at = voice.wave_table + voice.wave_pos_table
        voice.step, voice.morph_speed, voice.wave_count = data[at : at + 3]
        voice.wave_pos_table += 3
    playing = voice.half
    fill = swap_halves(voice)
    command = voice.step
    if command == PLAIN_COPY:
        CopyWave(module, voice, fill)
        return
    target = voice.pointer if command & 0xC0 == 0x40 else voice.sample2
    for n, inside in enumerate(window(voice.wave_pos, command)):
        byte = voice.buffer[playing + n]
        if inside:
            now, goal = signed(byte), signed(read(module, target, n))
            if abs(goal - now) <= voice.morph_speed:
                now = goal
            else:
                now += voice.morph_speed if goal > now else -voice.morph_speed
            byte = now & 0xFF
        voice.buffer[fill + n] = byte
    if command & 0xC0 != 0xC0:
        voice.wave_pos = (voice.wave_pos + command) & WAVE_MASK


def CopyWave(module: Module, voice: Voice, fill: int) -> None:
    for n in range(WAVE_BYTES):
        voice.buffer[fill + n] = read(module, voice.pointer, n)


def ChunkTable(module: Module, voice: Voice) -> None:
    """Entries (offset high, offset low, ticks); TABLE_END jumps. An entry
    moves the chunk pointer into sample 2. Between entries, only the
    audio interrupt moves it."""
    data = module.data
    voice.wave_count = (voice.wave_count - 1) & 0xFF
    if not voice.wave_count:
        at = voice.wave_table + voice.wave_pos_table
        while data[at] == TABLE_END:
            voice.wave_pos_table = data[at + 1]
            at = voice.wave_table + voice.wave_pos_table
        voice.pointer = voice.sample2 + word(data, at)
        voice.mode &= ~STOPPED
        voice.wave_count = data[at + 2]
        voice.wave_pos_table += 3
    ChunkStep(voice)


def ChunkStep(voice: Voice) -> None:
    """Without FREQUENCY_BASED: 128 bytes, so the chunks join. With it:
    128 × period / the base note's period. A higher note plays each
    chunk faster and steps less, so the sample moves at the base note's
    speed at every pitch."""
    if not voice.mode & FREQUENCY_BASED:
        voice.step = CHUNK_BYTES
        return
    base = PERIODS[voice.mask]
    whole, rest = divmod(voice.period, base)
    voice.step = (whole * CHUNK_BYTES + rest * CHUNK_BYTES // base) & 0xFFFF


# --- Stream ------------------------------------------------------------


def ReadStream(module: Module, voice: Voice) -> None:
    """Commands until a note, a note cut or a portamento. A note byte,
    then a tick count."""
    data = module.data
    while True:
        byte = data[voice.stream]
        voice.stream += 1
        if byte < 0x80:
            voice.period = NotePeriod(voice, byte)
            start_note(module, voice)
            return
        if Command(module, voice, byte & 0x7F):
            return


def NotePeriod(voice: Voice, note: int) -> int:
    return PERIODS[note + voice.transpose & 0xFF]


def start_note(module: Module, voice: Voice) -> None:
    """The tick count, then each table restarts unless its keep flag is
    set."""
    voice.mode &= ~STOPPED
    voice.ticks = module.data[voice.stream]
    voice.stream += 1
    if not voice.keep & KEEP_WAVE:
        voice.wave_pos_table, voice.wave_count = 0, 1
        voice.wave_pos = voice.start_pos
    if not voice.keep & KEEP_VOLUME:
        voice.volume_pos, voice.volume_count = 0, 1
    if not voice.keep & KEEP_PERIOD:
        voice.period_pos, voice.period_count = 0, 1


def Command(module: Module, voice: Voice, number: int) -> bool:
    """COMMANDS runs the others; NOTE_CUT cuts the note. True: the stream
    waits."""
    if number == NOTE_CUT:
        NoteCut(module, voice)
        return True
    return COMMANDS[number - 1](module, voice)


def NoteCut(module: Module, voice: Voice) -> None:
    """Volume 0 now, not next tick; then a tick count."""
    voice.volume = voice.volume_count = 0
    voice.hw_volume = voice.volume_delta = 0
    voice.ticks = module.data[voice.stream]
    voice.stream += 1


def CmdCall(module: Module, voice: Voice) -> bool:
    """Argument n: push the return address; go to offset n."""
    target = arg(module, voice)
    voice.stack.append(voice.stream)
    voice.stream = AddressAt(module, target)
    return False


def CmdReturn(module: Module, voice: Voice) -> bool:
    voice.stream = voice.stack.pop()
    return False


def CmdLoopStart(module: Module, voice: Voice) -> bool:
    """Arguments count, unused byte: push the loop's start, then the count."""
    count = module.data[voice.stream]
    voice.stream += 2
    voice.stack += [voice.stream, count]
    return False


def CmdLoop(module: Module, voice: Voice) -> bool:
    """Back to the loop's start until the count reaches 0."""
    count, start = voice.stack.pop() - 1, voice.stack.pop()
    if count:
        voice.stream = start
        voice.stack += [start, count]
    return False


def CmdSamples(module: Module, voice: Voice) -> bool:
    """Arguments a, b: samples 1 and 2 at offsets a and b."""
    voice.pointer = AddressAt(module, arg(module, voice))
    voice.sample2 = AddressAt(module, arg(module, voice))
    return False


def CmdVolumeTable(module: Module, voice: Voice) -> bool:
    """Argument n: restart the volume table at offset n."""
    voice.volume_table = AddressAt(module, arg(module, voice))
    voice.volume_pos, voice.volume_count = 0, 1
    return False


def CmdPeriodTable(module: Module, voice: Voice) -> bool:
    """Argument n: restart the period table at offset n."""
    voice.period_table = AddressAt(module, arg(module, voice))
    voice.period_pos, voice.period_count = 0, 1
    return False


def CmdWaveTable(module: Module, voice: Voice) -> bool:
    """n mode: restart the wave table at offset n. Chunk mode sets
    AUDxLEN to 64 words. The wave modes take the start position from
    bits 0-4; leaving chunk mode sets 16 words on the voice's buffer."""
    voice.wave_table = AddressAt(module, arg(module, voice))
    voice.wave_pos_table, voice.wave_count = 0, 1
    mode, was = arg(module, voice), voice.mode
    voice.mode = mode
    if mode & CHUNKS:
        voice.channel.length = CHUNK_WORDS
        return False
    voice.wave_pos = voice.start_pos = mode & WAVE_MASK
    if was & CHUNKS:
        voice.channel.queue(paula.Sample(voice.buffer, 0, WAVE_BYTES // 2))
        voice.step = 0
    return False


def CmdPortamento(module: Module, voice: Voice) -> bool:
    """Arguments from, to, ticks: from note `from`, reach note `to` in `ticks`.
    The step is the period difference / ticks, at least 1; the delay is
    ticks / difference, at least 1. It acts as a note, and `ticks` is
    also its length. Equal notes divide by zero: the 68000 traps."""
    data = module.data
    first, last, ticks = data[voice.stream : voice.stream + 3]
    voice.period = start = NotePeriod(voice, first)
    difference = NotePeriod(voice, last) - start
    down = 0x80 if difference < 0 else 0
    difference = abs(difference)
    voice.porta_step = down | ((difference // ticks) & 0xFF or 1)
    if not difference:
        raise ZeroDivisionError("CmdPortamento: equal notes")
    voice.porta_delay = (ticks // difference) & 0xFF or 1
    voice.porta_count, voice.porta_ticks = 1, ticks
    voice.stream += 2
    start_note(module, voice)
    return True


def CmdTranspose(module: Module, voice: Voice) -> bool:
    """Argument n: added to every note."""
    voice.transpose = arg(module, voice)
    return False


def CmdGoto(module: Module, voice: Voice) -> bool:
    """Argument n: go to offset n, and count a goto for the song end."""
    voice.stream = AddressAt(module, arg(module, voice))
    module.looped = (module.looped << 1 | 1) & 0xFFFF
    return False


def CmdKeepFlags(module: Module, voice: Voice) -> bool:
    """Argument flags: which tables a note leaves running."""
    voice.keep = arg(module, voice)
    return False


def CmdMask(module: Module, voice: Voice) -> bool:
    """Argument n: the mix and exclusive-or mask, or the chunks' base note."""
    voice.mask = arg(module, voice)
    return False


COMMANDS = (
    CmdCall,  # $81
    CmdReturn,  # $82
    CmdLoopStart,  # $83
    CmdLoop,  # $84
    CmdSamples,  # $85
    CmdVolumeTable,  # $86
    CmdPeriodTable,  # $87
    CmdWaveTable,  # $88
    CmdPortamento,  # $89
    CmdTranspose,  # $8a
    CmdGoto,  # $8b
    CmdKeepFlags,  # $8c
    CmdMask,  # $8d
)


def OffsetAt(module: Module, n: int) -> int:
    """Entry n of the subsong record's offset list: signed, since data
    lies on both sides of the record."""
    return signed_long(module.data, module.base + 4 * n)


def AddressAt(module: Module, n: int) -> int:
    return module.base + OffsetAt(module, n)


# --- Helpers -----------------------------------------------------------


def arg(module: Module, voice: Voice) -> int:
    value = module.data[voice.stream]
    voice.stream += 1
    return value


def swap_halves(voice: Voice) -> int:
    """Queue the half just filled; return the other one, to fill now.
    Paula takes the queued half at its next reload."""
    voice.channel.queue(paula.Sample(voice.buffer, voice.half, WAVE_BYTES // 2))
    voice.half ^= WAVE_BYTES
    return voice.half


def window(start: int, length: int) -> list[bool]:
    """Which of the 32 bytes lie in the window from `start`, `length` &
    31 bytes long. It wraps past byte 31."""
    end = start + (length & WAVE_MASK)
    inside = bool(end & WAVE_BYTES)
    end &= WAVE_MASK
    out = []
    for n in range(WAVE_BYTES):
        if n == start:
            inside = not inside
        if n == end:
            inside = not inside
        out.append(inside)
    return out


def chunk(module: Module, at: int | None) -> paula.Sample:
    """64 words from `at`; Paula ignores bit 0 of an address. Past the
    file's end the hardware reads on; the model stops there."""
    if at is None:
        return paula.Sample(EMPTY, 0, CHUNK_WORDS)
    at &= ~1
    return paula.Sample(module.data, at, min(CHUNK_WORDS, (len(module.data) - at) // 2))


def read(module: Module, at: int | None, n: int) -> int:
    """Byte n from `at`; None is EmptySample."""
    return EMPTY[n] if at is None else module.data[at + n]


def signed(value: int) -> int:
    return value - 0x100 if value & 0x80 else value


def word(data: bytes | bytearray, at: int) -> int:
    return data[at] << 8 | data[at + 1]


def signed_long(data: bytes | bytearray, at: int) -> int:
    value = word(data, at) << 16 | word(data, at + 2)
    return value - (1 << 32) if value & 1 << 31 else value
