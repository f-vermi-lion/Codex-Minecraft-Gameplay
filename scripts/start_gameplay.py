"""Start the Japanese gameplay session without changing global Codex settings."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys


def launch_arguments():
    root = Path(__file__).resolve().parents[1]
    vault = root.parent / 'Codexs-obsidian-vault'
    if not (vault / 'AGENTS.md').is_file():
        raise ValueError('Expected the sibling Codexs-obsidian-vault with AGENTS.md.')
    codex = shutil.which('codex.exe')
    if not codex:
        raise ValueError('codex.exe was not found on PATH. Use a Windows Codex CLI installation.')
    # Replace inherited extra writable roots, then add only the designated vault.
    # Shared-desktop compatibility is needed for game input; keep the sandbox on.
    return [
        codex, '--cd', str(root),
        '--sandbox', 'workspace-write', '--ask-for-approval', 'on-request', '--search',
        '--config', 'sandbox_workspace_write.writable_roots=[]',
        '--add-dir', str(vault.resolve()),
        '--config', 'sandbox_workspace_write.network_access=false',
        '--config', 'windows.sandbox_private_desktop=false',
        'Read AGENTS.md and the Minecraft gameplay skill. Respond in Japanese. '
        'Read the designated Obsidian vault note. Observe Minecraft before input; '
        'aim for the Ender Dragon in singleplayer Survival Normal with verified pauses. '
        'Stop and report if ordinary desktop access is unavailable.',
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
