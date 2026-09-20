"""Snapshot identity, scalar-safe coordinates, and whole-suggestion edit planning."""
from bisect import bisect_left
from .protocol import identifier
from .validation import ConformanceError, MAX_SOURCE_BYTES, validate_apply_edits


class Coordinates:
    def __init__(self, text):
        self.offsets = [0]
        for char in text:
            if 0xD800 <= ord(char) <= 0xDFFF:
                raise ValueError('Source contains invalid Unicode')
            self.offsets.append(self.offsets[-1] + (2 if ord(char) > 0xFFFF else 1))

    def point(self, offset):
        index = bisect_left(self.offsets, offset)
        if index == len(self.offsets) or self.offsets[index] != offset:
            raise ValueError('Range splits a Unicode scalar or exceeds the source')
        return index

    def region(self, span):
        return self.point(span['location']), self.point(span['location'] + span['length'])

    def range(self, start, end):
        return {'location': self.offsets[start], 'length': self.offsets[end] - self.offsets[start]}


class Document:
    def __init__(self):
        self.snapshot = None
        self.stamp = None
        self.coordinates = Coordinates('')

    @property
    def text(self):
        return self.snapshot['sources'][0]['text'] if self.snapshot else ''

    def observe(self, text, syntax, stamp, force=False):
        if len(text.encode('utf-8')) > MAX_SOURCE_BYTES:
            raise ValueError('Refine supports buffers up to 1 MiB of UTF-8 text')
        source = {'sourceId': 'document', 'text': text, 'sourceSyntax': syntax}
        if force or self.snapshot is None or self.stamp != stamp or self.snapshot['sources'][0] != source:
            self.coordinates = Coordinates(text)
            self.snapshot = {'revision': identifier(), 'sources': [source]}
            self.stamp = stamp
            return True
        return False

    def plan(self, request):
        if request['expectedRevision'] != self.snapshot['revision'] or request['sourceId'] != 'document':
            return None, 'staleRevision'
        validate_apply_edits(request)
        result = self.text
        spans = []
        for edit in request['edits']:
            start, end = self.coordinates.region(edit['range'])
            if self.text[start:end] != edit['expectedText']:
                return None, 'textMismatch'
            spans.append((start, end, edit['replacement']))
            result = result[:start] + edit['replacement'] + result[end:]
        if len(result.encode('utf-8')) > MAX_SOURCE_BYTES:
            raise ValueError('Correction exceeds the source limit')
        return (spans, result), None
