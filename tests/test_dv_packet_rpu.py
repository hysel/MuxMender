import tempfile
import unittest
from pathlib import Path
from xml.sax.saxutils import quoteattr
from dv_packet_rpu import hex_payload,packet_rpu,write_selected


def dump(data):
    return '\n'+ '\n'.join(f'{i:08x}: '+(' '.join(data[i+j:i+j+2].hex() for j in range(0,min(16,len(data)-i),2))).ljust(39)+'  '+'.'*min(16,len(data)-i) for i in range(0,len(data),16))+'\n'


def packet(marker):
    nals=[b'\x02\x01\x80',b'\x7c\x01\x19'+bytes([marker])]
    return b''.join(len(n).to_bytes(4,'big')+n for n in nals)


class PacketRpuTests(unittest.TestCase):
    def test_packet_payload_dump_is_disposable_work_not_report(self):
        from replacement_cleanup import disposable
        self.assertTrue(disposable(Path('source-rpu-packets.xml')))
        self.assertFalse(disposable(Path('validation.xml')))

    def test_hex_xml_whitespace_and_lengths(self):
        for length in range(1,80):
            data=bytes(range(length));self.assertEqual(hex_payload(dump(data).replace('\n',' ')),data)
        with self.assertRaises(ValueError):hex_payload(dump(b'abc').replace('00000000','00000010'))

    def test_one_picture_and_one_rpu_required(self):
        self.assertEqual(packet_rpu(packet(3),4),b'\x19\x03')
        for data in [packet(3)[:-1],packet(3)+packet(4),b'\x00\x00',b'\x00\x00\x00\x02\x7c\x01']:
            with self.assertRaises(ValueError):packet_rpu(data,4)

    def run_mapping(self,frames,packets):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);xml=root/'packets.xml';out=root/'rpu.bin'
            xml.write_text('<ffprobe><packets>'+''.join('<packet pos='+quoteattr(str(pos))+' pts_time='+quoteattr(pts)+' size='+quoteattr(str(len(data)))+' data='+quoteattr(dump(data))+'/>' for pos,pts,data in packets)+'</packets></ffprobe>')
            count=write_selected(xml,frames,out,4)
            return count,out.read_bytes()

    def test_display_order_and_unselected_preroll(self):
        frames=[dict(pkt_pos='10',best_effort_timestamp_time='0.1'),dict(pkt_pos='30',best_effort_timestamp_time='0.2')]
        count,data=self.run_mapping(frames,[(5,'0.0',packet(0)),(30,'0.2',packet(2)),(10,'0.1',packet(1))])
        self.assertEqual(count,2);self.assertEqual(data,b'\0\0\0\1\x19\x01\0\0\0\1\x19\x02')

    def test_missing_duplicate_or_changed_identity_rejected(self):
        frames=[dict(pkt_pos='10',best_effort_timestamp_time='0.1')]
        for packets in [[],[(10,'0.2',packet(1))],[(10,'0.1',packet(1)),(10,'0.1',packet(2))]]:
            with self.assertRaises(ValueError):self.run_mapping(frames,packets)
        with self.assertRaises(ValueError):self.run_mapping(frames*2,[(10,'0.1',packet(1))])
