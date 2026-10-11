"""Linux-only generated-fixture diagnostics; not runtime qualification."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    if sys.platform != 'linux':
        raise RuntimeError('Run these media diagnostics on Linux only')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    from job_tracking import tracked_call, progress
    from types import SimpleNamespace
    from unittest.mock import patch
    import auto_optimize as ao
    import matroska_audio_recovery as recovery
    import av
    base = Path('/output')
    runtime = base/'ffmpeg9-full-runtime-export-20261010/bin'
    reader = base/'ffmpeg9-full-reader-export-20261010/ffprobe-cuda'
    libraries = [base/'ffmpeg9-diagnostic-host-lib-20261010',
                 base/'ffmpeg9-full-os-libs-20261010',
                 base/'ffmpeg9-full-deps-export-20261010/lib']
    os.environ['LD_LIBRARY_PATH'] = ':'.join(map(str, libraries))+':/usr/lib/x86_64-linux-gnu'
    fields = ('best_effort_timestamp_time,width,height,pix_fmt,sample_aspect_ratio,'
              'interlaced_frame,top_field_first,repeat_pict,color_primaries,color_transfer,'
              'color_space,color_range,side_data_list')
    report = dict(qualification=False, production_changed=False, quality_gates_changed=False,
                  pyav_version=av.__version__,pyav_library_versions=av.library_versions,
                  host_library_sha256=hashlib.sha256((libraries[0]/'libnuma.so.1').read_bytes()).hexdigest(),
                  reader=[], audio=[])

    def command(argv, env=None):
        p = subprocess.run(list(map(str, argv)), capture_output=True, text=True,
                           timeout=60, env=env)
        if p.returncode:
            raise RuntimeError(p.stderr[-3000:])
        return p.stdout

    def save():
        (args.output/'result.json').write_text(json.dumps(report, indent=2))

    def run():
        save()
        with tempfile.TemporaryDirectory(prefix='fixtures-', dir=args.output) as folder:
            temp = Path(folder)
            progress('Comparing generated HEVC CPU/GPU frame evidence', directory=args.output)
            for hdr in (False, True):
                source = temp/('hdr.mkv' if hdr else 'sdr.mkv')
                command([runtime/'ffmpeg','-v','error','-nostdin','-n','-f','lavfi','-i',
                    'testsrc2=size=320x180:rate=12:duration=2','-c:v','hevc_nvenc',
                    '-preset','p4','-cq','18','-pix_fmt','yuv420p10le',
                    '-color_primaries','bt2020' if hdr else 'bt709',
                    '-color_trc','smpte2084' if hdr else 'bt709',
                    '-colorspace','bt2020nc' if hdr else 'bt709',source])
                evidence=[]
                for label,binary,gpu in [('cpu',runtime/'ffprobe',False),('gpu',reader,True)]:
                    env=dict(os.environ,MUXMENDER_RESEARCH_CUDA_READER='1' if gpu else '0')
                    data=json.loads(command([binary,'-v','error','-select_streams','v:0',
                        '-show_frames','-show_entries','frame='+fields,'-of','json',source],env))
                    (args.output/(('hdr' if hdr else 'sdr')+'-'+label+'.json')).write_text(json.dumps(data,indent=2))
                    evidence.append(data['frames'])
                changes=[dict(frame=i+1,differences={k:dict(cpu=a.get(k),gpu=b.get(k))
                    for k in sorted(set(a)|set(b)) if a.get(k)!=b.get(k) or (k in a)!=(k in b)})
                    for i,(a,b) in enumerate(zip(*evidence)) if a!=b]
                report['reader'].append(dict(hdr=hdr,counts=list(map(len,evidence)),changes=changes))
                save()
            progress('Comparing generated DTS packet and decoded-sample evidence',directory=args.output)
            for label,bin_dir in [('baseline',Path('/usr/local/bin')),('candidate',runtime)]:
                root=temp/label;root.mkdir()
                source=root/'source.mkv';output=root/'output.mkv'
                command([bin_dir/'ffmpeg','-v','error','-nostdin','-f','lavfi','-i',
                    'testsrc2=size=64x64:rate=24:duration=2','-f','lavfi','-i',
                    'sine=frequency=440:sample_rate=48000:duration=2','-c:v','libx264',
                    '-threads:v','2','-color_primaries','bt709','-color_trc','bt709',
                    '-colorspace','bt709','-color_range','tv','-c:a','dca','-strict','-2',source])
                opts=SimpleNamespace(ffmpeg=str(bin_dir/'ffmpeg'),ffprobe=str(bin_dir/'ffprobe'),
                                     timeout=60,source=source,vmaf_mean=90,vmaf_p5=90)
                work=ao.Workflow(opts,root,lambda:None);before=work.probe(source)
                info=SimpleNamespace(bit_depth=8,hdr=False,dolby_vision=False,mastering_display_metadata=None)
                error='[aost#0:1/copy @ 0x123] Non-monotonic DTS; previous: 484795, current: 484747; Error submitting a packet to the muxer: Invalid argument'
                with patch.object(ao.mm,'encoder_options',return_value=['-c:v','libx264','-crf','18']):
                    recovery.recover(work,source,output,dict(codec='h264',encoder='libx264',quality='compact'),
                                     info,before,'full-encode',float(before['format']['duration']),error)
                row=dict(runtime=label,files=[])
                frames=work.frame_file(source,'source',before['format'])
                row['full_preservation_frames']=work.validate(source,output,before,'h264',
                    'diagnostic-full-preservation',frames)
                relay=root/'output-audio-recovery-packets.mka'
                for name,file in [('source',source),('relay',relay),('output',output)]:
                    data=json.loads(command([bin_dir/'ffprobe','-v','error','-select_streams','a:0',
                        '-show_packets','-show_data_hash','sha256','-of','json',file]))
                    (args.output/(label+'-'+name+'-packets.json')).write_text(json.dumps(data,indent=2))
                    pcm=root/(name+'.pcm')
                    command([bin_dir/'ffmpeg','-v','error','-nostdin','-i',file,'-map','0:a:0',
                             '-c:a','pcm_s16le','-f','s16le',pcm])
                    row['files'].append(dict(name=name,packet_count=len(data['packets']),
                        tail=data['packets'][-2:],pcm_bytes=pcm.stat().st_size,
                        pcm_sha256=hashlib.sha256(pcm.read_bytes()).hexdigest()))
                    with av.open(str(file)) as container:
                        packets=[dict(pts=p.pts,dts=p.dts,duration=p.duration,time_base=str(p.time_base))
                                 for p in container.demux(*container.streams.audio) if p.size]
                    row['files'][-1]['pyav_packet_tail']=packets[-2:]
                    other=Path('/usr/local/bin/ffprobe') if label=='candidate' else runtime/'ffprobe'
                    cross=json.loads(command([other,'-v','error','-select_streams','a:0',
                        '-show_packets','-of','json',file]))
                    row['files'][-1]['other_runtime_tail']=cross['packets'][-2:]
                report['audio'].append(row);save()
        report['temporary_media_removed']=True;save()
        return 0
    return tracked_call(run,'FFmpeg exported-runtime mismatch investigation',folder=args.output)


if __name__=='__main__':
    raise SystemExit(main())
