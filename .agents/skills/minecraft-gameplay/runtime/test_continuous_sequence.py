"""Mock-only safety tests for preserving inputs across bounded transitions."""
import threading
import unittest
from unittest.mock import Mock, patch

import input_boundary as boundary
from minecraft import Minecraft
from test_input_boundary import FakeClock, TrackingOwnership
from test_minecraft import RuntimeBackend, ConcurrentBackend


class TransitionBackend(RuntimeBackend):
    def __init__(self, clock):
        super().__init__(clock)
        self.physical = set()
        self.pointer_bad_at = None
        self.on_guard = lambda: None

    def guard(self, target):
        super().guard(target)
        self.on_guard()

    def guard_pointer(self, target):
        self.guard(target)
        if self.pointer_bad_at is not None and self.clock.now >= self.pointer_bad_at:
            raise boundary.ControlError('Pointer left Minecraft')

    def down(self, vk):
        active = set(self.physical)
        active.update(boundary.KEYS[name][1] if kind == 'key' else boundary.BUTTONS[name][2]
                      for kind, name in self.held)
        if active & {0xa0, 0xa1}:
            active.add(0x10)
        if active & {0xa2, 0xa3}:
            active.add(0x11)
        return vk in active

    def preflight(self, target, keys, buttons, **owned):
        self.preflight_calls += 1
        boundary.Windows.preflight(self, target, keys, buttons, **owned)


class ContinuousSequenceTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.backend = TransitionBackend(self.clock)

    def session(self):
        return Minecraft(_backend=self.backend, _clock=self.clock)

    def run_steps(self, actions):
        with self.session() as game:
            with game.sequence_async(actions, preserve_inputs=True) as action:
                return action.result(timeout=2)

    def inputs(self):
        return [event for event in self.backend.events if event[1] != 'move']

    def test_shield_stays_down_through_camera_movement_and_pause_key(self):
        result = self.run_steps([
            {'keys': ['esc'], 'buttons': ['right'], 'seconds': .04},
            {'buttons': ['right'], 'seconds': .3, 'dx': -31, 'dy': 17},
            {'keys': ['w'], 'buttons': ['right'], 'seconds': .1},
            {'keys': ['esc'], 'buttons': ['right'], 'seconds': .04},
        ])
        right = [e for e in self.inputs() if e[1:3] == ('button', 'right')]
        self.assertEqual([e[3] for e in right], [True, False])
        self.assertEqual(right[0][0], 0)
        self.assertAlmostEqual(right[1][0], .48)
        self.assertEqual(len(result['steps']), 4)
        moves = [e for e in self.backend.events if e[1] == 'move']
        self.assertEqual((sum(e[2] for e in moves), sum(e[3] for e in moves)), (-31, 17))
        self.assertFalse(self.backend.held)
        self.assertFalse(self.backend.locked)

    def test_omitted_inputs_release_before_attack_and_reacquire_afterward(self):
        self.run_steps([
            {'buttons': ['right'], 'seconds': .1},
            {'buttons': ['left'], 'seconds': .02},
            {'buttons': ['right'], 'seconds': .1},
        ])
        self.assertEqual([e[1:] for e in self.inputs()], [
            ('button', 'right', True), ('button', 'right', False),
            ('button', 'left', True), ('button', 'left', False),
            ('button', 'right', True), ('button', 'right', False)])

    def test_every_step_and_preserve_option_validate_before_input(self):
        with self.session() as game:
            for steps in ([], [{'seconds': 3}, {'seconds': 3}],
                          [{'buttons': ['right']}, {'keys': ['bad']}],
                          [{'seconds': float('nan')}], [{'dx': True}]):
                with self.subTest(steps=steps), self.assertRaises(ValueError):
                    game.sequence_async(steps, preserve_inputs=True)
            with self.assertRaises(ValueError):
                game.sequence_async([{}], preserve_inputs=1)
        self.assertEqual(self.inputs(), [])

    def test_owned_modifiers_persist_but_physical_modifiers_stop_next_press(self):
        self.run_steps([
            {'keys': ['shift', 'ctrl'], 'buttons': ['right'], 'seconds': .1},
            {'keys': ['shift', 'ctrl', 'w'], 'buttons': ['right'], 'seconds': .1},
        ])
        for vk in (0xa1, 0xa3, 0x12, 0x5b, 0x5c):
            with self.subTest(vk=vk):
                self.setUp()
                self.backend.on_guard = lambda vk=vk: (
                    self.backend.physical.add(vk) if self.clock.now >= .05 else None)
                with self.assertRaisesRegex(boundary.ControlError, 'physical keys'):
                    self.run_steps([
                        {'keys': ['shift', 'ctrl'], 'buttons': ['right'], 'seconds': .1},
                        {'keys': ['shift', 'ctrl', 'e'], 'buttons': ['right'], 'seconds': .1},
                    ])
                self.assertFalse(self.backend.held)
                self.assertNotIn(('key', 'e', True), [e[1:] for e in self.inputs()])

    def test_focus_pointer_stop_and_cancellation_release_retained_inputs(self):
        for failure in ('focus', 'pointer', 'stop', 'cancel'):
            with self.subTest(failure=failure):
                self.setUp()
                cancel = threading.Event()
                def check():
                    if self.clock.now >= .15:
                        if failure == 'cancel':
                            cancel.set()
                        elif failure == 'stop':
                            raise boundary.ControlError('Stopped: F8 or stop file')
                self.backend.on_guard = check
                if failure == 'focus':
                    self.backend.lose_focus_at = .15
                if failure == 'pointer':
                    self.backend.pointer_bad_at = .15
                ownership = TrackingOwnership(3)  # w, right, left
                with self.assertRaises(boundary.ControlError):
                    boundary.perform_continuous_sequence(
                        self.backend, self.backend.target,
                        [([], ['right'], .1, 0, 0), (['w'], ['right'], .2, 0, 0),
                         ([], ['left'], .1, 0, 0)], self.clock, ownership, cancel)
                self.assertFalse(self.backend.held)
                self.assertEqual(list(ownership), [0, 0, 0])
                self.assertNotIn(('button', 'left', True), [e[1:] for e in self.inputs()])

    def test_uncertain_new_press_releases_it_and_retained_shield(self):
        self.backend.fail_press = ('button', 'left')
        ownership = TrackingOwnership(2)
        with self.assertRaisesRegex(boundary.ControlError, 'Uncertain press'):
            boundary.perform_continuous_sequence(
                self.backend, self.backend.target,
                [([], ['right'], .1, 0, 0), ([], ['right', 'left'], .1, 0, 0)],
                self.clock, ownership)
        self.assertFalse(self.backend.held)
        self.assertEqual(list(ownership), [0, 0])
        self.assertIn((1, 1), ownership.writes)

    def test_watchdog_tracks_retained_button_and_failed_release_until_join(self):
        context = Mock()
        reader, writer, monitor = Mock(), Mock(), Mock()
        context.Pipe.return_value = (reader, writer)
        context.RawArray.side_effect = lambda kind, count: TrackingOwnership(count)
        context.Process.return_value = monitor
        self.backend.fail_release = ('button', 'right')
        monitor.join.side_effect = lambda: self.assertTrue(self.backend.locked)
        with patch('minecraft.MP.get_context', return_value=context):
            with self.session() as game:
                game._use_watchdogs = True
                with self.assertRaisesRegex(boundary.ControlError, 'release every input'):
                    with game.sequence_async([
                        {'keys': ['esc'], 'buttons': ['right'], 'seconds': .04},
                        {'buttons': ['right'], 'seconds': .1},
                        {'keys': ['w'], 'seconds': .1},
                    ], preserve_inputs=True) as action:
                        action.result(timeout=2)
        args = context.Process.call_args.kwargs['args']
        self.assertEqual(args[1:3], (['esc', 'w'], ['right']))
        self.assertEqual(list(args[3]), [0, 0, 1])
        self.assertEqual(args[3].writes.count((2, 1)), 1)
        writer.send.assert_not_called()
        writer.close.assert_called_once_with()
        monitor.join.assert_called_once_with()
        self.assertNotIn(('key', 'w', True), [e[1:] for e in self.inputs()])

    def test_parallel_observation_failure_cancels_before_owner_unlocks(self):
        backend = ConcurrentBackend()
        with Minecraft(_backend=backend, _clock=backend.clock) as game:
            with game.sequence_async([
                {'buttons': ['right'], 'seconds': 4},
                {'buttons': ['left'], 'seconds': .1},
            ], preserve_inputs=True) as action:
                self.assertTrue(backend.pressed.wait(2))
                game.frame()
                self.assertEqual(backend.observed_inputs[-1], {('button', 'right')})
                with self.assertRaisesRegex(boundary.ControlError, 'owns this session'):
                    game.press('e')
                with patch.object(backend, 'frame', side_effect=OSError('capture failed')):
                    with self.assertRaises(OSError):
                        game.frame()
                self.assertTrue(action.finished.wait(2))
        self.assertFalse(backend.held)
        self.assertEqual(backend.unlocked_inputs, set())
        self.assertNotIn(('button', 'left', True), [e[1:] for e in backend.events])


if __name__ == '__main__':
    unittest.main()
