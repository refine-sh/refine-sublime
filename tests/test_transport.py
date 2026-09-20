import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch

from refine.protocol import discover, encode_frame, make_store, receive_frame
from refine.transport import Transport


class TransportTests(unittest.TestCase):
    def test_worker_handshake_dispatch_and_graceful_close(self):
        with tempfile.TemporaryDirectory(prefix='rst-', dir='/tmp') as directory:
            root = Path(directory)
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.addCleanup(listener.close)
            listener.bind(str(root / 's'))
            os.chmod(root / 's', 0o600)
            listener.listen(1)
            listener.settimeout(3)
            (root / 'owner.lock').touch(mode=0o600)
            descriptor = {'version': 1, 'socketPath': str(root / 's'), 'launchToken': 'A'*64,
                          'serverEpoch': 'epoch', 'protocolMajor': 1, 'protocolMinor': 0, 'pid': os.getpid()}
            endpoint = root / 'endpoint.json'
            endpoint.write_text(json.dumps(descriptor))
            endpoint.chmod(0o600)
            store = make_store()
            received = []
            failures = []
            completed = threading.Event()
            def server():
                try:
                    connection, _ = listener.accept()
                    with connection:
                        connection.settimeout(3)
                        hello = receive_frame(connection)
                        self.assertEqual(hello['client']['id'], 'refine-sublime')
                        self.assertEqual(set(hello['capabilities']), {
                            'com.runjuu.refine.suggestion-shortcuts.v1',
                            'com.runjuu.refine.suggestion-shortcuts.v2'})
                        self.assertNotIn('leftShift', hello['hostCapabilities']['interceptableSuggestionActionKeys'])
                        connection.sendall(encode_frame({'type': 'welcome', 'protocol': {'major': 1, 'minor': 0},
                            'serverEpoch': 'epoch', 'runResumed': False, 'capabilities': [],
                            'limits': {'maxFrameBytes': 8388608, 'maxSources': 2, 'maxSourceBytes': 1048576}}))
                        received.append(receive_frame(connection))
                        connection.sendall(encode_frame({'type': 'event', 'sequence': 1, 'epoch': 'epoch',
                            'event': {'type': 'documentAccepted', 'revision': 'r1'}}))
                        received.append(receive_frame(connection))
                except BaseException as error:
                    failures.append(error)
                finally:
                    completed.set()
            def callback(kind, payload):
                if kind == 'connected':
                    transport.send({'type': 'openDocument', 'snapshot': {'revision': 'r1', 'sources': [
                        {'sourceId': 'document', 'text': 'Example.', 'sourceSyntax': 'plainText'}]}})
                elif kind == 'event':
                    transport.stop()
            server_thread = threading.Thread(target=server, daemon=True)
            server_thread.start()
            with patch('refine.transport.discover', lambda store: discover(store, endpoint)):
                transport = Transport(store, lambda fn: fn(), callback)
                transport.start()
                self.assertTrue(completed.wait(4))
                transport.stop()
                transport.thread.join(4)
            server_thread.join(4)
            self.assertFalse(transport.thread.is_alive())
            self.assertFalse(failures, failures)
            self.assertEqual([entry['command']['type'] for entry in received], ['openDocument', 'closeDocument'])
            self.assertEqual([entry['sequence'] for entry in received], [1, 2])
