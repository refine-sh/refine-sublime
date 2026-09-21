import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_editor as fixtures
from refine.colors import FALLBACK_SCOPES, SCOPES, fill_scope, scopes_for


class ColorTests(unittest.TestCase):
    def test_custom_colors_update_without_touching_user_scheme(self):
        view = fixtures.View()
        view.settings = lambda: {'color_scheme': 'Packages/Theme/Example.sublime-color-scheme'}
        with tempfile.TemporaryDirectory() as root:
            user = Path(root) / 'User'
            user.mkdir()
            original = user / 'Example.sublime-color-scheme'
            original.write_text('{"globals":{"background":"#123456"}}')
            with patch.object(fixtures.sublime, 'packages_path', return_value=root, create=True):
                colors = {'grammarColor': '#FF0000', 'fluencyColor': '#0000FF'}
                self.assertEqual(scopes_for(view, colors), SCOPES)
                generated = Path(root) / 'Refine Color Overrides/Example.sublime-color-scheme'
                rules = {r['scope']: r for r in json.loads(generated.read_text())['rules']}
                self.assertEqual(rules[SCOPES['grammar']]['foreground'], '#FF0000')
                for kind in SCOPES:
                    fill = fill_scope(SCOPES[kind])
                    self.assertNotIn('foreground', rules[fill])
                    self.assertFalse(fill.startswith(SCOPES[kind] + '.'))
                    self.assertEqual(rules[fill]['background'], rules[SCOPES[kind]]['foreground'] + '26')
                self.assertEqual(rules[SCOPES['mixed']]['foreground'], '#7F007F')
                stamp = generated.stat().st_mtime_ns
                scopes_for(view, colors)
                self.assertEqual(generated.stat().st_mtime_ns, stamp)
                colors['grammarColor'] = '#00FF00'
                scopes_for(view, colors)
                self.assertIn('#00FF00', generated.read_text())
                self.assertEqual(original.read_text(), '{"globals":{"background":"#123456"}}')

    def test_legacy_scheme_keeps_theme_fallback(self):
        view = fixtures.View()
        view.settings = lambda: {'color_scheme': 'Legacy.tmTheme'}
        self.assertEqual(scopes_for(view, {}), FALLBACK_SCOPES)
        self.assertEqual(fill_scope(FALLBACK_SCOPES['grammar']), 'region.redish')

    def test_auto_prepares_light_and_dark_schemes(self):
        view = fixtures.View()
        view.settings = lambda: {'color_scheme': 'auto'}
        preferences = {'light_color_scheme': 'Light.sublime-color-scheme',
                       'dark_color_scheme': 'Dark.sublime-color-scheme'}
        with tempfile.TemporaryDirectory() as root:
            with patch.object(fixtures.sublime, 'packages_path', return_value=root, create=True), \
                    patch.object(fixtures.sublime, 'load_settings', return_value=preferences, create=True):
                self.assertEqual(scopes_for(view, {'grammarColor': '#112233', 'fluencyColor': '#445566'}), SCOPES)
            directory = Path(root) / 'Refine Color Overrides'
            self.assertEqual((directory / preferences['light_color_scheme']).read_text(),
                             (directory / preferences['dark_color_scheme']).read_text())
