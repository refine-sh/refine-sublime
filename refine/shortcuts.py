"""Map negotiated Refine shortcuts to context-owned Sublime key bindings."""
from .validation import ConformanceError, validate_portable_value, validate_with_schema

V1 = 'com.runjuu.refine.suggestion-shortcuts.v1'
V2 = 'com.runjuu.refine.suggestion-shortcuts.v2'
CAPABILITIES = [V1, V2]
LEGACY_KEYS = {'tab': 'tab', 'escape': 'escape', 'return': 'enter', 'space': 'space',
               'delete': 'backspace', 'leftArrow': 'left', 'rightArrow': 'right',
               'upArrow': 'up', 'downArrow': 'down'}
MODIFIERS = [('control', 'ctrl'), ('option', 'alt'), ('shift', 'shift'), ('command', 'super')]
SPECIAL = {'Tab': 'tab', 'Escape': 'escape', 'Enter': 'enter', 'Space': 'space',
           'Backspace': 'backspace', 'Delete': 'delete', 'Insert': 'insert',
           'ArrowLeft': 'left', 'ArrowRight': 'right', 'ArrowUp': 'up', 'ArrowDown': 'down',
           'Home': 'home', 'End': 'end', 'PageUp': 'pageup', 'PageDown': 'pagedown',
           'NumLock': 'clear', 'NumpadDecimal': 'keypad_period', 'NumpadDivide': 'keypad_divide',
           'NumpadMultiply': 'keypad_multiply', 'NumpadSubtract': 'keypad_minus',
           'NumpadAdd': 'keypad_plus', 'NumpadEnter': 'keypad_enter'}
SPECIAL.update({'F' + str(i): 'f' + str(i) for i in range(1, 21)})
SPECIAL.update({'Numpad' + str(i): 'keypad' + str(i) for i in range(10)})
PRINTABLE = 'abcdefghijklmnopqrstuvwxyz0123456789,./;\'`-=[]\\'


def validate_binding(binding, store, v2=False):
    validate_portable_value(binding)
    schema = 'suggestion-shortcuts-v2' if v2 else 'suggestion-shortcuts'
    validate_with_schema(binding, 'schema/' + schema + '.schema.json', store)
    if v2 and binding['kind'] != 'keyCombination':
        return
    code, modifiers = binding['code'], binding['modifiers']
    if code.startswith(('Shift', 'Alt', 'Control')):
        if modifiers:
            raise ConformanceError('shortcut', 'Standalone modifier has additional modifiers')
    else:
        printable = code.startswith(('Key', 'Digit', 'Intl', 'Numpad')) or code in {
            'Equal', 'Minus', 'BracketRight', 'BracketLeft', 'Quote', 'Semicolon',
            'Backslash', 'Comma', 'Slash', 'Period', 'Backquote'}
        if printable and not set(modifiers) & {'control', 'option', 'command'}:
            raise ConformanceError('shortcut', 'Typing shortcut requires a modifier')


def validate_presentation_shortcuts(content, capabilities, store):
    if V1 not in capabilities and V2 not in capabilities:
        return
    quick = content['interaction']['quickApply']
    for name in ('applyShortcut', 'dismissShortcut'):
        if name not in quick:
            raise ConformanceError('shortcut', 'Missing negotiated shortcut')
        validate_binding(quick[name], store, V2 in capabilities)


def sublime_key(binding):
    if binding.get('kind', 'keyCombination') != 'keyCombination':
        return None
    code = binding['code']
    key = SPECIAL.get(code)
    if key is None and (code.startswith(('Key', 'Digit', 'Intl')) or code in {
            'Equal', 'Minus', 'BracketRight', 'BracketLeft', 'Quote', 'Semicolon',
            'Backslash', 'Comma', 'Slash', 'Period', 'Backquote'}):
        # Sublime keymaps address the current-layout unshifted key, as published
        # by Refine. Never substitute the US character from a physical code.
        value = binding['key']
        key = value if len(value) == 1 and value in PRINTABLE else None
    if key is None:
        return None
    return '+'.join([native for modifier, native in MODIFIERS if modifier in binding['modifiers']] + [key])


def conflicts(left, right):
    def signature(binding):
        kind = binding.get('kind', 'keyCombination')
        if kind == 'keyCombination':
            return kind, binding['code'], tuple(sorted(binding['modifiers']))
        if kind == 'modifierChord':
            return kind, tuple(sorted(binding['keys']))
        return kind, binding['key']
    if signature(left) == signature(right):
        return True
    for standalone, other in ((left, right), (right, left)):
        code = standalone.get('code', '')
        if standalone.get('kind', 'keyCombination') != 'keyCombination' or not code.startswith(('Shift', 'Alt', 'Control')):
            continue
        kind = other.get('kind', 'keyCombination')
        if kind == 'modifierChord' and code in other['keys']:
            return True
        if kind == 'modifierDoubleTap' and code == other['key']:
            return True
        modifier = {'Shift': 'shift', 'Alt': 'option', 'Control': 'control'}
        if kind == 'keyCombination' and any(code.startswith(prefix) and name in other['modifiers'] for prefix, name in modifier.items()):
            return True
    return False


class Shortcuts:
    def __init__(self, quick, capabilities):
        self.keys = {}
        self.labels = {}
        self.messages = []
        negotiated = V1 in capabilities or V2 in capabilities
        bindings = {}
        for action in ('apply', 'dismiss'):
            if negotiated:
                binding = quick[action + 'Shortcut']
                bindings[action] = binding
                key = sublime_key(binding)
                self.labels[action] = binding['label']
            else:
                legacy = quick[action + 'Key']
                key = LEGACY_KEYS.get(legacy)
                self.labels[action] = legacy
            self.keys[action] = key
            if key is None:
                self.messages.append('{} shortcut unavailable in Sublime Text: {}. Choose a key combination in Refine.'.format(action.title(), self.labels[action]))
        if (negotiated and conflicts(bindings['apply'], bindings['dismiss'])) or (
                self.keys['apply'] is not None and self.keys['apply'] == self.keys['dismiss']):
            self.keys = {'apply': None, 'dismiss': None}
            self.messages = ['Apply and Dismiss shortcuts conflict. Choose different shortcuts in Refine.']


class QuickActivation:
    def __init__(self):
        self.generation = None
        self.active = None
        self.can_auto_activate = True
        self.selection = None

    def cancel(self):
        self.active = None
        self.can_auto_activate = False

    def update(self, content, check_id, selection, card=False, explicit=False):
        generation = (content['documentRevision'], check_id)
        if generation != self.generation:
            self.generation = generation
            self.active = None
            self.can_auto_activate = True
        moved = selection != self.selection
        self.selection = selection
        if not content['interaction']['quickApply']['enabled'] or card:
            self.cancel()
            return
        candidates = []
        if selection and selection[0] == selection[1]:
            point = selection[0]
            for suggestion in content['suggestions']:
                span = suggestion['activationRange']
                if 'apply' in suggestion['availableActions'] and span['location'] <= point <= span['location'] + span['length']:
                    candidates.append(suggestion)
        candidate = min(candidates, key=lambda s: (s['activationRange']['length'],
            {'grammar': 0, 'mixed': 1, 'fluency': 2}[s['kind']], s['activationRange']['location'], s['id']), default=None)
        candidate_id = candidate['id'] if candidate else None
        if self.active != candidate_id:
            self.active = None
        if (explicit and moved) or self.can_auto_activate:
            self.active = candidate_id
            if candidate_id:
                self.can_auto_activate = False
