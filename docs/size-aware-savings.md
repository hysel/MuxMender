# A worthwhile saving depends on file size

New requests default to size-aware savings: save the smaller of 25% of the
original or 1 GB, with a 100 MB minimum. These are decimal units. A 2 GB video
must save 500 MB; a 20 GB video must save 1 GB. Files too small to satisfy the
minimum are kept without an encode.

Choose a fixed percentage instead if preferred. Existing queued requests retain
their original fixed targets; deployment does not silently change them.

The preview lists each file's target. Samples use the equivalent percentage to
screen candidates, but remain estimates. Full outputs must meet the actual byte
requirement, and replacement independently checks it again. Quality, resolution,
HDR, timing, audio and subtitle checks are unchanged. Lower percentages for large
files are not permission to lower quality.

The standalone automatic command accepts `--savings-mode size-aware` (default)
or `--savings-mode fixed --minimum-savings-percent 20`.
