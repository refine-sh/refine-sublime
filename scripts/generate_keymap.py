#!/usr/bin/env python3
"""Generate inert-until-owned bindings without writing the user's keymap."""
from pathlib import Path
import itertools
import json
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from refine.shortcuts import SPECIAL, PRINTABLE, MODIFIERS


def bindings():
    keys = sorted(set(SPECIAL.values()) | set(PRINTABLE))
    for size in range(5):
        for modifiers in itertools.combinations([native for _, native in MODIFIERS], size):
            for key in keys:
                if key in PRINTABLE and not set(modifiers) & {'ctrl', 'alt', 'super'}:
                    continue
                token = '+'.join(list(modifiers) + [key])
                yield {'keys': [token], 'command': 'refine_shortcut', 'args': {'key': token}, 'context': [
                    {'key': 'refine_shortcut', 'operand': token},
                    {'key': 'auto_complete_visible', 'operand': False},
                    {'key': 'overlay_visible', 'operand': False},
                    {'key': 'panel_has_focus', 'operand': False},
                    {'key': 'is_recording_macro', 'operand': False},
                    {'key': 'has_next_field', 'operand': False}]}


if __name__ == '__main__':
    (ROOT / 'Default.sublime-keymap').write_text('[\n' + ',\n'.join('  ' + json.dumps(binding, separators=(',', ':')) for binding in bindings()) + '\n]\n')
