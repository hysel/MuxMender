"""Reproduce fractional MP4 start-time rounding with tiny generated media only."""
import argparse
import json
from pathlib import Path
import subprocess
from unittest.mock import patch
from auto_optimize import encode_command,compare_frames


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg',default='ffmpeg');parser.add_argument('--ffprobe',default='ffprobe')
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();root=args.output_dir;root.mkdir(exist_ok=False)
    source=root/'generated.mp4'
    def run(command):subprocess.run(list(map(str,command)),check=True,capture_output=True,timeout=90)
    run([args.ffmpeg,'-v','error','-nostdin','-n','-f','lavfi','-i','testsrc2=size=320x180:rate=24000/1001',
         '-t','2','-c:v','libx264','-preset','ultrafast','-crf','18','-video_track_timescale','1000',
         '-output_ts_offset','0.094','-avoid_negative_ts','disabled',source])
    data=json.loads(subprocess.check_output([args.ffprobe,'-v','error','-show_streams','-of','json',str(source)]))
    def frames(path):
        result=subprocess.check_output([args.ffprobe,'-v','error','-select_streams','v:0','-show_frames',
            '-show_entries','frame=best_effort_timestamp_time,width,height,pix_fmt,sample_aspect_ratio,interlaced_frame,repeat_pict,color_range,color_space,color_transfer,color_primaries',
            '-of','compact=p=0',str(path)])
        target=root/(path.stem+'-frames.txt');target.write_bytes(result);return target
    original=frames(source);results={}
    for label,fix in [('old-clock',False),('demux-clock',True)]:
        output=root/(label+'.mkv')
        # CPU is strictly a tiny deterministic fixture, not a production fallback.
        with patch('auto_optimize.mm.encoder_options',return_value=['-c:v','libx264','-preset','ultrafast','-crf','18']):
            command=encode_command(args.ffmpeg,source,output,{'codec':'hevc','encoder':'hevc_nvenc','quality':'balanced'},None,data['streams'])
        if not fix:
            index=command.index('-enc_time_base:v:0');del command[index:index+2]
        run(command)
        try:results[label]={'frames':compare_frames(original,frames(output)),'passed':True}
        except ValueError as exc:results[label]={'passed':False,'error':str(exc)}
    (root/'result.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))
    if not results['demux-clock']['passed']:raise ValueError('Demux timestamp fix failed')


if __name__=='__main__':main()
