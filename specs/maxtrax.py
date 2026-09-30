"""MaxTrax, the Music-X playback driver: max.asm and shared.asm.

Card: players/MaxTrax.md. Level 2: the control flow runs. Each CamelCase
function is a new name in data/annot/MaxTrax.yaml (max.asm) or
data/annot/MaxTrax-shared.yaml (shared.asm); each CamelCase class is in
their `types:`. This build has no modulation and no microtonal tuning.

The score is one MIDI-like event list for 16 MIDI channels. The driver
picks one of 4 voices per note and plays it through audio.device. Each
frame, it reads the events that are due, counts down note lengths and
runs the volume envelopes.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from hardware import paula
from hardware.amiga import Amiga
from hardware.clock import FRAME_CCK, LINE_CCK

VOICES, CHANNELS = 4, 16
XCHANNEL = 16  # the game's notes play on this extra channel
PATCH_MASK = 63
REPEATS = 4  # nesting depth
PPQ = 192  # pulses per quarter note
NO_BEND = 64 << 7
MAX_BEND_RANGE = 24
K_VALUE = 0x09FD77  # log2 period of MIDI note 45, in 16.16
PREF_PERIOD = 0x08FD77  # above this, take the next sample, an octave lower
PERIOD_LIMIT = 0x06F73D  # below this, the period is too short: silence
ERROR_PERIOD = 1000
BEAM_LIMIT = 128  # past this display line, events wait for the next frame
FULL = 128  # note and envelope volume that is not scaled
MAX_VOLUME = 64

# voice_Status: a lower value is freer
ENV_FREE, ENV_HALT, ENV_DECAY, ENV_RELEASE = 0, 1, 2, 3
ENV_SUSTAIN, ENV_ATTACK, ENV_START = 4, 5, 6
PRI_SCORE, PRI_NOTE, PRI_SOUND = 0, 1, 2
LEFT_0, RIGHT_0 = 0, 1  # voices 0 and 3 are left, 1 and 2 right
MUST_HAVE_SIDE = 0x08
SOUND_RIGHT_SIDE, SOUND_STEREO, SOUND_LOOP = 0x02, 0x03, 0x04

NOTE_OFF = 0xFF  # a free stop event
NO_NOTE = 0xFF  # a channel's last note: none; bit 7 marks it
TEMPO, SPECIAL, CONTROL, PROGRAM, BEND, END = 0x80, 0xA0, 0xB0, 0xC0, 0xE0, 0xFF
MARK, SYNC, BEGIN_REPEAT, END_REPEAT = 0, 1, 2, 3

ALOG = (  # alogtable: 65536 × (2^(i/256) - 1), and a closing 0
    *(0, 178, 356, 535, 714, 893, 1073, 1254, 1435, 1617, 1799, 1981),
    *(2164, 2348, 2532, 2716, 2902, 3087, 3273, 3460, 3647, 3834, 4022),
    *(4211, 4400, 4590, 4780, 4971, 5162, 5353, 5546, 5738, 5932, 6125),
    *(6320, 6514, 6710, 6906, 7102, 7299, 7496, 7694, 7893, 8092, 8292),
    *(8492, 8693, 8894, 9096, 9298, 9501, 9704, 9908, 10113, 10318, 10524),
    *(10730, 10937, 11144, 11352, 11560, 11769, 11979, 12189, 12400, 12611),
    *(12823, 13036, 13249, 13462, 13676, 13891, 14106, 14322, 14539, 14756),
    *(14974, 15192, 15411, 15630, 15850, 16071, 16292, 16514, 16737, 16960),
    *(17183, 17408, 17633, 17858, 18084, 18311, 18538, 18766, 18995, 19224),
    *(19454, 19684, 19915, 20147, 20379, 20612, 20846, 21080, 21315, 21550),
    *(21786, 22023, 22260, 22498, 22737, 22977, 23216, 23457, 23698, 23940),
    *(24183, 24426, 24670, 24915, 25160, 25406, 25652, 25900, 26148, 26396),
    *(26645, 26895, 27146, 27397, 27649, 27902, 28155, 28409, 28664, 28919),
    *(29175, 29432, 29690, 29948, 30207, 30466, 30727, 30988, 31249, 31512),
    *(31775, 32039, 32303, 32568, 32834, 33101, 33369, 33637, 33906, 34175),
    *(34446, 34717, 34988, 35261, 35534, 35808, 36083, 36359, 36635, 36912),
    *(37190, 37468, 37747, 38028, 38308, 38590, 38872, 39155, 39439, 39724),
    *(40009, 40295, 40582, 40870, 41158, 41448, 41738, 42029, 42320, 42613),
    *(42906, 43200, 43495, 43790, 44087, 44384, 44682, 44981, 45280, 45581),
    *(45882, 46184, 46487, 46791, 47095, 47401, 47707, 48014, 48322, 48631),
    *(48940, 49251, 49562, 49874, 50187, 50500, 50815, 51131, 51447, 51764),
    *(52082, 52401, 52721, 53041, 53363, 53685, 54008, 54333, 54658, 54983),
    *(55310, 55638, 55966, 56296, 56626, 56957, 57289, 57622, 57956, 58291),
    *(58627, 58964, 59301, 59640, 59979, 60319, 60661, 61003, 61346, 61690),
    *(62035, 62381, 62727, 63075, 63424, 63774, 64124, 64476, 64828, 65182),
    0,
)


# --- What the composer edits -------------------------------------------


@dataclass
class Event:  # CookedEvent, 6 bytes
    command: int  # $00-$7f: a note number
    data: int  # low nibble: MIDI channel; a note's high nibble: velocity / 16
    start: int  # pulses since the previous event
    stop: int  # a note's length in pulses; other events keep data here


@dataclass
class Segment:  # EnvelopeData
    duration: int  # ms
    volume: int  # 8.8: $8000 is full


@dataclass
class Sample:  # SampleData: one octave
    attack: bytes  # played once
    sustain: bytes  # looped
    next: "Sample | None" = None  # the same sound an octave lower, twice as long


@dataclass
class Patch:  # PatchData
    sample: Sample | None = None
    attack: list[Segment] = field(default_factory=list)
    release: list[Segment] = field(default_factory=list)
    volume: int = 0  # the sustain volume without an attack envelope
    tune: int = 0  # 1/24 semitones


# --- audio.device, summarized ------------------------------------------


@dataclass
class Request:
    data: bytes
    cycles: int  # 0: forever
    period: int | None = None  # ADIOF_PERVOL: set with the request
    volume: int = 0


@dataclass
class AudioDevice:
    """A summary of audio.device for one unit, not replay code. CMD_WRITE
    queues a request; the device writes the next one's registers at the
    audio interrupt, so requests follow without a gap. After the last,
    DMA goes off. ADCMD_PERVOL sets period and volume at once."""

    channel: paula.Channel
    queue: list[Request] = field(default_factory=list)
    playing: Request | None = None
    passes: int = 0

    def write(self, request: Request) -> None:
        self.queue.append(request)
        if self.playing is None:
            self.start_next()

    def start_next(self) -> None:
        self.playing = self.queue.pop(0) if self.queue else None
        if self.playing is None:
            self.channel.disable()
            return
        if self.playing.period is not None:
            self.pervol(self.playing.period, self.playing.volume)
        self.passes = 0
        self.channel.on_irq(lambda c: self.interrupt())
        self.channel.play(paula.Sample(self.playing.data))

    def interrupt(self) -> None:
        """A pass begins. Before the request's last pass, the next one's
        registers go in, so it follows at once."""
        request = self.playing
        if request is None:
            return
        self.passes += 1
        if request.cycles and self.passes >= request.cycles:
            self.playing = self.queue.pop(0) if self.queue else None
            if self.playing is None:
                self.channel.queue(paula.Sample(bytes(2)))
                self.channel.disable()
                return
            self.passes = 0
            self.channel.queue(paula.Sample(self.playing.data))

    def pervol(self, period: int, volume: int) -> None:
        self.channel.period = period
        self.channel.set_volume(volume)

    def flush(self) -> None:
        self.queue.clear()
        self.playing = None
        self.channel.disable()


# --- Replay state -------------------------------------------------------


@dataclass
class Channel:  # ChannelData: a MIDI channel
    number: int
    patch: Patch = field(default_factory=Patch)
    rpn: int = 0
    porta_time: int = 500  # ms
    bend: int = NO_BEND  # 14 bits
    real_bend: int = 0  # 1/256 semitones
    bend_range: int = MAX_BEND_RANGE
    volume: int = FULL  # scales new notes only
    voices_active: int = 0
    right: bool = False  # CHAN_PAN: picks a side, not a level
    mono: bool = False
    portamento: bool = False
    damper: bool = False
    altered: bool = False  # recalculate pitch and volume this frame
    last_note: int = NO_NOTE


@dataclass
class Envelope:  # voice_Envelope, TicksLeft, EnvelopeLeft
    segments: list[Segment] = field(default_factory=list)
    index: int = 0
    left: int = 0  # segments
    ticks_left: int = 0  # ms × 256
    increment: int = 0  # volume per frame, 8.8


@dataclass
class StopEvent:  # glob_NoteOff: one per voice
    note: int = NOTE_OFF
    channel: int = 0
    time: int = 0  # pulses × 256, or ms × 256 on the extra channel


@dataclass
class Voice:  # VoiceData
    number: int
    device: AudioDevice
    channel: Channel | None = None  # None: free
    patch: Patch = field(default_factory=Patch)
    status: int = ENV_FREE
    envelope: Envelope = field(default_factory=Envelope)
    base_note: int = 0
    end_note: int = 0  # portamento's target
    porta_ticks: int = 0  # ms × 256
    note_volume: int = FULL
    base_volume: int = 0  # 8.8, from the envelope
    last_period: int = 0  # 0: out of range
    period_offset: int = 0  # octaves of sample shift, 16.16
    priority: int = PRI_SCORE
    stolen: bool = False
    porta: bool = False
    damper: bool = False
    blocked: bool = False  # a game sound plays here
    recalc: bool = False  # keep the sample; only the period changes
    unique_id: int = 0
    link: int = 0  # a stereo sound's other voice; its own number if none
    last_volume: int = 0


@dataclass
class Module:  # _globaldata, _voice, _channel, _xchannel, _patch
    amiga: Amiga
    scores: list[list[Event]]
    patches: list[Patch]
    frequency: int = 50  # VBlankFrequency
    voices: list[Voice] = field(default_factory=list)
    channels: list[Channel] = field(default_factory=list)  # 16, then the extra
    stops: list[StopEvent] = field(default_factory=list)
    score: int = 0
    current: int = 0  # the next event
    ticks: int = 0  # pulses × 256
    current_time: int = 0  # pulses: the last event's time
    tick_unit: int = 0  # pulses × 256 per frame
    frame_unit: int = 0  # ms × 256 per frame
    tempo: int = 120  # the score's start tempo
    current_tempo: int = 0  # BPM × 16
    start_tempo: int = 0
    delta_tempo: int = 0
    tempo_time: int = 0  # a slide's length, pulses × 256; 0: none
    tempo_ticks: int = 0
    repeat_points: list[int] = field(default_factory=lambda: [0] * REPEATS)
    repeat_counts: list[int] = field(default_factory=lambda: [0] * REPEATS)
    repeat_total: int = 0
    volume: int = MAX_VOLUME  # set by the game
    velocity: bool = False  # MUSIC_VELOCITY: notes use their velocity
    playing: bool = False
    loop: bool = False
    added_note: bool = False
    last_voice: int = 0
    unique_id: int = 0
    rounds: dict[str, int] = field(default_factory=lambda: {"right": 0, "left": 0})
    sync: Callable[[int], None] | None = None  # the game's task


def new_module(scores: list[list[Event]], patches: list[Patch], amiga: Amiga) -> Module:
    """InitMusicTagList: FrameUnit = 1000 ms / frequency, × 256. The
    vertical blank causes a software interrupt that runs MusicServer."""
    module = Module(amiga, scores, patches)
    module.frame_unit = (1000 << 8) // module.frequency
    module.voices = [
        Voice(n, AudioDevice(c), link=n) for n, c in enumerate(amiga.paula.channels)
    ]
    module.stops = [StopEvent() for _ in range(VOICES)]
    OpenMusic(module)
    amiga.vblank.handler = lambda: MusicServer(module)
    return module


def OpenMusic(module: Module) -> None:
    """Channel n starts with patch n. Even channels start on the left."""
    module.channels = [Channel(n, module.patches[n]) for n in range(CHANNELS + 1)]
    for channel in module.channels:
        ResetChannel(channel)


def PlaySong(module: Module, mark: int) -> None:
    """Stops every voice, starts the score at a mark, with the score's
    start tempo."""
    SystemReset(module)
    module.current = 0
    SkipMarks(module, mark)
    for stop in module.stops:
        stop.note = NOTE_OFF
    SetTempo(module, module.tempo << 4)
    module.repeat_total = 0
    module.current_time = module.tempo_time = module.ticks = 0
    module.playing = True


def SkipMarks(module: Module, count: int) -> None:
    """Moves past `count` mark events; the end wraps."""
    events = module.scores[module.score]
    start = scan = module.current
    for _ in range(count):
        while True:
            event = events[scan]
            if event.command == END:
                start = scan = 0
                continue
            scan += 1
            if event.command == SPECIAL and event.stop >> 8 == MARK:
                start = scan
                break
    module.current = start


def AdvanceSong(module: Module, count: int) -> bool:
    """A game call while the score plays. The clocks run on, so the
    next event waits its start delta after the last one read."""
    if not module.playing:
        return False
    SkipMarks(module, count)
    return True


def SystemReset(module: Module) -> None:
    for voice in module.voices:
        if voice.channel is not None:
            KillVoice(module, voice)


def SetTempo(module: Module, tempo: int) -> None:
    """TickUnit = (tempo >> 4) × 192 × 256 / (60 × frequency): pulses per
    frame, × 256. `tempo` is BPM × 16."""
    module.current_tempo = tempo
    module.tick_unit = ((tempo & 0xFFFF) >> 4) * (PPQ << 8) // (60 * module.frequency)


# --- Frame -------------------------------------------------------------


def beam_line(module: Module) -> int:
    return module.amiga.now % FRAME_CCK // LINE_CCK


def MusicServer(module: Module) -> None:
    """Once per frame: note lengths, the due events, a tempo slide, then
    the envelopes. The game's volume and velocity flag are copied first
    when it changes them (not modelled)."""
    ScoreClock(module)
    if module.playing:
        ReadEvents(module)
        ContinueTempo(module)
    EnvelopeManager(module, module.frame_unit)
    for voice in module.voices:
        if voice.channel is None and voice.blocked:
            SoundPlaying(module, voice)


def ScoreClock(module: Module) -> None:
    """The clock gains TickUnit. Then each voice's stop event counts
    down: in pulses, or in ms for the game's notes."""
    module.ticks += module.tick_unit
    for n, (voice, stop) in enumerate(zip(module.voices, module.stops)):
        module.last_voice = n
        if voice.channel is None or stop.note & 0x80:
            continue
        StopCountdown(module, stop)


def StopCountdown(module: Module, stop: StopEvent) -> None:
    """At 0, a note-off for the voice. NoteOff checks the voice's note."""
    extra = stop.channel == XCHANNEL
    stop.time -= module.frame_unit if extra else module.tick_unit
    if stop.time > 0:
        return
    NoteOff(module, module.channels[stop.channel], stop.note)
    stop.note = NOTE_OFF


def ReadEvents(module: Module) -> None:
    """Events whose time has come, in order. Past display line 128, the
    rest wait for the next frame. The model's CPU takes no time, so it
    never gets there."""
    events = module.scores[module.score]
    pulses = module.ticks >> 8
    while True:
        if BeamBudget(module):
            return
        event = events[module.current]
        time = module.current_time + event.start
        if time > pulses:
            return
        module.current_time = time
        if not RunEvent(module, event):
            return
        module.current += 1


def BeamBudget(module: Module) -> bool:
    return beam_line(module) >= BEAM_LIMIT


def RunEvent(module: Module, event: Event) -> bool:
    """False: stop reading this frame; the event pointer is set.

    Below TEMPO: a note; data high nibble × 8 is its velocity, stop its
    length. TEMPO: data BPM, stop a slide length. SPECIAL: stop high
    byte the kind (MARK, SYNC, BEGIN_REPEAT, END_REPEAT), low byte a
    value. CONTROL: a CC; stop is number and value. PROGRAM: stop low
    byte. BEND: pitch bend; stop, 7 bits each. END: the end. $f0 sysex and $f8 clock are declared in driver.i but skipped.
    """
    channel = module.channels[event.data & 0x0F]
    if event.command < 0x80:
        module.added_note = False
        velocity = (event.data >> 1) & 0x78
        NoteOn(module, channel, event.command, velocity, PRI_SCORE)
        if module.added_note:
            SetStopEvent(module, event)
    elif event.command == TEMPO:
        TempoSlide(module, event)
    elif event.command == END:
        return ScoreEnd(module)
    elif event.command == BEND:
        PitchBend(channel, event.stop & 0x7F, (event.stop >> 8) & 0x7F)
    elif event.command == CONTROL:
        ControlCh(module, channel, event.stop >> 8, event.stop & 0xFF)
    elif event.command == PROGRAM:
        ProgramCh(module, channel, event.stop & 0xFF)
    elif event.command == SPECIAL:
        kind, value = event.stop >> 8, event.stop & 0xFF
        if kind == SYNC:
            SyncEvent(module, value)
        elif kind == BEGIN_REPEAT:
            BeginRepeat(module, value)
        elif kind == END_REPEAT:
            return EndRepeat(module)
    return True


def SetStopEvent(module: Module, event: Event) -> None:
    """The note's length becomes the stop event of its voice, relative to
    now. A voice has one: a new note replaces the old one's."""
    stop = module.stops[module.last_voice]
    stop.note, stop.channel = event.command, event.data & 0x0F
    stop.time = (event.stop + module.current_time - (module.ticks >> 8)) << 8


def TempoSlide(module: Module, event: Event) -> None:
    """A length under one frame's pulses sets the tempo at once. Else the
    tempo moves linearly to the target over the length."""
    target = event.data << 4
    if module.tick_unit >> 8 >= event.stop:
        SetTempo(module, target)
        module.tempo_time = 0
        return
    module.start_tempo = module.current_tempo
    module.delta_tempo = (target - module.current_tempo) & 0xFFFF
    module.tempo_time = event.stop << 8
    module.tempo_ticks = 0


def ContinueTempo(module: Module) -> None:
    """Tempo = start + delta × elapsed / length. The delta is read as an
    unsigned word, so a slide to a slower tempo overshoots high until
    its end: a bug."""
    if not module.tempo_time:
        return
    module.tempo_ticks += module.tick_unit
    if module.tempo_ticks >= module.tempo_time:
        SetTempo(module, (module.start_tempo + module.delta_tempo) & 0xFFFF)
        module.tempo_time = 0
        return
    delta = module.delta_tempo & 0xFFFF
    step = delta * module.tempo_ticks // module.tempo_time
    SetTempo(module, (module.start_tempo + step) & 0xFFFF)


def ScoreEnd(module: Module) -> bool:
    """With looping, back to the start with the clocks at 0; else the
    music stops. Either way, no more events this frame."""
    if module.loop:
        module.current = 0
        module.ticks = module.current_time = 0
    else:
        module.playing = False
    return False


def SyncEvent(module: Module, value: int) -> None:
    """Signals the game's task with a value."""
    if module.sync is not None:
        module.sync(value)


def BeginRepeat(module: Module, count: int) -> None:
    """Plays the section count + 1 times. A fifth level is ignored."""
    if module.repeat_total == REPEATS:
        return
    level = module.repeat_total
    module.repeat_total += 1
    module.repeat_counts[level] = count
    module.repeat_points[level] = module.current + 1


def EndRepeat(module: Module) -> bool:
    """A jump back resets the clocks and ends this frame's events."""
    if not module.repeat_total:
        return True
    level = module.repeat_total - 1
    if module.repeat_counts[level] == 0:
        module.repeat_total = level
        return True
    module.repeat_counts[level] -= 1
    module.current = module.repeat_points[level]
    module.ticks = module.current_time = 0
    return False


# --- Channel messages ---------------------------------------------------


def ProgramCh(module: Module, channel: Channel, program: int) -> None:
    channel.patch = module.patches[program & PATCH_MASK]


def PitchBend(channel: Channel, low: int, high: int) -> None:
    """RealBend = (bend - center) × range × 256 / center: 1/256
    semitones."""
    channel.bend = (high << 7) + low
    offset = channel.bend - NO_BEND
    channel.real_bend = int(offset * (channel.bend_range << 8) / NO_BEND)
    channel.altered = True


def ResetChannel(channel: Channel) -> None:
    channel.porta_time = 500
    channel.bend, channel.real_bend = NO_BEND, 0
    channel.bend_range, channel.volume = MAX_BEND_RANGE, FULL
    channel.right = bool(channel.number & 1)
    channel.portamento = False
    channel.altered = True


def ControlCh(module: Module, channel: Channel, number: int, value: int) -> None:
    """5, 37: portamento time in ms, 7 bits each. 6: data entry, the
    bend range for RPN 0, at most 24. 7: channel volume, for new notes
    only. 10: pan, a side. 64: damper pedal. 65: portamento; only mono
    mode glides. 81: audio filter (not modelled). 100, 101: RPN. 120:
    all sound off. 121: reset. 123: all notes off. 126, 127: mono or
    poly, after all notes off."""
    if number == 5:
        channel.porta_time = value << 7
    elif number == 5 + 32:
        channel.porta_time = (channel.porta_time & 0x3F80) | value
    elif number == 6:
        if channel.rpn:
            return
        channel.bend_range = min(value, MAX_BEND_RANGE)
        offset = channel.bend - NO_BEND
        if offset:
            range_bend(channel, offset)
    elif number == 7:
        channel.volume = value + 1 if value else 0
    elif number == 10:
        PanSide(channel, value)
    elif number == 64:
        DamperPedal(module, channel, value)
    elif number == 65:
        channel.portamento = bool(value & 0x40)
        if not channel.portamento:
            PortaOffBug(channel)
    elif number in (100, 101):
        RpnSelect(channel, number, value)
    elif number == 121:
        ResetChannel(channel)
    elif number == 123:
        AllNotesOff(module, channel)
    elif number in (126, 127):
        channel.mono = number == 126
        AllNotesOff(module, channel)
    elif number == 120:
        AllSoundsOff(module, channel)


def range_bend(channel: Channel, offset: int) -> None:
    """A new range recomputes the bend with unsigned math: below the
    center, the wheel then bends up, not down. A bug."""
    unsigned = (offset & 0xFFFF) * channel.bend_range << 8
    value = unsigned // NO_BEND & 0xFFFF
    channel.real_bend = value - 0x10000 if value & 0x8000 else value
    channel.altered = True


def PanSide(channel: Channel, value: int) -> None:
    """Below 64: the right side, though the source comment says left.
    At 64: by channel number."""
    if value < 64 or (value == 64 and not channel.number & 1):
        channel.right = True
    else:
        channel.right = False


def DamperPedal(module: Module, channel: Channel, value: int) -> None:
    """Down: note-offs mark the voice. Up: marked voices release."""
    channel.damper = bool(value & 0x40)
    if channel.damper:
        return
    for voice in module.voices:
        if voice.channel is channel and voice.damper:
            voice.damper = False
            voice.status = ENV_RELEASE


def PortaOffBug(channel: Channel) -> None:
    """Should forget the last note. The code writes NO_NOTE through a2, which
    in MusicServer points into the score: the channel keeps its last
    note, and a score byte is overwritten (not modelled)."""


def RpnSelect(channel: Channel, number: int, value: int) -> None:
    if number == 100:
        channel.rpn = (channel.rpn & 0xFF00) | value
    else:
        channel.rpn = (channel.rpn & 0x00FF) | value << 8


# --- Notes ---------------------------------------------------------------


def NoteOn(
    module: Module, channel: Channel, note: int, velocity: int, priority: int
) -> None:
    """Velocity 0 is ignored: only lengths end notes. In mono mode, a
    held voice glides with portamento, or restarts without it."""
    if velocity == 0 or channel.patch.sample is None:
        return
    voice: Voice | None
    if channel.mono and channel.voices_active:
        voice = next((v for v in module.voices if v.channel is channel), None)
        if voice is None:
            return
        if voice.status >= ENV_SUSTAIN and channel.portamento:
            MonoLegato(module, channel, voice, note, velocity)
            return
    else:
        side = RIGHT_0 if channel.right else LEFT_0
        voice = PickVoice(module, side, priority)
        if voice is None:
            return
    StealVoice(module, channel, voice, note, velocity, priority)


def MonoLegato(
    module: Module, channel: Channel, voice: Voice, note: int, velocity: int
) -> None:
    """The voice glides to the new note; no new sample. A glide still
    running jumps to its target first."""
    voice.porta_ticks = 0
    if voice.porta:
        voice.base_note = voice.end_note
    voice.porta = True
    voice.end_note = channel.last_note = note
    voice.note_volume = velocity + 1 if module.velocity else FULL
    module.added_note = True
    module.last_voice = voice.number


def StealVoice(
    module: Module,
    channel: Channel,
    voice: Voice,
    note: int,
    velocity: int,
    priority: int,
) -> None:
    """A busy voice is cut off at once, even mid-note."""
    stolen = voice.channel is not None
    if stolen:
        KillVoice(module, voice)
    voice.stolen, voice.porta, voice.damper = stolen, False, False
    voice.blocked = voice.recalc = False
    voice.channel, voice.patch, voice.base_note = channel, channel.patch, note
    sample = CalcNote(voice)
    voice.priority, voice.status = priority, ENV_START
    volume = velocity + 1 if module.velocity else FULL
    if channel.volume < FULL:
        volume = volume * channel.volume >> 7
    voice.note_volume, voice.base_volume = volume, 0
    period = voice.last_period or ERROR_PERIOD
    QueueAttack(voice, sample, period)
    channel.voices_active += 1
    if channel.number != XCHANNEL:
        if (
            channel.mono
            and channel.portamento
            and not channel.last_note & 0x80
            and channel.last_note != voice.base_note
        ):
            voice.porta_ticks = 0
            voice.end_note, voice.base_note = voice.base_note, channel.last_note
            voice.porta = True
        if channel.portamento:
            channel.last_note = note
    module.added_note = True
    module.last_voice = voice.number


def QueueAttack(voice: Voice, sample: Sample, period: int) -> None:
    """Two requests: the attack part once, then the sustain part looped
    by audio.device. The first carries the period, at volume 0; the
    envelope sets the volume later this frame. On Kickstart 2, after
    each request, the driver waits a line and 140 polls and sets the DMA
    bit again, in case the device missed it (not modelled)."""
    if sample.attack:
        voice.device.write(Request(sample.attack, 1, period, 0))
    QueueSustain(voice, sample, period)


def QueueSustain(voice: Voice, sample: Sample, period: int) -> None:
    if not sample.sustain:
        return
    first = None if sample.attack else period
    voice.device.write(Request(sample.sustain, 0, first, 0))


def NoteOff(module: Module, channel: Channel, note: int) -> None:
    """Releases the voice that the stop event belongs to, if it still
    plays this note: its end note while gliding. With the damper pedal
    down, the voice is only marked."""
    voice = module.voices[module.last_voice]
    if not channel.voices_active or voice.channel is not channel:
        return
    if voice.status <= ENV_RELEASE:
        return
    if note != (voice.end_note if voice.porta else voice.base_note):
        return
    if channel.damper:
        voice.damper = True
    else:
        voice.status = ENV_RELEASE


def AllNotesOff(module: Module, channel: Channel) -> None:
    for voice in module.voices:
        if voice.channel is channel:
            if channel.damper:
                voice.damper = True
            else:
                voice.status = ENV_RELEASE


def AllSoundsOff(module: Module, channel: Channel) -> None:
    for voice in module.voices:
        if voice.channel is channel:
            KillVoice(module, voice)


def KillVoice(module: Module, voice: Voice) -> None:
    assert voice.channel is not None
    voice.channel.voices_active -= 1
    voice.channel = None
    voice.status, voice.priority, voice.unique_id = ENV_FREE, PRI_SCORE, 0
    voice.stolen = voice.porta = voice.damper = voice.blocked = voice.recalc = False
    StopAudio(voice)


def StopAudio(voice: Voice) -> None:
    """StopAudio: CMD_FLUSH on the unit. Before Kickstart 2, the driver
    also writes period 1 to the channel to flush it."""
    voice.device.flush()


# --- Voice allocation ---------------------------------------------------


def status_of(module: Module, number: int) -> int:
    return module.voices[number].status


def PickVoice(module: Module, side: int, priority: int) -> Voice | None:
    """The side's freer voice first, or the other side's if
    ours has no free or releasing voice and it has one. A voice that a
    game sound blocks, or with a higher priority, is skipped: then the
    sibling, then the other side. MUST_HAVE_SIDE keeps the side first."""
    must = priority & MUST_HAVE_SIDE
    priority &= ~MUST_HAVE_SIDE
    number = side
    if not must:
        other = number ^ 1
        near = min(status_of(module, number), status_of(module, number ^ 3))
        far = min(status_of(module, other), status_of(module, other ^ 3))
        if near > ENV_RELEASE and far <= ENV_RELEASE:
            number = other

    def usable(n: int) -> bool:
        voice = module.voices[n]
        return not voice.blocked and voice.priority <= priority

    number, round_key = PickSibling(module, number)
    if not usable(number):
        number ^= 3
        if not usable(number):
            number, round_key = PickSibling(module, number ^ 1)
            if not usable(number):
                number ^= 3
                if not usable(number):
                    return None
    module.rounds[round_key] = number & 2
    return module.voices[number]


def PickSibling(module: Module, number: int) -> tuple[int, str]:
    """Of two voices on one side, the lower status wins. A
    tie goes by the side's round-robin value."""
    key = "left" if (number - 1) & 2 else "right"
    difference = status_of(module, number) - status_of(module, number ^ 3)
    if difference < 0:
        return number, key
    if difference > 0 or number & 2 == module.rounds[key]:
        return number ^ 3, key
    return number, key


# --- Pitch --------------------------------------------------------------


def CalcNote(voice: Voice) -> Sample:
    """Pitch adds up in 1/256 semitones: note, bend, portamento and the
    patch's tuning. It becomes a log2 period, then the period. A new note
    takes the patch's sample an octave lower while the period would
    exceed PREF_PERIOD, about 508. A recalculation keeps the octave."""
    channel = voice.channel
    assert channel is not None
    voice.last_period = 0
    extra = 0
    if voice.porta:
        steps = voice.end_note - voice.base_note
        extra = int(steps * voice.porta_ticks / channel.porta_time)
    tone = channel.real_bend + extra + (voice.base_note << 8)
    tone += int((voice.patch.tune << 8) / 24)
    tone -= 45 << 8
    log_period = K_VALUE - (int(tone * 4 / 3) << 4)
    sample = voice.patch.sample
    assert sample is not None
    if voice.recalc:
        log_period -= voice.period_offset
    else:
        voice.period_offset = 0
        sample, log_period = OctaveShift(voice, sample, log_period)
    if log_period >= PERIOD_LIMIT:
        voice.last_period = IntAlg(log_period)
    return sample


def OctaveShift(voice: Voice, sample: Sample, log_period: int) -> tuple[Sample, int]:
    while log_period > PREF_PERIOD and sample.next is not None:
        sample = sample.next
        voice.period_offset += 0x10000
        log_period -= 0x10000
    return sample, log_period


def IntAlg(log_period: int) -> int:
    """2^(log_period / 65536), from a 256-entry table with linear
    interpolation. 0 if out of range."""
    exponent, fraction = log_period >> 16, log_period & 0xFFFF
    low, high = ALOG[fraction >> 8], ALOG[(fraction >> 8) + 1]
    weight = ((fraction << 8) & 0xFFFF) + 128
    mantissa = (low + (((high - low) & 0xFFFF) * weight >> 16)) & 0xFFFF
    value = 0x80000000 | mantissa << 15
    if not 0 <= exponent < 32:
        return 0
    shift = exponent ^ 31
    if shift == 0:
        return value
    return (value >> shift) + ((value >> (shift - 1)) & 1)


# --- Volume and envelopes ------------------------------------------------


def CalcVolume(module: Module, voice: Voice) -> int:
    """Game volume × note volume / 128 × envelope volume / 128, at most 64.
    Channel volume counts only at note start."""
    volume = module.volume
    if voice.note_volume < FULL:
        volume = volume * voice.note_volume >> 7
    envelope = voice.base_volume >> 8
    if envelope < FULL:
        volume = volume * envelope >> 7
    voice.last_volume = min(volume, MAX_VOLUME)
    return voice.last_volume


def IncrVolume(module: Module, delta: int, time: int) -> int:
    """The volume step per frame to cover `delta` in `time`
    ms. A segment shorter than a frame jumps."""
    if not time:
        return delta
    size = abs(delta) & 0xFFFF
    step = size * 1000 // (time * module.frequency)
    if step > size:
        return delta
    return -step if delta < 0 else step


def EnvelopeManager(module: Module, delta: int) -> None:
    """Every voice, then the channels' altered flags clear."""
    for voice in module.voices:
        DoOneVoice(module, voice, delta)
    for channel in module.channels:
        channel.altered = False


def start_segment(module: Module, voice: Voice, segments: list[Segment]) -> None:
    env = voice.envelope
    env.segments, env.index, env.left = segments, 0, len(segments)
    segment = segments[0]
    env.ticks_left = segment.duration << 8
    env.increment = IncrVolume(
        module, segment.volume - voice.base_volume, segment.duration
    )


def DoOneVoice(module: Module, voice: Voice, delta: int) -> None:
    """One frame of a voice. `delta` is ms × 256. A voice in sustain does
    nothing unless its channel changed or it glides. Otherwise it sends
    period and volume to audio.device."""
    channel = voice.channel
    if channel is None:
        return
    if voice.status == ENV_SUSTAIN:
        if not channel.altered and not voice.porta:
            return
    elif voice.status == ENV_HALT:
        KillVoice(module, voice)
        return
    else:
        if not EnvelopeStep(module, voice, delta):
            voice.device.pervol(voice.last_period or ERROR_PERIOD, 0)
            return
    volume = CalcVolume(module, voice)
    recalc = channel.altered
    if voice.porta:
        voice.porta_ticks += delta
        recalc = True
        if voice.porta_ticks >> 8 >= channel.porta_time:
            voice.porta = False
            voice.base_note = voice.end_note
    if recalc:
        voice.recalc = True
        CalcNote(voice)
    if voice.last_period:
        voice.device.pervol(voice.last_period, volume)
    else:
        voice.device.pervol(ERROR_PERIOD, 0)


def EnvelopeStep(module: Module, voice: Voice, delta: int) -> bool:
    """Start, release, then the running segment. False: the voice halts
    at volume 0."""
    patch = voice.patch
    if voice.status == ENV_START:
        if not patch.attack:
            voice.status, voice.base_volume = ENV_SUSTAIN, patch.volume
            return True
        voice.status = ENV_ATTACK
        start_segment(module, voice, patch.attack)
    elif voice.status == ENV_RELEASE:
        if not patch.release:
            voice.status = ENV_HALT
            return False
        voice.status = ENV_DECAY
        start_segment(module, voice, patch.release)
    if voice.status == ENV_SUSTAIN:
        return True
    env = voice.envelope
    if delta < env.ticks_left:
        EnvelopeRamp(voice, delta)
        return True
    voice.base_volume = env.segments[env.index].volume
    env.left -= 1
    if env.left == 0:
        if voice.status == ENV_DECAY:
            voice.status = ENV_HALT
            return False
        voice.status = ENV_SUSTAIN
        return True
    env.index += 1
    segment = env.segments[env.index]
    env.ticks_left = segment.duration << 8
    env.increment = IncrVolume(
        module, segment.volume - voice.base_volume, segment.duration
    )
    return True


def EnvelopeRamp(voice: Voice, delta: int) -> None:
    """The volume moves linearly to the segment's target, within 0..$8000."""
    env = voice.envelope
    voice.base_volume = min(max(voice.base_volume + env.increment, 0), 0x8000)
    env.ticks_left -= delta


# --- Game notes and sounds ---------------------------------------------


def ExtraNote(
    module: Module, note: int, patch: int, duration: int, volume: int, pan: int
) -> int:
    """PlayNote: a game note on the extra channel, priority 1. Its length
    is in ms. Returns the voice + 1, or 0."""
    channel = module.channels[XCHANNEL]
    channel.right, channel.mono, channel.portamento = bool(pan), False, False
    channel.patch = module.patches[patch]
    module.added_note = False
    NoteOn(module, channel, note & 0x7F, volume & 0xFF, PRI_NOTE)
    if not module.added_note:
        return 0
    stop = module.stops[module.last_voice]
    stop.note, stop.channel, stop.time = note & 0x7F, XCHANNEL, duration << 8
    return module.last_voice + 1


def ExtraSound(module: Module, data: bytes, volume: int, period: int, pan: int) -> int:
    """PlaySound: a raw sample, priority 2. It blocks its voice until it
    ends. A stereo sound takes a left and a right voice. Returns an id,
    or 0."""
    cycles = pan >> 8 if pan & SOUND_LOOP else 1
    side = RIGHT_0 if pan & SOUND_RIGHT_SIDE else LEFT_0
    priority = (pan & MUST_HAVE_SIDE) | PRI_SOUND
    first = PickVoice(module, side, priority)
    if first is None:
        return 0
    second = None
    if pan & SOUND_STEREO == SOUND_STEREO and not (first.number - 1) & 2:
        second = PickVoice(module, LEFT_0, priority)
        if second is not None and (second.number - 1) & 2:
            block(module, second, data, cycles, period, volume)
        else:
            second = None
    block(module, first, data, cycles, period, volume)
    first.link = second.number if second is not None else first.number
    if second is not None:
        second.link = second.number
    first.unique_id = module.unique_id | first.number | 1 << 31
    module.unique_id = (module.unique_id + 4) & ~3
    return first.unique_id


def block(
    module: Module, voice: Voice, data: bytes, cycles: int, period: int, volume: int
) -> None:
    if voice.channel is not None:
        KillVoice(module, voice)
    voice.blocked, voice.priority = True, PRI_SOUND
    voice.device.write(Request(data, cycles, period, volume))


def ExtraStop(module: Module, unique_id: int) -> None:
    """StopSound: by id; a stereo sound's linked voice stops too."""
    voice = module.voices[unique_id & 3]
    if voice.unique_id != unique_id:
        return
    for target in {voice, module.voices[voice.link]}:
        if target.blocked:
            StopAudio(target)
            target.status, target.priority, target.unique_id = ENV_FREE, PRI_SCORE, 0
            target.blocked = False


def SoundPlaying(module: Module, voice: Voice) -> bool:
    """A finished game sound unblocks its voice, and its
    stereo link."""
    if not voice.blocked:
        return False
    if voice.device.playing is not None:
        return True
    voice.blocked, voice.priority, voice.unique_id = False, PRI_SCORE, 0
    if voice.link != voice.number:
        SoundPlaying(module, module.voices[voice.link])
    return False
