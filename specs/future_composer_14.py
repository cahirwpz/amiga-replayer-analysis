"""Future Composer 1.4's replay: FC1.4.s, by SuperSero of the Superions.

Card: players/FutureComposer1.4.md. Level 2: the control flow runs. Each
CamelCase function is a label in data/annot/FutureComposer1.4.yaml; each
CamelCase class is in its `types:`. Comments name the voice fields by
their offsets in Voice1Data.

Each instrument runs two command lists once per tick: the pitch list
(waveform, transpose, bends, vibrato) and the volume list. A pattern note
only stops the channel; the pitch list starts the sound.
"""

from dataclasses import dataclass, field

from hardware import paula
from hardware.amiga import Amiga, Priority
from specs.controls import CommandList, StateMachine

VOICES = 4
ROWS = 32  # a pattern: 32 rows of 2 bytes
ROW_SIZE = 2
PATTERN_END = 0x49  # a note byte that ends the pattern early
POSITION_SIZE = 13  # 4 × (pattern, transpose, instrument transpose), speed
LIST_SIZE = 64  # a pattern, a pitch list, an instrument
VOLUME_HEADER = 5  # an instrument's bytes before its volume list
SAMPLES, WAVEFORMS = 10, 80
DEFAULT_SPEED = 3
SPEED_EVENTS = 4  # pattern ends between two speed reads
LOCKED = 0x80  # a pitch list byte with bit 7: a fixed note
INSTRUMENT_MASK = 0x3F
PORTA_UP_MAX = 0x1F  # portamento bytes above this slide down
LOWEST, HIGHEST = 0xD60, 0x71  # period limits
LOOP_DELAY = 3  # the loop is written when this counts down past 2
VIBRATO_START = 0x40  # the state byte at note start; bit 5: rising
RISING = 0x20
DMA_ON_CCK = 400  # the rest of the tick's work before DMA on (guess)

LIST_END, LIST_LOOP, SET_WAVE, SET_VIBRATO = 0xE1, 0xE0, 0xE2, 0xE3
CHANGE_WAVE, JUMP, WAIT, PACK, BEND = 0xE4, 0xE7, 0xE8, 0xE9, 0xEA
PACK_MAGIC = b"SSMP"
PACK_DATA = 4 + 320  # a pack's data follows the magic and 20 entries

PERIODS = (  # 128 entries: two 4-octave runs with clamped and low gaps
    *(1712, 1616, 1524, 1440, 1356, 1280, 1208, 1140, 1076, 1016, 960, 906),
    *(856, 808, 762, 720, 678, 640, 604, 570, 538, 508, 480, 453),
    *(428, 404, 381, 360, 339, 320, 302, 285, 269, 254, 240, 226),
    *(214, 202, 190, 180, 170, 160, 151, 143, 135, 127, 120, 113),
    *(113,) * 12,
    *(3424, 3232, 3048, 2880, 2712, 2560, 2416, 2280, 2152, 2032, 1920, 1812),
    *(6848, 6464, 6096, 5760, 5424, 5120, 4832, 4560, 4304, 4064, 3840, 3624),
    *(1712, 1616, 1524, 1440, 1356, 1280, 1208, 1140, 1076, 1016, 960, 906),
    *(856, 808, 762, 720, 678, 640, 604, 570, 538, 508, 480, 453),
    *(428, 404, 381, 360, 339, 320, 302, 285, 269, 254, 240, 226),
    *(214, 202, 190, 180, 170, 160, 151, 143, 135, 127, 120, 113),
)


# --- What the composer edits -------------------------------------------


@dataclass
class Sound:  # SampleInfo: 10 samples, then 80 waveforms
    data: bytes  # from the start; a sample pack starts with "SSMP"
    length: int  # words
    repeat_start: int  # bytes
    repeat_length: int  # words


@dataclass
class Position:  # 13 bytes at PositionTable
    patterns: list[int]  # per voice
    transposes: list[int]  # per voice: added to notes
    instrument_transposes: list[int]  # per voice: added to instrument numbers
    speed: int  # ticks per row; 0 keeps the speed


@dataclass
class Score:  # the module after InitMusic
    sequence: bytes  # PositionTable: the positions' raw bytes
    positions: list[Position]
    patterns: list[bytes]  # PatternTable: 64 bytes each
    pitch_lists: list[bytes]  # PitchListTable: 64 bytes each
    instruments: list[bytes]  # InstrumentTable: 64 bytes each
    sounds: list[Sound]


# --- Voice state -------------------------------------------------------


@dataclass
class PitchList(CommandList):  # 18 list, 50 pos, 26 wait
    steps: bytes = bytes([LIST_END])
    transpose: int = 0  # 43: this tick's step; bit 7: a fixed note


@dataclass
class VolumeList(CommandList):  # 10 list, 16 pos, 25 wait, 23 counter, 24 speed
    steps: bytes = bytes([LIST_END])


@dataclass
class Bend(StateMachine):  # pitch: 4, 5, 42; volume: 14, 15, 38
    step: int = 0  # signed byte
    time: int = 0  # steps left
    flip: bool = False  # it acts every second tick


@dataclass
class Vibrato(StateMachine):  # 27 speed, 28 depth, 29 pos, 30 delay, 46 state
    speed: int = 0
    depth: int = 0
    pos: int = 0
    delay: int = 0
    state: int = VIBRATO_START


@dataclass
class Voice:  # Voice1Data: 74 bytes per voice
    channel: paula.Channel
    number: int
    position: int = 1  # 6: the next position; the first is read at init
    pattern: int = 0  # 34: its number
    row: int = 0  # 40: bytes into the pattern
    transpose: int = 0  # 44
    instrument_transpose: int = 0  # 22
    note: int = 0  # 8
    pitch: PitchList = field(default_factory=PitchList)
    volume_list: VolumeList = field(default_factory=VolumeList)
    volume: int = 0  # 45
    vibrato: Vibrato = field(default_factory=Vibrato)
    pitch_bend: Bend = field(default_factory=Bend)
    volume_bend: Bend = field(default_factory=Bend)
    porta: int = 0  # 47: speed; 0 off
    porta_flip: bool = False  # 39
    slide: int = 0  # 56: portamento and pitch bend, in period units
    sound: bytes = b""  # 68: the running sound's start
    loop_countdown: int = 0  # 72
    repeat_start: int = 0  # 64
    repeat_length: int = 0  # 66


@dataclass
class Module:  # DmaStartMask, SpeedEvents, TickCounter, TicksPerRow, MusicOn
    score: Score
    amiga: Amiga
    voices: list[Voice] = field(default_factory=list)
    dma_on: set[int] = field(default_factory=set)  # DmaStartMask: voices to start
    speed_events: int = 0  # SpeedEvents: pattern ends since the last speed read
    counter: int = 1  # TickCounter
    speed: int = DEFAULT_SPEED  # TicksPerRow
    playing: bool = False  # MusicOn


def signed(byte: int) -> int:
    return byte - 256 if byte & 0x80 else byte


def new_module(score: Score, amiga: Amiga) -> Module:
    """Play runs once per vertical blank."""
    module = Module(score, amiga)
    module.voices = [Voice(c, n) for n, c in enumerate(amiga.paula.channels)]
    amiga.vblank.handler = lambda: Play(module)
    return module


def InitMusic(module: Module) -> None:
    """Each voice reads position 0. The speed comes from
    position 0, or 3. Samples and waveforms are set up by the loader;
    see LoadModule."""
    first = module.score.positions[0]
    module.speed = module.counter = first.speed or DEFAULT_SPEED
    module.speed_events = 0
    for voice in module.voices:
        voice.position = 1
        voice.row = 0
        voice.pattern = first.patterns[voice.number]
        voice.transpose = first.transposes[voice.number]
        voice.instrument_transpose = first.instrument_transposes[voice.number]
    module.playing = True


def LoadModule(data: bytes) -> Score:
    """The FC14 header: the positions' length; offset and length of the
    patterns, pitch lists and instruments; offsets of the samples and
    waveforms. Then 10 sample headers and 80 waveform lengths. Each
    sample is followed by 2 spare bytes."""

    def long(at: int) -> int:
        return int.from_bytes(data[at : at + 4], "big")

    def word(at: int) -> int:
        return int.from_bytes(data[at : at + 2], "big")

    count = long(4) // POSITION_SIZE
    positions = []
    for n in range(count):
        at = 180 + n * POSITION_SIZE
        entry = data[at : at + POSITION_SIZE]
        positions.append(
            Position(
                patterns=[entry[3 * v] for v in range(VOICES)],
                transposes=[entry[3 * v + 1] for v in range(VOICES)],
                instrument_transposes=[entry[3 * v + 2] for v in range(VOICES)],
                speed=entry[12],
            )
        )

    def blocks(start: int, end: int) -> list[bytes]:
        return [data[at : at + LIST_SIZE] for at in range(start, end, LIST_SIZE)]

    sounds = []
    at = long(32)
    for n in range(SAMPLES):
        length = word(40 + 6 * n)
        sounds.append(Sound(data[at:], length, word(42 + 6 * n), word(44 + 6 * n)))
        at += 2 * length + 2
    at = long(36)
    for n in range(WAVEFORMS):
        length = data[100 + n]
        sounds.append(Sound(data[at:], length, 0, length))
        at += 2 * length
    return Score(
        data[180 : 180 + count * POSITION_SIZE],
        positions,
        blocks(long(8), long(8) + long(12)),
        blocks(long(16), long(16) + long(20)),
        blocks(long(24), long(24) + long(28)),
        sounds,
    )


# --- Tick ---------------------------------------------------------------


def Play(module: Module) -> None:
    """Rows every `speed` ticks. Then, per voice: pitch list, volume list,
    period and volume. DMA goes on only for voices whose pitch list set a
    wave this tick: the bits a row sets are cleared first."""
    if not module.playing:
        return
    module.counter -= 1
    if module.counter == 0:
        module.counter = module.speed
        for voice in module.voices:
            NewRow(module, voice)
    module.dma_on.clear()
    for voice in module.voices:
        period = VoiceTick(module, voice)
        voice.channel.period = period
        voice.channel.set_volume(voice.volume)
    starting = [module.voices[n] for n in sorted(module.dma_on)]

    def dma_on() -> None:
        for voice in starting:
            voice.channel.enable()
        for voice in module.voices:
            WriteLoops(voice)

    module.amiga.after(DMA_ON_CCK, Priority.CPU, dma_on)


def WriteLoops(voice: Voice) -> None:
    """For each channel: a tick after a wave starts, its loop goes to AUDxLC and
    AUDxLEN. No busy-wait: a tick is far longer than a DMA start."""
    before = voice.loop_countdown
    if not before:
        return
    voice.loop_countdown -= 1
    if before != LOOP_DELAY - 1:
        return
    voice.loop_countdown = 0
    loop = voice.sound[
        voice.repeat_start : voice.repeat_start + 2 * voice.repeat_length
    ]
    voice.channel.queue(paula.Sample(loop))


# --- Rows ---------------------------------------------------------------


def NewRow(module: Module, voice: Voice) -> None:
    """After 32 rows, or at an $49 note, the voice reads its
    next position; each voice steps on its own."""
    pattern = module.score.patterns[voice.pattern]
    if voice.row == ROWS * ROW_SIZE or pattern[voice.row] == PATTERN_END:
        NextPosition(module, voice)
    ReadNote(module, voice)


def NextPosition(module: Module, voice: Voice) -> None:
    """After the last position, the song restarts at position 0."""
    voice.row = 0
    positions = module.score.positions
    if voice.position == len(positions):
        voice.position = 0  # SongEnd tells the host
    ReadSpeed(module, voice)
    position = positions[voice.position]
    voice.pattern = position.patterns[voice.number]
    voice.transpose = position.transposes[voice.number]
    voice.instrument_transpose = position.instrument_transposes[voice.number]
    voice.position += 1


def ReadSpeed(module: Module, voice: Voice) -> None:
    """A counter over all voices' pattern ends: the first read is
    the fifth, then every fourth. With equal pattern lengths, voice 1
    reads each position's speed, except position 1's. Another voice
    reads the byte 3 × its number further on: in the next position."""
    module.speed_events += 1
    if module.speed_events != SPEED_EVENTS + 1:
        return
    module.speed_events = 1
    at = voice.position * POSITION_SIZE + 3 * voice.number + 12
    sequence = module.score.sequence
    speed = sequence[at] if at < len(sequence) else 0
    if speed:
        module.speed = module.counter = speed


def ReadNote(module: Module, voice: Voice) -> None:
    """A note clears the slide. A row with info bit 7 takes its
    portamento speed from the next row's info byte; bit 6 alone, on an
    empty row, turns portamento off."""
    pattern = module.score.patterns[voice.pattern]
    note, info = pattern[voice.row], pattern[voice.row + 1]
    if note or info & 0xC0:
        if note:
            voice.slide = 0
        voice.porta = 0
        if info & 0x80:
            voice.porta = SlideSpeed(module, voice)
    if note & 0x7F:
        StartInstrument(module, voice, note & 0x7F, info)
    voice.row += ROW_SIZE


def SlideSpeed(module: Module, voice: Voice) -> int:
    """The next row's info byte. On the last row, it is the next
    pattern's first info byte in memory."""
    at = voice.row + 3
    number = voice.pattern + at // LIST_SIZE
    patterns = module.score.patterns
    return patterns[number][at % LIST_SIZE] if number < len(patterns) else 0


def StartInstrument(module: Module, voice: Voice, note: int, info: int) -> None:
    """DMA off. The instrument: volume speed, pitch list number,
    vibrato speed, depth and delay, then the volume list. Both lists and
    the vibrato restart; bends, the last transpose step, slide and
    portamento carry on."""
    voice.note = note
    voice.channel.disable()
    number = AddInstrTranspose(voice, info)
    instrument = module.score.instruments[number]
    voice.volume_list = VolumeList(
        steps=instrument[VOLUME_HEADER:], counter=instrument[0], speed=instrument[0]
    )
    voice.pitch = PitchList(
        steps=module.score.pitch_lists[instrument[1]], transpose=voice.pitch.transpose
    )
    voice.vibrato = Vibrato(instrument[2], instrument[3], instrument[3], instrument[4])


def AddInstrTranspose(voice: Voice, info: int) -> int:
    """64 instruments; the position's instrument transpose is added."""
    return ((info & INSTRUMENT_MASK) + voice.instrument_transpose) & 0xFF


# --- Pitch list ---------------------------------------------------------


def VoiceTick(module: Module, voice: Voice) -> int:
    """The pitch list, the volume list, then the period."""
    PitchListTick(module, voice)
    VolumeListTick(voice)
    return CalcPeriod(voice)


def PitchListTick(module: Module, voice: Voice) -> None:
    """A wait skips the list. A step is at most one command,
    then one transpose byte. $e1 ends the list; $e0 loops it once."""
    pitch = voice.pitch
    if pitch.wait:
        pitch.wait -= 1
        return
    ReadPitchList(module, voice)


def ReadPitchList(module: Module, voice: Voice) -> None:
    """After an $e0 loop, the new byte is not checked for
    $e0 or $e1 again."""
    pitch = voice.pitch
    byte = pitch.steps[pitch.pos]
    if byte == LIST_END:
        return
    if byte == LIST_LOOP:
        pitch.pos = pitch.steps[pitch.pos + 1] & 0x3F
        byte = pitch.steps[pitch.pos]
    args = pitch.steps[pitch.pos + 1 : pitch.pos + 3]
    if byte == SET_WAVE:
        SetWave(module, voice, args[0])
    elif byte == CHANGE_WAVE:
        ChangeWave(module, voice, args[0])
    elif byte == PACK:
        SampleFromPack(module, voice, args[0], args[1])
    elif byte == JUMP:
        PitchListJump(module, voice, args[0])
        return
    elif byte == BEND:
        voice.pitch_bend.step, voice.pitch_bend.time = args[0], args[1]
        pitch.pos += 3
    elif byte == WAIT:
        PitchWait(module, voice, args[0])
        return
    elif byte == SET_VIBRATO:
        voice.vibrato.speed, voice.vibrato.depth = args[0], args[1]
        pitch.pos += 3
    ReadTranspose(voice)


def ReadTranspose(voice: Voice) -> None:
    """transpose. Every step ends with one: bit 7 set is a fixed note."""
    pitch = voice.pitch
    pitch.transpose = pitch.steps[pitch.pos]
    pitch.pos += 1


def start_sound(
    voice: Voice, sound: bytes, length: int, start: int, words: int
) -> None:
    voice.channel.queue(paula.Sample(sound[: 2 * length]))
    voice.sound, voice.repeat_start, voice.repeat_length = sound, start, words
    voice.loop_countdown = LOOP_DELAY


def SetWave(module: Module, voice: Voice, number: int) -> None:
    """$e2. DMA off; DMA on at the tick's end. The volume
    list restarts."""
    voice.channel.disable()
    module.dma_on.add(voice.number)
    sound = module.score.sounds[number]
    start_sound(
        voice, sound.data, sound.length, sound.repeat_start, sound.repeat_length
    )
    RestartVolList(voice)
    voice.pitch.pos += 2


def RestartVolList(voice: Voice) -> None:
    voice.volume_list.pos, voice.volume_list.counter = 0, 1


def ChangeWave(module: Module, voice: Voice, number: int) -> None:
    """$e4. DMA stays on: the new wave starts at the next loop
    end. The volume list runs on."""
    sound = module.score.sounds[number]
    start_sound(
        voice, sound.data, sound.length, sound.repeat_start, sound.repeat_length
    )
    voice.pitch.pos += 2


def SampleFromPack(module: Module, voice: Voice, number: int, entry: int) -> None:
    """$e9. A sample that starts with "SSMP" holds up to 20
    samples. An entry: data offset, length, repeat start, repeat length.
    DMA off and on as $e2; the volume list restarts. Without the magic,
    DMA is still switched."""
    voice.channel.disable()
    module.dma_on.add(voice.number)
    pack = module.score.sounds[number].data
    if pack[:4] == PACK_MAGIC:
        at = 4 + 16 * entry
        offset = int.from_bytes(pack[at : at + 4], "big")
        length, start, words = (
            int.from_bytes(pack[at + n : at + n + 2], "big") for n in (4, 6, 8)
        )
        start_sound(voice, pack[PACK_DATA + offset :], length, start, words)
        RestartVolList(voice)
    voice.pitch.pos += 3


def PitchListJump(module: Module, voice: Voice, number: int) -> None:
    """$e7. Another pitch list, from its start, at once."""
    voice.pitch.steps, voice.pitch.pos = module.score.pitch_lists[number], 0
    ReadPitchList(module, voice)


def PitchWait(module: Module, voice: Voice, ticks: int) -> None:
    """$e8. The list waits; this tick counts. A wait of 0
    reads on at once."""
    voice.pitch.wait = ticks
    voice.pitch.pos += 2
    PitchListTick(module, voice)


# --- Volume list --------------------------------------------------------


def VolumeListTick(voice: Voice) -> None:
    """A wait or a running volume bend skips the list. Else it
    steps every `speed` ticks: $ea bends, $e8 waits, $e0 loops, $e1
    ends; any other byte is the volume."""
    vol = voice.volume_list
    if vol.wait:
        vol.wait -= 1
        return
    if voice.volume_bend.time:
        VolumeBend(voice)
        return
    vol.counter = (vol.counter - 1) & 0xFF
    if vol.counter:
        return
    vol.counter = vol.speed
    ReadVolume(voice)


def ReadVolume(voice: Voice) -> None:
    """$e0's argument counts from the instrument's start, so 5
    is subtracted."""
    vol = voice.volume_list
    while True:
        byte = vol.steps[vol.pos]
        if byte == LIST_END:
            return
        if byte == BEND:
            voice.volume_bend.step = vol.steps[vol.pos + 1]
            voice.volume_bend.time = vol.steps[vol.pos + 2]
            vol.pos += 3
            VolumeBend(voice)
            return
        if byte == WAIT:
            vol.wait = vol.steps[vol.pos + 1]
            vol.pos += 2
            return
        if byte == LIST_LOOP:
            VolumeLoop(voice)
            continue
        voice.volume = byte
        vol.pos += 1
        return


def VolumeLoop(voice: Voice) -> None:
    """$e0."""
    vol = voice.volume_list
    vol.pos = ((vol.steps[vol.pos + 1] & 0x3F) - VOLUME_HEADER) & 0xFFFF


def VolumeBend(voice: Voice) -> None:
    """Every second tick, the volume moves by a signed step.
    Past 127 it wraps negative: the volume and the bend drop to 0."""
    bend = voice.volume_bend
    bend.flip = not bend.flip
    if not bend.flip:
        return
    bend.time = (bend.time - 1) & 0xFF  # a bend of time 0 runs 255 steps
    voice.volume = (voice.volume + bend.step) & 0xFF
    if voice.volume & 0x80:
        voice.volume = bend.time = 0


# --- Period -------------------------------------------------------------


def CalcPeriod(voice: Voice) -> int:
    """Note + position transpose + pitch list transpose, or a
    fixed note; then vibrato, portamento and pitch bend."""
    index = LockedNote(voice)
    period = PERIODS[index] + VibratoTick(voice, index)
    DoSlide(voice)
    PitchBend(voice)
    return ClampPeriod(period + voice.slide)


def LockedNote(voice: Voice) -> int:
    """A pitch list byte with bit 7 ignores both transposes
    and the note."""
    step = voice.pitch.transpose
    if step & LOCKED:
        return step & 0x7F
    return (step + voice.note + voice.transpose) & 0x7F


def VibratoTick(voice: Voice, index: int) -> int:
    """After the delay, a triangle between 0 and 2 × depth,
    `speed` per tick, starting at depth and falling. The offset doubles
    for each octave below index 48, so its width in semitones stays
    about the same. State bit 7 would skip every second update; nothing
    sets it."""
    vib = voice.vibrato
    offset = 0
    if vib.delay:
        vib.delay -= 1
    else:
        top = (vib.depth * 2) & 0xFF
        if vib.state & RISING:
            vib.pos = (vib.pos + vib.speed) & 0xFF
            if vib.pos >= top:
                vib.state &= ~RISING
                vib.pos = top
        else:
            vib.pos -= vib.speed
            if vib.pos < 0:
                vib.state |= RISING
                vib.pos = 0
        offset = vib.pos - (top >> 1)
        scale = (2 * index + 0xA0) & 0x1FF
        while scale < 0x100:
            offset *= 2
            scale += 0x18
    vib.state ^= 1
    return offset


def DoSlide(voice: Voice) -> None:
    """Portamento, every second tick: $01-$1f slides up, $21-$3f down."""
    voice.porta_flip = not voice.porta_flip
    if not voice.porta_flip or not voice.porta:
        return
    if voice.porta <= PORTA_UP_MAX:
        voice.slide -= voice.porta
    else:
        voice.slide += voice.porta & PORTA_UP_MAX


def PitchBend(voice: Voice) -> None:
    """Every second tick, while time lasts: the slide moves by
    the signed step. Positive steps raise the pitch."""
    bend = voice.pitch_bend
    bend.flip = not bend.flip
    if not bend.flip or not bend.time:
        return
    bend.time -= 1
    voice.slide -= signed(bend.step)


def ClampPeriod(period: int) -> int:
    """The period stays within 113..3424. The compare is
    unsigned, so a negative sum gives 3424."""
    period &= 0xFFFF
    if period < HIGHEST:
        period = HIGHEST
    return min(period, LOWEST)
