# Copyright 2026 Wuyang Zhou and Tianyu Wei
# SPDX-License-Identifier: Apache-2.0

"""Tests for the code-execution API; no Win32 backend is constructed."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import threading
import time
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from minecraft import Minecraft
import input_boundary as boundary
from test_input_boundary import FakeBackend, FakeClock


class RuntimeBackend(FakeBackend):
    def __init__(self, clock):
        super().__init__(clock)
        self.target = {'hwnd': 123, 'pid': 456}
        self.mutex = object()
        self.locked = False
        self.points = []
        self.focused = False

    def choose(self, hwnd=None):
        if hwnd is not None and hwnd != self.target['hwnd']:
            raise AssertionError('Unexpected HWND')
        return dict(self.target)

    def lock(self):
        self.locked = True
        return self.mutex

    def unlock(self, mutex):
        if mutex is not self.mutex:
            raise AssertionError('Wrong mutex')
        self.locked = False

    def focus(self, target):
        self.focused = True

    def frame(self, target):
        self.guard(target)
        return Image.new('RGB', (16, 9), 'black')

    def capture(self, target, destination, max_width):
        self.guard(target)
        return {'path': str(destination), 'source_size': [16, 9], 'image_size': [16, 9]}

    def point(self, target, x, y):
        self.guard(target)
        self.points.append((x, y))


class MinecraftApiTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.backend = RuntimeBackend(self.clock)

    def session(self, **kwargs):
        return Minecraft(_backend=self.backend, _clock=self.clock, **kwargs)

    def test_long_hold_is_split_into_boundary_leases(self):
        with self.session() as game:
            report = game.hold(keys=('w',), seconds=12)
        self.assertEqual(report['chunks'], 3)
        self.assertEqual([round(item['elapsed_seconds']) for item in report['leases']], [4, 4, 4])
        presses = [event for event in self.backend.events if event[1:] == ('key', 'w', True)]
        releases = [event for event in self.backend.events if event[1:] == ('key', 'w', False)]
        self.assertEqual(len(presses), 3)
        self.assertEqual(len(releases), 3)
        self.assertFalse(self.backend.locked)

    def test_large_mouse_motion_is_split_without_losing_delta(self):
        with self.session() as game:
            report = game.look(4001, -2500, seconds=0.06)
        self.assertEqual(report['chunks'], 3)
        moves = [event for event in self.backend.events if event[1] == 'move']
        self.assertEqual(sum(event[2] for event in moves), 4001)
        self.assertEqual(sum(event[3] for event in moves), -2500)

    def test_focus_capture_wait_and_click_are_composable(self):
        with self.session(focus=True) as game:
            self.assertEqual(game.frame().size, (16, 9))
            capture = game.capture('captures/current.png')
            game.wait(0.12)
            game.click(7, 4)
        self.assertTrue(self.backend.focused)
        self.assertEqual(capture['source_size'], [16, 9])
        self.assertEqual(self.backend.points, [(7, 4)])
        self.assertFalse(self.backend.locked)

    def test_methods_require_owned_session(self):
        game = self.session()
        with self.assertRaisesRegex(RuntimeError, 'context manager'):
            game.frame()

    def test_focus_loss_releases_current_chunk_and_stops_following_chunks(self):
        self.backend.lose_focus_at = 5.02
        with self.assertRaisesRegex(Exception, 'lost focus'):
            with self.session() as game:
                game.hold(keys=('w',), seconds=12)
        self.assertEqual(self.backend.held, set())
        self.assertFalse(self.backend.locked)


class RealClock:
    monotonic = staticmethod(time.monotonic)
    sleep = staticmethod(time.sleep)

    @property
    def now(self):
        return time.monotonic()


class ConcurrentBackend(RuntimeBackend):
    """Real scheduling, fake inputs. Events coordinate tests without polling."""

    def __init__(self):
        super().__init__(RealClock())
        self.pressed = threading.Event()
        self.releasing = threading.Event()
        self.release_gate = None
        self.observed_inputs = []
        self.unlocked_inputs = None

    def _input(self, kind, name, pressed):
        try:
            super()._input(kind, name, pressed)
        finally:
            if pressed:
                self.pressed.set()

    def frame(self, target):
        result = super().frame(target)
        self.observed_inputs.append(set(self.held))
        return result

    def capture(self, target, destination, max_width):
        self.observed_inputs.append(set(self.held))
        return super().capture(target, destination, max_width)

    def release(self, keys, buttons, on_released=None):
        self.releasing.set()
        if self.release_gate is not None and not self.release_gate.wait(2):
            raise AssertionError('Test release gate was not opened.')
        return super().release(keys, buttons, on_released=on_released)

    def unlock(self, mutex):
        self.unlocked_inputs = set(self.held)
        super().unlock(mutex)


class AsyncMinecraftTests(unittest.TestCase):
    def setUp(self):
        self.backend = ConcurrentBackend()

    def session(self):
        return Minecraft(_backend=self.backend, _clock=self.backend.clock)

    def wait_for_press(self):
        self.assertTrue(self.backend.pressed.wait(2), 'Input worker never pressed its key.')

    def test_frames_captures_and_analysis_run_while_the_same_key_stays_held(self):
        with self.session() as game:
            with game.hold_async(keys=('w',), seconds=5) as action:
                self.wait_for_press()
                for _ in range(3):
                    frame = game.frame()
                    self.assertEqual(frame.getpixel((0, 0)), (0, 0, 0))
                game.capture('captures/mock-only.png')
                self.assertFalse(action.done())
                self.assertEqual(self.backend.observed_inputs, [{('key', 'w')}] * 4)
                self.assertEqual(self.backend.release_calls, [])
            self.assertTrue(action.done())
            self.assertEqual(self.backend.held, set())
            game.press('e')
        self.assertEqual(self.backend.unlocked_inputs, set())

    def test_competing_inputs_cannot_move_pointer_focus_or_inject_keys(self):
        with self.session() as game:
            with game.hold_async(keys=('w',), seconds=5):
                self.wait_for_press()
                attempts = (
                    lambda: game.press('e'), lambda: game.look(20, 0),
                    lambda: game.click(3, 4), game.focus,
                    lambda: game.hold_async(buttons=('left',), seconds=.1).__enter__(),
                )
                # Also exercise callers on other threads within the session.
                with ThreadPoolExecutor(max_workers=2) as pool:
                    for attempt in attempts:
                        with self.assertRaisesRegex(boundary.ControlError, 'owns this session'):
                            pool.submit(attempt).result(timeout=2)
                self.assertEqual(self.backend.points, [])
                self.assertFalse(self.backend.focused)
                presses = [e[1:] for e in self.backend.events if e[1] == 'key' and e[3]]
                self.assertEqual(presses, [('key', 'w', True)])

    def test_observer_exception_cancels_held_keys_and_buttons(self):
        with self.session() as game:
            with self.assertRaisesRegex(ValueError, 'analysis failed'):
                with game.hold_async(keys=('w',), buttons=('left',), seconds=5):
                    self.wait_for_press()
                    raise ValueError('analysis failed')
            self.assertEqual(self.backend.held, set())
            game.press('e')

    def test_capture_failure_cancels_even_if_caller_catches_it(self):
        with self.session() as game:
            with game.hold_async(keys=('w',), seconds=5) as action:
                self.wait_for_press()
                with patch.object(self.backend, 'capture', side_effect=OSError('capture failed')):
                    with self.assertRaisesRegex(OSError, 'capture failed'):
                        game.capture('captures/mock-only.png')
                with self.assertRaises(boundary.ActionCancelled):
                    action.result(timeout=2)
                self.assertEqual(self.backend.held, set())

    def test_slow_frame_does_not_extend_hold_or_block_focus_loss_cleanup(self):
        for lose_focus in (False, True):
            with self.subTest(lose_focus=lose_focus):
                self.backend = ConcurrentBackend()
                entered, finish_frame = threading.Event(), threading.Event()
                def slow_frame(target):
                    self.backend.observed_inputs.append(set(self.backend.held))
                    entered.set()
                    if not finish_frame.wait(2):
                        raise AssertionError('Test frame was not released.')
                    return Image.new('RGB', (16, 9))
                try:
                    with self.session() as game, patch.object(self.backend, 'frame', slow_frame):
                        with ThreadPoolExecutor(max_workers=1) as pool:
                            try:
                                with game.hold_async(keys=('w',), seconds=.2) as action:
                                    self.wait_for_press()
                                    observation = pool.submit(game.frame)
                                    self.assertTrue(entered.wait(2))
                                    if lose_focus:
                                        self.backend.lose_focus_at = self.backend.clock.now
                                        with self.assertRaisesRegex(boundary.ControlError, 'lost focus'):
                                            action.result(timeout=1)
                                    else:
                                        action.result(timeout=1)
                                    self.assertFalse(observation.done())
                                    self.assertEqual(self.backend.held, set())
                                    self.assertEqual(self.backend.observed_inputs, [{('key', 'w')}])
                                    finish_frame.set()
                                    observation.result(timeout=1)
                            finally:
                                finish_frame.set()
                except boundary.ControlError:
                    if not lose_focus:
                        raise
                finally:
                    finish_frame.set()
                self.assertEqual(self.backend.unlocked_inputs, set())

    def test_cancel_stops_before_the_next_lease(self):
        with self.session() as game:
            with game.hold_async(keys=('w',), seconds=12) as action:
                self.wait_for_press()
                action.cancel()
                with self.assertRaises(boundary.ActionCancelled):
                    action.result(timeout=2)
            presses = [e for e in self.backend.events if e[1:] == ('key', 'w', True)]
            self.assertEqual(len(presses), 1)
            self.assertEqual(self.backend.held, set())

    def test_native_stop_and_target_guards_apply_during_background_input(self):
        for cause in ('f8', 'stop_file', 'focus', 'minimized', 'destroyed', 'pid'):
            with self.subTest(cause=cause):
                self.backend = ConcurrentBackend()
                native = object.__new__(boundary.Windows)
                native.u = Mock()
                native.u.IsWindow.return_value = True
                native.u.GetForegroundWindow.return_value = 123
                native.u.IsIconic.return_value = False
                native.pid = Mock(return_value=456)
                native.down = Mock(return_value=False)
                stopped = Mock()
                stopped.exists.return_value = False
                triggers = {
                    'f8': lambda: setattr(native.down, 'return_value', True),
                    'stop_file': lambda: setattr(stopped.exists, 'return_value', True),
                    'focus': lambda: setattr(native.u.GetForegroundWindow, 'return_value', 999),
                    'minimized': lambda: setattr(native.u.IsIconic, 'return_value', True),
                    'destroyed': lambda: setattr(native.u.IsWindow, 'return_value', False),
                    'pid': lambda: setattr(native.pid, 'return_value', 999),
                }
                with patch.object(boundary, 'STOP_FILE', stopped):
                    with patch.object(self.backend, 'guard', native.guard):
                        with self.session() as game:
                            with self.assertRaises(boundary.ControlError):
                                with game.hold_async(keys=('w',), seconds=5) as action:
                                    self.wait_for_press()
                                    triggers[cause]()
                                    action.result(timeout=1)
                            self.assertEqual(self.backend.held, set())
                self.assertEqual(self.backend.unlocked_inputs, set())

    def test_input_error_is_propagated_when_scope_exits(self):
        self.backend.fail_press = ('key', 'w')
        with self.session() as game:
            with self.assertRaisesRegex(boundary.ControlError, 'Uncertain press'):
                with game.hold_async(keys=('w',), seconds=.1):
                    self.wait_for_press()
            self.assertEqual(self.backend.held, set())

    def test_session_exit_joins_active_input_before_unlocking(self):
        with self.session() as game:
            action = game.hold_async(keys=('w',), seconds=5)
            action.__enter__()  # Outer cleanup also handles a forgotten scope.
            self.wait_for_press()
        self.assertTrue(action.done())
        self.assertFalse(action.thread.is_alive())
        self.assertEqual(self.backend.unlocked_inputs, set())
        self.assertFalse(self.backend.locked)

    def test_release_in_progress_keeps_input_reservation(self):
        self.backend.release_gate = threading.Event()
        try:
            with self.session() as game:
                with game.hold_async(keys=('w',), seconds=5) as action:
                    self.wait_for_press()
                    action.cancel()
                    self.assertTrue(self.backend.releasing.wait(2))
                    self.assertTrue(self.backend.locked)
                    with self.assertRaises(TimeoutError):
                        action.result(timeout=.01)
                    with self.assertRaisesRegex(boundary.ControlError, 'owns this session'):
                        game.press('e')
                    self.backend.release_gate.set()
                self.assertEqual(self.backend.held, set())
        finally:
            self.backend.release_gate.set()

    def test_interruption_while_waiting_for_cleanup_does_not_unlock_early(self):
        self.backend.release_gate = threading.Event()
        try:
            with self.session() as game:
                action = game.hold_async(keys=('w',), seconds=5)
                action.__enter__()
                self.wait_for_press()
                original_wait = action.finished.wait
                def interrupted_wait(timeout):
                    self.assertTrue(self.backend.locked)
                    self.backend.release_gate.set()
                    raise KeyboardInterrupt()
                with patch.object(action.finished, 'wait'):
                    def once(timeout):
                        action.finished.wait.side_effect = original_wait
                        return interrupted_wait(timeout)
                    action.finished.wait.side_effect = once
                    with self.assertRaises(KeyboardInterrupt):
                        action.__exit__(None, None, None)
                self.assertEqual(self.backend.held, set())
        finally:
            self.backend.release_gate.set()

    def test_watchdog_is_used_and_joined_before_action_finishes(self):
        context = Mock()
        reader, writer, monitor = Mock(), Mock(), Mock()
        context.Pipe.return_value = (reader, writer)
        context.RawArray.side_effect = lambda kind, count: [0] * count
        context.Process.return_value = monitor
        def joined():
            self.assertTrue(self.backend.locked)
            self.assertEqual(self.backend.held, set())
        monitor.join.side_effect = joined
        with patch('minecraft.MP.get_context', return_value=context):
            with self.session() as game:
                game._use_watchdogs = True
                with game.hold_async(keys=('w',), seconds=5) as action:
                    self.wait_for_press()
                self.assertTrue(action.done())
                monitor.join.assert_called_once_with()
                writer.send.assert_called_once_with('released')
                self.assertIs(context.Process.call_args.kwargs['target'], boundary.watchdog)

    def test_unentered_context_never_sends_input_and_bad_arguments_fail_early(self):
        with self.session() as game:
            action = game.hold_async(keys=('w',), seconds=.1)
            with self.assertRaisesRegex(RuntimeError, 'context manager'):
                action.result()
            for kwargs in ({'keys': ('w', 'w')}, {'buttons': ('invalid',)},
                           {'seconds': float('inf')}, {'seconds': -.1}, {'dx': True}):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    game.hold_async(**kwargs)
            self.assertEqual(self.backend.events, [])

    def test_interruption_after_thread_spawn_never_leaves_an_unowned_input(self):
        with self.session() as game:
            action = game.hold_async(keys=('w',), seconds=5)
            original_start = action.thread.start
            def interrupted_start():
                original_start()
                raise KeyboardInterrupt()
            with patch.object(action.thread, 'start', interrupted_start):
                with self.assertRaises(KeyboardInterrupt):
                    action.__enter__()
            action.thread.join(timeout=2)
            self.assertFalse(action.thread.is_alive())
            self.assertEqual(self.backend.events, [])
            game.press('e')
        self.assertEqual(self.backend.unlocked_inputs, set())

    def test_thread_start_failure_leaves_session_usable(self):
        with self.session() as game:
            action = game.hold_async(keys=('w',), seconds=5)
            with patch.object(action.thread, 'start', side_effect=RuntimeError('cannot start')):
                with self.assertRaisesRegex(RuntimeError, 'cannot start'):
                    action.__enter__()
            self.assertEqual(self.backend.events, [])
            game.press('e')


if __name__ == '__main__':
    unittest.main()
