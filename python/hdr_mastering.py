"""Exact mastering-display payloads and complete source-timeline summaries."""
from fractions import Fraction
import struct


def mastering_payload(frame):
    rows=[s for s in frame.get('side_data_list',[]) if s.get('side_data_type')=='Mastering display metadata']
    if not rows:return None
    if len(rows)!=1:raise ValueError('Ambiguous mastering-display metadata')
    row=rows[0]
    # HEVC serializes G/B/R coordinates, then white point and max/min luminance.
    keys=('green_x','green_y','blue_x','blue_y','red_x','red_y',
          'white_point_x','white_point_y','max_luminance','min_luminance')
    values=[]
    for i,key in enumerate(keys):
        try:value=Fraction(str(row[key]))*(50000 if i<8 else 10000)
        except (KeyError,ValueError,TypeError,ZeroDivisionError) as exc:
            raise ValueError('Invalid mastering-display field: '+key) from exc
        if value.denominator!=1 or not 0<=value<2**(16 if i<8 else 32):
            raise ValueError('Mastering-display value is not exactly representable in HEVC: '+key)
        values.append(int(value))
    return struct.pack('>8H2I',*values)


def mastering_timeline(frames,guard=lambda:None):
    count=present=changes=0;first=previous=None;initialized=False
    for frame in frames:
        if count%4096==0:guard()
        payload=mastering_payload(frame);count+=1;present+=payload is not None
        if not initialized:first=payload;initialized=True
        elif payload!=previous:changes+=1
        previous=payload
    if not count:raise ValueError('No decoded mastering-display timeline')
    return dict(frames=count,present_frames=present,changes=changes,
                changing=changes>0,complete=present==count,
                first_payload=first.hex() if first is not None else None,
                method='complete-decoded-mastering-display-timeline')


def constrain_candidates(report,timeline,source_codec):
    """Record a source-derived limitation of the current HEVC-to-AV1 finalizer.

    This finalizer restores HDR10+/CLL, but cannot encode arbitrary changing
    HEVC mastering values exactly in AV1's different fixed-point units. Keep
    constant-mastering AV1 trials available and evaluate preserved alternatives.
    """
    if source_codec!='hevc' or not timeline.get('changing'):return False
    if not report.get('source_id') or type(timeline.get('frames')) is not int or timeline['frames']<=0:
        raise ValueError('Complete source mastering evidence required')
    report['full_source_mastering']=dict(timeline,source_id=report['source_id'])
    for trial in report.get('trials',[]):
        if trial.get('codec')=='av1':
            trial['full_source_preservation']=dict(supported=False,
                reason='Current AV1 finalizer cannot preserve this changing mastering-display timeline exactly',
                source_id=report['source_id'],frames=timeline['frames'])
    return True


def resume_preservable_candidates(report,minimum,evaluate,guard=lambda:None):
    """Resume checks deferred behind an incumbent now disproved on full metadata."""
    from candidate_validation import encoded_size
    from codec_selection import select_candidate
    for trial in sorted(report.get('trials',[]),key=lambda t:encoded_size(report,t) or float('inf')):
        guard()
        if trial.get('codec')=='av1' or not trial.get('validation_dominance'):continue
        trial['superseded_validation_dominance']=trial.pop('validation_dominance')
        evaluate(trial)  # Complete quality/preservation checks; never approve by size.
        decision=select_candidate(report,minimum)
        if decision['action']=='encode_copy':return decision
    return select_candidate(report,minimum)
