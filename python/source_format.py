"""Validate format identifiers, not a historical list of supported GPU formats."""
import re


def valid_pixel_format(value):
    return isinstance(value,str) and value not in ('unknown','none') and re.fullmatch(r'[a-z][a-z0-9_]{0,31}',value) is not None
