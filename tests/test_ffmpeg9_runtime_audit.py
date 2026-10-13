import unittest
from tools.audit_image_runtime import ffmpeg9_issues


class RuntimeAuditTests(unittest.TestCase):
    def libraries(self):
        return {k:[v,1,102] for k,v in dict(libavcodec=63,libavformat=63,
            libavutil=61,libavfilter=12,libswscale=10,libswresample=7,libavdevice=63).items()}

    def test_complete_migration(self):
        self.assertEqual(ffmpeg9_issues([dict(path='/ffmpeg',version_output='ffmpeg version 9.0.2 test')],self.libraries()),[])

    def test_old_reader_rejected(self):
        self.assertTrue(ffmpeg9_issues([dict(path='/reader',version_output='ffprobe version 8.0.1 test')],self.libraries()))

    def test_old_or_missing_pyav_libraries_rejected(self):
        libraries=self.libraries();libraries['libavcodec'][0]=62
        self.assertTrue(ffmpeg9_issues([],libraries))
        self.assertTrue(ffmpeg9_issues([],{}))
