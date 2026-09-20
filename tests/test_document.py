import unittest
from refine.document import Document, Coordinates
from refine.validation import ConformanceError


class DocumentTests(unittest.TestCase):
    def test_scalar_boundaries_including_combining_characters(self):
        coords = Coordinates('a😀e\u0301\r\nz')
        self.assertEqual(coords.region({'location': 1, 'length': 2}), (1, 2))
        self.assertEqual(coords.point(4), 3)  # Combining mark is a valid scalar boundary.
        for offset in (2, 100, -1):
            with self.assertRaises(ValueError):
                coords.point(offset)

    def test_aba_history_never_reuses_revision(self):
        doc = Document()
        revisions = []
        for stamp, text in enumerate(('a', 'b', 'a')):
            doc.observe(text, 'plainText', stamp)
            revisions.append(doc.snapshot['revision'])
        self.assertEqual(len(set(revisions)), 3)
        self.assertFalse(doc.observe('a', 'plainText', 2))
        self.assertTrue(doc.observe('a', 'markdownDocumentHardLineBreaks', 2))

    def test_descending_edits_after_emoji(self):
        doc = Document()
        doc.observe('😀 She go home.', 'plainText', 1)
        request = {'expectedRevision': doc.snapshot['revision'], 'sourceId': 'document', 'edits': [
            {'range': {'location': 10, 'length': 4}, 'expectedText': 'home', 'replacement': 'outside'},
            {'range': {'location': 7, 'length': 2}, 'expectedText': 'go', 'replacement': 'goes'}]}
        plan, reason = doc.plan(request)
        self.assertIsNone(reason)
        self.assertEqual(plan[1], '😀 She goes outside.')
        request['edits'].reverse()
        with self.assertRaises(ConformanceError):
            doc.plan(request)

    def test_all_edits_validated_before_mutation(self):
        doc = Document()
        doc.observe('abc def', 'plainText', 1)
        request = {'expectedRevision': doc.snapshot['revision'], 'sourceId': 'document', 'edits': [
            {'range': {'location': 4, 'length': 3}, 'expectedText': 'def', 'replacement': 'x'},
            {'range': {'location': 0, 'length': 3}, 'expectedText': 'bad', 'replacement': 'y'}]}
        self.assertEqual(doc.plan(request), (None, 'textMismatch'))
        self.assertEqual(doc.text, 'abc def')
        request['expectedRevision'] = 'old'
        self.assertEqual(doc.plan(request), (None, 'staleRevision'))

    def test_noop_and_overlapping_edits_rejected(self):
        doc = Document()
        doc.observe('abc', 'plainText', 1)
        for edits in ([{'range': {'location': 0, 'length': 1}, 'expectedText': 'a', 'replacement': 'a'}], [
            {'range': {'location': 1, 'length': 2}, 'expectedText': 'bc', 'replacement': 'x'},
            {'range': {'location': 0, 'length': 2}, 'expectedText': 'ab', 'replacement': 'y'}]):
            with self.assertRaises(ConformanceError):
                doc.plan({'expectedRevision': doc.snapshot['revision'], 'sourceId': 'document', 'edits': edits})
