"""One evidence-triggered rate-control experiment, never an approval policy."""
import math


def rate_retry(report, source_bytes, duration):
    """Keep failed HEVC settings, changing only its peak-rate ceiling.

    Six times source average is a bounded trial heuristic, not a measured peak
    or a universal encoder limit. Runtime and media validation remain required.
    Never spend this retry on size-only failures or processing errors.
    """
    if (type(source_bytes) is not int or source_bytes <= 0 or
            not isinstance(duration, (int, float)) or isinstance(duration, bool) or
            not math.isfinite(duration) or duration <= 0):
        return None
    ceiling = min(1000, max(20, math.ceil(source_bytes * 8 / duration / 1e6 * 6)))
    choices = []
    for trial in report.get('trials', []):
        settings = trial.get('settings', {})
        samples = trial.get('samples', [])
        if (trial.get('encoder') != 'hevc_nvenc' or settings.get('encoder') != 'hevc_nvenc' or
                trial.get('runtime_supported') is not True or trial.get('playback_compatible') is not True or
                settings.get('nvenc_maxrate_mbps') is not None or trial.get('error') or
                any(s.get('error') for s in samples)):
            continue
        failed = [s['quality']['p5'] for s in samples
                  if s.get('quality', {}).get('passed') is False and
                  s.get('preservation_pass') is True and s.get('decode_pass') is True and
                  isinstance(s.get('quality', {}).get('p5'), (int, float)) and
                  math.isfinite(s['quality']['p5'])]
        if failed:
            choices.append((min(failed), trial.get('id', ''), settings))
    if not choices:
        return None
    _, parent, settings = max(choices, key=lambda row: (row[0], row[1]))
    return dict(settings=dict(settings, nvenc_maxrate_mbps=ceiling), parent_trial=parent,
                policy='source-average-times-six-v1', source_average_mbps=source_bytes * 8 / duration / 1e6,
                maximum_additional_trials=1, quality_thresholds_unchanged=True)
