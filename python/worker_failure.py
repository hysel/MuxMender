"""Expose a bounded terminal worker diagnostic when no result was created."""
import re


def terminal_reason(text):
    text=str(text)[-32768:]
    if 'Traceback (most recent call last):' not in text:return None
    text=text.rsplit('Traceback (most recent call last):',1)[1]
    matches=re.findall(r'^(?:[A-Za-z_]\w*\.)*(?:RuntimeError|ValueError|OSError|PermissionError|FileNotFoundError|TimeoutError|ProcessingTimeout): (.+)$',text,re.M)
    return matches[-1].strip()[:4096] if matches and matches[-1].strip() else None
