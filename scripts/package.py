#!/usr/bin/env python3
"""Build a self-contained package without tests, source documents, or local data."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
output = ROOT / 'dist/Refine.sublime-package'
output.parent.mkdir(exist_ok=True)
files = [ROOT / name for name in ('Refine.py', '.python-version', 'Default.sublime-commands',
                                 'Context.sublime-menu', 'Default.sublime-keymap', 'README.md', 'LICENSE')]
files += sorted((ROOT / 'refine').glob('*.py'))
files += sorted((ROOT / 'vendor/protocol/schema').glob('*.json'))
files += [ROOT / 'vendor/protocol/LICENSE']
with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as package:
    for path in files:
        package.write(path, str(path.relative_to(ROOT)))
print(output)
