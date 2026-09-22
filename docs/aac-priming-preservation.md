# Keeping AAC audio intact when changing containers

Some MP4 files carry instructions to skip encoder startup samples. Copying their
AAC packets into MKV without those instructions can introduce extra audio at the
beginning. A shorter final packet can also appear with a different duration in
MKV. Neither difference is approved simply by widening a timing tolerance.

The shared processing engine detects explicit AAC startup-sample instructions.
For supported timestamps it copies the original compressed audio, sets Matroska
CodecDelay with MKVToolNix, and compensates the container timestamps. It then
checks the entire decoded audio: sample hashes, sample counts, frame counts and
presentation times. Audio is not re-encoded.

Only after that proof may validation accept a missing initial packet duration or
a narrowly recognized final-packet duration representation. Packet bytes, packet
counts and timestamps still have to match. Unsupported trim instructions or
failed evidence leave the original intact. Existing quality, resolution, color,
subtitle and size checks remain unchanged.

## Qualification on September 22, 2026

A separate copy of the reported MP4 case passed:

- All 298,050 compressed AAC packets matched.
- All 298,048 decoded audio frames had identical samples and sample counts.
- Maximum decoded presentation-time difference: 0.667 milliseconds (below the
  existing 2-millisecond limit).
- The corrective remux preserved the encoded video packets, video timing and
  stream metadata.

This qualifies the observed AAC priming case, not every possible MP4 edit list.
The source media and running TrueNAS app were not changed by this test. The new
engine code needs deployment before the production queue can use it.
