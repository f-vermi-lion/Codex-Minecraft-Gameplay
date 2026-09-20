"""Exploration alerts use synthetic screenshots and a fake game, never Win32."""
import unittest
from PIL import Image, ImageDraw
from survival_watch import SurvivalWatch, SurvivalAlert


def screen(red_width=250, burning=False):
    image = Image.new('RGB', (1920, 1009), (70, 25, 20))
    draw = ImageDraw.Draw(image)
    draw.rectangle((590, 860, 590 + red_width, 879), fill=(240, 30, 25))
    if burning:
        draw.rectangle((0, 510, 470, 807), fill=(161, 83, 3))
        draw.rectangle((1450, 510, 1919, 807), fill=(153, 67, 5))
    return image


class FakeGame:
    def __init__(self, after=None):
        self.current = screen()
        self.after = after
        self.events = []

    def frame(self):
        return self.current

    def hold(self, **kwargs):
        self.events.append(('hold', kwargs))
        if self.after is not None:
            self.current = self.after
        return 'performed'

    def wait(self, seconds):
        self.events.append(('wait', seconds))
        if self.after is not None:
            self.current = self.after


class SurvivalWatchTests(unittest.TestCase):
    def test_damage_during_mining_interrupts_before_next_action(self):
        raw = FakeGame(screen(red_width=170))
        game = SurvivalWatch(raw)
        with self.assertRaises(SurvivalAlert):
            game.hold(buttons=('left',), seconds=1.2)
            game.press('w')
        self.assertEqual(len(raw.events), 1)
        self.assertEqual(raw.events[0][1]['seconds'], 1.2)

    def test_existing_damage_prevents_input(self):
        raw = FakeGame()
        game = SurvivalWatch(raw)
        raw.current = screen(red_width=170)
        with self.assertRaises(SurvivalAlert):
            game.look(100, 0)
        self.assertEqual(raw.events, [])

    def test_fire_can_alert_before_heart_loss(self):
        raw = FakeGame(screen(burning=True))
        game = SurvivalWatch(raw)
        with self.assertRaisesRegex(SurvivalAlert, 'fire'):
            game.hold(keys=('w',), seconds=.2)

    def test_wait_stops_at_first_observation(self):
        raw = FakeGame(screen(red_width=170))
        game = SurvivalWatch(raw)
        with self.assertRaises(SurvivalAlert):
            game.wait(2)
        self.assertEqual(raw.events, [('wait', .2)])

    def test_large_hold_is_rejected_before_input(self):
        raw = FakeGame()
        game = SurvivalWatch(raw)
        with self.assertRaises(ValueError):
            game.hold(buttons=('left',), seconds=2)
        self.assertEqual(raw.events, [])

    def test_healthy_actions_preserve_arguments_and_result(self):
        raw = FakeGame()
        game = SurvivalWatch(raw)
        result = game.hold(keys=('w',), seconds=.3, dx=12, dy=-3)
        self.assertEqual(result, 'performed')
        self.assertEqual(raw.events[0][1], dict(keys=('w',), buttons=(), seconds=.3, dx=12, dy=-3))

    def test_missing_hud_is_rejected(self):
        raw = FakeGame()
        raw.current = Image.new('RGB', (1920, 1009), 'black')
        with self.assertRaises(SurvivalAlert):
            SurvivalWatch(raw)


if __name__ == '__main__':
    unittest.main()
