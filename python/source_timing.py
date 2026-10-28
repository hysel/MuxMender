"""Read-only terminal timing preflight; full-file validation remains mandatory."""
from fractions import Fraction
import math
import subprocess

from artifact_manifest import stamp
from task_progress import run_probe


def terminal_conflict(frames, packets):
    """Confirm a decoded clock conflict against the original compressed packets."""
    by_position={str(row['pos']):row for row in packets if row.get('pos') not in (None,'N/A')}
    previous=None
    for frame in frames:
        raw=frame.get('pts_time')
        if raw in (None,'N/A'):continue
        point=Fraction(raw)
        if previous is not None and point<=previous[0]:
            left,right=by_position.get(str(previous[1].get('pkt_pos'))),by_position.get(str(frame.get('pkt_pos')))
            if left and right and left['pos']!=right['pos'] and all(
                    p.get('pts_time') not in (None,'N/A') and Fraction(p['pts_time'])==value
                    for p,value in ((left,previous[0]),(right,point))):
                return dict(previous_pts=str(previous[0]),pts=str(point),
                            previous_packet=left['pos'],packet=right['pos'])
        previous=(point,frame)
    return None


def check_tail(workflow, source, metadata):
    """Catch terminal source defects before full encoding, without a full decode."""
    from auto_optimize import compact_rows
    from dvd_av1_batch import save
    duration=float(metadata['format']['duration'])
    start=float(metadata['format'].get('start_time',0))
    if not math.isfinite(duration) or duration<=0 or not math.isfinite(start):
        raise ValueError('Invalid source duration for terminal timing check')
    identity=stamp(source);workflow.guard()
    interval=str(max(start,start+duration-10))+'%'
    frames=workflow.directory/'source-tail-frames.jsonl'
    base=[workflow.args.ffprobe,'-v','error','-threads','2',
          *workflow.reader_input_options(source),*workflow.decoder_options(source),
          '-read_intervals',interval,'-select_streams','V:0']
    try:
        run_probe([*base,'-show_frames','-show_entries','frame=pts_time,best_effort_timestamp_time,pkt_pos',
                   '-of','compact=p=0',str(source)],frames,'Checking original terminal timestamps',
                  workflow.args.timeout,workflow.guard,10,max(start,start+duration-10))
    except subprocess.CalledProcessError:
        # Some otherwise readable containers cannot seek. A failed optional seek
        # is not evidence of a defective source; the normal full audit still runs.
        workflow.guard()
        if stamp(source)!=identity:raise ValueError('Source changed during terminal timing check')
        save(workflow.directory/'source-tail-timing.json',dict(scope='terminal-window-only',
             state='inconclusive',reason='Terminal seek unavailable; complete validation required',
             full_validation_still_required=True,source_unchanged=True))
        return
    # A seek can yield incomplete evidence in some containers. It cannot approve
    # a file, nor replace the complete frame audit. Only packet-confirmed defects
    # are rejected here; ordinary decoder errors remain for full validation.
    rows=list(compact_rows(frames,'pts_time'))
    suspects=any(Fraction(b['pts_time'])<=Fraction(a['pts_time']) for a,b in zip(rows,rows[1:])
                 if a['pts_time']!='N/A' and b['pts_time']!='N/A')
    conflict=None
    if suspects:
        packets=workflow.directory/'source-tail-all-packets.txt'
        run_probe([*base,'-show_packets','-show_entries','packet=pts_time,pos','-of','compact=p=0',str(source)],
                  packets,'Confirming original timestamp conflict',workflow.args.timeout,workflow.guard)
        conflict=terminal_conflict(rows,compact_rows(packets,'pos'))
    workflow.guard()
    if stamp(source)!=identity:raise ValueError('Source changed during terminal timing check')
    save(workflow.directory/'source-tail-timing.json',dict(
        scope='terminal-window-only',seconds=10,decoded_frames=len(rows),
        conflict=conflict,full_validation_still_required=True,source_unchanged=True))
    if conflict:
        raise ValueError('Original video has conflicting presentation timestamps near its end. '
                         'Original retained before full encoding; a separate timestamp repair would be required.')
