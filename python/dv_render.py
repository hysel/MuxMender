"""Native Dolby Vision rendering for comparisons, never output publication.

Both files use the same libplacebo transform and common HDR target before the
existing metric. This is a rendered comparison, not a Dolby-certified metric.
FEL is not accepted here: FFmpeg's filter does not feed its enhancement layer
into libplacebo's separate composition interface.
"""
import json
import re
from pathlib import Path
from auto_optimize import Workflow, main_video
from hdr_auto import quality_graph


RENDER_FILTER=('libplacebo=apply_dolbyvision=1:format=yuv420p10le:colorspace=bt2020nc:'
    'color_primaries=bt2020:color_trc=smpte2084:range=tv:peak_detect=0:deband=0:dithering=none')


def combine_quality_views(native, fallback):
    """Neither a native DV view nor its compatible fallback may hide failure."""
    import copy
    result=copy.deepcopy(native)
    for key in ('self','candidate'):
        if native[key]['frames']!=fallback[key]['frames']:raise ValueError('Quality views cover different frames')
        result[key]=dict(native[key],mean=min(native[key]['mean'],fallback[key]['mean']),
            p5=min(native[key]['p5'],fallback[key]['p5']),passed=native[key]['passed'] and fallback[key]['passed'])
    result['views']=dict(native_dv={key:dict(native[key]) for key in ('self','candidate')},compatible_fallback=fallback)
    result['note']='Minimum native-DV and compatible-fallback scores; both views must meet requested quality floors'
    return result


def render_command(ffmpeg, source, output, *, device=0):
    if type(device) is not int or device<0:raise ValueError('Invalid Vulkan device index')
    return [ffmpeg,'-v','verbose','-nostdin','-n','-init_hw_device',f'vulkan=gpu:{device}',
        '-filter_hw_device','gpu','-noautorotate','-i',str(source),'-map','0:V:0','-vf',
        RENDER_FILTER,
        '-fps_mode','passthrough','-c:v','ffv1','-level','3','-color_primaries','bt2020',
        '-color_trc','smpte2084','-colorspace','bt2020nc','-color_range','tv',str(output)]


def native_quality_command(ffmpeg, candidate, source, name, rate, *, device=0):
    from auto_optimize import quality_command
    if type(device) is not int or device<0:raise ValueError('Invalid Vulkan device index')
    # No frame trim, scaling, interpolation or temporary video. Preservation
    # checks establish input alignment; the metric must cover all those frames.
    graph=quality_graph(name,rate).replace('[0:V:0]','[dv0]').replace('[1:V:0]','[dv1]')
    graph=f'[0:V:0]{RENDER_FILTER}[dv0];[1:V:0]{RENDER_FILTER}[dv1];'+graph
    command=quality_command(ffmpeg,candidate,source,graph)
    return command[:1]+['-init_hw_device',f'vulkan=gpu:{device}','-filter_hw_device','gpu']+command[1:]


def single_layer_configuration(metadata):
    video=main_video(metadata)
    configs=[s for s in video.get('side_data_list',[]) if 'dv_profile' in s]
    if len(configs)!=1:raise ValueError('Native render requires one DV configuration')
    config=configs[0]
    if (type(config.get('dv_profile')) is not int or config['dv_profile'] not in (5,8)
            or config.get('el_present_flag')!=0 or config.get('bl_present_flag')!=1
            or config.get('rpu_present_flag')!=1):
        raise ValueError('Native single-layer renderer cannot verify missing RPU or enhancement composition')
    return config


def render_configuration(metadata, frames, mel_evidence=None):
    if mel_evidence is None:return single_layer_configuration(metadata)
    from dv_layer_evidence import profile7_configuration
    configs=[s for s in main_video(metadata).get('side_data_list',[]) if 'dv_profile' in s]
    if len(configs)!=1:raise ValueError('Expected one layered DV configuration')
    config=profile7_configuration(configs[0])
    if (mel_evidence.get('scope')!='layer-preservation-only' or mel_evidence.get('enhancement_types')!=['MEL']
            or mel_evidence.get('frames')!=frames or mel_evidence.get('configuration')!=config
            or type(mel_evidence.get('enhancement_video_bytes')) is not int or mel_evidence['enhancement_video_bytes']<=0
            or any(not re.fullmatch('[0-9a-f]{64}',mel_evidence.get(k,'')) for k in
                   ('rpu_sha256','enhancement_video_sha256'))):
        raise ValueError('Native MEL rendering needs complete verified layer evidence; FEL composition is separate')
    return config


def measure_native_quality(workflow, source, candidate, frames, rate, label, *, device=None,mel_evidence=None):
    if not isinstance(label,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',label):
        raise ValueError('Native render label must be a simple name')
    if type(frames) is not int or frames<=0:raise ValueError('Native render needs complete frame coverage')
    before=workflow.probe(source);after=workflow.probe(candidate)
    if render_configuration(before,frames,mel_evidence)!=render_configuration(after,frames,mel_evidence):
        raise ValueError('Native comparison DV configuration changed')
    directory=Path(workflow.directory)/label;directory.mkdir()
    work=Workflow(workflow.args,directory,workflow.guard)
    duration=float(before['format']['duration'])
    from auto_optimize import quality_summary
    from native_pipeline import stage
    from job_tracking import progress
    from dv_renderer import discover
    import os
    if any(main_video(before).get(k)!=main_video(after).get(k) for k in ('width','height','sample_aspect_ratio')):
        raise ValueError('Native comparison changed geometry or aspect ratio')
    scores={}
    renderer=discover(work.args.ffmpeg,directory,work.guard,device=device)
    device=renderer['device']['index']
    for kind,path in (('self',source),('candidate',candidate)):
        work.guard()
        name='native-'+kind+'-vmaf.json'
        command=native_quality_command(work.args.ffmpeg,path,source,name,rate,device=device)
        progress('Native Dolby Vision '+kind+' quality',unit='frames',detail=f'Comparing all {frames} frames')
        with (directory/(kind+'.log')).open('x',encoding='utf-8') as log:
            log.write(json.dumps(command)+'\n')
            stage(command,duration,timeout=work.args.timeout,stall=180,guard=work.guard,
                  observe=lambda line:log.write(line) and False,cwd=directory,expected_frames=frames,
                  env=dict(os.environ,**renderer['environment']))
        scores[kind]=quality_summary(json.loads((directory/name).read_text()),frames,90,90)
        if kind=='self' and not scores[kind]['passed']:raise ValueError('Native quality self-check failed')
    result=dict(**scores)
    if any(result[k].get('frames')!=frames for k in ('self','candidate')):
        raise ValueError('Native-render metric coverage is incomplete')
    result.update(domain='dv-libplacebo-common-render-v1',
        note='Both DV pictures reshaped by libplacebo before common HDR metric; not Dolby certification',
        publication_authorized=False,renderer='libplacebo',vulkan_device=device,
        intermediate_media_written=False,hardware_renderer=renderer['device'])
    with (directory/'native-quality.json').open('x',encoding='utf-8') as handle:json.dump(result,handle,indent=2)
    return result
