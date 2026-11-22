import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from refine.protocol import CAPABILITIES, Connection, WAVY_UNDERLINE, encode_frame, make_store
from refine.validation import ConformanceError

FIXTURE = json.loads((Path(__file__).resolve().parents[1] / 'vendor/protocol/vectors/state/golden-writing-session.json').read_text())


class Socket:
    def __init__(self, values): self.input = io.BytesIO(b''.join(encode_frame(v) for v in values))
    def settimeout(self, value): pass
    def connect(self, path): pass
    def sendall(self, data): pass
    def recv(self, size): return self.input.read(size)
    def shutdown(self, how): pass
    def close(self): pass


class WavyUnderlineProtocolTests(unittest.TestCase):
    def setUp(self):
        self.hello = copy.deepcopy(FIXTURE['messages']['hello'])
        self.hello['capabilities'] = list(CAPABILITIES)
        self.descriptor = {'socketPath': '/unused-test-socket', 'launchToken': 'A' * 64, 'serverEpoch': 'epoch'}

    def welcome(self, capabilities):
        welcome = copy.deepcopy(FIXTURE['messages']['welcome'])
        welcome['serverEpoch'], welcome['capabilities'] = 'epoch', capabilities
        return welcome

    def presentation(self, style):
        event = copy.deepcopy(FIXTURE['messages']['presentation'])
        event['sequence'], event['epoch'] = 1, 'epoch'
        event['event']['content']['appearance']['highlight']['style'] = style
        return event

    def receive(self, capabilities, style):
        event = self.presentation(style)
        with patch('refine.protocol.socket.socket', return_value=Socket([self.welcome(capabilities), event])):
            connection = Connection(make_store(), self.descriptor, self.hello)
            self.assertEqual(connection.capabilities, set(capabilities))
            return event, connection.receive()

    def test_hello_offers_wavy_underline(self):
        self.assertIn(WAVY_UNDERLINE, CAPABILITIES)

    def test_activated_client_accepts_wavy_underline_unchanged(self):
        event, received = self.receive([WAVY_UNDERLINE], 'wavyUnderline')
        self.assertEqual(received, event)
        self.assertEqual(received['event']['content']['appearance']['highlight']['style'], 'wavyUnderline')

    def test_activated_client_still_accepts_base_styles(self):
        for style in ('underline', 'dashedUnderline', 'highlight'):
            with self.subTest(style=style):
                event, received = self.receive([WAVY_UNDERLINE], style)
                self.assertEqual(received, event)

    def test_unactivated_client_rejects_wavy_underline(self):
        with self.assertRaises(ConformanceError):
            self.receive([], 'wavyUnderline')

    def test_activated_client_rejects_other_unknown_styles(self):
        for style in ('dottedUnderline', 'WavyUnderline'):
            with self.subTest(style=style):
                with self.assertRaises(ConformanceError):
                    self.receive([WAVY_UNDERLINE], style)

    def test_activated_wavy_presentation_keeps_base_validation(self):
        event = self.presentation('wavyUnderline')
        event['event']['content']['appearance']['highlight']['grammarColor'] = 'red'
        with patch('refine.protocol.socket.socket', return_value=Socket([self.welcome([WAVY_UNDERLINE]), event])):
            connection = Connection(make_store(), self.descriptor, self.hello)
            with self.assertRaises(ConformanceError):
                connection.receive()

    def test_unoffered_activation_is_rejected(self):
        hello = dict(self.hello, capabilities=[c for c in CAPABILITIES if c != WAVY_UNDERLINE])
        with patch('refine.protocol.socket.socket', return_value=Socket([self.welcome([WAVY_UNDERLINE])])):
            with self.assertRaises(ConformanceError):
                Connection(make_store(), self.descriptor, hello)


if __name__ == '__main__':
    unittest.main()
