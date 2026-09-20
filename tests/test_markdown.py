import unittest
from refine.markdown import render


class MarkdownTests(unittest.TestCase):
    def test_formatting_and_unfinished_stream(self):
        html = render('# Reason\n\n**Bold** and *italic* with `**literal**`.\n\n1. First\n2. Second\n\n```python\n<script>')
        self.assertIn('<strong>Reason</strong>', html)
        self.assertIn('<em>italic</em>', html)
        self.assertIn('<code>**literal**</code>', html)
        self.assertIn('<ol><li>First</li><li>Second</li></ol>', html)
        self.assertIn('<pre><code>&lt;script&gt;</code></pre>', html)

    def test_model_html_and_links_cannot_create_controls(self):
        html = render('<a href="apply">Apply</a> [click](javascript:alert(1)) ![remote](https://example.com/x)')
        self.assertNotIn('<a ', html)
        self.assertNotIn('<img', html)
        self.assertIn('&lt;a', html)
