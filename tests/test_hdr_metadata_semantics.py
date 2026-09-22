import unittest
from hdr10plus_validation import canonical_hdr_metadata


class HDRMetadataSemanticsTests(unittest.TestCase):
    def test_equivalent_mastering_fractions_only(self):
        a=[dict(side_data_type='Mastering display metadata', red_x='35400/50000',
                min_luminance='50/10000', max_luminance='40000000/10000')]
        b=[dict(side_data_type='Mastering display metadata', red_x='177/250',
                min_luminance='1/200', max_luminance='4000/1')]
        self.assertEqual(canonical_hdr_metadata(a),canonical_hdr_metadata(b))
        self.assertEqual(a[0]['red_x'],'35400/50000')
        b[0]['red_x']='178/250'
        self.assertNotEqual(canonical_hdr_metadata(a),canonical_hdr_metadata(b))
        b[0]['red_x']='0/0'
        with self.assertRaises(ValueError):canonical_hdr_metadata(b)

    def test_dynamic_metadata_and_missing_properties_are_not_normalized_away(self):
        a=[dict(side_data_type='HDR10+ metadata', anchors=[1,2])]
        b=[dict(side_data_type='HDR10+ metadata', anchors=[2,1])]
        self.assertNotEqual(canonical_hdr_metadata(a),canonical_hdr_metadata(b))
        self.assertNotEqual(canonical_hdr_metadata(a),canonical_hdr_metadata([]))
