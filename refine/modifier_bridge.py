"""Connection-local ownership for Refine's native standalone modifier monitor."""
import os
import time
import sublime

from .protocol import identifier
from .shortcuts import MODIFIER_BRIDGE, Shortcuts


class ModifierBridge:
    def __init__(self, session):
        self.session = session
        self.owner_id = None
        self.signature = None
        self.available = False
        self.monitor_available = None
        self.renewed_at = 0
        self.generation = 0

    def start(self):
        self.stop()
        if MODIFIER_BRIDGE not in self.session.capabilities:
            return
        generation = self.generation
        def tick():
            if generation != self.generation or self.session.closed or not self.session.connected:
                return
            self.poll()
            sublime.set_timeout(tick, 100)
        tick()

    def stop(self):
        self.generation += 1
        self.owner_id = None
        self.signature = None
        self.available = False
        self.monitor_available = None

    def invalidate(self):
        if self.owner_id and self.session.connected and not self.session.closed:
            self.session.send({'type': 'setModifierShortcutOwner', 'owner': {
                'ownerId': identifier(), 'processId': os.getppid(), 'keys': []}})
        self.owner_id = None
        self.signature = None
        self.available = False
        self.rebuild_shortcuts()

    def current(self):
        session = self.session
        if (MODIFIER_BRIDGE not in session.capabilities or session.modifier_input_blocks
                or not session.view.is_valid()):
            return None
        suggestion = session.shortcut_suggestion()
        if not suggestion or not session.shortcuts.native_keys:
            return None
        window = session.view.window()
        # Conservative: native input cannot evaluate Sublime keymap context predicates.
        if getattr(window, 'active_panel', lambda: None)():
            return None
        if session.view.is_popup_visible() and not session.open_suggestion:
            return None
        keys = tuple(sorted(code for action, code in session.shortcuts.native_keys.items()
            if (action != 'apply' or not session.view.is_read_only()) and
            ((session.open_suggestion and action in suggestion['availableActions']) or
             (not session.open_suggestion and (action == 'dismiss' or 'apply' in suggestion['availableActions'])))))
        if not keys:
            return None
        return (session.view.id(), session.input_epoch, session.document.stamp,
                session.check_id, suggestion['id'], session.open_suggestion,
                tuple((region.a, region.b) for region in session.view.sel()), keys)

    def poll(self, render=True):
        session = self.session
        if not session.connected or session.closed or MODIFIER_BRIDGE not in session.capabilities:
            return
        current = self.current()
        changed = current != self.signature or self.owner_id is None
        if changed:
            self.signature = current
            self.owner_id = identifier()
            self.available = False
            self.rebuild_shortcuts()
        if changed or (current and time.monotonic() - self.renewed_at >= 0.5):
            self.renewed_at = time.monotonic()
            session.send({'type': 'setModifierShortcutOwner', 'owner': {
                'ownerId': self.owner_id, 'processId': os.getppid(),
                'keys': list(current[-1]) if current else []}})
        if changed and render and session.content:
            session.render()

    def rebuild_shortcuts(self):
        session = self.session
        if session.content and session.shortcuts:
            session.shortcuts = Shortcuts(session.content['interaction']['quickApply'],
                                          session.capabilities, self.available, self.monitor_available)

    def set_available(self, available):
        if self.available == available and self.monitor_available == available:
            return
        self.monitor_available = available
        self.available = available
        self.rebuild_shortcuts()
        self.session.render()

    def receive(self, event):
        if MODIFIER_BRIDGE not in self.session.capabilities:
            raise ValueError('Unnegotiated modifier bridge event')
        payload = event['state'] if event['type'] == 'modifierShortcutAvailability' else event['press']
        if (not self.owner_id or payload['ownerId'] != self.owner_id or
                not self.signature or self.current() != self.signature):
            return
        if event['type'] == 'modifierShortcutAvailability':
            self.set_available(payload['available'])
        elif self.available and payload['code'] in self.signature[-1]:
            self.session.perform_shortcut(payload['code'])
