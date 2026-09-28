"""Mock-only coverage for short action transitions; never connects to a game."""
import threading
import unittest
from unittest.mock import Mock, patch

from minecraft import Minecraft
import input_boundary as boundary
from test_input_boundary import FakeClock, TrackingOwnership
from test_minecraft import RuntimeBackend, ConcurrentBackend


class SequenceTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.backend = RuntimeBackend(self.clock)

    def session(self):
        return Minecraft(_backend=self.backend, _clock=self.clock)

    def watchdog(self):
        context = Mock()
        reader, writer, monitor = Mock(), Mock(), Mock()
        context.Pipe.return_value = (reader, writer)
        context.RawArray.side_effect = lambda kind, count: TrackingOwnership(count)
        context.Process.return_value = monitor
        return context, reader, writer, monitor

    def test_ordered_transitions_share_one_watchdog_and_preserve_ownership_mapping(self):
        context, reader, writer, monitor = self.watchdog()
        steps = [
            {'keys': ('esc',), 'buttons': ('right',), 'seconds': .04},
            {'buttons': ('right',), 'seconds': .3, 'dx': 17},
            {'buttons': ('left',), 'seconds': .03},
            {'keys': ('esc',), 'seconds': .04},
        ]
        def join():
            self.assertTrue(self.backend.locked)
            self.assertFalse(self.backend.held)
        monitor.join.side_effect = join
        with patch('minecraft.MP.get_context', return_value=context):
            with self.session() as game:
                game._use_watchdogs = True
                with game.sequence_async(steps) as action:
                    result = action.result(timeout=2)
        self.assertEqual(len(result['steps']), 4)
        self.assertEqual(self.backend.preflight_calls, 4)
        context.Process.assert_called_once()
        monitor.start.assert_called_once_with()
        monitor.join.assert_called_once_with()
        writer.send.assert_called_once_with('released')
        args = context.Process.call_args.kwargs['args']
        self.assertEqual(args[1:3], (['esc'], ['right', 'left']))
        self.assertEqual(list(args[3]), [0, 0, 0])
        self.assertEqual(args[3].writes, [
            (0, 1), (1, 1), (1, 0), (0, 0),
            (1, 1), (1, 0), (2, 1), (2, 0), (0, 1), (0, 0)])
        self.assertAlmostEqual(args[4], 2.41)
        self.assertFalse(self.backend.locked)

    def test_all_steps_are_validated_before_input(self):
        bad = [
            [], [{'keys': ('w',), 'seconds': 3}, {'seconds': 3}],
            [{'seconds': .02}, {'buttons': ('invalid',)}],
            [{'seconds': float('nan')}], [{'dx': True}],
            [{'focus': True}], [{'keys': ('w', 'w')}],
        ]
        with self.session() as game:
            for steps in bad:
                with self.subTest(steps=steps), self.assertRaises(ValueError):
                    game.sequence_async(steps)
        self.assertEqual(self.backend.events, [])

    def test_focus_loss_releases_inputs_and_cancels_later_steps(self):
        self.backend.lose_focus_at = .11
        with self.session() as game:
            with self.assertRaisesRegex(boundary.ControlError, 'lost focus'):
                with game.sequence_async([
                    {'keys': ('esc',), 'seconds': .04},
                    {'buttons': ('right',), 'seconds': .3},
                    {'buttons': ('left',), 'seconds': .03},
                ]) as action:
                    action.result(timeout=2)
        self.assertFalse(self.backend.held)
        self.assertNotIn(('button', 'left', True), [event[1:] for event in self.backend.events])

    def test_failed_release_leaves_correct_bits_for_watchdog_and_stops_sequence(self):
        context, reader, writer, monitor = self.watchdog()
        self.backend.fail_release = ('button', 'right')
        with patch('minecraft.MP.get_context', return_value=context):
            with self.session() as game:
                game._use_watchdogs = True
                with self.assertRaisesRegex(boundary.ControlError, 'release every input'):
                    with game.sequence_async([
                        {'keys': ('esc',), 'buttons': ('right',), 'seconds': .04},
                        {'buttons': ('left',), 'seconds': .03},
                    ]) as action:
                        action.result(timeout=2)
        args = context.Process.call_args.kwargs['args']
        self.assertEqual(list(args[3]), [0, 1, 0])
        writer.send.assert_not_called()
        writer.close.assert_called_once_with()
        monitor.join.assert_called_once_with()
        self.assertNotIn(('button', 'left', True), [event[1:] for event in self.backend.events])

    def test_capture_and_cancel_keep_single_owner_and_release_before_unlock(self):
        backend = ConcurrentBackend()
        with Minecraft(_backend=backend, _clock=backend.clock) as game:
            with game.sequence_async([
                {'buttons': ('right',), 'seconds': 4},
                {'buttons': ('left',), 'seconds': .03},
            ]) as action:
                self.assertTrue(backend.pressed.wait(2))
                game.frame()
                self.assertEqual(backend.observed_inputs[-1], {('button', 'right')})
                with self.assertRaisesRegex(boundary.ControlError, 'owns this session'):
                    game.press('e')
                action.cancel()
        self.assertFalse(backend.held)
        self.assertEqual(backend.unlocked_inputs, set())
        self.assertNotIn(('button', 'left', True), [event[1:] for event in backend.events])

    def test_capture_failure_aborts_remaining_sequence(self):
        backend = ConcurrentBackend()
        with Minecraft(_backend=backend, _clock=backend.clock) as game:
            with game.sequence_async([
                {'buttons': ('right',), 'seconds': 4},
                {'buttons': ('left',), 'seconds': .03},
            ]) as action:
                self.assertTrue(backend.pressed.wait(2))
                with patch.object(backend, 'frame', side_effect=OSError('capture failed')):
                    with self.assertRaisesRegex(OSError, 'capture failed'):
                        game.frame()
                self.assertTrue(action.finished.wait(2))
        self.assertFalse(backend.held)
        self.assertNotIn(('button', 'left', True), [event[1:] for event in backend.events])


if __name__ == '__main__':
    unittest.main()

