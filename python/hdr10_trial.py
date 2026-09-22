"""Three-scene NVIDIA HDR10 safe-copy trial; never approves replacement."""
import argparse
import json
import math
import shutil
import subprocess
import uuid
from pathlib import Path
from types import SimpleNamespace

from hdr10plus_preserve import finalize
from job_tracking import tracked_call, progress
from native_pipeline import stage


def chroma_options(video):
    """Preserve siting in the HEVC SPS, which NVENC may omit despite AVOptions.

    This trial does no resizing or chroma subsampling: planar 4:2:0 -> P010
    changes storage layout only. Never use this to retag an arbitrary resample.
    """
    location=video.get('chroma_location')
    values={'left':0,'center':1,'topleft':2,'top':3,'bottomleft':4,'bottom':5}
    if location in (None,'unspecified'):return []
    if location not in values:raise ValueError('Unknown source chroma location: '+str(location))
    return ['-chroma_sample_location:v:0',location,'-bsf:v:0',
            'hevc_metadata=chroma_sample_loc_type='+str(values[location])]


def trial(args):
    source=args.source.resolve(strict=True)
    root=args.output_dir.resolve()/('hdr10-trial-'+uuid.uuid4().hex[:12])
    if shutil.disk_usage(args.output_dir).free < 4*1024**3:raise ValueError('Need 4 GiB free for isolated trials')
    root.mkdir(exist_ok=False)
    identity=(source.stat().st_size,source.stat().st_mtime_ns)
    def guard():
        if (source.stat().st_size,source.stat().st_mtime_ns)!=identity:raise ValueError('Source changed; stopping trial')
    def probe(path):
        p=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],
                         capture_output=True,text=True,check=True,timeout=60)
        return json.loads(p.stdout)
    def work():
        data=probe(source);duration=float(data['format']['duration'])
        video=[v for v in data['streams'] if v['codec_type']=='video']
        if len(video)!=1 or video[0]['index']!=0 or video[0].get('color_transfer')!='smpte2084' or video[0].get('pix_fmt')!='yuv420p10le':
            raise ValueError('Trial requires one 10-bit 4:2:0 PQ video at stream zero')
        if not math.isfinite(duration) or duration < 120:raise ValueError('Invalid or too short source')
        video=video[0]
        reports=[]
        for number,fraction in enumerate((.15,.5,.85),1):
            folder=root/f'scene-{number}';folder.mkdir(exist_ok=False)
            ref=folder/'original-excerpt.mkv';encoded=folder/'nvidia-encoded.mkv'
            progress(f'Extracting HDR10 scene {number}/3',directory=root)
            stage(['ffmpeg','-v','warning','-nostdin','-n','-ss',str(duration*fraction),'-i',str(source),
                   '-t','10','-map','0','-c','copy','-avoid_negative_ts','make_zero',
                   '-progress','pipe:1','-nostats',str(ref)],10,timeout=180,stall=60,guard=guard)
            reference=probe(ref);seconds=float(reference['format']['duration'])
            progress(f'Encoding NVIDIA HDR10 scene {number}/3',directory=root)
            options=chroma_options(video)
            stage(['ffmpeg','-hide_banner','-nostdin','-n','-i',str(ref),'-map','0','-map_metadata','0',
                   '-map_chapters','0','-c','copy','-c:v:0','hevc_nvenc','-preset','p5','-rc','vbr',
                   '-cq','22','-b:v','0','-pix_fmt','p010le','-color_primaries',video['color_primaries'],
                   '-color_trc',video['color_transfer'],'-colorspace',video['color_space'],
                   '-color_range',video['color_range'],*options,'-fps_mode:v','passthrough',
                   '-progress','pipe:1','-nostats',str(encoded)],seconds,0,100,timeout=600,stall=120,guard=guard)
            settings=SimpleNamespace(source=ref,encoded=encoded,output_dir=folder,mode='hdr10',timeout=1800,
                ffmpeg='ffmpeg',ffprobe='ffprobe',mkvmerge='mkvmerge',mkvextract='mkvextract',mkvpropedit='mkvpropedit')
            finalize(settings)
            report_paths=list(folder.glob('hdr10plus-preserve-*/preservation.json'))
            if len(report_paths)!=1:raise ValueError('Missing unique preservation result')
            report=json.loads(report_paths[0].read_text());reports.append(report)
            guard()
        summary=dict(source=str(source),encoder='hevc_nvenc',scenes=reports,
                     quality_approved=False,replacement_authorized=False,
                     state='preservation-verified-visual-review-required')
        (root/'trial.json').write_text(json.dumps(summary,indent=2))
        progress('Three HDR10 scenes preserved — visual review required',directory=root,
                 detail='Sample evidence only. No automatic quality approval or replacement.')
        print(json.dumps(summary,indent=2),flush=True)
    print(root,flush=True)
    return tracked_call(work,'NVIDIA static HDR10 three-scene test',folder=root)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    return trial(parser.parse_args())


if __name__=='__main__':raise SystemExit(main())
