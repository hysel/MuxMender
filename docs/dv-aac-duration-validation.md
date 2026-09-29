# Dolby Vision: checking an omitted AAC duration

A full conversion stopped because its validator expected every audio packet
to include a duration field. A separate remux reproduced the issue: the first
AAC packet kept its compressed bytes and timestamps, but FFmpeg omitted its
duration field. Some later durations used different millisecond rounding.

The shared full-file Dolby Vision validator now identifies this representation
case instead of crashing with a missing-field error. It does not invent a
duration or approve the file merely because its packets match. Every affected
track must also pass the existing shared decoded-audio comparison: PCM hashes,
sample counts, frame durations and presentation timing. The existing timing
tolerance is unchanged. Audio bytes or timestamps changing still fails the
compressed-packet check before this proof is attempted.

Both full conversion and retained-output verification use the same proof helper.
The helper reports progress and writes frame hashes, not a large decoded-audio
file. Regression tests cover missing duration, changed payloads and timestamps,
and identical decoded bytes presented at a different time.

Full-length media qualification remains a separate development job. Passing
unit tests alone does not approve a conversion or authorize source replacement.
