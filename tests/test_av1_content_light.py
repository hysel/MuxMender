import struct,tempfile,unittest,sys,json,subprocess,shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from av1_content_light import patch_packet,restore_ivf,obus,leb,constant_light,finalize,restore_container,available


class ContentLightTests(unittest.TestCase):
    def test_finalizer_reattaches_artwork_from_second_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);encoded=root/'encoded.mkv';output=root/'out.mkv';encoded.write_bytes(b'encoded')
            packet=b'\x32\x02\x33\x44'
            ivf=b'DKIF'+struct.pack('<HH',0,32)+b'AV01'+b'\0'*20+struct.pack('<IQ',len(packet),0)+packet
            def execute(command,*args):
                if command[-1].endswith('.json'):
                    Path(command[-3]).write_bytes(b'video');Path(command[-1]).write_text('{}')
                else:Path(command[-1]).write_bytes(b'output')
            covers=Mock(side_effect=lambda command,*args,**kwargs:command)
            work=SimpleNamespace(args=SimpleNamespace(ffmpeg='ffmpeg'),directory=root,guard=lambda:None,
                hdr_intermediates={},execute=execute,preserve_covers=covers,
                probe=lambda p:dict(streams=[dict(index=0,codec_type='video',width=64,height=64,sample_aspect_ratio='1:1')]))
            finalize(work,encoded,output,b'\0'*4,'test',1)
            self.assertEqual(covers.call_args.kwargs['input_index'],1)
            self.assertEqual(len(work.hdr_intermediates[output.resolve()]),2)

    def test_only_observed_constant_complete_metadata_is_restored(self):
        def frame(a,b):return dict(side_data_list=[dict(side_data_type='Content light level metadata',max_content=a,max_average=b)])
        self.assertEqual(constant_light([frame(0,0),frame(0,0)]),b'\0'*4)
        self.assertEqual(constant_light([frame(500,100)]),struct.pack('>HH',500,100))
        for frames in [[],[{}],[frame(0,0),{}],[frame(0,0),frame(1,0)]]:
            self.assertIsNone(constant_light(frames))

    def test_insert_zero_values_preserves_other_obus(self):
        packet=b'\x12\x00\x0a\x02\x11\x22\x2a\x02\x02\x80\x32\x02\x33\x44'
        out,digest=patch_packet(packet,b'\0'*4)
        self.assertEqual(out,packet[:-4]+b'\x2a\x06\x01'+b'\0'*4+b'\x80'+packet[-4:])
        self.assertEqual(patch_packet(out,b'\0'*4),(out,digest))
        self.assertEqual(patch_packet(out,b'\0\x64\0\x32')[1],digest)

    def test_bad_obus_rejected(self):
        for packet in [b'\x80',b'\x30\x01',b'\x32\x80',b'\x32\x04a',b'\x12\0']:
            with self.assertRaises(ValueError):patch_packet(packet,b'\0'*4)

    def test_ivf_timing_and_nonmetadata_bytes_preserved(self):
        header=b'DKIF'+struct.pack('<HH',0,32)+b'AV01'+b'\0'*20;packet=b'\x32\x02\x33\x44'
        with tempfile.TemporaryDirectory() as directory:
            a=Path(directory)/'a.ivf';b=Path(directory)/'b.ivf'
            a.write_bytes(header+struct.pack('<IQ',len(packet),1234)+packet)
            proof=restore_ivf(a,b,b'\0'*4);data=b.read_bytes()
            self.assertEqual(data[:32],header);self.assertEqual(data[36:44],struct.pack('<Q',1234))
            self.assertEqual(proof['packets'],1);self.assertTrue(proof['picture_payload_unchanged'])
            with self.assertRaises(ValueError):restore_ivf(a,b,b'\0'*4)


@unittest.skipUnless(sys.platform=='linux' and available() and shutil.which('ffmpeg') and shutil.which('ffprobe'),
                     'Optional AV1 packet-copy qualification runs on Linux only')
class ContainerRepairTests(unittest.TestCase):
    def test_generated_clip_exact_pictures_timing_and_collision_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'generated.mkv';output=Path(directory)/'restored.mkv'
            subprocess.run(['ffmpeg','-v','error','-nostdin','-n','-f','lavfi','-i','testsrc2=size=64x64:rate=5',
                '-frames:v','3','-vf','format=yuv420p10le','-c:v','libaom-av1','-cpu-used','8','-threads','1',
                '-color_primaries','bt2020','-color_trc','smpte2084','-colorspace','bt2020nc',str(source)],check=True,capture_output=True,timeout=30)
            original=source.read_bytes();proof=restore_container(source,output,b'\0'*4)
            self.assertEqual(proof['packets'],3)
            def frames(path):
                return json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_frames','-of','json',str(path)],timeout=30))['frames']
            before=frames(source);after=frames(output)
            self.assertEqual([f['pts'] for f in before],[f['pts'] for f in after])
            self.assertEqual(constant_light(after),b'\0'*4)
            def digest(path):
                return subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-map','0:v:0','-f','hash','-hash','sha256','-'],timeout=30)
            self.assertEqual(digest(source),digest(output))
            for destination in [source,output]:
                with self.assertRaises((ValueError,FileExistsError)):restore_container(source,destination,b'\0'*4)
            self.assertEqual(source.read_bytes(),original)
