"""Host-contract tests with an editor double; real Sublime smoke steps are in README."""
import copy
import json
from pathlib import Path
import sys
import types
import unittest


class Region:
    def __init__(self, a, b=None):
        self.a = a
        self.b = a if b is None else b
    def begin(self): return min(self.a, self.b)
    def end(self): return max(self.a, self.b)
    def empty(self): return self.a == self.b


class Selection(list):
    def add(self, region): self.append(region)


sublime = types.ModuleType('sublime')
sublime.Region = Region
sublime.scheduled = []
sublime.set_timeout = lambda fn, delay=0: sublime.scheduled.append(fn)
sublime.status_message = lambda message: None
for index, name in enumerate(('DRAW_NO_OUTLINE', 'DRAW_NO_FILL', 'DRAW_STIPPLED_UNDERLINE', 'DRAW_SOLID_UNDERLINE', 'DRAW_EMPTY', 'HIDE_ON_MOUSE_MOVE_AWAY')):
    setattr(sublime, name, 1 << index)
sys.modules['sublime'] = sublime
from refine.editor import Session
from refine.presentation import card


class FakeTransport:
    def __init__(self, store, dispatch, callback):
        self.commands = []
        self.disconnected = False
    def start(self): pass
    def send(self, command):
        self.commands.extend(command if isinstance(command, list) else [command])
        return True
    def stop(self): pass
    def disconnect(self): self.disconnected = True


class View:
    def __init__(self):
        self.text = '😀 She go home.'
        self.count = 0
        self.readonly = False
        self.regions = {}
        self.statuses = {}
        self.selection = Selection([Region(6)])
        self.undo_stack = []
        self.popup = ''
        self.session = None
        self.replace_count = 0
    def settings(self): return {}
    def match_selector(self, point, selector): return selector == 'text.plain'
    def id(self): return 1
    def buffer_id(self): return 1
    def is_valid(self): return True
    def size(self): return len(self.text)
    def substr(self, region): return self.text[region.begin():region.end()]
    def change_count(self): return self.count
    def erase_regions(self, key): self.regions.pop(key, None)
    def add_regions(self, key, regions, *args, **kwargs): self.regions[key] = regions
    def set_status(self, key, value): self.statuses[key] = value
    def erase_status(self, key): self.statuses.pop(key, None)
    def sel(self): return self.selection
    def visible_region(self): return Region(0, len(self.text))
    def is_read_only(self): return self.readonly
    def is_auto_complete_visible(self): return False
    def window(self): return self
    def active_view(self): return self
    def show_popup(self, html, **kwargs):
        if self.popup:
            self.hide_popup()
        self.popup = html
        self.popup_options = kwargs
    def hide_popup(self):
        self.popup = ''
        callback = getattr(self, 'popup_options', {}).get('on_hide')
        self.popup_options = {}
        if callback:
            callback()
    def is_popup_visible(self): return bool(self.popup)
    def update_popup(self, html): self.popup = html
    def show(self, point): pass
    def run_command(self, name, args):
        assert name == 'refine_commit'
        self.session.commit(object(), args['transaction'])
    def replace(self, edit, region, text):
        self.undo_stack.append(self.text)
        self.replace_count += 1
        self.text = self.text[:region.begin()] + text + self.text[region.end():]
        self.count += 1
        self.session.modified()  # Sublime emits edit callbacks synchronously.


class EditorTests(unittest.TestCase):
    def setUp(self):
        sublime.scheduled.clear()
        self.view = View()
        self.session = Session(self.view, None, FakeTransport)
        self.view.session = self.session
        self.session.receive('connected', {'runResumed': False})
        fixture = json.loads((Path(__file__).resolve().parents[1] / 'vendor/protocol/vectors/state/golden-writing-session.json').read_text())
        self.content = copy.deepcopy(fixture['messages']['presentation']['event']['content'])
        self.content['documentRevision'] = self.session.document.snapshot['revision']
        suggestion = self.content['suggestions'][0]
        suggestion['activationRange'] = {'location': 3, 'length': 12}
        suggestion['highlightRanges'] = [{'location': 7, 'length': 2}]
        self.content['suggestions'] = [suggestion]
        self.session.receive('event', {'type': 'presentationContentReplaced', 'checkId': 'check', 'content': self.content})

    def apply_event(self):
        suggestion = self.content['suggestions'][0]
        self.session.action('apply', suggestion['id'])
        action = self.session.transport.commands[-1]
        self.assertEqual(action['type'], 'performAction')
        return {'type': 'applyRequested', 'transactionId': 'tx', 'actionId': action['actionId'], 'request': {
            'expectedRevision': self.content['documentRevision'], 'sourceId': 'document', 'edits': [
                {'range': {'location': 10, 'length': 4}, 'expectedText': 'home', 'replacement': 'outside'},
                {'range': {'location': 7, 'length': 2}, 'expectedText': 'go', 'replacement': 'goes'}]}}

    def test_apply_is_one_mutation_and_duplicate_transaction_does_not_repeat(self):
        event = self.apply_event()
        self.session.receive('event', event)
        self.assertEqual(self.view.text, '😀 She goes outside.')
        self.assertEqual(self.view.replace_count, 1)
        self.assertEqual(self.session.receipts['tx']['status'], 'applied')
        self.session.receive('event', event)
        self.assertEqual(self.view.replace_count, 1)
        self.assertEqual(self.view.undo_stack, ['😀 She go home.'])
        self.view.text = self.view.undo_stack.pop()
        self.view.count += 1
        self.session.modified()
        self.assertEqual(self.session.document.text, '😀 She go home.')
        self.assertNotEqual(self.session.document.snapshot['revision'], self.content['documentRevision'])

    def test_typing_before_apply_rejects_stale_revision(self):
        event = self.apply_event()
        self.view.text += ' More.'
        self.view.count += 1
        self.session.receive('event', event)
        self.assertEqual(self.view.replace_count, 0)
        self.assertEqual(self.session.receipts['tx']['reason'], 'staleRevision')

    def test_expected_text_mismatch_and_readonly_do_not_mutate(self):
        event = self.apply_event()
        event['request']['edits'][-1]['expectedText'] = 'zz'
        self.session.receive('event', event)
        self.assertEqual(self.view.replace_count, 0)
        self.assertEqual(self.session.receipts['tx']['reason'], 'textMismatch')
        self.view.readonly = True
        event = self.apply_event()
        event['transactionId'] = 'readonly'
        self.session.receive('event', event)
        self.assertEqual(self.session.receipts['readonly']['reason'], 'readOnly')
        self.assertEqual(self.view.replace_count, 0)

    def test_unsolicited_apply_never_mutates(self):
        event = self.apply_event()
        event['actionId'] = 'unknown'
        self.session.receive('event', event)
        self.assertEqual(self.view.replace_count, 0)
        self.assertEqual(self.session.receipts['tx']['status'], 'unavailable')

    def test_reconnect_restores_receipt_before_snapshot_then_attention(self):
        self.session.receive('event', self.apply_event())
        self.session.receive('disconnected', 'offline')
        self.session.transport.commands.clear()
        self.session.receive('connected', {'runResumed': True})
        self.assertEqual([c['type'] for c in self.session.transport.commands], ['completeApply', 'replaceDocument', 'updateAttention'])
        self.assertEqual(self.view.replace_count, 1)
        self.session.receive('disconnected', 'offline')
        self.session.transport.commands.clear()
        self.session.receive('connected', {'runResumed': False})
        self.assertEqual([c['type'] for c in self.session.transport.commands], ['openDocument', 'updateAttention'])
        self.assertEqual(self.session.receipts, {})

    def test_stale_presentation_cannot_restore_highlights(self):
        self.view.text += 'x'
        self.view.count += 1
        self.session.modified()
        self.session.receive('event', {'type': 'presentationContentReplaced', 'checkId': 'old', 'content': self.content})
        self.assertIsNone(self.session.content)
        self.assertFalse(self.view.regions)

    def test_scalar_splitting_highlight_disconnects(self):
        self.content['suggestions'][0]['highlightRanges'] = [{'location': 1, 'length': 1}]
        self.session.receive('event', {'type': 'presentationContentReplaced', 'checkId': 'bad', 'content': self.content})
        self.assertTrue(self.session.transport.disconnected)
        self.assertFalse(self.view.regions)

    def test_manual_selection_uses_utf16_and_typing_only_sends_snapshot(self):
        self.view.selection = Selection([Region(0, 1)])
        self.session.check()
        self.assertEqual(self.session.transport.commands[-1]['intent']['selection']['range'], {'location': 0, 'length': 2})
        self.view.text += '!'
        self.view.count += 1
        self.session.modified()
        self.session.transport.commands.clear()
        self.session.sync()
        self.assertEqual([c['type'] for c in self.session.transport.commands], ['replaceDocument', 'updateAttention'])

    def test_explain_command_opens_card_and_streams_text(self):
        suggestion_id = self.content['suggestions'][0]['id']
        self.session.action('explain', suggestion_id)
        self.assertEqual(self.session.open_suggestion, suggestion_id)
        action_id = self.session.transport.commands[-1]['actionId']
        self.session.receive('event', {'type': 'explanationReplaced', 'actionId': action_id,
                                      'update': {'status': 'streaming', 'text': 'Subject and verb must agree.'}})
        self.assertIn('Subject and verb must agree.', self.view.popup)

    def test_explain_popup_click_keeps_owner_and_displays_stream(self):
        suggestion_id = self.content['suggestions'][0]['id']
        self.session.show(suggestion_id)
        self.view.popup_options['on_navigate']('explain')
        self.assertIn('Explaining…', self.view.popup)
        self.assertEqual(self.session.open_suggestion, suggestion_id)
        action_id = self.session.transport.commands[-1]['actionId']
        for status, text in [('streaming', 'Subject and verb'), ('completed', 'Subject and verb must agree.')]:
            self.session.receive('event', {'type': 'explanationReplaced', 'actionId': action_id,
                                          'update': {'status': status, 'text': text}})
            self.assertIn(text, self.view.popup)
        self.assertNotIn(action_id, self.session.actions)

    def test_report_busy_rejection_retry_and_confirmation(self):
        suggestion = self.content['suggestions'][0]
        if 'report' not in suggestion['availableActions']:
            suggestion['availableActions'].append('report')
        self.session.show(suggestion['id'])
        self.session.action('report')
        request = self.session.transport.commands[-1]
        self.assertIn('Reporting…', self.view.popup)
        self.assertNotIn('href="report"', self.view.popup)
        count = len(self.session.transport.commands)
        self.session.action('report')
        self.assertEqual(len(self.session.transport.commands), count)
        self.session.event({'type': 'actionRejected', 'actionId': request['actionId'], 'reason': 'engineUnavailable'})
        self.assertIn('Retry report', self.view.popup)
        self.assertIn('could not complete', self.view.popup)
        self.session.action('report')
        self.session.event({'type': 'actionCompleted', 'actionId': self.session.transport.commands[-1]['actionId']})
        self.assertIn('Reported', self.view.popup)
        self.assertIn('Report sent.', self.view.popup)
        count = len(self.session.transport.commands)
        self.session.action('report')
        self.assertEqual(len(self.session.transport.commands), count)

    def test_explanation_metadata_formatting_and_duplicate_guard(self):
        self.session.action('explain', self.content['suggestions'][0]['id'])
        request = self.session.transport.commands[-1]
        count = len(self.session.transport.commands)
        self.session.action('explain')
        self.assertEqual(len(self.session.transport.commands), count)
        self.session.event({'type': 'explanationReplaced', 'actionId': request['actionId'],
                            'update': {'status': 'started', 'attribution': {
                                'languageDisplayName': 'Arabic', 'modelDisplayName': 'Explanation Model', 'textDirection': 'rtl'}}})
        self.session.event({'type': 'explanationReplaced', 'actionId': request['actionId'],
                            'update': {'status': 'completed', 'text': '**Agreement**\n\n- Use `goes`.'}})
        self.assertIn('Arabic · Explanation Model', self.view.popup)
        self.assertIn('dir="rtl"', self.view.popup)
        self.assertIn('<strong>Agreement</strong>', self.view.popup)
        self.assertIn('<li>Use <code>goes</code>.</li>', self.view.popup)
        self.assertNotIn('Explaining…', self.view.popup)

    def test_explanation_failure_allows_retry_and_closed_card_finishes(self):
        self.session.action('explain', self.content['suggestions'][0]['id'])
        action_id = self.session.transport.commands[-1]['actionId']
        self.session.event({'type': 'explanationReplaced', 'actionId': action_id,
                            'update': {'status': 'unavailable', 'reason': 'engineUnavailable'}})
        self.assertIn('Retry explain', self.view.popup)
        self.assertNotIn('Explaining…', self.view.popup)
        self.session.action('explain')
        action_id = self.session.transport.commands[-1]['actionId']
        self.view.hide_popup()
        self.session.event({'type': 'explanationReplaced', 'actionId': action_id,
                            'update': {'status': 'completed', 'text': 'Finished.'}})
        self.assertNotIn(action_id, self.session.actions)
        self.assertFalse(self.view.popup)

    def test_action_feedback_does_not_leak_to_new_revision(self):
        self.session.action('dismiss', self.content['suggestions'][0]['id'])
        action_id = self.session.transport.commands[-1]['actionId']
        self.view.text += '!'
        self.view.count += 1
        self.session.refresh()
        self.session.event({'type': 'actionRejected', 'actionId': action_id, 'reason': 'stale'})
        self.assertFalse(self.session.feedback)

    def test_explicit_check_is_sent_once_per_connection(self):
        self.session.check()
        self.session.sync()
        self.session.sync()
        self.assertEqual(sum(c['type'] == 'requestCheck' for c in self.session.transport.commands), 1)
        self.session.receive('disconnected', 'offline')
        self.session.receive('connected', {'runResumed': True})
        self.assertEqual(sum(c['type'] == 'requestCheck' for c in self.session.transport.commands), 2)

    def test_exception_after_mutation_is_indeterminate_and_not_retried(self):
        event = self.apply_event()
        original_replace = self.view.replace
        def throwing_replace(*args):
            original_replace(*args)
            raise ValueError('Simulated failure after host mutation')
        self.view.replace = throwing_replace
        self.session.receive('event', event)
        self.assertEqual(self.session.receipts['tx']['status'], 'indeterminate')
        self.session.receive('event', event)
        self.assertEqual(self.view.replace_count, 1)

    def test_click_opens_immediately_but_selection_and_other_popups_are_respected(self):
        self.session.show_clicked_suggestion()
        self.assertEqual(self.session.open_suggestion, self.content['suggestions'][0]['id'])
        self.assertEqual(self.view.popup_options['flags'], 0)
        self.view.hide_popup()
        self.view.selection = Selection([Region(3, 8)])
        self.session.show_clicked_suggestion()
        self.assertFalse(self.view.popup)
        self.view.selection = Selection([Region(6)])
        self.view.show_popup('Another plugin')
        self.session.show_clicked_suggestion()
        self.assertEqual(self.view.popup, 'Another plugin')

    def test_click_does_not_open_stale_or_unfocused_suggestions(self):
        self.session.has_focus = False
        self.session.show_clicked_suggestion()
        self.assertFalse(self.view.popup)
        self.session.has_focus = True
        self.view.text += '!'
        self.view.count += 1
        self.session.show_clicked_suggestion()
        self.assertFalse(self.view.popup)

    def test_hover_card_allows_moving_toward_it_and_updates_keep_ownership(self):
        suggestion_id = self.content['suggestions'][0]['id']
        self.session.show(suggestion_id, hover=True)
        self.assertEqual(self.view.popup_options['flags'], sublime.HIDE_ON_MOUSE_MOVE_AWAY)
        self.session.show(suggestion_id, update=True)
        self.assertEqual(self.session.open_suggestion, suggestion_id)
        self.assertEqual(self.view.popup_options['flags'], sublime.HIDE_ON_MOUSE_MOVE_AWAY)
        self.view.hide_popup()
        self.assertIsNone(self.session.open_suggestion)

    def test_card_groups_explanation_before_footer_and_shows_available_shortcuts(self):
        html = card(self.content['suggestions'][0], self.content, 'A reason', self.session.shortcuts)
        self.assertLess(html.index('href="explain"'), html.index('<div class="diff"'))
        self.assertLess(html.index('A reason'), html.index('<div class="actions"'))
        self.assertIn('class="control primary"', html)
        for action in ('apply', 'dismiss'):
            if self.session.shortcuts.keys[action]:
                self.assertIn('(' + self.session.shortcuts.labels[action] + ')', html)

    def test_popup_escapes_source_and_explanation(self):
        suggestion = self.content['suggestions'][0]
        suggestion['diff'] = [{'kind': 'insert', 'text': '<a href="report">bad</a>'}]
        html = card(suggestion, self.content, '<script>no</script>')
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('&lt;a·href=', html)
