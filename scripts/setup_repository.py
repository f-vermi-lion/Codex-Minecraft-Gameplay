"""Validate the tracked Codex skill and install local ignore rules."""
# Copyright 2026 Wuyang Zhou and Tianyu Wei
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SKILL = '.agents/skills/minecraft-gameplay/SKILL.md'
BEGIN_IGNORE = '# BEGIN Minecraft Gameplay generated rules'
END_IGNORE = '# END Minecraft Gameplay generated rules'


def local_path(root, relative):
    path = root / relative
    # Keep generated files in this checkout, even when a parent is a link.
    path.resolve().relative_to(root)
    return path


def merge_ignore(existing, template):
    block = BEGIN_IGNORE + '\n' + template.strip() + '\n' + END_IGNORE
    if BEGIN_IGNORE in existing or END_IGNORE in existing:
        if existing.count(BEGIN_IGNORE) != 1 or existing.count(END_IGNORE) != 1:
            raise ValueError('The generated .gitignore block has conflicting markers.')
        start = existing.index(BEGIN_IGNORE)
        end = existing.index(END_IGNORE)
        if end < start:
            raise ValueError('The generated .gitignore block has reversed markers.')
        return existing[:start] + block + existing[end + len(END_IGNORE):]
    separator = '' if not existing else ('\n' if existing.endswith('\n') else '\n\n')
    return existing + separator + block + '\n'


def setup(root=ROOT):
    root = Path(root).resolve()
    source = local_path(root, SKILL).read_text(encoding='utf-8')
    if not source.startswith('---\n') or '\n---\n' not in source[4:]:
        raise ValueError('The gameplay skill is missing its YAML frontmatter.')
    ignore = local_path(root, '.gitignore')
    existing = ignore.read_text(encoding='utf-8') if ignore.exists() else ''
    template = local_path(root, 'gitignore.template').read_text(encoding='utf-8')
    merged = merge_ignore(existing, template)
    changed = []
    data = merged.encode('utf-8')
    if not ignore.exists() or ignore.read_bytes() != data:
        ignore.write_bytes(data)
        changed.append(ignore.relative_to(root).as_posix())
    return {'status': 'ready', 'updated': changed, 'gameplay_source': SKILL}


def main():
    try:
        print(json.dumps(setup(), indent=2))
    except (OSError, ValueError) as error:
        print('Setup failed: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
