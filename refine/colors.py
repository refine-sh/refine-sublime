"""Add Refine-only scopes to Sublime's current JSON color scheme."""
import json
from pathlib import Path

import sublime


FALLBACK_SCOPES = {'grammar': 'region.redish', 'fluency': 'region.bluish', 'mixed': 'region.purplish'}
SCOPES = {kind: 'refine.mark.' + kind for kind in FALLBACK_SCOPES}


def scheme_rules(highlight):
    grammar, fluency = highlight['grammarColor'], highlight['fluencyColor']
    mixed = '#' + ''.join('{:02X}'.format(
        (int(grammar[i:i + 2], 16) + int(fluency[i:i + 2], 16)) // 2)
        for i in (1, 3, 5))
    rules = []
    for kind, color in (('grammar', grammar), ('fluency', fluency), ('mixed', mixed)):
        rules.append({'scope': SCOPES[kind], 'foreground': color})
        # A background-only scope keeps the text readable. Keep it separate
        # from the underline scope so it cannot inherit its foreground color.
        rules.append({'scope': fill_scope(SCOPES[kind]), 'background': color + '26'})
    return {'rules': rules}


def scopes_for(view, highlight):
    scheme = view.settings().get('color_scheme', '')
    if scheme == 'auto':
        preferences = sublime.load_settings('Preferences.sublime-settings')
        # Prepare both schemes so an OS appearance change needs no new check.
        schemes = [preferences.get('light_color_scheme', ''),
                   preferences.get('dark_color_scheme', '')]
    else:
        schemes = [scheme]
    if not all(name.endswith('.sublime-color-scheme') for name in schemes):
        return FALLBACK_SCOPES
    try:
        # Sublime merges same-named JSON schemes across packages. Keep generated
        # rules in our own package; never edit the user's scheme or preferences.
        directory = Path(sublime.packages_path()) / 'Refine Color Overrides'
        directory.mkdir(exist_ok=True)
        data = json.dumps(scheme_rules(highlight), indent=2) + '\n'
        for name in schemes:
            path = directory / Path(name).name
            if not path.exists() or path.read_text(encoding='utf-8') != data:
                path.write_text(data, encoding='utf-8')
    except OSError as error:
        print('Refine: unable to update highlight colors: {}'.format(error))
        return FALLBACK_SCOPES
    return SCOPES


def fill_scope(scope):
    return scope.replace('refine.mark.', 'refine.fill.', 1) if scope.startswith('refine.mark.') else scope
