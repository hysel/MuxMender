"""Isolated rate-control diagnosis; outputs are not publication candidates."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from auto_optimize import quality_command, quality_summary
from hdr_auto import quality_graph
from job_tracking import tracked_call, progress
from native_pipeline import stage


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--ffmpeg',required=True)
    p.add_argument('--ffprobe',required=True)
    p.add_argument('--matrix',choices=('initial','ceiling'),default='initial')
    a=p.parse_args()
    a.root.mkdir(parents=True,exist_ok=False)
    data=json.loads(subprocess.check_output([a.ffprobe,'-v','error','-select_streams','v:0',
        '-show_streams','-of','json',str(a.reference)],text=True))['streams'][0]
    identity=(a.reference.stat().st_size,a.reference.stat().st_mtime_ns)
    def guard():
        if (a.reference.stat().st_size,a.reference.stat().st_mtime_ns)!=identity:
            raise ValueError('Reference changed')
        if shutil.disk_usage(a.root).free<2*1024**3:raise ValueError('Low scratch space')
    variants=[('cq18',['-tune','hq','-rc','vbr','-cq','18','-b:v','0']),
              ('cq12',['-tune','hq','-rc','vbr','-cq','12','-b:v','0']),
              ('qp18',['-tune','hq','-rc','constqp','-qp','18']),
              ('lossless',['-tune','lossless','-rc','constqp','-qp','0'])]
    if a.matrix=='ceiling':
        variants=[('cq18-cap200m',['-tune','hq','-rc','vbr','-cq','18','-b:v','0','-maxrate','200M','-bufsize','400M']),
                  ('cq25-cap200m',['-tune','hq','-rc','vbr','-cq','25','-b:v','0','-maxrate','200M','-bufsize','400M']),
                  ('cq32-default',['-tune','hq','-rc','vbr','-cq','32','-b:v','0'])]
    state=dict(state='running',started=time.time(),total=len(variants)+1,steps=[])
    def save():
        state['updated']=time.time()
        temp=a.root/'batch-status.tmp'
        temp.write_text(json.dumps(state,indent=2));temp.replace(a.root/'batch-status.json')
    def execute():
        for index,(name,options) in enumerate([('self',None),*variants],1):
            row=dict(name=name,state='running',started=time.time())
            state['steps'].append(row);state['current']=index;save()
            try:
                candidate=a.reference
                if options is not None:
                    candidate=a.root/(name+'.mkv')
                    progress('Testing NVIDIA rate control: '+name,completed=index-1,total=len(variants)+1)
                    cmd=[a.ffmpeg,'-hide_banner','-nostdin','-n','-v','error','-copyts','-i',str(a.reference),
                         '-map','0:v:0','-frames:v','72','-c:v','hevc_nvenc','-preset','p7',*options,
                         '-pix_fmt','p010le','-fps_mode','passthrough','-enc_time_base','demux',
                         '-color_primaries',data['color_primaries'],'-color_trc',data['color_transfer'],
                         '-colorspace',data['color_space'],'-color_range',data['color_range'],
                         '-progress','pipe:1',str(candidate)]
                    stage(cmd,3,timeout=180,stall=60,guard=guard,expected_frames=72)
                    row['bytes']=candidate.stat().st_size
                progress('Checking identical HDR render: '+name,completed=index-1,total=len(variants)+1)
                graph=quality_graph(name+'-vmaf.json',data['avg_frame_rate'],72)
                stage(quality_command(a.ffmpeg,candidate,a.reference,graph),3,timeout=600,stall=120,
                      guard=guard,cwd=a.root,expected_frames=72)
                row['quality']=quality_summary(json.loads((a.root/(name+'-vmaf.json')).read_text()),72,90,90)
                row['state']='passed'
                if name=='self' and not row['quality']['passed']:raise ValueError('Self-check failed')
            except Exception as exc:
                row.update(state='failed',error=str(exc))
            row['finished']=time.time();save()
            if name=='self' and row['state']=='failed':break
        guard()
        state.update(state='completed' if all(s['state']=='passed' for s in state['steps']) else 'completed-with-failures',finished=time.time())
        save()
        progress('Rate-control diagnostic complete',completed=len(state['steps']),total=len(variants)+1,
                 detail='Diagnostic scores only; no metadata qualification or replacement')
    return tracked_call(execute,'Older NVIDIA HDR rate-control investigation',folder=a.root/'reports')


if __name__=='__main__':raise SystemExit(main())
