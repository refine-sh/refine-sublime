"""Exercise shipped key dispatch against a live Session fixture."""
import json
from pathlib import Path
import unittest
import test_editor as fixtures


class KeyboardTests(unittest.TestCase):
    setUp = fixtures.EditorTests.setUp
    def dispatch(self, key):
        root = Path(__file__).resolve().parents[1]
        keymap = root / 'Default.sublime-keymap'
        bindings = json.loads(keymap.read_text()) if keymap.exists() else []
        for binding in bindings:
            if binding['keys'] != [key]:
                continue
            if binding['command'] == 'refine_shortcut' and self.session.shortcut_action(key):
                self.session.perform_shortcut(key)
                return True
        return False

    def test_configured_tab_applies_current_suggestion(self):
        self.session.transport.commands.clear()
        self.assertTrue(self.dispatch('tab'), 'Configured Apply shortcut has no active editor binding')
        self.assertEqual(self.session.transport.commands[-1]['kind'], 'apply')

    def test_configured_escape_dismisses_current_suggestion(self):
        self.session.show(self.content['suggestions'][0]['id'])
        self.session.transport.commands.clear()
        self.assertTrue(self.dispatch('escape'), 'Configured Dismiss shortcut has no active editor binding')
        self.assertEqual(self.session.transport.commands[-1]['kind'], 'dismiss')

    def configure(self, apply, dismiss, capabilities):
        from refine.shortcuts import Shortcuts
        self.session.capabilities = capabilities
        quick = self.content['interaction']['quickApply']
        quick['applyShortcut'], quick['dismissShortcut'] = apply, dismiss
        self.session.shortcuts = Shortcuts(quick, capabilities)

    def test_standalone_shift_unavailable_without_disabling_other_actions(self):
        from refine.shortcuts import V2
        self.configure({'kind': 'keyCombination', 'code': 'ShiftLeft', 'key': 'ShiftLeft', 'modifiers': [], 'label': 'Left Shift'},
                       {'kind': 'keyCombination', 'code': 'Escape', 'key': 'Escape', 'modifiers': [], 'label': 'Esc'}, [V2])
        self.assertIsNone(self.session.shortcuts.keys['apply'])
        self.assertIn('Left Shift', self.session.shortcuts.messages[0])
        self.assertFalse(self.dispatch('tab'))
        self.session.show(self.content['suggestions'][0]['id'])
        self.assertTrue(self.dispatch('escape'))
        self.assertEqual(self.session.transport.commands[-1]['kind'], 'dismiss')
        self.session.action('apply', self.content['suggestions'][0]['id'])
        self.assertEqual(self.session.transport.commands[-1]['kind'], 'apply')

    def test_custom_combination_exact_modifiers_and_no_legacy_fallback(self):
        from refine.shortcuts import V2
        self.configure({'kind': 'keyCombination', 'code': 'ArrowRight', 'key': 'ArrowRight', 'modifiers': ['option'], 'label': '⌥→'},
                       {'kind': 'keyCombination', 'code': 'Escape', 'key': 'Escape', 'modifiers': [], 'label': 'Esc'}, [V2])
        self.assertFalse(self.dispatch('tab'))
        self.assertFalse(self.dispatch('right'))
        self.assertFalse(self.dispatch('alt+shift+right'))
        self.assertTrue(self.dispatch('alt+right'))
        self.assertEqual(self.session.transport.commands[-1]['kind'], 'apply')

    def test_cursor_escape_cancels_activation_without_dismissing_suggestion(self):
        self.session.transport.commands.clear()
        self.assertTrue(self.dispatch('escape'))
        self.assertFalse(self.session.transport.commands)
        self.assertFalse(self.dispatch('tab'))
        self.assertIsNotNone(self.session.content)
        self.session.event({'type': 'presentationContentReplaced', 'checkId': 'check', 'content': self.content})
        self.assertFalse(self.dispatch('tab'))
        self.session.event({'type': 'presentationContentReplaced', 'checkId': 'new-check', 'content': self.content})
        self.assertTrue(self.dispatch('tab'))

    def test_caret_move_rearms_after_escape_but_selection_does_not(self):
        self.dispatch('escape')
        self.view.selection = fixtures.Selection([fixtures.Region(7)])
        self.session.selection_modified()
        self.assertTrue(self.session.shortcut_action('tab'))
        self.view.selection = fixtures.Selection([fixtures.Region(6, 8)])
        self.session.selection_modified()
        self.assertFalse(self.session.shortcut_action('tab'))

    def test_disabled_quick_apply_still_allows_open_card_actions(self):
        self.content['interaction']['quickApply']['enabled'] = False
        self.session.update_activation()
        self.assertFalse(self.dispatch('tab'))
        self.session.show(self.content['suggestions'][0]['id'])
        self.assertTrue(self.dispatch('tab'))

    def test_busy_shortcut_is_consumed_without_duplicate_request(self):
        self.session.transport.commands.clear()
        self.assertTrue(self.dispatch('tab'))
        self.assertTrue(self.dispatch('tab'))
        self.assertEqual(sum(c['type'] == 'performAction' for c in self.session.transport.commands), 1)

    def test_stale_disconnected_unfocused_and_autocomplete_keys_propagate(self):
        self.session.has_focus = False
        self.assertFalse(self.dispatch('tab'))
        self.session.has_focus = True
        self.view.is_auto_complete_visible = lambda: True
        self.assertFalse(self.dispatch('tab'))
        self.view.is_auto_complete_visible = lambda: False
        self.session.connected = False
        self.assertFalse(self.dispatch('tab'))
        self.session.connected = True
        self.view.count += 1
        self.assertFalse(self.dispatch('tab'))

    def test_shortcut_conflict_disables_keys_but_not_pointer_action(self):
        from refine.shortcuts import V2
        binding = {'kind': 'keyCombination', 'code': 'ArrowRight', 'key': 'ArrowRight', 'modifiers': ['option'], 'label': '⌥→'}
        self.configure(binding, binding, [V2])
        self.assertFalse(self.dispatch('alt+right'))
        self.assertTrue(self.session.shortcuts.messages)
        self.session.action('apply', self.content['suggestions'][0]['id'])
        self.assertEqual(self.session.transport.commands[-1]['kind'], 'apply')

    def test_unsupported_gesture_warns_and_never_falls_back(self):
        from refine.shortcuts import V2
        self.configure({'kind': 'modifierDoubleTap', 'key': 'AltRight', 'label': 'Double-tap Right Option'},
                       {'kind': 'keyCombination', 'code': 'Escape', 'key': 'Escape', 'modifiers': [], 'label': 'Esc'}, [V2])
        self.assertFalse(self.dispatch('tab'))
        self.assertTrue(self.session.shortcuts.messages)

    def test_caret_activation_renders_and_clears_visible_feedback(self):
        self.view.selection = fixtures.Selection([fixtures.Region(0)])
        self.session.selection_modified()
        self.view.selection = fixtures.Selection([fixtures.Region(7)])
        self.session.selection_modified()
        self.assertTrue(self.view.regions.get('refine.active'))
        self.assertTrue(self.view.regions.get('refine.tip'))
        self.assertIn('to apply', self.view.statuses['refine'])
        self.assertIsNone(self.session.open_suggestion)
        self.session.perform_shortcut('escape')
        self.assertFalse(self.view.regions.get('refine.active'))
        self.assertFalse(self.view.regions.get('refine.tip'))
        self.view.selection = fixtures.Selection([fixtures.Region(8)])
        self.session.selection_modified()
        self.assertTrue(self.view.regions.get('refine.active'))
        self.view.selection = fixtures.Selection([fixtures.Region(0)])
        self.session.selection_modified()
        self.assertFalse(self.view.regions.get('refine.active'))
        self.assertNotIn('to apply', self.view.statuses['refine'])

    def test_highlight_only_and_open_card_suppress_cursor_tip(self):
        self.content['interaction']['quickApply']['activationStyle'] = 'highlightChanges'
        self.session.render()
        self.assertTrue(self.view.regions.get('refine.active'))
        self.assertFalse(self.view.regions.get('refine.tip'))
        self.session.show(self.content['suggestions'][0]['id'])
        self.assertFalse(self.view.regions.get('refine.active'))
        self.assertFalse(self.view.regions.get('refine.tip'))

    def test_active_highlight_replaces_underline_and_focus_loss_restores_it(self):
        import copy
        suggestion = self.content['suggestions'][0]
        other = copy.deepcopy(suggestion)
        other['id'] = 'other'
        other['highlightRanges'] = [{'location': 10, 'length': 4}]
        self.content['suggestions'].append(other)
        key = 'refine.' + suggestion['kind']
        for style in ('underline', 'dashedUnderline'):
            self.content['appearance']['highlight']['style'] = style
            self.session.has_focus = True
            self.session.render()
            self.assertTrue(self.view.regions['refine.active'])
            self.assertEqual(len(self.view.regions[key]), 1)
            self.assertEqual(self.view.regions[key][0].begin(), 9)
            self.session.has_focus = False
            self.session.render_activation()
            self.assertFalse(self.view.regions.get('refine.active'))
            self.assertEqual(len(self.view.regions[key]), 2)

    def test_generated_keymap_is_current_and_only_context_owned(self):
        import importlib.util
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('keymap_generator', root / 'scripts/generate_keymap.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        actual = json.loads((root / 'Default.sublime-keymap').read_text())
        self.assertEqual(actual, list(module.bindings()))
        self.assertEqual(len({tuple(binding['keys']) for binding in actual}), len(actual))
