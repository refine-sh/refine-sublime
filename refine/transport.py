"""One socket worker; editor callbacks are serialized on the editor thread."""
import queue
import select
import threading

from .protocol import Connection, Rejected, discover, identifier, PROTOCOL, MAX_SEQUENCE
from .validation import ConformanceError
from .shortcuts import CAPABILITIES, LEGACY_KEYS


class Transport:
    def __init__(self, store, dispatch, callback):
        self.store = store
        self.dispatch = dispatch
        self.callback = callback
        self.stop_event = threading.Event()
        self.outbox = queue.Queue(maxsize=16)
        self.connection = None
        self.run_id = identifier()
        self.epoch = None
        self.generation = 0
        self.thread = threading.Thread(target=self._run, name='Refine Sublime', daemon=True)

    def start(self):
        self.thread.start()

    def send(self, command):
        try:
            self.outbox.put_nowait(command)
            return True
        except queue.Full:
            self.disconnect()
            return False

    def disconnect(self):
        connection = self.connection
        if connection:
            connection.close()

    def stop(self):
        # A final closeDocument releases native ownership promptly when connected.
        # It is sent by the worker, never by the editor thread.
        self.stop_event.set()

    def _notify(self, kind, payload):
        done = threading.Event()
        generation = self.generation
        def deliver():
            try:
                if not self.stop_event.is_set() and generation == self.generation:
                    self.callback(kind, payload)
            finally:
                done.set()
        self.dispatch(deliver)
        while not done.wait(0.1):
            if self.stop_event.is_set():
                return

    def _run(self):
        delay = 1
        while not self.stop_event.is_set():
            try:
                disconnected_message = 'Refine disconnected — reconnecting'
                descriptor = discover(self.store)
                if self.epoch != descriptor['serverEpoch']:
                    self.run_id = identifier()
                    self.epoch = descriptor['serverEpoch']
                hello = {'type': 'hello', 'protocol': PROTOCOL,
                         'client': {'id': 'refine-sublime', 'version': '0.2.0', 'host': 'sublime'},
                         'hostCapabilities': {'interceptableSuggestionActionKeys': list(LEGACY_KEYS)},
                         'runId': self.run_id, 'capabilities': CAPABILITIES}
                connection = Connection(self.store, descriptor, hello)
                self.connection = connection
                self.generation += 1
                self._notify('connected', connection.welcome)
                delay = 1
                while not self.stop_event.is_set():
                    for _ in range(16):
                        try:
                            command = self.outbox.get_nowait()
                        except queue.Empty:
                            break
                        for item in command if isinstance(command, list) else [command]:
                            connection.send(item)
                    readable, _, _ = select.select([connection.socket], [], [], 0.05)
                    if readable:
                        envelope = connection.receive()
                        self._notify('event', envelope['event'])
                        event = envelope['event']
                        if (event['type'] == 'fault' and event['fatal']) or connection.event_sequence > MAX_SEQUENCE:
                            break
                if self.stop_event.is_set():
                    connection.send({'type': 'closeDocument'})
            except Rejected as error:
                if error.message['recovery'] == 'newRun':
                    self.run_id = identifier()
                disconnected_message = 'Refine: ' + error.message['reason']
            except ConformanceError:
                disconnected_message = 'Refine: incompatible or invalid protocol; use a compatible app/plugin pair'
            except (OSError, EOFError, ValueError, RecursionError):
                disconnected_message = 'Refine unavailable — open Refine for Mac'
            finally:
                if self.connection:
                    self.connection.close()
                    self.connection = None
                while True:
                    try:
                        self.outbox.get_nowait()
                    except queue.Empty:
                        break
            if not self.stop_event.is_set():
                self._notify('disconnected', disconnected_message)
                self.stop_event.wait(delay)
                delay = min(delay * 2, 15)
