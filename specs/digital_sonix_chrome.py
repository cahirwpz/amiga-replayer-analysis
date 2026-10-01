"""Digital Sonix & Chrome's replay, from Dragon's Breath (1990).
Digital Sonix & Chrome_v1.asm, Wanted Team's adaptation.

Card: players/DigitalSonixChrome.md. Level 2: the control flow runs.
Each CamelCase function is a new name in data/annot/DigitalSonixChrome.yaml;
each CamelCase class is in its `types:`.

There is no instrument program and no effect command. A row names one
instrument per voice. The instrument fixes the period, the volume and how
often its loop plays. Audio interrupts count the loop passes; the tick
only reads rows.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import partial

from hardware import paula
from hardware.amiga import Amiga, Priority
from hardware.clock import CPU_PER_CCK

NO_NOTE = 0xFF  # a row's byte: the voice plays on
FREE = 0xFF  # a voice's effect and request: none
FIRST_IGNORED = 0x80  # requests from here on are ignored
COLUMNS = 4  # one column of row bytes per voice
HEADER = 12  # before the positions: tempo, counts, sizes
POSITION_SIZE = 6
INSTRUMENT_SIZE = 18
TEMPO_BASE = 1500  # TempoBase: speed = 1500 / tempo, rounded
FLUSH_PERIOD = 1  # the extra word after DMA off lasts 2 CCK
# One WaitAudioIrq loop: move.w, and.w, bne.s not taken, bra.s
POLL_CCK = (16 + 4 + 8 + 10) // CPU_PER_CCK
SILENCE = paula.Sample(bytes(4))  # Empty: 2 words, each handler's is_Data


# --- What the composer edits -------------------------------------------


@dataclass
class Position:  # 6 bytes at PositionTable
    pattern: int  # +0: its first row's offset in each column
    repeats: int  # +4: plays of the pattern; 0 ends the subsong
    rows: int  # +5


@dataclass
class Instrument:  # 18 bytes at InstrumentTable
    period: int  # +0: every note of this instrument plays at this period
    length: int  # +2: bytes
    loop_start: int  # +6: bytes into the sample
    loops: int  # +10: loop passes after the first pass; 0: plays once
    sample: bytes  # +12: an offset into the sample data
    volume: int  # +16


@dataclass
class Score:  # ModuleBase: the module after LoadModule
    speed: int  # ticks per row, from the header's tempo
    positions: list[Position]
    columns: bytes  # four columns of one byte per row
    column: int  # header long: bytes per column
    instruments: list[Instrument]


# --- Replay state --------------------------------------------------------


@dataclass
class Voice:
    channel: paula.Channel
    passes: int = 0  # PassesLeft: audio interrupts left before silence
    loop: paula.Sample | None = None  # LoopStart, LoopLength
    effect: int = FREE  # SfxPlaying: the playing effect's number
    request: int = FREE  # SfxRequest: written by the game


@dataclass
class Module:  # PlayerData
    score: Score
    amiga: Amiga
    voices: list[Voice] = field(default_factory=list)
    first: int = 0  # FirstPosition: the subsong's first position
    position: int = 0  # PositionNumber
    row: int = 0  # RowOffset: the next row's offset in each column
    rows_played: int = 0  # RowsPlayed
    repeats_left: int = 0  # RepeatsLeft
    counter: int = 1  # RowCounter: ticks to the next row


Then = Callable[[], None]


def new_module(score: Score, amiga: Amiga) -> Module:
    """The player calls Play once per tick."""
    module = Module(score, amiga)
    module.voices = [Voice(channel) for channel in amiga.paula.channels]
    amiga.vblank.handler = lambda: Play(module)
    return module


def LoadModule(data: bytes) -> Score:
    """Header: tempo word, instrument count, position
    count, a sample size long, bytes per column. Then positions, the four
    columns, instruments and the sample data. Speed = 1500 / tempo,
    rounded: the tempo is fixed for the whole module."""
    tempo = int.from_bytes(data[0:2], "big")
    instruments, positions = data[2], data[3]
    column = int.from_bytes(data[8:12], "big")
    at = HEADER
    table = []
    for _ in range(positions):
        entry = data[at : at + POSITION_SIZE]
        table.append(Position(int.from_bytes(entry[0:4], "big"), entry[4], entry[5]))
        at += POSITION_SIZE
    columns = data[at : at + COLUMNS * column]
    at += COLUMNS * column
    samples = at + instruments * INSTRUMENT_SIZE
    sounds = []
    for _ in range(instruments):
        entry = data[at : at + INSTRUMENT_SIZE]
        length = int.from_bytes(entry[2:6], "big")
        start = samples + int.from_bytes(entry[12:16], "big")
        sounds.append(
            Instrument(
                period=int.from_bytes(entry[0:2], "big"),
                length=length,
                loop_start=int.from_bytes(entry[6:10], "big"),
                loops=int.from_bytes(entry[10:12], "big"),
                sample=data[start : start + length],
                volume=entry[16],
            )
        )
        at += INSTRUMENT_SIZE
    speed = (tempo // 2 + TEMPO_BASE) // tempo
    return Score(speed, table, columns, column, sounds)


def StartSubsong(module: Module, number: int) -> None:
    """Subsongs follow each other in the positions; a position with
    0 repeats ends each one. No voice plays an effect."""
    positions = module.score.positions
    first = 0
    for _ in range(number):
        while positions[first].repeats:
            first += 1
        first += 1
    for voice in module.voices:
        voice.effect = voice.request = FREE
    module.first = module.position = first
    module.rows_played, module.counter = 0, 1
    module.row = positions[first].pattern
    module.repeats_left = positions[first].repeats


def request_effect(module: Module, voice: int, number: int) -> None:
    """Called by the game: an instrument number to play as an effect."""
    module.voices[voice].request = number


# --- Tick ---------------------------------------------------------------


def Play(module: Module) -> None:
    """A row every `speed` ticks, then the game's effect requests. Each
    note start busy-waits, so the steps run in order.

    The original also had a song fade. Every 4 rows, a fade level moved
    one step toward a target. StartNote shifted the instrument volume
    right by that level. Wanted Team's version comments both out."""
    module.counter -= 1
    if module.counter:
        SfxClaimVoice(module, lambda: None)
        return
    module.counter = module.score.speed
    ReadRow(module, lambda: SfxClaimVoice(module, lambda: None))


def in_order(steps: Sequence[Callable[[Then], None]], then: Then) -> None:
    """The CPU runs each step to its end, busy-waits included."""
    if not steps:
        then()
        return
    steps[0](lambda: in_order(steps[1:], then))


def ReadRow(module: Module, then: Then) -> None:
    """One byte per voice. A voice that plays an effect reads nothing:
    the effect takes it, and its music notes are lost."""
    score, row = module.score, module.row
    notes = [
        NO_NOTE
        if voice.effect < FIRST_IGNORED
        else score.columns[n * score.column + row]
        for n, voice in enumerate(module.voices)
    ]
    module.row += 1
    starts = [
        partial(StartNote, module, voice, note)
        for voice, note in zip(module.voices, notes)
    ]

    def counted() -> None:
        CountRepeats(module)
        then()

    in_order(starts, counted)


def CountRepeats(module: Module) -> None:
    """After the pattern's last row, it plays again until its repeats run
    out."""
    position = module.score.positions[module.position]
    module.rows_played += 1
    if module.rows_played != position.rows:
        return
    module.rows_played = 0
    module.repeats_left -= 1
    if module.repeats_left == 0:
        NextPosition(module)
    else:
        module.row = position.pattern


def NextPosition(module: Module) -> None:
    """A position with 0 repeats sends the subsong back to its start."""
    module.position += 1
    if module.score.positions[module.position].repeats == 0:
        module.position = module.first  # SongEnd tells the host
    position = module.score.positions[module.position]
    module.row, module.repeats_left = position.pattern, position.repeats


def SfxClaimVoice(module: Module, then: Then) -> None:
    """A request plays if its number is at most the playing effect's: a
    lower number wins. A free voice holds FREE. A request from
    FIRST_IGNORED up is ignored and stays."""

    def claim(voice: Voice, then: Then) -> None:
        number = voice.request
        if number >= FIRST_IGNORED:
            then()
            return
        voice.request = FREE
        if number > voice.effect:
            then()
            return

        def started() -> None:
            voice.effect = number
            then()

        StartNote(module, voice, number, started)

    in_order([partial(claim, voice) for voice in module.voices], then)


# --- Note start -----------------------------------------------------------


def StartNote(module: Module, voice: Voice, number: int, then: Then) -> None:
    """NO_NOTE: the voice plays on. Else DMA off at period 1, with
    INTREQ clear and a write to AUDxDAT. The channel ends its word, plays
    one more at period 1 and requests an interrupt, which it leaves
    pending, so it goes idle. WaitAudioIrq waits for that request, so
    DMA on restarts the channel: no fixed wait."""
    if number == NO_NOTE:
        then()
        return
    channel = voice.channel
    channel.disable()
    channel.period = FLUSH_PERIOD
    channel.irq_requested = False
    channel.irq_enabled = False
    channel.write_data()
    instrument = module.score.instruments[number]
    channel.set_volume(instrument.volume)
    channel.queue(paula.Sample(instrument.sample))
    SetLoopCount(voice, instrument)
    poll = partial(WaitAudioIrq, module, voice, instrument, then)
    module.amiga.after(POLL_CCK, Priority.CPU, poll)


def SetLoopCount(voice: Voice, instrument: Instrument) -> None:
    """The first pass, then `loops` passes of the loop. With 0 loops, the
    loop is not set: the first interrupt already queues silence."""
    voice.passes = instrument.loops + 1
    if instrument.loops:
        loop = instrument.sample[instrument.loop_start : instrument.length]
        voice.loop = paula.Sample(loop)


def WaitAudioIrq(
    module: Module, voice: Voice, instrument: Instrument, then: Then
) -> None:
    """Polls INTREQR until the channel requests. The wait lasts as long as
    the old word: up to 2 × its period CCK. A poll takes longer than the
    extra word, so the channel is idle when DMA goes on."""
    if voice.channel.irq_requested:
        SetFixedPeriod(module, voice, instrument)
        then()
        return
    retry = partial(WaitAudioIrq, module, voice, instrument, then)
    module.amiga.after(POLL_CCK, Priority.CPU, retry)


def SetFixedPeriod(module: Module, voice: Voice, instrument: Instrument) -> None:
    """The instrument's period; notes carry no pitch. DMA on from idle
    restarts the channel. The audio interrupt counts the passes."""
    channel = voice.channel
    channel.period = instrument.period
    channel.enable()
    channel.irq_requested = False
    channel.on_irq(lambda c: CountLoopPass(voice))


# --- Audio interrupt ----------------------------------------------------


def CountLoopPass(voice: Voice) -> None:
    """Audio0-3: one per reload, the first at DMA start. It queues the
    loop until the passes run out, then silence. The interrupt after
    that ends the sound. Wanted Team's handlers first wait for the next
    scanline; the model leaves that out."""
    if voice.passes == 0:
        LoopsDone(voice)
        return
    voice.passes -= 1
    if voice.passes and voice.loop is not None:
        voice.channel.queue(voice.loop)
    else:
        voice.channel.queue(SILENCE)


def LoopsDone(voice: Voice) -> None:
    """The channel loops silence with its interrupt off. The voice is free
    for effects again; a music note also frees it."""
    voice.channel.irq_enabled = False
    voice.effect = FREE
