"""Compatibility CLI for the renamed Minecraft input boundary."""
import json
import multiprocessing as MP
import sys

from input_boundary import *  # noqa: F401,F403 - compatibility for existing callers


if __name__ == '__main__':
    MP.freeze_support()
    try:
        print(json.dumps(main(), indent=2))
    except (ControlError, ValueError, OSError, KeyboardInterrupt) as exc:
        print(json.dumps({'error': str(exc) or 'Interrupted'}), file=sys.stderr)
        sys.exit(1)
