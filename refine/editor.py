"""Editor-owned state. Every method runs on Sublime's main thread."""
import sublime
from html import escape

from .document import Document
from .protocol import identifier
from .transport import Transport
from .validation import ConformanceError
from .presentation import card
from .shortcuts import Shortcuts, QuickActivation
from .modifier_bridge import ModifierBridge
from .colors import FALLBACK_SCOPES, scopes_for, fill_scope

REGION_KEYS = ('refine.grammar', 'refine.fluency', 'refine.mixed', 'refine.active', 'refine.tip')


def syntax_for(view):
    if view.settings().get('is_widget') or view.settings().get('refine_enabled', True) is False:
        return None
    if view.match_selector(0, 'text.html.markdown'):
        return 'markdownDocumentHardLineBreaks'
    if view.match_selector(0, 'text.plain'):
        return 'plainText'
    return None


class Session:
    def __init__(self, view, store, transport_factory=Transport):
        self.view = view
        self.document = Document()
        self.transport = transport_factory(store, lambda fn: sublime.set_timeout(fn, 0), self.receive)
        self.connected = False
        self.closed = False
        self.content = None
        self.color_scopes = FALLBACK_SCOPES
        self.capabilities = []
        self.shortcuts = None
        self.activation = QuickActivation()
        self.check_id = None
        self.input_epoch = 0
        self.has_focus = True
        self.modifier_input_blocks = set()
        self.modifier_bridge = ModifierBridge(self)
        self.open_suggestion = None
        self.explanation = ''
        self.explanation_attribution = None
        self.feedback = {}
        self.actions = {}
        self.receipts = {}
        self.pending_check = None
        self.pending_check_sent = False
        self.pending_apply = None
        self.applying = False
        self.serial = 0
        self.attention_serial = 0
        self.sent_revision = None
        self.status = 'Refine: connecting…'
        self.refresh()
        self.view.set_status('refine', self.status)
        self.transport.start()

    def refresh(self, force=False):
        if self.closed or not self.view.is_valid():
            return False
        syntax = syntax_for(self.view)
        if not syntax:
            return False
        text = self.view.substr(sublime.Region(0, self.view.size()))
        changed = self.document.observe(text, syntax, self.view.change_count(), force)
        if changed:
            self.clear_presentation()
            if self.pending_check and self.pending_check['revision'] != self.document.snapshot['revision']:
                self.pending_check = None
        return changed

    def clear_presentation(self):
        self.input_epoch += 1
        self.modifier_bridge.invalidate()
        self.activation.cancel()
        self.shortcuts = None
        for key in REGION_KEYS:
            self.view.erase_regions(key)
        self.content = None
        if self.open_suggestion:
            self.view.hide_popup()
        self.open_suggestion = None
        self.explanation = ''
        self.explanation_attribution = None
        self.feedback.clear()
        # Apply requests can still arrive for a stale revision: reject them explicitly.
        self.actions = {key: value for key, value in self.actions.items() if value[0] == 'apply'}

    def close(self):
        self.closed = True
        self.modifier_bridge.stop()
        self.clear_presentation()
        self.view.erase_status('refine')
        self.transport.stop()

    def attach_view(self, view):
        if self.view.id() != view.id():
            for key in REGION_KEYS:
                self.view.erase_regions(key)
            if self.open_suggestion:
                self.view.hide_popup()
            self.open_suggestion = None
            self.view.erase_status('refine')
            self.view = view
            self.view.set_status('refine', self.status)
        self.modified()
        if self.content:
            self.render()

    def modified(self):
        if self.applying or self.closed:
            return
        try:
            self.refresh()
        except (ValueError, UnicodeError):
            self.close()
            self.view.set_status('refine', 'Refine: buffer exceeds 1 MiB or contains invalid Unicode')
            return
        self.serial += 1
        serial = self.serial
        def publish():
            if not self.closed and serial == self.serial:
                self.sync()
        # Coalesce source observation; checking/debounce policy belongs to Refine.
        sublime.set_timeout(publish, 150)

    def send(self, command):
        if self.connected and self.transport.send(command):
            return True
        self.connected = False
        return False

    def sync(self, resumed=False):
        if not self.connected or self.closed:
            return
        self.refresh()
        snapshot = self.document.snapshot
        if self.sent_revision != snapshot['revision']:
            command_type = 'replaceDocument' if self.sent_revision is not None or resumed else 'openDocument'
            if not self.send({'type': command_type, 'snapshot': snapshot}):
                return
            self.sent_revision = snapshot['revision']
        self.attention()
        if self.pending_check and not self.pending_check_sent and self.pending_check['revision'] == snapshot['revision']:
            # Keep until presentation arrives, so a disconnect can restore the explicit check.
            if self.send(self.pending_check):
                self.pending_check_sent = True
                self.status = 'Refine: checking…'
                self.view.set_status('refine', self.status)

    def attention(self):
        if not self.connected or not self.document.snapshot:
            return
        if self.view.change_count() != self.document.stamp:
            return
        coords = self.document.coordinates
        visible = self.view.visible_region()
        selections = self.view.sel()
        attention = {'sourceId': 'document', 'visibleRanges': []}
        if not visible.empty():
            attention['visibleRanges'] = [coords.range(visible.begin(), visible.end())]
        if selections:
            attention['caretOffset'] = coords.offsets[selections[0].b]
        self.send({'type': 'updateAttention', 'revision': self.document.snapshot['revision'], 'attention': attention})

    def selection_modified(self):
        self.input_epoch += 1
        self.update_activation(explicit=True)
        if self.content and self.view.change_count() == self.document.stamp:
            self.render()
        else:
            self.render_activation()
        self.attention_serial += 1
        serial = self.attention_serial
        sublime.set_timeout(lambda: self.attention() if not self.closed and serial == self.attention_serial else None, 100)

    def check(self):
        self.refresh()
        self.pending_check_sent = False
        self.pending_check = {'type': 'requestCheck', 'revision': self.document.snapshot['revision']}
        selections = self.view.sel()
        if len(selections) == 1 and not selections[0].empty():
            selection = selections[0]
            self.pending_check['intent'] = {'selection': {'sourceId': 'document',
                'range': self.document.coordinates.range(selection.begin(), selection.end())}}
        elif len(selections) > 1:
            sublime.status_message('Refine: select one range, or clear selections to check the document')
            self.pending_check = None
            return
        self.sync()

    def receive(self, kind, payload):
        if self.closed:
            return
        try:
            if kind == 'connected':
                self.connected = True
                self.capabilities = payload.get('capabilities', [])
                self.pending_check_sent = False
                self.sent_revision = None
                self.refresh()
                if not payload['runResumed']:
                    self.receipts.clear()
                    self.actions.clear()
                else:
                    if self.receipts and not self.send([{'type': 'completeApply', 'transactionId': transaction, 'outcome': outcome}
                                                       for transaction, outcome in self.receipts.items()]):
                        return
                self.status = 'Refine: connected'
                self.view.set_status('refine', self.status)
                self.sync(resumed=payload['runResumed'])
                self.modifier_bridge.start()
            elif kind == 'disconnected':
                self.connected = False
                self.modifier_bridge.stop()
                self.sent_revision = None
                self.clear_presentation()
                self.actions.clear()
                self.status = payload
                self.view.set_status('refine', payload)
            elif kind == 'event':
                self.event(payload)
        except (ConformanceError, ValueError, KeyError, IndexError, UnicodeError):
            self.connected = False
            self.clear_presentation()
            self.view.set_status('refine', 'Refine: invalid or stale server data; reconnecting')
            self.transport.disconnect()

    def event(self, event):
        kind = event['type']
        if kind in ('modifierShortcutAvailability', 'modifierShortcutPressed'):
            self.modifier_bridge.receive(event)
        elif kind == 'presentationContentReplaced':
            self.refresh()
            content = event['content']
            if content['documentRevision'] != self.document.snapshot['revision']:
                return
            ids = set()
            for suggestion in content['suggestions']:
                if suggestion['sourceId'] != 'document' or suggestion['id'] in ids:
                    raise ValueError('Invalid suggestion identity')
                ids.add(suggestion['id'])
                for span in [suggestion['activationRange']] + suggestion['highlightRanges']:
                    self.document.coordinates.region(span)
            self.input_epoch += 1
            self.modifier_bridge.invalidate()
            self.check_id = event['checkId']
            self.content = content
            self.shortcuts = Shortcuts(content['interaction']['quickApply'], self.capabilities,
                                       native_monitor_available=self.modifier_bridge.monitor_available)
            self.update_activation()
            if content['status'] in ('checking', 'complete', 'unavailable'):
                self.pending_check = None
            self.render()
        elif kind == 'applyRequested':
            transaction = event['transactionId']
            if transaction in self.receipts:
                self.send({'type': 'completeApply', 'transactionId': transaction, 'outcome': self.receipts[transaction]})
                return
            action = self.actions.pop(event['actionId'], None)
            if not action or action[0] != 'apply' or action[1] != event['request']['expectedRevision']:
                self.finish_apply(transaction, {'status': 'unavailable'})
                return
            self.pending_apply = event
            # Only this command owns a valid Edit token. No source travels in command args.
            self.view.run_command('refine_commit', {'transaction': transaction})
            if self.pending_apply:
                self.pending_apply = None
                self.finish_apply(transaction, {'status': 'unavailable'})
            outcome = self.receipts.get(transaction, {})
            if outcome.get('status') == 'applied':
                self.set_feedback(action, 'success', 'Suggestion applied.')
            else:
                self.set_feedback(action, 'error', 'Could not apply this suggestion. Check writing again.')
                if self.open_suggestion == action[2]:
                    self.show(action[2], update=True)
        elif kind == 'explanationReplaced':
            action = self.actions.get(event['actionId'])
            if not action or action[0] != 'explain' or not self.content or action[1] != self.content['documentRevision']:
                return
            update = event['update']
            terminal = update['status'] in ('completed', 'stale', 'unavailable')
            if terminal:
                self.actions.pop(event['actionId'], None)
                state = 'success' if update['status'] == 'completed' else 'error'
                self.set_feedback(action, state, '' if state == 'success' else
                                  'Explanation unavailable. Try again.' if update['status'] == 'unavailable' else
                                  'This suggestion is stale. Check writing again.')
            if action[2] != self.open_suggestion:
                return
            if update['status'] == 'started':
                self.explanation_attribution = update['attribution']
            if 'text' in update:
                self.explanation = update['text']
            elif update['status'] == 'started':
                self.explanation = 'Explaining…'
            elif update['status'] in ('stale', 'unavailable') and self.explanation == 'Explaining…':
                self.explanation = ''
            self.show(self.open_suggestion, update=True)
        elif kind in ('actionCompleted', 'actionRejected'):
            action = self.actions.pop(event['actionId'], None)
            if action:
                if kind == 'actionCompleted':
                    self.set_feedback(action, 'success', {'report': 'Report sent.', 'dismiss': 'Suggestion dismissed.',
                                                         'apply': 'Suggestion applied.'}.get(action[0], ''))
                else:
                    reasons = {'stale': 'This suggestion is stale. Check writing again.',
                               'disconnected': 'Refine disconnected. Reconnect and try again.',
                               'engineUnavailable': 'Refine could not complete this action. Try again.'}
                    self.set_feedback(action, 'error', reasons.get(event['reason'], 'Action unavailable. Try again.'))
                if self.open_suggestion == action[2]:
                    if kind == 'actionRejected' and action[0] == 'explain' and self.explanation == 'Explaining…':
                        self.explanation = ''
                    self.show(action[2], update=True)
        elif kind == 'resyncRequired':
            self.refresh(force=True)
            self.sent_revision = None if event['reason'] == 'documentNotOpen' else 'resync'
            self.sync()
        elif kind == 'fault':
            self.clear_presentation()
            self.view.set_status('refine', 'Refine: ' + event['code'])
            if event['fatal']:
                self.connected = False

    def render(self):
        content = self.content
        highlight = content['appearance']['highlight']
        self.color_scopes = scopes_for(self.view, highlight)
        self.render_activation()
        progress = content.get('progress')
        if progress:
            self.status = 'Refine: {}/{}'.format(progress['completedUnitCount'], progress['totalUnitCount'])
        elif content['status'] == 'complete':
            self.status = 'Refine: {} suggestion(s){}'.format(len(content['suggestions']), ' · selection' if content['coverage'] == 'partial' else '')
        elif content['status'] == 'unavailable':
            self.status = 'Refine: ' + content['unavailableReason']
        else:
            self.status = 'Refine: ' + content['status']
        if self.shortcuts and self.shortcuts.messages:
            self.status += ' · ' + ' '.join(self.shortcuts.messages)
        elif self.shortcuts and self.shortcuts.keys['apply'] and self.activation.active and content['interaction']['quickApply']['activationStyle'] == 'showTipAndHighlight':
            self.status += ' · ' + self.shortcuts.labels['apply'] + ' to apply'
        self.view.set_status('refine', self.status)
        if self.open_suggestion:
            if self.suggestion(self.open_suggestion):
                self.show(self.open_suggestion, update=True)
            else:
                self.view.hide_popup()
                self.open_suggestion = None

    def render_marks(self, highlighted_id=None):
        if not self.content or self.view.change_count() != self.document.stamp:
            for kind in self.color_scopes:
                self.view.erase_regions('refine.' + kind)
            return
        style = self.content['appearance']['highlight']['style']
        flags = sublime.DRAW_NO_OUTLINE
        if style != 'highlight':
            flags |= sublime.DRAW_NO_FILL
            flags |= sublime.DRAW_STIPPLED_UNDERLINE if style == 'dashedUnderline' else sublime.DRAW_SOLID_UNDERLINE
        for kind, scope in self.color_scopes.items():
            if style == 'highlight':
                scope = fill_scope(scope)
            regions = [sublime.Region(*self.document.coordinates.region(span))
                       for suggestion in self.content['suggestions']
                       if suggestion['kind'] == kind and suggestion['id'] != highlighted_id
                       for span in suggestion['highlightRanges']]
            self.view.add_regions('refine.' + kind, regions, scope, '', flags | sublime.DRAW_EMPTY)

    def render_activation(self):
        self.modifier_bridge.poll(render=False)
        for key in ('refine.active', 'refine.tip'):
            self.view.erase_regions(key)
        visible = (self.connected and self.has_focus and not self.open_suggestion
                   and self.view.change_count() == self.document.stamp)
        suggestion = self.suggestion(self.activation.active) if visible else None
        self.render_marks(suggestion['id'] if suggestion else None)
        if not suggestion:
            return
        regions = [sublime.Region(*self.document.coordinates.region(span))
                   for span in suggestion['highlightRanges']]
        self.view.add_regions('refine.active', regions, fill_scope(self.color_scopes[suggestion['kind']]), '',
                              sublime.DRAW_NO_OUTLINE | sublime.DRAW_EMPTY)
        if self.content['interaction']['quickApply']['activationStyle'] != 'showTipAndHighlight':
            return
        if self.shortcuts.messages:
            tip = ' '.join(self.shortcuts.messages)
        elif self.shortcuts.pending:
            return
        else:
            tip = '{} to apply · {} to cancel'.format(
                self.shortcuts.labels['apply'], self.shortcuts.labels['dismiss'])
        end = self.document.coordinates.region(suggestion['activationRange'])[1]
        self.view.add_regions('refine.tip', [sublime.Region(end)], '', '', 0,
                              annotations=['<body>' + escape(tip) + '</body>'])

    def suggestion(self, suggestion_id):
        if not self.content:
            return None
        return next((s for s in self.content['suggestions'] if s['id'] == suggestion_id), None)

    def at(self, point):
        if not self.content:
            return None
        for suggestion in self.content['suggestions']:
            start, end = self.document.coordinates.region(suggestion['activationRange'])
            if start <= point < end or start == end == point:
                return suggestion['id']
        return None

    def show_clicked_suggestion(self):
        # A click opens immediately without changing keyboard Quick Apply behavior.
        selections = self.view.sel()
        if (self.closed or not self.connected or not self.has_focus
                or len(selections) != 1 or not selections[0].empty()
                or self.view.is_auto_complete_visible()
                or (self.view.is_popup_visible() and not self.open_suggestion)):
            return
        self.show()

    def show(self, suggestion_id=None, update=False, hover=False):
        self.refresh()
        if suggestion_id is None and self.view.sel():
            suggestion_id = self.at(self.view.sel()[0].b)
        suggestion = self.suggestion(suggestion_id)
        if not suggestion:
            return
        same_popup = self.open_suggestion == suggestion_id and self.view.is_popup_visible()
        if not same_popup and self.view.is_popup_visible():
            # Sublime invokes the previous on_hide when replacing a popup.
            # Finish that lifecycle before assigning the new suggestion owner.
            self.view.hide_popup()
        if self.open_suggestion != suggestion_id:
            self.explanation = ''
            self.explanation_attribution = None
            self.input_epoch += 1
        self.open_suggestion = suggestion_id
        self.activation.cancel()
        self.render_activation()
        html = card(suggestion, self.content, self.explanation, self.shortcuts,
                    self.feedback.get(suggestion_id, {}), self.explanation_attribution)
        if same_popup:
            self.view.update_popup(html)
        else:
            revision = self.content['documentRevision']
            self.view.show_popup(html, location=self.document.coordinates.region(suggestion['activationRange'])[0],
                flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY if hover else 0,
                max_width=560, max_height=480,
                on_navigate=lambda action: self.action(action, suggestion_id, revision),
                on_hide=self.popup_hidden)

    def popup_hidden(self):
        self.input_epoch += 1
        self.open_suggestion = None
        self.modifier_bridge.poll(render=False)

    def action(self, kind, suggestion_id=None, revision=None):
        self.refresh()
        if not self.connected or not self.content:
            return
        if revision and revision != self.content['documentRevision']:
            return
        suggestion_id = suggestion_id or self.open_suggestion or (self.at(self.view.sel()[0].b) if self.view.sel() else None)
        suggestion = self.suggestion(suggestion_id)
        if not suggestion or kind not in suggestion['availableActions']:
            return
        if kind == 'apply' and any(action[0] == 'apply' for action in self.actions.values()):
            return
        if any(a[0] == kind and a[2] == suggestion_id for a in self.actions.values()):
            return
        if kind == 'report' and self.feedback.get(suggestion_id, {}).get(kind, {}).get('state') == 'success':
            return
        if kind == 'explain':
            self.show(suggestion_id)
            self.explanation = 'Explaining…'
            self.explanation_attribution = None
            self.show(suggestion_id, update=True)
        action_id = identifier()
        revision = self.content['documentRevision']
        self.actions[action_id] = (kind, revision, suggestion_id)
        self.set_feedback(self.actions[action_id], 'busy', '')
        if not self.send({'type': 'performAction', 'actionId': action_id, 'kind': kind,
                         'suggestion': {'id': suggestion_id, 'documentRevision': revision}}):
            action = self.actions.pop(action_id, None)
            self.set_feedback(action, 'error', 'Refine disconnected. Reconnect and try again.')
            if kind == 'explain':
                self.explanation = ''
        if self.open_suggestion == suggestion_id:
            self.show(suggestion_id, update=True)

    def set_feedback(self, action, state, message):
        if not action or not self.content or action[1] != self.content['documentRevision']:
            return
        self.feedback.setdefault(action[2], {})[action[0]] = {'state': state, 'message': message}

    def update_activation(self, explicit=False):
        if not self.content or self.view.change_count() != self.document.stamp:
            self.activation.cancel()
            return
        selections = self.view.sel()
        selection = None
        if len(selections) == 1:
            region = selections[0]
            offsets = self.document.coordinates.offsets
            selection = (offsets[region.a], offsets[region.b])
        self.activation.update(self.content, self.check_id, selection,
                               card=bool(self.open_suggestion), explicit=explicit)

    def modifier_input_command(self, command):
        blocks = self.modifier_input_blocks
        before = set(blocks)
        if command == 'show_overlay':
            blocks.add('overlay')
        elif command == 'hide_overlay':
            blocks.discard('overlay')
        elif command == 'insert_snippet':
            blocks.add('snippet')
        elif command == 'clear_fields':
            blocks.discard('snippet')
        elif command == 'toggle_record_macro':
            blocks.symmetric_difference_update({'macro'})
        if blocks != before:
            self.input_epoch += 1
            self.modifier_bridge.invalidate()
            self.modifier_bridge.poll()

    def shortcut_suggestion(self):
        if (self.closed or not self.has_focus or not self.connected or not self.content or not self.shortcuts
                or self.view.change_count() != self.document.stamp):
            return None
        if self.view.is_auto_complete_visible() or self.view.settings().get('is_widget'):
            return None
        window = self.view.window()
        if not window or window.active_view() != self.view:
            return None
        # The card owns its actions independently of Quick Apply enablement.
        suggestion_id = self.open_suggestion or self.activation.active
        suggestion = self.suggestion(suggestion_id)
        if not suggestion:
            return None
        return suggestion

    def shortcut_action(self, key):
        suggestion = self.shortcut_suggestion()
        if not suggestion:
            return None
        for action in ('apply', 'dismiss'):
            if self.shortcuts.keys[action] != key:
                continue
            if action == 'apply' and self.view.is_read_only():
                return None
            if self.open_suggestion:
                if action in suggestion['availableActions']:
                    return action
            elif action == 'dismiss' or 'apply' in suggestion['availableActions']:
                return action
        return None

    def perform_shortcut(self, key):
        self.refresh()
        action = self.shortcut_action(key)
        if action is None:
            return
        suggestion_id = self.open_suggestion or self.activation.active
        if action == 'dismiss' and not self.open_suggestion:
            self.activation.cancel()
            self.render()
            return
        # A busy owner still consumes its matching key but never reissues it.
        if any(item[0] == action and item[2] == suggestion_id for item in self.actions.values()):
            return
        self.action(action, suggestion_id)

    def navigate(self, forward=True):
        self.refresh()
        if not self.content or not self.content['suggestions']:
            return
        entries = sorted((self.document.coordinates.region(s['activationRange'])[0], s['id']) for s in self.content['suggestions'])
        point = self.view.sel()[0].b if self.view.sel() else 0
        candidates = [entry for entry in entries if (entry[0] > point if forward else entry[0] < point)]
        position, suggestion_id = (candidates[0] if candidates else entries[0]) if forward else (candidates[-1] if candidates else entries[-1])
        self.view.sel().clear()
        self.view.sel().add(sublime.Region(position))
        self.view.show(position)
        self.show(suggestion_id)

    def commit(self, edit, transaction):
        event = self.pending_apply
        if not event or transaction != event['transactionId']:
            return
        self.pending_apply = None
        outcome = {'status': 'unavailable'}
        self.applying = True
        mutation_started = False
        try:
            self.refresh()
            if self.view.is_read_only():
                outcome = {'status': 'unsupported', 'reason': 'readOnly', 'snapshot': self.document.snapshot}
            else:
                plan, reason = self.document.plan(event['request'])
                if reason:
                    outcome = {'status': 'rejected', 'reason': reason, 'snapshot': self.document.snapshot}
                else:
                    spans, result = plan
                    start = spans[-1][0]
                    end = spans[0][1]
                    replacement = result[start:end + len(result) - len(self.document.text)]
                    # One native buffer operation, inside one TextCommand: atomic and undoable.
                    outcome = {'status': 'indeterminate'}
                    mutation_started = True
                    self.view.replace(edit, sublime.Region(start, end), replacement)
                    self.refresh()
                    outcome = {'status': 'applied' if self.document.text == result else 'indeterminate',
                               'snapshot': self.document.snapshot}
        except (ValueError, ConformanceError, UnicodeError):
            outcome = {'status': 'indeterminate' if mutation_started else 'unavailable'}
        except Exception:
            # A native exception may have happened after mutation. Never retry it.
            outcome = {'status': 'indeterminate'}
        finally:
            self.applying = False
            self.finish_apply(transaction, outcome)

    def finish_apply(self, transaction, outcome):
        self.receipts[transaction] = outcome
        self.send({'type': 'completeApply', 'transactionId': transaction, 'outcome': outcome})
        if 'snapshot' in outcome:
            self.sent_revision = outcome['snapshot']['revision']
        self.attention()
