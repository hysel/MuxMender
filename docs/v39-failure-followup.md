# Follow-up to the v39 run

Development only; the deployed image and queue have not been changed.

## Implemented, awaiting real-case qualification

- DV sample decode validation now uses a microsecond output clock and passthrough
  frame timing in its null sink. A generated variable-timing clip reproduced the
  old duplicate-DTS diagnostic and passed with the new options. Candidate files
  are not modified, and strict decoder diagnostics are still fatal.
- HDR mismatch errors retain bounded source/output metadata values. Cleanup had
  removed the frame manifests needed to diagnose two failed trials, so these
  failures must be reproduced before a preservation change can be justified.
- Full-output savings rejections show actual GB/percentage saved, the required
  percentage, and whether full validation was performed. Sample rejections count
  size versus measured-quality failures, without claiming the source is optimal.

## Remaining investigation

### September 25 follow-up

Seven historical failed inputs were manually replaced by the owner. They are
not retry targets and their replacement files must not be treated as the same
qualification sources.

The remaining audio failure was reproduced in the source itself. Its final AC3
packet is 1,040 bytes, after 152,308 earlier packets; the preceding packets
inspected at the tail are 2,560 bytes each. Strict decoding reports an
incomplete frame. An audio repair requires an
explicit separate-copy experiment, not silently dropping the packet.

The remaining HDR case changes content-light metadata within a scene. A shared
frame-associated restoration path is under real-source testing; see
[changing HDR brightness](changing-hdr-brightness.md). Quality gates are unchanged.

- Two copied-packet failures involve TrueHD stream 1: packet 2 has no timestamp
  in the source; adjacent packets have 0 and 2 ms. The reported output supplies
  1 ms. This is a recovery hypothesis, not permission to ignore absent timestamps.
  Require coded/decoded audio timing, sample-count and payload evidence first.
  A development recovery path now requires identical ordered compressed payloads,
  bounded interior timestamp reconstruction, and complete decoded PCM/sample/timing
  equality. Negative integration tests confirm PCM changes and other codecs still
  fail. A generated TrueHD remux compared 1,200 decoded frames with identical PCM
  and zero timing delta. Real-case full-file qualification remains outstanding.
- One full mux failed on PGS subtitle stream 3 with backwards DTS. Test a
  packet-preserving muxer route and validate presentation cues, not sorting or
  dropping packets blindly.
  Read-only source inspection confirms the original order jumps from 849.849 to
  847.096 seconds. This is not a newly introduced encoder timestamp change.
- One source AC3 decode fails on an incomplete frame. Locate the damaged data;
  do not silently discard audio or waive strict decoding.
- Improve sampling near the savings boundary. Two full outputs missed the
  target despite eligible samples. No guarantee can be inferred from three scenes.

No originals were replaced by development tests. No new image was built.
