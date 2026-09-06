"""Size eligibility is separate from structural and playback verification."""
import math


def savings_summary(size_pairs):
    """Aggregate accepted outputs; percentage is weighted by source bytes."""
    pairs = list(size_pairs)
    source = sum(a for a, b in pairs)
    output = sum(b for a, b in pairs)
    saved = source - output
    return dict(files=len(pairs), source_bytes=source, output_bytes=output,
                saved_bytes=saved, saved_MB=saved/10**6, saved_GB=saved/10**9,
                saved_TB=saved/10**12, saved_percent=100*saved/source if source else 0,
                basis='Accepted output size reduction; originals and intermediates retained unless explicitly removed. Decimal MB/GB/TB; not measured disk space reclaimed.')


def savings_summary_text(summary):
    return (f"Size reduction across {summary['files']} accepted output(s): "
            f"{summary['saved_MB']:,.2f} MB / {summary['saved_GB']:,.3f} GB / "
            f"{summary['saved_TB']:.6f} TB ({summary['saved_percent']:.2f}%). "
            'Retained originals/intermediates still occupy disk space.')


class NoSavingsError(ValueError):
    """Stop optimization while retaining the original and diagnostic outputs."""


def savings_decision(source_bytes, output_bytes, minimum_percent=5.0):
    if source_bytes <= 0 or output_bytes <= 0:
        raise ValueError('Positive source and output sizes are required')
    if not math.isfinite(minimum_percent) or not 0 <= minimum_percent < 100:
        raise ValueError('Minimum savings must be finite and in [0,100)')
    savings = 100 * (source_bytes-output_bytes) / source_bytes
    eligible = output_bytes < source_bytes and savings >= minimum_percent
    reason = ('meets size threshold; preservation and playback checks still required' if eligible else
              'output is larger than or equal to the source; keep original' if output_bytes >= source_bytes else
              'savings are below the minimum; keep original')
    return dict(eligible=eligible, savings_percent=savings,
                minimum_percent=minimum_percent, source_bytes=source_bytes,
                output_bytes=output_bytes, reason=reason)
