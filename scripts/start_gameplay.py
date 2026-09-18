"""Start the Japanese gameplay session without changing global Codex settings."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys


def launch_arguments():
    root = Path(__file__).resolve().parents[1]
    codex = shutil.which('codex.exe')
    if not codex:
        raise ValueError('codex.exe was not found on PATH. Use a Windows Codex CLI installation.')
    # Shared-desktop compatibility is needed for game input; keep file and network
    # boundaries on and grant no writable directory outside this repository.
    return [
        codex, '--cd', str(root),
        '--sandbox', 'workspace-write', '--ask-for-approval', 'on-request', '--search',
        '--config', 'sandbox_workspace_write.writable_roots=[]',
        '--config', 'sandbox_workspace_write.network_access=false',
        '--config', 'windows.sandbox_private_desktop=false',
        'Read AGENTS.md and use the Minecraft gameplay skill. Respond in Japanese. '
        'Observe Minecraft, then autonomously pursue the requested in-game goal within '
        'the repository, GUI, and game-rule boundaries. Improve the repository tools '
        'when useful. Stop and report if ordinary desktop access is unavailable.',
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Show launch arguments without starting Codex.')
    args = parser.parse_args()
    try:
        command = launch_arguments()
        if args.check:
            print(json.dumps(command, indent=2))
            return 0
        return subprocess.run(command, shell=False).returncode
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
