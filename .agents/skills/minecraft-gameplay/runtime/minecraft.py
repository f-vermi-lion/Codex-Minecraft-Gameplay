# Copyright 2026 Wuyang Zhou and Tianyu Wei
# SPDX-License-Identifier: Apache-2.0

"""Code-execution API above the Minecraft-only Windows input boundary."""
from concurrent.futures import Future
import math
import multiprocessing as MP
from pathlib import Path
import threading
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


class _InputAction:
    """Scoped background input. Exiting always cancels and joins the worker."""

    def __init__(self, game, operation):
        self.game = game
        self.operation = operation
        self.cancel_event = threading.Event()
        self.ready = threading.Event()
        self.finished = threading.Event()
        self.future = Future()
        self.thread = threading.Thread(target=self._run, name='minecraft-input', daemon=True)
        self.entered = False
        self.closed = False

    def __enter__(self):
        if self.entered:
            raise RuntimeError('Input action contexts cannot be reused.')
        self.game._start_action(self)
        self.entered = True
        return self

    def _run(self):
        try:
            # Thread.start can be interrupted after spawning the thread. Do
            # not send input until the session confirms a successful start.
            self.ready.wait()
            if self.cancel_event.is_set():
                raise boundary.ActionCancelled('Input action cancelled.')
            self.future.set_result(self.operation(self.cancel_event))
        except BaseException as exc:
            self.future.set_exception(exc)
        finally:
            self.finished.set()

    def cancel(self):
        """Request release at the next boundary check; result/exit waits for it."""
        self.cancel_event.set()

    def done(self):
        return self.future.done()

    def result(self, timeout=None):
        if not self.entered:
            raise RuntimeError('Use hold_async as a context manager.')
        return self.future.result(timeout=timeout)

    def __exit__(self, exc_type, exc, traceback):
        if self.closed:
            return False
        self.cancel()
        interrupted = None
        try:
            # A KeyboardInterrupt during join must not hand the session to a
            # new action while the old worker still holds an input.
            while not self.finished.is_set():
                try:
                    self.finished.wait(.05)
                except BaseException as error:
                    interrupted = error
                    self.cancel()
            self.thread.join()
            try:
                self.future.result()
            except boundary.ActionCancelled:
                pass
            except BaseException:
                if exc_type is None:
                    raise
            if interrupted is not None and exc_type is None:
                raise interrupted
        finally:
            self.game._finish_action(self)
            self.closed = True
        return False


class _SteeredAction(_InputAction):
    """Mouse updates are requests to the existing worker, never direct input."""

    def __init__(self, game, operation, steering):
        super().__init__(game, operation)
        self._steering = steering

    def steer(self, dx, dy):
        with self.game._state_lock:
            self.game._require_active()
            if (not self.entered or self.closed or self.game._action is not self
                    or self.cancel_event.is_set() or self.done()):
                raise boundary.ControlError('Mouse steering requires a running action context.')
            self._steering.submit(dx, dy)


class Minecraft:
    """Persistent target and composable actions for agent-authored Python code."""

    def __init__(self, hwnd=None, focus=False, _backend=None, _clock=time):
        self.backend = _backend if _backend is not None else boundary.Windows()
        self.target = self.backend.choose(hwnd)
        self.clock = _clock
        self.focus_on_enter = focus
        self._use_watchdogs = _backend is None
        self._mutex = None
        self._state_lock = threading.RLock()
        self._observation_lock = threading.Lock()
        self._action = None
        self._closing = False
        self._owner_thread = None

    def __enter__(self):
        with self._state_lock:
            if self._mutex is not None:
                raise RuntimeError('Minecraft session is already active.')
            self._mutex = self.backend.lock()
            try:
                if self.focus_on_enter:
                    self.backend.focus(self.target)
                self.backend.guard(self.target)
            except BaseException:
                self.backend.unlock(self._mutex)
                self._mutex = None
                raise
            self._closing = False
            self._owner_thread = threading.get_ident()
        return self

    def __exit__(self, exc_type, exc, traceback):
        with self._state_lock:
            if self._mutex is None:
                return False
            if self._owner_thread != threading.get_ident():
                raise RuntimeError('Close Minecraft on the thread that opened it.')
            self._closing = True
            action = self._action
        try:
            if action is not None:
                action.__exit__(exc_type, exc, traceback)
        finally:
            with self._state_lock:
                mutex, self._mutex = self._mutex, None
                self.backend.unlock(mutex)
                self._owner_thread = None
        return False

    def _require_active(self):
        with self._state_lock:
            if self._mutex is None or self._closing:
                raise RuntimeError('Use Minecraft as an active context manager.')

    def _start_action(self, action):
        with self._state_lock:
            self._require_active()
            if self._action is not None:
                raise boundary.ControlError('Another input action owns this session; finish its context first.')
            self._action = action
            try:
                action.thread.start()
            except BaseException:
                action.cancel()
                self._action = None
                raise
            finally:
                action.ready.set()

    def _finish_action(self, action):
        with self._state_lock:
            if self._action is action:
                self._action = None

    def _cancel_action(self):
        with self._state_lock:
            if self._action is not None:
                self._action.cancel()

    def _observe(self, operation):
        try:
            with self._observation_lock:
                self._require_active()
                return operation()
        except BaseException:
            self._cancel_action()
            raise

    def focus(self):
        self._require_active()
        def focus_target(cancel_event):
            if cancel_event.is_set():
                raise boundary.ActionCancelled('Input action cancelled.')
            self.backend.focus(self.target)
            self.backend.guard(self.target)
        with _InputAction(self, focus_target) as action:
            return action.result()

    def frame(self):
        return self._observe(lambda: self.backend.frame(self.target))

    def capture(self, path, max_width=7680):
        self._require_active()
        if not 320 <= max_width <= 7680:
            raise ValueError('max_width must be between 320 and 7680.')
        return self._observe(lambda: self.backend.capture(self.target, Path(path), max_width))

    def wait(self, seconds):
        self._require_active()
        seconds = _positive_seconds(seconds)
        deadline = self.clock.monotonic() + seconds
        try:
            while self.clock.monotonic() < deadline:
                self._require_active()
                self.backend.guard(self.target)
                self.clock.sleep(max(0.0, min(0.05, deadline - self.clock.monotonic())))
            self.backend.guard(self.target)
        except BaseException:
            self._cancel_action()
            raise

    def _run_chunk(self, keys, buttons, seconds, dx, dy, cancel_event):
        if cancel_event.is_set():
            raise boundary.ActionCancelled('Input action cancelled.')
        if not self._use_watchdogs or not (keys or buttons):
            return boundary.perform(
                self.backend, self.target, keys, buttons, seconds, dx, dy, self.clock,
                cancel_event=cancel_event)

        context = MP.get_context('spawn')
        reader, writer = context.Pipe(duplex=False)
        ownership = context.RawArray('b', len(keys) + len(buttons))
        monitor = context.Process(
            target=boundary.watchdog,
            args=(reader, keys, buttons, ownership, seconds + 2.0))
        try:
            monitor.start()
        except BaseException:
            reader.close()
            writer.close()
            raise
        reader.close()
        try:
            return boundary.perform(
                self.backend, self.target, keys, buttons, seconds, dx, dy,
                self.clock, ownership, cancel_event=cancel_event)
        finally:
            try:
                if not any(ownership):
                    writer.send('released')
            except (BrokenPipeError, EOFError, OSError):
                pass
            writer.close()
            # Keep the session's input ownership until backup cleanup has also
            # finished. A timed join could let an old watchdog release a new
            # action's keys after a failed release or slow child startup.
            monitor.join()

    def hold_async(self, keys=(), buttons=(), seconds=0.1, dx=0, dy=0):
        """Return a context for held input concurrent with frame/capture/analysis.

        Starts on entry, never queues another input, and cancels/joins on exit.
        The finite duration and independent watchdog apply just as for hold().
        """
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
        plan = list(zip(durations, x_parts, y_parts))
        for duration, x_part, y_part in plan:
            boundary.validate_action(keys, buttons, duration, x_part, y_part)
        return _InputAction(self, lambda cancel: self._hold_plan(keys, buttons, dx, dy, plan, cancel))

    def mine_async(self, seconds):
        """Hold only left-click continuously, for at most 45 seconds.

        Use after observing a stationary mining target. The normal exclusive
        input owner, pointer/target guards, cancellation, and watchdog apply.
        The caller must monitor the target and cancel when it changes.
        """
        self._require_active()
        seconds = _positive_seconds(seconds)
        boundary.validate_action([], ['left'], seconds, 0, 0)
        return _InputAction(
            self, lambda cancel: self._run_chunk([], ['left'], seconds, 0, 0, cancel))

    def _hold_plan(self, keys, buttons, dx, dy, plan, cancel_event):
        reports = []
        for duration, x_part, y_part in plan:
            reports.append(self._run_chunk(keys, buttons, duration, x_part, y_part, cancel_event))
        return {
            'chunks': len(reports),
            'elapsed_seconds': round(sum(item['elapsed_seconds'] for item in reports), 4),
            'keys': keys,
            'buttons': buttons,
            'mouse_delta': [dx, dy],
            'leases': reports,
        }

    def hold(self, keys=(), buttons=(), seconds=0.1, dx=0, dy=0):
        """Wait for one logical action, split into low-level safety leases."""
        with self.hold_async(keys=keys, buttons=buttons, seconds=seconds, dx=dx, dy=dy) as action:
            return action.result()

    def sequence_async(self, actions, *, preserve_inputs=False, steerable=False):
        """Run up to five seconds of transitions under one scoped watchdog.

        Each action uses the hold arguments and the unchanged input boundary.
        By default inputs are released between steps. preserve_inputs=True
        retains shared inputs until a step omits them, with the same guards
        and final release. Validation of the whole sequence precedes input.
        With steerable=True, action.steer(dx, dy) submits a latest-only mouse
        update to that same worker. It cannot change keys, buttons or duration.
        """
        self._require_active()
        if not isinstance(preserve_inputs, bool):
            raise ValueError('preserve_inputs must be a boolean.')
        if not isinstance(steerable, bool) or (steerable and not preserve_inputs):
            raise ValueError('steerable requires preserve_inputs=True.')
        steps = []
        total = 0.0
        for action in actions:
            if not isinstance(action, dict) or set(action) - {'keys', 'buttons', 'seconds', 'dx', 'dy'}:
                raise ValueError('Sequence actions must contain only hold arguments.')
            keys, buttons = list(action.get('keys', ())), list(action.get('buttons', ()))
            seconds = _positive_seconds(action.get('seconds', .1))
            dx, dy = _integer_delta(action.get('dx', 0), 'dx'), _integer_delta(action.get('dy', 0), 'dy')
            boundary.validate_action(keys, buttons, seconds, dx, dy)
            total += seconds
            if total > boundary.MAX_SECONDS + 1e-9:
                raise ValueError('A sequence must total at most five seconds.')
            steps.append((keys, buttons, seconds, dx, dy))
        if not steps:
            raise ValueError('A sequence must contain at least one action.')
        if steerable:
            steering = boundary.MouseSteering()
            return _SteeredAction(self, lambda cancel: self._run_sequence(
                steps, total, cancel, preserve_inputs, steering), steering)
        return _InputAction(self, lambda cancel: self._run_sequence(steps, total, cancel, preserve_inputs))

    def _run_sequence(self, steps, total, cancel_event, preserve_inputs=False, steering=None):
        keys = list(dict.fromkeys(key for step in steps for key in step[0]))
        buttons = list(dict.fromkeys(button for step in steps for button in step[1]))
        identities = [('key', key) for key in keys] + [('button', button) for button in buttons]
        reader = writer = monitor = None
        ownership = None
        if self._use_watchdogs and identities:
            context = MP.get_context('spawn')
            reader, writer = context.Pipe(duplex=False)
            ownership = context.RawArray('b', len(identities))
            monitor = context.Process(target=boundary.watchdog,
                                      args=(reader, keys, buttons, ownership, total + 2.0))
            try:
                monitor.start()
            except BaseException:
                reader.close()
                writer.close()
                raise
            reader.close()
        reports = []
        try:
            if preserve_inputs:
                return boundary.perform_continuous_sequence(
                    self.backend, self.target, steps, self.clock, ownership, cancel_event,
                    steering=steering)
            for step_keys, step_buttons, seconds, dx, dy in steps:
                if cancel_event.is_set():
                    raise boundary.ActionCancelled('Input action cancelled.')
                indices = ([identities.index(('key', key)) for key in step_keys]
                           + [identities.index(('button', button)) for button in step_buttons])
                mapped = _OwnershipView(ownership, indices) if ownership is not None else None
                reports.append(boundary.perform(
                    self.backend, self.target, step_keys, step_buttons, seconds,
                    dx, dy, self.clock, mapped, cancel_event=cancel_event))
            return {'steps': reports, 'elapsed_seconds': round(sum(r['elapsed_seconds'] for r in reports), 4)}
        finally:
            if monitor is not None:
                try:
                    if not any(ownership):
                        writer.send('released')
                except (BrokenPipeError, EOFError, OSError):
                    pass
                writer.close()
                monitor.join()

    def press(self, *keys, seconds=0.08):
        return self.hold(keys=keys, seconds=seconds)

    def look(self, dx, dy, seconds=0.08):
        return self.hold(seconds=seconds, dx=dx, dy=dy)

    def click(self, x, y, button='left', seconds=0.08):
        self._require_active()
        if button not in boundary.BUTTONS:
            raise ValueError('Unknown mouse button: ' + str(button))
        action = self.hold_async(buttons=(button,), seconds=seconds)
        hold_operation = action.operation
        def point_and_hold(cancel_event):
            if cancel_event.is_set():
                raise boundary.ActionCancelled('Input action cancelled.')
            self.backend.point(self.target, x, y)
            return hold_operation(cancel_event)
        action.operation = point_and_hold
        with action:
            return action.result()


class _OwnershipView:
    """Map a step's ownership slots onto the sequence watchdog's shared array."""

    def __init__(self, ownership, indices):
        self.ownership, self.indices = ownership, indices

    def __setitem__(self, index, value):
        self.ownership[self.indices[index]] = value


def stop():
    """Request persistent input stop without sending GUI input."""
    boundary.STOP_FILE.touch()


def reset_stop():
    """Clear a previously understood stop cause before a new observation."""
    if boundary.STOP_FILE.exists():
        boundary.STOP_FILE.unlink()
