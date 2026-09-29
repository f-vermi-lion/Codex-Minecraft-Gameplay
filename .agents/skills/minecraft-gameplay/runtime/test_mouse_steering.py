"""Mock-only coverage for observation-driven motion under one input owner."""
import threading
import unittest
from unittest.mock import patch

import input_boundary as boundary
from minecraft import Minecraft
from test_input_boundary import FakeClock, FakeBackend, TrackingOwnership
from test_minecraft import ConcurrentBackend
import test_minecraft_transitions as transition_tests


class SteeringBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.backend = FakeBackend(self.clock)
        self.channel = boundary.MouseSteering()
        self.target = {'hwnd': 123, 'pid': 456}

    def run_input(self, **kwargs):
        return boundary.perform_continuous_sequence(
            self.backend, self.target, [([], ['right'], .12, 0, 0)],
            self.clock, steering=self.channel, **kwargs)

    def moves(self):
        return [(e[2], e[3]) for e in self.backend.events if e[1] == 'move' and (e[2] or e[3])]

    def test_latest_command_is_applied_by_held_input_without_repressing(self):
        self.channel.submit(99, 20)
        self.channel.submit(-17, 31)
        original = self.backend.move
        def move(dx, dy):
            self.assertEqual(self.backend.held, {('button', 'right')})
            original(dx, dy)
        self.backend.move = move
        result = self.run_input()
        self.assertEqual(self.moves(), [(-17, 31)])
        self.assertEqual(result['steering_delta'], [-17, 31])
        self.assertEqual([e[1:] for e in self.backend.events if e[1] == 'button'],
                         [('button', 'right', True), ('button', 'right', False)])

    def test_invalid_updates_are_rejected_without_native_input(self):
        for delta in ((True, 0), (0, 2.1), (2001, 0), (0, -2001)):
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                self.channel.submit(*delta)
        self.assertEqual(self.backend.events, [])

    def test_total_motion_budget_failure_releases_and_clears_watchdog_bits(self):
        ownership = TrackingOwnership(1)
        self.channel.submit(2000, 0)
        original = self.clock.sleep
        def sleep(seconds):
            original(seconds)
            self.channel.submit(-1, 0)
        self.clock.sleep = sleep
        with self.assertRaisesRegex(boundary.ControlError, 'budget'):
            self.run_input(ownership=ownership)
        self.assertEqual(self.moves(), [(2000, 0)])
        self.assertEqual(list(ownership), [0])
        self.assertFalse(self.backend.held)

    def test_focus_or_pointer_loss_prevents_queued_motion_and_releases(self):
        for pointer in (False, True):
            with self.subTest(pointer=pointer):
                self.setUp()
                original = self.clock.sleep
                def sleep(seconds):
                    original(seconds)
                    self.channel.submit(200, 0)
                    if pointer:
                        def reject(target):
                            raise boundary.ControlError('pointer left target')
                        self.backend.guard_pointer = reject
                    else:
                        self.backend.lose_focus_at = self.clock.now
                self.clock.sleep = sleep
                with self.assertRaises(boundary.ControlError):
                    self.run_input()
                self.assertEqual(self.moves(), [])
                self.assertFalse(self.backend.held)

    def test_cancel_prevents_queued_motion_and_releases(self):
        cancelled = threading.Event()
        original = self.clock.sleep
        def sleep(seconds):
            original(seconds)
            self.channel.submit(200, 0)
            cancelled.set()
        self.clock.sleep = sleep
        with self.assertRaises(boundary.ActionCancelled):
            self.run_input(cancel_event=cancelled)
        self.assertEqual(self.moves(), [])
        self.assertFalse(self.backend.held)


class SteeringApiTests(unittest.TestCase):
    def test_updates_use_existing_worker_while_capture_and_exclusivity_remain(self):
        backend = ConcurrentBackend()
        moved = threading.Event()
        worker_ids = []
        original = backend.move
        def move(dx, dy):
            original(dx, dy)
            if dx or dy:
                worker_ids.append(threading.get_ident())
                moved.set()
        backend.move = move
        with Minecraft(_backend=backend, _clock=backend.clock) as game:
            action = game.sequence_async([{'buttons': ('right',), 'seconds': 1}],
                                         preserve_inputs=True, steerable=True)
            with self.assertRaises(boundary.ControlError):
                action.steer(1, 0)
            with action:
                self.assertTrue(backend.pressed.wait(2))
                game.frame()
                self.assertEqual(backend.observed_inputs[-1], {('button', 'right')})
                action.steer(21, -17)
                self.assertTrue(moved.wait(2))
                self.assertEqual(worker_ids, [action.thread.ident])
                with self.assertRaisesRegex(boundary.ControlError, 'owns this session'):
                    game.look(1, 0)
                action.cancel()
            with self.assertRaises(boundary.ControlError):
                action.steer(1, 0)
            self.assertFalse(backend.held)
        self.assertEqual(backend.unlocked_inputs, set())

    def test_capture_failure_cancels_steering_and_waits_for_release(self):
        backend = ConcurrentBackend()
        with Minecraft(_backend=backend, _clock=backend.clock) as game:
            with game.sequence_async([{'buttons': ('right',), 'seconds': 1}],
                                     preserve_inputs=True, steerable=True) as action:
                self.assertTrue(backend.pressed.wait(2))
                with patch.object(backend, 'frame', side_effect=OSError('capture failed')):
                    with self.assertRaises(OSError):
                        game.frame()
                self.assertTrue(action.finished.wait(2))
            self.assertFalse(backend.held)

    def test_validation_keeps_steering_bounded_and_opt_in(self):
        backend = ConcurrentBackend()
        with Minecraft(_backend=backend, _clock=backend.clock) as game:
            for kwargs in ({'steerable': True}, {'preserve_inputs': True, 'steerable': 1}):
                with self.assertRaises(ValueError):
                    game.sequence_async([{'seconds': .1}], **kwargs)
            with self.assertRaises(ValueError):
                game.sequence_async([{'seconds': 5}, {'seconds': .1}],
                                    preserve_inputs=True, steerable=True)
        self.assertEqual(backend.events, [])

    def test_steering_uses_single_watchdog_with_original_input_ownership(self):
        fixture = transition_tests.SequenceTests()
        fixture.setUp()
        context, reader, writer, monitor = fixture.watchdog()
        original = boundary.perform_continuous_sequence
        def perform(*args, **kwargs):
            kwargs['steering'].submit(13, -9)
            return original(*args, **kwargs)
        with patch('minecraft.MP.get_context', return_value=context), \
                patch('minecraft.boundary.perform_continuous_sequence', side_effect=perform):
            with fixture.session() as game:
                game._use_watchdogs = True
                with game.sequence_async([
                    {'keys': ('esc',), 'buttons': ('right',), 'seconds': .04},
                    {'buttons': ('right',), 'seconds': .2}],
                    preserve_inputs=True, steerable=True) as action:
                    result = action.result(timeout=2)
        self.assertEqual(result['steering_delta'], [13, -9])
        context.Process.assert_called_once()
        self.assertEqual(list(context.Process.call_args.kwargs['args'][3]), [0, 0])
        writer.send.assert_called_once_with('released')
        monitor.join.assert_called_once_with()
        self.assertFalse(fixture.backend.held)


if __name__ == '__main__':
    unittest.main()
