# Copyright 2026 Wuyang Zhou and Tianyu Wei
# SPDX-License-Identifier: Apache-2.0

"""Tests for the code-execution API; no Win32 backend is constructed."""
import unittest

from PIL import Image

from minecraft import Minecraft
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


if __name__ == '__main__':
    unittest.main()
