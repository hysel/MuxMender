"""Read-only Linux diagnostics: hardware reader feasibility and damaged audio packets."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    if sys.platform != 'linux':
        raise RuntimeError('Linux-only diagnostics')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--video-request',required=True)
    parser.add_argument('--audio-request',required=True)
    args=parser.parse_args()
    args.output.mkdir(exist_ok=False)
    from job_tracking import tracked_call,progress
    def run():
        import av
        requests=json.loads(Path('/output/ui-requests/requests.json').read_text())['jobs']
        if any(j.get('state') in ('pending','running') for j in requests):
            raise RuntimeError('Production must be idle')
        os.nice(10)
        report=dict(production_changed=False,publication_authorized=False,quality_gates_changed=False)
        def source(identifier):
            p=Path(next(j for j in requests if j['id']==identifier)['source']).resolve(strict=True)
            if not p.is_relative_to('/media'):raise ValueError('Read-only source required')
            return p
        video=source(args.video_request)
        progress('NVIDIA reader · short strict feasibility check',0,2,unit='diagnostic cases',
                 detail='60-second reader check only; GPU decoding does not imply corruption recovery')
        command=['/usr/local/bin/ffmpeg','-v','error','-nostdin','-xerror',
                 '-hwaccel','cuda','-hwaccel_output_format','cuda','-c:v','h264_cuvid',
                 '-i',str(video),'-map','0:v:0','-t','60','-fps_mode','passthrough','-f','null','-']
        p=subprocess.run(command,capture_output=True,text=True,timeout=300)
        (args.output/'gpu-reader.log').write_text(p.stderr)
        report['gpu_short']=dict(exit_code=p.returncode,strict_pass=p.returncode==0 and not p.stderr.strip(),
                                 diagnostic=p.stderr[-2000:],seconds_requested=60)
        (args.output/'result.json').write_text(json.dumps(report,indent=2))
        audio=source(args.audio_request)
        progress('Audio · finding independently undecodable packets',1,2,unit='diagnostic cases',
                 detail='Complete packet scan, no concealment or repaired output')
        failures=[];packets=0;decoded=0
        with av.open(str(audio)) as container:
            track=container.streams.audio[0]
            if track.codec_context.name!='ac3':raise ValueError('This diagnostic qualifies AC3 only')
            for packet in container.demux(track):
                if not packet.size:continue
                packets+=1
                context=av.CodecContext.create('ac3','r')
                try:
                    frames=context.decode(packet)
                    decoded+=sum(frame.samples for frame in frames)
                except av.FFmpegError as exc:
                    failures.append(dict(packet=packets,pts=packet.pts,time_base=str(packet.time_base),
                        position=packet.pos,size=packet.size,error=str(exc)))
                if packets%4096==0:
                    progress('Audio · scanning source packets',1,2,unit='diagnostic cases',
                        detail=f'{packets} packets inspected; {len(failures)} decoder failures')
        report['audio_packets']=dict(packets=packets,decoded_samples=decoded,failures=failures,
                                     decoder='PyAV '+av.__version__,complete=True)
        report['complete']=True
        (args.output/'result.json').write_text(json.dumps(report,indent=2))
        progress('Controlled recovery diagnostics finished',2,2,unit='diagnostic cases',
                 detail='Read result.json; no source repair or conversion approval')
        return 0
    return tracked_call(run,'Decoder recovery — NVIDIA and audio packet diagnosis',folder=args.output/'reports')


if __name__=='__main__':raise SystemExit(main())
