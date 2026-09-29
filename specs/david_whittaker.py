"""David Whittaker's Amiga replay, from Xenon 2 Megablast (1989). The
replay ships inside the module; this model reads
data/module/DavidWhittaker/dw.ingame.

Card: players/DavidWhittaker.md. Level 2: the control flow runs. Each
CamelCase function is a LABEL in data/disasm/DavidWhittaker.cnf; each
CamelCase class is in the `types:` of data/annot/DavidWhittaker.yaml.

The module starts with seven stubs that save registers and call
InitSong, Play, StopSound, Resume, StartEffect, EndEffects and
StartFade. Code, tables, patterns and samples follow.

Each voice reads a position list of pattern offsets. A pattern is a
byte stream: length bytes, instrument bytes, list bytes and commands
come before a note. A note plays for the current length. Each note
restarts its volume list; the pitch list runs on across notes. A tempo
byte drops a share of the ticks.

The game starts sound effects on a channel of its choice. Music then
writes only a copy of its registers; when the effect ends, the copy
goes to Paula and the music note sounds on. A synthetic effect adds one
of two period steps, and plays one of two sample offsets, as two
rotating bit patterns choose.

Left out: the host's timer; DeliTracker calls Play once per tick.
"""

from dataclasses import dataclass, field

from hardware import paula
from hardware.amiga import DEFAULT_LATCH, Amiga

VOICES = 4
CLOCK = 3579545  # NTSC colour clock: the tune's dividend
TUNE_SHIFT = 10  # period = table × tune >> 10
SAMPLES = 20  # InitSamples
EFFECT_SAMPLES = 18  # InitEffectSamples
SONG_SIZE = 10
SAMPLE_SIZE = 12
EFFECT_SIZE = 24  # a synthetic effect's record
EFFECT_SAMPLE_SIZE = 16
EFFECT_SAMPLE_DATA = 0xFF1C  # InitEffectSamples: added to SampleData
EFFECT_VOICE_SIZE = 36
SILENT_WORDS = 32
FULL_VOLUME = 64  # MasterVolume at InitSong
NTSC_SKIP = 6  # with Ntsc set, every sixth tick is dropped
MIN_PERIOD = 124  # effects clamp to it; a sample effect's slide ends there
LIST_END = 0x80  # a pitch list byte with it: restart the list after it
HOLD = 0x80  # a volume list byte with it: stay on this value
NOTE_MAX = 0x7F
FIRST_LENGTH = 0xE0  # length bytes: 1 to 32 × Speed ticks
FIRST_SAMPLE = 0xB0  # instrument bytes: 48 samples
FIRST_VOLUME_LIST = 0xA0
FIRST_PITCH_LIST = 0x90
SLIDE_ON = 1 << 1  # Voice.flags

# Stream commands, by CommandTable
(NEXT_PATTERN, SLIDE, REST, HOLD_NOTE, SONG_END, TRANSPOSE, VIBRATO_ON,
 VIBRATO_OFF, VOICE_TRANSPOSE, POSITIONS, SPEED, FADE) = range(0x80, 0x8C)  # fmt: skip


# --- Player state ------------------------------------------------------


@dataclass
class Sample:  # Samples: 12 bytes each
    start: int = 0  # 0: bytes into the module
    loop: int = -1  # 4: bytes; <0: silence after one pass
    length: int = 0  # 8: words
    tune: int = 0  # 10: CLOCK / the sample's rate


@dataclass
class Shadow:  # Shadows: 12 bytes per channel; music writes here always
    start: int = 0  # 0
    length: int = 0  # 4
    period: int = 0  # 6
    volume: int = 0  # 8
    written: bool = False  # 10: music ran on this channel
    effect: bool = False  # 11: an effect owns the channel


@dataclass
class Voice:  # Voices: 48 bytes each
    channel: paula.Channel
    shadow: Shadow
    flags: int = 0  # 0
    vibrato_on: bool = False  # 1: non-zero
    vibrato_growing: bool = True  # 1, bit 7
    vibrato_adding: bool = True  # 1, bit 0
    note: int = 0  # 2
    transpose: int = 0  # 3
    pos: int = 0  # 4: the stream, bytes into the module
    positions: int = 0  # 8: the position list
    position: int = 2  # 10: bytes into it
    pitch_start: int = 0  # 12
    pitch_pos: int = 0  # 16
    slide_step: int = 0  # 20
    slide_delay: int = 0  # 21
    looped: bool = True  # 22: QueueLoop ran for this note
    sample: Sample = field(default_factory=Sample)  # 24
    length: int = 1  # 28: ticks per note
    ticks: int = 1  # 30
    slide: int = 0  # 32: the sum of slide steps
    volume_start: int = 0  # 34
    volume_pos: int = 0  # 38
    volume_speed: int = 0  # 42
    volume_ticks: int = 0  # 43
    vibrato_speed: int = 0  # 44
    vibrato_value: int = 0  # 45
    vibrato_depth: int = 0  # 46


@dataclass
class Effect:  # EffectVoices: 36 bytes per channel; the first 24 from SynthEffects
    step: int = 0  # 0: added to the period every tick
    reset_period: int = 0  # 2
    steps: tuple[int, int] = (0, 0)  # 4: bit 0 clear, then set; added each pattern step
    period: int = 0  # 8
    offsets: tuple[int, int] = (0, 0)  # 10: bit 0 clear, then set; into EffectWave
    reset_ticks: int = 0  # 14: 0: no reset
    step_ticks: int = 0  # 15: 0: no pattern steps
    step_pattern: int = 0  # 16: rotated right each step; bit 0 picks
    offset_pattern: int = 0  # 17: rotated right each tick; bit 0 picks
    duration: int = 0  # 18: ticks; 0: until the volume list ends
    volume_speed: int = 0  # 19
    volume_list: int = 0  # 20
    sample_effect: int = 0  # 21: 0: synthetic; else the sample effect
    length: int = 0  # 22: words
    reset_count: int = 0  # 24
    step_count: int = 0  # 25
    active: bool = False  # 26
    volume_count: int = 1  # 27
    volume_pos: int = 0  # 28
    slide_period: int = 0  # 34: a sample effect's period


@dataclass
class EffectSample:  # EffectSamples: 16 bytes each
    start: int = 0  # 0
    loop: int = -1  # 4
    length: int = 0  # 8: words
    period: int = 0  # 10
    duration: int = 0  # 12: ticks, from the length and the rate
    no_duration: bool = False  # 13: the slide or the loop ends it
    slide: int = 0  # 14: added to the period each tick


@dataclass
class Module:  # the module is the replay: code, tables, songs and samples
    amiga: Amiga
    data: bytearray
    # offsets of the labels in data/disasm/DavidWhittaker.cnf, for dw.ingame
    period_table: int = 0x6B8  # PeriodTable: from 8192 down, a word per note
    pitch_lists: int = 0x748  # PitchLists: a word offset per list
    default_pitch_list: int = 0x768  # DefaultPitchList
    samples_at: int = 0x79A  # Samples
    songs: int = 0x88A  # Songs
    effect_samples_at: int = 0x13B4  # EffectSamples
    synth_effects: int = 0x17F4  # SynthEffects
    effect_volume_lists: int = 0x1A20  # after EffectWave: a word offset per list
    volume_lists: int = 0x1ABE  # VolumeLists: a word offset per list
    sample_data: int = 0x1BE2  # SampleData
    voices: list[Voice] = field(default_factory=list)
    effects: list[Effect] = field(default_factory=list)
    samples: list[Sample] = field(default_factory=list)
    effect_samples: list[EffectSample] = field(default_factory=list)
    silent: int = 0  # SilentAddress: 64 zero bytes after the samples
    effect_wave: int = 0  # EffectWave: 64 bytes further
    speed: int = 1  # Speed: ticks per length unit
    master_volume: int = FULL_VOLUME  # MasterVolume
    tempo: int = 0  # Tempo: dropped ticks, in 256ths
    tempo_sum: int = 0  # TempoSum
    fade_speed: int = 0  # FadeSpeed: 0: no fade
    fade_ticks: int = 0
    song_ready: bool = False
    playing: bool = False  # Playing
    transpose: int = 0  # Transpose: for all voices
    ntsc: bool = False  # Ntsc: 0 in Xenon 2
    ntsc_ticks: int = NTSC_SKIP  # NtscTicks
    effect_channel: int = 0  # EffectChannel


# --- Start -------------------------------------------------------------


def new_module(module: Module, song: int) -> Module:
    """DeliTracker calls Play by its own timer."""
    module.voices = [Voice(c, Shadow()) for c in module.amiga.paula.channels]
    module.effects = [Effect() for _ in range(VOICES)]
    InitSong(module, song)
    module.amiga.timer.on_underflow = lambda: Play(module)
    module.amiga.timer.set_latch(DEFAULT_LATCH)
    return module


def InitSong(module: Module, song: int) -> None:
    """A song record: the speed, the tempo, then one position list per
    voice. dw.ingame holds one song."""
    StopSound(module)
    InitSamples(module)
    module.transpose = 0
    data = module.data
    record = module.songs + SONG_SIZE * song
    module.speed = signed_byte(data[record])
    module.tempo = data[record + 1]
    for n, voice in enumerate(module.voices):
        voice.ticks, voice.flags, voice.vibrato_on, voice.transpose = 1, 0, False, 0
        voice.looped = True
        voice.pitch_start = voice.pitch_pos = module.default_pitch_list
        voice.positions = word(data, record + 2 + 2 * n)
        voice.position = 2
        voice.pos = word(data, voice.positions)
    module.master_volume = FULL_VOLUME
    module.fade_speed = 0
    module.playing = module.song_ready = True


def InitSamples(module: Module) -> None:
    """Once: each sample has a long length and a word rate before its
    data. The tune turns the rate into a period factor; the loop comes
    from the table. Then four tunes get a fixed correction: Xenon 2's
    own detune (guess)."""
    if module.samples:
        return
    data = module.data
    at = module.sample_data
    for n in range(SAMPLES):
        size, rate = long(data, at), word(data, at + 4)
        loop = signed_long(long(data, module.samples_at + SAMPLE_SIZE * n + 4))
        module.samples.append(Sample(at + 6, loop, size >> 1, CLOCK // rate))
        at += 6 + size
    module.silent = at
    module.effect_wave = at + 64
    for n, amount in ((11, 2), (5, 8), (6, 8), (7, 2)):
        module.samples[n].tune -= amount


def StopSound(module: Module) -> None:
    module.playing = False
    for voice, effect in zip(module.voices, module.effects):
        effect.active = False
        voice.shadow.written = voice.shadow.effect = False
        voice.channel.disable()
        voice.channel.set_volume(0)


def Resume(module: Module) -> None:
    """DMA on for all channels, if a song is set up."""
    if not module.song_ready:
        return
    for voice in module.voices:
        voice.channel.enable()
    module.playing = True


def StartFade(module: Module) -> None:
    """The game's fade: one volume step every third tick."""
    module.fade_speed = module.fade_ticks = 3


def EndEffects(module: Module) -> None:
    """Every effect ends on its next tick."""
    for effect in module.effects:
        effect.duration = 1


# --- Tick --------------------------------------------------------------


def Play(module: Module) -> None:
    """With Ntsc, every sixth tick is dropped: 60 Hz plays at 50 Hz.
    Tempo adds to a byte sum; each carry drops the music's tick. A fade
    lowers MasterVolume. Effects run after the music, but not on a
    dropped NTSC tick or after the song ends."""
    if module.playing:
        if module.ntsc:
            module.ntsc_ticks -= 1
            if not module.ntsc_ticks:
                module.ntsc_ticks = NTSC_SKIP
                return
        module.tempo_sum += module.tempo
        carry = module.tempo_sum > 0xFF
        module.tempo_sum &= 0xFF
        if not carry:
            if not Fade(module):
                return
            for voice in module.voices:
                if not VoiceTick(module, voice):
                    return
    PlayEffects(module)


def Fade(module: Module) -> bool:
    """False: the fade reached 0 and the song ended."""
    if not module.fade_speed:
        return True
    if module.master_volume:
        module.fade_ticks -= 1
        if module.fade_ticks:
            return True
        module.master_volume -= 1
        if module.master_volume:
            module.fade_ticks = module.fade_speed
            return True
    SongEnd(module)
    return False


def VoiceTick(module: Module, voice: Voice) -> bool:
    """False: the song ended."""
    voice.shadow.written = True
    QueueLoop(module, voice)
    return CountDown(module, voice)


def QueueLoop(module: Module, voice: Voice) -> None:
    """The tick after a note: the loop from its offset, or silence."""
    if voice.looped:
        return
    voice.looped = True
    sample = voice.sample
    if sample.loop < 0:
        write_sample(voice, module.silent, SILENT_WORDS, module)
    else:
        write_sample(
            voice, sample.start + sample.loop, sample.length - sample.loop // 2, module
        )


def CountDown(module: Module, voice: Voice) -> bool:
    """At 0, the next event. One tick before, DMA goes off, unless the
    next byte is HOLD_NOTE or an effect owns the channel. Effects skip
    that tick."""
    voice.ticks -= 1
    if not voice.ticks:
        return ReadStream(module, voice)
    if voice.ticks != 1:
        Effects(module, voice)
    elif not voice.shadow.effect and module.data[voice.pos] != HOLD_NOTE:
        voice.channel.disable()
    return True


def ReadStream(module: Module, voice: Voice) -> bool:
    """Bytes until a note, REST, HOLD_NOTE or SONG_END."""
    voice.flags = 0
    data = module.data
    while True:
        byte = data[voice.pos]
        voice.pos += 1
        if byte <= NOTE_MAX:
            NoteOn(module, voice, byte)
            return True
        outcome = ReadCommand(module, voice, byte)
        if outcome is not None:
            return outcome


def NoteOn(module: Module, voice: Voice, note: int) -> None:
    """The note plays for the current length. Its volume list restarts;
    its pitch list does not. The first volume value sounds at once."""
    data = module.data
    voice.note = note
    voice.volume_pos = voice.volume_start
    first = data[voice.volume_pos]
    voice.volume_pos += 1
    voice.volume_ticks = voice.volume_speed
    sample = voice.sample
    write_sample(voice, sample.start, sample.length, module)
    write_volume(voice, first * module.master_volume >> 6)
    write_period(voice, note_period(module, voice, 0))
    voice.looped = False
    StartNote(voice)


def StartNote(voice: Voice) -> None:
    """Also HOLD_NOTE: the length again, and DMA on."""
    voice.ticks = voice.length
    voice.channel.enable()


def Effects(module: Module, voice: Voice) -> None:
    """Pitch list, slide and vibrato set the period. The pitch list
    steps every tick; a byte with LIST_END restarts it."""
    data = module.data
    value = data[voice.pitch_pos]
    voice.pitch_pos += 1
    if value & LIST_END:
        voice.pitch_pos = voice.pitch_start
    period = note_period(module, voice, value & ~LIST_END)
    if voice.flags & SLIDE_ON:
        if voice.slide_delay:
            voice.slide_delay -= 1
        else:
            voice.slide += voice.slide_step
            period -= voice.slide
    write_period(voice, Vibrato(voice, period))
    VolumeList(module, voice)


def Vibrato(voice: Voice, period: int) -> int:
    """A triangle in period units, as in Fred: up by `speed` to the
    depth, down to 0, then the same below the note. No delay."""
    if not voice.vibrato_on:
        return period
    if voice.vibrato_growing:
        voice.vibrato_value = (voice.vibrato_value + voice.vibrato_speed) & 0xFF
        if voice.vibrato_value == voice.vibrato_depth:
            voice.vibrato_growing = False
    else:
        voice.vibrato_value = (voice.vibrato_value - voice.vibrato_speed) & 0xFF
        if not voice.vibrato_value:
            voice.vibrato_growing = True
    if not voice.vibrato_value:
        voice.vibrato_adding = not voice.vibrato_adding
    value = signed_byte(voice.vibrato_value)
    return period + value if voice.vibrato_adding else period - value


def VolumeList(module: Module, voice: Voice) -> None:
    """One value every `volume_speed` + 1 ticks. A value with HOLD
    stays: the list ends on it."""
    voice.volume_ticks -= 1
    if voice.volume_ticks >= 0:
        return
    voice.volume_ticks = voice.volume_speed
    value = module.data[voice.volume_pos]
    if not value & HOLD:
        voice.volume_pos += 1
    write_volume(voice, (value & ~HOLD) * module.master_volume >> 6)


def ReadCommand(module: Module, voice: Voice, byte: int) -> bool | None:
    """None: read on. Length, instrument and list bytes set state for
    the next note."""
    data = module.data
    if byte >= FIRST_LENGTH:
        voice.length = (byte - FIRST_LENGTH + 1) * module.speed
    elif byte >= FIRST_SAMPLE:
        voice.sample = module.samples[byte - FIRST_SAMPLE]
    elif byte >= FIRST_VOLUME_LIST:
        at = word(data, module.volume_lists + 2 * (byte - FIRST_VOLUME_LIST))
        voice.volume_start = at
        voice.volume_speed = data[at - 1]
    elif byte >= FIRST_PITCH_LIST:
        at = word(data, module.pitch_lists + 2 * (byte - FIRST_PITCH_LIST))
        voice.pitch_start = voice.pitch_pos = at
    elif byte == NEXT_PATTERN:
        NextPattern(module, voice)
    elif byte == SLIDE:
        SetSlide(module, voice)
    elif byte == REST:
        Rest(module, voice)
        return True
    elif byte == HOLD_NOTE:
        StartNote(voice)
        return True
    elif byte == SONG_END:
        SongEnd(module)
        return False
    elif byte == TRANSPOSE:
        SetTranspose(module, voice)
    elif byte == VIBRATO_ON:
        VibratoOn(module, voice)
    elif byte == VIBRATO_OFF:
        VibratoOff(voice)
    elif byte == VOICE_TRANSPOSE:
        VoiceTranspose(module, voice)
    elif byte == POSITIONS:
        SetPositions(module, voice)
    elif byte == SPEED:
        SetSpeed(module, voice)
    elif byte == FADE:
        SetFade(module, voice)
    return None


def NextPattern(module: Module, voice: Voice) -> None:
    """The next word of the position list. A 0 word wraps to its first."""
    data = module.data
    at = voice.positions + voice.position
    voice.position += 2
    if not word(data, at):
        at, voice.position = voice.positions, 2
    voice.pos = word(data, at)


def SetPositions(module: Module, voice: Voice) -> None:
    """Switches the voice to another position list. The current
    pattern plays on; the next NEXT_PATTERN starts the new list."""
    voice.positions = word(module.data, voice.pos)
    voice.position = 0
    voice.pos += 2


def SetSlide(module: Module, voice: Voice) -> None:
    """A signed step and a delay. The slide runs until the next event."""
    voice.slide = 0
    voice.slide_step = signed_byte(module.data[voice.pos])
    voice.slide_delay = module.data[voice.pos + 1]
    voice.pos += 2
    voice.flags |= SLIDE_ON


def Rest(module: Module, voice: Voice) -> None:
    """Silence for the current length."""
    voice.ticks = voice.length
    write_sample(voice, module.silent, SILENT_WORDS, module)


def SongEnd(module: Module) -> None:
    module.song_ready = module.playing = False
    for voice, effect in zip(module.voices, module.effects):
        effect.active = False
        voice.shadow.written = voice.shadow.effect = False
        voice.channel.disable()


def SetTranspose(module: Module, voice: Voice) -> None:
    """For all voices."""
    module.transpose = module.data[voice.pos]
    voice.pos += 1


def VibratoOn(module: Module, voice: Voice) -> None:
    voice.vibrato_on = voice.vibrato_growing = voice.vibrato_adding = True
    voice.vibrato_speed = module.data[voice.pos]
    voice.vibrato_depth = module.data[voice.pos + 1]
    voice.vibrato_value = 0
    voice.pos += 2


def VibratoOff(voice: Voice) -> None:
    voice.vibrato_on = False


def VoiceTranspose(module: Module, voice: Voice) -> None:
    voice.transpose = module.data[voice.pos]
    voice.pos += 1


def SetSpeed(module: Module, voice: Voice) -> None:
    """Ticks per length unit, for all voices."""
    module.speed = signed_byte(module.data[voice.pos])
    voice.pos += 1


def SetFade(module: Module, voice: Voice) -> None:
    """The score starts a fade: one volume step every N ticks."""
    module.fade_speed = module.fade_ticks = module.data[voice.pos]
    voice.pos += 1


# --- Sound effects -----------------------------------------------------


def StartEffect(module: Module, request: int) -> None:
    """d0: bits 8 and 9 the channel, the low byte the effect. A negative
    effect is a sample effect. The channel's music goes on in its
    shadow only."""
    module.effect_channel = request >> 8 & 3
    number = signed_byte(request & 0xFF)
    voice = module.voices[module.effect_channel]
    voice.shadow.effect = True
    if number < 0:
        StartSampleEffect(module, request & 0x7F)
        return
    DmaWait()
    voice.channel.disable()
    DmaWait()
    effect = read_effect(module.data, module.synth_effects + EFFECT_SIZE * number)
    effect.reset_count, effect.step_count = effect.reset_ticks, effect.step_ticks
    effect.volume_count = 1
    effect.volume_pos = word(
        module.data, module.effect_volume_lists + 2 * effect.volume_list
    )
    DmaWait()
    effect.active = True
    module.effects[module.effect_channel] = effect


def InitEffectSamples(module: Module) -> None:
    """Once: 18 samples from EFFECT_SAMPLE_DATA on, past the end of
    dw.ingame: the game loads them there (guess). The duration in ticks
    is length × 50 / rate + 1, so the sample plays once. The period is
    CLOCK / rate: the recorded rate, with no note."""
    if module.effect_samples:
        return
    data = module.data
    at = module.sample_data + EFFECT_SAMPLE_DATA
    for n in range(EFFECT_SAMPLES):
        size, rate = long(data, at), word(data, at + 4)
        record = module.effect_samples_at + EFFECT_SAMPLE_SIZE * n
        duration = (word(data, at + 2) * 50 // rate + 1) & 0xFF
        module.effect_samples.append(
            EffectSample(
                at + 6,
                signed_long(long(data, record + 4)),
                size >> 1,
                CLOCK // rate,
                duration,
                bool(data[record + 13]),
                signed_word(word(data, record + 14)),
            )  # fmt: skip
        )
        at += 6 + size


def StartSampleEffect(module: Module, number: int) -> None:
    InitEffectSamples(module)
    channel = module.voices[module.effect_channel].channel
    effect = module.effects[module.effect_channel]
    effect.sample_effect = number | 0x80
    channel.disable()
    DmaWait()
    sample = module.effect_samples[number]
    effect.duration = 0 if sample.no_duration else sample.duration
    channel.queue(chip(module, sample.start, sample.length))
    channel.period = effect.slide_period = sample.period
    channel.set_volume(FULL_VOLUME)
    channel.enable()
    effect.active = True
    DmaWait()
    if sample.loop < 0:
        channel.queue(chip(module, module.silent, SILENT_WORDS))
    else:
        channel.queue(
            chip(module, sample.start + sample.loop, sample.length - sample.loop // 2)
        )


def DmaWait() -> None:
    """A busy-wait of 513 loops, so Paula sees DMA go off. About 5000
    CCK (estimate)."""


def PlayEffects(module: Module) -> None:
    for voice, effect in zip(module.voices, module.effects):
        if effect.active:
            EffectTick(module, voice, effect)


def EffectTick(module: Module, voice: Voice, effect: Effect) -> None:
    """The duration counts down; then the effect ends."""
    if effect.duration:
        effect.duration -= 1
        if not effect.duration:
            EndEffect(module, voice, effect)
            return
    if effect.sample_effect:
        SampleEffect(module, voice, effect)
    else:
        SynthEffect(module, voice, effect)


def EndEffect(module: Module, voice: Voice, effect: Effect) -> None:
    """The channel goes back to the music: its shadow goes to Paula, so
    the music's current note sounds on."""
    effect.active = False
    voice.channel.disable()
    voice.shadow.effect = False
    if not voice.shadow.written:
        return
    shadow = voice.shadow
    DmaWait()
    voice.channel.queue(chip(module, shadow.start, shadow.length))
    voice.channel.period = shadow.period
    voice.channel.set_volume(shadow.volume)
    voice.channel.enable()


def SampleEffect(module: Module, voice: Voice, effect: Effect) -> None:
    """A slide on the period. Below MIN_PERIOD the effect ends."""
    sample = module.effect_samples[effect.sample_effect & 0x7F]
    if not sample.slide:
        voice.channel.period = effect.slide_period
        return
    effect.slide_period += sample.slide
    if effect.slide_period < MIN_PERIOD:
        EndEffect(module, voice, effect)
        return
    voice.channel.period = effect.slide_period


def SynthEffect(module: Module, voice: Voice, effect: Effect) -> None:
    """Every `step_ticks`, the step pattern rotates; its bit picks one
    of two steps for the period. Every tick, `step` adds too. Every
    `reset_ticks`, the period jumps back to `reset_period`."""
    if effect.step_ticks:
        effect.step_count -= 1
        if not effect.step_count:
            effect.step_count = effect.step_ticks
            bit, effect.step_pattern = rotate(effect.step_pattern)
            effect.period += effect.steps[bit]
    effect.period += effect.step
    if effect.reset_ticks:
        effect.reset_count -= 1
        if not effect.reset_count:
            effect.reset_count = effect.reset_ticks
            effect.period = effect.reset_period
    if not EffectVolume(module, voice, effect):
        return
    EffectOutput(module, voice, effect)


def EffectVolume(module: Module, voice: Voice, effect: Effect) -> bool:
    """A volume list, one value every `volume_speed` ticks. 0 ends the
    effect: False. A negative value holds."""
    effect.volume_count -= 1
    if effect.volume_count:
        return True
    effect.volume_count = effect.volume_speed
    value = module.data[effect.volume_pos]
    if not value:
        EndEffect(module, voice, effect)
        return False
    if not value & 0x80:
        effect.volume_pos += 1
        voice.channel.set_volume(value)
    return True


def EffectOutput(module: Module, voice: Voice, effect: Effect) -> None:
    """The period, at least MIN_PERIOD. The offset pattern rotates each
    tick; its bit picks one of two starts in EffectWave. So the effect
    can switch between two waves, or noise and silence, in a rhythm."""
    voice.channel.period = max(effect.period, MIN_PERIOD)
    bit, effect.offset_pattern = rotate(effect.offset_pattern)
    start = module.effect_wave + effect.offsets[bit]
    voice.channel.queue(chip(module, start, effect.length))
    voice.channel.enable()


# --- Helpers -----------------------------------------------------------


def note_period(module: Module, voice: Voice, offset: int) -> int:
    """(note + Transpose + voice transpose + pitch offset), then the
    table × tune >> 10."""
    note = (voice.note + module.transpose + voice.transpose + offset) & 0xFF
    table = word(module.data, module.period_table + 2 * note)
    return table * voice.sample.tune >> TUNE_SHIFT


def write_sample(voice: Voice, start: int, words: int, module: Module) -> None:
    """To the shadow; to Paula only while no effect owns the channel."""
    voice.shadow.start, voice.shadow.length = start, words
    if not voice.shadow.effect:
        voice.channel.queue(chip(module, start, words))


def write_period(voice: Voice, period: int) -> None:
    voice.shadow.period = period & 0xFFFF
    if not voice.shadow.effect:
        voice.channel.period = voice.shadow.period


def write_volume(voice: Voice, volume: int) -> None:
    voice.shadow.volume = volume
    if not voice.shadow.effect:
        voice.channel.set_volume(volume)


def chip(module: Module, start: int, words: int) -> paula.Sample:
    return paula.Sample(module.data, start & ~1, words)


def rotate(pattern: int) -> tuple[int, int]:
    """`ror.b #1`: bit 0 comes out and goes to bit 7."""
    bit = pattern & 1
    return bit, pattern >> 1 | bit << 7


def read_effect(data: bytes | bytearray, at: int) -> Effect:
    r = data[at : at + EFFECT_SIZE]
    return Effect(
        signed_word(word(r, 0)), word(r, 2),
        (signed_word(word(r, 4)), signed_word(word(r, 6))), word(r, 8),
        (word(r, 10), word(r, 12)), r[14], r[15], r[16], r[17], r[18],
        r[19], r[20], r[21], word(r, 22),
    )  # fmt: skip


def signed_long(value: int) -> int:
    return value - (1 << 32) if value & 1 << 31 else value


def signed_word(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def signed_byte(value: int) -> int:
    return value - 0x100 if value & 0x80 else value


def word(data: bytes | bytearray, at: int) -> int:
    return data[at] << 8 | data[at + 1]


def long(data: bytes | bytearray, at: int) -> int:
    return word(data, at) << 16 | word(data, at + 2)
