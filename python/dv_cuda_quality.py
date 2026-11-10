"""Job-local native Dolby Vision scoring using the canonical rendered pixels.

GPU scoring requires an exact short CPU trial and measured speed gain. Native
rendering, full frame coverage, requested floors and CPU fallback are unchanged.
"""
from fractions import Fraction
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace
from copy import copy

from cuda_quality import BOUNDARY_MARGIN,equivalent,scores


def commands(cpu, gpu, candidate, reference, video, rate, name, directory, device, *, paired=False, frame_count=None):
    from dv_render import RENDER_FILTER
    from hdr_auto import RENDER_FILTER as COMMON_RENDER
    rate=Fraction(rate)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+',name) or type(device) is not int or device<0:
        raise ValueError('Invalid native scoring report or device')
    if rate<=0:raise ValueError('Invalid native comparison rate')
    if frame_count is not None and (type(frame_count) is not int or frame_count<=0):
        raise ValueError('Invalid native comparison calibration length')
    if any(type(video.get(k)) is not int or video[k]<=0 for k in ('width','height')):
        raise ValueError('Invalid native comparison geometry')
    clock=f'settb=AVTB,setpts=N*{rate.denominator}/({rate.numerator}*TB)'
    producers=[]
    for index,path in enumerate((candidate,reference)):
        prefix=f'trim=end_frame={frame_count},' if frame_count is not None else ''
        producers.append([cpu,'-v','error','-xerror','-nostdin','-init_hw_device',f'vulkan=gpu:{device}',
            '-filter_hw_device','gpu','-filter_threads','2','-threads','2','-noautorotate','-i',str(path),
            '-map','0:V:0','-vf',prefix+RENDER_FILTER+','+COMMON_RENDER+','+clock,'-pix_fmt','yuv420p10le','-threads:v','2',
            '-enc_time_base:v',str(1/rate),
            '-fps_mode','passthrough','-progress',str(Path(directory)/f'render-{index}-progress.txt'),
            '-nostats','-f','rawvideo','pipe:1'])
    consumer=[gpu,'-hide_banner','-v','warning','-nostdin','-init_hw_device','cuda=metric:0','-filter_hw_device','metric']
    for index in range(2):
        consumer+=['-f','rawvideo','-pixel_format','yuv420p10le','-video_size',f"{video['width']}x{video['height']}",
                   '-framerate',str(rate),'-analyzeduration','0','-probesize','32','-i',f'pipe:input-{index}']
    graph=f'[0:v]{clock},hwupload_cuda[d];[1:v]{clock},hwupload_cuda[r];[d][r]libvmaf_cuda=n_threads=0:log_fmt=json:log_path={name}'
    if paired:
        graph=(f'[0:v]{clock},hwupload_cuda[d];[1:v]{clock},hwupload_cuda[r];'
            '[r]split=3[s0][s1][r0];[s0][s1]libvmaf_cuda=n_threads=0:log_fmt=json:log_path=self-vmaf.json[s];'
            '[d][r0]libvmaf_cuda=n_threads=0:log_fmt=json:log_path=candidate-vmaf.json[c]')
    consumer+=['-filter_complex_threads','2','-filter_complex',graph,'-progress','pipe:1','-nostats','-f','null','-']
    if paired:consumer[-3:-3]=['-map','[s]','-map','[c]']
    return consumer,producers


class Scorer:
    def __init__(self, workflow, renderer, before, after, rate):
        from cuda_quality import discover
        from dv_render import RENDER_FILTER
        from hdr_auto import RENDER_FILTER as COMMON_RENDER
        from auto_optimize import main_video
        self.workflow=workflow;self.renderer=renderer;self.video=main_video(before);self.rate=rate
        self.context=discover(workflow.args.ffmpeg)
        if any(type(self.video.get(k)) is not int or not 0<self.video[k]<=limit
               for k,limit in (('width',3840),('height',2160))):
            self.context=None  # Outside tested scoring scope stays on CPU.
        self.states=workflow.native_quality_profiles
        self.prefix_frames=None
        keys=('codec_name','width','height','pix_fmt','field_order','color_range','color_space',
              'color_transfer','color_primaries','chroma_location','side_data_list')
        self.profile=json.dumps(dict(domain='native-dv-pipe-v1',binding=self.context['binding'] if self.context else None,
            renderer=renderer['device'],rate=str(Fraction(rate)),render=RENDER_FILTER,common=COMMON_RENDER,
            source={k:self.video.get(k) for k in keys},output={k:main_video(after).get(k) for k in keys}),sort_keys=True)

    def qualify_prefix(self, candidate, reference, count):
        """A bounded job-local trial is separate from full result evidence."""
        from dv_render import native_quality_command
        from native_pipeline import stage
        from job_tracking import progress
        w=self.workflow;count=min(count,120);seconds=float(Fraction(count,1)/Fraction(self.rate))
        folder=Path(w.directory)/'gpu-calibration';folder.mkdir()
        args=copy(w.args);args.timeout=min(w.args.timeout,180)
        child=object.__new__(Scorer)
        child.__dict__=dict(self.__dict__,workflow=SimpleNamespace(args=args,directory=folder,
            guard=w.guard,native_quality_profiles=self.states),prefix_frames=count)
        def cpu(kind,path):
            progress('Checking native GPU scorer against CPU',unit='frames',
                detail=f'{count} calibration frames in {kind} view; final checks still cover the complete video')
            command=native_quality_command(w.args.ffmpeg,path,reference,'native-'+kind+'-vmaf.json',
                self.rate,device=self.renderer['device']['index'],frame_count=count)
            timing={}
            with (folder/(kind+'.log')).open('x') as log:
                stage(command,seconds,timeout=args.timeout,stall=min(180,args.timeout),guard=w.guard,
                    observe=lambda line:log.write(line) and False,cwd=folder,expected_frames=count,
                    env=dict(os.environ,**self.renderer['environment']),measurement=timing)
            return timing
        result=child.run_pair(candidate,reference,count,seconds,cpu)
        return dict(passed=bool(result) and all(result[k].get('qualified_for_later_checks') is True
            for k in ('self','candidate')),frames=count,scope='Job-local scorer calibration only; not full-video validation',
            views=result)

    def cpu_pair(self, cpu, candidate, reference, count):
        from auto_optimize import quality_summary
        timing={'self':cpu('self',reference)}
        path=Path(self.workflow.directory)/'native-self-vmaf.json'
        if not quality_summary(json.loads(path.read_text()),count,90,90)['passed']:
            raise ValueError('Native quality self-check failed')
        timing['candidate']=cpu('candidate',candidate)
        return timing

    def run_pair(self, candidate, reference, count, duration, cpu):
        """Render the reference once while retaining two complete quality views."""
        from auto_optimize import quality_summary
        from job_tracking import replace_record,progress
        from native_stream import stage
        w=self.workflow;key='paired-v1:'+self.profile;state=self.states.get(key)
        qualifying=(self.context is not None and state is None and 0<count<=6000 and duration>0
                    and (duration<=60 or self.prefix_frames is not None and count<=120))
        if self.context is None or state is False:return None
        prefix_proof=None
        if state is None and not qualifying:
            try:
                prefix_proof=self.qualify_prefix(candidate,reference,count)
            except Exception as exc:
                w.guard()
                prefix_proof=dict(passed=False,diagnostic=type(exc).__name__+': '+str(exc)[:400])
            self.states[key]=bool(prefix_proof.get('passed'))
            if not self.states[key]:
                self.cpu_pair(cpu,candidate,reference,count)
                return {k:dict(backend='cpu',domain='native-dv-paired-v1',automatic_calibration=prefix_proof,
                    reason='Matching native GPU trial did not qualify; complete CPU checks used') for k in ('self','candidate')}
        mean=getattr(w.args,'vmaf_mean',90);p5=getattr(w.args,'vmaf_p5',90)
        paths={k:Path(w.directory)/('native-'+k+'-vmaf.json') for k in ('self','candidate')}
        cpu_timing=None
        if qualifying:
            cpu_timing=self.cpu_pair(cpu,candidate,reference,count)
        info={k:dict(backend='cpu',domain='native-dv-paired-v1') for k in paths}
        if prefix_proof is not None:
            for k in paths:info[k]['automatic_calibration']=prefix_proof
        cpu_running=False;cpu_ready=qualifying
        try:
            folder=Path(w.directory)/'paired-cuda';folder.mkdir()
            command,producers=commands(w.args.ffmpeg,self.context['binary'],candidate,reference,self.video,
                self.rate,'candidate.json',folder,self.renderer['device']['index'],paired=True,frame_count=self.prefix_frames)
            environment=dict(os.environ)
            environment['LD_LIBRARY_PATH']=str(Path(self.context['binary']).parent.parent/'lib')+':'+environment.get('LD_LIBRARY_PATH','')
            progress('Comparing native Dolby Vision on GPU',unit='frames',
                     detail=f'Checking source and candidate together; all {count} frames in each view')
            timing={}
            with (folder/'score.log').open('x') as log:
                stage(command,duration,producer_commands=producers,
                    producer_env=dict(os.environ,**self.renderer['environment']),env=environment,directory=folder,
                    expected_frames=count,guard=w.guard,timeout=w.args.timeout,stall=180,
                    observe=lambda line:log.write(line) and False,measurement=timing)
            gpu={k:folder/(k+'-vmaf.json') for k in paths}
            summaries={}
            for k in paths:
                scores(gpu[k],count)
                summaries[k]=quality_summary(json.loads(gpu[k].read_text()),count,mean,p5)
            if qualifying:
                proofs={k:equivalent(paths[k],gpu[k],count,mean,p5) for k in paths}
                faster=(all(t.get('scope')=='native-stage-active-v1' for t in cpu_timing.values()) and
                        timing.get('scope')=='native-stage-active-v1' and
                        timing['execution_seconds']<sum(t['execution_seconds'] for t in cpu_timing.values())*.95)
                self.states[key]=all(p['passed'] for p in proofs.values()) and faster
                for k in paths:
                    info[k].update(qualification=proofs[k],qualified_for_later_checks=self.states[key],
                        cpu_seconds=cpu_timing[k]['execution_seconds'],paired_gpu_seconds=timing['execution_seconds'])
                return info
            near=any(min(abs(s['mean']-mean),abs(s['p5']-p5))<=BOUNDARY_MARGIN for s in summaries.values())
            if near:
                cpu_running=True
                self.cpu_pair(cpu,candidate,reference,count)
                cpu_running=False;cpu_ready=True
                proofs={k:equivalent(paths[k],gpu[k],count,mean,p5) for k in paths}
                if not all(p['passed'] for p in proofs.values()):self.states[key]=False
                for k in paths:info[k].update(qualification=proofs[k],reason='Quality threshold confirmed with CPU')
                return info
            for k in paths:
                replace_record(gpu[k],paths[k])
                info[k].update(backend='cuda',runtime=self.context['binding'],
                    paired_gpu_seconds=timing['execution_seconds'],qualification='matching-job-local-native-paired-trial')
            return info
        except Exception as exc:
            if cpu_running:
                self.states[key]=False
                raise  # A failed CPU check must not be run again as GPU fallback.
            w.guard();self.states[key]=False
            if not cpu_ready:self.cpu_pair(cpu,candidate,reference,count)
            for k in paths:info[k].update(reason='GPU scoring unavailable; complete CPU check used',
                                        diagnostic=type(exc).__name__+': '+str(exc)[:400])
            return info

    def run(self, candidate, reference, name, count, duration, cpu):
        from auto_optimize import quality_summary
        from job_tracking import replace_record
        from native_stream import stage
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',name):
            raise ValueError('Invalid native scoring report name')
        w=self.workflow;destination=Path(w.directory)/name
        info=dict(backend='cpu',domain='native-dv-pipe-v1')
        state=self.states.get(self.profile)
        qualifying=self.context is not None and state is None and 0<duration<=60 and 0<count<=6000
        if self.context is None or state is False or (state is None and not qualifying):
            cpu();return info
        mean=getattr(w.args,'vmaf_mean',90);p5=getattr(w.args,'vmaf_p5',90)
        cpu_timing=cpu() if qualifying else None
        cpu_running=False;cpu_ready=qualifying
        try:
            folder=destination.with_suffix('');folder=folder.with_name(folder.name+'-cuda');folder.mkdir()
            command,producers=commands(w.args.ffmpeg,self.context['binary'],candidate,reference,self.video,
                                      self.rate,'score-vmaf.json',folder,self.renderer['device']['index'])
            environment=dict(os.environ)
            environment['LD_LIBRARY_PATH']=str(Path(self.context['binary']).parent.parent/'lib')+':'+environment.get('LD_LIBRARY_PATH','')
            timing={}
            with (folder/'score.log').open('x') as log:
                stage(command,duration,producer_commands=producers,
                    producer_env=dict(os.environ,**self.renderer['environment']),env=environment,directory=folder,
                    expected_frames=count,guard=w.guard,timeout=w.args.timeout,stall=180,
                    observe=lambda line:log.write(line) and False,measurement=timing)
            gpu=folder/'score-vmaf.json';scores(gpu,count)
            result=quality_summary(json.loads(gpu.read_text()),count,mean,p5)
            if qualifying:
                proof=equivalent(destination,gpu,count,mean,p5)
                faster=(cpu_timing.get('scope')==timing.get('scope')=='native-stage-active-v1' and
                        timing['execution_seconds']<cpu_timing['execution_seconds']*.95)
                self.states[self.profile]=proof['passed'] and faster
                return dict(info,qualification=proof,qualified_for_later_checks=self.states[self.profile],
                            cpu_seconds=cpu_timing.get('execution_seconds'),gpu_seconds=timing.get('execution_seconds'))
            if min(abs(result['mean']-mean),abs(result['p5']-p5))<=BOUNDARY_MARGIN:
                cpu_running=True;cpu()
                cpu_running=False;cpu_ready=True
                proof=equivalent(destination,gpu,count,mean,p5)
                if not proof['passed']:self.states[self.profile]=False
                return dict(info,qualification=proof,reason='Quality threshold confirmed with CPU')
            replace_record(gpu,destination)
            return dict(info,backend='cuda',runtime=self.context['binding'],gpu_seconds=timing['execution_seconds'],
                        qualification='matching-job-local-native-trial')
        except Exception as exc:
            if cpu_running:
                self.states[self.profile]=False
                raise
            w.guard()
            self.states[self.profile]=False
            if not cpu_ready:cpu()
            return dict(info,reason='GPU scoring unavailable; complete CPU check used',
                        diagnostic=type(exc).__name__+': '+str(exc)[:400])
