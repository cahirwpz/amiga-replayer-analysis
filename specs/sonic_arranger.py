"""Sonic Arranger's replay: Sonic Arranger_v1.asm, Wanted Team's
adaptation of the Sonic Arranger 2.18 player (Carsten Schlote, Branko
Mikić and Carsten Herbst, 1991-95).

Card: players/SonicArranger.md. Level 2: the control flow runs. Each
CamelCase function is a new name in data/annot/SonicArranger.yaml; each
CamelCase class is in its `types:`. Comments name the voice fields by
their offsets in the voice record.

A position gives each voice a start row in one shared list of rows. The
voice reads `pattern length` rows from there. An instrument is a sample
or a synth wave. A synth note copies its wave into the voice's own
buffer; Paula plays that copy, and one of 17 wave effects rewrites it
every N ticks. Two tables run per note: pitch offsets (the format's
`AMF`) and volume (its `ADSR`). DeliTracker's volume, balance and
analyser hooks, the pattern display and the editor's voice switches are
left out. So is the sound effect entry, which the adaptation keeps only
as a comment: it locks a voice for some rows and plays one note there.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from typing import cast

from hardware import paula
from hardware.amiga import Amiga, Priority
from hardware.clock import LINE_CCK

Then = Callable[[], None]

VOICES = 4
WAVE_SIZE = 128  # waves, pitch tables and volume tables: 128 bytes each
ARPEGGIO_SIZE = 16  # loop start, loop length, then 14 note offsets
HOLD, NOTE_OFF = 0x80, 0x7F  # a row's note byte
MAX_VOLUME = 64
MIN_PERIOD = 0x71
VIBRATO_OFF = 0xFF  # the low byte of the vibrato delay
E_CLOCK = 0xAD303  # CIA counts per second, PAL: the original's timer base
SLOTS_END = 0x16  # the beam position after the audio DMA slots
POLL_CCK = 15  # one INTREQR poll: about 30 68000 cycles (estimate)
SILENCE = paula.Sample(bytes(2))  # a one-word buffer of zeros

PERIODS = (  # Periods: index 0 is no note; 108 notes, 9 octaves
    0,
    *(13696, 12928, 12192, 11520, 10848, 10240, 9664, 9120, 8608, 8128, 7680, 7248),
    *(6848, 6464, 6096, 5760, 5424, 5120, 4832, 4560, 4304, 4064, 3840, 3624),
    *(3424, 3232, 3048, 2880, 2712, 2560, 2416, 2280, 2152, 2032, 1920, 1812),
    *(1712, 1616, 1524, 1440, 1356, 1280, 1208, 1140, 1076, 1016, 960, 906),
    *(856, 808, 762, 720, 678, 640, 604, 570, 538, 508, 480, 453),
    *(428, 404, 381, 360, 339, 320, 302, 285, 269, 254, 240, 226),
    *(214, 202, 190, 180, 170, 160, 151, 143, 135, 127, 120, 113),
    *(107, 101, 95, 90, 85, 80, 75, 71, 67, 63, 60, 56),
    *(53, 50, 47, 45, 42, 40, 37, 35, 33, 31, 30, 28),
    0xFFFF,
)

VIBRATO = bytes.fromhex(  # VibratoTable: one sine cycle, 256 signed bytes
    "000306090c101316191c1f2225282b2e313436393c3f424447494c4e51535658"
    "5a5c5e60626466686a6c6d6f70727374767778797a7b7b7c7d7d7e7e7e7f7f7f"
    "7f7f7f7f7e7e7d7d7c7c7b7a7978777675747271706e6c6b69676563615f5d5b"
    "59575452504d4b484543403d3b3835322f2c292724201d1a1714110e0b080502"
    "fffcf9f6f2efece9e6e3e0dddad7d4d1cecbc9c6c3c0bebbb8b6b3b1aeacaaa8"
    "a5a3a19f9d9b999896949391908e8d8c8a898887868685848483838282828282"
    "82828282828383848485868788898a8b8c8d8f9092939597989a9c9ea0a2a4a6"
    "a9abadb0b2b5b7babcbfc2c4c7cacdd0d3d6d9dbdee2e5e8ebeef1f4f7fafd00"
)


# --- What the composer edits -------------------------------------------


@dataclass
class Row:  # 4 bytes: note, instrument, control, argument
    note: int  # 0 none, $80 hold, $7f note-off
    instrument: int  # 0 none; numbers start at 1
    control: int  # bits 4-5 arpeggio, bit 6 and 7 skip transposes, 0-3 command
    argument: int

    @property
    def arpeggio(self) -> int:
        """0: none; 1-3: one of the instrument's three arpeggios."""
        return (self.control >> 4) & 3

    @property
    def command(self) -> int:
        return self.control & 0x0F


@dataclass
class Track:  # one voice's part of a position: 4 bytes
    start: int  # a row number in the shared row list
    instrument_transpose: int  # signed byte
    note_transpose: int  # signed byte


@dataclass
class Subsong:  # 6 words
    speed: int  # ticks per row
    rows: int  # pattern length
    first: int  # position
    last: int
    restart: int
    hz: int  # ticks per second; 0 keeps the timer


@dataclass
class Instrument:  # 152 bytes
    synth: bool  # $00
    wave: int  # $02: a wave number, or a sample number
    length: int  # $04: words
    repeat: int  # $06: a sample's loop, words; 0 the whole, 1 none
    volume: int  # $10
    fine_tune: int  # $12: the low byte is signed
    portamento: int  # $14: speed; 0 off
    vibrato_delay: int  # $16: $ff in the low byte is off
    vibrato_speed: int  # $18
    vibrato_depth: int  # $1a: divides the sine
    pitch_table: int  # $1c: the pitch table's number
    pitch_delay: int  # $1e
    pitch_length: int  # $20: bytes played once
    pitch_repeat: int  # $22: bytes looped after them
    volume_table: int  # $24
    volume_delay: int  # $26
    volume_length: int  # $28
    volume_repeat: int  # $2a
    sustain_point: int  # $2c
    sustain_delay: int  # $2e
    effect_arg: int  # $40: a value, or the second wave's number
    effect: int  # $42: 0-17
    start: int  # $44: first byte of the effect's range
    end: int  # $46: last byte of the range
    effect_delay: int  # $48
    arpeggios: tuple[bytes, bytes, bytes]  # $4a: 16 bytes each


@dataclass
class Score:  # the module, after the loader has resolved its pointers
    subsongs: list[Subsong]
    positions: list[tuple[Track, Track, Track, Track]]  # 16 bytes each
    rows: list[Row]  # all tracks' rows, in one list
    instruments: list[Instrument]
    samples: list[bytes]  # empty: no sample
    waves: list[bytes]  # WavePool
    volume_tables: list[bytes]  # AdsrPool: unsigned levels
    pitch_tables: list[bytes]  # AmfPool: signed period offsets


# --- Voice state -------------------------------------------------------


@dataclass
class Voice:  # 206 bytes each, in chip memory
    channel: paula.Channel
    bit: int  # this channel's DMACON bit
    wave: bytearray = field(default_factory=lambda: bytearray(WAVE_SIZE))  # $00
    note: int = 0  # $80
    previous: int = 0  # $82: the last note, where a portamento starts
    pitch_offset: int = 0  # $84: subtracted from the period
    slide: int = 0  # $86: added to the offset each tick but the row's
    number: int = 0  # $88: the instrument's number
    instrument: Instrument | None = None  # $8a
    volume: int = 0  # $8e
    volume_slide: int = 0  # $90
    vibrato_pos: int = 0  # $92
    vibrato_delay: int = 0  # $94
    portamento: int = 0  # $9a: speed; 0 off
    glide: int = 0  # $9c: the gliding period; 0 not started
    volume_pos: int = 0  # $9e
    sustain_wait: int = 0  # $a0
    volume_wait: int = 0  # $a2
    pitch_pos: int = 0  # $a4
    pitch_wait: int = 0  # $a6
    effect_pos: int = 0  # $a8
    effect_count: int = 0  # $aa: effects 2, 8, 10 and 17
    effect_wait: int = 0  # $ac
    arpeggio_pos: int = 0  # $ae
    row_arpeggio: int = 0  # $b0: 0, 1, 2
    silent: bool = True  # $b5 bit 0
    morphed: bool = False  # bit 1: effects 9 and 15 reached the target
    pulse_done: bool = False  # bit 2: effect 2 stopped
    morph_back: bool = False  # bit 3: effect 15 heads for the first wave
    playing_synth: bool = False  # $ba: the note's instrument is a synth
    loop_pending: bool = False  # one byte per voice: write the loop next tick
    track: int = 0  # the row number this voice reads
    track_transposes: Track = field(default_factory=lambda: Track(0, 0, 0))
    row: Row = field(default_factory=lambda: Row(0, 0, 0, 0))  # the current row


@dataclass
class Module:  # the song's state words and the four voices
    score: Score
    amiga: Amiga
    voices: list[Voice] = field(default_factory=list)
    speed: int = 6
    rows: int = 64
    first: int = 0
    last: int = 0
    restart: int = 0
    hz: int = 50
    tick: int = 0
    row: int = 0
    position: int = 0
    master: int = MAX_VOLUME
    dma_on: int = 0  # channels to start at the tick's end
    filter_on: bool = True
    ended: bool = False


def signed(byte: int) -> int:
    byte &= 0xFF
    return byte - 256 if byte & 0x80 else byte


def word(value: int) -> int:
    """A signed 16-bit register."""
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def neg(byte: int) -> int:
    return -byte & 0xFF


def table_byte(tables: list[bytes], number: int, pos: int) -> int:
    """Tables lie end to end, 128 bytes each: a position past 127 reads
    the next table. Past the last one the model gives 0."""
    at, i = divmod(number * WAVE_SIZE + pos, WAVE_SIZE)
    return tables[at][i] if at < len(tables) else 0


def period_of(note: int) -> int:
    """Past index 109 the code reads the table that follows; the model
    gives 0."""
    return PERIODS[note] if 0 <= note < len(PERIODS) else 0


def new_module(score: Score, amiga: Amiga) -> Module:
    """DeliTracker calls Play by its own timer; InitSong sets its rate."""
    module = Module(score, amiga)
    module.voices = [Voice(c, 1 << c.number) for c in amiga.paula.channels]
    amiga.timer.on_underflow = lambda: Play(module)
    return module


def InitSong(module: Module, number: int) -> None:
    """The subsong's six words. The first tick reads a row, and that row
    starts the first position."""
    ResetVoices(module)
    song = module.score.subsongs[number]
    module.speed, module.rows = song.speed, song.rows
    module.first, module.last, module.restart = song.first, song.last, song.restart
    module.hz = song.hz
    module.position = song.first - 1
    module.tick, module.row = song.speed, song.rows
    module.master = MAX_VOLUME
    SetTimer(module)
    module.amiga.timer.start()


def ResetVoices(module: Module) -> None:
    module.voices = [Voice(v.channel, v.bit) for v in module.voices]


def SetTimer(module: Module) -> None:
    """The subsong's rate in Hz sets the CIA timer: E clock / Hz. The
    adaptation takes the same value from DeliTracker's timer × 50."""
    if module.hz:
        module.amiga.timer.set_latch(E_CLOCK // module.hz)


# --- Tick ---------------------------------------------------------------


def Play(module: Module) -> None:
    """First the loops of last tick's samples. Every `speed` ticks a row.
    Then all voices. Channels whose note started go on last."""
    write_loops(module)
    module.tick += 1
    if module.tick >= module.speed:
        module.tick = 0
        PlayRow(module, lambda: end_tick(module))
    else:
        end_tick(module)


def end_tick(module: Module) -> None:
    TickVoices(module)
    for voice in module.voices:
        if module.dma_on & voice.bit:
            voice.channel.enable()
    module.dma_on = 0


def write_loops(module: Module) -> None:
    for voice in module.voices:
        if voice.loop_pending:
            WriteLoop(module, voice)
        voice.loop_pending = False


def WriteLoop(module: Module, voice: Voice) -> None:
    """A tick after a sample starts: its loop. Repeat 0 loops the whole
    sample; 1 plays silence. A sample whose first pass is shorter than
    a tick plays twice."""
    inst = voice.instrument
    if inst is None or inst.repeat == 0:
        return
    sample = module.score.samples[inst.wave]
    if inst.repeat == 1 or not sample:
        voice.channel.queue(SILENCE)
        return
    at = 2 * inst.length
    voice.channel.queue(paula.Sample(sample[at : at + 2 * inst.repeat]))


def PlayRow(module: Module, then: Then) -> None:
    """The next row of each track; after `pattern length` rows, the next
    position."""
    module.row += 1
    if module.row >= module.rows:
        module.row = 0
        ReadPosition(module)
    else:
        NextRow(module)
    ReadRows(module, then)


def ReadPosition(module: Module) -> None:
    """After the last position, the restart position; the song ends
    there (SongEnd). A position gives each voice a start row in the
    shared list, and its transposes. Tracks may overlap."""
    module.position += 1
    if module.position > module.last:
        module.position = module.restart
        module.ended = True  # SongEnd
    tracks = module.score.positions[module.position]
    for voice, track in zip(module.voices, tracks):
        voice.track = track.start
        voice.track_transposes = track
        voice.row = module.score.rows[voice.track]


def NextRow(module: Module) -> None:
    for voice in module.voices:
        voice.track += 1
        voice.row = module.score.rows[voice.track]


def ReadRows(module: Module, then: Then) -> None:
    """Voice by voice, since a note start may busy-wait."""

    def read(index: int) -> None:
        if index == VOICES:
            then()
            return
        ReadVoiceRow(module, module.voices[index], partial(read, index + 1))

    read(0)


def ReadVoiceRow(module: Module, voice: Voice, then: Then) -> None:
    """A row without a note may set the instrument: its settings and
    tables restart, the wave copy plays on. $80 holds the note; $7f
    ends it. A note after a synth note does not stop the channel: the
    new wave overwrites the playing copy, and a new sample starts at
    the copy's next loop. A note after a sample waits for the channel
    to stop."""
    row = voice.row
    if row.note == 0:
        if row.instrument:
            SetInstrument(module, voice, row.instrument)
        RowCommand(module, voice)
        then()
        return
    if row.note == HOLD:
        RowCommand(module, voice)
        then()
        return
    if row.note == NOTE_OFF:
        VoiceOff(voice)
        RowCommand(module, voice)
        then()
        return
    note, number = row.note, row.instrument
    if not row.control & 0x40:
        note += voice.track_transposes.note_transpose
    if number and not row.control & 0x80:
        number += voice.track_transposes.instrument_transpose
    number &= 0xFF
    voice.previous, voice.note = voice.note, note
    if not voice.previous:
        voice.previous = note

    def start() -> None:
        if number:
            SetInstrument(module, voice, number)
        elif voice.instrument is None:
            VoiceOff(voice)  # and no command: the code jumps, not calls
            then()
            return
        else:
            RestartInstrument(module, voice)
        assert voice.instrument is not None
        voice.playing_synth = voice.instrument.synth
        if voice.playing_synth:
            StartSynthWave(module, voice)
        else:
            StartSample(module, voice)
        RowCommand(module, voice)
        then()

    if voice.playing_synth:
        start()
    else:
        StopChannel(module, voice, start)


def StopChannel(module: Module, voice: Voice, then: Then) -> None:
    """Wanted Team's stop. Next line, after the audio slots: period 1,
    DMA off, poll until the channel requests its interrupt. The
    original instead wrote DMA off, length 1 and period $72 and did not
    wait: the rest of the tick gave the channel time to stop."""
    amiga = module.amiga
    channel = voice.channel

    def poll() -> None:
        if channel.irq_requested:
            then()
        else:
            amiga.after(POLL_CCK, Priority.CPU, poll)

    def stop() -> None:
        channel.period = 1
        if not channel.dma:
            then()
            return
        channel.irq_requested = False
        channel.disable()
        poll()

    line = amiga.now - amiga.now % LINE_CCK + LINE_CCK
    amiga.schedule(line + SLOTS_END, Priority.CPU, stop)


def SetInstrument(module: Module, voice: Voice, number: int) -> None:
    """Volume, portamento and vibrato from the instrument, then the
    tables. A number past the last instrument gives the last one."""
    voice.number = number
    number = min(number, len(module.score.instruments))
    inst = voice.instrument = module.score.instruments[number - 1]
    voice.volume = inst.volume
    voice.portamento = inst.portamento
    voice.glide = voice.vibrato_pos = 0
    voice.vibrato_delay = inst.vibrato_delay
    RestartInstrument(module, voice)


def RestartInstrument(module: Module, voice: Voice) -> None:
    """Fine tune, both tables, the effect and the arpeggio restart. The
    voice may sound again."""
    inst = voice.instrument
    assert inst is not None
    voice.pitch_offset = signed(inst.fine_tune)
    voice.volume_wait, voice.volume_pos, voice.sustain_wait = inst.volume_delay, 0, 0
    voice.pitch_wait, voice.pitch_pos = inst.pitch_delay, 0
    voice.effect_pos, voice.effect_count = inst.start, 0
    voice.effect_wait = inst.effect_delay
    voice.arpeggio_pos = voice.row_arpeggio = 0
    voice.silent = voice.morphed = voice.pulse_done = voice.morph_back = False


def StartSample(module: Module, voice: Voice) -> None:
    """The start plays the first part and the loop once. The loop
    follows a tick later: see WriteLoop. A missing sample silences the
    voice."""
    inst = voice.instrument
    assert inst is not None
    sample = module.score.samples[inst.wave]
    if not sample:
        voice.silent = True
        VoiceOff(voice)
        voice.loop_pending = False
        return
    length = inst.length + (0 if inst.repeat == 1 else inst.repeat)
    voice.channel.queue(paula.Sample(sample[: 2 * length]))
    module.dma_on |= voice.bit
    voice.loop_pending = True


def StartSynthWave(module: Module, voice: Voice) -> None:
    """Copy the wave into the voice's buffer; Paula plays the buffer.
    The copy runs in blocks of 16 bytes."""
    inst = voice.instrument
    assert inst is not None
    size = (((inst.length - 1) >> 3) + 1) * 16
    voice.wave[:size] = first(module, inst)[:size]
    # DMA reads the buffer as it plays, so the effects change the sound.
    voice.channel.queue(paula.Sample(cast(bytes, voice.wave)))
    voice.channel.length = inst.length
    module.dma_on |= voice.bit
    voice.loop_pending = False


def VoiceOff(voice: Voice) -> None:
    """Volume 0 and a silent loop. DMA stays on. The instrument is gone,
    so the voice stays silent until a note names one."""
    voice.channel.set_volume(0)
    voice.channel.queue(SILENCE)
    voice.volume = voice.number = 0
    voice.instrument = None
    voice.loop_pending = False


# --- Row commands -------------------------------------------------------


def RowCommand(module: Module, voice: Voice) -> None:
    """Slides last one row: each row clears them first."""
    voice.slide = voice.volume_slide = 0
    COMMANDS[voice.row.command](module, voice, voice.row.argument)


def NoCommand(module: Module, voice: Voice, arg: int) -> None:
    """Command 0 is also the row arpeggio: see RowArpeggio."""


def CmdSlide(module: Module, voice: Voice, arg: int) -> None:
    """1: a signed step per tick; positive raises the pitch."""
    voice.slide = signed(arg)


def CmdVolumePosition(module: Module, voice: Voice, arg: int) -> None:
    """2: jump in the volume table."""
    voice.volume_pos = arg


def CmdVibrato(module: Module, voice: Voice, arg: int) -> None:
    """4: the vibrato starts now. The code stores a speed and a depth
    from the argument, but the vibrato reads the instrument's: the
    argument has no effect."""
    voice.vibrato_delay = 0


def CmdSync(module: Module, voice: Voice, arg: int) -> None:
    """5: a value for the host program; the adaptation drops it."""


def CmdMasterVolume(module: Module, voice: Voice, arg: int) -> None:
    """6: scales every voice from the next volume write."""
    module.master = arg if arg == MAX_VOLUME else arg & 0x3F


def CmdPortamento(module: Module, voice: Voice, arg: int) -> None:
    """7: glide from the previous note at this speed."""
    voice.portamento = arg


def CmdPortamentoOff(module: Module, voice: Voice, arg: int) -> None:
    voice.portamento = 0


def CmdPatternLength(module: Module, voice: Voice, arg: int) -> None:
    """9: 1-64 rows, for all voices from now on."""
    if 0 < arg <= 0x40:
        module.rows = arg


def CmdVolumeSlide(module: Module, voice: Voice, arg: int) -> None:
    """A: a signed step per tick, every tick."""
    voice.volume_slide = signed(arg)


def CmdPositionJump(module: Module, voice: Voice, arg: int) -> None:
    """B: the next row starts position `arg`."""
    module.position = arg - 1
    module.row = module.rows


def CmdVolume(module: Module, voice: Voice, arg: int) -> None:
    """C: at most 64."""
    voice.volume = min(arg, MAX_VOLUME)


def CmdPatternBreak(module: Module, voice: Voice, arg: int) -> None:
    """D: the next row starts the next position."""
    module.row = module.rows


def CmdFilter(module: Module, voice: Voice, arg: int) -> None:
    """E: 0 turns the audio filter on, other values off."""
    module.filter_on = arg == 0


def CmdSpeed(module: Module, voice: Voice, arg: int) -> None:
    """F: 1-16 ticks per row."""
    if 0 < signed(arg) <= 0x10:
        module.speed = arg


COMMANDS: tuple[Callable[[Module, Voice, int], None], ...] = (
    NoCommand,
    CmdSlide,
    CmdVolumePosition,
    NoCommand,
    CmdVibrato,
    CmdSync,
    CmdMasterVolume,
    CmdPortamento,
    CmdPortamentoOff,
    CmdPatternLength,
    CmdVolumeSlide,
    CmdPositionJump,
    CmdVolume,
    CmdPatternBreak,
    CmdFilter,
    CmdSpeed,
)


# --- Voices, every tick -------------------------------------------------


def TickVoices(module: Module) -> None:
    for voice in module.voices:
        VoiceTick(module, voice)


def VoiceTick(module: Module, voice: Voice) -> None:
    """Arpeggio, portamento, vibrato and the pitch table make the
    period. Then the wave effect, for synth sounds, and the volume
    table. A silent voice plays the silent word at volume 0."""
    inst = voice.instrument
    if voice.silent or inst is None:
        voice.channel.set_volume(0)
        voice.channel.queue(SILENCE)
        return
    note, previous = Arpeggio(voice, inst)
    period = Portamento(voice, note, previous)
    period = Vibrato(voice, inst, period)
    period = PitchWalker(module, voice, inst, period)
    SetPitch(module, voice, period)
    if inst.synth:
        WaveEffect(module, voice, inst)
    VolumeWalker(module, voice, inst)


def Arpeggio(voice: Voice, inst: Instrument) -> tuple[int, int]:
    """The row's flags pick one of three arpeggios; the current row
    counts, so each row may pick another. An arpeggio plays its offsets
    from the first, then loops from its loop start. Without one,
    command 0 with an argument is the row arpeggio."""
    note, previous = voice.note, voice.previous
    table = voice.row.arpeggio
    if not table:
        return RowArpeggio(voice, note, previous)
    arp = inst.arpeggios[table - 1]
    offset = arp[2 + voice.arpeggio_pos]
    note = (note & 0xFF00) | ((note + offset) & 0xFF)
    previous = (previous & 0xFF00) | ((previous + offset) & 0xFF)
    voice.arpeggio_pos += 1
    if voice.arpeggio_pos >= arp[0] + arp[1]:
        voice.arpeggio_pos = arp[0]
    return note, previous


def RowArpeggio(voice: Voice, note: int, previous: int) -> tuple[int, int]:
    """Command 0 xy: the note, +x, +y, one per tick."""
    row = voice.row
    if row.command or not row.argument:
        return note, previous
    step = voice.row_arpeggio
    voice.row_arpeggio = (step + 1) % 3
    offset = (0, row.argument >> 4, row.argument & 0x0F)[step]
    return note + offset, previous + offset


def Portamento(voice: Voice, note: int, previous: int) -> int:
    """The glide starts at the previous note's period and moves by the
    speed each tick. Within one step of the target it turns itself off.
    A note without an instrument keeps the gliding period."""
    target = period_of(note)
    if not voice.portamento:
        return target
    if not voice.glide:
        voice.glide = period_of(previous)
    if abs(target - voice.glide) - voice.portamento < 0:
        voice.portamento = 0
        return target
    if voice.glide >= target:
        voice.glide -= voice.portamento
    else:
        voice.glide += voice.portamento
    return voice.glide


def Vibrato(voice: Voice, inst: Instrument, period: int) -> int:
    """After the delay, the sine × 4 / depth: a larger depth gives a
    smaller vibrato. Depth 0 adds nothing."""
    if voice.vibrato_delay & 0xFF == VIBRATO_OFF:
        return period
    if voice.vibrato_delay:
        voice.vibrato_delay -= 1
        return period
    value = signed(VIBRATO[voice.vibrato_pos]) * 4
    if inst.vibrato_depth:
        period += int(value / inst.vibrato_depth)
    voice.vibrato_pos = (voice.vibrato_pos + inst.vibrato_speed) & 0xFF
    return period


def PitchWalker(module: Module, voice: Voice, inst: Instrument, period: int) -> int:
    """The pitch table: a signed byte per step, subtracted from the
    period. It steps every `delay` ticks. Its first `length` bytes play
    once, the next `repeat` bytes loop; without a repeat the last byte
    holds."""
    total = inst.pitch_length + inst.pitch_repeat
    if not total:
        return period
    tables = module.score.pitch_tables
    period -= signed(table_byte(tables, inst.pitch_table, voice.pitch_pos))
    voice.pitch_wait = (voice.pitch_wait - 1) & 0xFFFF
    if not voice.pitch_wait:
        voice.pitch_wait = inst.pitch_delay
        voice.pitch_pos += 1
        if voice.pitch_pos >= total:
            back = 0 if inst.pitch_repeat else 1
            voice.pitch_pos = inst.pitch_length - back
    return period


def SetPitch(module: Module, voice: Voice, period: int) -> None:
    """Minus the pitch offset: fine tune, slides, and effects 10 and 17.
    At least $71. The slide adds on every tick but the row's."""
    period = max(word(period - voice.pitch_offset), MIN_PERIOD)
    if module.tick:
        voice.pitch_offset = word(voice.pitch_offset + voice.slide)
    voice.channel.period = period


def VolumeWalker(module: Module, voice: Voice, inst: Instrument) -> None:
    """Level = volume × table value × master volume / 64². Without a
    volume table, volume × master / 64. Then the volume slide."""
    total = inst.volume_length + inst.volume_repeat
    if not total:
        voice.channel.set_volume(voice.volume * module.master >> 6)
        VolumeSlide(voice)
        return
    tables = module.score.volume_tables
    level = table_byte(tables, inst.volume_table, voice.volume_pos)
    value = level * module.master >> 6
    voice.channel.set_volume((voice.volume * value >> 6) & 0x7F)
    AdsrSustain(voice, inst, value)
    VolumeSlide(voice)


def AdsrSustain(voice: Voice, inst: Instrument, value: int) -> None:
    """While the rows hold the note ($80), the table stops at its
    sustain point. A sustain delay N does not stop it: the table then
    steps once every N + 1 ticks, and slower still with its own delay.
    A row without $80 lets the table run on: the release."""
    if voice.row.note != HOLD or voice.volume_pos < inst.sustain_point:
        AdsrStep(voice, inst, value)
        return
    if not inst.sustain_delay:
        return
    if voice.sustain_wait:
        voice.sustain_wait -= 1
        return
    voice.sustain_wait = inst.sustain_delay
    AdsrStep(voice, inst, value)


def AdsrStep(voice: Voice, inst: Instrument, value: int) -> None:
    """Every `delay` ticks one byte; the loop is as in PitchWalker. A
    table without a repeat that ends on 0 silences the voice until the
    next note."""
    voice.volume_wait = (voice.volume_wait - 1) & 0xFFFF
    if voice.volume_wait:
        return
    voice.volume_wait = inst.volume_delay
    voice.volume_pos += 1
    total = inst.volume_length + inst.volume_repeat
    if voice.volume_pos < total:
        return
    back = 0 if inst.volume_repeat else 1
    voice.volume_pos = inst.volume_length - back
    if not inst.volume_repeat and not value & 0xFF:
        voice.silent = True


def VolumeSlide(voice: Voice) -> None:
    voice.volume = min(max(voice.volume + voice.volume_slide, 0), MAX_VOLUME)


# --- Wave effects -------------------------------------------------------


def WaveEffect(module: Module, voice: Voice, inst: Instrument) -> None:
    """Every `effect delay` ticks, the instrument's effect rewrites the
    voice's copy. The changes pile up until the next note. Arguments:
    a value or a second wave (`effect_arg`), and a byte range `start`
    to `end`. The effect position walks the range: see EffectStep.

    | No. | Operation                                                  |
    | --- | ---------------------------------------------------------- |
    | 1   | Negate the byte at the position                            |
    | 2   | Pulse: negate the first W bytes of a fresh copy            |
    | 3   | Add the value to every byte of the range                   |
    | 4   | Rotate the range one byte left                             |
    | 5   | Add the second wave to the range                           |
    | 6   | Restore the byte at the position, negate the next one      |
    | 7   | Add one byte of the second wave to the range               |
    | 8   | Effect 7, and negate one byte at a moving position         |
    | 9   | Morph the range towards the second wave, 1 per byte        |
    | 10  | Raise the pitch by `start`, for `end` runs                 |
    | 11  | Move each byte away from its right neighbour               |
    | 12  | Flip bits of the byte at the position by the beam position |
    | 13  | Low-pass: move bytes 2 towards their neighbour             |
    | 14  | Effect 13, with limits read from the second wave           |
    | 15  | Morph to the second wave, back to the first, forever       |
    | 16  | Scramble the range and add the beam position               |
    | 17  | Lower the pitch by `start` × value each run; restart       |
    """
    voice.effect_wait = (voice.effect_wait - 1) & 0xFFFF
    if voice.effect_wait:
        NoEffect(module, voice, inst)
        return
    voice.effect_wait = inst.effect_delay
    if 1 <= inst.effect <= len(EFFECTS):
        EFFECTS[inst.effect - 1](module, voice, inst)


def NoEffect(module: Module, voice: Voice, inst: Instrument) -> None:
    """Effect 0, and the ticks between runs."""


def EffectStep(voice: Voice, inst: Instrument) -> None:
    """The effect position moves one byte, from `start` to `end`, then
    back to `start`. Effects 2, 5, 9, 15 and 16 do not move it."""
    voice.effect_pos += 1
    if voice.effect_pos > inst.end:
        voice.effect_pos = inst.start


def span(inst: Instrument) -> range:
    return range(inst.start, inst.end + 1)


def other(module: Module, inst: Instrument) -> bytes:
    """The second wave, named by the effect's argument. Some effects
    read past its end, into the next wave."""
    return wave_from(module.score.waves, inst.effect_arg)


def first(module: Module, inst: Instrument) -> bytes:
    """The instrument's own wave, unchanged."""
    return wave_from(module.score.waves, inst.wave)


def wave_from(waves: list[bytes], number: int) -> bytes:
    return bytes(table_byte(waves, number, i) for i in range(2 * WAVE_SIZE))


def beam(module: Module) -> int:
    """VHPOSR's low byte: the beam's horizontal position, in CCK."""
    return module.amiga.now % LINE_CCK


def Effect1(module: Module, voice: Voice, inst: Instrument) -> None:
    voice.wave[voice.effect_pos] = neg(voice.wave[voice.effect_pos])
    EffectStep(voice, inst)


def Effect2(module: Module, voice: Voice, inst: Instrument) -> None:
    """The width W is the second wave's byte at the counter, 0-127.
    Bytes from W on are the first wave's; bytes before W, negated. The
    counter runs to `start` + `end`, then back to `start`. With `end`
    0 and W 0 at that point, the effect stops."""
    if voice.pulse_done:
        return
    width = other(module, inst)[voice.effect_count] & 0x7F
    wave, size = first(module, inst), 2 * inst.length
    voice.wave[width:size] = wave[width:size]
    voice.wave[:width] = bytes(neg(b) for b in wave[:width])
    voice.effect_count += 1
    if voice.effect_count > inst.start + inst.end:
        voice.effect_count = inst.start
        if not inst.end and not width:
            voice.pulse_done = True


def Effect3(module: Module, voice: Voice, inst: Instrument) -> None:
    for i in span(inst):
        voice.wave[i] = (voice.wave[i] + inst.effect_arg) & 0xFF
    EffectStep(voice, inst)


def Effect4(module: Module, voice: Voice, inst: Instrument) -> None:
    """The rotation takes one byte past `end`."""
    a, b = inst.start, inst.end + 2
    voice.wave[a:b] = voice.wave[a + 1 : b] + voice.wave[a : a + 1]
    EffectStep(voice, inst)


def Effect5(module: Module, voice: Voice, inst: Instrument) -> None:
    wave = other(module, inst)
    for i in span(inst):
        voice.wave[i] = (voice.wave[i] + wave[i]) & 0xFF


def Effect6(module: Module, voice: Voice, inst: Instrument) -> None:
    pos = voice.effect_pos
    voice.wave[pos] = first(module, inst)[pos]
    j = (pos if pos < inst.end else inst.start - 1) + 1
    voice.wave[j] = neg(voice.wave[j])
    EffectStep(voice, inst)


def Effect7(module: Module, voice: Voice, inst: Instrument) -> None:
    AddOtherByte(module, voice, inst)
    EffectStep(voice, inst)


def AddOtherByte(module: Module, voice: Voice, inst: Instrument) -> None:
    """The second wave's byte at `start` + position, added to the
    range."""
    value = other(module, inst)[inst.start + voice.effect_pos]
    for i in span(inst):
        voice.wave[i] = (voice.wave[i] + value) & 0xFF


def Effect8(module: Module, voice: Voice, inst: Instrument) -> None:
    AddOtherByte(module, voice, inst)
    at = inst.start + voice.effect_count
    voice.wave[at] = neg(voice.wave[at])
    voice.effect_count += 1
    if voice.effect_count > inst.end - inst.start:
        voice.effect_count = 0
    EffectStep(voice, inst)


def Effect9(module: Module, voice: Voice, inst: Instrument) -> None:
    """Once the copy equals the second wave, the effect stops."""
    if not voice.morphed:
        Morph(voice, inst, other(module, inst))


def Effect15(module: Module, voice: Voice, inst: Instrument) -> None:
    """At each arrival the target swaps: the second wave, then the
    first, and so on."""
    if voice.morphed:
        voice.morph_back = not voice.morph_back
        voice.morphed = False
    target = first(module, inst) if voice.morph_back else other(module, inst)
    Morph(voice, inst, target)


def Morph(voice: Voice, inst: Instrument, target: bytes) -> None:
    """Each byte of the range moves 1 towards the target's byte."""
    changed = False
    for i in span(inst):
        b, t = voice.wave[i], target[i]
        if b != t:
            changed = True
            voice.wave[i] = (b + (1 if signed(b) < signed(t) else -1)) & 0xFF
    if not changed:
        voice.morphed = True


def Effect10(module: Module, voice: Voice, inst: Instrument) -> None:
    """The step is `start`'s low byte, signed; `end` counts the runs."""
    if voice.effect_count < inst.end:
        voice.pitch_offset = word(voice.pitch_offset + signed(inst.start))
        voice.effect_count += 1
    EffectStep(voice, inst)


def Effect11(module: Module, voice: Voice, inst: Instrument) -> None:
    """A byte above its right neighbour loses the value; others gain
    it. The last byte compares with the one past `end`."""
    for i in span(inst):
        b = voice.wave[i]
        step = (
            -inst.effect_arg
            if signed(b) > signed(voice.wave[i + 1])
            else inst.effect_arg
        )
        voice.wave[i] = (b + step) & 0xFF
    EffectStep(voice, inst)


def Effect12(module: Module, voice: Voice, inst: Instrument) -> None:
    voice.wave[voice.effect_pos] ^= beam(module)
    EffectStep(voice, inst)


def Effect13(module: Module, voice: Voice, inst: Instrument) -> None:
    smooth(voice, inst, [inst.effect_arg] * len(span(inst)))
    EffectStep(voice, inst)


def Effect14(module: Module, voice: Voice, inst: Instrument) -> None:
    """The limits come from the second wave, from byte `end` on."""
    wave = other(module, inst)
    count = len(span(inst))
    smooth(voice, inst, [b & 0x7F for b in wave[inst.end : inst.end + count]])
    EffectStep(voice, inst)


def smooth(voice: Voice, inst: Instrument, limits: list[int]) -> None:
    """A byte that differs from its right neighbour by more than its
    limit moves 2 towards it. The last byte's neighbour is the first
    of the range."""
    for k, i in enumerate(span(inst)):
        b = voice.wave[i]
        n = voice.wave[i + 1] if i != inst.end else voice.wave[inst.start]
        up = signed(b) <= signed(n)
        diff = (b - n) & 0xFF
        if diff & 0x80:
            diff = neg(diff)
        if diff > limits[k]:
            voice.wave[i] = (b + (2 if up else -2)) & 0xFF


def Effect16(module: Module, voice: Voice, inst: Instrument) -> None:
    """Each byte: xor 5, rotate left 2, add the beam position. The code
    reads the beam once per byte; the model reads it once."""
    noise = beam(module)
    for i in reversed(span(inst)):
        b = voice.wave[i] ^ 5
        b = ((b << 2) | (b >> 6)) & 0xFF
        voice.wave[i] = (b + noise) & 0xFF


def Effect17(module: Module, voice: Voice, inst: Instrument) -> None:
    """Each run lowers the pitch by `start` × value more. After `end`
    runs the pitch offset returns to the fine tune word, unmasked."""
    if voice.effect_count >= inst.end:
        voice.pitch_offset = word(inst.fine_tune)
        voice.effect_count = 0
    voice.pitch_offset = word(voice.pitch_offset - inst.start * inst.effect_arg)
    voice.effect_count += 1
    EffectStep(voice, inst)


EFFECTS: tuple[Callable[[Module, Voice, Instrument], None], ...] = (
    Effect1,
    Effect2,
    Effect3,
    Effect4,
    Effect5,
    Effect6,
    Effect7,
    Effect8,
    Effect9,
    Effect10,
    Effect11,
    Effect12,
    Effect13,
    Effect14,
    Effect15,
    Effect16,
    Effect17,
)
