"""Basic tests for the shared specs: clock, CIA timer and Paula.

Run: python3 -m unittest discover -s tests
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hardware.amiga import Amiga, Priority  # noqa: E402
from hardware.cia import E_DIVIDER, CiaTimer  # noqa: E402
from hardware.clock import FRAME_CCK, LINE_CCK  # noqa: E402
from hardware.paula import SLOT_CCK, Attach, Sample, next_slot  # noqa: E402


class Amiga_(unittest.TestCase):
    def test_parts_share_one_clock(self):
        amiga = Amiga()
        self.assertIs(amiga.paula.clock, amiga)
        self.assertIs(amiga.timer.clock, amiga)
        self.assertIs(amiga.vblank.clock, amiga)
        self.assertTrue(all(c.clock is amiga for c in amiga.paula.channels))

    def test_timer_drives_a_play_routine(self):
        amiga, ticks = Amiga(), []
        amiga.timer.on_underflow = lambda: ticks.append(amiga.now)
        amiga.timer.set_latch(99)
        amiga.timer.start()
        amiga.run(1000)
        self.assertEqual(ticks, [500, 1000])


class Clock(unittest.TestCase):
    def test_runs_events_in_time_order(self):
        m, seen = Amiga(), []
        m.schedule(30, Priority.CPU, lambda: seen.append(30))
        m.schedule(10, Priority.CPU, lambda: seen.append(10))
        m.run(100)
        self.assertEqual(seen, [10, 30])

    def test_orders_ties_by_priority(self):
        m, seen = Amiga(), []
        m.schedule(5, Priority.CPU, lambda: seen.append("cpu"))
        m.schedule(5, Priority.INTERRUPT, lambda: seen.append("interrupt"))
        m.schedule(5, Priority.HARDWARE, lambda: seen.append("hardware"))
        m.run(5)
        self.assertEqual(seen, ["hardware", "interrupt", "cpu"])

    def test_step_runs_the_next_cck(self):
        m, seen = Amiga(), []

        def fetch():
            seen.append(("fetch", m.now))
            m.request_interrupt(lambda: seen.append(("irq", m.now)))

        m.schedule(40, Priority.HARDWARE, fetch)
        m.schedule(90, Priority.CPU, lambda: seen.append(("cpu", m.now)))
        self.assertEqual(m.step(), 40)
        self.assertEqual(seen, [("fetch", 40), ("irq", 40)])
        self.assertEqual(m.step(), 90)
        self.assertIsNone(m.step())
        self.assertEqual(m.now, 90)

    def test_now_is_read_only(self):
        with self.assertRaises(AttributeError):
            Amiga().now = 5  # type: ignore[misc]

    def test_rejects_an_event_in_the_past(self):
        m = Amiga()
        m.run(100)
        with self.assertRaises(ValueError):
            m.schedule(50, Priority.CPU, lambda: None)

    def test_run_stops_at_until(self):
        m, seen = Amiga(), []
        m.schedule(50, Priority.CPU, lambda: seen.append(m.now))
        m.schedule(150, Priority.CPU, lambda: seen.append(m.now))
        m.run(100)
        self.assertEqual((seen, m.now), ([50], 100))
        m.run(200)
        self.assertEqual(seen, [50, 150])

    def test_vertical_blank_comes_once_per_frame(self):
        m, seen = Amiga(), []
        m.vblank.handler = lambda: seen.append(m.now)
        m.vblank.start()
        m.run(3 * FRAME_CCK)
        self.assertEqual(seen, [FRAME_CCK, 2 * FRAME_CCK, 3 * FRAME_CCK])


class Cia(unittest.TestCase):
    def test_period_is_latch_plus_one_counts(self):
        m, seen = Amiga(), []
        timer = CiaTimer(m, lambda: seen.append(m.now))
        timer.set_latch(99)
        timer.start()
        m.run(1000)
        self.assertEqual(seen, [500, 1000])
        self.assertEqual(seen[0], (99 + 1) * E_DIVIDER)

    def test_new_latch_takes_effect_at_the_next_underflow(self):
        m, seen = Amiga(), []
        timer = CiaTimer(m, lambda: seen.append(m.now))
        timer.set_latch(99)
        timer.start()
        m.run(250)
        timer.set_latch(9)
        m.run(600)
        self.assertEqual(seen, [500, 550, 600])


def playing(paula, channel, events):
    """Record (time, first byte of the playing sample) at each interrupt."""
    paula.channels[channel].on_irq(
        lambda c: events.append((paula.clock.now, c.playing.data[:1]))
    )


class Paula_(unittest.TestCase):
    def setUp(self):
        self.m = Amiga()
        self.paula = self.m.paula
        self.channel = self.paula.channels[0]
        self.channel.period = 200
        self.events = []
        playing(self.paula, 0, self.events)

    def test_each_channel_has_its_own_slot(self):
        self.assertEqual(next_slot(0, 0), SLOT_CCK[0])
        self.assertEqual(next_slot(3, 0), SLOT_CCK[3])
        self.assertEqual(next_slot(0, SLOT_CCK[0] + 1), LINE_CCK + SLOT_CCK[0])

    def test_interrupts_at_start_and_at_each_reload(self):
        self.channel.play(Sample(b"N" * 8))
        self.m.run(3000)
        times = [t for t, _ in self.events]
        self.assertEqual(times[0], SLOT_CCK[0])
        self.assertGreater(len(times), 1)

    def test_loop_written_after_the_start_plays_the_note_first(self):
        self.m.schedule(100, Priority.CPU, lambda: self.channel.play(Sample(b"N" * 8)))
        self.m.schedule(
            100 + LINE_CCK, Priority.CPU, lambda: self.channel.queue(Sample(b"L" * 4))
        )
        self.m.run(3000)
        self.assertEqual([b for _, b in self.events[:2]], [b"N", b"L"])

    def test_loop_written_before_the_start_replaces_it(self):
        self.m.schedule(100, Priority.CPU, lambda: self.channel.play(Sample(b"N" * 8)))
        self.m.schedule(181, Priority.CPU, lambda: self.channel.queue(Sample(b"L" * 4)))
        self.m.run(3000)
        self.assertEqual(self.events[0][1], b"L")

    def test_dma_on_before_idle_does_not_restart(self):
        # N is 4 words: its start reload at 14, words at 241, 695, 1149.
        self.channel.play(Sample(b"N" * 8))
        self.m.run(700)
        self.channel.disable()
        self.channel.play(Sample(b"R" * 8))  # at once: the word still plays
        self.m.run(1500)
        # A restart would reload R at the next slot, 922. Instead R waits
        # for N's own reload, with its last word at 1149.
        self.assertEqual(self.events[1:], [(1149, b"R")])

    def test_dma_on_after_idle_restarts(self):
        self.channel.play(Sample(b"N" * 8))
        self.m.run(1000)
        self.channel.irq_enabled = False  # the extra word's request stays set
        self.channel.disable()
        self.m.run(1000 + 4 * self.channel.period + 2 * LINE_CCK)
        self.assertTrue(self.channel.idle)
        self.channel.irq_enabled = True
        start = self.m.now
        self.channel.play(Sample(b"R" * 8))
        self.m.run(start + LINE_CCK)
        self.assertEqual(self.events[-1][1], b"R")

    def test_period_times_each_word_not_the_dma_slot(self):
        # At period 428 a word lasts 856 CCK: 3.77 lines, not 4.
        self.channel.period = 428
        self.channel.play(Sample(b"N" * 4))  # two words: a reload per 1712 CCK
        self.m.run(100 * 1712)
        times = [t for t, _ in self.events][1:]
        per_reload = (times[-1] - times[0]) / (len(times) - 1)
        self.assertAlmostEqual(per_reload, 1712, delta=3)

    def test_dma_off_before_output_goes_idle(self):
        self.channel.play(Sample(b"N" * 8))
        self.m.run(SLOT_CCK[0])  # the start reload only
        self.channel.disable()
        self.m.run(1000)
        self.assertTrue(self.channel.idle)

    def test_disable_with_intreq_set_stops_the_channel(self):
        self.channel.play(Sample(b"N" * 8))
        self.m.run(300)
        self.channel.irq_enabled = False
        self.channel.irq_requested = True
        self.channel.disable()
        self.m.run(5000)
        self.assertTrue(self.channel.idle)

    def test_disable_with_intreq_clear_plays_one_more_word(self):
        # N's first word plays from 241 to 641; DMA goes off during it.
        self.channel.play(Sample(b"N" * 8))
        self.m.run(300)
        self.channel.irq_enabled = False
        self.channel.irq_requested = False
        self.channel.disable()
        self.m.run(640)
        self.assertFalse(self.channel.irq_requested)
        self.m.run(641)
        self.assertTrue(self.channel.irq_requested)
        self.assertFalse(self.channel.idle)
        self.m.run(641 + 2 * self.channel.period)
        self.assertTrue(self.channel.idle)

    def test_data_write_from_idle_requests_at_once(self):
        self.channel.irq_enabled = False
        self.channel.period = 1
        self.channel.write_data()
        self.assertTrue(self.channel.irq_requested)
        self.m.run(2)
        self.assertTrue(self.channel.idle)

    def test_volume_bit_6_forces_the_maximum(self):
        self.channel.set_volume(0x40 | 5)
        self.assertEqual(self.channel.volume, 64)
        self.channel.set_volume(33)
        self.assertEqual(self.channel.volume, 33)

    def test_attach_writes_words_to_the_next_channel(self):
        self.paula.adkcon([Attach.VOLUME, Attach.NONE, Attach.NONE, Attach.NONE])
        self.channel.play(Sample(bytes([0, 40, 0, 20])))
        self.m.run(2000)
        self.assertIn(self.paula.channels[1].volume, (40, 20))
        self.assertIsNone(self.paula.channels[3].modulates)


if __name__ == "__main__":
    unittest.main()
