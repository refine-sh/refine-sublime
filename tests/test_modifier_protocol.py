import io
import unittest
from refine.protocol import Connection, encode_frame, make_store
from refine.shortcuts import MODIFIER_BRIDGE, V2
from refine.validation import ConformanceError


class ModifierProtocolTests(unittest.TestCase):
    def connection(self, enabled, event=None):
        connection = Connection.__new__(Connection)
        connection.capabilities = {V2, MODIFIER_BRIDGE} if enabled else {V2}
        connection.store = make_store()
        connection.command_sequence = connection.event_sequence = 1
        connection.epoch = 'epoch'
        class Socket:
            def __init__(self):
                self.data = io.BytesIO(encode_frame({'type': 'event', 'sequence': 1, 'epoch': 'epoch', 'event': event})) if event else io.BytesIO()
                self.sent = []
            def sendall(self, data): self.sent.append(data)
            def recv(self, size): return self.data.read(size)
        connection.socket = Socket()
        return connection

    def test_unnegotiated_bridge_command_never_reaches_socket(self):
        connection = self.connection(False)
        command = {'type': 'setModifierShortcutOwner', 'owner': {'ownerId': 'owner', 'processId': 42, 'keys': ['ShiftLeft']}}
        with self.assertRaises(ConformanceError):
            connection.send(command)
        self.assertEqual(connection.socket.sent, [])
        connection = self.connection(True)
        connection.send(command)
        self.assertEqual(len(connection.socket.sent), 1)

    def test_extension_events_require_activation(self):
        for event in [
            {'type': 'modifierShortcutAvailability', 'state': {'ownerId': 'owner', 'available': True}},
            {'type': 'modifierShortcutPressed', 'press': {'ownerId': 'owner', 'code': 'ShiftLeft'}}
        ]:
            with self.subTest(event=event['type']):
                with self.assertRaises(ConformanceError):
                    self.connection(False, event).receive()
                self.assertEqual(self.connection(True, event).receive()['event'], event)
