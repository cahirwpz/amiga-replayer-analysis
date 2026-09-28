"""Face The Music's replay, by J. Schmidt (MAXON, 1991), in the
EaglePlayer Face The Music V1.7 (Aug/29/93), adapted by Buggs of DEFECT.

Card: players/FaceTheMusic.md. Level 2: the control flow runs. Each
CamelCase function is a LABEL in data/disasm/FaceTheMusic.cnf; each
CamelCase class is in the `types:` of data/annot/FaceTheMusic.yaml.
Comments name the track fields by their offsets in a track record, $BA
bytes each.

Eight tracks share four channels, two per channel. Each audio interrupt
mixes its pair into a buffer of 100 words. Paula plays the pair's higher
track at that track's own period, and at the louder track's volume. The
CPU copies the higher track's bytes, and adds the lower track's bytes,
resampled and scaled by the ratio of the two volumes.

Each track reads one list of 16-bit events, with waits between them.
An event can start a script: a program of 4-byte lines on the track.
A script can wait, branch on pitch or volume, react to events, run four
LFOs, and act on any other track.

Left out: DeliTracker's hooks and song-end checks, the song loop events
($E000), Chase (after a seek, the last sample and volume replay), the
LED filter, and the tables' exact values: the model computes them.
PairPeriods and StepTable come within 1 of the binary's tables,
LfoWaves within 5.
"""

from collections.abc import Callable
from dataclasses import dataclass, field, fields
from enum import Enum, auto
from math import pi, sin

from hardware import paula
from hardware.amiga import Amiga

TRACKS, PAIRS = 8, 4
MIX_WORDS = 100  # AUDxLEN of every channel
MIX_BYTES = 2 * MIX_WORDS
SLOTS = 63  # sample slots
PITCH_MAX = 0x21E  # 1/16 semitone per unit; 8 table entries per semitone
STEPS_PER_OCTAVE = 96
TOP_PERIOD = 855  # PairPeriods: pitch 0
VOLUME_MAX = 64
GLOBAL_MAX = 63
SPEED_MAX, DEPTH_MAX = 0xBF, 0x7F  # an LFO's limits
LFO_WAVE_BYTES = 192
TEMPO_MIN = 0x1000  # SetTempo: CIA counts
WAIT_FOREVER = 0xFFFF  # ScriptWait 0: until an event
RELEASE = 0x23  # a note event's pitch field: the note is released
LINE_LIMIT = 100_000  # model only: a script loop without a wait hangs the 68000

# EventVolumes: an event's volume nibble 1-10. Nibble 3 gives 0; the
# pattern gives 14 (guess: a typo). Nibbles 11-15 read the next table.
EVENT_VOLUMES = (0, 7, 0, 21, 28, 36, 43, 50, 56, 64)


class Flow(Enum):
    NEXT = auto()  # ScriptNext: the next line
    JUMP = auto()  # the op set `line`
    EXIT = auto()  # stop until the next tick


# --- Player state ------------------------------------------------------


@dataclass
class Sample:  # Instruments: 16 bytes each; addresses into `memory`
    start: int = 0
    one_shot: int = 0  # words played once
    loop_start: int = 0
    loop: int = 0  # words; 0: silence after the one-shot part
    end: int = 0


@dataclass
class Lfo:  # four per track, from $6A, 20 bytes each
    target: str = ""  # LfoTargets: a field of the work track; "": none
    once: bool = False  # bit 3: stop at the wave's end
    limit: int = 0
    wave: int = 0  # LfoWaves: 0 sine, 1 square, 2 triangle, 3-4 ramps
    pos: int = 0
    speed: int = 0  # bytes per tick; 0: off
    depth: int = 0
    last: int = 0


@dataclass
class Track:  # Track0: $BA bytes each
    pair: int  # $24: the pair whose PairTune word the track's detune ops write
    play: int = 0  # 0: the next byte to mix
    instrument: int = -1  # 4: an Instruments slot; -1 SilentSample
    start: int = 0  # 8
    one_shot: int = 0  # $0C
    loop_start: int = 0  # $0E
    loop: int = 0  # $12
    end: int = 0  # $14
    volume: int = 0  # $1C: 0-64
    pitch: int = 0  # $1E: 0-$21E
    step: int = 0  # $20: the lower track's skip step
    fraction: int = 0  # $22
    held: int = 0  # $28: the last byte mixed
    events: int = 0  # $2A: the event list, bytes into `memory`
    events_end: int = 0  # $2E
    row_pos: int = 0  # $32
    spacing: int = 0  # $36: rows after an event without a wait word
    wait: int = 0  # $38: rows left
    porta_step: int = 0  # $3A: signed, 8.8
    porta_acc: int = 0  # $3C
    porta_target: int = 0  # $40
    slide_acc: int = 0  # $42: volume, 8.8
    slide_step: int = 0  # $46
    script: int = 0  # $48: first line, bytes into `memory`
    line: int | None = None  # $4C: None: no script runs
    script_end: int = 0  # $50
    script_wait: int = 0  # $54
    loop_count: int = 0  # $56
    work: int = 0  # $58: the track that the ops act on
    handlers: list[int] = field(default_factory=lambda: [0] * 6)  # $5C: line + 1
    pending: int = 0  # $68: a handler's line + 1
    lfos: list[Lfo] = field(default_factory=lambda: [Lfo() for _ in range(4)])


# Handlers, in the order of `Track.handlers`
NEW_PITCH, NEW_VOLUME, NEW_SAMPLE, ON_RELEASE, ON_PORTAMENTO, VOLUME_DOWN = range(6)

# LfoTargets: the first byte's high nibble picks a field and its limit
LFO_TARGETS: dict[int, tuple[str, int]] = {
    1: ("lfo0.speed", 0x5F), 2: ("lfo1.speed", 0x5F), 3: ("lfo2.speed", 0x5F),
    4: ("lfo3.speed", 0x5F), 5: ("lfo0.depth", 0x7F), 6: ("lfo1.depth", 0x7F),
    7: ("lfo2.depth", 0x7F), 8: ("lfo3.depth", 0x7F), 10: ("volume", 0x40),
    15: ("pitch", PITCH_MAX),
}  # fmt: skip


@dataclass
class Module:
    amiga: Amiga
    memory: bytearray  # the file, then SilentSample's 100 words
    samples: list[Sample] = field(default_factory=list)  # Instruments
    scripts: list[tuple[int, int]] = field(default_factory=list)  # Scripts: start, end
    tracks: list[Track] = field(default_factory=list)
    track_mask: int = 0  # TrackMask: tracks that read events
    global_volume: int = GLOBAL_MAX  # GlobalVolume
    tempo: int = 0  # Tempo: CIA counts per tick
    ticks_per_row: int = 6  # TicksPerRow
    row_ticks: int = 1
    song_line: int = 0  # SongLine
    end_line: int = 0
    restart_line: int = 0
    jump: int | None = None  # JumpToLine: the next row seeks
    ended: bool = False
    silent: Sample = field(default_factory=Sample)  # SilentSample
    pair_tune: list[int] = field(default_factory=lambda: [0] * PAIRS)  # PairTune
    next_periods: list[int] = field(default_factory=lambda: [428] * PAIRS)
    next_volumes: list[int] = field(default_factory=lambda: [0] * PAIRS)
    buffers: list[bytearray] = field(
        default_factory=lambda: [bytearray(2 * MIX_BYTES) for _ in range(PAIRS)]
    )  # MixBuffer0-3: two halves each
    halves: list[int] = field(default_factory=lambda: [0] * PAIRS)  # Halves


# --- Tables ------------------------------------------------------------


def pair_period(pitch: int) -> int:
    """PairPeriods: 855 at pitch 0, down 2^(1/96) per 2 units."""
    return round(TOP_PERIOD * 2 ** (-(pitch // 2) / STEPS_PER_OCTAVE))


def skip_step(difference: int) -> int:
    """StepTable: the share of output bytes on which the lower track
    reads no new byte, × 65536."""
    return round(65536 * (1 - 2 ** (-(difference // 2) / STEPS_PER_OCTAVE))) & 0xFFFF


def scale(byte: int, row: int) -> int:
    """VolumeTables: 64 rows of 256 bytes, (signed byte × row) >> 6. They
    start at a 256-byte boundary, so the mixer finds a value by putting
    the byte into the low byte of the row's address."""
    return (signed(byte) * row >> 6) & 0xFF


def lfo_wave(wave: int, pos: int) -> int:
    """LfoWaves: five waves of 192 signed bytes."""
    phase = pos / LFO_WAVE_BYTES
    ramp = round(255 * phase) - 128
    shape = {
        0: round(127 * sin(2 * pi * phase)),
        1: 127 if phase < 0.5 else -128,
        2: round(127 * (1 - 4 * abs(phase - 0.25) if phase < 0.75 else 4 * phase - 4)),
        3: -ramp - 1,
        4: ramp,
    }
    return shape.get(wave, 0)


# --- Start -------------------------------------------------------------


def new_module(amiga: Amiga, data: bytes) -> Module:
    module = Module(amiga, bytearray(data) + bytes(MIX_BYTES))
    silent_at = len(data)
    module.silent = Sample(silent_at, 0, silent_at, MIX_WORDS, silent_at + MIX_BYTES)
    LoadModule(module)
    for n, channel in enumerate(amiga.paula.channels):
        channel.on_irq(audio_irq(module, n))
    StartSong(module)
    amiga.timer.on_underflow = lambda: Tick(module)
    amiga.timer.set_latch(module.tempo)
    amiga.timer.start()
    return module


def audio_irq(module: Module, pair: int) -> Callable[[paula.Channel], None]:
    """AudioIrq0-3: channel n's interrupt mixes pair n."""
    return lambda _: MixPairs(module, pair)


def LoadModule(module: Module) -> None:
    """`FTM`, a header length, the header, 32-byte sample names, the
    scripts, eight tracks, then the samples of the named slots."""
    data = module.memory
    if data[:3] != b"FTM":
        raise ValueError("no FTM header")
    header = data[4 : 4 + data[3]]
    if header[0] < 3 or not header[9] & 1:
        raise ValueError("unsupported FTM version")
    names, at = header[1], 4 + data[3]
    named = [data[at + 32 * n] != 0 for n in range(names)] + [False] * (SLOTS - names)
    at += 32 * names
    module.tempo = word(header, 4)
    module.track_mask, module.global_volume = header[7], header[8]
    module.ticks_per_row = header[10]
    measure = header[11]
    module.end_line = word(header, 2) * measure
    module.scripts = [(0, 0)] * 64
    for _ in range(header[0x4C]):
        lines, index = word(data, at), word(data, at + 2)
        module.scripts[index] = (at + 4, at + 4 + 4 * lines)
        at += 4 + 4 * lines
    module.tracks = []
    for n in range(TRACKS):
        spacing, length = word(data, at), word(data, at + 2) << 16 | word(data, at + 4)
        track = Track(
            n // 2, spacing=spacing, events=at + 6, events_end=at + 6 + length
        )
        module.tracks.append(track)
        at += 6 + length
    module.samples = []
    for slot in range(SLOTS):
        if not named[slot]:
            module.samples.append(module.silent)
            continue
        one_shot, loop = word(data, at), word(data, at + 2)
        start = at + 4
        loop_start, end = start + 2 * one_shot, start + 2 * (one_shot + loop)
        module.samples.append(Sample(start, one_shot, loop_start, loop, end))
        at = end


def StartSong(module: Module) -> None:
    """Silence on every track; every channel loops SilentSample at period
    428 until its first interrupt, which sets period 214. Then all
    tracks seek to the start line, and the first row plays."""
    for track in module.tracks:
        StartSample(track, module.silent)
        track.volume, track.pitch = VOLUME_MAX, 0
    for channel in module.amiga.paula.channels:
        channel.period = 428
        channel.set_volume(VOLUME_MAX)
        channel.play(paula.Sample(module.memory, module.silent.start, MIX_WORDS))
    module.next_periods = [214] * PAIRS
    module.song_line = module.restart_line
    Seek(module)
    module.row_ticks = module.ticks_per_row
    PlayRows(module)


# --- Tick --------------------------------------------------------------


def Tick(module: Module) -> None:
    """The CIA timer's tick. Rows every `ticks_per_row` ticks; the
    tracks' slides, scripts and LFOs every tick."""
    module.row_ticks -= 1
    if not module.row_ticks:
        module.row_ticks = module.ticks_per_row
        PlayRows(module)
    RunScripts(module)


def PlayRows(module: Module) -> None:
    """Each track of the mask reads its row. A jump seeks first."""
    if module.jump is not None:
        module.song_line, module.jump = module.jump, None
        Seek(module)
        return
    for n, track in enumerate(module.tracks):
        if module.track_mask & 1 << n:
            TrackRow(module, track)
    module.song_line += 1
    if module.song_line == module.end_line:
        module.ended = True
        module.song_line = module.restart_line
        Seek(module)


def Seek(module: Module) -> None:
    for track in module.tracks:
        SeekTrack(module, track)


def SeekTrack(module: Module, track: Track) -> None:
    """Walk the events up to the song line: an event takes one row plus
    the track's spacing, a wait word $F000 + n takes n rows."""
    data, row, at = module.memory, 0, track.events
    while at < track.events_end and row < module.song_line:
        value = word(data, at)
        at += 2
        if value >= 0xF000:
            row += value & 0x0FFF
            continue
        row += 1
        if at < track.events_end and word(data, at) < 0xF000:
            row += track.spacing
    track.row_pos, track.wait = at, row - module.song_line


def TrackRow(module: Module, track: Track) -> None:
    """At the end of a wait: a wait word waits; an event plays, then the
    next word waits, or the track's spacing does."""
    track.wait -= 1
    if track.wait >= 0 or track.row_pos >= track.events_end:
        return
    data = module.memory
    value = word(data, track.row_pos)
    if value > 0xF000:
        track.wait = (value & 0x0FFF) - 1
        track.row_pos += 2
        return
    if value == 0xF000:
        track.row_pos += 2
    PatternEvent(module, track, word(data, track.row_pos))
    track.row_pos += 2
    following = word(data, track.row_pos) if track.row_pos < track.events_end else 0
    if following >= 0xF000:
        track.wait = following & 0x0FFF
        track.row_pos += 2
    else:
        track.wait = track.spacing


def PatternEvent(module: Module, track: Track, value: int) -> None:
    """$B000 starts a script, $C000 a portamento, $D000 a fade to 0.
    Below $B000: a sample in bits 6-11 and a volume in bits 12-15. Every
    kind but $C000 then takes bits 0-5 as a pitch. Each part that is
    set can raise its handler; a later one replaces an earlier one."""
    kind, middle, low = value & 0xF000, (value & 0x0FC0) >> 6, value & 0x3F
    if not value:
        return
    new_sample = False
    if kind == 0xC000:
        Portamento(module, track, middle, low)
        return
    if kind == 0xD000:
        Fade(module, track, middle)
    elif kind == 0xB000:
        start, end = module.scripts[middle]
        track.script, track.line, track.script_end = start, start, end
        track.script_wait = track.loop_count = track.pending = 0
        track.handlers = [0] * 6
        track.work = module.tracks.index(track)
    elif kind != 0xE000:
        if middle:
            new_sample = True
            track.instrument = middle - 1
            raise_handler(track, NEW_SAMPLE)
        if kind:
            track.volume, track.slide_step = event_volume(kind >> 12), 0
            raise_handler(track, NEW_VOLUME)
    if low == RELEASE:
        raise_handler(track, ON_RELEASE)
        return
    if not low or low > RELEASE:
        return
    track.pitch, track.porta_step = (low - 1) << 4, 0
    raise_handler(track, NEW_PITCH)
    sample = sample_of(module, track)
    silent = track.start == module.silent.start
    if new_sample or silent or not sample.loop:
        StartSample(track, sample)


def Portamento(module: Module, track: Track, rows: int, note: int) -> None:
    """$C000: slide to pitch field `note` over `rows` rows; 0 rows jump."""
    if not note:
        return
    track.porta_target = (note - 1) << 4
    track.porta_acc = track.pitch << 8
    distance = (track.porta_target << 8) - track.porta_acc
    if not distance:
        track.porta_step = 0
        return
    if not rows:
        track.pitch, track.porta_step = track.porta_target, 0
        return
    track.porta_step = int(distance / (rows * module.ticks_per_row))
    raise_handler(track, ON_PORTAMENTO)


def Fade(module: Module, track: Track, rows: int) -> None:
    """$D000: the volume slides to 0 over `rows` rows; 0 rows: at once."""
    if not rows:
        track.volume = 0
        return
    track.slide_acc = track.volume << 8
    track.slide_step = track.slide_acc // (rows * module.ticks_per_row)
    raise_handler(track, VOLUME_DOWN)


def StartSample(track: Track, sample: Sample) -> None:
    """A note with a sample, a silent track or a one-shot sample
    restarts; a looping sample plays on under a new pitch: legato."""
    track.play, track.start, track.one_shot = (
        sample.start,
        sample.start,
        sample.one_shot,
    )
    track.loop_start, track.loop, track.end = sample.loop_start, sample.loop, sample.end
    track.fraction = 0


def RunScripts(module: Module) -> None:
    for track in module.tracks:
        TrackTick(module, track)


def TrackTick(module: Module, track: Track) -> None:
    """The fade, the portamento, then the script: a raised handler, a
    wait, or lines until one stops. Then the LFOs."""
    if track.slide_step:
        track.slide_acc -= track.slide_step
        if track.slide_acc < 0:
            track.slide_acc = track.slide_step = 0
        track.volume = track.slide_acc >> 8
    if track.porta_step:
        track.porta_acc += track.porta_step
        track.pitch = (track.porta_acc >> 8) & ~1
        up = track.porta_step > 0
        if (
            up
            and track.pitch >= track.porta_target
            or not up
            and track.pitch <= track.porta_target
        ):
            track.pitch, track.porta_step = track.porta_target, 0
    if track.line is not None:
        if track.pending:
            ScriptEvent(module, track)
        elif not track.script_wait:
            ScriptRun(module, track)
        elif track.script_wait != WAIT_FOREVER:
            track.script_wait -= 1
    Lfos(module, track)


def ScriptEvent(module: Module, track: Track) -> None:
    """A raised handler resets the wait and the loop count, then runs
    from its line."""
    line, track.pending = track.pending - 1, 0
    track.script_wait = track.loop_count = 0
    goto(track, line)
    if track.line is not None:
        ScriptRun(module, track)


def ScriptRun(module: Module, track: Track) -> None:
    """Lines until an op exits. A loop without a wait never exits: the
    68000 hangs in it."""
    for _ in range(LINE_LIMIT):
        if track.line is None:
            return
        line = long(module.memory, track.line)
        flow = SCRIPT_OPS[line >> 24](module, track, line)
        if flow is Flow.EXIT:
            return
        if flow is Flow.NEXT:
            ScriptNext(track)
    raise RuntimeError("ScriptRun: a script loops without a wait")


def ScriptNext(track: Track) -> None:
    assert track.line is not None
    track.line += 4
    if track.line >= track.script_end:
        track.line = None


# --- Script ops: flow --------------------------------------------------
# A line: op byte, then A in bits 12-23 and B in bits 0-11.


Op = Callable[[Module, Track, int], Flow]


def no_op(module: Module, track: Track, line: int) -> Flow:
    """Op 0: the next line."""
    return Flow.NEXT


def ScriptWait(module: Module, track: Track, line: int) -> Flow:
    """B ticks, the current one included; 0: until a handler runs."""
    track.script_wait = (arg_b(line) - 1) & 0xFFFF
    if track.script_wait != WAIT_FOREVER:
        ScriptNext(track)
    return Flow.EXIT


def ScriptGoto(module: Module, track: Track, line: int) -> Flow:
    goto(track, arg_b(line))
    return Flow.JUMP


def ScriptLoop(module: Module, track: Track, line: int) -> Flow:
    """A times to line B, then on. One counter per track: loops do not
    nest."""
    if not track.loop_count:
        track.loop_count = arg_a(line)
        if not track.loop_count:
            return Flow.NEXT
        return ScriptGoto(module, track, line)
    track.loop_count -= 1
    if not track.loop_count:
        return Flow.NEXT
    return ScriptGoto(module, track, line)


def ScriptChain(module: Module, track: Track, line: int) -> Flow:
    """Script A, from line B."""
    start, end = module.scripts[arg_a(line) & 0x3F]
    if not start:
        return ScriptEnd(module, track, line)
    track.script, track.script_end = start, end
    goto(track, arg_b(line))
    return Flow.JUMP


def ScriptEnd(module: Module, track: Track, line: int) -> Flow:
    track.line = None
    return Flow.EXIT


def IfPitchEqual(module: Module, track: Track, line: int) -> Flow:
    return branch(module, track, line, work(module, track).pitch == arg_a(line))


def IfPitchAtMost(module: Module, track: Track, line: int) -> Flow:
    return branch(module, track, line, work(module, track).pitch <= arg_a(line))


def IfPitchAtLeast(module: Module, track: Track, line: int) -> Flow:
    return branch(module, track, line, work(module, track).pitch >= arg_a(line))


def IfVolumeEqual(module: Module, track: Track, line: int) -> Flow:
    return branch(module, track, line, work(module, track).volume == arg_a(line))


def IfVolumeAtMost(module: Module, track: Track, line: int) -> Flow:
    return branch(module, track, line, work(module, track).volume <= arg_a(line))


def IfVolumeAtLeast(module: Module, track: Track, line: int) -> Flow:
    return branch(module, track, line, work(module, track).volume >= arg_a(line))


def handler_op(kind: int) -> Op:
    """OnNewPitch to OnVolumeDown: the script's own track runs line B
    when that event comes."""

    def op(module: Module, track: Track, line: int) -> Flow:
        track.handlers[kind] = arg_b(line) + 1
        return Flow.NEXT

    return op


OnNewPitch, OnNewVolume, OnNewSample = map(handler_op, range(3))
OnRelease, OnPortamento, OnVolumeDown = map(handler_op, range(3, 6))


# --- Script ops: the work track's sound --------------------------------


def RestartSample(module: Module, track: Track, line: int) -> Flow:
    target = work(module, track)
    StartSample(target, sample_of(module, target))
    return Flow.NEXT


def SilenceSample(module: Module, track: Track, line: int) -> Flow:
    StartSample(work(module, track), module.silent)
    return Flow.NEXT


def SetPlayPosition(module: Module, track: Track, line: int) -> Flow:
    """In words from the start; the add and subtract ops count bytes."""
    target = work(module, track)
    target.play, target.fraction = target.start + 2 * (line & 0x1FFFF), 0
    return Flow.NEXT


def AddPlayPosition(module: Module, track: Track, line: int) -> Flow:
    target = work(module, track)
    target.play, target.fraction = target.play + (line & 0x1FFFF), 0
    return Flow.NEXT


def SubPlayPosition(module: Module, track: Track, line: int) -> Flow:
    target = work(module, track)
    target.play, target.fraction = target.play - (line & 0x1FFFF), 0
    return Flow.NEXT


def SetPitch(module: Module, track: Track, line: int) -> Flow:
    work(module, track).pitch = min(2 * arg_b(line), PITCH_MAX)
    return Flow.NEXT


def SetDetune(module: Module, track: Track, line: int) -> Flow:
    """The pair's detune: added to the lower track's skip step."""
    module.pair_tune[work(module, track).pair] = arg_b(line)
    return Flow.NEXT


def AddDetunePitch(module: Module, track: Track, line: int) -> Flow:
    target = work(module, track)
    module.pair_tune[target.pair] = (
        module.pair_tune[target.pair] + arg_a(line)
    ) & 0xFFFF
    target.pitch = min(target.pitch + 2 * arg_b(line), PITCH_MAX)
    return Flow.NEXT


def SubDetunePitch(module: Module, track: Track, line: int) -> Flow:
    target = work(module, track)
    module.pair_tune[target.pair] = (
        module.pair_tune[target.pair] - arg_a(line)
    ) & 0xFFFF
    target.pitch = max(target.pitch - 2 * arg_b(line), 0)
    return Flow.NEXT


def SetVolumeOp(module: Module, track: Track, line: int) -> Flow:
    work(module, track).volume = min(line & 0xFF, VOLUME_MAX)
    return Flow.NEXT


def AddVolume(module: Module, track: Track, line: int) -> Flow:
    """A byte add: past 255 it wraps before the limit."""
    target = work(module, track)
    target.volume = min((target.volume + (line & 0xFF)) & 0xFF, VOLUME_MAX)
    return Flow.NEXT


def SubVolume(module: Module, track: Track, line: int) -> Flow:
    target = work(module, track)
    value = (target.volume - (line & 0xFF)) & 0xFF
    target.volume = 0 if value & 0x80 else value
    return Flow.NEXT


def SetSample(module: Module, track: Track, line: int) -> Flow:
    """Slot n; the next restart plays it."""
    work(module, track).instrument = line & 0xFF
    return Flow.NEXT


def SetSampleStart(module: Module, track: Track, line: int) -> Flow:
    target = work(module, track)
    target.start = min(sample_of(module, target).start + (line & 0x1FFFF), target.end)
    return Flow.NEXT


def AddSampleStart(module: Module, track: Track, line: int) -> Flow:
    """Bug: it computes the new start in d0 but stores d1, a leftover
    register. The model leaves the start as it is."""
    return Flow.NEXT


def SubSampleStart(module: Module, track: Track, line: int) -> Flow:
    """Bug: it masks the line with d1 before d1 is loaded. The model
    leaves the start as it is."""
    return Flow.NEXT


def set_one_shot(target: Track, words: int) -> None:
    target.one_shot = words
    target.loop_start = target.start + 2 * words
    target.end = target.loop_start + 2 * target.loop


def set_loop(target: Track, words: int) -> None:
    target.loop = words
    target.end = target.start + 2 * (target.one_shot + words)


def SetOneShot(module: Module, track: Track, line: int) -> Flow:
    set_one_shot(work(module, track), line & 0xFFFF)
    return Flow.NEXT


def AddOneShot(module: Module, track: Track, line: int) -> Flow:
    target = work(module, track)
    set_one_shot(target, min(target.one_shot + (line & 0xFFFF), 0xFFFF))
    return Flow.NEXT


def SubOneShot(module: Module, track: Track, line: int) -> Flow:
    target = work(module, track)
    set_one_shot(target, max(target.one_shot - (line & 0xFFFF), 0))
    return Flow.NEXT


def SetLoopLength(module: Module, track: Track, line: int) -> Flow:
    set_loop(work(module, track), line & 0xFFFF)
    return Flow.NEXT


def AddLoopLength(module: Module, track: Track, line: int) -> Flow:
    target = work(module, track)
    set_loop(target, min(target.loop + (line & 0xFFFF), 0xFFFF))
    return Flow.NEXT


def SubLoopLength(module: Module, track: Track, line: int) -> Flow:
    target = work(module, track)
    set_loop(target, max(target.loop - (line & 0xFFFF), 0))
    return Flow.NEXT


# --- Script ops: other tracks, LFOs, the song --------------------------


def CopyPitch(module: Module, track: Track, line: int) -> Flow:
    work(module, track).pitch = module.tracks[line & 7].pitch
    return Flow.NEXT


def CopyVolume(module: Module, track: Track, line: int) -> Flow:
    work(module, track).volume = module.tracks[line & 7].volume
    return Flow.NEXT


def CopySample(module: Module, track: Track, line: int) -> Flow:
    work(module, track).instrument = module.tracks[line & 7].instrument
    return Flow.NEXT


def CloneTrack(module: Module, track: Track, line: int) -> Flow:
    """All $BA bytes of track n: sound, events, script state, LFOs, and
    the detune pointer. So the clone's detune ops change n's pair."""
    source, target = module.tracks[line & 7], work(module, track)
    for f in fields(Track):
        value = getattr(source, f.name)
        if isinstance(value, list):
            value = [Lfo(**vars(v)) if isinstance(v, Lfo) else v for v in value]
        setattr(target, f.name, value)
    return Flow.NEXT


def lfo_ops(n: int) -> tuple[Op, Op, Op]:
    """StartLfo: byte 1 holds the target (high nibble), `once` (bit 3)
    and the wave (bits 0-2); byte 2 the speed; byte 3 the depth.
    RaiseLfo and LowerLfo add or subtract bytes 2 and 3."""

    def start(module: Module, track: Track, line: int) -> Flow:
        lfo = track.lfos[n]
        first = line >> 16 & 0xFF
        lfo.target, lfo.limit = LFO_TARGETS.get(first >> 4, ("", 0))
        lfo.once, lfo.wave, lfo.pos, lfo.last = bool(first & 8), first & 7, 0, 0
        lfo.speed = min(line >> 8 & 0xFF, SPEED_MAX)
        lfo.depth = line & 0x7F
        return Flow.NEXT

    def raise_(module: Module, track: Track, line: int) -> Flow:
        lfo = track.lfos[n]
        lfo.speed = min((lfo.speed + (line >> 8 & 0xFF)) & 0xFF, SPEED_MAX)
        lfo.depth = min((lfo.depth + (line & 0xFF)) & 0xFF, DEPTH_MAX)
        return Flow.NEXT

    def lower(module: Module, track: Track, line: int) -> Flow:
        lfo = track.lfos[n]
        lfo.speed = max(lfo.speed - (line >> 8 & 0xFF), 0)
        lfo.depth = max(lfo.depth - (line & 0xFF), 0)
        return Flow.NEXT

    return start, raise_, lower


StartLfo1, RaiseLfo1, LowerLfo1 = lfo_ops(0)
StartLfo2, RaiseLfo2, LowerLfo2 = lfo_ops(1)
StartLfo3, RaiseLfo3, LowerLfo3 = lfo_ops(2)
StartLfo4, RaiseLfo4, LowerLfo4 = lfo_ops(3)


def SelectTrack(module: Module, track: Track, line: int) -> Flow:
    """The ops from now on act on track n."""
    track.work = line & 7
    return Flow.NEXT


def ShiftTrack(module: Module, track: Track, line: int) -> Flow:
    track.work = (track.work + (line & 7)) % TRACKS
    return Flow.NEXT


def SetGlobalVolume(module: Module, track: Track, line: int) -> Flow:
    module.global_volume = min(line & 0xFF, GLOBAL_MAX)
    return Flow.NEXT


def SetTempo(module: Module, track: Track, line: int) -> Flow:
    """CIA counts per tick, at least $1000: at most 173 ticks a second."""
    module.tempo = max(line & 0xFFFF, TEMPO_MIN)
    module.amiga.timer.set_latch(module.tempo)
    return Flow.NEXT


def SetTicksPerRow(module: Module, track: Track, line: int) -> Flow:
    module.ticks_per_row = line & 0xFF
    return Flow.NEXT


def JumpToLine(module: Module, track: Track, line: int) -> Flow:
    """At the next row, every track seeks to song line B."""
    module.jump = line & 0xFFFF
    return Flow.NEXT


SCRIPT_OPS: tuple[Op, ...] = (
    no_op, ScriptWait, ScriptGoto, ScriptLoop, ScriptChain, ScriptEnd,
    IfPitchEqual, IfPitchAtMost, IfPitchAtLeast, IfVolumeEqual, IfVolumeAtMost,
    IfVolumeAtLeast, OnNewPitch, OnNewVolume, OnNewSample, OnRelease, OnPortamento,
    OnVolumeDown, RestartSample, SilenceSample, SetPlayPosition, AddPlayPosition,
    SubPlayPosition, SetPitch, SetDetune, AddDetunePitch, SubDetunePitch, SetVolumeOp,
    AddVolume, SubVolume, SetSample, SetSampleStart, AddSampleStart, SubSampleStart,
    SetOneShot, AddOneShot, SubOneShot, SetLoopLength, AddLoopLength, SubLoopLength,
    CopyPitch, CopyVolume, CopySample, CloneTrack, StartLfo1, RaiseLfo1, LowerLfo1,
    StartLfo2, RaiseLfo2, LowerLfo2, StartLfo3, RaiseLfo3, LowerLfo3, StartLfo4,
    RaiseLfo4, LowerLfo4, SelectTrack, ShiftTrack, SetGlobalVolume, SetTempo,
    SetTicksPerRow, JumpToLine,
)  # fmt: skip


def Lfos(module: Module, track: Track) -> None:
    """Each running LFO adds the change of its wave value × depth >> 7
    to its target field on the work track, within 0 and the limit. On
    pitch the change counts twice. A `once` LFO stops at the wave's
    end."""
    target = work(module, track)
    for lfo in track.lfos:
        if not lfo.speed or not lfo.target:
            continue
        value = lfo_wave(lfo.wave, lfo.pos) * lfo.depth >> 7
        change = value - lfo.last
        if lfo.target == "pitch":
            change *= 2
        now = get_field(target, lfo.target) + change
        set_field(target, lfo.target, 0 if now < 0 else min(now, lfo.limit))
        lfo.last = value
        lfo.pos += lfo.speed
        if lfo.pos >= LFO_WAVE_BYTES:
            lfo.pos -= LFO_WAVE_BYTES
            if lfo.once:
                lfo.speed = 0


# --- Mixer -------------------------------------------------------------


class Scaled(Enum):
    LOWER = auto()  # the lower track is quieter: it goes through the table
    HIGHER = auto()  # the higher track is quieter
    NONE = auto()  # equal volumes


def MixPairs(module: Module, pair: int) -> None:
    """Channel `pair`'s interrupt. All four channels get the period and
    volume computed at their last mix. Then this pair's higher track
    sets the next period, the louder one the next volume, and the pair
    is mixed into the half Paula takes next."""
    for n, channel in enumerate(module.amiga.paula.channels):
        channel.period = module.next_periods[n]
        channel.set_volume(module.next_volumes[n])
    high, low = module.tracks[2 * pair], module.tracks[2 * pair + 1]
    if high.pitch <= low.pitch:
        high, low = low, high
    module.next_periods[pair] = pair_period(high.pitch)
    difference = high.pitch - low.pitch
    low.step = (skip_step(difference) + module.pair_tune[pair]) & 0xFFFF
    loud, quiet = high.volume, low.volume
    if loud == quiet:
        mode, row = Scaled.NONE, 0
    elif loud > quiet:
        mode, row = Scaled.LOWER, quiet * 64 // loud
    else:
        mode, row, loud = Scaled.HIGHER, loud * 64 // quiet, quiet
    module.next_volumes[pair] = loud * module.global_volume >> 6
    buffer, half = module.buffers[pair], module.halves[pair]
    channel = module.amiga.paula.channels[pair]
    channel.queue(paula.Sample(buffer, half, MIX_WORDS))
    MixPair(module, high, low, mode, row, buffer, half)
    module.halves[pair] ^= MIX_BYTES


def MixPair(
    module: Module,
    high: Track,
    low: Track,
    mode: Scaled,
    row: int,
    out: bytearray,
    at: int,
) -> None:
    """100 words. The higher track moves a byte per output byte; the
    lower one reads a new byte unless its skip step carries. The sum
    wraps: nothing clips it.

    Each track's count is its words left in the sample, and a segment
    runs to the smaller count. The lower track reads fewer bytes than it
    writes, yet its count runs out as if it did not. So it jumps to its
    loop start early, by its pitch ratio."""
    data = module.memory
    high_left, low_left = words_left(module, high), words_left(module, low)
    filled, held, pos = 0, low.held, at
    while filled < MIX_WORDS:
        count = min(high_left, low_left, MIX_WORDS - filled)
        for _ in range(2 * count):
            byte = data[high.play]
            high.play += 1
            total = low.fraction + low.step
            low.fraction = total & 0xFFFF
            if total <= 0xFFFF:  # no carry: a new byte
                held = data[low.play]
                low.play += 1
                if mode is Scaled.LOWER:
                    held = scale(held, row)
            if mode is Scaled.HIGHER:
                byte = scale(byte, row)
            out[pos] = (byte + held) & 0xFF
            pos += 1
        filled += count
        high_left -= count
        low_left -= count
        if not high_left:
            high_left = restart_loop(module, high)
        if not low_left:
            low_left = restart_loop(module, low)
    high.held, high.fraction = data[high.play - 1], 0
    low.held = held


def words_left(module: Module, track: Track) -> int:
    left = (track.end - track.play) // 2
    return left if left > 0 else restart_loop(module, track)


def restart_loop(module: Module, track: Track) -> int:
    """The loop, or SilentSample when there is none."""
    if not track.loop:
        silent = module.silent
        track.start, track.one_shot = silent.start, silent.one_shot
        track.loop_start, track.loop, track.end = (
            silent.loop_start,
            silent.loop,
            silent.end,
        )
    track.play = track.loop_start
    return track.loop


# --- Helpers -----------------------------------------------------------


def arg_a(line: int) -> int:
    return line >> 12 & 0xFFF


def arg_b(line: int) -> int:
    return line & 0xFFF


def goto(track: Track, line: int) -> None:
    track.line = track.script + 4 * line
    if track.line >= track.script_end:
        track.line = None


def branch(module: Module, track: Track, line: int, taken: bool) -> Flow:
    return ScriptGoto(module, track, line) if taken else Flow.NEXT


def work(module: Module, track: Track) -> Track:
    return module.tracks[track.work]


def raise_handler(track: Track, kind: int) -> None:
    if track.handlers[kind]:
        track.pending = track.handlers[kind]


def event_volume(nibble: int) -> int:
    return EVENT_VOLUMES[nibble - 1] if nibble <= len(EVENT_VOLUMES) else 0


def sample_of(module: Module, track: Track) -> Sample:
    return module.silent if track.instrument < 0 else module.samples[track.instrument]


def get_field(track: Track, name: str) -> int:
    if name.startswith("lfo"):
        lfo = track.lfos[int(name[3])]
        return lfo.speed if name.endswith("speed") else lfo.depth
    value: int = getattr(track, name)
    return value


def set_field(track: Track, name: str, value: int) -> None:
    if name.startswith("lfo"):
        setattr(track.lfos[int(name[3])], name.split(".")[1], value)
    else:
        setattr(track, name, value)


def signed(value: int) -> int:
    return value - 0x100 if value & 0x80 else value


def word(data: bytes | bytearray, at: int) -> int:
    return data[at] << 8 | data[at + 1]


def long(data: bytes | bytearray, at: int) -> int:
    return word(data, at) << 16 | word(data, at + 2)
