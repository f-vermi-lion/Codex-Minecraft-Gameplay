"""Exploration alerts use synthetic screenshots and a fake game, never Win32."""
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from PIL import Image, ImageDraw
from survival_watch import SurvivalWatch, SurvivalAlert, lava_like_overlay, retreat_on_alert


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

    def test_background_flame_does_not_change_heart_measurement(self):
        raw = FakeGame(screen())
        draw = ImageDraw.Draw(raw.current)
        draw.rectangle((590, 852, 929, 860), fill=(255, 50, 5))
        draw.rectangle((920, 860, 929, 891), fill=(255, 50, 5))
        game = SurvivalWatch(raw)
        game.look(0, 100)
        self.assertEqual(len(raw.events), 1)

    def test_submerged_lava_alerts_without_heart_loss_or_orange_flames(self):
        submerged = screen()
        ImageDraw.Draw(submerged).rectangle((200, 160, 1700, 650), fill=(142, 25, 2))
        raw = FakeGame(submerged)
        game = SurvivalWatch(raw)
        with self.assertRaisesRegex(SurvivalAlert, 'submerged lava'):
            game.hold(buttons=('left',), seconds=.2)
        self.assertEqual(len(raw.events), 1)
        self.assertIs(game.last_frame, submerged)

    def test_submerged_detection_scales_with_frame(self):
        submerged = screen()
        ImageDraw.Draw(submerged).rectangle((200, 160, 1700, 650), fill=(142, 25, 2))
        self.assertTrue(lava_like_overlay(submerged.resize((1600, 841))))

    def test_small_lava_patch_or_dark_netherrack_does_not_match_submerged_view(self):
        frame = screen()
        self.assertFalse(lava_like_overlay(frame))
        ImageDraw.Draw(frame).rectangle((800, 300, 1100, 500), fill=(142, 25, 2))
        self.assertFalse(lava_like_overlay(frame))

    def test_retreat_waits_for_mining_scope_release_then_pauses_and_reraises(self):
        raw = FakeGame()

        @contextmanager
        def mining_scope():
            raw.events.append(('mining',))
            try:
                yield
            finally:
                raw.events.append(('released',))

        with patch('survival_watch.ensure_game_menu', side_effect=lambda game: game.events.append(('paused',))):
            with self.assertRaisesRegex(SurvivalAlert, 'lava'):
                with retreat_on_alert(raw, seconds=.8):
                    with mining_scope():
                        raise SurvivalAlert('lava')
        self.assertEqual(raw.events, [
            ('mining',), ('released',),
            ('hold', {'keys': ('s',), 'seconds': .8}), ('paused',)])

    def test_retreat_does_not_handle_unrelated_or_boundary_failures(self):
        raw = FakeGame()
        with patch('survival_watch.ensure_game_menu') as pause:
            with self.assertRaisesRegex(RuntimeError, 'focus lost'):
                with retreat_on_alert(raw, seconds=.8):
                    raise RuntimeError('focus lost')
        self.assertEqual(raw.events, [])
        pause.assert_not_called()

    def test_retreat_attempts_pause_if_recovery_input_is_rejected(self):
        raw = FakeGame()
        with patch.object(raw, 'hold', side_effect=RuntimeError('focus lost')):
            with patch('survival_watch.ensure_game_menu') as pause:
                with self.assertRaisesRegex(RuntimeError, 'focus lost'):
                    with retreat_on_alert(raw, seconds=.8):
                        raise SurvivalAlert('lava')
                pause.assert_called_once_with(raw)

    def test_retreat_requires_a_positive_finite_duration_before_body(self):
        raw = FakeGame()
        for seconds in (0, -1, float('inf'), float('nan'), True):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                with retreat_on_alert(raw, seconds=seconds):
                    self.fail('invalid duration reached excavation')
        self.assertEqual(raw.events, [])

    def test_successful_excavation_sends_no_recovery_input(self):
        raw = FakeGame()
        with patch('survival_watch.ensure_game_menu') as pause:
            with retreat_on_alert(raw, seconds=.8):
                pass
        self.assertEqual(raw.events, [])
        pause.assert_not_called()


if __name__ == '__main__':
    unittest.main()
