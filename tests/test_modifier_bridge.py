import unittest
import test_editor
from refine.shortcuts import MODIFIER_BRIDGE, V2, Shortcuts


class ModifierBridgeTests(unittest.TestCase):
    def setUp(self):
        fixture = test_editor.EditorTests()
        fixture.setUp()
        self.session, self.view, self.content = fixture.session, fixture.view, fixture.content
        quick = self.content['interaction']['quickApply']
        quick['applyShortcut'] = {'kind': 'keyCombination', 'code': 'ShiftLeft', 'key': 'ShiftLeft', 'modifiers': [], 'label': 'Left Shift'}
        quick['dismissShortcut'] = {'kind': 'keyCombination', 'code': 'ControlRight', 'key': 'ControlRight', 'modifiers': [], 'label': 'Right Control'}
        self.session.capabilities = [V2, MODIFIER_BRIDGE]
        self.session.shortcuts = Shortcuts(quick, self.session.capabilities)
        self.bridge = self.session.modifier_bridge
        self.session.transport.commands.clear()

    def arm(self):
        self.bridge.poll()
        self.owner = self.bridge.owner_id
        self.bridge.receive({'type': 'modifierShortcutAvailability', 'state': {'ownerId': self.owner, 'available': True}})
        self.session.transport.commands.clear()

    def press(self, code='ShiftLeft', owner=None):
        self.bridge.receive({'type': 'modifierShortcutPressed', 'press': {'ownerId': owner or self.owner, 'code': code}})

    def test_old_refine_keeps_existing_unavailable_behavior_without_new_commands(self):
        self.session.capabilities = [V2]
        self.session.shortcuts = Shortcuts(self.content['interaction']['quickApply'], [V2])
        self.bridge.start()
        self.bridge.poll()
        self.assertEqual(self.session.transport.commands, [])
        self.assertIsNone(self.session.shortcuts.keys['apply'])
        self.assertTrue(self.session.shortcuts.messages)

    def test_requires_availability_then_uses_normal_action_and_busy_deduplication(self):
        self.bridge.poll()
        self.owner = self.bridge.owner_id
        self.session.transport.commands.clear()
        self.press()
        self.assertEqual(self.session.transport.commands, [])
        self.arm()
        self.assertEqual(self.session.shortcuts.keys['apply'], 'ShiftLeft')
        self.press('ShiftRight')
        self.assertEqual(self.session.transport.commands, [])
        self.press()
        self.press()
        actions = [c for c in self.session.transport.commands if c['type'] == 'performAction']
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['kind'], 'apply')

    def test_stale_owner_focus_source_and_selection_are_rejected(self):
        self.arm()
        self.press(owner='stale')
        self.session.has_focus = False
        self.press()
        self.session.has_focus = True
        self.view.count += 1
        self.press()
        self.view.count -= 1
        self.view.selection[0].b += 1
        self.press()
        self.assertEqual(self.session.transport.commands, [])

    def test_cursor_dismiss_cancels_without_dismissing_suggestion(self):
        self.arm()
        self.press('ControlRight')
        self.assertIsNone(self.session.activation.active)
        self.assertFalse(any(c['type'] == 'performAction' for c in self.session.transport.commands))

    def test_card_dismiss_uses_dismiss_action(self):
        self.session.show(self.content['suggestions'][0]['id'])
        self.arm()
        self.press('ControlRight')
        self.assertEqual(self.session.transport.commands[-1]['kind'], 'dismiss')

    def test_readonly_autocomplete_and_panels_cannot_apply(self):
        self.arm()
        self.view.readonly = True
        self.press()
        self.view.readonly = False
        self.view.is_auto_complete_visible = lambda: True
        self.press()
        self.view.is_auto_complete_visible = lambda: False
        self.view.active_panel = lambda: 'find'
        self.press()
        self.assertEqual(self.session.transport.commands, [])

    def test_disconnect_rearm_and_permission_denial_disable_old_owner(self):
        self.arm()
        old = self.owner
        self.bridge.receive({'type': 'modifierShortcutAvailability', 'state': {'ownerId': old, 'available': False}})
        self.press()
        self.assertIsNone(self.session.shortcuts.keys['apply'])
        self.bridge.stop()
        self.bridge.poll()
        self.assertNotEqual(old, self.bridge.owner_id)
        self.session.transport.commands.clear()
        self.press(owner=old)
        self.assertEqual(self.session.transport.commands, [])

    def test_overlay_cannot_clear_macro_or_snippet_block(self):
        self.arm()
        self.session.modifier_input_command('toggle_record_macro')
        self.session.modifier_input_command('insert_snippet')
        self.session.modifier_input_command('show_overlay')
        self.session.modifier_input_command('hide_overlay')
        self.assertEqual(self.session.modifier_input_blocks, {'macro', 'snippet'})
        self.assertIsNone(self.bridge.current())
        self.session.modifier_input_command('toggle_record_macro')
        self.assertIsNone(self.bridge.current())
        self.session.modifier_input_command('clear_fields')
        self.assertIsNotNone(self.bridge.current())
