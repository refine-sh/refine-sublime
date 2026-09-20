"""Strict, dependency-free Protocol 1.0 transport. No editor API imports."""
import json
import os
import socket
import stat
import struct
import uuid
from pathlib import Path

from .validation import (ConformanceError, SchemaStore, MAX_FRAME_BYTES,
                         strict_loads, validate_portable_value,
                         validate_with_schema, validate_semantics)

from .shortcuts import CAPABILITIES, V1, V2, validate_presentation_shortcuts

PROTOCOL = {"major": 1, "minor": 0}
DESCRIPTOR = Path.home() / "Library/Application Support/com.runjuu.refine/Integrations/endpoint.json"
MAX_SEQUENCE = 4294967295


def identifier():
    return uuid.uuid4().hex


def validate(value, schema, store):
    validate_portable_value(value)
    validate_with_schema(value, schema, store)
    validate_semantics(value, CAPABILITIES, schema)


def encode_frame(value):
    validate_portable_value(value)
    data = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if not 0 < len(data) <= MAX_FRAME_BYTES:
        raise ConformanceError('frame-size', 'Frame exceeds the protocol limit')
    return struct.pack('>I', len(data)) + data


def receive_exact(sock, size):
    result = bytearray()
    while len(result) < size:
        data = sock.recv(min(size - len(result), 65536))
        if not data:
            raise EOFError('Connection closed')
        result.extend(data)
    return bytes(result)


def receive_frame(sock):
    size = struct.unpack('>I', receive_exact(sock, 4))[0]
    if not 0 < size <= MAX_FRAME_BYTES:
        raise ConformanceError('frame-size', 'Invalid frame length')
    value = strict_loads(receive_exact(sock, size).decode('utf-8'))
    if not isinstance(value, dict):
        raise ConformanceError('frame-shape', 'Frame must be an object')
    return value


def validate_path(path, kind, mode):
    info = os.lstat(str(path))
    if not kind(info.st_mode) or stat.S_IMODE(info.st_mode) != mode or info.st_uid != os.getuid():
        raise ConformanceError('discovery', 'Invalid endpoint permissions or file type')


def discover(store, path=DESCRIPTOR):
    path = Path(path)
    validate_path(path.parent, stat.S_ISDIR, 0o700)
    validate_path(path.parent / 'owner.lock', stat.S_ISREG, 0o600)
    validate_path(path, stat.S_ISREG, 0o600)
    # Bound the descriptor and refuse symlink substitution between lstat/open.
    fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid():
            raise ConformanceError('discovery', 'Invalid endpoint file')
        data = stream.read(65537)
    if len(data) > 65536:
        raise ConformanceError('discovery', 'Endpoint descriptor is too large')
    descriptor = strict_loads(data.decode('utf-8'))
    validate(descriptor, 'schema/endpoint-descriptor.schema.json', store)
    socket_path = Path(descriptor['socketPath'])
    if not socket_path.is_absolute():
        raise ConformanceError('discovery', 'Socket path must be absolute')
    validate_path(socket_path.parent, stat.S_ISDIR, 0o700)
    validate_path(socket_path, stat.S_ISSOCK, 0o600)
    return descriptor


class Rejected(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(message['reason'])


class Connection:
    def __init__(self, store, descriptor, hello):
        self.store = store
        self.command_sequence = 1
        self.event_sequence = 1
        self.epoch = descriptor['serverEpoch']
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.settimeout(5)
        try:
            self.socket.connect(descriptor['socketPath'])
            hello = dict(hello, launchToken=descriptor['launchToken'])
            validate(hello, 'schema/handshake.schema.json#/$defs/hello', store)
            self.socket.sendall(encode_frame(hello))
            response = receive_frame(self.socket)
            validate(response, 'schema/handshake.schema.json', store)
            if response['type'] == 'rejected':
                raise Rejected(response)
            if response['type'] != 'welcome' or response['serverEpoch'] != self.epoch:
                raise ConformanceError('handshake', 'Unexpected welcome or capabilities')
            activated = set(response['capabilities'])
            if not activated <= set(hello['capabilities']) or {V1, V2} <= activated:
                raise ConformanceError('handshake', 'Unoffered or conflicting shortcut capabilities')
            self.capabilities = activated
            self.welcome = response
        except Exception:
            self.close()
            raise

    def send(self, command, command_id=None):
        envelope = {'type': 'command', 'sequence': self.command_sequence,
                    'id': command_id or identifier(), 'command': command}
        self.send_envelope(envelope)

    def send_envelope(self, envelope):
        validate(envelope, 'schema/envelope.schema.json#/$defs/commandEnvelope', self.store)
        if envelope['sequence'] != self.command_sequence:
            raise ConformanceError('sequence', 'Invalid command sequence')
        self.socket.sendall(encode_frame(envelope))
        self.command_sequence += 1
        if self.command_sequence > MAX_SEQUENCE:
            self.close()

    def receive(self):
        envelope = receive_frame(self.socket)
        validate(envelope, 'schema/envelope.schema.json#/$defs/eventEnvelope', self.store)
        if envelope['epoch'] != self.epoch or envelope['sequence'] != self.event_sequence:
            raise ConformanceError('sequence', 'Invalid event epoch or sequence')
        if envelope['event']['type'] == 'presentationContentReplaced':
            validate_presentation_shortcuts(envelope['event']['content'], self.capabilities, self.store)
        self.event_sequence += 1
        return envelope

    def close(self):
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.socket.close()


def make_store(loader=None):
    root = Path(__file__).resolve().parent.parent / 'vendor/protocol'
    store = SchemaStore(root)
    if loader:
        for name in ('shared', 'command', 'event', 'handshake', 'envelope', 'endpoint-descriptor', 'suggestion-shortcuts', 'suggestion-shortcuts-v2'):
            path = 'schema/' + name + '.schema.json'
            store.documents[path] = json.loads(loader('vendor/protocol/' + path))
    return store
