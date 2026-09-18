# Copyright 2026 Wuyang Zhou and Tianyu Wei
# SPDX-License-Identifier: Apache-2.0

"""Code-execution API above the Minecraft-only Windows input boundary."""
import math
import multiprocessing as MP
from pathlib import Path
import time

import input_boundary as boundary


def _positive_seconds(value, label='seconds'):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value <= 0):
        raise ValueError('%s must be a positive finite number.' % label)
    return float(value)


def _integer_delta(value, label):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError('%s must be an integer.' % label)
    return value


def _split_total(total, count):
    previous = 0
    for index in range(1, count + 1):
        current = round(total * index / count)
        yield current - previous
        previous = current


def _split_seconds(total, count):
    previous = 0.0
    for index in range(1, count + 1):
        current = total * index / count
        yield round(current - previous, 12)
        previous = current


class Minecraft:
    """Persistent target and composable actions for agent-authored Python code."""

    def __init__(self, hwnd=None, focus=False, _backend=None, _clock=time):
        self.backend = _backend if _backend is not None else boundary.Windows()
        self.target = self.backend.choose(hwnd)
        self.clock = _clock
        self.focus_on_enter = focus
        self._use_watchdogs = _backend is None
        self._mutex = None

    def __enter__(self):
        if self._mutex is not None:
            raise RuntimeError('Minecraft session is already active.')
        self._mutex = self.backend.lock()
        try:
            if self.focus_on_enter:
                self.backend.focus(self.target)
            self.backend.guard(self.target)
        except Exception:
            self.backend.unlock(self._mutex)
            self._mutex = None
            raise
        return self

    def __exit__(self, exc_type, exc, traceback):
        mutex, self._mutex = self._mutex, None
        if mutex is not None:
            self.backend.unlock(mutex)
        return False

    def _require_active(self):
        if self._mutex is None:
            raise RuntimeError('Use Minecraft as a context manager.')

    def focus(self):
        self._require_active()
        self.backend.focus(self.target)
        self.backend.guard(self.target)

    def frame(self):
        self._require_active()
        return self.backend.frame(self.target)

    def capture(self, path, max_width=7680):
        self._require_active()
        if not 320 <= max_width <= 7680:
            raise ValueError('max_width must be between 320 and 7680.')
        return self.backend.capture(self.target, Path(path), max_width)

    def wait(self, seconds):
        self._require_active()
        seconds = _positive_seconds(seconds)
        deadline = self.clock.monotonic() + seconds
        while self.clock.monotonic() < deadline:
            self.backend.guard(self.target)
            self.clock.sleep(max(0.0, min(0.05, deadline - self.clock.monotonic())))
        self.backend.guard(self.target)

    def _run_chunk(self, keys, buttons, seconds, dx, dy):
        if not self._use_watchdogs or not (keys or buttons):
            return boundary.perform(
                self.backend, self.target, keys, buttons, seconds, dx, dy, self.clock)

        context = MP.get_context('spawn')
        reader, writer = context.Pipe(duplex=False)
        ownership = context.RawArray('b', len(keys) + len(buttons))
        monitor = context.Process(
            target=boundary.watchdog,
            args=(reader, keys, buttons, ownership, seconds + 2.0))
        monitor.start()
        reader.close()
        try:
            return boundary.perform(
                self.backend, self.target, keys, buttons, seconds, dx, dy,
                self.clock, ownership)
        finally:
            try:
                if not any(ownership):
                    writer.send('released')
            except (BrokenPipeError, EOFError, OSError):
                pass
            writer.close()
            monitor.join(1.0)

    def hold(self, keys=(), buttons=(), seconds=0.1, dx=0, dy=0):
        """Perform one logical action, split only into low-level safety leases."""
        self._require_active()
        keys, buttons = list(keys), list(buttons)
        seconds = _positive_seconds(seconds)
        dx, dy = _integer_delta(dx, 'dx'), _integer_delta(dy, 'dy')
        chunks = max(
            1,
            math.ceil(seconds / boundary.MAX_SECONDS),
            math.ceil(abs(dx) / boundary.MAX_MOUSE_DELTA),
            math.ceil(abs(dy) / boundary.MAX_MOUSE_DELTA),
        )
        if seconds / chunks < 0.02:
            raise ValueError('seconds is too short for the required safe mouse-motion chunks.')
        durations = list(_split_seconds(seconds, chunks))
        x_parts, y_parts = list(_split_total(dx, chunks)), list(_split_total(dy, chunks))
        reports = []
        for duration, x_part, y_part in zip(durations, x_parts, y_parts):
            reports.append(self._run_chunk(keys, buttons, duration, x_part, y_part))
        return {
            'chunks': len(reports),
            'elapsed_seconds': round(sum(item['elapsed_seconds'] for item in reports), 4),
            'keys': keys,
            'buttons': buttons,
            'mouse_delta': [dx, dy],
            'leases': reports,
        }

    def press(self, *keys, seconds=0.08):
        return self.hold(keys=keys, seconds=seconds)

    def look(self, dx, dy, seconds=0.08):
        return self.hold(seconds=seconds, dx=dx, dy=dy)

    def click(self, x, y, button='left', seconds=0.08):
        self._require_active()
        if button not in boundary.BUTTONS:
            raise ValueError('Unknown mouse button: ' + str(button))
        self.backend.point(self.target, x, y)
        return self.hold(buttons=(button,), seconds=seconds)


def stop():
    """Request persistent input stop without sending GUI input."""
    boundary.STOP_FILE.touch()


def reset_stop():
    """Clear a previously understood stop cause before a new observation."""
    if boundary.STOP_FILE.exists():
        boundary.STOP_FILE.unlink()
