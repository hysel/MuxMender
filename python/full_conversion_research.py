"""Full-copy experiment using the shared encoder and validator; never publishes."""
from pathlib import Path
import os

from dvd_av1_batch import save
from job_tracking import progress, workflow_stage
from task_progress import digest


def require_read_only(source):
    if not hasattr(os, 'statvfs') or not os.statvfs(source).f_flag & os.ST_RDONLY:
        raise ValueError('Full research requires an OS-enforced read-only source mount')


def finish(workflow, source, data, info, settings, baseline, source_hash,
           duration, savings_policy, decision, state):
    """Sample rejection does not prevent measurement, but is never erased."""
    directory = workflow.directory
    output = directory / ('research-full-av1' + workflow.output_suffix)
    state.update(research_only=True, publication_authorized=False,
                 original_retained=True, sample_decision=decision,
                 quality_thresholds=dict(mean=workflow.args.vmaf_mean, p5=workflow.args.vmaf_p5),
                 candidate=str(output), settings=settings)
    save(directory / 'status.json', state)
    try:
        workflow_stage('encode')
        workflow.encode_preserving_color(source, output, settings, info, data,
                                         'research-full-encode', duration)
        state.update(source_bytes=baseline['size'], output_bytes=output.stat().st_size,
                     saved_percent=100 * (1 - output.stat().st_size / baseline['size']))
        state['size_pass'] = (output.stat().st_size < baseline['size'] and
            baseline['size'] - output.stat().st_size >= savings_policy['required_bytes'])
        save(directory / 'status.json', state)
        workflow_stage('validate')
        frames = workflow.frame_cache.get(str(source.resolve())) if workflow.hdr_mode else None
        if frames is None:
            frames = workflow.frame_file(source, 'research-full-source', data['format'])
        workflow.validate(source, output, data, settings['codec'], 'research-full', frames)
        state['preservation_pass'] = True
        save(directory / 'status.json', state)
        count = workflow.compare_frame_files(frames, frames)
        quality = workflow.quality(source, output, 'research-full', count, duration)
        state['full_quality'] = quality
        if digest(source, workflow.guard) != source_hash:
            raise ValueError('Source hash changed; research result invalid')
        state.update(source_sha256=source_hash, output_sha256=digest(output, workflow.guard),
                     state='research-completed-not-approved',
                     all_checks_passed=(decision.get('action') == 'encode_copy' and
                                        state['size_pass'] and quality['passed']))
        progress('Full research completed — no replacement authorized', directory=directory,
                 detail='Separate output retained. See status.json for sample, full quality, preservation and size results.')
    except BaseException as exc:
        state.update(state='research-stopped-not-approved', error=str(exc))
        raise
    finally:
        # The requested experimental copy stays available, including failures.
        # The shared caller's finalizer removes intermediate work and raw metrics.
        save(directory / 'status.json', state)
    return 0
