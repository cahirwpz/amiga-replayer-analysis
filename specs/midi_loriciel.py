"""MIDI-Loriciel's replay: MIDI - Loriciel.AMP.asm, Wanted Team's V2.0
adaptation of the intro player of Entity (Loriciel, 1993).

Card: players/MIDI-Loriciel.md. Level 2: the control flow runs. Each
CamelCase function is a new name in data/annot/MIDI-Loriciel.yaml; each
CamelCase class is in its `types:`.

The score is an SMF. A separate bank holds instruments: each MIDI
program is a list of sample zones. There is no envelope, vibrato or
instrument program: a note-on sets sample, period and volume once. Four
voices are allocated per note-on. The adaptation sends its Paula writes
through EaglePlayer calls and drops the original's delay loops and play
count. It keeps the original lines as comments; this model follows them.
V1.0 of the adaptation shares the replay code. The adaptations pair
`MIDI.name` with `SMPL.name`, or `.MID` with `.BSP`. Their format checks
differ: V1.0 takes formats 0 and 1; V2.0 rejects 0 but takes 2 and up.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import partial

from hardware import paula
from hardware.amiga import Amiga, Priority
from hardware.clock import CPU_PER_CCK

Steps = Iterator[int]  # a routine that busy-waits: each value is a wait in CCK

VOICES = 4
MIDI_CHANNELS = 16
PULSES_PER_TICK = 4
DEFAULT_PPQ = 192  # a negative division, SMPTE time, gets this instead
DEFAULT_TEMPO = 500_000  # microseconds per quarter note: 120 BPM
E_CLOCK = 715_909  # CIA counts per second on NTSC; PAL has 709379
# After DMA on or off: $200 + 1 loops of nop and dbra. A taken dbra takes 10
# cycles, the last one 14.
NOTE_DELAY_CCK = (513 * 4 + 512 * 10 + 14) // CPU_PER_CCK
SILENCE = paula.Sample(bytes(16))  # the original's empty sample, 8 words;
# the adaptation plays the bank's cleared tag, 2 words, instead
SYSEX, META = 0xF0, 0xFF
NOTE_OFF, NOTE_ON, PROGRAM = 0x80, 0x90, 0xC0
META_CHANNEL, META_END, META_TEMPO = 0x20, 0x2F, 0x51

# PeriodTable: index 0 sits 29 entries into the table. Entries below 124
# are faster than Paula's DMA can fetch (see paula.MIN_PERIOD).
PERIODS = (
    *(1991, 1882, 1772, 1678, 1584, 1491, 1408, 1329, 1254, 1184, 1117, 1055),
    *(995, 940, 887, 837, 790, 746, 704, 664, 627, 592, 559, 527),
    *(498, 470, 443, 419, 395, 373, 352, 332, 314, 296, 279, 264),
    *(249, 235, 222, 209, 198, 186, 176, 166, 157, 148, 140, 132),
    *(124, 117, 111, 105, 99, 93, 88, 83, 78, 74, 70, 66),
)
PERIOD_ZERO = 29

VELOCITY = (  # VelocityTable: velocity / 2 in, half the volume out
    *range(16),
    *(n for n in range(16, 24) for _ in range(2)),
    *(n for n in range(24, 32) for _ in range(4)),
)


# --- What the composer edits -------------------------------------------


@dataclass
class Zone:
    """One sample of an instrument. `top` is the highest note it plays;
    `offset` is subtracted from the note to pick the period."""

    sample: paula.Sample
    offset: int
    top: int


@dataclass
class Bank:
    """The `BNKS` file: per MIDI program, a list of zones, lowest first.
    Loading relocates its offsets into pointers in place."""

    instruments: list[list[Zone]]


@dataclass
class Score:
    """The SMF: format and track count are read, never checked."""

    data: bytes


# --- Player state ------------------------------------------------------


@dataclass
class Track:
    """One `MTrk` chunk. The chunk's end is stored but never read: a
    track without an end event runs on into the next chunk."""

    pos: int
    active: bool = True
    wait: int | None = None  # pulses; None until the first delta is read
    channel: int = 0  # the last channel event's, or the channel prefix


@dataclass
class Voice:
    output: paula.Channel
    midi_channel: int | None = None  # None: free
    note: int = 0


@dataclass
class MidiChannel:
    instrument: list[Zone]
    latest: Voice | None = None  # the voice of its last note-on


@dataclass
class Module:
    score: Score
    bank: Bank
    amiga: Amiga
    plays: int  # passes of the song that the game asked for
    voices: list[Voice]
    ppq_scaled: int = 0  # PPQ × 10000
    tracks: list[Track] = field(default_factory=list)
    active: int = 0  # tracks without an end event yet
    midi_channels: list[MidiChannel] = field(default_factory=list)


# --- Start -------------------------------------------------------------


def new_module(score: Score, bank: Bank, amiga: Amiga, plays: int) -> Module:
    """The game's start call: a play count of 0 plays nothing. CIA-B
    timer A runs PlayTick."""
    voices = [Voice(channel) for channel in amiga.paula.channels]
    module = Module(score, bank, amiga, plays, voices)
    if plays:
        InitTracks(module)
        StartSound(module)
        amiga.timer.on_underflow = lambda: run(amiga, PlayTick(module))
        amiga.timer.start()
    return module


def InitTracks(module: Module) -> None:
    """Reads the header's track count and division, then each track's
    start. A negative division means SMPTE time; the player uses 192 PPQ
    instead."""
    data, pos = module.score.data, 8
    count = word(data, pos + 2)
    division = word(data, pos + 4)
    ppq = DEFAULT_PPQ if division & 0x8000 else division
    module.ppq_scaled = ppq * 10_000
    module.active, pos = count, pos + 6
    module.tracks = []
    for _ in range(count):
        module.tracks.append(InitTrack(data, pos))
        pos += 8 + long(data, pos + 4)


def InitTrack(data: bytes, pos: int) -> Track:
    """No bound: a 17th track overwrites the state after the 16 slots."""
    assert data[pos : pos + 4] == b"MTrk"
    return Track(pos + 8)


def StartSound(module: Module) -> None:
    ResetVoices(module)
    ResetMidiChannels(module)
    SetTempo(module, DEFAULT_TEMPO)


def ResetVoices(module: Module) -> None:
    for voice in module.voices:
        voice.output.set_volume(0)
        voice.output.disable()
        voice.midi_channel = None


def ResetMidiChannels(module: Module) -> None:
    """Every MIDI channel starts with the bank's first program."""
    first = module.bank.instruments[0]
    module.midi_channels = [MidiChannel(first) for _ in range(MIDI_CHANNELS)]


# --- Timing ------------------------------------------------------------


def SetTempo(module: Module, tempo: int) -> None:
    """Tempo, in microseconds per quarter note, sets the tick rate: a
    tick is four pulses. The rate is a whole number of ticks per second,
    so at 48 Hz it can be 2 % off. The divisions are 16-bit (overflow
    not modelled)."""
    pulses_per_second = module.ppq_scaled // (tempo // 100)
    SetTimer(module, (pulses_per_second & 0xFFFF) >> 2)


def SetTimer(module: Module, ticks_per_second: int) -> None:
    """The latch uses the NTSC E clock, so on PAL the song plays 0.9 %
    slow."""
    module.amiga.timer.set_latch(E_CLOCK // ticks_per_second)


def PlayTick(module: Module) -> Steps:
    """The timer interrupt. Each active track advances four pulses, in
    file order. Then SilentTail. Once every track has ended, one tick
    restarts the song instead; after the last pass it stops."""
    if module.active:
        for track in module.tracks:
            if track.active:
                yield from TrackTick(module, track)
    else:
        module.plays -= 1
        if not module.plays:
            module.amiga.timer.on_underflow = None  # the timer stops
            ResetVoices(module)
            return
        RestartSong(module)
    SilentTail(module)


def RestartSong(module: Module) -> None:
    """Tracks, voices, programs and tempo all start again."""
    InitTracks(module)
    StartSound(module)


def TrackTick(module: Module, track: Track) -> Steps:
    """At its first visit, a track reads its first delta. Later visits
    subtract four pulses; at zero or below, the waiting event runs."""
    if track.wait is None:
        track.wait = 0
    else:
        track.wait -= PULSES_PER_TICK
        if track.wait > 0:
            return
        yield from ReadEvent(module, track)
    yield from ReadDelta(module, track)


def ReadDelta(module: Module, track: Track) -> Steps:
    """A zero delta runs the next event in this visit. A positive one
    ends the visit, even when the negative remainder of the last wait
    makes the sum zero or less: events closer than four pulses slip to
    later ticks. The remainder keeps the average in time."""
    while track.active:
        delta = read_number(module.score.data, track)
        if delta:
            SaveWait(track, delta)
            return
        yield from ReadEvent(module, track)


def SaveWait(track: Track, delta: int) -> None:
    assert track.wait is not None
    track.wait += delta


# --- Events ------------------------------------------------------------


def ReadEvent(module: Module, track: Track) -> Steps:
    """Every event needs its status byte: there is no running status.
    Unknown system events skip two bytes, whatever their length."""
    status = read_byte(module.score.data, track)
    if status < SYSEX:
        yield from ChannelEvent(module, track, status)
    elif status == SYSEX:
        SkipSysex(module, track)
    elif status == META:
        ReadMeta(module, track)
    else:
        SkipTwoBytes(track)


def ChannelEvent(module: Module, track: Track, status: int) -> Steps:
    """Only note-on, note-off and program change act. The others, CCs
    and pitch bend among them, skip two bytes. Channel pressure has one,
    so the track loses its place. A data byte where a status byte
    belongs also sets the track's channel, from its low four bits."""
    track.channel = status & 0x0F
    kind = status & 0xF0
    if kind == NOTE_ON:
        yield from NoteOnEvent(module, track)
    elif kind == NOTE_OFF:
        yield from NoteOffEvent(module, track)
    elif kind == PROGRAM:
        ProgramEvent(module, track)
    else:
        SkipTwoBytes(track)


def SkipTwoBytes(track: Track) -> None:
    track.pos += 2


def SkipSysex(module: Module, track: Track) -> None:
    track.pos += read_number(module.score.data, track)


def ReadMeta(module: Module, track: Track) -> None:
    """End, channel prefix and tempo take their length byte on trust."""
    kind = read_byte(module.score.data, track)
    if kind == META_END:
        EndTrack(module, track)
    elif kind == META_CHANNEL:
        ChannelPrefix(module, track)
    elif kind == META_TEMPO:
        TempoEvent(module, track)
    else:
        SkipMeta(module, track)


def SkipMeta(module: Module, track: Track) -> None:
    track.pos += read_number(module.score.data, track)


def EndTrack(module: Module, track: Track) -> None:
    track.pos += 1
    track.active = False
    module.active -= 1


def ChannelPrefix(module: Module, track: Track) -> None:
    """The next channel event overwrites it."""
    track.pos += 1
    track.channel = read_byte(module.score.data, track)


def TempoEvent(module: Module, track: Track) -> None:
    track.pos += 1
    data = module.score.data
    tempo = int.from_bytes(data[track.pos : track.pos + 3], "big")
    track.pos += 3
    SetTempo(module, tempo)


def NoteOnEvent(module: Module, track: Track) -> Steps:
    """Velocity 0 is a note-off."""
    data = module.score.data
    if data[track.pos + 1] == 0:
        yield from NoteOffEvent(module, track)
        return
    note, velocity = read_byte(data, track), read_byte(data, track)
    yield from StartNote(module, track.channel, note, velocity)


def NoteOffEvent(module: Module, track: Track) -> Steps:
    """Its velocity is read and dropped."""
    data = module.score.data
    note, _ = read_byte(data, track), read_byte(data, track)
    yield from StopNote(module, track.channel, note)


def ProgramEvent(module: Module, track: Track) -> None:
    SelectProgram(module, track.channel, read_byte(module.score.data, track))


def SelectProgram(module: Module, channel: int, program: int) -> None:
    """Later notes on the MIDI channel use the instrument; playing notes
    keep theirs. A program beyond the bank reads past it (not
    modelled)."""
    module.midi_channels[channel].instrument = module.bank.instruments[program]


# --- Voices ------------------------------------------------------------


def StartNote(module: Module, channel: int, note: int, velocity: int) -> Steps:
    """No DMA off comes first. On a free voice, note-off already stopped
    the channel, so DMA on starts the sample. A stolen voice still plays,
    so DMA on changes nothing: the new sample starts only if Paula
    reloads the channel before SilentTail, which queues silence. If not,
    the note is silent, or the old sample plays on at the new period and
    volume. Paula reloads when a pass ends; a silent pass of 8 words
    takes 16 × period CCK."""
    voice = AllocateVoice(module, channel, note)
    SelectSample(module, voice, note)
    SetVelocity(voice, velocity)
    voice.output.enable()
    yield NOTE_DELAY_CCK


def StopNote(module: Module, channel: int, note: int) -> Steps:
    """DMA off, with no release: the note stops at once."""
    voice = MatchNoteOff(module, channel, note)
    if voice is None:
        return
    voice.output.disable()
    yield NOTE_DELAY_CCK


def AllocateVoice(module: Module, channel: int, note: int) -> Voice:
    """The first free voice, from voice 0 up. With none free, it steals
    the last busy voice of this MIDI channel, else voice 0. Age and
    volume play no part. The MIDI channel then reaches only this voice:
    a second note hides the first from note-off."""
    stolen = module.voices[0]
    for voice in module.voices:
        if voice.midi_channel is None:
            break
        if voice.midi_channel == channel:
            stolen = voice
    else:
        voice = stolen
    voice.midi_channel, voice.note = channel, note
    module.midi_channels[channel].latest = voice
    return voice


def MatchNoteOff(module: Module, channel: int, note: int) -> Voice | None:
    """Only the MIDI channel's latest voice can end, and only if it
    still plays this channel and note. An earlier voice stays busy until
    it is stolen, even after its sample ends. With a repeated pitch, the
    first note-off ends the latest note."""
    midi = module.midi_channels[channel]
    voice = midi.latest
    if voice is None or voice.midi_channel != channel or voice.note != note:
        return None
    voice.midi_channel = None
    midi.latest = None
    return voice


def SelectSample(module: Module, voice: Voice, note: int) -> None:
    """Queues the zone's sample and sets the period at once."""
    assert voice.midi_channel is not None
    zone = FindSampleZone(module.midi_channels[voice.midi_channel].instrument, note)
    voice.output.queue(zone.sample)
    voice.output.period = PERIODS[PERIOD_ZERO + note - zone.offset]


def FindSampleZone(instrument: list[Zone], note: int) -> Zone:
    """The first zone whose top is at or above the note. Above the last
    zone, the player reads past the list (not modelled)."""
    return next(zone for zone in instrument if note <= zone.top)


def SetVelocity(voice: Voice, velocity: int) -> None:
    """Volume 0 to 62, once per note. The curve is steep up to velocity
    32 and flat above: velocity 64 gives 48."""
    voice.output.set_volume(2 * VELOCITY[velocity >> 1])


def SilentTail(module: Module) -> None:
    """Each busy voice queues silence at the end of every tick. So a
    sample plays once and never loops; sample loops in the bank are
    never used. The voice stays busy until note-off."""
    for voice in module.voices:
        if voice.midi_channel is not None:
            voice.output.queue(SILENCE)


# --- Helpers -----------------------------------------------------------


def run(amiga: Amiga, steps: Steps) -> None:
    """Runs a routine up to its next busy-wait, then goes on after it."""
    for wait in steps:
        amiga.after(wait, Priority.CPU, partial(run, amiga, steps))
        return


def read_byte(data: bytes, track: Track) -> int:
    byte = data[track.pos]
    track.pos += 1
    return byte


def read_number(data: bytes, track: Track) -> int:
    """A variable-length number: 7 bits per byte, bit 7 set on all but
    the last byte."""
    value = 0
    while True:
        byte = read_byte(data, track)
        value = value << 7 | byte & 0x7F
        if not byte & 0x80:
            return value


def word(data: bytes, pos: int) -> int:
    return int.from_bytes(data[pos : pos + 2], "big")


def long(data: bytes, pos: int) -> int:
    return int.from_bytes(data[pos : pos + 4], "big")
