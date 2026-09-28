"""SoundPlayer V4.05 (Scott Johnston, 1991), from Lemmings' CDTV
version: SoundPlayer_v1.asm, Wanted Team's adaptation.

Card: players/SoundPlayer.md. Level 2: the control flow runs. Each
CamelCase function is a new name in data/annot/SoundPlayer.yaml; each
CamelCase class is in its `types:`.

A song is one list of rows: 12 bytes, three per voice. Each voice reads
its own column from its own track position, with its own waits and
repeats. A song takes the voices in its voice mask; the others play on.
So a game can start a sound effect as a song on one voice while the
music keeps the rest. An instrument is an IFF 8SVX sample: a one-shot
part, then a repeat part. The adaptation keeps the game's entry points
as comments: start a song, silence voices, read and write the game
flags, and fade voices. This model follows them.
"""

from dataclasses import dataclass, field

from hardware import paula
from hardware.amiga import Amiga

VOICES = 4
ROW_SIZE = 12  # 3 bytes per voice: note, instrument, command
FIRST_ROW = 3  # after the header: timer low byte, timer high byte, voice mask
SPEED = 6  # ticks per row; nothing changes it
MAX_VOLUME = 63
NO_REPEAT = 0xFF
GAME_FLAGS = 20
KEEP_TIMER = 0xFF  # a timer low byte of $ff keeps the running rate
EMPTY = paula.Sample(bytes(2))  # one word of chip memory; queued between notes

# PeriodTable: notes 1-39, G#0 to B-3 in ProTracker's names. It skips
# B-0: note 3 is A#0, note 4 is C-1. Notes 38 and 39 are faster than
# Paula's DMA can fetch (see paula.MIN_PERIOD).
PERIODS = (
    *(1076, 1016, 960),
    *(856, 808, 762, 720, 678, 640, 604, 570, 538, 508, 480, 453),
    *(428, 404, 381, 360, 339, 320, 302, 285, 269, 254, 240, 226),
    *(214, 202, 190, 180, 170, 160, 151, 143, 135, 127, 120, 113),
)


# --- What the composer edits -------------------------------------------


@dataclass
class Instrument:
    """An 8SVX sample. Its one-shot part starts each note; its repeat
    part follows. Up to 38 instruments."""

    first: paula.Sample | None  # None: no one-shot part
    repeat: paula.Sample | None  # None: no repeat part
    played: bool = False  # set at each note start; the game reads and clears it


@dataclass
class Track:
    """One voice's place in one song's rows: a position, one repeat mark
    and one wait. Each song keeps four."""

    data: bytes  # the song's
    start: int
    pos: int = 0
    mark: int = 0
    count: int = NO_REPEAT  # repeats left; NO_REPEAT: no repeat is open
    wait: int = 0  # rows left on the current row


@dataclass
class Song:
    """The header's first two bytes are a CIA timer latch, low byte first.
    The third is the voice mask. The rows follow."""

    data: bytes
    timer: int | None  # None: keep the running rate
    mask: int
    tracks: list[Track]


# --- Player state ------------------------------------------------------


@dataclass
class Voice:
    output: paula.Channel
    track: Track | None = None  # in the song that last took the voice
    note: int = 0  # this row's bytes; 0: none
    instrument_number: int = 0
    command: int = 0
    pending: paula.Sample | None = None  # a one-shot part to start next tick
    repeat: paula.Sample | None = None
    instrument: Instrument | None = None
    period: int = 0
    volume: int = MAX_VOLUME
    hold: bool = False
    slide_down: bool = False
    slide_speed: int = 0  # ticks per volume step; 0: off
    slide_count: int = 0
    locked: bool = False  # a game fade runs; volume commands do nothing


@dataclass
class Module:
    amiga: Amiga
    songs: list[Song]
    instruments: list[Instrument]
    voices: list[Voice]
    counter: int = 0  # ticks to the next row
    flags: list[bool] = field(default_factory=lambda: [False] * GAME_FLAGS)
    attach: list[paula.Attach] = field(
        default_factory=lambda: [paula.Attach.NONE] * VOICES
    )
    filter: bool = True  # the audio filter


# --- Start -------------------------------------------------------------


def new_module(
    amiga: Amiga, songs: list[Song], instruments: list[Instrument]
) -> Module:
    """All voices start on song 0, silent. The CIA timer runs Tick."""
    voices = [Voice(channel) for channel in amiga.paula.channels]
    module = Module(amiga, songs, instruments, voices)
    SilenceVoices(module, 0b1111)
    amiga.timer.on_underflow = lambda: Tick(module)
    amiga.timer.start()
    return module


def new_song(data: bytes) -> Song:
    """The game's song setup. All four tracks start one row before the
    first, since a row tick moves on before it reads."""
    timer = None if data[0] == KEEP_TIMER else data[1] << 8 | data[0]
    tracks = [Track(data, FIRST_ROW - ROW_SIZE) for _ in range(VOICES)]
    return Song(data, timer, data[2], tracks)


def StartSong(module: Module, number: int) -> None:
    """A game entry point. Each voice outside the song's mask keeps
    playing its own song."""
    song = module.songs[number]
    RewindSong(song)
    ClaimVoices(module, song)


def RewindSong(song: Song) -> None:
    for track in song.tracks:
        track.pos, track.count, track.wait = track.start, NO_REPEAT, 0


def ClaimVoices(module: Module, song: Song) -> None:
    """Volume 0 for each voice taken: its first note is silent without a
    volume command. Slide and hold carry over from the last song."""
    for n, voice in enumerate(module.voices):
        if song.mask >> n & 1:
            voice.track = song.tracks[n]
            voice.volume, voice.locked = 0, False
    if song.timer is not None:
        module.amiga.timer.set_latch(song.timer)


def SilenceVoices(module: Module, mask: int) -> None:
    """A game entry point: DMA off for the voices in the mask, which then
    play song 0."""
    for n, voice in enumerate(module.voices):
        if mask >> n & 1:
            voice.output.disable()
            voice.output.queue(EMPTY)
    module.songs[0].mask = mask
    StartSong(module, 0)


# --- Tick --------------------------------------------------------------


def Tick(module: Module) -> None:
    """Volume slides and sample parts, then the notes of the last row
    start. Every sixth tick is a row tick: tracks move on, rows are
    read, new notes stop their channels, and commands run."""
    for voice in module.voices:
        VolumeSlide(module, voice)
    for voice in module.voices:
        NoteRestart(voice)
    RowTimer(module)
    if module.counter:
        return
    for voice in module.voices:
        VoiceWait(voice)
    for column, voice in enumerate(module.voices):
        ReadRow(module, voice, column)
    for voice in module.voices:
        NoteStop(module, voice)
    RowCommands(module)


def RowTimer(module: Module) -> None:
    """The counter runs 0, 5, 4, 3, 2, 1, 0: a row every six ticks."""
    module.counter = SPEED - 1 if module.counter == 0 else module.counter - 1


def VoiceWait(voice: Voice) -> None:
    """A waiting voice stays on its row; else it moves one row on."""
    track = voice.track
    assert track is not None
    if track.wait:
        track.wait -= 1
        if track.wait:
            return
    track.pos += ROW_SIZE


def ReadRow(module: Module, voice: Voice, column: int) -> None:
    """A waiting voice reads nothing, so its row does not repeat."""
    track = voice.track
    assert track is not None
    if track.wait:
        return
    at = track.pos + 3 * column
    voice.note, voice.instrument_number, voice.command = track.data[at : at + 3]


def NoteStop(module: Module, voice: Voice) -> None:
    """DMA off on the row tick. The note starts one tick later, so every
    note has a gap of one tick. The period waits for that start too.
    Notes keep the voice's volume: an instrument has none."""
    if not voice.note:
        return
    voice.output.disable()
    voice.period = PERIODS[voice.note - 1]
    instrument = module.instruments[voice.instrument_number - 1]
    voice.instrument = instrument
    voice.pending, voice.repeat = instrument.first, instrument.repeat
    voice.note = 0


def NoteRestart(voice: Voice) -> None:
    """Queues the one-shot part and sets DMA on. An instrument without a
    one-shot part never starts: DMA stays off."""
    if voice.pending is None:
        return
    assert voice.instrument is not None
    channel = voice.output
    channel.queue(voice.pending)
    channel.period = voice.period
    channel.set_volume(voice.volume)
    channel.enable()
    voice.pending = None
    voice.instrument.played = True


def VolumeSlide(module: Module, voice: Voice) -> None:
    """One step every `slide_speed` ticks, between 0 and 63. At the
    limit, the next step ends the slide."""
    HoldOrRelease(voice)
    if not voice.slide_speed:
        return
    voice.slide_count = (voice.slide_count - 1) & 0xFF
    if voice.slide_count:
        return
    voice.slide_count = voice.slide_speed
    limit = 0 if voice.slide_down else MAX_VOLUME
    if voice.volume == limit:
        voice.slide_speed = 0
        return
    voice.volume += -1 if voice.slide_down else 1
    voice.output.set_volume(voice.volume)


def HoldOrRelease(voice: Voice) -> None:
    """Each tick, unless held, queues the repeat part, or one empty word.
    Paula takes it when the playing part ends. Held, nothing is queued,
    so the part that plays loops: after a note, the one-shot part."""
    if voice.hold:
        return
    voice.output.queue(voice.repeat or EMPTY)


# --- Commands ----------------------------------------------------------


def RowCommands(module: Module) -> None:
    for voice in module.voices:
        RunCommand(module, voice)


def RunCommand(module: Module, voice: Voice) -> None:
    """A 256-byte table maps the command byte to a handler. Handlers
    take their argument from the byte itself: its distance from the
    first byte of the range. Unused bytes do nothing."""
    byte, voice.command = voice.command, 0
    for first, last, handler in COMMANDS:
        if first <= byte <= last:
            handler(module, voice, byte - first)
            return


def CmdFilterOff(module: Module, voice: Voice, arg: int) -> None:
    module.filter = False


def CmdFilterOn(module: Module, voice: Voice, arg: int) -> None:
    module.filter = True


def CmdVolume(module: Module, voice: Voice, arg: int) -> None:
    """Volume 0 to 63, at once. Ignored while a game fade runs."""
    if voice.locked:
        return
    voice.volume = arg
    voice.output.set_volume(arg)


def CmdStop(module: Module, voice: Voice, arg: int) -> None:
    """DMA off."""
    voice.output.disable()


def CmdWait(module: Module, voice: Voice, arg: int) -> None:
    """The row lasts 1 to 50 rows. A running wait is kept."""
    track = voice.track
    assert track is not None
    if not track.wait:
        track.wait = arg + 1


def CmdSlideUp(module: Module, voice: Voice, arg: int) -> None:
    """One step every 1 to 10 ticks."""
    voice.slide_down = False
    voice.slide_speed = voice.slide_count = arg + 1


def CmdSlideDown(module: Module, voice: Voice, arg: int) -> None:
    voice.slide_down = True
    voice.slide_speed = voice.slide_count = arg + 1


def CmdSetFlag(module: Module, voice: Voice, arg: int) -> None:
    """Sets game flag 0 to 19."""
    module.flags[arg] = True


def CmdHold(module: Module, voice: Voice, arg: int) -> None:
    voice.hold = True


def CmdRelease(module: Module, voice: Voice, arg: int) -> None:
    """The repeat part follows when the playing part ends."""
    voice.hold = False


def CmdClearFlags(module: Module, voice: Voice, arg: int) -> None:
    module.flags = [False] * GAME_FLAGS


def CmdRepeatStart(module: Module, voice: Voice, arg: int) -> None:
    """1 to 10 repeats of the rows after this one. While a
    repeat is open, it does nothing: one level, no nesting."""
    track = voice.track
    assert track is not None
    if track.count == NO_REPEAT:
        track.mark, track.count = track.pos, arg + 1


def CmdRepeatEnd(module: Module, voice: Voice, arg: int) -> None:
    """Back to the row after the mark while repeats are left. With N
    repeats, the rows play N + 1 times."""
    track = voice.track
    assert track is not None
    if track.count == 0:
        track.count = NO_REPEAT
        return
    track.count -= 1
    track.pos = track.mark


def CmdStepBack(module: Module, voice: Voice, arg: int) -> None:
    """The row plays again at every row tick, until the game starts
    another song on the voice. Its note restarts each time."""
    track = voice.track
    assert track is not None
    track.pos -= ROW_SIZE


def CmdRestart(module: Module, voice: Voice, arg: int) -> None:
    """This voice goes back to its first row; the others play on."""
    track = voice.track
    assert track is not None
    track.pos = track.start


def CmdVolModOn(module: Module, voice: Voice, arg: int) -> None:
    """Channel 0, 1 or 2 sets the next channel's volume. Any
    voice's row can link any pair."""
    set_attach(module, arg, paula.Attach.VOLUME, True)


def CmdPerModOn(module: Module, voice: Voice, arg: int) -> None:
    """Channel 0, 1 or 2 sets the next channel's period."""
    set_attach(module, arg, paula.Attach.PERIOD, True)


def CmdClearFlag(module: Module, voice: Voice, arg: int) -> None:
    """Clears game flag 0 to 19."""
    module.flags[arg] = False


def CmdVolModOff(module: Module, voice: Voice, arg: int) -> None:
    set_attach(module, arg, paula.Attach.VOLUME, False)


def CmdPerModOff(module: Module, voice: Voice, arg: int) -> None:
    """Channel 0 or 1. For channel 2, see CmdPerModOff2."""
    set_attach(module, arg, paula.Attach.PERIOD, False)


def CmdPerModOff2(module: Module, voice: Voice, arg: int) -> None:
    """Ends period modulation from channel 2. No command byte reaches
    it: $fe does nothing. Once on, it stays on until the game resets
    ADKCON."""
    set_attach(module, 2, paula.Attach.PERIOD, False)


COMMANDS = (  # CommandTable, as byte ranges
    (0x01, 0x01, CmdFilterOff),
    (0x02, 0x02, CmdFilterOn),
    (0x03, 0x42, CmdVolume),
    (0x43, 0x43, CmdStop),
    (0x57, 0x88, CmdWait),
    (0xA7, 0xB0, CmdSlideUp),
    (0xB1, 0xBA, CmdSlideDown),
    (0xBB, 0xCE, CmdSetFlag),
    (0xCF, 0xCF, CmdHold),
    (0xD0, 0xD0, CmdRelease),
    (0xD1, 0xD1, CmdClearFlags),
    (0xD2, 0xDB, CmdRepeatStart),
    (0xDC, 0xDC, CmdRepeatEnd),
    (0xDD, 0xDD, CmdStepBack),
    (0xDE, 0xDE, CmdRestart),
    (0xDF, 0xE1, CmdVolModOn),
    (0xE2, 0xE4, CmdPerModOn),
    (0xE5, 0xF8, CmdClearFlag),
    (0xF9, 0xFB, CmdVolModOff),
    (0xFC, 0xFD, CmdPerModOff),
)


# --- The game's side ---------------------------------------------------


def GameFade(module: Module, mask: int, speed: int) -> None:
    """Slides the voices in the mask down, one step every `speed`
    ticks. Until a song takes the voice again, volume commands do
    nothing; a slide command can still turn the fade around."""
    for n, voice in enumerate(module.voices):
        if mask >> n & 1:
            voice.slide_down = voice.locked = True
            voice.slide_speed = voice.slide_count = speed


def GameReadsFlag(module: Module, number: int) -> bool:
    """Flags 1 to 20 in the game's numbering; commands count from 0."""
    return module.flags[number - 1]


# --- Helpers -----------------------------------------------------------


def set_attach(module: Module, channel: int, mode: paula.Attach, on: bool) -> None:
    """One ADKCON bit; the others stay."""
    if on:
        module.attach[channel] |= mode
    else:
        module.attach[channel] &= ~mode
    module.amiga.paula.adkcon(module.attach)
