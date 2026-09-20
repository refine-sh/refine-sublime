import json
from pathlib import Path
import unittest
from refine.protocol import make_store
from refine.shortcuts import validate_binding, validate_presentation_shortcuts, V1, V2
from refine.validation import ConformanceError


class ShortcutProtocolTests(unittest.TestCase):
    def test_shared_shortcut_vectors(self):
        root = Path(__file__).resolve().parents[1] / 'vendor/protocol/vectors/shortcuts'
        for filename, v2 in [('bindings.json', False), ('bindings-v2.json', True)]:
            for case in json.loads((root / filename).read_text())['cases']:
                with self.subTest(case=case['id']):
                    if case['valid']:
                        validate_binding(case['value'], make_store(), v2)
                    else:
                        with self.assertRaises(ConformanceError):
                            validate_binding(case['value'], make_store(), v2)

    def test_extension_fields_required_only_when_negotiated(self):
        content = {'interaction': {'quickApply': {}}}
        validate_presentation_shortcuts(content, [], make_store())
        for capability in (V1, V2):
            with self.assertRaises(ConformanceError):
                validate_presentation_shortcuts(content, [capability], make_store())

    def test_transport_negotiates_and_validates_shortcut_presentations(self):
        import copy
        import io
        from unittest.mock import patch
        from refine.protocol import Connection, encode_frame
        root = Path(__file__).resolve().parents[1]
        fixture = json.loads((root / 'vendor/protocol/vectors/state/golden-writing-session.json').read_text())
        hello = copy.deepcopy(fixture['messages']['hello'])
        hello['capabilities'] = [V1, V2]
        descriptor = {'socketPath': '/unused-test-socket', 'launchToken': 'A' * 64, 'serverEpoch': 'epoch'}
        welcome = copy.deepcopy(fixture['messages']['welcome'])
        welcome['serverEpoch'] = 'epoch'
        welcome['capabilities'] = [V2]
        event = copy.deepcopy(fixture['messages']['presentation'])
        event['sequence'], event['epoch'] = 1, 'epoch'
        quick = event['event']['content']['interaction']['quickApply']
        quick['applyShortcut'] = {'kind': 'keyCombination', 'code': 'ShiftLeft', 'key': 'ShiftLeft', 'modifiers': [], 'label': 'Left Shift'}
        quick['dismissShortcut'] = {'kind': 'keyCombination', 'code': 'Escape', 'key': 'Escape', 'modifiers': [], 'label': 'Esc'}

        class Socket:
            def __init__(self, values): self.input = io.BytesIO(b''.join(encode_frame(v) for v in values))
            def settimeout(self, value): pass
            def connect(self, path): pass
            def sendall(self, data): pass
            def recv(self, size): return self.input.read(size)
            def shutdown(self, how): pass
            def close(self): pass

        with patch('refine.protocol.socket.socket', return_value=Socket([welcome, event])):
            connection = Connection(make_store(), descriptor, hello)
            self.assertEqual(connection.capabilities, {V2})
            self.assertEqual(connection.receive(), event)
        for bad_caps in ([V1, V2], ['unknown.capability.v1']):
            bad_welcome = dict(welcome, capabilities=bad_caps)
            with patch('refine.protocol.socket.socket', return_value=Socket([bad_welcome])):
                with self.assertRaises(ConformanceError):
                    Connection(make_store(), descriptor, hello)
        with patch('refine.protocol.socket.socket', return_value=Socket([welcome])):
            with self.assertRaises(ConformanceError):
                Connection(make_store(), descriptor, dict(hello, capabilities=[]))
        del quick['applyShortcut']
        with patch('refine.protocol.socket.socket', return_value=Socket([welcome, event])):
            connection = Connection(make_store(), descriptor, hello)
            with self.assertRaises(ConformanceError):
                connection.receive()
