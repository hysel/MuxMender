"""Small, bounded wall-time counters; never alter processing decisions."""


def category(phase):
    label=str(phase).lower()
    if label.startswith('verifying file checksum:'):return 'checksums'
    if label.startswith(('checking frame timing:', 'checking hdr frame timing:', 'comparing frame geometry')):return 'frame_validation'
    if label.startswith(('checking copied track:', 'checking all copied tracks:',
                         'organizing copied-track', 'comparing copied track', 'reusing verified sample', 'reusing verified source')):return 'track_validation'
    if label.startswith(('reading media metadata:', 'inspecting legacy color')):return 'metadata'
    if label.endswith('-quality'):return 'quality_measurement'
    if label.endswith('-decode'):return 'full_decode'
    if label.startswith('reference-'):return 'sample_extraction'
    if label=='full-encode' or label.startswith(('hevc_nvenc-', 'av1_nvenc-', 'hevc_amf-', 'av1_amf-',
                                               'hevc_qsv-', 'av1_qsv-', 'libx265-', 'libsvtav1-', 'libaom-av1-')):
        return 'encoding'
    return 'other'


def accumulate(totals, phase, seconds):
    key=category(phase)
    totals[key]=totals.get(key,0.0)+max(0.0,seconds)
