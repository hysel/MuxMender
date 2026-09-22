"""Narrow, per-encoder trial deduplication; never an input-wide rejection gate."""
import re


def structural_failure_code(message):
    # These are layout/signaling failures that changing CQ/preset cannot repair.
    # Do not classify quality scores, frame loss, decode errors, resource errors,
    # arbitrary subprocess errors or timeouts: they may have another viable path.
    if re.fullmatch(r'Frame \d+: chroma location changed', message):
        return 'chroma_siting_preservation'
    prefixes = {
        'Requires exactly one moving video track (cover pictures are separate)': 'source_video_layout',
        'HDR finalizer requires one moving video track': 'source_video_layout',
        'Cover picture precedes the movie track; stream ordering needs specialized handling': 'source_video_layout',
        'Interleaved cover artwork needs stream-order-preserving remux support': 'source_video_layout',
        'Cover artwork needs a supported image codec, filename and MIME type': 'source_artwork_layout',
        'Attachment payload hash unavailable': 'attachment_evidence_unavailable',
    }
    return prefixes.get(message)


def previous_structural_failure(trials, encoder):
    for trial in trials:
        if trial.get('encoder') == encoder and trial.get('structural_failure'):
            return trial
    return None
