"""Structural/contrast checks, not a substitute for assistive-technology review."""
from html.parser import HTMLParser
import re
import unittest
from ui.app import HTML
from ui.workspace import STYLE


class WorkspaceAccessibilityTests(unittest.TestCase):
    def test_unique_ids_and_explicit_form_labels(self):
        class Parser(HTMLParser):
            def __init__(self):
                super().__init__(); self.ids=[]; self.labels=[]; self.fields=[]
            def handle_starttag(self, tag, attrs):
                attrs=dict(attrs)
                if 'id' in attrs:self.ids.append(attrs['id'])
                if tag=='label':self.labels.append(attrs.get('for'))
                if tag in ('input','select') and attrs.get('type')!='hidden':self.fields.append(attrs.get('id'))
        parser=Parser();parser.feed(HTML)
        self.assertEqual(len(parser.ids),len(set(parser.ids)))
        self.assertTrue(set(parser.fields)<=set(parser.labels))
        self.assertTrue(set(parser.labels)<=set(parser.ids))
        self.assertIn('<html lang="en">',HTML)
        self.assertIn('aria-live="polite"',HTML)
        self.assertEqual(HTML.count('<option value="replaced">'),1)
        self.assertIn('label for="result-sort"',HTML)

    def test_both_theme_text_and_control_contrast(self):
        def luminance(color):
            values=[int(color[i:i+2],16)/255 for i in (1,3,5)]
            values=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
            return sum(a*b for a,b in zip(values,(.2126,.7152,.0722)))
        def ratio(a,b):
            a,b=sorted((luminance(a),luminance(b)))
            return (b+.05)/(a+.05)
        for block in re.findall(r':root(?:\[data-theme=dark\])?\{([^}]+)',STYLE)[:2]:
            colors=dict(re.findall(r'--([\w-]+):(#[0-9a-f]{6})',block))
            for foreground in ('text','muted','danger'):
                for background in ('bg','panel','soft'):
                    self.assertGreaterEqual(ratio(colors[foreground],colors[background]),4.5,(foreground,background))
            self.assertGreaterEqual(ratio(colors['accent-text'],colors['accent']),4.5)
            for foreground in ('border','focus'):
                self.assertGreaterEqual(ratio(colors[foreground],colors['panel']),3)
