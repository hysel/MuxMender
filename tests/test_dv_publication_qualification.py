import copy
import unittest
from dv_mel import publication_qualified


class PublicationQualificationTests(unittest.TestCase):
    def evidence(self,profile=5,kind='MEL'):
        score=dict(mean=96,p5=93,frames=24,passed=True)
        result=dict(status='validated-research-copy',settings=dict(encoder='hevc_nvenc'),
            source_sha256='a'*64,source_bytes=100,output_sha256='b'*64,
            source_unchanged=True,copied_tracks_preserved=True,
            frame_checks=dict(frames=24,timing_preserved=True,static_hdr_preserved=True,
                frame_picture_preserved=True,rpu_present_every_frame=True),
            quality=dict(self=dict(score),candidate=dict(score),domain='dv-libplacebo-common-render-v1'),
            rpu_frames=24,rpu_digest='c'*64,configuration=dict(dv_profile=profile))
        if profile==7:
            result['layer_checks']=dict(frames=24,enhancement_types=[kind],scope='layer-preservation-only',
                rpu_sha256='c'*64,enhancement_video_sha256='d'*64,
                configuration=dict(dv_profile=7,el_present_flag=1,bl_present_flag=1,rpu_present_flag=1))
            from dv_render import combine_quality_views
            result['quality']=combine_quality_views(result['quality'],copy.deepcopy(result['quality']))
            if kind=='FEL':
                result['quality'].update(domain='dv-felbaker-common-render-v1',native_fel_quality_evaluated=True,
                    views={name:dict(self=dict(score),candidate=dict(score)) for name in ('native_dv','compatible_fallback')})
        return result

    def qualify(self,result,profile=5,**kwargs):
        return publication_qualified(result,'a'*64,100,'b'*64,profile,90,90,**kwargs)

    def test_qualified_paths_and_explicit_research_separation(self):
        for profile,kind in [(5,'MEL'),(7,'MEL'),(7,'FEL')]:
            result=self.evidence(profile,kind)
            self.assertTrue(self.qualify(result,profile))
            self.assertFalse(self.qualify(result,profile,experimental=True))
            result['status']='unqualified-fel-research-copy'
            self.assertFalse(self.qualify(result,profile))

    def test_missing_or_changed_full_evidence_cannot_publish(self):
        for field in ('source_sha256','source_unchanged','copied_tracks_preserved','output_sha256'):
            result=self.evidence();result[field]=None
            with self.assertRaises(ValueError):self.qualify(result)
        for field in ('timing_preserved','static_hdr_preserved','frame_picture_preserved','rpu_present_every_frame'):
            result=self.evidence();result['frame_checks'][field]=False
            with self.assertRaises(ValueError):self.qualify(result)
        result=self.evidence();result['quality']['candidate']['mean']=89
        with self.assertRaises(ValueError):self.qualify(result)
        result=self.evidence(7);del result['layer_checks']['enhancement_video_sha256']
        with self.assertRaises(ValueError):self.qualify(result,7)
        result=self.evidence(7);del result['quality']['views']['compatible_fallback']
        with self.assertRaises(ValueError):self.qualify(result,7)

    def test_other_backends_remain_evaluable_but_not_implicitly_certified(self):
        result=self.evidence();result['settings']['encoder']='hevc_amf'
        self.assertFalse(self.qualify(result))
        self.assertFalse(self.qualify(self.evidence(8),8))
