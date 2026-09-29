"""SoundMon 2.2's replay: Soundmon2.2.s, by Brian Postma (1991), adapted
for UADE by mld.

Card: players/SoundMon2.2.md. Level 2: the control flow runs. Each
CamelCase function is a new name in data/annot/SoundMon2.2.yaml; each
CamelCase class is in its `types:`. Comments name the voice fields by
their offsets in Voices.

A synth instrument plays a 64-byte table from a pool. Four table walkers
step through other tables of the same pool: `ADSR` scales the volume,
`LFO` offsets the period, `EG` negates the wave's first samples and
`MOD` writes one byte of the wave. A wave effect changes the wave's
first 32 bytes. The next note writes them back.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from hardware import paula
from hardware.amiga import DEFAULT_LATCH, Amiga, Priority
from specs.controls import Countdown, Mode, TableWalker

VOICES = 4
HEADER = 512  # title, 'V.3', table count, length, 15 instruments
INSTRUMENT_SIZE = 32  # instrument n starts at byte 32 × n
INSTRUMENTS = 15
POSITION_SIZE = 16  # 4 entries: pattern word, instrument transpose, note transpose
ENTRY_SIZE = 4
ROWS = 16
ROW_SIZE = 3  # note; instrument and option; argument
PATTERN_SIZE = ROWS * ROW_SIZE
TABLE_SIZE = 64
SAVED = 32  # bytes a note saves; effects change only these
MOD_BYTE = 32  # the wave byte that MOD writes, just past the saved bytes
SYNTH = 0xFF  # the first byte of a synth instrument
USE_INSTRUMENT = 0xFF  # a voice volume that means: the instrument's volume
DEFAULT_SPEED = 6
ARP_STEPS = 4
# Measured in vAmiga without display DMA: data/timing/soundmon_22.yaml, run by
# tools/timing.py. Bitplane DMA takes bus slots, so a display makes both longer.
DMA_WAIT_CCK = 648  # DmaWait: 128 dbra loops
# From DmaWait's end to DMA on: RestoreWaves and StartNoteLoop, for one new
# note without a sample, the shortest path. Four sample notes take 1291 CCK.
START_CCK = 442

# Commands: the low nibble of a row's second byte
ARPEGGIO, VOLUME, SPEED, FILTER, SLIDE_UP, SLIDE_DOWN = 0, 1, 2, 3, 4, 5
VIBRATO, JUMP, AUTO_SLIDE, AUTO_ARPEGGIO, NO_TRANSPOSE = 6, 7, 8, 9, 10
EFFECT = 11
LEGATO_FLIP, LEGATO, LEGATO_KEEP_ADSR = 13, 14, 15  # change the note only

VIBRATO_TABLE = (0, 64, 128, 64, 0, -64, -128, -64)

BELOW = 36  # entries before note 1
PERIODS = (
    *(6848, 6464, 6080, 5760, 5440, 5120, 4832, 4576, 4320, 4064, 3840, 3616),
    *(3424, 3232, 3040, 2880, 2720, 2560, 2416, 2288, 2160, 2032, 1920, 1808),
    *(1712, 1616, 1520, 1440, 1360, 1280, 1208, 1144, 1080, 1016, 960, 904),
    *(856, 808, 760, 720, 680, 640, 604, 572, 540, 508, 480, 452),
    *(428, 404, 380, 360, 340, 320, 302, 286, 270, 254, 240, 226),
    *(214, 202, 190, 180, 170, 160, 151, 143, 135, 127, 120, 113),
    *(107, 101, 95, 90, 85, 80, 76, 72, 68, 64, 60, 57),
)
EMPTY = paula.Sample(bytes(2))  # EmptySample: one silent word


# --- What the composer edits -------------------------------------------


@dataclass
class Score:  # the module in chip memory, after InitSong
    memory: bytearray  # effects and walkers write into it
    length: int  # positions
    table_pool: int  # TablePool: offset of table 0
    sample_at: list[int]  # SamplePtrs: offset per instrument 1..15

    def byte(self, at: int) -> int:
        return self.memory[at]

    def word(self, at: int) -> int:
        return int.from_bytes(self.memory[at : at + 2], "big")

    def table(self, number: int) -> int:
        return self.table_pool + number * TABLE_SIZE


@dataclass
class Instrument:  # a sample instrument: a name, then 4 words at byte 24
    length: int  # words
    repeat_start: int  # bytes
    repeat_length: int  # words; 1: no loop
    volume: int


@dataclass
class WalkerSetup:  # one walker in a synth instrument
    control: int  # 0 off, 1 once, other values loop
    table: int  # in the pool
    length: int  # values; may run into the next tables
    speed: int  # ticks per step
    delay: int = 0  # ticks before the first step


@dataclass
class SynthInstrument:  # StartSynthNote: 32 bytes, byte 0 is SYNTH
    wave: int  # table number
    wave_length: int  # words
    adsr: WalkerSetup  # volume; starts at once, no delay
    lfo: WalkerSetup  # period
    lfo_depth: int  # divides the value; 0 is 1
    eg: WalkerSetup  # negated samples
    mod: WalkerSetup  # wave byte 32
    effect: int  # 0-6
    effect_speed: int  # step size, or ticks per step for 1
    effect_delay: int
    volume: int


def instrument(score: Score, number: int) -> Instrument:
    at = number * INSTRUMENT_SIZE + 24
    word = score.word
    return Instrument(word(at), word(at + 2), word(at + 4), word(at + 6))


def synth_instrument(score: Score, number: int) -> SynthInstrument:
    b = score.memory[number * INSTRUMENT_SIZE : (number + 1) * INSTRUMENT_SIZE]

    def w(at: int) -> int:
        return int.from_bytes(b[at : at + 2], "big")

    return SynthInstrument(
        wave=b[1],
        wave_length=w(2),
        adsr=WalkerSetup(b[4], b[5], w(6), b[8]),
        lfo=WalkerSetup(b[9], b[10], w(12), b[15], b[14]),
        lfo_depth=b[11],
        eg=WalkerSetup(b[16], b[17], w(18), b[21], b[20]),
        mod=WalkerSetup(b[25], b[26], w(30), b[27], b[28]),
        effect=b[22],
        effect_speed=b[23],
        effect_delay=b[24],
        volume=b[29],
    )


# --- Voice state -------------------------------------------------------


@dataclass
class Walker(
    TableWalker, Countdown
):  # RunWalkers: pos 14-20, counter 22-25, control 29-32
    BITS = 8


@dataclass
class SavedWave:  # SavedWaves: 36 bytes per voice
    address: int | None = None  # the wave; None: nothing saved
    data: bytes = bytes(SAVED)


@dataclass
class Voice:  # Voices: 36 bytes per voice
    channel: paula.Channel
    number: int
    period: int = 0  # 0; bit 15 there is new_note
    new_note: bool = False
    volume: int = 0  # 2; USE_INSTRUMENT: the instrument's
    instrument: int = 0  # 3
    start: int | None = None  # 4: the loop, AUDxLC every tick; None: EmptySample
    length: int = 1  # 8: words
    note: int = 0  # 10
    arpeggio: int = 0  # 11: ARPEGGIO's argument
    auto_slide: int = 0  # 12: signed, added every tick
    auto_arpeggio: int = 0  # 13
    eg: Walker = field(default_factory=Walker)
    lfo: Walker = field(default_factory=Walker)
    adsr: Walker = field(default_factory=Walker)
    mod: Walker = field(default_factory=Walker)
    effect_delay: int = 0  # 26
    synth: bool = False  # 27
    eg_value: int = 0  # 28: negated samples now
    vibrato: int = 0  # 34: divides the table value; 0 off
    effect: int = 0  # 35


@dataclass
class Module:  # Position, Speed, ArpStep and the other globals
    score: Score
    amiga: Amiga
    voices: list[Voice] = field(default_factory=list)
    saved: list[SavedWave] = field(default_factory=list)
    position: int = 0  # Position
    row: int = 0  # RowOffset: bytes into the pattern
    tick_count: int = 1  # TickCount
    speed: int = DEFAULT_SPEED  # Speed
    arp_step: int = 1  # ArpStep: shared by all voices
    vibrato_pos: int = 0  # VibratoPtr: shared by all voices
    jump: int | None = None  # JumpPosition
    dma_off: set[int] = field(default_factory=set)  # DmaMask after ReadRow
    dma_on: set[int] = field(default_factory=set)  # DmaMask after StartNote
    filter: bool = False  # the LED filter


def signed(byte: int) -> int:
    return byte - 256 if byte & 0x80 else byte


def divs(value: int, divisor: int) -> int:
    """68000 divs: the quotient rounds towards zero."""
    quotient = abs(value) // divisor
    return quotient if value >= 0 else -quotient


def period_of(note: int) -> int:
    return PERIODS[BELOW + note - 1]


def sample(score: Score, at: int | None, words: int) -> paula.Sample:
    """The channel reads memory live, so synth writes are heard."""
    if at is None:
        return EMPTY
    return paula.Sample(score.memory, at, words)


def new_module(score: Score, amiga: Amiga) -> Module:
    """DeliTracker calls PlayTick by its own timer."""
    module = Module(score, amiga)
    module.voices = [Voice(c, n) for n, c in enumerate(amiga.paula.channels)]
    module.saved = [SavedWave() for _ in range(VOICES)]
    amiga.timer.on_underflow = lambda: PlayTick(module)
    amiga.timer.set_latch(DEFAULT_LATCH)
    return module


def InitSong(data: bytes) -> Score:
    """The table pool follows the patterns; the samples follow the
    pool. The highest pattern number in the positions gives the number
    of patterns. Only a 'V.3' module has tables. A synth instrument has
    no sample data."""
    memory = bytearray(data)
    tables = data[29] if data[26:29] == b"V.3" else 0
    length = int.from_bytes(data[30:32], "big")
    entries = (HEADER + n * ENTRY_SIZE for n in range(length * VOICES))
    highest = max([1, *(int.from_bytes(data[at : at + 2], "big") for at in entries)])
    pool = HEADER + length * POSITION_SIZE + highest * PATTERN_SIZE
    at = pool + tables * TABLE_SIZE
    sample_at = []
    for number in range(1, INSTRUMENTS + 1):
        sample_at.append(at)
        header = number * INSTRUMENT_SIZE
        if data[header] != SYNTH:
            at += 2 * int.from_bytes(data[header + 24 : header + 26], "big")
    return Score(memory, length, pool, sample_at)


# --- Tick ---------------------------------------------------------------


def PlayTick(module: Module) -> None:
    """Per voice: slide, vibrato, the loop, the arpeggio. Then the
    walkers. Every `speed` ticks, a row. The arpeggio step and the vibrato
    position are global: notes never reset them."""
    module.arp_step = (module.arp_step - 1) % ARP_STEPS
    module.vibrato_pos = (module.vibrato_pos + 1) % len(VIBRATO_TABLE)
    for voice in module.voices:
        TickVoice(module, voice)
    RunWalkers(module)
    module.tick_count = (module.tick_count - 1) & 0xFF
    if module.tick_count == 0:
        PlayRow(module)


def TickVoice(module: Module, voice: Voice) -> None:
    """The auto slide moves the period every tick. The period goes to
    the channel, with vibrato if set. AUDxLC and AUDxLEN get the loop every
    tick, so a note's loop starts a tick after the note."""
    channel = voice.channel
    voice.period = (voice.period + signed(voice.auto_slide)) & 0xFFFF
    if voice.vibrato:
        offset = divs(VIBRATO_TABLE[module.vibrato_pos], voice.vibrato)
        channel.period = (voice.period + offset) & 0xFFFF
    else:
        channel.period = voice.period
    channel.queue(sample(module.score, voice.start, voice.length))
    if voice.arpeggio or voice.auto_arpeggio:
        Arpeggio(module, voice)


def Arpeggio(module: Module, voice: Voice) -> None:
    """A 4-tick cycle: high nibbles, base note, base note, low nibbles.
    The row's arpeggio and the auto arpeggio add up."""
    step = module.arp_step
    if step == 0:
        offset = (voice.arpeggio >> 4) + (voice.auto_arpeggio >> 4)
    elif step == 1:
        offset = (voice.arpeggio & 0x0F) + (voice.auto_arpeggio & 0x0F)
    else:
        offset = 0
    SetArpPeriod(voice, (voice.note + offset) & 0xFF)


def SetArpPeriod(voice: Voice, note: int) -> None:
    """The voice's period too: an arpeggio undoes the auto slide and
    replaces the vibrato."""
    voice.period = voice.channel.period = period_of(signed(note))


def PlayRow(module: Module) -> None:
    """DMA off for restarted voices, a busy-wait, then the waves come
    back, the notes start and DMA goes on. A synth note on the voice's
    instrument never had DMA off, so DMA on changes nothing: the channel
    plays on.

    A stopped channel restarts only if its word ends before DMA on. That
    takes up to 2 × period CCK. DMA off to DMA on takes at least
    DMA_WAIT_CCK + START_CCK = 1090 CCK. So a note with a period above 545
    can miss its restart. With 6 bitplanes on, both take longer: 1554 CCK,
    so the limit falls to 777. It then plays the old sample on, and the new
    sample starts at the old one's next reload."""
    module.tick_count = module.speed
    ReadRow(module)
    for number in sorted(module.dma_off):
        module.voices[number].channel.disable()

    def after_wait() -> None:
        RestoreWaves(module)
        module.dma_on.clear()
        for voice in module.voices:
            if voice.new_note:
                StartNote(module, voice)
        module.amiga.after(START_CCK, Priority.CPU, dma_on)

    def dma_on() -> None:
        for number in sorted(module.dma_on):
            module.voices[number].channel.enable()

    module.amiga.after(DMA_WAIT_CCK, Priority.CPU, after_wait)


def RestoreWaves(module: Module) -> None:
    """A voice with a new note writes back the 32 bytes it saved. All
    voices restore before any saves again."""
    for voice, saved in zip(module.voices, module.saved):
        if voice.new_note and saved.address is not None:
            at = saved.address
            module.score.memory[at : at + SAVED] = saved.data
            saved.address = None


# --- Rows ---------------------------------------------------------------


def ReadRow(module: Module) -> None:
    module.dma_off.clear()
    for voice in module.voices:
        ReadVoiceRow(module, voice)
    NextRow(module)


def ReadVoiceRow(module: Module, voice: Voice) -> None:
    """Voice 0 reads the position's last entry, voice 3 its first.
    Pattern numbers start at 1. A row without a note still runs its
    option."""
    score = module.score
    entry = HEADER + module.position * POSITION_SIZE
    entry += (VOICES - 1 - voice.number) * ENTRY_SIZE
    pattern = score.word(entry)
    instr_transpose, note_transpose = score.byte(entry + 2), score.byte(entry + 3)
    at = HEADER + score.length * POSITION_SIZE + (pattern - 1) * PATTERN_SIZE
    at += module.row
    note, info, arg = score.memory[at : at + ROW_SIZE]
    if note:
        NewNote(module, voice, note, info, arg, instr_transpose, note_transpose)
    Options(module, voice, info & 0x0F, arg)


def NewNote(
    module: Module,
    voice: Voice,
    note: int,
    info: int,
    arg: int,
    instr_transpose: int,
    note_transpose: int,
) -> None:
    """A note clears auto slide, auto arpeggio and vibrato. NO_TRANSPOSE
    skips the note transpose if its argument's high nibble is set, the
    instrument transpose if its low nibble is set. The three legato
    commands only change the period. A sample note always restarts. A synth note
    restarts DMA only for another instrument; it restarts the walkers
    anyway."""
    option = info & 0x0F
    voice.auto_slide = voice.auto_arpeggio = voice.vibrato = 0
    if not (option == NO_TRANSPOSE and arg & 0xF0):
        note = signed((note + note_transpose) & 0xFF)
    voice.note = note & 0xFF
    voice.period = period_of(note)
    if option >= LEGATO_FLIP:
        return
    voice.new_note = True
    voice.volume = USE_INSTRUMENT
    number = info >> 4 or voice.instrument
    if not (option == NO_TRANSPOSE and arg & 0x0F):
        number = AddInstrTranspose(number, instr_transpose)
    if voice.synth and number == voice.instrument:
        return
    voice.instrument = number
    module.dma_off.add(voice.number)


def AddInstrTranspose(number: int, transpose: int) -> int:
    return (number + transpose) & 0xFF


def Options(module: Module, voice: Voice, option: int, arg: int) -> None:
    """ARPEGGIO sets the arpeggio, so any row with another command ends
    it. SLIDE_UP and SLIDE_DOWN move the period once per row and end the
    arpeggio. Volume on a synth voice waits for the next note or `ADSR`
    step. EFFECT on a row with a new note is lost: StartSynthNote sets
    the instrument's effect. The one unnamed command does nothing."""
    if option == ARPEGGIO:
        voice.arpeggio = arg
    elif option == VOLUME:
        voice.volume = arg
        if not voice.synth:
            voice.channel.set_volume(arg)
    elif option == SPEED:
        module.tick_count = module.speed = arg
    elif option == FILTER:
        module.filter = arg != 0
    elif option == SLIDE_UP:
        voice.period = (voice.period - arg) & 0xFFFF
        voice.arpeggio = 0
    elif option == SLIDE_DOWN:
        voice.period = (voice.period + arg) & 0xFFFF
        voice.arpeggio = 0
    elif option == VIBRATO:
        voice.vibrato = arg
    elif option == JUMP:
        module.jump = arg
    elif option == AUTO_SLIDE:
        voice.auto_slide = arg
    elif option == EFFECT:
        voice.effect = arg
    elif option == AUTO_ARPEGGIO or option >= LEGATO_FLIP:
        SetAutoArp(voice, option, arg)


def SetAutoArp(voice: Voice, option: int, arg: int) -> None:
    """AUTO_ARPEGGIO and the legato commands. LEGATO_FLIP flips bit 0 of
    the effect number. All but LEGATO_KEEP_ADSR restart `ADSR`; one that
    had ended runs once more."""
    voice.auto_arpeggio = arg
    if option == LEGATO_FLIP:
        voice.effect ^= 1
    if option == LEGATO_KEEP_ADSR:
        return
    voice.adsr.pos = 0
    if voice.adsr.mode == Mode.OFF:
        voice.adsr.mode = Mode.ONCE


def NextRow(module: Module) -> None:
    """A jump goes to row 0 of its position after all voices read.
    After the last position, the song restarts at position 0."""
    if module.jump is not None:
        module.position, module.row, module.jump = module.jump, 0, None
        return
    module.row += ROW_SIZE
    if module.row < PATTERN_SIZE:
        return
    module.row = 0
    module.position += 1
    if module.position == module.score.length:
        module.position = 0  # SongEnd tells the host


# --- Note start ---------------------------------------------------------


def StartNote(module: Module, voice: Voice) -> None:
    """The period and the sample go to the channel at once. A sample
    with a loop start plays up to its loop end; one with a loop at 0
    plays only the loop. The loop follows at the next tick."""
    voice.new_note = False
    channel = voice.channel
    channel.period = voice.period
    score = module.score
    if score.byte(voice.instrument * INSTRUMENT_SIZE) == SYNTH:
        StartSynthNote(module, voice)
        return
    voice.synth = False
    voice.lfo.mode = Mode.OFF
    inst = instrument(score, voice.instrument)
    at = score.sample_at[voice.instrument - 1]
    channel.queue(sample(score, at, inst.length))
    volume = inst.volume if voice.volume == USE_INSTRUMENT else voice.volume
    channel.set_volume(volume)
    voice.length = inst.repeat_length
    if inst.repeat_length == 1:
        voice.start = None
    elif inst.repeat_start:
        voice.start = at + inst.repeat_start
        channel.queue(sample(score, at, inst.repeat_start // 2 + inst.repeat_length))
    else:
        voice.start = at
        channel.queue(sample(score, at, inst.repeat_length))
    module.dma_on.add(voice.number)


def mode(control: int) -> Mode:
    return (Mode.OFF, Mode.ONCE)[control] if control < 2 else Mode.LOOP


def walker(score: Score, setup: WalkerSetup, delay: int) -> Walker:
    """The table is a live view: `EG` and effects may change it."""
    at = score.table(setup.table)
    table = memoryview(score.memory)[at : at + setup.length]
    return Walker(
        table=table, mode=mode(setup.control), counter=delay & 0xFF, speed=setup.speed
    )


def StartSynthNote(module: Module, voice: Voice) -> None:
    """The walkers restart; each waits its delay + 1 ticks, `ADSR` 1.
    With `ADSR` on, its first value scales the volume at once. If `EG`,
    `MOD` or the effect is on, the note saves the wave's first 32 bytes."""
    score = module.score
    inst = synth_instrument(score, voice.instrument)
    voice.synth = True
    voice.eg = walker(score, inst.eg, inst.eg.delay + 1)
    voice.lfo = walker(score, inst.lfo, inst.lfo.delay + 1)
    voice.adsr = walker(score, inst.adsr, 1)
    voice.mod = walker(score, inst.mod, inst.mod.delay + 1)
    voice.effect_delay = (inst.effect_delay + 1) & 0xFF
    voice.effect = inst.effect
    voice.eg_value = 0
    voice.start, voice.length = score.table(inst.wave), inst.wave_length
    voice.channel.queue(sample(score, voice.start, voice.length))
    if voice.adsr.mode != Mode.OFF:
        if voice.volume == USE_INSTRUMENT:
            voice.volume = inst.volume
        voice.channel.set_volume(adsr_volume(voice.adsr.table[0], voice.volume))
    else:
        volume = inst.volume if voice.volume == USE_INSTRUMENT else voice.volume
        voice.channel.set_volume(volume)
    if voice.eg.mode != Mode.OFF or voice.mod.mode != Mode.OFF or voice.effect:
        SaveWave(module, voice)
    module.dma_on.add(voice.number)


def SaveWave(module: Module, voice: Voice) -> None:
    assert voice.start is not None
    saved = module.saved[voice.number]
    saved.address = voice.start
    saved.data = bytes(module.score.memory[voice.start : voice.start + SAVED])


def adsr_volume(value: int, volume: int) -> int:
    """A signed table value, as 0..63, times the voice volume, / 64."""
    return ((((value + 128) & 0xFF) >> 2) * volume) >> 6


# --- Synth walkers ------------------------------------------------------


def RunWalkers(module: Module) -> None:
    """Per synth voice: `ADSR`, `LFO`, then, if the note saved its wave,
    `EG`, the effect and `MOD`."""
    for voice, saved in zip(module.voices, module.saved):
        if not voice.synth:
            continue
        AdsrWalker(voice)
        LfoWalker(module, voice)
        if saved.address is None:
            continue
        EgWalker(module, voice, saved)
        WaveEffect(module, voice, saved)
        ModWalker(module, voice, saved.address)


def AdsrWalker(voice: Voice) -> None:
    """The volume holds between steps. Once mode stops on the last value."""
    if voice.adsr.mode == Mode.OFF or not voice.adsr.due():
        return
    value = voice.adsr.step()
    assert value is not None
    voice.channel.set_volume(adsr_volume(value, voice.volume))


def LfoWalker(module: Module, voice: Voice) -> None:
    """The signed value / depth goes on the period, only at a step:
    TickVoice writes the plain period on the other ticks."""
    if voice.lfo.mode == Mode.OFF or not voice.lfo.due():
        return
    value = voice.lfo.step()
    assert value is not None
    depth = synth_instrument(module.score, voice.instrument).lfo_depth
    offset = divs(signed(value), depth) if depth else signed(value)
    voice.channel.period = (voice.period + offset) & 0xFFFF


def EgWalker(module: Module, voice: Voice, saved: SavedWave) -> None:
    """The value, as 0..31, is how many leading samples are negated
    copies of the saved ones. Only the samples between the old and the
    new count change."""
    if voice.eg.mode == Mode.OFF or not voice.eg.due():
        return
    value = voice.eg.step()
    assert value is not None and saved.address is not None
    new, old = ((value + 128) & 0xFF) >> 3, voice.eg_value
    voice.eg_value = new
    memory, at = module.score.memory, saved.address
    for n in range(old, new):
        memory[at + n] = -saved.data[n] & 0xFF
    for n in range(new, old):
        memory[at + n] = saved.data[n]


def WaveEffect(module: Module, voice: Voice, saved: SavedWave) -> None:
    """The effect number picks one; 0 and 7 and up do nothing."""
    effects: dict[int, Callable[[Module, Voice, SavedWave], None]] = {
        1: SmoothWave,
        2: MorphToMirror,
        3: MorphToSaved,
        4: MorphToNext,
        5: MorphToSavedCopy,
        6: CopyNextTable,
    }
    if handler := effects.get(voice.effect):
        handler(module, voice, saved)


def effect_due(module: Module, voice: Voice) -> bool:
    voice.effect_delay = (voice.effect_delay - 1) & 0xFF
    if voice.effect_delay:
        return False
    inst = synth_instrument(module.score, voice.instrument)
    voice.effect_delay = inst.effect_speed
    return True


def SmoothWave(module: Module, voice: Voice, saved: SavedWave) -> None:
    """Every `speed` ticks: each byte becomes the mean of the new byte
    before it and the old byte after it. The first reads the byte before
    the wave, the last byte 32."""
    if not effect_due(module, voice):
        return
    memory, at = module.score.memory, saved.address
    assert at is not None
    before = signed(memory[at - 1])
    for n in range(SAVED):
        before = (signed(memory[at + n + 1]) + before) >> 1
        memory[at + n] = before & 0xFF


def move_towards(module: Module, voice: Voice, at: int, targets: bytes) -> None:
    """Each byte moves by `speed` towards its target, every tick. A
    step larger than the gap overshoots, so the byte may swing."""
    speed = synth_instrument(module.score, voice.instrument).effect_speed
    memory = module.score.memory
    for n, target in enumerate(targets):
        now = signed(memory[at + n])
        if signed(target) > now:
            memory[at + n] = (memory[at + n] + speed) & 0xFF
        elif signed(target) < now:
            memory[at + n] = (memory[at + n] - speed) & 0xFF


def MorphToMirror(module: Module, voice: Voice, saved: SavedWave) -> None:
    """Towards the saved bytes in reverse order: a mirrored wave."""
    assert saved.address is not None
    move_towards(module, voice, saved.address, saved.data[::-1])


def MorphToSaved(module: Module, voice: Voice, saved: SavedWave) -> None:
    """Towards the saved bytes: it undoes `EG` and `MOD` changes."""
    assert saved.address is not None
    move_towards(module, voice, saved.address, saved.data)


def MorphToNext(module: Module, voice: Voice, saved: SavedWave) -> None:
    """Towards the next table in the pool."""
    at = saved.address
    assert at is not None
    after = bytes(module.score.memory[at + TABLE_SIZE : at + TABLE_SIZE + SAVED])
    move_towards(module, voice, at, after)


def MorphToSavedCopy(module: Module, voice: Voice, saved: SavedWave) -> None:
    """A second copy of MorphToSaved's code."""
    MorphToSaved(module, voice, saved)


def CopyNextTable(module: Module, voice: Voice, saved: SavedWave) -> None:
    """After the delay, the next table's first 32 bytes replace the
    wave's, once; the effect turns off."""
    if not effect_due(module, voice):
        return
    voice.effect, voice.effect_delay = 0, 1
    memory, at = module.score.memory, saved.address
    assert at is not None
    memory[at : at + SAVED] = memory[at + TABLE_SIZE : at + TABLE_SIZE + SAVED]


def ModWalker(module: Module, voice: Voice, at: int) -> None:
    """The value replaces wave byte 32, past the saved bytes: the next
    note does not restore it. In a 16-word wave, byte 32 is the next
    table's first byte."""
    if voice.mod.mode == Mode.OFF or not voice.mod.due():
        return
    value = voice.mod.step()
    assert value is not None
    module.score.memory[at + MOD_BYTE] = value
