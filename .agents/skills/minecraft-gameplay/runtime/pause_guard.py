"""Confirm the observed Japanese Game Menu before leaving gameplay unattended.

The template is the title from the 1920 x 1009, GUI-scale-4 game window.
Other layouts fail closed. This helper sends input only through Minecraft.
"""
from pathlib import Path

from PIL import Image, ImageChops


TITLE_BOX = (832, 154, 1086, 198)
FRAME_SIZE = (1920, 1009)
_TITLE = Image.open(Path(__file__).with_name('pause_menu_ja.png')).convert('1')
_TITLE_COUNT = _TITLE.histogram()[255]


def is_game_menu(frame):
    """Recognize the title, including its empty background, at the known scale."""
    if frame.size != FRAME_SIZE:
        return False
    red, green, blue = frame.crop(TITLE_BOX).convert('RGB').split()
    lightest_floor = ImageChops.darker(ImageChops.darker(red, green), blue)
    white = lightest_floor.point(lambda v: 255 if v > 230 else 0, mode='1')
    overlap = ImageChops.logical_and(white, _TITLE).histogram()[255]
    extra = white.histogram()[255] - overlap
    return overlap >= _TITLE_COUNT * .98 and extra <= 20


def ensure_game_menu(game, *, max_escapes=3):
    """Close an inventory or submenu and verify an actual Game Menu frame.

    An already visible menu is preserved. Call with the original Minecraft API,
    outside any asynchronous input scope and inside its ownership context.
    """
    if not isinstance(max_escapes, int) or isinstance(max_escapes, bool) or max_escapes < 1:
        raise ValueError('max_escapes must be a positive integer')
    frame = game.frame()
    if is_game_menu(frame):
        return frame
    for _ in range(max_escapes):
        game.press('esc')
        game.wait(.2)
        frame = game.frame()
        if is_game_menu(frame):
            return frame
    raise RuntimeError('Game Menu was not confirmed; inspect the current Minecraft screen.')
