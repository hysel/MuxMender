"""Strict FFmpeg activity evidence, independent of percentage/duration estimates."""
import math


class EncoderActivity:
    def __init__(self):
        self.frames = 0
        self.microseconds = 0

    def update(self, line):
        key, separator, value = line.strip().partition('=')
        if not separator or key not in ('frame', 'out_time_us', 'out_time_ms'):
            return False
        try:
            number = int(value)
        except ValueError:
            return False
        if number < 0 or number >= 2**62:
            return False
        attribute = 'frames' if key == 'frame' else 'microseconds'
        if number <= getattr(self, attribute):
            return False
        setattr(self, attribute, number)
        return True


def timestamp_percent(line, duration):
    if not math.isfinite(duration) or duration <= 0:
        return None
    key, separator, value = line.strip().partition('=')
    if not separator or key not in ('out_time_us', 'out_time_ms'):
        return None
    try:
        number = int(value)
    except ValueError:
        return None
    if number < 0 or number >= 2**62:
        return None
    return min(100., number / duration / 10000)
