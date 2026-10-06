import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from streaming_pipeline import chapter_xml_signature, verify_chapters_preserved


XML = '<Chapters><EditionEntry><EditionUID>1</EditionUID><ChapterAtom><ChapterUID>2</ChapterUID><ChapterTimeStart>00:00:00.000000000</ChapterTimeStart><ChapterDisplay><ChapterString>Chapter 01</ChapterString><ChapterLanguage>eng</ChapterLanguage></ChapterDisplay></ChapterAtom></EditionEntry></Chapters>'


class ChapterPreservationTests(unittest.TestCase):
    def verify(self, before=None, after=None, documents=None, container='matroska,webm'):
        before = before or [(0, 10.001, {'title': 'Chapter 01'})]
        after = after or [(0, 10.000, {'title': 'Chapter 01'})]
        documents = documents or [XML, XML]
        with patch('streaming_pipeline.chapter_summary', side_effect=[before, after]), \
             patch('streaming_pipeline.np.checked_json', return_value={'format': {'format_name': container}}), \
             patch('streaming_pipeline.subprocess.run', side_effect=[SimpleNamespace(stdout=x) for x in documents]) as extract:
            return verify_chapters_preserved('ffprobe', 'source.mkv', 'output.mkv', 60), extract

    def test_inferred_endpoint_difference_requires_identical_native_tree(self):
        result, extract = self.verify()
        self.assertEqual(result['method'], 'exact-native-matroska-tree')
        self.assertEqual(extract.call_count, 2)
        self.assertNotEqual(result['reported_endpoints_before'], result['reported_endpoints_after'])

    def test_changed_stored_start_title_language_flags_uid_or_end_rejected(self):
        for changed in [XML.replace('00:00:00.000000000', '00:00:00.001000000'),
                        XML.replace('Chapter 01', 'Changed'), XML.replace('eng', 'fra'),
                        XML.replace('<ChapterUID>2', '<ChapterUID>3'),
                        XML.replace('</ChapterAtom>', '<ChapterFlagHidden>1</ChapterFlagHidden></ChapterAtom>'),
                        XML.replace('</ChapterAtom>', '<ChapterTimeEnd>00:00:10.000000000</ChapterTimeEnd></ChapterAtom>')]:
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, 'stored chapter tree'):
                self.verify(documents=[XML, changed])

    def test_reported_start_or_title_change_is_never_ignored(self):
        for after in [[(.001, 10, {'title': 'Chapter 01'})], [(0, 10, {'title': 'Changed'})]]:
            with self.assertRaisesRegex(ValueError, 'count, start timestamp or tags'):
                self.verify(after=after)

    def test_non_matroska_mismatch_remains_failure(self):
        with self.assertRaisesRegex(ValueError, 'proof unavailable'):
            self.verify(container='mov,mp4')

    def test_reported_explicit_endpoint_mismatch_cannot_use_inferred_end_exception(self):
        explicit = XML.replace('</ChapterAtom>', '<ChapterTimeEnd>00:00:10.000000000</ChapterTimeEnd></ChapterAtom>')
        with self.assertRaisesRegex(ValueError, 'explicitly stored end'):
            self.verify(documents=[explicit, explicit])

    def test_missing_extractor_does_not_approve(self):
        with patch('streaming_pipeline.chapter_summary', side_effect=[[(0, 10, {})], [(0, 11, {})]]), \
             patch('streaming_pipeline.np.checked_json', return_value={'format': {'format_name': 'matroska'}}), \
             patch('streaming_pipeline.subprocess.run', side_effect=FileNotFoundError):
            with self.assertRaises(FileNotFoundError):
                verify_chapters_preserved('ffprobe', 'source', 'output', 60)

    def test_native_tree_formatting_only_is_ignored(self):
        self.assertEqual(chapter_xml_signature(XML), chapter_xml_signature('\ufeff'+XML.replace('><', '>\n  <')))
        with self.assertRaises(ValueError):
            chapter_xml_signature('<!ENTITY x "value">'+XML)

    def test_matching_reported_chapters_remains_fast(self):
        result, extract = self.verify(before=[(0, 10, {})], after=[(0, 10, {})])
        self.assertEqual(result['method'], 'reported-chapters')
        extract.assert_not_called()


if __name__ == '__main__':
    unittest.main()
