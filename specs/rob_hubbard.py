"""Rob Hubbard's Amiga replay, from PGA Tour Golf (1990). The replay ships
inside each module; this model reads data/module/RobHubbard/rh.GMUSIC.

Card: players/RobHubbard.md. Level 2: the control flow runs. Each
CamelCase function is a LABEL in data/disasm/RobHubbard.cnf; each
CamelCase class is in the `types:` of data/annot/RobHubbard.yaml.

The module starts with five `bra.w`: Play, InitSong, StopSound, and two
routines that save and restore the level 4 interrupt vector. The replay
is 830 bytes; tables, songs and samples follow it.

Each voice reads its own byte stream, pattern by pattern, from a
position list. A note byte carries its length. An instrument is a
sample, or one of three short waves in the replay's data. Each sample
stores its recording rate, and the period is scaled by it. A wave
instrument can have vibrato and a sweep: each tick, the sweep writes
one byte into the wave, so an edge moves back and forth. There is no
volume envelope.

Left out: the host's timer; DeliTracker calls Play once per tick.
"""

from dataclasses import dataclass, field

from hardware import paula
from hardware.amiga import Amiga

VOICES = 4
DEFAULT_LATCH = 14187  # DeliTracker's timer, 50 Hz (guess): no DTP_Timer tag
CLOCK = 3579545  # NTSC colour clock: the tune's dividend
TUNE_SHIFT = 10  # period = table × tune >> 10
SAMPLES = 11  # InitSamples: sample instruments 0-10
WAVES = (13, 14, 15)  # InitWaves: wave instruments
SONG_SIZE = 18
SILENT = paula.Sample(bytes(64))  # SilentWords: 32 words of silence
LOW, HIGH = 0x00, 0x3C  # Sweep's two byte values
VIBRATO_LOOP = 0x84  # a vibrato table's last byte: restart
NOTE_MAX = 0x7F  # stream bytes up to this are a length and a note

# Stream commands
INSTRUMENT, PORTAMENTO, REST, NOP, PATTERN_END, STOP = range(0x80, 0x86)


# --- Player state ------------------------------------------------------


@dataclass
class Instrument:  # Instruments: 32 bytes each
    start: int = 0  # 0: bytes into the module
    loop: int = 0  # 4: bytes; 0: silence after one pass; <0: all of it loops
    length: int = 0  # 8: words
    tune: int = 0  # 12: 3579545 / the sample's rate
    volume: int = 0  # 14
    divider: int = 0  # 16: vibrato; 0: none
    vibrato: int = 0  # 18: offset into VibratoTables
    high: int = 0  # 20: the sweep's upper byte; 0: no sweep
    low: int = 0  # 22: its lower byte


@dataclass
class Voice:  # Voices: 38 bytes each
    channel: paula.Channel
    portamento_on: bool = False  # 0, bit 1: cleared at every event
    sweep_down: bool = False  # 0, bit 2
    note: int = 0  # 2
    pos: int = 0  # 4: the stream, bytes into the module
    positions: int = 0  # 8: the position list
    position: int = 4  # 12: bytes into the position list
    ticks: int = 1  # 16
    period: int = 0  # 18: after portamento
    step: int = 0  # 20: portamento, added each tick
    looped: bool = True  # 22: QueueLoop ran for this note
    instrument: Instrument = field(default_factory=Instrument)  # 24
    vibrato_pos: int = 0  # 28
    vibrato_start: int = 0  # 32
    sweep_pos: int = 0  # 36


@dataclass
class Module:  # the module is the replay: code, tables, songs and samples
    amiga: Amiga
    data: bytearray  # Sweep writes into it
    # offsets of the labels in data/disasm/RobHubbard.cnf, for rh.GMUSIC
    period_table: int = 0x3DC  # PeriodTable: from 4096 down, a word per note
    wave_list: int = 0x43E  # WaveList
    instruments_at: int = 0x44A  # Instruments
    vibrato_tables: int = 0x64A  # VibratoTables
    songs: int = 0x6AE  # Songs
    silent_words: int = 0x100E  # SilentWords; the samples follow 64 bytes on
    instruments: list[Instrument] = field(default_factory=list)
    voices: list[Voice] = field(default_factory=list)
    playing: bool = False  # Playing
    speed: int = 1  # Speed: ticks per length unit
    default_instrument: int = 0  # DefaultInstrument


# --- Start -------------------------------------------------------------


def new_module(module: Module, song: int, instrument: int) -> Module:
    """DeliTracker calls Play by its own timer."""
    module.voices = [Voice(c) for c in module.amiga.paula.channels]
    module.instruments = [
        read_instrument(module.data, module.instruments_at + 32 * n)
        for n in range(max(WAVES) + 1)
    ]
    InitSong(module, song, instrument)
    module.amiga.timer.on_underflow = lambda: Play(module)
    module.amiga.timer.set_latch(DEFAULT_LATCH)
    return module


def InitSong(module: Module, song: int, instrument: int) -> None:
    """d0: the song; d1: the instrument that $80 with a negative
    argument picks. Stops the sound, sets up samples, waves and voices,
    then points the level 4 interrupt at NullInterrupt.

    rh.GMUSIC clears d0 after StopSound, so it always plays song 0.
    rh.FLYMUS lacks that `moveq` and plays the song in d0."""
    module.default_instrument = instrument & 0xFF
    StopSound(module)
    song = 0
    InitSamples(module)
    InitWaves(module)
    InitVoices(module, song)
    module.playing = True


def InitSamples(module: Module) -> None:
    """Each sample has a long length and a word rate before its data.
    The tune turns the rate into a period factor, so any rate plays in
    tune."""
    at = module.silent_words + 64
    for instrument in module.instruments[:SAMPLES]:
        length, rate = long(module.data, at), word(module.data, at + 4)
        instrument.start, instrument.length = at + 6, length >> 1
        instrument.tune = CLOCK // rate
        at += 6 + length


def InitWaves(module: Module) -> None:
    """Instruments 13 to 15 point at three waves in the replay's data.
    Their records hold vibrato and sweep settings."""
    for n, number in enumerate(WAVES):
        module.instruments[number].start = long(module.data, module.wave_list + 4 * n)


def InitVoices(module: Module, song: int) -> None:
    """A song record: byte 1 the speed, then one position list per
    voice."""
    record = module.songs + SONG_SIZE * song
    module.speed = module.data[record + 1]
    for n, voice in enumerate(module.voices):
        voice.ticks, voice.position = 1, 4
        voice.positions = long(module.data, record + 2 + 4 * n)
        voice.pos = long(module.data, voice.positions)


def NullInterrupt() -> None:
    """`rte`: audio interrupts return at once."""


def StopSound(module: Module) -> None:
    module.playing = False
    for voice in module.voices:
        voice.channel.disable()


# --- Tick --------------------------------------------------------------


def Play(module: Module) -> None:
    """Voices 3 down to 0."""
    if not module.playing:
        return
    for voice in reversed(module.voices):
        if not VoiceTick(module, voice):
            return


def VoiceTick(module: Module, voice: Voice) -> bool:
    """False: the song stopped."""
    QueueLoop(module, voice)
    return CountDown(module, voice)


def QueueLoop(module: Module, voice: Voice) -> None:
    """The tick after a note: the loop from its offset, or silence, or
    nothing, so the whole sample loops."""
    if voice.looped:
        return
    voice.looped = True
    instrument = voice.instrument
    if not instrument.loop:
        voice.channel.queue(SILENT)
    elif instrument.loop > 0:
        start = instrument.start + instrument.loop
        end = instrument.start + 2 * instrument.length
        voice.channel.queue(paula.Sample(bytes(module.data[start:end])))


def CountDown(module: Module, voice: Voice) -> bool:
    """At 0, the next event. One tick before, DMA goes off: every note
    ends with a short gap. Else the effects run."""
    voice.ticks -= 1
    if not voice.ticks:
        voice.portamento_on = voice.sweep_down = False
        return ReadStream(module, voice)
    if voice.ticks == 1:
        voice.channel.disable()
    Portamento(voice)
    Vibrato(module, voice)
    Sweep(module, voice)
    return True


def ReadStream(module: Module, voice: Voice) -> bool:
    """Commands until a note or a rest."""
    data = module.data
    while True:
        byte = data[voice.pos]
        voice.pos += 1
        if byte <= NOTE_MAX:
            NoteOn(module, voice, byte)
            return True
        if byte == INSTRUMENT:
            SetInstrument(module, voice)
        elif byte == PORTAMENTO:
            SetPortamento(module, voice)
        elif byte == REST:
            Rest(module, voice)
            return True
        elif byte == PATTERN_END:
            NextPosition(module, voice)
        elif byte == STOP:
            StopSound(module)
            return False


def SetInstrument(module: Module, voice: Voice) -> None:
    """A negative number picks the song's default instrument."""
    number = module.data[voice.pos]
    voice.pos += 1
    if number & 0x80:
        number = module.default_instrument
    voice.instrument = module.instruments[number]
    voice.vibrato_start = module.vibrato_tables + voice.instrument.vibrato


def Rest(module: Module, voice: Voice) -> None:
    """A length × speed ticks of silence."""
    voice.ticks = module.data[voice.pos] * module.speed
    voice.pos += 1
    voice.channel.queue(SILENT)


def SetPortamento(module: Module, voice: Voice) -> None:
    """A signed step for the next note only: every event clears it."""
    voice.step = signed_byte(module.data[voice.pos])
    voice.pos += 1
    voice.portamento_on = True


def NextPosition(module: Module, voice: Voice) -> None:
    """The next pattern in the voice's list. Offset 0 wraps to the first."""
    at = voice.positions + voice.position
    voice.position += 4
    if not long(module.data, at):
        at, voice.position = voice.positions, 4
    voice.pos = long(module.data, at)


def NoteOn(module: Module, voice: Voice, length: int) -> None:
    """The length × speed ticks, then the note. The period is the
    table's value × the instrument's tune >> 10."""
    voice.ticks = length * module.speed
    voice.note = module.data[voice.pos]
    voice.pos += 1
    instrument = voice.instrument
    voice.sweep_pos = instrument.low
    voice.vibrato_pos = voice.vibrato_start
    start, words = instrument.start, instrument.length
    voice.channel.queue(paula.Sample(bytes(module.data[start : start + 2 * words])))
    voice.channel.set_volume(instrument.volume)
    table = word(module.data, module.period_table + 2 * voice.note)
    voice.period = table * instrument.tune >> TUNE_SHIFT
    voice.channel.period = voice.period
    voice.channel.enable()
    voice.looped = False


def Portamento(voice: Voice) -> None:
    if voice.portamento_on:
        voice.period = (voice.period + voice.step) & 0xFFFF
        voice.channel.period = voice.period


def Vibrato(module: Module, voice: Voice) -> None:
    """period + period / divider × value. So the swing is a share of the
    period: the same interval on every note. $84 restarts the table."""
    divider = voice.instrument.divider
    if not divider:
        return
    value = module.data[voice.vibrato_pos]
    voice.vibrato_pos += 1
    if value == VIBRATO_LOOP:
        value = module.data[voice.vibrato_start]
        voice.vibrato_pos = voice.vibrato_start + 1
    offset = (voice.period // divider & 0xFFFF) * signed_byte(value)
    voice.channel.period = (voice.period + offset) & 0xFFFF


def Sweep(module: Module, voice: Voice) -> None:
    """One byte per tick into the playing wave. Up from `low`, it writes
    $00; past `high` it turns and writes $3C, one byte past `high`.
    SweepDown goes back. The edge between the two values moves: a
    pulse-width sweep. The wave is shared, so every voice on this
    instrument hears it."""
    instrument = voice.instrument
    if not instrument.high:
        return
    if voice.sweep_down:
        SweepDown(module, voice)
        return
    voice.sweep_pos += 1
    if voice.sweep_pos > instrument.high:
        voice.sweep_down = True
        write_sweep(module, voice, HIGH)
    else:
        write_sweep(module, voice, LOW)


def SweepDown(module: Module, voice: Voice) -> None:
    """Down, it writes $3C; at `low` it turns and writes $00."""
    voice.sweep_pos -= 1
    if voice.sweep_pos > voice.instrument.low:
        write_sweep(module, voice, HIGH)
    else:
        voice.sweep_down = False
        write_sweep(module, voice, LOW)


def write_sweep(module: Module, voice: Voice, value: int) -> None:
    module.data[voice.instrument.start + voice.sweep_pos] = value


# --- Helpers -----------------------------------------------------------


def read_instrument(data: bytearray, at: int) -> Instrument:
    return Instrument(
        long(data, at), signed_long(long(data, at + 4)), word(data, at + 8),
        word(data, at + 12), word(data, at + 14), word(data, at + 16),
        word(data, at + 18), word(data, at + 20), word(data, at + 22),
    )  # fmt: skip


def signed_long(value: int) -> int:
    return value - (1 << 32) if value & 1 << 31 else value


def signed_byte(value: int) -> int:
    return value - 0x100 if value & 0x80 else value


def word(data: bytes | bytearray, at: int) -> int:
    return data[at] << 8 | data[at + 1]


def long(data: bytes | bytearray, at: int) -> int:
    return word(data, at) << 16 | word(data, at + 2)
