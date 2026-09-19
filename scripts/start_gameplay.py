"""Start the Japanese gameplay session without changing global Codex settings."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys


def launch_arguments():
    root = Path(__file__).resolve().parents[1]
    workspace = root.parent
    vault = workspace / 'Codexs-obsidian-vault'
    if not (workspace / 'AGENTS.md').is_file():
        raise ValueError('Expected the shared parent workspace to contain AGENTS.md.')
    if not (vault / 'AGENTS.md').is_file():
        raise ValueError('Expected the sibling Codexs-obsidian-vault with AGENTS.md.')
    codex = shutil.which('codex.exe')
    if not codex:
        raise ValueError('codex.exe was not found on PATH. Use a Windows Codex CLI installation.')
    # The common parent contains the gameplay repository, its designated vault,
    # and their shared AGENTS.md. Clear inherited extra roots and keep network
    # and shared-desktop settings explicit.
    return [
        codex, '--cd', str(workspace),
        '--sandbox', 'workspace-write', '--ask-for-approval', 'on-request', '--search',
        '--config', 'sandbox_workspace_write.writable_roots=[]',
        '--config', 'sandbox_workspace_write.network_access=false',
        '--config', 'windows.sandbox_private_desktop=false',
        'Follow the parent AGENTS.md. For gameplay, read '
        'Codex-Minecraft-Gameplay/AGENTS.md and use its Minecraft gameplay skill. '
        'Use Codexs-obsidian-vault/AGENTS.md for durable notes. Respond in Japanese. '
        'Observe Minecraft, then autonomously pursue the requested in-game goal within '
        'the workspace, GUI, and game-rule boundaries. Improve the repository tools '
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
