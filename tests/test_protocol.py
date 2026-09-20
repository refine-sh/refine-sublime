import importlib.util
import json
import os
from pathlib import Path
import socket
import struct
import tempfile
import threading
import unittest

from refine.protocol import (Connection, discover, make_store, encode_frame, receive_frame, validate, Rejected)
from refine.validation import ConformanceError, strict_loads

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'vendor/protocol'
spec = importlib.util.spec_from_file_location('upstream_runner', VENDOR / 'runner/conformance.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ProtocolTests(unittest.TestCase):
    def test_upstream_positive_and_negative_vectors(self):
        store = make_store()
        counts = {'positive': 0, 'negative': 0}
        for family in counts:
            for path in (VENDOR / 'vectors/json' / family).glob('*.json'):
                for case in json.loads(path.read_text())['cases']:
                    with self.subTest(case=case['id']):
                        def check():
                            if 'documentText' in case:
                                value = strict_loads(case['documentText'])
                            elif 'generate' in case:
                                value = runner.generated_value(case['generate'])
                            else:
                                value = case['value']
                            # Base client does not offer capabilities. Test schemas separately
                            # with the published registry where a vector activates extensions.
                            from refine.validation import validate_portable_value, validate_with_schema, validate_semantics
                            validate_portable_value(value)
                            validate_with_schema(value, case['schema'], store)
                            published = runner.published_capability_ids(VENDOR, runner.SchemaStore(VENDOR))
                            validate_semantics(value, published, case['schema'])
                        if family == 'positive':
                            check()
                        else:
                            with self.assertRaises((ConformanceError, UnicodeError, ValueError)):
                                check()
                        counts[family] += 1
        self.assertGreater(counts['positive'], 20)
        self.assertGreater(counts['negative'], 20)

    def test_fragmented_and_coalesced_frames(self):
        a, b = socket.socketpair()
        self.addCleanup(a.close)
        self.addCleanup(b.close)
        frames = encode_frame({'hello': '😀'}) + encode_frame({'second': True})
        def writer():
            for byte in frames:
                b.sendall(bytes([byte]))
        thread = threading.Thread(target=writer)
        thread.start()
        self.assertEqual(receive_frame(a), {'hello': '😀'})
        self.assertEqual(receive_frame(a), {'second': True})
        thread.join()

    def test_malformed_frames(self):
        for payload in (b'{"x":1,"x":2}', b'{"x":-0}', b'{"x":null}', b'{"x":1e0}', b'[]', b'\xff'):
            a, b = socket.socketpair()
            try:
                b.sendall(struct.pack('>I', len(payload)) + payload)
                with self.assertRaises((ConformanceError, UnicodeError, ValueError)):
                    receive_frame(a)
            finally:
                a.close()
                b.close()

    def test_discovery_requires_private_paths_and_rejects_symlinks(self):
        with tempfile.TemporaryDirectory(prefix='rs-', dir='/tmp') as directory:
            path = Path(directory)
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.addCleanup(sock.close)
            sock.bind(str(path / 's'))
            os.chmod(path / 's', 0o600)
            (path / 'owner.lock').touch(mode=0o600)
            descriptor = {'version': 1, 'socketPath': str(path / 's'), 'launchToken': 'A'*64,
                          'serverEpoch': 'epoch', 'protocolMajor': 1, 'protocolMinor': 0, 'pid': os.getpid()}
            endpoint = path / 'endpoint.json'
            endpoint.write_text(json.dumps(descriptor))
            endpoint.chmod(0o600)
            self.assertEqual(discover(make_store(), endpoint), descriptor)
            endpoint.chmod(0o644)
            with self.assertRaises(ConformanceError):
                discover(make_store(), endpoint)
            endpoint.chmod(0o600)
            endpoint.rename(path / 'real.json')
            endpoint.symlink_to(path / 'real.json')
            with self.assertRaises(ConformanceError):
                discover(make_store(), endpoint)
