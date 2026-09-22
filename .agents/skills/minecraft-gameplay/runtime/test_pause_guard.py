import unittest
from unittest.mock import Mock

from PIL import Image

from pause_guard import FRAME_SIZE, TITLE_BOX, _TITLE, ensure_game_menu, is_game_menu


def menu_frame():
    frame = Image.new('RGB', FRAME_SIZE, (40, 20, 10))
    frame.paste(_TITLE.convert('RGB'), TITLE_BOX)
    return frame


class PauseGuardTests(unittest.TestCase):
    def test_recognizes_title(self):
        self.assertTrue(is_game_menu(menu_frame()))

    def test_rejects_gameplay_and_bright_background(self):
        self.assertFalse(is_game_menu(Image.new('RGB', FRAME_SIZE)))
        self.assertFalse(is_game_menu(Image.new('RGB', FRAME_SIZE, 'white')))

    def test_rejects_other_window_size(self):
        self.assertFalse(is_game_menu(menu_frame().resize((1600, 841))))

    def test_rejects_displaced_title(self):
        frame = Image.new('RGB', FRAME_SIZE)
        frame.paste(_TITLE.convert('RGB'), (TITLE_BOX[0] + 12, TITLE_BOX[1]))
        self.assertFalse(is_game_menu(frame))

    def test_already_paused_is_not_resumed(self):
        game = Mock()
        game.frame.return_value = menu_frame()
        self.assertTrue(is_game_menu(ensure_game_menu(game)))
        game.press.assert_not_called()

    def test_inventory_closure_is_not_mistaken_for_pause(self):
        game = Mock()
        game.frame.side_effect = [Image.new('RGB', FRAME_SIZE, (30, 30, 30)),
                                  Image.new('RGB', FRAME_SIZE, (80, 20, 10)),
                                  menu_frame()]
        self.assertTrue(is_game_menu(ensure_game_menu(game)))
        self.assertEqual(game.press.call_count, 2)
        self.assertTrue(all(call.args == ('esc',) for call in game.press.call_args_list))

    def test_unrecognized_screen_has_bounded_retries(self):
        game = Mock()
        game.frame.return_value = Image.new('RGB', FRAME_SIZE)
        with self.assertRaisesRegex(RuntimeError, 'not confirmed'):
            ensure_game_menu(game)
        self.assertEqual(game.press.call_count, 3)

    def test_input_failure_propagates(self):
        game = Mock()
        game.frame.return_value = Image.new('RGB', FRAME_SIZE)
        game.press.side_effect = RuntimeError('focus lost')
        with self.assertRaisesRegex(RuntimeError, 'focus lost'):
            ensure_game_menu(game)
        self.assertEqual(game.press.call_count, 1)

    def test_rejects_invalid_retry_count_before_input(self):
        for invalid in (0, -1, True, 1.5):
            game = Mock()
            with self.assertRaises(ValueError):
                ensure_game_menu(game, max_escapes=invalid)
            game.press.assert_not_called()


if __name__ == '__main__':
    unittest.main()
