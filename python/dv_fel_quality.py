"""Streaming native FEL research comparison shared by command-line frontends.

Optional renderer dependencies are explicit. No automatic admission, output
replacement, or dependency installation is authorized by this module.
"""
from fractions import Fraction
import json
import os
from pathlib import Path
import subprocess
import sys


def renderer_plugin(args):
    """Resolve an explicit or bundled dependency, never a GPU/media allowlist."""
    explicit=getattr(args,'fel_render_plugin',None)
    candidates=[Path(explicit)] if explicit else [
        Path(__file__).resolve().parent/'runtime/felbaker/libfelbaker.so',
        Path(__file__).resolve().parents[1]/'runtime/felbaker/libfelbaker.so',
        Path('/usr/local/lib/libfelbaker.so')]
    for candidate in candidates:
        if candidate.is_file():return candidate.resolve(strict=True)
    raise RuntimeError('Native FEL comparison requires FelBaker and VapourSynth; install the optional runtime or select --fel-render-plugin')


def measure_research_quality(workflow, original, final, evidence, frames, rate, fallback):
    """Optional native comparison for the explicit separate-copy research flow."""
    plugin=getattr(workflow.args,'fel_render_plugin',None)
    if not plugin:
        return dict(fallback,publication_authorized=False,native_fel_quality_verified=False,
                    note='HDR10 fallback diagnostic only; reconstructed FEL picture quality has not been evaluated')
    from dv_render import combine_quality_views
    native=measure_fel_quality(workflow,original,final,evidence,frames,rate,'native-fel-quality',
                              plugin=plugin,python=getattr(workflow.args,'fel_render_python',None))
    result=combine_quality_views(native,fallback)
    result.update(native_fel_quality_evaluated=True,publication_authorized=False,
                  note='Weaker native FEL reconstruction and HDR10 fallback scores; research screening, not replacement approval')
    return result


def metric_command(ffmpeg,descriptors,width,height,rate,name):
    from hdr_auto import quality_graph
    if len(descriptors) not in (1,2) or any(type(fd) is not int or fd<0 for fd in descriptors):
        raise ValueError('One or two valid renderer pipes required')
    if any(type(x) is not int or x<=0 for x in (width,height)):
        raise ValueError('Positive renderer dimensions required')
    graph=quality_graph(name,rate)
    command=[ffmpeg,'-hide_banner','-nostdin','-v','warning','-xerror','-filter_complex_threads','2']
    for fd in descriptors:
        command+=['-threads','1','-f','rawvideo','-pixel_format','gbrp16le',
                  '-video_size',f'{width}x{height}','-framerate',str(Fraction(rate)),
                  '-color_primaries','bt2020','-color_trc','smpte2084',
                  '-colorspace','rgb','-color_range','pc','-i',f'pipe:{fd}']
    if len(descriptors)==1:
        graph='[0:v:0]split=2[self0][self1];'+graph.replace('[0:V:0]','[self0]').replace('[1:V:0]','[self1]')
    return command+['-filter_complex',graph,'-an','-sn','-progress','pipe:1','-nostats','-f','null','-']


def measure_fel_quality(workflow, original, final, evidence, frames, rate, label,
                        *,plugin,renderer_environment=None,python=None):
    """Compare already independently verified layers without rendered media files.

    `original` and `final` are fresh extract_layers results. `evidence` must be
    the successful complete layer_preservation_evidence result for this pair.
    The surrounding candidate service must still validate source identity,
    frame timing/geometry and copied tracks. This does not replace those checks.
    """
    import re
    from auto_optimize import quality_summary
    from job_tracking import progress
    from native_pipeline import stage
    from muxmender import stop_process_tree
    if sys.platform!='linux':raise RuntimeError('Native FEL streaming requires the qualified Linux runtime')
    if type(frames) is not int or frames<=0:raise ValueError('Complete verified frame count required')
    if not isinstance(label,str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]*',label):
        raise ValueError('Simple research directory label required')
    from dv_layer_evidence import requires_fel_reconstruction
    if (evidence.get('scope')!='layer-preservation-only' or not requires_fel_reconstruction(evidence.get('enhancement_types'))
            or evidence.get('frames')!=frames
            or any(not re.fullmatch('[0-9a-f]{64}',evidence.get(k,'')) for k in ('rpu_sha256','enhancement_video_sha256'))
            or type(evidence.get('enhancement_video_bytes')) is not int or evidence['enhancement_video_bytes']<=0):
        raise ValueError('Complete FEL preservation evidence required')
    from dv_layer_evidence import profile7_configuration
    profile7_configuration(evidence.get('configuration'))
    for inventory in (original,final):
        if (inventory.get('frames')!=frames or inventory.get('enhancement_types')!=evidence.get('enhancement_types')
                or inventory.get('configuration')!=evidence.get('configuration')
                or any(inventory.get(k)!=evidence.get(k) for k in ('rpu_sha256','enhancement_video_sha256'))):
            raise ValueError('Layer inventory does not match verified FEL pair')
    directory=Path(workflow.directory)/label;directory.mkdir()
    plugin=Path(plugin).resolve(strict=True)
    from dv_fel_runtime import child_environment
    renderer_environment=child_environment(plugin,renderer_environment)
    configuration=directory/'renderer-config';configuration.mkdir()
    renderer_environment['XDG_CONFIG_HOME']=str(configuration)
    worker=Path(__file__).with_name('dv_fel_render.py')
    meta=workflow.probe(Path(original['base']))['streams'][0]
    width,height=meta['width'],meta['height']
    other=workflow.probe(Path(final['base']))['streams'][0]
    if (width,height)!=(other['width'],other['height']):raise ValueError('FEL base geometry changed')
    scores={}
    for kind,inputs in [('self',(original,)),('candidate',(final,original))]:
        workflow.guard();progress('Native FEL streamed quality: '+kind,unit='frames',detail=f'Comparing all {frames} frames')
        processes=[];descriptors=[];logs=[]
        try:
            for index,inventory in enumerate(inputs):
                read_fd,write_fd=os.pipe();descriptors.append(read_fd)
                log=(directory/f'{kind}-renderer-{index}.log').open('xb');logs.append(log)
                command=[python or sys.executable,'-B',str(worker),'--base',inventory['base'],
                         '--enhancement',inventory['enhancement'],'--rpu',inventory['rpu'],
                         '--frames',str(frames),'--plugin',str(plugin),
                         '--ffmpeg',workflow.args.ffmpeg,'--ffprobe',workflow.args.ffprobe]
                try:
                    processes.append(subprocess.Popen(command,stdout=write_fd,stderr=log,env=renderer_environment))
                finally:os.close(write_fd)
            name=kind+'-vmaf.json'
            command=metric_command(workflow.args.ffmpeg,descriptors,width,height,rate,name)
            with (directory/(kind+'-metric.log')).open('x') as log:
                stage(command,float(Fraction(frames)/Fraction(rate)),timeout=workflow.args.timeout,stall=180,
                      guard=workflow.guard,cwd=directory,expected_frames=frames,pass_fds=descriptors,
                      observe=lambda line:log.write(line) and False)
            for process in processes:
                if process.wait(timeout=30):raise RuntimeError('Native FEL renderer failed; inspect its log')
            scores[kind]=quality_summary(json.loads((directory/name).read_text()),frames,90,90)
            if kind=='self' and not scores[kind]['passed']:raise ValueError('Native FEL self comparison failed')
        finally:
            for fd in descriptors:os.close(fd)
            for process in processes:
                if process.poll() is None:stop_process_tree(process)
                process.wait(timeout=30)
            for log in logs:log.close()
    result=dict(**scores,domain='dv-felbaker-common-render-v1',publication_authorized=False,
                intermediate_media_written=False,renderer='FelBaker',
                note='Native reconstructed FEL common-HDR metric screening; not Dolby certification')
    (directory/'native-quality.json').write_text(json.dumps(result,indent=2))
    return result
