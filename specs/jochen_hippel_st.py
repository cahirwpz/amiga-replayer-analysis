"""Jochen Hippel's Atari ST replay, run on the Amiga through a sound chip
emulator. Jochen Hippel ST_v4.asm, Wanted Team's adaptation (V1.3, 2008).

Card: players/Jochen_Hippel_ST.md. Level 2: the control flow runs.
Each CamelCase function is a label in data/annot/Jochen_Hippel_ST.yaml;
each CamelCase class is in its `types:`. Comments name the voice fields
by their offsets in lbL000E72.

The ST replay drives three voices. It writes YM2149 registers into a copy
in RAM. After it, EmuTick turns the three chip channels into Paula
channels 0, 3 and 2. Paula channel 1 plays samples and the `SID` pulse.
DeliTracker's volume, balance and analyzer hooks (ChangeVolume, SetVol,
SetPer, SetTwo) are left out.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import partial

from hardware import paula
from hardware.amiga import Amiga, Priority
from hardware.clock import LINE_CCK
from specs.controls import CommandList, StateMachine

CHIP_VOICES = 3
PAULA_OF_CHIP = (0, 3, 2)  # EmuTick: chip channels A, B, C
DIGI_CHANNEL = 1
POSITION_SIZE = 12  # 4 bytes per voice: pattern, transpose, instr. transpose, flags
SUBSONG_SIZE = 6  # first position, last position, speed
DEFAULT_SPEED = 4  # InitSound: a subsong with speed 0
VOLUME_HEADER = 5  # an instrument's bytes before its volume list
DEFAULT_LATCH = 14187  # DeliTracker's timer, 50 Hz (guess): no DTP_Timer tag

# Pattern bytes
PATTERN_END, SET_LENGTH, REST = 0xFF, 0xFE, 0xFD
LEGATO = 0x80  # a note byte with bit 7: the lists run on
HAS_ARG = 0xE0  # flag bits that add a third byte
SLIDE, OWN_PITCH_LIST = 0x20, 0x40
INSTRUMENT_MASK = 0x1F

# Position flags
VOLUME_OFFSET, SET_SPEED = 0xF0, 0xE0

# Pitch list and volume list opcodes
LOOP, HOLD, RESTART_VOLUME, VIBRATO, TONE_NOISE = 0xE0, 0xE1, 0xE2, 0xE3, 0xE4
NOISE_ONLY, TONE_ONLY, DIGI_OFF, WAIT, SKIP = 0xE5, 0xE6, 0xE7, 0xE8, 0xE9
DIGI_ON = 0xEA
FIRST_NOTE = 0xEB  # without TypePlay, bytes from here on are notes
LATER_OPCODES = 0xEF  # with TypePlay: $eb-$ef are opcodes too
LOOP_MASK = 0x3F  # without TypePlay, a loop target is masked
FIXED = 0x80  # a pitch list byte with bit 7: a fixed note

# Voice modes, field $32
BOTH, NOISE, TONE = 0, 1, 2

# Chip registers in RegisterShadow
TONE_LO = (0, 2, 4)
TONE_HI = (1, 3, 5)
NOISE_PERIOD, MIXER = 6, 7
LEVEL = (8, 9, 10)
ENVELOPE_MODE = 0x10  # a volume register bit

PERIODS = (  # lbW000F70: YM2149 tone periods, 8 octaves; 32 zeros follow
    *(3822, 3607, 3405, 3214, 3033, 2863, 2702, 2551, 2407, 2272, 2145, 2024),
    *(1911, 1803, 1702, 1607, 1516, 1431, 1351, 1275, 1203, 1136, 1072, 1012),
    *(955, 901, 851, 803, 758, 715, 675, 637, 601, 568, 536, 506),
    *(477, 450, 425, 401, 379, 357, 337, 318, 300, 284, 268, 253),
    *(238, 225, 212, 200, 189, 178, 168, 159, 150, 142, 134, 126),
    *(119, 112, 106, 100, 94, 89, 84, 79, 75, 71, 67, 63),
    *(59, 56, 53, 50, 47, 44, 42, 39, 37, 35, 33, 31),
    *(29, 28, 26, 25, 23, 22, 21, 19, 18, 17, 16, 15),
    *(0,) * 32,
)
OCTAVE_NOTE = 48  # OctaveVibrato: below this note, the offset doubles per octave

# Emulator
VOLUME_TABLE = (0, 1, 2, 3, 4, 6, 8, 10, 13, 16, 20, 24, 30, 38, 48, 64, 32)
TONE_FACTOR = 7  # Paula period = chip period × 7 + 1
NOISE_PERIODS = tuple(0x280 - 16 * n for n in range(32))  # by noise register
SILENT_PERIOD = 0x100
LEVELS = (0x80, 0x93, 0xA7, 0xBF, 0xCF, 0xDF, 0xEF, 0xFF)  # Bit8Table, signed
LEVELS_HIGH = (0x0F, 0x1F, 0x2F, 0x3F, 0x4F, 0x5F, 0x6F, 0x7F)
BIT8 = LEVELS + LEVELS_HIGH
SID_LOW = 0x80  # SIDword's first byte
SID_MIN, SID_MAX = 0x10, 0xEEE  # periods outside turn the pulse off
NOISE_SIZE = 1024
NOISE_SEED = int.from_bytes(b"HIPP", "big")
SLOTS_END = 0x16  # NotePlay waits until this beam position, after audio DMA
POLL_CCK = 15  # one INTREQR poll: about 30 68000 cycles (estimate)
DIGI_VOLUME = 0x40
DIGI_LOOP = 0x10  # an end word of $10: a 16-byte looped wave
DIGI_BASE_NOTE = 72  # TypePeriod: this note plays at Period

DEFAULT_LIST = bytes([1, 0, 0, 0, 0, 0, 0, HOLD])  # lbW000E1A: both lists at init
SQUARE = paula.Sample(bytes([0xB2, 0xB2, 0x4D, 0x4D]))  # -78, -78, 77, 77
EMPTY = paula.Sample(bytes(2))  # lbL001470

Then = Callable[[], None]


# --- What the composer edits -------------------------------------------


@dataclass
class Subsong:  # 6 bytes at lbL000F5A
    first: int  # position
    last: int
    speed: int  # ticks per row; InitSound sets 0 to 4


@dataclass
class Instrument:  # at lbL000F4E: 5 header bytes, then the volume list
    speed: int  # +0: ticks per volume list visit
    pitch_list: int  # +1
    vibrato_speed: int  # +2
    vibrato_depth: int  # +3
    vibrato_delay: int  # +4
    volume_list: bytes


@dataclass
class DigiSample:  # 8 bytes at lbL000F6A
    start: int  # +0: offset in the sample data
    end: int  # +2: 0: the next entry's start; $10: a 16-byte loop


@dataclass
class Score:  # lbL000F66: a 'COSO' module after InitPlay
    positions: bytes  # lbL000F52: rows of POSITION_SIZE
    patterns: list[bytes]  # lbL000F46
    pitch_lists: list[bytes]  # lbL000F4A
    instruments: list[Instrument]  # lbL000F4E
    subsongs: list[Subsong]  # lbL000F5A
    samples: list[DigiSample]
    sample_data: bytes
    scaled: bool  # lbB000F6F: 'MMME' at +$20; see ScaledVibrato
    all_opcodes: bool  # TypePlay: $e0-$ef are all opcodes
    digi_period: int  # Period: from the ST replay's timer data, or $248
    digi_notes: bool  # TypePeriod: StartDigi reads a note byte
    sid_stub: bool  # TypeSID: an 'MMME' module with $ef; SidVoice is skipped


# --- ST replay state -----------------------------------------------------


@dataclass
class PitchReader(CommandList):  # 8 list, $18 pos, $25 wait; speed 1
    steps: bytes = bytes([HOLD])
    step: int = 0  # $26: the last note byte; bit 7: a fixed note


@dataclass
class VolumeReader(CommandList):  # 4 list, $16 pos, $24 wait, $22 counter, $23 speed
    steps: bytes = bytes([HOLD])


@dataclass
class Vibrato(StateMachine):  # $27 speed, $28 depth, $29 pos, $2A delay, $2B state
    speed: int = 0
    depth: int = 0
    pos: int = 0
    delay: int = 0
    flip: bool = False  # $2B bit 5; its meaning differs per vibrato


@dataclass
class Voice:  # lbL000E72, lbL000EA6, lbL000EDA: $38 bytes each
    number: int
    column: int  # $2E: which 4 bytes of a position this voice reads
    position: int = 0  # $14 / 12: the next position to read
    pattern: bytes = b""  # 12
    row: int = 0  # bytes into the pattern
    counter: int = 0  # $1A: rows left in the note
    length: int = 0  # $1B
    positions_left: int = 0  # $1C: counted by voice 0 only
    note: int = 0  # $1E
    flags: int = 0  # $1F: instrument in bits 0-4
    arg: int = 0  # $2C: the third byte
    transpose: int = 0  # $21
    instrument_transpose: int = 0  # $20
    volume_offset: int = 0  # $30
    pitch: PitchReader = field(default_factory=PitchReader)
    volume_list: VolumeReader = field(default_factory=VolumeReader)
    volume: int = 0  # $2F
    vibrato: Vibrato = field(default_factory=Vibrato)
    slide: int = 0  # $10: the sum of slide steps
    mode: int = TONE  # $32
    noise: int = 0  # $2D: 0 leaves the noise register alone
    tone_flags: int = 0  # $33
    period: int = 0  # $34: SID1, SID2, SID3 read it
    sid_mode: int = -1  # $36: voice A's only is read


@dataclass
class ChipRegisters:  # RegisterShadow: registers 0-10 of the YM2149
    values: list[int] = field(default_factory=lambda: [0] * 11)


# --- Emulator state ------------------------------------------------------


@dataclass
class EmuState:  # lbL000616, lbL000622, lbL00062E: 12 bytes each
    volume: int = 0  # +0
    period: int = 0  # +2
    playing: int = 0  # +10: 0 silence, 1 tone, 2 noise


@dataclass
class DigiState:  # lbW0004C8 and its neighbours
    state: int = 0  # 0 off, 1 start, 2 playing
    sample: paula.Sample = field(default_factory=lambda: EMPTY)  # lbL0004BE
    loop: paula.Sample = field(default_factory=lambda: EMPTY)  # RepStart
    period: int = 0x240  # lbW0004C4
    volume: int = 0x40  # lbW0004C6; negative: channel A's volume


@dataclass
class Module:
    score: Score
    amiga: Amiga
    voices: list[Voice] = field(default_factory=list)
    registers: ChipRegisters = field(default_factory=ChipRegisters)
    mixer: int = 0  # lbL000E64: bit n clear enables tone n, n+3 noise n
    noise: int = 0  # lbL000E64 + 1
    counter: int = 1  # lbW000E6C: ticks to the next row
    speed: int = DEFAULT_SPEED  # lbW000E6E
    stop: bool = False  # lbW000E70
    silenced: bool = False  # lbW000E70 + 1
    first: int = 0  # the subsong's first position
    song_length: int = 0  # lbW000F44: positions after the first
    emu: list[EmuState] = field(default_factory=list)
    digi: DigiState = field(default_factory=DigiState)
    noise_sample: paula.Sample = field(default_factory=lambda: EMPTY)


def new_module(score: Score, amiga: Amiga) -> Module:
    """DeliTracker calls Interrupt by its own timer."""
    module = Module(score, amiga)
    module.voices = [Voice(n, n) for n in range(CHIP_VOICES)]
    module.emu = [EmuState() for _ in range(CHIP_VOICES)]
    module.noise_sample = InitSamp()
    amiga.timer.on_underflow = lambda: Interrupt(module)
    amiga.timer.set_latch(DEFAULT_LATCH)
    return module


def InitSamp() -> paula.Sample:
    """InitPlayer fills the noise sample once: 1024 bytes of NoiseRandom.
    The channel loops it, so the noise repeats every 1024 bytes."""
    seed, data = NOISE_SEED, bytearray()
    for _ in range(NOISE_SIZE):
        seed, byte = NoiseRandom(seed)
        data.append(byte)
    return paula.Sample(bytes(data))


def NoiseRandom(seed: int) -> tuple[int, int]:
    """x × 3677, plus the low word of x + $e90 shifted left 4,
    bit 31 cleared, minus 1. The byte is bits 8-15."""
    mask = 0xFFFFFFFF
    product = seed * 3677 & mask
    added = seed + 0xE90 & mask
    added = added & 0xFFFF0000 | added << 4 & 0xFFFF
    seed = ((product + added & mask) & 0x7FFFFFFF) - 1 & mask
    return seed, seed >> 8 & 0xFF


def InitPlay(data: bytes, word_offsets: bool, all_opcodes: bool) -> Score:
    """A 'COSO' module; InitPlayer packs an older one with Compress first.
    Header longs at +4 to +$1c: offsets of the pitch lists, instruments,
    patterns, positions, subsongs and samples. Each table holds word
    offsets (TypeAdr) or long offsets. Words: +$24 the highest pitch list,
    +$26 the highest instrument, +$30 the subsong count."""

    def word(at: int) -> int:
        return int.from_bytes(data[at : at + 2], "big")

    def long(at: int) -> int:
        return int.from_bytes(data[at : at + 4], "big")

    def table(header: int, count: int) -> list[bytes]:
        base, size = long(header), 2 if word_offsets else 4
        return [
            data[int.from_bytes(data[base + n * size : base + (n + 1) * size], "big") :]
            for n in range(count)
        ]

    rows = data[long(0x10) : long(0x14)]
    pattern_count = max(rows[0::4], default=0) + 1
    instruments = []
    for raw in table(8, word(0x26) + 1):
        speed, pitch_list, vib_speed, vib_depth, vib_delay = raw[:VOLUME_HEADER]
        instruments.append(
            Instrument(
                speed, pitch_list, vib_speed, vib_depth, vib_delay, raw[VOLUME_HEADER:]
            )
        )
    subsongs = []
    for n in range(word(0x30)):
        at = long(0x14) + n * SUBSONG_SIZE
        subsongs.append(Subsong(word(at), word(at + 2), word(at + 4)))
    samples, sample_data = [], data[long(0x1C) :] if long(0x1C) else b""
    for at in range(0, len(sample_data) - 7, 8):
        if at and not word(long(0x1C) + at):
            break
        samples.append(DigiSample(word(long(0x1C) + at), word(long(0x1C) + at + 2)))
    return Score(
        positions=data[long(0x10) :],
        patterns=table(12, pattern_count),
        pitch_lists=table(4, word(0x24) + 1),
        instruments=instruments,
        subsongs=subsongs,
        samples=samples,
        sample_data=sample_data,
        scaled=data[0x20:0x24] == b"MMME",
        all_opcodes=all_opcodes,
        digi_period=0x248,
        digi_notes=False,
        sid_stub=False,
    )


# --- Start and stop ------------------------------------------------------


def InitSound(module: Module, subsong: int) -> None:
    """The emulator resets, then the replay."""
    ResetEmu(module)
    Init(module, subsong)


def Init(module: Module, subsong: int) -> None:
    """Subsong 0 stops the music; see Play. Else InitSong."""
    if subsong == 0:
        module.stop = True
        return
    entry = module.score.subsongs[subsong - 1]
    module.speed = entry.speed or DEFAULT_SPEED
    InitSong(module, entry.first, entry.last)


def InitSong(module: Module, first: int, last: int) -> None:
    """Each voice reads the first position. Its flags set only the volume
    offset; the speed comes from the subsong. The first tick reads a
    row."""
    module.first, module.song_length = first, last - first
    for voice in module.voices:
        voice.pitch = PitchReader(steps=DEFAULT_LIST)
        voice.volume_list = VolumeReader(steps=DEFAULT_LIST, counter=1, speed=1)
        voice.vibrato = Vibrato(flip=voice.vibrato.flip)
        voice.note = voice.flags = voice.volume = voice.arg = voice.noise = 0
        voice.mode, voice.slide, voice.sid_mode, voice.tone_flags = TONE, 0, -1, 0
        voice.counter = 0
        voice.positions_left = module.song_length
        entry = position_entry(module, voice, first)
        voice.pattern = module.score.patterns[entry[0]]
        voice.row = 0
        voice.transpose, voice.instrument_transpose = signed(entry[1]), entry[2]
        voice.volume_offset = entry[3] & 0x0F if entry[3] & 0xF0 == 0xF0 else 0
        voice.position = first + 1
    module.counter = 1
    module.stop = module.silenced = False


def position_entry(module: Module, voice: Voice, position: int) -> bytes:
    at = position * POSITION_SIZE + voice.column * 4
    return module.score.positions[at : at + 4]


def signed(byte: int) -> int:
    return byte - 256 if byte & 0x80 else byte


# --- Tick ---------------------------------------------------------------


def Interrupt(module: Module) -> None:
    """Once per tick: the ST replay, then the emulator. The emulator's
    busy-waits delay the next steps."""
    Play(module)
    EmuTick(module, lambda: None)


def Play(module: Module) -> None:
    """Voices A, B, C run their lists and set their registers. Then the
    mixer and the noise register. Then, every `speed` ticks, each voice
    reads its pattern: a new note's lists first run on the next tick."""
    regs = module.registers.values
    if module.stop:
        if not module.silenced:
            module.silenced = True
            for n in (TONE_LO[2], TONE_HI[2], *LEVEL):
                regs[n] = 0
        return
    for voice in module.voices:
        period, volume = PitchList(module, voice)
        regs[TONE_LO[voice.number]] = period & 0xFF
        regs[TONE_HI[voice.number]] = period >> 8 & 0xFF
        regs[LEVEL[voice.number]] = volume
        if voice.number == 0 and not module.score.sid_stub:
            SidVoice(module, voice, period, volume)
    regs[MIXER] = module.mixer
    regs[NOISE_PERIOD] = module.noise
    module.counter -= 1
    if module.counter:
        return
    module.counter = module.speed
    for voice in module.voices:
        ReadPattern(module, voice)


# --- Sequencer ------------------------------------------------------------


def ReadPattern(module: Module, voice: Voice) -> None:
    """A note lasts its length + 1 rows. $ff ends the pattern, $fe sets the
    length, $fd sets it and rests."""
    voice.counter -= 1
    if voice.counter >= 0:
        return
    voice.counter = voice.length
    while True:
        byte = voice.pattern[voice.row]
        voice.row += 1
        if byte == PATTERN_END:
            NextPosition(module, voice)
        elif byte == SET_LENGTH:
            SetNoteLength(voice)
        elif byte == REST:
            Rest(voice)
            return
        else:
            ReadNote(module, voice, byte)
            return


def NextPosition(module: Module, voice: Voice) -> None:
    """Each voice steps at its own pattern end, so voices stay in step only
    if their patterns last equally long. Voice 0 counts the positions for
    all. Flags $fx set this voice's volume offset; $ex set the speed of
    all voices."""
    if voice.number == 0:
        voice.positions_left -= 1
        if voice.positions_left < 0:
            RestartSong(module)
    entry = position_entry(module, voice, voice.position)
    voice.transpose, voice.instrument_transpose = signed(entry[1]), entry[2]
    flags = entry[3]
    if flags & 0xF0 == VOLUME_OFFSET:
        voice.volume_offset = flags & 0x0F
    elif flags & 0xF0 == SET_SPEED:
        module.speed = flags & 0x0F
    voice.pattern, voice.row = module.score.patterns[entry[0]], 0
    voice.position += 1


def RestartSong(module: Module) -> None:
    """Voice 0 passed the last position. Every voice's next position is the
    first again; voices 1 and 2 finish their patterns first. SongEnd
    tells DeliTracker. The emulator resets and voice A's `SID` stops."""
    for voice in module.voices:
        voice.position = module.first
    module.voices[0].positions_left = module.song_length
    module.voices[0].sid_mode = -1
    ResetEmu(module)


def SetNoteLength(voice: Voice) -> None:
    """$fe n: later notes last n + 1 rows."""
    voice.length = voice.counter = voice.pattern[voice.row]
    voice.row += 1


def Rest(voice: Voice) -> None:
    """$fd n: set the length and read no note: the last note's
    lists run on."""
    SetNoteLength(voice)


def ReadNote(module: Module, voice: Voice, note: int) -> None:
    """A note byte, a flags byte, and a third byte if a flag in bits 5-7 is
    set. Bit 5: slide by the third byte. Bit 6: the third byte picks the
    pitch list. A note with bit 7 changes the pitch only: the lists run
    on. Else the instrument restarts both lists and the vibrato. The
    instrument number is the flags plus the instrument transpose."""
    score = module.score
    voice.note = note
    voice.flags = voice.pattern[voice.row]
    voice.row += 1
    if voice.flags & HAS_ARG:
        voice.arg = voice.pattern[voice.row]
        voice.row += 1
    voice.slide = 0
    if note & LEGATO:
        return
    number = (voice.flags & INSTRUMENT_MASK) + voice.instrument_transpose
    if number >= len(score.instruments):
        number = 0
    instrument = score.instruments[number]
    voice.volume_list = VolumeReader(
        steps=instrument.volume_list,
        counter=instrument.speed,
        speed=instrument.speed,
    )
    voice.vibrato = Vibrato(
        speed=instrument.vibrato_speed,
        depth=instrument.vibrato_depth,
        pos=instrument.vibrato_depth,
        delay=instrument.vibrato_delay,
    )
    pitch_list = voice.arg if voice.flags & OWN_PITCH_LIST else instrument.pitch_list
    if pitch_list >= len(score.pitch_lists):
        pitch_list = 0
    voice.pitch = PitchReader(
        steps=score.pitch_lists[pitch_list], step=voice.pitch.step
    )


# --- Pitch list -----------------------------------------------------------


PitchCommand = Callable[[Module, Voice], bool]  # True: read the next byte


def PitchList(module: Module, voice: Voice) -> tuple[int, int]:
    """Each tick: opcodes until a note byte, a hold or a wait. Then the
    volume list. Returns the chip period and the volume register."""
    voice.noise = 0
    reader = voice.pitch
    while True:
        if reader.wait:
            reader.wait -= 1
            break
        byte = reader.steps[reader.pos]
        command = PitchCommands(module.score, byte)
        if command is None:
            PitchNote(voice, byte)
            break
        if not command(module, voice):
            break
    return VolumeList(module, voice)


def PitchCommands(score: Score, byte: int) -> PitchCommand | None:
    """The jump table. Without TypePlay, $eb-$ef are notes, and so is $ea
    when the module has no samples."""
    if byte < LOOP or byte > LATER_OPCODES:
        return None
    if not score.all_opcodes:
        if byte >= FIRST_NOTE or (byte == DIGI_ON and not score.samples):
            return None
        return BASE_COMMANDS.get(byte)
    return LATER_COMMANDS.get(byte)


def PitchNote(voice: Voice, byte: int) -> None:
    """A note offset for this tick; see PitchToPeriod."""
    voice.pitch.step = byte
    voice.pitch.pos += 1


def arg(voice: Voice, n: int = 1) -> int:
    return voice.pitch.steps[voice.pitch.pos + n]


def PitchLoop(module: Module, voice: Voice) -> bool:
    """$e0 n: go to byte n."""
    target = arg(voice)
    voice.pitch.jump(target if module.score.all_opcodes else target & LOOP_MASK)
    return True


def PitchHold(module: Module, voice: Voice) -> bool:
    """$e1: stay here. With TypePlay, the byte before it is the
    note offset again."""
    if module.score.all_opcodes:
        voice.pitch.step = voice.pitch.steps[voice.pitch.pos - 1]
    return False


def RestartVolumeList(module: Module, voice: Voice) -> bool:
    """$e2: the volume list starts again and steps on this tick."""
    voice.volume_list.pos = 0
    voice.volume_list.counter = 1
    voice.pitch.pos += 1
    return True


def SetVibrato(module: Module, voice: Voice) -> bool:
    """$e3 speed depth."""
    voice.vibrato.speed, voice.vibrato.depth = arg(voice), arg(voice, 2)
    voice.pitch.pos += 3
    return True


def ToneAndNoise(module: Module, voice: Voice) -> bool:
    """$e4 n: tone and noise on; the noise register gets n this
    tick. The emulator plays only the tone; see EmuChannel."""
    voice.mode, voice.noise = BOTH, arg(voice)
    voice.pitch.pos += 2
    return True


def NoiseOnly(module: Module, voice: Voice) -> bool:
    """$e5: noise at the note's pitch; see PitchToPeriod."""
    voice.mode = NOISE
    voice.pitch.pos += 1
    return True


def ToneOnly(module: Module, voice: Voice) -> bool:
    """$e6."""
    voice.mode = TONE
    voice.pitch.pos += 1
    return True


def PitchWait(module: Module, voice: Voice) -> bool:
    """$e8 n: the pitch list pauses n ticks, this one included.
    The volume list runs on."""
    voice.pitch.wait = arg(voice)
    voice.pitch.pos += 2
    return True


def PitchListJump(module: Module, voice: Voice) -> bool:
    """$e7 n with TypePlay: go on in pitch list n. The code reads
    the list's offset through a register left from elsewhere; the model
    shows the intent (guess)."""
    lists = module.score.pitch_lists
    voice.pitch.steps = lists[min(arg(voice), len(lists) - 1)]
    voice.pitch.pos = 0
    return True


def SkipByte(module: Module, voice: Voice) -> bool:
    """$e9 n: no effect."""
    voice.pitch.pos += 2
    return True


def StopDigi(module: Module, voice: Voice) -> bool:
    """$e7, or $ed with TypePlay: Paula channel 1 goes silent."""
    module.digi.state = 0
    voice.pitch.pos += 1
    return True


def StartDigi(module: Module, voice: Voice) -> bool:
    """$ea n, or $ec n with TypePlay: sample n on Paula channel 1, at
    volume 64. An end word of $10 loops a 16-byte wave. The rate is
    Period. With TypePeriod a note byte follows; note 72 plays at Period,
    bit 7 makes it fixed."""
    score, digi = module.score, module.digi
    number = arg(voice)
    entry = score.samples[number]
    loop = EMPTY
    if entry.end == DIGI_LOOP:
        end = entry.start + DIGI_LOOP
        loop = paula.Sample(score.sample_data[entry.start : end])
    elif entry.end == 0:
        end = score.samples[number + 1].start
    else:
        end = entry.end
    digi.sample = paula.Sample(score.sample_data[entry.start : end])
    digi.loop = loop
    digi.volume = DIGI_VOLUME
    digi.period = score.digi_period
    voice.pitch.pos += 2
    if score.digi_notes:
        note = arg(voice, 0)
        voice.pitch.pos += 1
        if not note & FIXED:
            note += voice.note + voice.transpose
        note &= 0x7F
        if note < 96:
            ratio = 2 ** ((DIGI_BASE_NOTE - note) / 12)
            digi.period = int(score.digi_period * ratio) + 1
    digi.state = 1
    return True


def SlideCommand(module: Module, voice: Voice) -> bool:
    """$ea n with TypePlay: slide by n, as flag bit 5 does."""
    voice.flags, voice.arg = SLIDE, arg(voice)
    voice.pitch.pos += 2
    return True


def SetToneFlags(module: Module, voice: Voice) -> bool:
    """$eb n with TypePlay; see ToneFlags."""
    voice.tone_flags = arg(voice)
    voice.pitch.pos += 2
    return True


def SidCommand(module: Module, voice: Voice) -> bool:
    """$ee n with TypePlay: the `SID` mode; only voice A's counts.
    $ef n stores a byte that nothing reads."""
    if arg(voice, 0) == 0xEE:
        voice.sid_mode = signed(arg(voice))
    voice.pitch.pos += 2
    return True


BASE_COMMANDS: dict[int, PitchCommand] = {
    LOOP: PitchLoop,
    HOLD: PitchHold,
    RESTART_VOLUME: RestartVolumeList,
    VIBRATO: SetVibrato,
    TONE_NOISE: ToneAndNoise,
    NOISE_ONLY: NoiseOnly,
    TONE_ONLY: ToneOnly,
    DIGI_OFF: StopDigi,
    WAIT: PitchWait,
    SKIP: SkipByte,
    DIGI_ON: StartDigi,
}
LATER_COMMANDS: dict[int, PitchCommand] = {
    **BASE_COMMANDS,
    DIGI_OFF: PitchListJump,
    DIGI_ON: SlideCommand,
    0xEB: SetToneFlags,
    0xEC: StartDigi,
    0xED: StopDigi,
    0xEE: SidCommand,
    0xEF: SidCommand,
}


# --- Volume list ------------------------------------------------------------


def VolumeList(module: Module, voice: Voice) -> tuple[int, int]:
    """Every `speed` ticks: one volume byte. $e0 n loops, $e1 holds, $e8 n
    pauses n ticks. A wait also stops the speed counter. $e2-$e7 return
    from PitchList at once, so Play writes junk to the registers; the
    model treats them as a hold."""
    reader = voice.volume_list
    while True:
        if reader.wait:
            reader.wait -= 1
            break
        reader.counter -= 1
        if reader.counter:
            break
        reader.counter = reader.speed
        if not ReadVolume(module, voice):
            break
    return PitchToPeriod(module, voice)


def ReadVolume(module: Module, voice: Voice) -> bool:
    """True after $e8: VolumeList starts over."""
    reader = voice.volume_list
    while True:
        byte = reader.steps[reader.pos]
        if byte == LOOP:
            VolumeLoop(module, voice)
            continue
        if byte == WAIT:
            VolumeWait(voice)
            return True
        if byte == HOLD:
            if module.score.all_opcodes:
                voice.volume = reader.steps[reader.pos - 1]
            return False
        if LOOP < byte <= WAIT:
            return False
        voice.volume = byte
        reader.pos += 1
        return False


def VolumeLoop(module: Module, voice: Voice) -> None:
    """$e0 n: n counts from the instrument's start."""
    reader = voice.volume_list
    target = reader.steps[reader.pos + 1]
    if not module.score.all_opcodes:
        target &= LOOP_MASK
    reader.pos = target - VOLUME_HEADER


def VolumeWait(voice: Voice) -> None:
    """$e8 n."""
    reader = voice.volume_list
    reader.wait = reader.steps[reader.pos + 1]
    reader.pos += 2


# --- Pitch and mixer -------------------------------------------------------


def PitchToPeriod(module: Module, voice: Voice) -> tuple[int, int]:
    """The note offset plus the pattern note and the transpose picks a chip
    period; a fixed offset ignores both. The mode sets the voice's mixer
    bits. Then vibrato and slide: 'MMME' modules scale them by the period,
    others use period units. Returns the period and the volume."""
    step = voice.pitch.step
    note = step if step & FIXED else step + voice.note + voice.transpose
    note &= 0x7F
    period = PERIODS[note]
    tone_bit, noise_bit = 1 << voice.column, 1 << voice.column + 3
    if voice.mode == BOTH:
        module.mixer &= ~(tone_bit | noise_bit) & 0xFF
    elif voice.mode == NOISE:
        module.mixer = module.mixer & ~noise_bit & 0xFF | tone_bit
        voice.noise = step & 0x7F if step & FIXED else voice.note + step
    else:
        module.mixer = module.mixer & ~tone_bit & 0xFF | noise_bit
    NoisePeriod(module, voice)
    if module.score.scaled:
        period = ScaledSlide(voice, ScaledVibrato(voice, period))
    else:
        period = PeriodSlide(voice, OctaveVibrato(voice, period, note))
    voice.period = period
    volume = VolumeOffset(voice)
    if module.score.scaled:
        period = ToneFlags(voice, period)
    return period, volume


def NoisePeriod(module: Module, voice: Voice) -> None:
    """The chip has one noise register for all three channels. A voice
    writes it only in a tick where its noise value is set; the last
    writer wins. The value is inverted: a higher value, a higher noise
    pitch on the chip."""
    if voice.noise:
        module.noise = ~voice.noise & 0x1F


def ScaledVibrato(voice: Voice, period: int) -> int:
    """After the delay, pos moves by speed
    between 0 and 2 × depth; flip set means down. The offset is
    (pos - depth) × period / 1024: the same width in cents at every
    pitch."""
    vib = voice.vibrato
    if vib.delay:
        vib.delay -= 1
        return period
    if vib.flip:
        vib.pos -= vib.speed
        if vib.pos < 0:
            vib.pos, vib.flip = 0, False
    else:
        vib.pos += vib.speed
        if vib.pos > 2 * vib.depth:
            vib.pos, vib.flip = 2 * vib.depth, True
    return period + ((vib.pos - vib.depth) * period >> 10)


def ScaledSlide(voice: Voice, period: int) -> int:
    """Flag bit 5: the sum grows by the
    signed third byte each tick; the period drops by sum × period / 1024.
    The vibrato delay does not delay it."""
    if not voice.flags & SLIDE:
        return period
    voice.slide += signed(voice.arg)
    return period - (voice.slide * period >> 10)


def OctaveVibrato(voice: Voice, period: int, note: int) -> int:
    """Pos moves between 0 and 2 × depth; flip set means up,
    so it starts down. Depth with bit 7 is the whole range. The offset is
    pos minus half the range, doubled for each octave below note 48. So
    its width in cents stays about the same."""
    vib = voice.vibrato
    if vib.delay:
        vib.delay -= 1
        return period
    top = vib.depth & 0x7F if vib.depth & 0x80 else vib.depth * 2 & 0xFF
    if vib.flip:
        vib.pos += vib.speed
        if vib.pos >= top:
            vib.pos, vib.flip = top, False
    else:
        vib.pos -= vib.speed
        if vib.pos < 0:
            vib.pos, vib.flip = 0, True
    offset = vib.pos - top // 2
    octaves = (OCTAVE_NOTE - 1 - note) // 12 + 1 if note < OCTAVE_NOTE else 0
    return period + (offset << octaves)


def PeriodSlide(voice: Voice, period: int) -> int:
    """Flag bit 5: the period drops by the signed third byte / 16
    more each tick. Its speed in cents grows with pitch."""
    if not voice.flags & SLIDE:
        return period
    voice.slide += signed(voice.arg) << 12
    return period - (voice.slide >> 16)


def ToneFlags(voice: Voice, period: int) -> int:
    """Only 'MMME' modules. Bit 1 of $eb's byte zeroes the
    period. Bits 2 and 3 set a value that nothing reads."""
    return 0 if voice.tone_flags & 0x02 else period


def VolumeOffset(voice: Voice) -> int:
    """The list's volume minus the position's offset, at least 0."""
    return max(0, voice.volume - voice.volume_offset)


def SidVoice(module: Module, voice: Voice, period: int, volume: int) -> None:
    """Voice A's `SID` mode picks a period: 1 its own, 2 and 3 voice B's or
    C's from the last tick, 4 the last one. Paula channel 1 then plays a
    2-byte pulse; see SidPulse. Mode 0 or a period outside $11-$eee turns
    it off."""
    mode, digi = voice.sid_mode, module.digi
    if mode < 0:
        return
    if mode != 4:
        if mode in (2, 3):
            period = module.voices[mode - 1].period
        if mode == 0 or not SID_MIN < period <= SID_MAX:
            voice.sid_mode = -1
            digi.state = 0
            return
        digi.period = period * TONE_FACTOR + 1
    SidPulse(module, volume)


def SidPulse(module: Module, volume: int) -> None:
    """A 2-byte wave: -128, then a level from voice A's volume. The Paula
    volume is chip channel A's too. The channel restarts every tick."""
    level = BIT8[volume & 0x0F]
    pulse = paula.Sample(bytes([SID_LOW, level]))
    digi = module.digi
    digi.sample = digi.loop = pulse
    digi.volume = -1
    digi.state = 1


# --- Emulator ----------------------------------------------------------------


def ResetEmu(module: Module) -> None:
    """Every chip channel counts as silent, so the next tick
    restarts it. The register values matter only while Play is stopped:
    then channel C plays a tone at volume 32."""
    for state in module.emu:
        state.playing = 0
    module.digi.state = 0
    regs = module.registers.values
    regs[MIXER], regs[LEVEL[2]], regs[TONE_HI[2]] = 0x3B, ENVELOPE_MODE, 4
    regs[LEVEL[0]] = regs[LEVEL[1]] = regs[TONE_LO[2]] = 0


def in_order(steps: Sequence[Callable[[Then], None]], then: Then) -> None:
    """The CPU runs each step to its end, busy-waits included."""
    if not steps:
        then()
        return
    steps[0](lambda: in_order(steps[1:], then))


def EmuTick(module: Module, then: Then) -> None:
    """Chip channels A, B, C go to Paula channels 0, 3, 2, then
    EmuDigi drives channel 1. The registers were written by Play."""
    regs = module.registers.values
    enabled = ~regs[MIXER] & 0x3F
    steps: list[Callable[[Then], None]] = []
    for n in range(CHIP_VOICES):
        period = (regs[TONE_HI[n]] << 8 | regs[TONE_LO[n]]) & 0xFFF
        steps.append(partial(EmuChannel, module, n, period, regs[LEVEL[n]], enabled))
    steps.append(partial(EmuDigi, module))
    in_order(steps, then)


def EmuChannel(
    module: Module, n: int, period: int, level: int, enabled: int, then: Then
) -> None:
    """Tone wins over noise. A volume register with bit 4, the chip's
    envelope, gives a fixed 32; the model clamps higher values, which
    read past the table. With neither on, the channel restarts an empty
    sample every tick."""
    state = module.emu[n]
    state.volume = VOLUME_TABLE[min(level, ENVELOPE_MODE)]
    state.period = period * TONE_FACTOR + 1
    if enabled & 1 << n:
        EmuTone(module, n, then)
    elif enabled & 1 << n + 3:
        EmuNoise(module, n, then)
    else:
        state.volume, state.period, state.playing = 0, SILENT_PERIOD, 0

        def written() -> None:
            WriteChannel(module, n)
            then()

        NotePlay(module, PAULA_OF_CHIP[n], EMPTY, EMPTY, written)


def EmuTone(module: Module, n: int, then: Then) -> None:
    """A 4-byte square, looped. It restarts only when the channel was not
    playing a tone, so a new pitch keeps the phase."""
    state = module.emu[n]

    def written() -> None:
        WriteChannel(module, n)
        then()

    if state.playing == 1:
        written()
        return
    state.playing = 1
    NotePlay(module, PAULA_OF_CHIP[n], SQUARE, SQUARE, written)


def EmuNoise(module: Module, n: int, then: Then) -> None:
    """The 1024-byte noise sample, looped. The period comes from the noise
    register: 640 - 16 × value. So a higher register gives a higher
    pitch, the opposite of the chip."""
    state = module.emu[n]
    register = module.registers.values[NOISE_PERIOD] & 0x1F

    def written() -> None:
        state.period = NOISE_PERIODS[register]
        WriteChannel(module, n)
        then()

    if state.playing == 2:
        written()
        return
    state.playing = 2
    noise = module.noise_sample
    NotePlay(module, PAULA_OF_CHIP[n], noise, noise, written)


def WriteChannel(module: Module, n: int) -> None:
    """volume and period, once per tick."""
    state = module.emu[n]
    channel = module.amiga.paula.channels[PAULA_OF_CHIP[n]]
    channel.set_volume(state.volume)
    channel.period = state.period


def EmuDigi(module: Module, then: Then) -> None:
    """Paula channel 1. Off: it restarts an empty sample every tick. Start:
    it starts the sample once, then plays on untouched. A negative volume
    takes chip channel A's."""
    digi = module.digi
    channel = module.amiga.paula.channels[DIGI_CHANNEL]
    if digi.state == 2:
        then()
        return

    def written() -> None:
        channel.period = digi.period
        channel.set_volume(module.emu[0].volume if digi.volume < 0 else digi.volume)
        then()

    if digi.state == 0:
        NotePlay(module, DIGI_CHANNEL, EMPTY, EMPTY, written)
        return
    digi.state = 2
    NotePlay(module, DIGI_CHANNEL, digi.sample, digi.loop, written)


# --- Note start ---------------------------------------------------------------


def after_slots(now: int) -> int:
    """The next line's beam position SLOTS_END: its audio slots are past."""
    return now - now % LINE_CCK + LINE_CCK + SLOTS_END


def NotePlay(
    module: Module,
    number: int,
    start: paula.Sample,
    loop: paula.Sample,
    then: Then,
) -> None:
    """Wanted Team's restart. Next line: period 1, DMA off, wait for the
    channel's request. Write the start. Next line: DMA on, wait for the
    start reload. Next line: write the loop. The caller sets the period.
    So each restart costs at least three lines of busy-wait."""
    amiga = module.amiga
    channel = amiga.paula.channels[number]

    def wait_request(done: Then) -> None:
        if channel.irq_requested:
            done()
        else:
            amiga.after(POLL_CCK, Priority.CPU, partial(wait_request, done))

    def on_line(step: Then) -> None:
        amiga.schedule(after_slots(amiga.now), Priority.CPU, step)

    def stop() -> None:
        channel.period = 1
        if channel.dma:
            channel.irq_requested = False
            channel.disable()
            wait_request(set_start)
        else:
            set_start()

    def set_start() -> None:
        channel.queue(start)
        on_line(start_dma)

    def start_dma() -> None:
        channel.irq_requested = False
        channel.enable()
        wait_request(lambda: on_line(set_loop))

    def set_loop() -> None:
        channel.queue(loop)
        then()

    on_line(stop)
