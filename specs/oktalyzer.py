"""Oktalyzer's two replays: okta.asm, a disassembly of the tracker by
Armin Sander. UADE's OKPlay2 holds replay 2.

Card: players/Oktalyzer.md. Level 2: the control flow runs. Each
CamelCase function is a new name in data/annot/Oktalyzer.yaml; each
CamelCase class is in its `types:`. Comments name the track fields by
their offsets in TrackData.

Eight tracks on four channels. The song marks each channel single or
mixed. A single channel plays one track through Paula. A mixed channel
plays two tracks from a buffer that the CPU fills each tick. Replay 1
plays every buffer at period 227 and resamples both tracks by code it
generates per note. Replay 2 plays a buffer at the higher note's period
and resamples only the lower track.

The model starts from the tracker's tables in memory; the file loader,
the editor, MIDI and the level meters are left out.
"""

from dataclasses import dataclass, field

from hardware import paula
from hardware.amiga import Amiga, Priority
from hardware.clock import LINE_CCK

CHANNELS = 4
CELL = 4  # note, sample, effect, argument
NOTES = 36  # C-1 to B-3; a note byte is 1 + its index
MAX_VOLUME = 64
LOWEST, HIGHEST = 856, 113  # period limits of effects 1 and 2
POLL_CCK = 10  # one INTREQR poll: about 20 68000 cycles (estimate)

# Sample modes, SampleInfo byte 30
MIXED_ONLY, SINGLE_ONLY, BOTH = 0, 1, 2

# Effects: the tracker shows them as 0-9, A-Z
PITCH_UP, PITCH_DOWN = 1, 2
ARPEGGIO, ARPEGGIO2, ARPEGGIO3, NOTE_DOWN, FILTER = 10, 11, 12, 13, 15
NOTE_UP_ONCE, NOTE_DOWN_ONCE, OLD_VOLUME, JUMP, SPEED = 17, 21, 24, 25, 28
NOTE_UP, VOLUME = 30, 31
ARPEGGIO_STEPS = (0, 1, 2, 0, 1, 2, 0, 1, 2, 0, 1, 2, 0, 1, 2, 0)
ARPEGGIO3_STEPS = (0, 1, 2, 3, 1, 2, 3, 1, 2, 3, 1, 2, 3, 1, 2, 3)

NOTE_PERIODS = (  # NotePeriods
    *(856, 808, 762, 720, 678, 640, 604, 570, 538, 508, 480, 453),
    *(428, 404, 381, 360, 339, 320, 302, 285, 269, 254, 240, 226),
    *(214, 202, 190, 180, 170, 160, 151, 143, 135, 127, 120, 113),
)

# Replay 1
PERIOD_1 = 227  # about one byte per scanline: 15.6 kHz
HALF_1 = 313  # bytes per tick per channel; the buffer holds two halves
NOTE_STEPS = (  # NoteSteps: 16.16 source bytes per output byte
    *(0x4409, 0x4814, 0x4C6E, 0x50E3, 0x55E6, 0x5B00, 0x606C, 0x662C, 0x6C40),
    *(0x72A5, 0x7955, 0x8090, 0x8813, 0x9028, 0x98DC, 0xA1C7, 0xABCC, 0xB600),
    *(0xC0D9, 0xCC59, 0xD881, 0xE54A, 0xF2AA, 0x101B2, 0x11026, 0x12051),
    *(0x13286, 0x1438E, 0x15696, 0x16C00, 0x181B2, 0x19745, 0x1AF68, 0x1CA95),
    *(0x1E555, 0x20365),
)

# Replay 2
TOP_NOTE_2 = 33  # ClampNote: mixed tracks play notes 0-33
WORDS_PER_FRAME = (  # WordsPerFrame, PAL: a frame at the note's period
    *(41, 43, 46, 49, 52, 55, 58, 62, 66, 69, 74, 78, 83, 87, 93, 98, 104),
    *(111, 117, 124, 132, 139, 148, 157, 166, 175, 186, 197, 208, 222, 235),
    *(248, 263, 279),
)
IDLE_WORDS_2 = 41  # Replay2Init: an 82-byte silent buffer at period 856


# --- What the composer edits -------------------------------------------


@dataclass
class SampleEntry:  # SampleInfo: 32 bytes each, 36 samples
    data: bytes  # mode 0 may lie in any memory; the CPU reads it
    repeat_start: int  # words
    repeat_length: int  # words; 0: no loop
    volume: int
    mode: int  # 0 mixed tracks, 7 bits; 1 single tracks, 8 bits; 2 both


@dataclass
class Score:  # the tracker's tables after loading
    mixed: list[bool]  # ChannelModes: per channel
    samples: list[SampleEntry | None]
    patterns: list[list[bytes]]  # rows; a row is 4 bytes per track
    positions: list[int]  # pattern numbers
    speed: int  # ticks per row at the start

    def tracks(self) -> int:
        return CHANNELS + sum(self.mixed)


# --- Track and channel state -------------------------------------------


@dataclass
class Track:  # TrackData: 14 bytes per track
    """A mixed track: a pointer, the bytes left, the note. A single
    channel's track keeps its loop, note and period."""

    data: bytes = b""  # 2: the sample; for a single track, its loop
    pointer: int = 0  # into data
    left: int = 0  # 6: bytes; a single track: loop words
    playing: bool = False
    note: int = 0  # 10: now; a single track: 8
    base: int = 0  # 12: a mixed track's note before effects
    period: int = 0  # 10: a single track's period


@dataclass
class ChannelBuffer:  # ChannelBuffers: 16 bytes per mixed channel
    buffer: bytes | None = None  # 0: this tick's buffer
    period: int = 0  # 4: the higher note's period
    words: int = 0  # 6: the buffer's length
    extra: int = 0  # 8: DriftFix, 0 or 1 word
    irq_seen: bool = False  # 10: INTREQ bit at the tick's start


@dataclass
class Module:  # TickInRow, RowSpeed, PositionIndex and the rest
    score: Score
    amiga: Amiga
    replay: int = 2
    tracks: list[Track] = field(default_factory=list)
    buffers: list[ChannelBuffer] = field(default_factory=list)
    counter: int = 0  # TickInRow
    speed: int = 6  # RowSpeed
    row: int = 0  # RowIndex
    position: int = 0  # PositionIndex
    jump: int | None = None  # JumpTarget
    cells: list[bytes] = field(default_factory=list)  # RowCells: this row
    volumes: list[int] = field(default_factory=lambda: [MAX_VOLUME] * CHANNELS)
    old_volumes: list[int] = field(default_factory=lambda: [MAX_VOLUME] * CHANNELS)
    filter: bool = False
    pending_dma: set[int] = field(default_factory=set)  # PendingDma
    resamplers: list[list["Op"]] = field(default_factory=list)  # ResamplerCode
    source_bytes: list[int] = field(default_factory=list)  # SourceBytes
    second_half: bool = False  # replay 1: the half this tick writes
    output: list[bytearray] = field(default_factory=list)  # replay 1 buffers


def signed(byte: int) -> int:
    return byte - 256 if byte & 0x80 else byte


def channel_of(score: Score, track: int) -> int:
    """TrackToChannel: a mixed channel owns two tracks, in order."""
    number = 0
    for channel, mixed in enumerate(score.mixed):
        number += 2 if mixed else 1
        if track < number:
            return channel
    raise IndexError(track)


def channel_tracks(score: Score, channel: int) -> list[int]:
    first = sum(2 if m else 1 for m in score.mixed[:channel])
    return [first, first + 1] if score.mixed[channel] else [first]


def new_module(score: Score, amiga: Amiga, replay: int = 2) -> Module:
    """The copper interrupt runs the replay once per frame."""
    module = Module(score, amiga, replay)
    module.tracks = [Track() for _ in range(score.tracks())]
    module.buffers = [ChannelBuffer() for _ in range(CHANNELS)]
    InitSong(module)
    if replay == 1:
        Replay1Init(module)
        amiga.vblank.handler = lambda: Play1(module)
    else:
        Replay2Init(module)
        amiga.vblank.handler = lambda: Play2(module)
    return module


def InitSong(module: Module) -> None:
    """All volumes 64. The first row is read after `speed` ticks."""
    module.volumes = [MAX_VOLUME] * CHANNELS
    module.speed = module.score.speed
    module.position, module.row, module.jump = 0, -1, None
    module.counter = 0
    module.cells = [bytes(CELL)] * module.score.tracks()


# --- The sequencer, shared by both replays ------------------------------


def ReplayHandler(module: Module) -> None:
    """Single channels first: last tick's DMA on, this row's notes, tick
    effects, volumes. Then the row counter, and at its end the next row
    and the mixed tracks' notes. Then the mixed tracks' tick effects."""
    SetHardware(module)
    module.counter += 1
    if module.counter >= module.speed:
        NewRow(module)
        GetMixedNotes(module)
    for track, cell in enumerate(module.cells):
        if module.score.mixed[channel_of(module.score, track)]:
            TrackEffects(module, track, cell)


def NewRow(module: Module) -> None:
    """After the pattern's last row, or after a jump, the next position.
    After the last position, position 0 and the song's first speed."""
    module.counter = 0
    module.row += 1
    score = module.score
    pattern = score.patterns[score.positions[module.position]]
    if module.jump is not None or module.row >= len(pattern):
        module.row = 0
        if module.jump is not None:
            module.position = module.jump
        else:
            module.position += 1
        if module.position == len(score.positions):
            module.position = 0
            module.speed = score.speed
        pattern = score.patterns[score.positions[module.position]]
    line = pattern[module.row]
    module.cells = [line[n : n + CELL] for n in range(0, len(line), CELL)]
    module.jump = None


def GetMixedNotes(module: Module) -> None:
    """A note on a mixed track sets the sample and the note. It ignores
    the sample's volume, and a sample of mode 1."""
    for number, cell in enumerate(module.cells):
        if not module.score.mixed[channel_of(module.score, number)]:
            continue
        if not cell[0]:
            continue
        entry = module.score.samples[cell[1]]
        if entry is None or entry.mode == SINGLE_ONLY:
            continue
        track = module.tracks[number]
        track.data, track.pointer, track.left = entry.data, 0, len(entry.data)
        track.playing = True
        track.note = track.base = cell[0] - 1


def SetHardware(module: Module) -> None:
    """At a row's first tick, single notes start: DMA off now, on at the
    next tick. So a single channel is silent for one tick before each
    note, and sounds a tick after the mixed tracks."""
    TurnDmaOn(module)
    if module.counter == 0:
        StartNotes(module)
    ChannelEffects(module)
    module.old_volumes = list(module.volumes)
    for channel, volume in zip(module.amiga.paula.channels, module.volumes):
        channel.set_volume(volume)


def TurnDmaOn(module: Module) -> None:
    """DMA on for last tick's notes; a busy-wait for two line changes;
    then their loops."""
    starting = sorted(module.pending_dma)
    module.pending_dma.clear()
    if not starting:
        return
    channels = module.amiga.paula.channels
    for number in starting:
        channels[number].enable()

    def write_loops() -> None:
        for number in starting:
            track = module.tracks[channel_tracks(module.score, number)[0]]
            channels[number].queue(paula.Sample(track.data))

    wait = LINE_CCK - module.amiga.now % LINE_CCK + LINE_CCK
    module.amiga.after(wait, Priority.CPU, write_loops)


def StartNotes(module: Module) -> None:
    """Single channels: DMA off, the sample, the period, its volume. A
    sample of mode 0 is ignored. With a loop, the channel plays up to the
    loop's end, then the loop; without, a 2-byte silent loop."""
    score = module.score
    for number, channel in enumerate(module.amiga.paula.channels):
        if score.mixed[number]:
            continue
        index = channel_tracks(score, number)[0]
        cell = module.cells[index]
        entry = score.samples[cell[1]] if cell[0] else None
        if entry is None or entry.mode == MIXED_ONLY or len(entry.data) < 2:
            continue
        track = module.tracks[index]
        channel.disable()
        module.pending_dma.add(number)
        track.note = cell[0] - 1
        track.period = channel.period = NOTE_PERIODS[track.note]
        module.volumes[number] = entry.volume
        if entry.repeat_length:
            start = 2 * entry.repeat_start
            end = start + 2 * entry.repeat_length
            channel.queue(paula.Sample(entry.data[:end]))
            track.data = entry.data[start:end]
        else:
            channel.queue(paula.Sample(entry.data))
            track.data = bytes(2)  # EmptyWave


# --- Effects ------------------------------------------------------------


def ChannelEffects(module: Module) -> None:
    """Single channels, every tick. Pitch effects work in periods (1, 2)
    or in notes (the rest)."""
    score = module.score
    for number in range(CHANNELS):
        if score.mixed[number]:
            continue
        index = channel_tracks(score, number)[0]
        cell = module.cells[index]
        track, channel = module.tracks[index], module.amiga.paula.channels[number]
        effect, arg = cell[2], cell[3]
        if effect == PITCH_UP:
            track.period = max(track.period - arg, HIGHEST)
            channel.period = track.period
        elif effect == PITCH_DOWN:
            track.period = min(track.period + arg, LOWEST)
            channel.period = track.period
        elif effect in (ARPEGGIO, ARPEGGIO2, ARPEGGIO3):
            note = arpeggio(module, effect, arg, track.note)
            if note is not None:
                SetNotePeriod(track, channel, note)
        elif effect in (NOTE_UP, NOTE_DOWN, NOTE_UP_ONCE, NOTE_DOWN_ONCE):
            step = slide(module, effect, arg)
            if step is not None:
                track.note += step
                SetNotePeriod(track, channel, track.note)
        elif effect == OLD_VOLUME:
            OldVolume(module, index, arg)
        else:
            song_effect(module, index, effect, arg)


def TrackEffects(module: Module, index: int, cell: bytes) -> None:
    """Mixed tracks, every tick. Pitch effects move the note; there is no
    portamento and no old volume."""
    track = module.tracks[index]
    effect, arg = cell[2], cell[3]
    if effect in (ARPEGGIO, ARPEGGIO2, ARPEGGIO3):
        note = arpeggio(module, effect, arg, track.base)
        if note is not None:
            track.note = note
    elif effect in (NOTE_UP, NOTE_DOWN, NOTE_UP_ONCE, NOTE_DOWN_ONCE):
        step = slide(module, effect, arg)
        if step is not None:
            track.base += step
            track.note += step
    elif effect not in (PITCH_UP, PITCH_DOWN, OLD_VOLUME):
        song_effect(module, index, effect, arg)


def arpeggio(module: Module, effect: int, arg: int, note: int) -> int | None:
    """Effect 10: down by the high nibble, base, up by the low nibble.
    Effect 11: base, up by the low nibble, base, down by the high
    nibble. Effect 12: up by the high nibble, up by the low nibble, base;
    its first tick keeps the last note."""
    high, low, tick = arg >> 4, arg & 0x0F, module.counter
    if effect == ARPEGGIO:
        return (note - high, note, note + low)[ARPEGGIO_STEPS[tick]]
    if effect == ARPEGGIO2:
        return (note, note + low, note, note - high)[tick & 3]
    step = ARPEGGIO3_STEPS[tick]
    return None if step == 0 else (0, note + high, note + low, note)[step]


def slide(module: Module, effect: int, arg: int) -> int | None:
    """Notes up or down: 30 and 13 every tick, 17 and 21 once per row."""
    once = effect in (NOTE_UP_ONCE, NOTE_DOWN_ONCE)
    if once and module.counter:
        return None
    return arg if effect in (NOTE_UP, NOTE_UP_ONCE) else -arg


def SetNotePeriod(track: Track, channel: paula.Channel, note: int) -> None:
    """The note, clamped to 0-35, gives the period."""
    track.period = channel.period = NOTE_PERIODS[min(max(note, 0), NOTES - 1)]


def song_effect(module: Module, index: int, effect: int, arg: int) -> None:
    if effect == JUMP:
        PositionJump(module, arg)
    elif effect == SPEED:
        SetSpeed(module, arg)
    elif effect == FILTER and not module.counter:
        module.filter = arg != 0
    elif effect == VOLUME:
        SetVolume(module, channel_of(module.score, index), arg)


def PositionJump(module: Module, arg: int) -> None:
    """At the row's first tick. The argument is decimal: $12 is 12."""
    target = (arg >> 4) * 10 + (arg & 0x0F)
    if not module.counter and target < len(module.score.positions):
        module.jump = target


def SetSpeed(module: Module, arg: int) -> None:
    if not module.counter and arg & 0x0F:
        module.speed = arg & 0x0F


def SetVolume(module: Module, channel: int, arg: int) -> None:
    """Up to 64 sets the channel's volume; both tracks of a mixed channel
    share it. Above, VolumeSlide."""
    if arg <= MAX_VOLUME:
        module.volumes[channel] = arg
    else:
        VolumeSlide(module, channel, arg)


def VolumeSlide(module: Module, channel: int, arg: int) -> None:
    """$41-$50 down and $51-$60 up every tick; $61-$70 down and $71-$80 up
    once per row. The step is the low nibble."""
    arg -= MAX_VOLUME
    kind, step = divmod(arg, 16)
    if kind > 3 or (kind >= 2 and module.counter):
        return
    volume = module.volumes[channel]
    if kind in (0, 2):
        module.volumes[channel] = max(volume - step, 0)
    else:
        module.volumes[channel] = min(volume + step, MAX_VOLUME)


def OldVolume(module: Module, index: int, arg: int) -> None:
    """Effect 24, single channels: the volume from before this tick, so
    a note keeps the last volume, not its sample's."""
    channel = channel_of(module.score, index)
    module.volumes[channel] = module.old_volumes[channel]
    if arg > MAX_VOLUME:
        VolumeSlide(module, channel, arg)


# --- Replay 1: generated resamplers -------------------------------------


@dataclass
class Op:  # one code piece of ResampleTemplates
    means: int  # output bytes that are means of the last output and `byte`
    copies: int  # output bytes of `byte`
    offset: int  # the source byte read: 0 or 1 past the pointer
    advance: int  # source bytes the pointer moves


def Replay1Init(module: Module) -> None:
    """Every channel loops a 626-byte buffer at period 227; single
    channels take over theirs with each note."""
    BuildResamplers(module)
    module.output = [bytearray(2 * HALF_1) for _ in range(CHANNELS)]
    for channel, buffer in zip(module.amiga.paula.channels, module.output):
        channel.period = PERIOD_1
        channel.play(paula.Sample(bytes(buffer)))


def BuildResamplers(module: Module) -> None:
    """Per note, straight-line code for 313 output bytes. Each output
    byte steps a 16.16 source position. A step of 1 copies; 2 copies and
    skips; 3 skips one and copies. Where the step repeats a source byte,
    the code writes means of the last output and the next source byte
    instead: 1-3 repeats. The model keeps the pieces as Ops."""
    module.resamplers, module.source_bytes = [], []
    for step in NOTE_STEPS:
        ops: list[Op] = []
        position, last, repeats = 0, -1, 0
        for _ in range(HALF_1):
            index = position >> 16
            if index == last:
                repeats += 1
            elif index - last == 1:
                ops.append(Op(min(repeats, 2), 1 + (repeats == 3), 0, 1))
                repeats = 0
            elif index - last == 2:
                ops.append(Op(0, 1, 0, 2))
            else:
                ops.append(Op(0, 1, 1, 2))
            last = index
            position += step
        if repeats:
            ops.append(Op(min(repeats, 2), int(repeats == 3), 0, 0))
        module.resamplers.append(ops)
        module.source_bytes.append(position >> 16)


def RunResampler(ops: list[Op], data: bytes, pointer: int) -> tuple[bytes, int]:
    """The generated code for one note: 313 bytes, and the new pointer.
    Means use byte adds: 7-bit samples keep them from wrapping."""
    out, last = bytearray(), 0
    for op in ops:
        at = pointer + op.offset
        byte = data[at] if at < len(data) else 0
        mean = (signed((last + byte) & 0xFF) >> 1) & 0xFF
        out += bytes([mean] * op.means + [byte] * op.copies)
        last = out[-1]
        pointer += op.advance
    return bytes(out), pointer


def Play1(module: Module) -> None:
    """The sequencer, then per mixed channel: resample both tracks,
    add them into this tick's half. The halves alternate each tick; the
    channel loops the whole buffer and is never synced. Paula reads the
    buffer in place; the model plays no bytes."""
    ReplayHandler(module)
    module.second_half = not module.second_half
    start = HALF_1 if module.second_half else 0
    for number in range(CHANNELS):
        if not module.score.mixed[number]:
            continue
        a, b = (ResampleTrack(module, t) for t in channel_tracks(module.score, number))
        module.output[number][start : start + HALF_1] = AddPacked(a, b, start % 2)


def ResampleTrack(module: Module, index: int) -> bytes:
    """A track stops at the tick when fewer bytes are left than its note
    needs: the last part never plays."""
    track = module.tracks[index]
    if not track.playing:
        return bytes(HALF_1)
    track.note = min(max(track.note, 0), NOTES - 1)
    if track.left <= module.source_bytes[track.note]:
        module.tracks[index] = Track()
        return bytes(HALF_1)
    out, pointer = RunResampler(
        module.resamplers[track.note], track.data, track.pointer
    )
    track.left -= pointer - track.pointer
    track.pointer = pointer
    return out


def AddPacked(a: bytes, b: bytes, lead: int) -> bytes:
    """add.l adds 4 bytes at once: a carry out of one byte spills into
    the byte before it. The odd byte is added alone."""
    out = bytearray(len(a))
    single = 0 if lead else len(a) - 1
    out[single] = (a[single] + b[single]) & 0xFF
    first = 1 if lead else 0
    for at in range(first, first + len(a) - 1, 4):
        total = int.from_bytes(a[at : at + 4], "big") + int.from_bytes(
            b[at : at + 4], "big"
        )
        out[at : at + 4] = (total & 0xFFFFFFFF).to_bytes(4, "big")
    return bytes(out)


# --- Replay 2: the higher note sets the rate ----------------------------


def Replay2Init(module: Module) -> None:
    for channel in module.amiga.paula.channels:
        channel.period = NOTE_PERIODS[0]
        channel.play(paula.Sample(bytes(2 * IDLE_WORDS_2)))


def Play2(module: Module) -> None:
    """Periods for last tick's buffers, the sequencer, then per mixed
    channel a new buffer. QueueBuffers waits for the channels."""
    SetPeriods(module)
    ReplayHandler(module)
    for number in range(CHANNELS):
        if module.score.mixed[number]:
            MixChannel(module, number)
    QueueBuffers(module)


def SetPeriods(module: Module) -> None:
    """Each mixed channel gets the period of the buffer queued last tick.
    DriftFix follows."""
    channels = module.amiga.paula.channels
    for channel, buffer in zip(channels, module.buffers):
        if buffer.period:
            channel.period = buffer.period
            buffer.irq_seen = channel.irq_requested
    DriftFix(module)


def DriftFix(module: Module) -> None:
    """A buffer lasts slightly less than a frame, so a channel runs
    ahead. One that already took its buffer at the tick's start gets one
    word more in the next."""
    for buffer in module.buffers:
        if buffer.buffer is not None:
            buffer.extra = int(buffer.irq_seen)


def QueueBuffers(module: Module) -> None:
    """Busy-wait until every mixed channel took last tick's buffer; then
    queue the new ones. So the tick waits for a channel that runs late."""
    channels = [
        c
        for c, b in zip(module.amiga.paula.channels, module.buffers)
        if b.buffer is not None
    ]

    def poll() -> None:
        if not all(channel.irq_requested for channel in channels):
            module.amiga.after(POLL_CCK, Priority.CPU, poll)
            return
        for channel, buffer in zip(module.amiga.paula.channels, module.buffers):
            if buffer.buffer is not None:
                channel.irq_requested = False
                channel.queue(paula.Sample(buffer.buffer))

    poll()


def ClampNote(track: Track) -> int:
    track.note = min(max(track.note, 0), TOP_NOTE_2)
    return track.note


def MixChannel(module: Module, number: int) -> None:
    """Two playing tracks: MixPair. One: CopySingle. None: silence at
    note 0's period."""
    first, second = (module.tracks[t] for t in channel_tracks(module.score, number))
    buffer = module.buffers[number]
    if first.playing and second.playing:
        PickHigher(module, buffer, first, second)
    else:
        CopySingle(buffer, first if first.playing else second)


def PickHigher(module: Module, buffer: ChannelBuffer, a: Track, b: Track) -> None:
    """The higher note plays unchanged; on equal notes, the first track."""
    if ClampNote(a) >= ClampNote(b):
        MixPair(buffer, a, b)
    else:
        MixPair(buffer, b, a)


def MixPair(buffer: ChannelBuffer, high: Track, low: Track) -> None:
    """The buffer lasts a frame at the higher note's period. The lower
    track is resampled to that rate, the higher one added on top. A
    track with fewer bytes left than the buffer needs stops."""
    buffer.period = NOTE_PERIODS[high.note]
    buffer.words = WORDS_PER_FRAME[high.note] + buffer.extra
    step = (buffer.period << 16) // NOTE_PERIODS[low.note]
    out = bytearray(2 * buffer.words)
    ResampleLower(out, low, step if step < 0x10000 else 0, buffer.words)
    AddHigher(out, high, buffer.words)
    buffer.buffer = bytes(out)


def ResampleLower(out: bytearray, track: Track, step: int, words: int) -> None:
    """A 16-bit fraction picks the source byte: each output byte repeats
    the last fetched one, with no interpolation. On equal notes, a plain
    copy. Too few bytes left: silence, and the track ends. An odd count
    skips one byte, to keep the pointer even."""
    if not step:
        copy_part(out, track, words)
        return
    needed = 2 * ((step * words) >> 16)
    if needed > track.left:
        track.left = 0
        return
    fraction, byte, fetched = 0, 0, 0
    for at in range(2 * words):
        fraction -= step
        if fraction < 0:
            fraction += 0x10000
            source = track.pointer + fetched
            byte = track.data[source] if source < len(track.data) else 0
            fetched += 1
        out[at] = byte
    fetched += fetched & 1
    if fetched > track.left:  # rounding took more than was left
        track.playing, track.left = False, 0
        return
    track.pointer += fetched
    track.left -= fetched


def AddHigher(out: bytearray, track: Track, words: int) -> None:
    """add.l per 2 words, add.w for the last few: carries spill into the
    byte before. Too few bytes left: the part that is there plays, then
    the track ends."""
    count = min(track.left // 2, words)
    longs = count - count % 8
    source = track.data[track.pointer : track.pointer + 2 * count]
    for at, size in [(n, 4) for n in range(0, 2 * longs, 4)] + [
        (n, 2) for n in range(2 * longs, 2 * count, 2)
    ]:
        total = int.from_bytes(out[at : at + size], "big") + int.from_bytes(
            source[at : at + size], "big"
        )
        out[at : at + size] = (total % (1 << 8 * size)).to_bytes(size, "big")
    end_or_step(track, words)


def copy_part(out: bytearray, track: Track, words: int) -> None:
    count = min(track.left // 2, words)
    out[: 2 * count] = track.data[track.pointer : track.pointer + 2 * count]
    end_or_step(track, words)


def end_or_step(track: Track, words: int) -> None:
    if track.left < 2 * words:
        track.playing, track.left = False, 0
        return
    track.pointer += 2 * words
    track.left -= 2 * words


def CopySingle(buffer: ChannelBuffer, track: Track) -> None:
    """One track at its own period: copied, then silence to the end."""
    note = ClampNote(track) if track.playing else 0
    buffer.period = NOTE_PERIODS[note]
    buffer.words = WORDS_PER_FRAME[note] + buffer.extra
    out = bytearray(2 * buffer.words)
    if track.playing:
        copy_part(out, track, buffer.words)
    buffer.buffer = bytes(out)
