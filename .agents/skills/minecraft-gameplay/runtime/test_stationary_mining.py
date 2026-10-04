"""Uninterrupted stationary mining tests; only mock input backends."""
import threading
import unittest
from unittest.mock import Mock, patch

import input_boundary as boundary
from minecraft import Minecraft
from test_input_boundary import FakeClock, FakeBackend
from test_minecraft import RuntimeBackend, ConcurrentBackend


class MiningBoundaryTests(unittest.TestCase):
    def test_only_stationary_left_button_gets_the_longer_limit(self):
        boundary.validate_action([], ['left'], 45, 0, 0)
        for keys, buttons, duration, dx, dy in (
            ([], ['left'], 45.01, 0, 0),
            ([], ['left'], float('nan'), 0, 0),
            ([], ['left'], float('inf'), 0, 0),
            (['w'], ['left'], 6, 0, 0),
            ([], ['right'], 6, 0, 0),
            ([], ['left', 'right'], 6, 0, 0),
            ([], ['left'], 6, 1, 0),
            ([], ['left'], 6, 0, 1),
        ):
            with self.subTest(action=(keys, buttons, duration, dx, dy)):
                with self.assertRaises(ValueError):
                    boundary.validate_action(keys, buttons, duration, dx, dy)

    def test_guards_and_cancellation_after_five_seconds_release_left(self):
        for failure in ('focus', 'pointer', 'cancel'):
            with self.subTest(failure=failure):
                clock = FakeClock()
                backend = FakeBackend(clock)
                cancel = threading.Event()
                original_sleep = clock.sleep
                def sleep(seconds):
                    original_sleep(seconds)
                    if failure == 'cancel' and clock.now >= 5.05:
                        cancel.set()
                clock.sleep = sleep
                if failure == 'focus':
                    backend.lose_focus_at = 5.05
                if failure == 'pointer':
                    def guard_pointer(target):
                        if clock.now >= 5.05:
                            raise boundary.ControlError('Pointer left Minecraft')
                    backend.guard_pointer = guard_pointer
                ownership = [0]
                with self.assertRaises(boundary.ControlError):
                    boundary.perform(backend, {'hwnd': 123, 'pid': 456},
                                     [], ['left'], 12, clock=clock,
                                     ownership=ownership, cancel_event=cancel)
                self.assertLess(clock.now, 5.08)
                self.assertEqual(backend.held, set())
                self.assertEqual(ownership, [0])
                presses = [e for e in backend.events if e[1:] == ('button', 'left', True)]
                self.assertEqual(len(presses), 1)


class MiningApiTests(unittest.TestCase):
    def test_twelve_second_mine_is_one_press_and_one_release(self):
        clock = FakeClock()
        backend = RuntimeBackend(clock)
        with Minecraft(_backend=backend, _clock=clock) as game:
            with game.mine_async(12) as action:
                result = action.result()
        presses = [e for e in backend.events if e[1:] == ('button', 'left', True)]
        releases = [e for e in backend.events if e[1:] == ('button', 'left', False)]
        self.assertEqual(len(presses), 1)
        self.assertEqual(len(releases), 1)
        self.assertAlmostEqual(releases[0][0] - presses[0][0], 12)
        self.assertEqual(result['elapsed_seconds'], 12)
        self.assertEqual(backend.held, set())
        self.assertFalse(backend.locked)

    def test_watchdog_and_exclusivity_remain_until_release_is_joined(self):
        backend = ConcurrentBackend()
        context = Mock()
        reader, writer, monitor = Mock(), Mock(), Mock()
        context.Pipe.return_value = (reader, writer)
        context.RawArray.side_effect = lambda kind, count: [0] * count
        context.Process.return_value = monitor
        def joined():
            self.assertTrue(backend.locked)
            self.assertEqual(backend.held, set())
        monitor.join.side_effect = joined
        with patch('minecraft.MP.get_context', return_value=context):
            with Minecraft(_backend=backend, _clock=backend.clock) as game:
                game._use_watchdogs = True
                with game.mine_async(12) as action:
                    self.assertTrue(backend.pressed.wait(2))
                    game.frame()
                    self.assertEqual(backend.observed_inputs, [{('button', 'left')}])
                    with self.assertRaises(boundary.ControlError):
                        game.press('w')
                    action.cancel()
                    with self.assertRaises(boundary.ActionCancelled):
                        action.result(timeout=2)
                monitor.join.assert_called_once_with()
                writer.send.assert_called_once_with('released')
                process_args = context.Process.call_args.kwargs
                self.assertIs(process_args['target'], boundary.watchdog)
                self.assertEqual(process_args['args'][-1], 14)
        self.assertEqual(backend.unlocked_inputs, set())


if __name__ == '__main__':
    unittest.main()

