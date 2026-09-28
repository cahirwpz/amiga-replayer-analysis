"""Synth Dream's replay: Synth Dream_v2.asm, Wanted Team's adaptation
of the player from the game Monster Business (Eclipse, 1991).

Card: players/SynthDream.md. Level 2: the control flow runs. Each
CamelCase function is a new name in data/annot/SynthDream.yaml; each
CamelCase class is in its `types:`. Comments name the voice fields by
their offsets in VoiceData.

Each voice reads its own position list and its own events. An event
carries a length in ticks and some of: note, volume, instrument, glide.
An instrument names four tables of runs: volume, note offset, fine
pitch and pulse wave. The pulse walker builds a 16-byte wave every
tick. DeliTracker's volume and analyser hooks (ChangeVolume, SetVol,
SetAll) are left out.
"""

from dataclasses import dataclass, field

from hardware import paula
from hardware.amiga import Amiga

VOICES = 4
SUBSONG_SIZE = 16  # 4 position list offsets
POSITION_SIZE = 12
INSTRUMENT_SIZE = 32
WAVE_SIZE = 16  # PulseWaves: 16 waves of 16 bytes
LOOP_POSITIONS, STOP_VOICE = 0xFE, 0xFF  # a position's first byte
PATTERN_END = 0xFF
TABLE_END = 0xFF  # a run's count byte: restart the table
FIRST_MODIFIER = 0x24  # events from here on have no length
UNITY = 0x2000  # ratios are x / 8192
FULL_VOLUME = 0x40
RISING_PERIOD = 0xFD00  # GlideToFit: the period rises, so the pitch falls
DEFAULT_LATCH = 14187  # DeliTracker's timer, 50 Hz (guess): no DTP_Timer tag

# Events: a word opcode, then its arguments
REST, SWITCH_VOLUME, LEGATO_OFF, LEGATO_ON = 0x1E, 0x24, 0x26, 0x28
GLIDE_UP, GLIDE_DOWN, SWITCH_FINE = 0x2A, 0x2C, 0x2E
FIT = ("length", "note", "glide")
EVENTS: dict[int, tuple[str, ...]] = {  # EventTable: the arguments, in order
    0x00: (),
    0x02: ("length",),
    0x04: ("note",),
    0x06: ("volume",),
    0x08: ("instrument",),
    0x0A: ("length", "note"),
    0x0C: ("length", "volume"),
    0x0E: ("length", "instrument"),
    0x10: ("note", "volume"),
    0x12: ("note", "instrument"),
    0x14: ("length", "note", "volume"),
    0x16: ("length", "note", "instrument"),
    0x18: FIT,
    0x1A: ("note", "volume", "instrument"),
    0x1C: ("length", "note", "volume", "instrument"),
    REST: ("length",),
    0x20: (*FIT, "instrument"),
    0x22: (*FIT, "instrument"),
}

PERIODS = (  # Periods: 144 notes, 12 octaves; each about halves the last
    *(
        53421,
        50423,
        47593,
        44921,
        42400,
        40020,
        37774,
        35654,
        33653,
        31764,
        29981,
        28299,
    ),
    *(
        26710,
        25211,
        23796,
        22461,
        21200,
        20010,
        18887,
        17827,
        16826,
        15882,
        14991,
        14149,
    ),
    *(13355, 12606, 11898, 11230, 10600, 10005, 9444, 8914, 8413, 7941, 7495, 7075),
    *(6678, 6303, 5949, 5615, 5300, 5003, 4722, 4457, 4207, 3971, 3748, 3537),
    *(3339, 3151, 2975, 2808, 2650, 2501, 2361, 2228, 2103, 1985, 1874, 1769),
    *(1669, 1576, 1487, 1404, 1325, 1251, 1180, 1114, 1052, 993, 937, 884),
    *(835, 788, 744, 702, 663, 625, 590, 557, 526, 496, 468, 442),
    *(417, 394, 372, 351, 331, 313, 295, 279, 263, 248, 234, 221),
    *(209, 197, 186, 175, 166, 156, 148, 139, 131, 124, 117, 111),
    *(104, 98, 93, 88, 83, 78, 74, 70, 66, 62, 59, 55),
    *(52, 49, 46, 44, 41, 39, 37, 35, 33, 31, 29, 28),
    *(26, 25, 23, 22, 21, 20, 18, 17, 16, 16, 15, 14),
)
RATIO_STEPS = 400  # 400 steps span one semitone, about 1/4 cent each


# --- What the composer edits -------------------------------------------


@dataclass
class Instrument:  # InstrumentTable: 32 bytes
    fixed: bool  # 1: ignore the position's transpose
    shift: int  # 2: a word; a signed byte offset into the ratio tables
    volume_table: int  # 4: offsets in the module; 0 none
    fine_table: int  # 8
    note_table: int  # 12
    pulse_table: int  # 16: 0 means a sample instrument
    start: int  # 20: in the sample file
    length: int  # 24: words
    loop: int  # 26
    loop_length: int  # 30: words


NO_INSTRUMENT = Instrument(False, 0, 0, 0, 0, 0, 0, 0, 0, 0)  # VoiceData starts at 0


@dataclass
class Score:  # SongPtr: the module; the samples are a second file
    data: bytes
    samples: bytes
    instruments: int  # InstrumentTable: offset
    volume_list: int  # VolumeTables: longs, table offsets for event $24
    fine_list: int  # FineTables: longs, for event $2e

    def word(self, at: int) -> int:
        return int.from_bytes(self.data[at : at + 2], "big")

    def long(self, at: int) -> int:
        return int.from_bytes(self.data[at : at + 4], "big")

    def instrument(self, number: int) -> Instrument:
        at = self.instruments + INSTRUMENT_SIZE * number
        return Instrument(
            fixed=self.data[at + 1] != 0,
            shift=signed_word(self.word(at + 2)),
            volume_table=self.long(at + 4),
            fine_table=self.long(at + 8),
            note_table=self.long(at + 12),
            pulse_table=self.long(at + 16),
            start=self.long(at + 20),
            length=self.word(at + 24),
            loop=self.long(at + 26),
            loop_length=self.word(at + 30),
        )


# --- Voice state -------------------------------------------------------


@dataclass
class Runs:  # a table walker: pointer 70-82, count 86-89, repeats 90-93
    """A table is runs: a count, a repeat number, then `count` values.
    A count byte of $ff restarts the table from `base`."""

    base: int = 0  # the instrument's table; 0 none
    pos: int = 0
    count: int = 0  # values left in this run
    size: int = 0  # the run's count, for a repeat
    repeats: int = 0
    width: int = 1  # bytes per value

    def restart(self, base: int) -> None:
        self.base = self.pos = base
        self.count = self.repeats = 0

    def step(self, data: bytes) -> int:
        """Once per tick. A run plays `count` values, then `repeats` more
        times. A count of 0 gives 256 values."""
        if not self.count:
            if self.repeats:
                self.pos -= self.width * self.size
                self.count = self.size
                self.repeats -= 1
            else:
                if data[self.pos] == TABLE_END:
                    self.pos = self.base
                self.count = self.size = data[self.pos]
                self.repeats = data[self.pos + 1]
                self.pos += 2
        value = int.from_bytes(data[self.pos : self.pos + self.width], "big")
        self.pos += self.width
        self.count = (self.count - 1) & 0xFF
        return value


@dataclass
class Voice:  # VoiceData: 206 bytes per voice
    channel: paula.Channel
    number: int
    positions: int = 0  # 2: the list's start
    next_position: int = 0  # 6
    pattern: int = 0  # 10: the pattern's start, for repeats
    event: int = 0  # 14: the next event
    transpose: int = 0  # 18
    repeats: int = 0  # 19
    swap_from: int = 0  # 20
    swap_to: int = 0  # 21
    position_volume: int = 0  # 23: subtracted from the volume
    left: int = 0  # 26: ticks left in the event
    length: int = 0  # 28: the event's length
    note: int = 0  # 30
    event_volume: int = 0  # 33: subtracted from the volume
    instrument: Instrument = field(default_factory=lambda: NO_INSTRUMENT)  # 38
    volume: Runs = field(default_factory=Runs)
    fine: Runs = field(default_factory=lambda: Runs(width=2))
    note_offset: Runs = field(default_factory=Runs)
    pulse: Runs = field(default_factory=lambda: Runs(width=2))
    glide: int = 0  # 94: the glide's ratio so far; 0 off
    glide_rate: int = 0  # 118: the ratio applied each tick
    glide_delay: int = 0  # 172
    offset: int = 0  # 96: the note table's value
    rest: bool = False  # 97
    period: int = 0  # 106
    level: int = 0  # 109
    stopped: bool = False  # 120
    volume_switch: int = 0  # 176: a table to switch to; 0 none
    volume_delay: int = 0  # 174
    fine_switch: int = 0  # 182
    fine_delay: int = 0  # 180
    wave: bytearray = field(default_factory=lambda: bytearray(WAVE_SIZE))  # 186
    legato: bool = False  # 202


@dataclass
class Module:  # the four VoiceData records
    score: Score
    amiga: Amiga
    voices: list[Voice] = field(default_factory=list)


def signed(byte: int) -> int:
    return byte - 256 if byte & 0x80 else byte


def signed_word(word: int) -> int:
    return word - 0x10000 if word & 0x8000 else word


def period_of(index: int) -> int:
    """Past index 143 the code reads the table that follows; the model
    gives 0."""
    return PERIODS[index] if index < len(PERIODS) else 0


def ratio(step: int) -> int:
    """PitchDownRatios for positive steps, PitchUpRatios for negative:
    8192 × 2^(step / 4800). A ratio above 8192 raises the period, so it
    lowers the pitch. The model computes what the tables hold."""
    return round(UNITY * 2 ** (step / (12 * RATIO_STEPS)))


def new_module(score: Score, amiga: Amiga) -> Module:
    """DeliTracker calls Play by its own timer."""
    module = Module(score, amiga)
    module.voices = [Voice(c, n) for n, c in enumerate(amiga.paula.channels)]
    amiga.timer.on_underflow = lambda: Play(module)
    amiga.timer.set_latch(DEFAULT_LATCH)
    return module


def InitSong(module: Module, subsong: int) -> None:
    """Each voice reads its own position list, from the subsong's 4
    offsets. A list whose first byte is $ff leaves the voice silent."""
    score = module.score
    for voice in module.voices:
        at = score.long(12 + SUBSONG_SIZE * subsong + 4 * voice.number)
        voice.positions = at
        voice.left = 0
        voice.stopped = score.data[at] == STOP_VOICE
        voice.legato = False
        ReadPosition(module, voice, at)


# --- Tick ---------------------------------------------------------------


def Play(module: Module) -> None:
    for voice in module.voices:
        if not voice.stopped:
            VoiceTick(module, voice)


def VoiceTick(module: Module, voice: Voice) -> None:
    """At an event's end, the next one. A rest only counts down, with
    DMA off. Else the table switches, the four walkers, the glide, and
    the channel."""
    if not voice.left:
        voice.glide = voice.offset = 0
        voice.rest = False
        ReadEvent(module, voice)
        if voice.stopped:
            return
    if voice.rest:
        voice.channel.disable()
        voice.left -= 1
        return
    SwitchTables(voice)
    data = module.score.data
    VolumeWalker(voice, data)
    period = NoteWalker(voice, data)
    period = FineWalker(voice, data, period)
    period = Glide(voice, period)
    sample = PulseWalker(module, voice)
    voice.period = ShiftPitch(voice, period)
    WriteChannel(module, voice, sample)


def RepeatPattern(module: Module, voice: Voice) -> bool:
    """At a pattern's end: again, while the position's repeats last;
    then the next position. False if the voice stopped."""
    if voice.repeats:
        voice.repeats -= 1
        voice.event = voice.pattern
        return True
    return NextPosition(module, voice)


def NextPosition(module: Module, voice: Voice) -> bool:
    """$fe loops the voice's list; $ff stops the voice. Each voice ends
    on its own; the song ends when all have looped or stopped. Pending
    table switches are dropped."""
    voice.volume_switch = voice.fine_switch = 0
    at = voice.next_position
    marker = module.score.data[at]
    if marker == STOP_VOICE:
        voice.stopped = True  # SongEnd, once all voices are done
        return False
    if marker == LOOP_POSITIONS:
        at = voice.positions  # SongEnd, once all voices are done
    ReadPosition(module, voice, at)
    return True


def ReadPosition(module: Module, voice: Voice, at: int) -> None:
    """A position: the pattern, transpose, repeats, an instrument swap
    (from, to) and a volume offset."""
    data = module.score.data
    voice.pattern = voice.event = module.score.long(at)
    voice.transpose = data[at + 4]
    voice.repeats = data[at + 5]
    voice.swap_from, voice.swap_to = data[at + 6], data[at + 7]
    voice.position_volume = data[at + 9]
    voice.next_position = at + POSITION_SIZE


def ReadEvent(module: Module, voice: Voice) -> None:
    """One event with a length, then any modifiers from $24 up. Every
    event but a modifier restarts the four tables."""
    score = module.score
    while score.data[voice.event] == PATTERN_END:
        if not RepeatPattern(module, voice):
            return
    opcode = score.word(voice.event)
    voice.event += 2
    if opcode in EVENTS:
        NoteEvent(module, voice, opcode)
    while FIRST_MODIFIER <= (opcode := score.word(voice.event)) < 0x8000:
        voice.event += 2
        Modifier(module, voice, opcode)


def NoteEvent(module: Module, voice: Voice, opcode: int) -> None:
    """The arguments follow in a fixed order. Without a length, the last
    length repeats. A glide fits its ratio to the note: see
    GlideToFit."""
    score = module.score
    voice.left = voice.length
    for name in EVENTS[opcode]:
        arg = score.word(voice.event)
        voice.event += 2
        if name == "length":
            voice.left = voice.length = arg
        elif name == "note":
            voice.note = arg
        elif name == "volume":
            voice.event_volume = arg & 0xFF
        elif name == "glide":
            GlideToFit(module, voice, arg)
        else:
            LoadInstrument(module, voice, arg)
    if opcode == REST:
        RestEvent(voice)
    restart_tables(voice)


def restart_tables(voice: Voice) -> None:
    inst = voice.instrument
    voice.volume.restart(inst.volume_table)
    voice.fine.restart(inst.fine_table)
    voice.note_offset.restart(inst.note_table)
    voice.pulse.restart(inst.pulse_table)


def LoadInstrument(module: Module, voice: Voice, number: int) -> None:
    """The position can swap one instrument for another."""
    if number & 0xFF == voice.swap_from:
        number = (number & 0xFF00) | voice.swap_to
    voice.instrument = module.score.instrument(number)


def RestEvent(voice: Voice) -> None:
    voice.rest = True


def GlideToFit(module: Module, voice: Voice, direction: int) -> None:
    """Words: the marker, the interval in ratio steps, the delay. The
    ratio per tick is interval / (length - delay) steps, so the glide
    spans the interval as the note ends. $fd00 raises the period."""
    score = module.score
    interval = score.word(voice.event)
    delay = score.word(voice.event + 2)
    voice.event += 4
    per_tick = interval // ((voice.length - delay) & 0xFFFF or 1)
    rising = direction == RISING_PERIOD
    voice.glide_rate = ratio(per_tick if rising else -per_tick)
    voice.glide_delay, voice.glide = delay, UNITY


def Modifier(module: Module, voice: Voice, opcode: int) -> None:
    """$24 and $2e switch a table after a delay; $26 and $28 turn legato
    off and on; $2a and $2c start a glide, after a delay, at a fixed
    ratio per tick (byte offsets into the ratio tables)."""
    score = module.score
    if opcode == LEGATO_ON:
        LegatoOn(voice)
        return
    if opcode == LEGATO_OFF:
        voice.legato = False
        return
    delay, arg = score.word(voice.event), score.word(voice.event + 2)
    voice.event += 4
    if opcode == SWITCH_VOLUME:
        SwitchVolTable(voice, delay, score.long(score.volume_list + arg))
    elif opcode == SWITCH_FINE:
        SwitchFineTable(voice, delay, score.long(score.fine_list + arg))
    elif opcode in (GLIDE_UP, GLIDE_DOWN):
        step = arg // 2
        voice.glide_rate = ratio(-step if opcode == GLIDE_UP else step)
        voice.glide_delay, voice.glide = delay, UNITY


def LegatoOn(voice: Voice) -> None:
    """The channel keeps running from one note to the next."""
    voice.legato = True


def SwitchVolTable(voice: Voice, delay: int, table: int) -> None:
    voice.volume_delay, voice.volume_switch = delay, table


def SwitchFineTable(voice: Voice, delay: int, table: int) -> None:
    voice.fine_delay, voice.fine_switch = delay, table


def SwitchTables(voice: Voice) -> None:
    """After the delay, the walker jumps to the new table, but its base
    stays: at the new table's $ff it returns to the instrument's own
    table. The code clears only the high word of the pending offset,
    so a low word that is not 0 waits another 65536 ticks."""
    for runs, attr, delay_attr in (
        (voice.volume, "volume_switch", "volume_delay"),
        (voice.fine, "fine_switch", "fine_delay"),
    ):
        pending = getattr(voice, attr)
        if not pending:
            continue
        delay = getattr(voice, delay_attr)
        if not delay:
            runs.pos, runs.count, runs.repeats = pending, 0, 0
            setattr(voice, attr, pending & 0xFFFF)
        setattr(voice, delay_attr, (delay - 1) & 0xFFFF)


# --- Walkers ------------------------------------------------------------


def VolumeWalker(voice: Voice, data: bytes) -> None:
    """The table's value, or 64 without one, minus the event's and the
    position's volume offsets; below 0 gives 0."""
    level = voice.volume.step(data) if voice.volume.base else FULL_VOLUME
    level = signed((level - voice.event_volume - voice.position_volume) & 0xFF)
    voice.level = max(level, 0)


def NoteWalker(voice: Voice, data: bytes) -> int:
    """The note, plus the position's transpose unless the instrument is
    fixed, plus the table's note offset: bytes that wrap."""
    if voice.note_offset.base:
        voice.offset = voice.note_offset.step(data)
    note = voice.note
    if not voice.instrument.fixed:
        note = (note & 0xFF00) | ((note + voice.transpose) & 0xFF)
    note = (note & 0xFF00) | ((note + voice.offset) & 0xFF)
    return period_of(note)


def FineWalker(voice: Voice, data: bytes, period: int) -> int:
    """A signed word of ratio steps scales the period."""
    if not voice.fine.base:
        return period
    step = signed_word(voice.fine.step(data))
    return (period * ratio(step)) >> 13


def Glide(voice: Voice, period: int) -> int:
    """After the delay, the ratio so far is multiplied by the rate each
    tick, and scales the period. It has no target: it runs to the
    event's end."""
    if not voice.glide:
        return period
    if voice.glide_delay:
        voice.glide_delay -= 1
        return period
    voice.glide = (voice.glide * voice.glide_rate) >> 13
    return (period * voice.glide) >> 13


def PulseWalker(module: Module, voice: Voice) -> paula.Sample:
    """A value's high byte W picks pulse wave W: W low bytes, then high
    ones. Its low byte A is taken from byte W, the first high byte: a
    soft edge between widths. The 16-byte wave is rebuilt every tick,
    in place. Without a pulse table, the instrument's sample. The code
    does not mask W; the model keeps it within the wave."""
    inst = voice.instrument
    if not voice.pulse.base:
        start = inst.start
        return paula.Sample(module.score.samples[start : start + 2 * inst.length])
    value = voice.pulse.step(module.score.data)
    width, amount = value >> 8, value & 0xFF
    voice.wave[:] = pulse_wave(width)
    voice.wave[width & 0x0F] = (voice.wave[width & 0x0F] - amount) & 0xFF
    return paula.Sample(voice.wave)


def pulse_wave(width: int) -> bytes:
    """PulseWaves: wave W has W bytes of $81, then $7f."""
    low = width & 0x0F
    return bytes([0x81] * low + [0x7F] * (WAVE_SIZE - low))


def ShiftPitch(voice: Voice, period: int) -> int:
    """The instrument's shift, a byte offset into the ratio tables,
    scales the period last."""
    shift = voice.instrument.shift
    if not shift:
        return period
    return (period * ratio(shift // 2)) >> 13


def WriteChannel(module: Module, voice: Voice, sample: paula.Sample) -> None:
    """First tick of an event: the sample, DMA on. Second: the loop. On
    the final tick: DMA off, unless legato; so the next note restarts a
    tick later, with no busy-wait. The ticks between set DMA on again."""
    channel = voice.channel
    channel.period, first = voice.period, voice.left == voice.length
    channel.set_volume(voice.level)
    inst = voice.instrument
    if first:
        channel.queue(sample)
        channel.enable()
    elif voice.left == voice.length - 1:
        if inst.pulse_table:
            channel.queue(sample)
        else:
            end = inst.loop + 2 * inst.loop_length
            channel.queue(paula.Sample(module.score.samples[inst.loop : end]))
        channel.enable()
    elif voice.left == 1 and not voice.legato:
        channel.disable()
    else:
        channel.enable()
    voice.left -= 1
