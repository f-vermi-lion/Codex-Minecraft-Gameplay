"""Optional screenshot-based monitoring for exploration, above the input boundary.

The HUD regions match the currently observed 1920 x 1009 gameplay layout.
Use only while the survival HUD is visible, not in inventories or menus.
Call the original Minecraft object's pause operation in a finally block.
"""
import math


class SurvivalAlert(RuntimeError):
    pass


def _pixels(image):
    reader = getattr(image, 'get_flattened_data', image.getdata)
    return list(reader())


def hud_red(frame):
    """Fraction of red heart pixels in the observed HUD region."""
    w, h = frame.size
    crop = frame.convert('RGB').crop((
        round(w * 590 / 1920), round(h * 852 / 1009),
        round(w * 930 / 1920), round(h * 892 / 1009)))
    pixels = _pixels(crop)
    return sum(r > 170 and g < 100 and b < 110 for r, g, b in pixels) / len(pixels)


def fire_like_overlay(frame):
    """Conservative alert for orange covering both lower sides of the view."""
    w, h = frame.size
    fractions = []
    for left, right in ((.02, .23), (.77, .98)):
        crop = frame.convert('RGB').crop((
            round(w * left), round(h * .50), round(w * right), round(h * .80)))
        pixels = _pixels(crop.resize((42, 30)))
        fractions.append(sum(r > 140 and 35 < g < 210 and b < 70
                             and r > 1.25 * g for r, g, b in pixels) / len(pixels))
    return min(fractions) > .15


class SurvivalWatch:
    """Check screenshots before and after each exploration action.

    This is a heuristic, not a guarantee of safe terrain. It never sends input
    except through the supplied Minecraft API and never handles GUI recovery.
    Long held inputs are rejected: splitting mining clicks would reset progress.
    Waits are sampled every 0.2 seconds, excluding screenshot overhead.
    """

    def __init__(self, game, *, max_hold=1.5, damage_fraction=.025):
        self._positive(max_hold)
        self._positive(damage_fraction)
        self.raw = game
        self.max_hold = max_hold
        self.damage_fraction = damage_fraction
        initial = game.frame()
        self.peak_red = hud_red(initial)
        if self.peak_red < .05:
            raise SurvivalAlert('Survival hearts are not clearly visible; inspect the screen.')
        self._check(initial)

    @staticmethod
    def _positive(value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError('Duration and thresholds must be positive finite numbers.')

    def _check(self, frame):
        red = hud_red(frame)
        if self.peak_red - red > self.damage_fraction:
            raise SurvivalAlert('Heart display decreased; stop and inspect immediately.')
        if fire_like_overlay(frame):
            raise SurvivalAlert('Possible fire or lava overlay; stop and inspect immediately.')
        self.peak_red = max(self.peak_red, red)
        return frame

    def frame(self):
        return self._check(self.raw.frame())

    def hold(self, keys=(), buttons=(), seconds=.1, dx=0, dy=0):
        self._positive(seconds)
        if seconds > self.max_hold:
            raise ValueError('Observe between shorter exploration holds.')
        self.frame()
        result = self.raw.hold(keys=keys, buttons=buttons, seconds=seconds, dx=dx, dy=dy)
        self.frame()
        return result

    def press(self, *keys, seconds=.08):
        return self.hold(keys=keys, seconds=seconds)

    def look(self, dx, dy, seconds=.08):
        return self.hold(seconds=seconds, dx=dx, dy=dy)

    def wait(self, seconds):
        self._positive(seconds)
        self.frame()
        remaining = seconds
        while remaining > 1e-9:
            step = min(.2, remaining)
            self.raw.wait(step)
            self.frame()
            remaining -= step

    def capture(self, path, max_width=7680):
        self.frame()
        return self.raw.capture(path, max_width=max_width)
