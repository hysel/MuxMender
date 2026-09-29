import tempfile
import unittest
from pathlib import Path
from hevc_content_light import restore,patch_packet,content_light,messages,sei,START


def frame(value):
    return {'side_data_list':[{'side_data_type':'Content light level metadata','max_content':value,'max_average':15}]}


def packet(value):
    return b'\x00\x00\x00\x01'+sei(b'\x4e\x01',[(144,content_light(frame(value))),(4,b'untouched')])+b'\x00\x00\x00\x01\x02\x01\x80\x55'


class ContentLightTests(unittest.TestCase):
    def test_preserves_picture_and_other_sei(self):
        original=packet(657);changed,digest=patch_packet(original,content_light(frame(711)))
        self.assertEqual(patch_packet(original,content_light(frame(657)))[1],digest)
        self.assertIn(b'untouched',changed)
        records=[];starts=list(START.finditer(changed))
        for i,m in enumerate(starts):
            nal=changed[m.end():starts[i+1].start() if i+1<len(starts) else len(changed)]
            if (nal[0]>>1)&63==39:records.extend(messages(nal))
        self.assertEqual([p for k,p in records if k==144],[content_light(frame(711))])

    def test_display_order_maps_to_coded_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=packet(657);source=root/'a.hevc';source.write_bytes(p*3)
            proof=restore(source,root/'b.hevc',[frame(1),frame(2),frame(3)],
                          [{'pkt_pos':0},{'pkt_pos':len(p)*2},{'pkt_pos':len(p)}])
            expected=b''.join(patch_packet(p,content_light(frame(v)))[0] for v in (1,3,2))
            self.assertEqual((root/'b.hevc').read_bytes(),expected)
            self.assertTrue(proof['picture_payload_unchanged'])
            self.assertEqual(source.read_bytes(),p*3)

    def test_invalid_mappings_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'a.hevc';source.write_bytes(packet(1)*2)
            for positions in ([0,0],[1,10],[0,-1],[0,None]):
                with self.assertRaises(ValueError):restore(source,root/'b.hevc',[frame(1),frame(2)],[{'pkt_pos':v} for v in positions])
            with self.assertRaises(ValueError):restore(source,source,[frame(1)],[{'pkt_pos':0}])

    def test_frame_count_and_packet_shape_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'a.hevc';source.write_bytes(packet(1))
            with self.assertRaises(ValueError):restore(source,Path(tmp)/'b.hevc',[frame(1)],[])
        with self.assertRaises(ValueError):patch_packet(packet(1)*2,b'1234')
        with self.assertRaises(ValueError):messages(b'\x4e\x01\x90\x04\x01')

    def test_metadata_must_be_exact_unsigned_values(self):
        for item in ({},frame(-1),frame(65536),frame('500')):
            with self.assertRaises(ValueError):content_light(item)


if __name__=='__main__':unittest.main()
